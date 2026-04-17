"""
Sign-in endpoint: Verify email + code, issue stateless JWT session token.
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

VERIFY_SECRET = os.environ.get("VERIFY_SECRET", "").strip()
STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "").strip()


def b64u_decode(s):
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def verify_challenge(email, code, challenge):
    try:
        payload_b64, sig_b64 = challenge.split(".", 1)
    except ValueError:
        return False, "Malformed challenge"

    try:
        payload_bytes = b64u_decode(payload_b64)
        expected_sig = hmac.new(VERIFY_SECRET.encode(), payload_bytes, hashlib.sha256).digest()
        actual_sig = b64u_decode(sig_b64)
    except Exception:
        return False, "Invalid challenge encoding"

    if not hmac.compare_digest(expected_sig, actual_sig):
        return False, "Invalid challenge signature"

    try:
        payload = json.loads(payload_bytes.decode())
    except Exception:
        return False, "Invalid challenge payload"

    if payload.get("email", "").lower() != email.lower():
        return False, "Email mismatch"

    if payload.get("code") != code:
        return False, "Incorrect code"

    if int(payload.get("exp", 0)) < int(time.time()):
        return False, "Code expired. Please request a new one."

    return True, ""


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


def create_session_token(email):
    now = int(time.time())
    exp = now + (30 * 86400)
    user_id = int(hashlib.md5(email.lower().encode()).hexdigest()[:8], 16)
    payload = json.dumps({"sub": user_id, "email": email, "iat": now, "exp": exp}, separators=(",", ":")).encode()
    sig = hmac.new(VERIFY_SECRET.encode(), payload, hashlib.sha256).digest()
    return b64u(payload) + "." + b64u(sig)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        email = body.get("email", "").strip().lower()
        code = body.get("code", "").strip()
        challenge = body.get("challenge", "").strip()

        if not email or not code or not challenge:
            self._json({"ok": False, "error": "Missing email, code, or challenge"}, 400)
            return

        if not VERIFY_SECRET or not STRIPE_SECRET:
            self._json({"ok": False, "error": "Server misconfigured"}, 500)
            return

        ok, err = verify_challenge(email, code, challenge)
        if not ok:
            self._json({"ok": False, "error": err}, 403)
            return

        try:
            has_sub, period_end = stripe_get_active_sub(email)
        except Exception as e:
            self._json({"ok": False, "error": "Stripe lookup failed: " + str(e)}, 502)
            return

        token = create_session_token(email)
        user_id = int(hashlib.md5(email.lower().encode()).hexdigest()[:8], 16)

        self._json({
            "ok": True,
            "token": token,
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
