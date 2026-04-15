#!/usr/bin/env python3
"""
MeetingMeter — standalone launcher.
This is the PyInstaller entry point. It bundles the server, UI, and control
window into one executable that works on any Mac or Windows machine.
"""

import json
import os
import sys
import time
import uuid
import signal
import socket
import platform
import threading
import webbrowser
import tkinter as tk
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Cross-platform font: SF Pro on Mac, Segoe UI on Windows
_FONT = "Helvetica Neue" if platform.system() == "Darwin" else "Segoe UI"

PORT = 8766
URL  = f"http://localhost:{PORT}"

# ── Path resolution (dev vs PyInstaller bundle) ────────────────────────────
def resource_path(filename):
    """Return the absolute path to a bundled resource."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


# Meeting history lives next to the executable (not inside the bundle)
def data_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


HISTORY_FILE = os.path.join(data_dir(), "meetingmeter_history.json")
CONFIG_FILE  = os.path.join(data_dir(), "meetingmeter_config.json")


# ── History helpers ────────────────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


# ── Config helpers ─────────────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Slack integration ──────────────────────────────────────────────────────
def post_to_slack(webhook_url, meeting_data):
    """Post a meeting summary to a Slack channel via incoming webhook."""
    title        = meeting_data.get("title", "Untitled Meeting")
    duration     = meeting_data.get("duration", "00:00:00")
    total_cost   = meeting_data.get("total_cost", "$0.00")
    currency     = meeting_data.get("currency", "USD")
    attendees    = meeting_data.get("attendees", [])

    # Build attendee lines
    attendee_lines = "\n".join(
        f"  • {a.get('name','?')} ({a.get('role','')}) — {a.get('cost','$0.00')}"
        for a in attendees
    ) or "  No attendees recorded."

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"💸 MeetingMeter: {title}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Duration*\n{duration}"},
                    {"type": "mrkdwn", "text": f"*Total Cost*\n:moneybag: *{total_cost}* {currency}"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Attendee Breakdown*\n{attendee_lines}"}
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "Sent by *MeetingMeter* — Know the real cost of every meeting."}]
            }
        ]
    }

    data = json.dumps(payload).encode()
    req  = urllib.request.Request(webhook_url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return {"ok": body.strip() == "ok", "response": body}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Google Calendar ICS parsing ────────────────────────────────────────────
def fetch_calendar_events(ics_url):
    """Fetch and parse upcoming events from a Google Calendar ICS URL."""
    try:
        req = urllib.request.Request(ics_url)
        req.add_header("User-Agent", "MeetingMeter/1.0")
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "error": f"Could not fetch calendar: {str(e)}"}

    events = []
    now    = time.time()

    # Split into VEVENT blocks
    blocks = raw.split("BEGIN:VEVENT")
    for block in blocks[1:]:
        end_idx = block.find("END:VEVENT")
        if end_idx == -1:
            continue
        block = block[:end_idx]

        def get_field(name, text):
            """Extract first matching field value, handling line folding."""
            lines = text.splitlines()
            result = []
            capture = False
            for line in lines:
                if line.startswith(name + ":") or line.startswith(name + ";"):
                    capture = True
                    result.append(line.split(":", 1)[-1].strip())
                elif capture and line.startswith((" ", "\t")):
                    result[-1] += line[1:]
                else:
                    capture = False
            return "".join(result) if result else ""

        summary  = get_field("SUMMARY",  block)
        dtstart  = get_field("DTSTART",  block)
        dtend    = get_field("DTEND",    block)
        location = get_field("LOCATION", block)
        desc     = get_field("DESCRIPTION", block)

        # Parse datetime — handles YYYYMMDDTHHMMSSZ and YYYYMMDD
        def parse_dt(val):
            val = val.split(";")[-1]  # strip TZID= prefix if any
            val = val.replace("Z", "").replace("T", "").replace("-", "").replace(":", "")
            try:
                if len(val) >= 14:
                    import datetime
                    dt = datetime.datetime(
                        int(val[0:4]), int(val[4:6]), int(val[6:8]),
                        int(val[8:10]), int(val[10:12]), int(val[12:14])
                    )
                    return dt.timestamp()
                elif len(val) == 8:
                    import datetime
                    dt = datetime.datetime(int(val[0:4]), int(val[4:6]), int(val[6:8]))
                    return dt.timestamp()
            except Exception:
                pass
            return None

        start_ts = parse_dt(dtstart)
        end_ts   = parse_dt(dtend)

        if not start_ts:
            continue

        # Only return events in the next 7 days
        if start_ts < now - 3600 or start_ts > now + 7 * 86400:
            continue

        duration_min = 0
        if end_ts and start_ts:
            duration_min = max(0, int((end_ts - start_ts) / 60))

        import datetime
        dt_obj  = datetime.datetime.fromtimestamp(start_ts)
        display = dt_obj.strftime("%a %b %-d, %-I:%M %p")

        events.append({
            "summary":      summary or "Untitled Event",
            "start":        display,
            "start_ts":     start_ts,
            "duration_min": duration_min,
            "location":     location,
            "description":  desc[:200] if desc else "",
        })

    events.sort(key=lambda e: e["start_ts"])
    return {"ok": True, "events": events}


# ── HTTP server ────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/meetingmeter"):
            html_path = resource_path("meetingmeter.html")
            with open(html_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif path == "/api/history":
            self.send_json(load_history())
        elif path == "/api/config":
            cfg = load_config()
            # Never expose sensitive keys — only confirm presence
            self.send_json({
                "slack_webhook":    cfg.get("slack_webhook", ""),
                "gcal_ics_url":     cfg.get("gcal_ics_url", ""),
                "has_slack":        bool(cfg.get("slack_webhook", "")),
                "has_gcal":         bool(cfg.get("gcal_ics_url", "")),
            })
        elif path == "/api/calendar-events":
            cfg     = load_config()
            ics_url = cfg.get("gcal_ics_url", "")
            if not ics_url:
                self.send_json({"ok": False, "error": "No calendar URL configured. Add it in Integrations settings."})
            else:
                self.send_json(fetch_calendar_events(ics_url))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path   = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        if path == "/api/history":
            history = load_history()
            entry = {
                "id":               str(uuid.uuid4()),
                "timestamp":        time.time(),
                "title":            body.get("title", "Untitled Meeting"),
                "duration_seconds": body.get("duration_seconds", 0),
                "total_cost":       body.get("total_cost", 0),
                "attendees":        body.get("attendees", []),
            }
            history.insert(0, entry)
            save_history(history)
            self.send_json(entry, 201)

        elif path == "/api/config":
            cfg = load_config()
            for k in ("slack_webhook", "gcal_ics_url"):
                if k in body:
                    cfg[k] = body[k]
            save_config(cfg)
            self.send_json({"ok": True})

        elif path == "/api/slack-notify":
            cfg         = load_config()
            webhook_url = cfg.get("slack_webhook", "")
            if not webhook_url:
                self.send_json({"ok": False, "error": "No Slack webhook configured. Add it in Integrations settings."}, 400)
                return
            self.send_json(post_to_slack(webhook_url, body))

        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "api" and parts[1] == "history":
            history = load_history()
            if len(parts) == 3:
                history = [e for e in history if e["id"] != parts[2]]
            else:
                history = []
            save_history(history)
            self.send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()


# ── Server lifecycle ───────────────────────────────────────────────────────
_server = None

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0

def start_server():
    global _server
    if is_port_in_use(PORT):
        return
    _server = HTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=_server.serve_forever, daemon=True).start()

def stop_server():
    global _server
    if _server:
        _server.shutdown()

def wait_for_server(timeout=6):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_in_use(PORT):
            return True
        time.sleep(0.15)
    return False


# ── Tkinter control window ─────────────────────────────────────────────────
def build_ui():
    root = tk.Tk()
    root.title("MeetingMeter")
    root.resizable(False, False)
    root.configure(bg="#0f0f13")

    w, h = 340, 185
    x = (root.winfo_screenwidth()  - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(root, text="💸  MeetingMeter",
        bg="#0f0f13", fg="#f0f0f5",
        font=(_FONT, 16, "bold")).pack(pady=(22, 4))

    tk.Label(root, text="Know the real cost of every meeting",
        bg="#0f0f13", fg="#7a7a9a",
        font=(_FONT, 11)).pack(pady=(0, 14))

    status_var = tk.StringVar(value="Starting…")
    status_lbl = tk.Label(root, textvariable=status_var,
        bg="#0f0f13", fg="#7a7a9a",
        font=(_FONT, 11))
    status_lbl.pack(pady=(0, 14))

    btn_frame = tk.Frame(root, bg="#0f0f13")
    btn_frame.pack()

    open_btn = tk.Button(
        btn_frame, text="Open App",
        bg="#7c6af7", fg="white",
        activebackground="#a78bfa", activeforeground="white",
        font=(_FONT, 12, "bold"),
        relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
        command=lambda: webbrowser.open(URL),
    )
    open_btn.grid(row=0, column=0, padx=6)

    def on_quit():
        stop_server()
        root.destroy()

    tk.Button(
        btn_frame, text="Quit",
        bg="#1a1a24", fg="#f0f0f5",
        activebackground="#2e2e3e", activeforeground="#f0f0f5",
        font=(_FONT, 12),
        relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
        command=on_quit,
    ).grid(row=0, column=1, padx=6)

    root.protocol("WM_DELETE_WINDOW", on_quit)

    def init():
        start_server()
        if wait_for_server():
            status_var.set("Running  ●")
            status_lbl.config(fg="#34d399")
            webbrowser.open(URL)
        else:
            status_var.set("Failed to start")
            status_lbl.config(fg="#f87171")

    threading.Thread(target=init, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    build_ui()
