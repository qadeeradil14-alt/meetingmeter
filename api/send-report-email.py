"""Send monthly report email via Resend."""
from __future__ import annotations
import os
import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
FROM_EMAIL = os.environ.get("VERIFY_FROM_EMAIL", "onboarding@resend.dev").strip()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        email = body.get("email", "").strip().lower()
        cc_raw = body.get("cc", [])
        cc = [e.strip().lower() for e in (cc_raw if isinstance(cc_raw, list) else [cc_raw]) if e and "@" in str(e)]
        report_html = body.get("reportHtml", "")
        report_text = body.get("reportText", "")

        if not email or "@" not in email:
            self._json({"ok": False, "error": "Valid email required"}, 400)
            return

        if not RESEND_API_KEY:
            self._json({"ok": False, "error": "Server misconfigured"}, 500)
            return

        # Send via Resend
        email_body = {
            "from": f"MeetingMeter <{FROM_EMAIL}>",
            "to": [email],
            **({"cc": cc} if cc else {}),
            "subject": f"Your Monthly Meeting Report - {report_text}",
            "html": f"""
            <div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:900px;margin:0 auto;padding:24px;">
              <h2 style="color:#7c6af7;margin-bottom:20px;">📊 Your Monthly Report</h2>
              <p style="color:#666;margin-bottom:20px;">{report_text}</p>
              <div style="background:#f9fafb;padding:20px;border-radius:8px;border:1px solid #e5e7eb;">
                {report_html}
              </div>
              <p style="color:#999;font-size:12px;margin-top:20px;">
                <a href="https://meetingmeter.tech/app" style="color:#7c6af7;text-decoration:none;">
                  View more reports in MeetingMeter →
                </a>
              </p>
            </div>
            """,
        }
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(email_body).encode(),
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "MeetingMeter/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            self._json({"ok": True})
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            self._json({"ok": False, "error": f"Resend HTTP {e.code}"}, 502)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 502)

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
