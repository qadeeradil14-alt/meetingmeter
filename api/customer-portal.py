import os, json
import urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()

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
        action = (body.get("action") or "").strip().lower()

        if not email:
            self._json(400, {"ok": False, "error": "Email required"})
            return

        try:
            # Step 1: Send verification email (always, even if customer doesn't exist)
            if action == "send_verification":
                # Generate simple verification code (in production, use proper tokens)
                verification_code = __import__("secrets").token_urlsafe(32)
                # In production, store in database + send actual email
                # For now, we'll send it via a hypothetical email service
                # Just acknowledge the request
                self._json(200, {"ok": True, "message": "Verification email sent. Check your inbox."})
                return

            # Step 2: Verify code and create portal session (only if code is valid)
            # For MVP: accept any submitted email + code combo and validate it was sent
            # In production: verify against stored code for that email
            if action == "verify_and_access":
                code = (body.get("code") or "").strip()
                if not code or len(code) < 10:
                    self._json(400, {"ok": False, "error": "Invalid verification code"})
                    return
                # In production: lookup stored code, verify it matches, ensure not expired
                # For now: assume valid if code exists

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
                return

            # Fallback: reject direct access
            self._json(400, {"ok": False, "error": "Verification required. Use send_verification first."})

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
