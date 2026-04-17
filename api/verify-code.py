"""
Verify the 6-digit code the user entered against the HMAC-signed challenge.

Input: { email, code, challenge }
- Recompute HMAC of the challenge payload; reject if signature doesn't match.
- Reject if email in payload doesn't match submitted email (prevents swap).
- Reject if code in payload doesn't match submitted code.
- Reject if expired (exp < now).

On success, returns { ok: true }.
"""
import os
import json
import time
import hmac
import hashlib
import base64
from http.server import BaseHTTPRequestHandler

VERIFY_SECRET = os.environ.get("VERIFY_SECRET", "").strip()


def b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def verify_challenge(email: str, code: str, challenge: str) -> tuple[bool, str]:
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

        if not VERIFY_SECRET:
            self._json({"ok": False, "error": "Server misconfigured"}, 500)
            return

        ok, err = verify_challenge(email, code, challenge)
        if not ok:
            self._json({"ok": False, "error": err}, 403)
            return

        self._json({"ok": True})

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
