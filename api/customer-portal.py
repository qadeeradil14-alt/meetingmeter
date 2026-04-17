import os, json, time, hmac, hashlib, base64
import urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
VERIFY_SECRET = os.environ.get("VERIFY_SECRET", "").strip()


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def verify_challenge(email: str, code: str, challenge: str):
    """Return (ok, error_message). Mirrors /api/verify-code logic."""
    try:
        payload_b64, sig_b64 = challenge.split(".", 1)
        payload_bytes = _b64u_decode(payload_b64)
        expected_sig = hmac.new(VERIFY_SECRET.encode(), payload_bytes, hashlib.sha256).digest()
        actual_sig = _b64u_decode(sig_b64)
    except Exception:
        return False, "Invalid challenge"

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

def stripe_post(path, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        f"https://api.stripe.com/v1/{path}",
        data=data,
        headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}",
                 "Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def stripe_get(path, params=None):
    url = f"https://api.stripe.com/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url,
        headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        email = (body.get("email") or "").strip().lower()
        code = (body.get("code") or "").strip()
        challenge = (body.get("challenge") or "").strip()

        if not email or not code or not challenge:
            self._json(400, {"ok": False, "error": "Email, code, and challenge required"})
            return

        if not VERIFY_SECRET:
            self._json(500, {"ok": False, "error": "Server misconfigured"})
            return

        # Verify the emailed code before opening the portal
        ok, err = verify_challenge(email, code, challenge)
        if not ok:
            self._json(403, {"ok": False, "error": err})
            return

        try:
            customers = stripe_get("customers", {"email": email, "limit": 1})
            if not customers["data"]:
                self._json(404, {"ok": False, "error": "No subscription found for that email"})
                return

            customer_id = customers["data"][0]["id"]
            session = stripe_post("billing_portal/sessions", {
                "customer": customer_id,
                "return_url": "https://meetingmeter.tech/app"
            })
            self._json(200, {"ok": True, "url": session["url"]})

        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
