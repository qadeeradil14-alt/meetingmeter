"""Send monthly report email via Resend."""
from __future__ import annotations
import os
import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler

ALLOWED_ORIGINS = {"https://agendaburn.com", "https://www.agendaburn.com"}

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
            "from": f"AgendaBurn <{FROM_EMAIL}>",
            "to": [email],
            **({"cc": cc} if cc else {}),
            "reply_to": "support@agendaburn.com",
            "subject": f"📊 Your Monthly Meeting Report — {report_text}",
            "html": f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:32px 16px;">

    <!-- Header -->
    <div style="background:#0f172a;border-radius:16px 16px 0 0;padding:28px 32px;text-align:center;">
      <div style="display:inline-flex;align-items:center;gap:10px;margin-bottom:8px;">
        <div style="width:28px;height:28px;border-radius:8px;background:#f6b54d;color:#0f172a;font-weight:900;font-size:14px;display:inline-flex;align-items:center;justify-content:center;line-height:1;">$</div>
        <span style="color:#f5f0e8;font-size:17px;font-weight:600;letter-spacing:-0.2px;">AgendaBurn</span>
      </div>
      <div style="color:#f6b54d;font-size:22px;font-weight:700;letter-spacing:-0.5px;">📊 Monthly Spend Report</div>
      <div style="color:#7290ab;font-size:13px;margin-top:6px;">{report_text}</div>
    </div>

    <!-- Report body -->
    <div style="background:#ffffff;border-radius:0 0 16px 16px;padding:28px 32px;border:1px solid #e5e7eb;border-top:none;">
      {report_html}
    </div>

    <!-- Footer -->
    <div style="text-align:center;margin-top:20px;padding:0 16px;">
      <a href="https://agendaburn.com/app" style="display:inline-block;padding:12px 28px;background:#f6b54d;color:#0f172a;font-weight:700;font-size:14px;border-radius:980px;text-decoration:none;">
        Open AgendaBurn →
      </a>
      <p style="color:#9ca3af;font-size:11px;margin-top:16px;">
        You received this because you requested a monthly report from AgendaBurn.<br>
        © 2026 AgendaBurn · <a href="https://agendaburn.com" style="color:#9ca3af;">agendaburn.com</a>
      </p>
    </div>

  </div>
</body>
</html>""",
        }
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(email_body).encode(),
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "AgendaBurn/1.0",
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
        origin = self.headers.get("Origin", "")
        allowed = origin if (origin in ALLOWED_ORIGINS or origin.endswith(".vercel.app")) else "https://agendaburn.com"
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
