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
import threading
import webbrowser
import tkinter as tk
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

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
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/history":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            history = load_history()
            entry = {
                "id": str(uuid.uuid4()),
                "timestamp": time.time(),
                "title": body.get("title", "Untitled Meeting"),
                "duration_seconds": body.get("duration_seconds", 0),
                "total_cost": body.get("total_cost", 0),
                "attendees": body.get("attendees", []),
            }
            history.insert(0, entry)
            save_history(history)
            self.send_json(entry, 201)
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
        font=("SF Pro Display", 16, "bold")).pack(pady=(22, 4))

    tk.Label(root, text="Know the real cost of every meeting",
        bg="#0f0f13", fg="#7a7a9a",
        font=("SF Pro Display", 11)).pack(pady=(0, 14))

    status_var = tk.StringVar(value="Starting…")
    status_lbl = tk.Label(root, textvariable=status_var,
        bg="#0f0f13", fg="#7a7a9a",
        font=("SF Pro Display", 11))
    status_lbl.pack(pady=(0, 14))

    btn_frame = tk.Frame(root, bg="#0f0f13")
    btn_frame.pack()

    open_btn = tk.Button(
        btn_frame, text="Open App",
        bg="#7c6af7", fg="white",
        activebackground="#a78bfa", activeforeground="white",
        font=("SF Pro Display", 12, "bold"),
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
        font=("SF Pro Display", 12),
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
