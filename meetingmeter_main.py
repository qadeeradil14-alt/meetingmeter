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
            from reportlab.lib.units import inch
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
