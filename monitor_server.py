#!/usr/bin/env python3
"""System Performance Monitor — HTTP API server."""

import json
import time
import signal
import psutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

START_TIME = time.time()


def get_stats():
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
    cpu_freq = psutil.cpu_freq()
    cpu_count = psutil.cpu_count(logical=True)
    cpu_physical = psutil.cpu_count(logical=False)

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    disk = psutil.disk_usage("/")
    try:
        disk_io = psutil.disk_io_counters()
        disk_read = disk_io.read_bytes
        disk_write = disk_io.write_bytes
    except Exception:
        disk_read = disk_write = 0

    try:
        net_io = psutil.net_io_counters()
        net_sent = net_io.bytes_sent
        net_recv = net_io.bytes_recv
    except Exception:
        net_sent = net_recv = 0

    # Top processes by CPU
    processes = []
    for p in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]),
                    key=lambda x: x.info.get("cpu_percent") or 0, reverse=True)[:10]:
        try:
            processes.append({
                "pid": p.info["pid"],
                "name": p.info["name"],
                "cpu": round(p.info.get("cpu_percent") or 0, 1),
                "mem": round(p.info.get("memory_percent") or 0, 1),
                "status": p.info.get("status", ""),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Battery
    battery = None
    try:
        b = psutil.sensors_battery()
        if b:
            battery = {
                "percent": round(b.percent, 1),
                "plugged": b.power_plugged,
                "secsleft": b.secsleft if b.secsleft != psutil.POWER_TIME_UNLIMITED else -1,
            }
    except Exception:
        pass

    uptime = int(time.time() - psutil.boot_time())

    return {
        "timestamp": time.time(),
        "uptime": uptime,
        "cpu": {
            "percent": cpu_percent,
            "per_core": cpu_per_core,
            "count_logical": cpu_count,
            "count_physical": cpu_physical,
            "freq_current": round(cpu_freq.current, 0) if cpu_freq else None,
            "freq_max": round(cpu_freq.max, 0) if cpu_freq else None,
        },
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "percent": swap.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
            "read_bytes": disk_read,
            "write_bytes": disk_write,
        },
        "network": {
            "bytes_sent": net_sent,
            "bytes_recv": net_recv,
        },
        "processes": processes,
        "battery": battery,
    }


def kill_process(pid, force=False):
    """Send SIGTERM or SIGKILL to a process. Returns (ok, message)."""
    try:
        p = psutil.Process(pid)
        name = p.name()
        if force:
            p.kill()   # SIGKILL
            return True, f"Force killed '{name}' (PID {pid})"
        else:
            p.terminate()  # SIGTERM
            return True, f"Terminated '{name}' (PID {pid})"
    except psutil.NoSuchProcess:
        return False, f"Process {pid} not found"
    except psutil.AccessDenied:
        return False, f"Access denied — cannot kill PID {pid}"
    except Exception as e:
        return False, str(e)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/kill":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
                pid = int(payload["pid"])
                force = bool(payload.get("force", False))
                ok, msg = kill_process(pid, force)
                result = json.dumps({"ok": ok, "message": msg}).encode()
                self.send_response(200 if ok else 400)
            except Exception as e:
                result = json.dumps({"ok": False, "message": str(e)}).encode()
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(result)))
            self.end_headers()
            self.wfile.write(result)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/stats":
            data = json.dumps(get_stats()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif path in ("/", "/monitor"):
            with open("monitor.html", "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    PORT = 8765
    # Warm up cpu_percent (first call always returns 0)
    psutil.cpu_percent(interval=None, percpu=True)
    time.sleep(0.2)

    print(f"System Monitor running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    server = HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
