#!/usr/bin/env python3
"""
MeetingMeter — standalone launcher.
Uses pywebview for a native app window — no browser chrome, no localhost URL visible.
"""

import json
import os
import sys
import time
import uuid
import socket
import threading
import webview
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


# ── pywebview JS API (exposed as window.pywebview.api in JS) ──────────────
class Api:
    """Methods here are callable from JavaScript as window.pywebview.api.*"""

    def save_csv(self, data, filename):
        """Build CSV in Python (avoids encoding issues in JS→Python bridge) and save."""
        try:
            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory=os.path.expanduser("~/Desktop"),
                save_filename=filename,
                file_types=("CSV Files (*.csv)", "All Files (*.*)")
            )
            if not result:
                return {"ok": False}
            path = result[0] if isinstance(result, (list, tuple)) else result

            # Build CSV entirely in Python — no encoding bridge problems
            lines = [
                "Meeting Report",
                f"Title,\"{data.get('title', '')}\"",
                f"Duration,{data.get('duration', '')}",
                f"Total Cost,{data.get('total_cost', '')}",
                f"Currency,{data.get('currency', '')}",
                "",
                "Name,Role,Salary (Annual),Cost This Meeting",
            ]
            for a in data.get("attendees", []):
                name = a.get("name", "Unnamed").replace('"', '""')
                role = a.get("role", "").replace('"', '""')
                lines.append(f'"{name}","{role}",{a.get("salary","")},{a.get("cost","")}')

            content = "\n".join(lines) + "\n"

            # utf-8-sig = UTF-8 with BOM — Excel on Mac & Windows reads special chars correctly
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                f.write(content)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_pdf(self, data):
        """Generate a PDF report via reportlab and save with native dialog."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch, pt
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer,
                Table, TableStyle, HRFlowable
            )
            import datetime

            title    = data.get("title", "Untitled Meeting")
            duration = data.get("duration", "00:00:00")
            total    = data.get("total_cost", "$0.00")
            currency = data.get("currency", "USD")
            rows     = data.get("attendees", [])
            generated = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")

            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory=os.path.expanduser("~/Desktop"),
                save_filename=f"{title.replace(' ', '-')}-cost-report.pdf",
                file_types=("PDF Files (*.pdf)", "All Files (*.*)")
            )
            if not result:
                return {"ok": False}
            path = result[0] if isinstance(result, (list, tuple)) else result

            # ── Colours ───────────────────────────────────────────
            gold   = colors.HexColor("#f59e0b")
            dark   = colors.HexColor("#111827")
            muted  = colors.HexColor("#6b7280")
            light  = colors.HexColor("#f3f4f6")
            subtle = colors.HexColor("#e5e7eb")
            faint  = colors.HexColor("#fafafa")

            # ── Base styles ───────────────────────────────────────
            base = getSampleStyleSheet()["Normal"]

            def s(name, size, color, bold=False, align=TA_LEFT, leading_mult=1.35):
                return ParagraphStyle(
                    name, parent=base,
                    fontSize=size,
                    leading=size * leading_mult,
                    textColor=color,
                    fontName="Helvetica-Bold" if bold else "Helvetica",
                    alignment=align,
                )

            # ── Page setup ────────────────────────────────────────
            L_MARGIN = R_MARGIN = 0.75 * inch
            PAGE_W = letter[0]
            avail_w = PAGE_W - L_MARGIN - R_MARGIN   # 7.0 inches exactly

            doc = SimpleDocTemplate(
                path, pagesize=letter,
                leftMargin=L_MARGIN, rightMargin=R_MARGIN,
                topMargin=0.75 * inch, bottomMargin=0.75 * inch,
            )

            # ── Story ─────────────────────────────────────────────
            story = []

            # Header
            story.append(Paragraph("MeetingMeter", s("brand", 22, dark, bold=True)))
            story.append(Spacer(1, 4))
            story.append(Paragraph("Meeting Cost Report", s("sub", 12, muted)))
            story.append(Spacer(1, 14))
            story.append(HRFlowable(width=avail_w, thickness=1, color=subtle))
            story.append(Spacer(1, 16))

            # Meeting title + meta
            story.append(Paragraph(title, s("mtitle", 18, dark, bold=True)))
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"Duration: {duration}  \u2022  Currency: {currency}  \u2022  {generated}",
                s("meta", 10, muted)
            ))
            story.append(Spacer(1, 20))

            # Total cost (big number)
            story.append(Paragraph(total, s("cost", 36, gold, bold=True)))
            story.append(Spacer(1, 6))
            story.append(Paragraph("Total Meeting Cost", s("clabel", 11, muted)))
            story.append(Spacer(1, 20))
            story.append(HRFlowable(width=avail_w, thickness=1, color=subtle))
            story.append(Spacer(1, 16))

            # Attendee table
            if rows:
                story.append(Paragraph("Cost Per Attendee", s("th", 13, dark, bold=True)))
                story.append(Spacer(1, 10))

                tdata = [["Name", "Role", "Rate / min", "Cost This Meeting"]]
                for a in rows:
                    tdata.append([
                        a.get("name", "Unnamed"),
                        a.get("role", ""),
                        a.get("rate", ""),
                        a.get("cost", ""),
                    ])

                # Proportional widths that exactly fill avail_w
                cw = [avail_w * p for p in [0.28, 0.24, 0.22, 0.26]]

                t = Table(tdata, colWidths=cw, repeatRows=1)
                t.setStyle(TableStyle([
                    # Header row
                    ("BACKGROUND",    (0, 0), (-1, 0), light),
                    ("TEXTCOLOR",     (0, 0), (-1, 0), muted),
                    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE",      (0, 0), (-1, 0), 9),
                    ("TOPPADDING",    (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    # Data rows
                    ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE",      (0, 1), (-1, -1), 11),
                    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, faint]),
                    ("TOPPADDING",    (0, 1), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 9),
                    # All cells
                    ("GRID",          (0, 0), (-1, -1), 0.5, subtle),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    # Right-align rate + cost columns
                    ("ALIGN",         (2, 0), (-1, -1), "RIGHT"),
                    # Bold gold for cost column
                    ("FONTNAME",      (3, 1), (3, -1), "Helvetica-Bold"),
                    ("TEXTCOLOR",     (3, 1), (3, -1), gold),
                ]))
                story.append(t)

            # Footer
            story.append(Spacer(1, 28))
            story.append(HRFlowable(width=avail_w, thickness=1, color=subtle))
            story.append(Spacer(1, 10))
            story.append(Paragraph(
                "Generated by <b>MeetingMeter</b>",
                s("footer", 9, muted, align=TA_CENTER)
            ))

            doc.build(story)
            return {"ok": True, "path": path}

        except Exception as e:
            return {"ok": False, "error": str(e)}

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

def wait_for_server(timeout=6):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_in_use(PORT):
            return True
        time.sleep(0.15)
    return False


# ── Main entry point ───────────────────────────────────────────────────────
if __name__ == "__main__":
    # Start the local API server in a background thread
    start_server()
    wait_for_server()

    # Open a native desktop window — no browser chrome, no localhost URL
    api = Api()
    window = webview.create_window(
        title="MeetingMeter",
        url=URL,
        js_api=api,
        width=980,
        height=740,
        min_size=(800, 600),
        resizable=True,
        text_select=False,
        background_color="#0f0f13",
    )
    webview.start()
