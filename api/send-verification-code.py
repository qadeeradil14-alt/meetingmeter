"""
Send a 6-digit verification code to the user's email inbox.

Flow:
  1. Frontend POSTs { email }
  2. Backend confirms the email has an active Stripe subscription
  3. Backend generates a 6-digit code
  4. Backend signs { email, code, exp } with HMAC-SHA256 using VERIFY_SECRET
  5. Backend emails the code via Resend
  6. Backend returns { ok: true, challenge } — frontend stores the challenge
  7. User enters code; frontend POSTs { email, code, challenge } to /api/verify-code
  8. verify-code recomputes HMAC and checks match

Stateless — no DB required. Challenge is short-lived (10 min).
"""
from __future__ import annotations
import os
import json
import time
import hmac
import hashlib
import base64
import secrets
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "").strip()
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
VERIFY_SECRET = os.environ.get("VERIFY_SECRET", "").strip()
FROM_EMAIL = os.environ.get("VERIFY_FROM_EMAIL", "onboarding@resend.dev").strip()

CODE_TTL_SECONDS = 10 * 60  # 10 minutes


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_challenge(email: str, code: str, exp: int) -> str:
    """Return a compact signed token: payload.sig (base64url)."""
    payload = json.dumps({"email": email, "code": code, "exp": exp}, separators=(",", ":")).encode()
    sig = hmac.new(VERIFY_SECRET.encode(), payload, hashlib.sha256).digest()
    return f"{b64u(payload)}.{b64u(sig)}"


def stripe_get_active_sub(email: str) -> tuple[bool, int]:
    """Return (has_active_sub, current_period_end) for the email's Stripe subscription."""
    creds = base64.b64encode(f"{STRIPE_SECRET}:".encode()).decode()
    url = "https://api.stripe.com/v1/customers?email=" + urllib.parse.quote(email) + "&limit=5"
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        customers = json.loads(resp.read())
    for customer in customers.get("data", []):
        cid = customer["id"]
        sub_url = f"https://api.stripe.com/v1/subscriptions?customer={cid}&status=active&limit=1"
        sub_req = urllib.request.Request(sub_url, headers={"Authorization": f"Basic {creds}"})
        with urllib.request.urlopen(sub_req, timeout=10) as sub_resp:
            subs = json.loads(sub_resp.read())
        if subs.get("data"):
            period_end = subs["data"][0].get("current_period_end", 0)
            return True, period_end
    return False, 0


def send_email_via_resend(to_email: str, code: str) -> tuple[bool, str]:
    """Send the verification code email via Resend. Returns (ok, error_message)."""
    body = {
        "from": f"MeetingMeter <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"Your MeetingMeter verification code: {code}",
        "html": (
            f"<div style=\"font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;margin:0 auto;padding:24px;\">"
            f"<h2 style=\"color:#7c6af7;margin:0 0 12px;\">Your verification code</h2>"
            f"<p style=\"color:#333;font-size:14px;line-height:1.5;\">Enter this code in MeetingMeter to continue:</p>"
            f"<div style=\"font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;padding:20px;background:#f4f3ff;border-radius:8px;color:#7c6af7;margin:16px 0;\">{code}</div>"
            f"<p style=\"color:#666;font-size:12px;\">This code expires in 10 minutes. If you didn't request this, ignore this email.</p>"
            f"</div>"
        ),
        "text": f"Your MeetingMeter verification code is: {code}\n\nThis code expires in 10 minutes. If you didn't request this, ignore this email.",
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(body).encode(),
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
        return True, ""
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        return False, f"Resend HTTP {e.code}: {err_body[:200]}"
    except Exception as e:
        return False, str(e)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        email = body.get("email", "").strip().lower()

        if not email or "@" not in email:
            self._json({"ok": False, "error": "Valid email required"}, 400)
            return

        if not STRIPE_SECRET or not RESEND_API_KEY or not VERIFY_SECRET:
            self._json({"ok": False, "error": "Server misconfigured (missing env vars)"}, 500)
            return

        # 1. Check that the email has an active subscription
        try:
            has_sub, period_end = stripe_get_active_sub(email)
        except Exception as e:
            self._json({"ok": False, "error": f"Stripe lookup failed: {str(e)}"}, 502)
            return

        if not has_sub:
            self._json({"ok": False, "error": "No active subscription found for that email"}, 404)
            return

        # 2. Generate a 6-digit code
        code = f"{secrets.randbelow(1_000_000):06d}"
        exp = int(time.time()) + CODE_TTL_SECONDS

        # 3. Sign the challenge (stateless)
        challenge = sign_challenge(email, code, exp)

        # 4. Send the code via Resend
        sent, err = send_email_via_resend(email, code)
        if not sent:
            self._json({"ok": False, "error": f"Could not send email: {err}"}, 502)
            return

        # 5. Return challenge + period_end to frontend
        self._json({"ok": True, "challenge": challenge, "period_end": period_end})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
