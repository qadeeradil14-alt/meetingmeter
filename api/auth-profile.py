"""
Profile endpoint: Validate JWT session token, return Pro status from Stripe.
"""
from __future__ import annotations
import os
import json
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "").strip()
VERIFY_SECRET = os.environ.get("VERIFY_SECRET", "").strip()


def get_token_from_header(headers):
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def b64u_decode(s):
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def validate_token(token):
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return False, None, None

    try:
        payload_bytes = b64u_decode(payload_b64)
        expected_sig = hmac.new(VERIFY_SECRET.encode(), payload_bytes, hashlib.sha256).digest()
        actual_sig = b64u_decode(sig_b64)
    except Exception:
        return False, None, None

    if not hmac.compare_digest(expected_sig, actual_sig):
        return False, None, None

    try:
        payload = json.loads(payload_bytes.decode())
    except Exception:
        return False, None, None

    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        return False, None, None

    user_id = payload.get("sub")
    email = payload.get("email", "").lower()
    return True, user_id, email


def stripe_get_active_sub(email):
    creds = base64.b64encode((STRIPE_SECRET + ":").encode()).decode()
    url = "https://api.stripe.com/v1/customers?email=" + urllib.parse.quote(email) + "&limit=5"
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + creds})
    with urllib.request.urlopen(req, timeout=10) as resp:
        customers = json.loads(resp.read())
    for customer in customers.get("data", []):
        cid = customer["id"]
        sub_url = "https://api.stripe.com/v1/subscriptions?customer=" + cid + "&status=active&limit=1"
        sub_req = urllib.request.Request(sub_url, headers={"Authorization": "Basic " + creds})
        with urllib.request.urlopen(sub_req, timeout=10) as sub_resp:
            subs = json.loads(sub_resp.read())
        if subs.get("data"):
            period_end = subs["data"][0].get("current_period_end", 0)
            return True, period_end
    return False, 0


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        token = get_token_from_header(self.headers)

        if not token:
            self._json({"ok": False, "error": "Missing Authorization header"}, 401)
            return

        is_valid, user_id, email = validate_token(token)
        if not is_valid:
            self._json({"ok": False, "error": "Invalid or expired session"}, 401)
            return

        try:
            has_sub, period_end = stripe_get_active_sub(email)
        except Exception as e:
            self._json({"ok": False, "error": "Stripe lookup failed: " + str(e)}, 502)
            return

        self._json({
            "ok": True,
            "user": {"id": user_id, "email": email},
            "pro": has_sub,
            "period_end": period_end,
        })

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

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
