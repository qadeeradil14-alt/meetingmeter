"""
Newsletter subscribe endpoint.

Input:  POST { email }
Action: Sends a notification to support@agendaburn.com via Resend so the
        owner can add the subscriber to their email list.

Simple and stateless — no database needed. Swap the body below for a
Mailchimp / ConvertKit / Resend Audiences API call when ready to scale.
"""
from __future__ import annotations
import os
import json
import re
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
FROM_EMAIL     = os.environ.get("VERIFY_FROM_EMAIL", "onboarding@resend.dev").strip()
NOTIFY_TO      = "support@agendaburn.com"

ALLOWED_ORIGINS = {"https://agendaburn.com", "https://www.agendaburn.com"}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def send_notify(subscriber_email: str) -> tuple[bool, str]:
    body = {
        "from": f"AgendaBurn Subscribers <{FROM_EMAIL}>",
        "to":   [NOTIFY_TO],
        "subject": f"New subscriber: {subscriber_email}",
        "text": (
            f"New newsletter subscriber:\n\n"
            f"  {subscriber_email}\n\n"
            f"Add them to your email list."
        ),
        "html": (
            f"<p style='font-family:sans-serif;font-size:15px;'>"
            f"New newsletter subscriber:<br><br>"
            f"<strong>{subscriber_email}</strong><br><br>"
            f"Add them to your email list."
            f"</p>"
        ),
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(body).encode(),
        headers={
            "Authorization":  f"Bearer {RESEND_API_KEY}",
            "Content-Type":   "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        return True, ""
    except urllib.error.HTTPError as e:
        return False, f"Resend HTTP {e.code}"
    except Exception as e:
        return False, str(e)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        email  = body.get("email", "").strip().lower()

        if not email or not EMAIL_RE.match(email):
            self._json({"ok": False, "error": "Valid email required"}, 400)
            return

        if not RESEND_API_KEY:
            # Silently succeed so the UX isn't broken even if misconfigured
            self._json({"ok": True}, 200)
            return

        ok, err = send_notify(email)
        # Always return ok=True to the user — subscribe should never visibly fail
        self._json({"ok": True})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        origin  = self.headers.get("Origin", "")
        allowed = origin if (origin in ALLOWED_ORIGINS or origin.endswith(".vercel.app")) else "https://agendaburn.com"
        self.send_header("Access-Control-Allow-Origin",  allowed)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")

    def _json(self, data, status=200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass
