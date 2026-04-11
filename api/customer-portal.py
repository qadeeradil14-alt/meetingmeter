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

        if not email:
            self._json(400, {"ok": False, "error": "Email required"})
            return

        try:
            # Find customer by email
            customers = stripe_get("customers", {"email": email, "limit": 1})
            if not customers["data"]:
                self._json(404, {"ok": False, "error": "No subscription found for that email"})
                return

            customer_id = customers["data"][0]["id"]

            # Create portal session
            session = stripe_post("billing_portal/sessions", {
                "customer": customer_id,
                "return_url": "https://meetingmeter-f2wq.vercel.app/app"
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
