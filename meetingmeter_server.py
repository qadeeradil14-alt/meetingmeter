#!/usr/bin/env python3
"""MeetingMeter — backend server. Serves the UI and persists meeting history."""

import json
import os
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Store history next to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(SCRIPT_DIR, "meetingmeter_history.json")


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
            html_path = os.path.join(SCRIPT_DIR, "meetingmeter.html")
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
        # DELETE /api/history/<id>  or  DELETE /api/history  (clear all)
        if len(parts) >= 2 and parts[0] == "api" and parts[1] == "history":
            history = load_history()
            if len(parts) == 3:
                entry_id = parts[2]
                history = [e for e in history if e["id"] != entry_id]
            else:
                history = []
            save_history(history)
            self.send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    PORT = 8766
    print(f"MeetingMeter running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    server = HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
