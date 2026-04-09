from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse


STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        session_id = body.get("session_id", "").strip()
        email = body.get("email", "").strip().lower()

        if not STRIPE_SECRET:
            self._json({"ok": False, "error": "Server misconfigured"}, 500)
            return

        # Verify by checkout session ID
        if session_id:
            result = self._verify_session(session_id)
            self._json(result)
            return

        # Verify by email (re-activation flow)
        if email:
            result = self._verify_email(email)
            self._json(result)
            return

        self._json({"ok": False, "error": "Provide session_id or email"}, 400)

    def _verify_session(self, session_id):
        try:
            url = f"https://api.stripe.com/v1/checkout/sessions/{urllib.parse.quote(session_id)}"
            req = urllib.request.Request(url)
            import base64
            creds = base64.b64encode(f"{STRIPE_SECRET}:".encode()).decode()
            req.add_header("Authorization", f"Basic {creds}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                session = json.loads(resp.read())

            if session.get("payment_status") != "paid":
                return {"ok": False, "error": "Payment not completed"}

            return {"ok": True, "email": session.get("customer_details", {}).get("email", "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _verify_email(self, email):
        try:
            # Search for customers with this email
            url = "https://api.stripe.com/v1/customers?email=" + urllib.parse.quote(email) + "&limit=5"
            req = urllib.request.Request(url)
            import base64
            creds = base64.b64encode(f"{STRIPE_SECRET}:".encode()).decode()
            req.add_header("Authorization", f"Basic {creds}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                customers = json.loads(resp.read())

            if not customers.get("data"):
                return {"ok": False, "error": "No account found for that email"}

            # Check if any customer has an active subscription
            for customer in customers["data"]:
                cid = customer["id"]
                sub_url = f"https://api.stripe.com/v1/subscriptions?customer={cid}&status=active&limit=1"
                sub_req = urllib.request.Request(sub_url)
                sub_req.add_header("Authorization", f"Basic {creds}")
                with urllib.request.urlopen(sub_req, timeout=10) as sub_resp:
                    subs = json.loads(sub_resp.read())
                if subs.get("data"):
                    return {"ok": True, "email": email}

            return {"ok": False, "error": "No active subscription for that email"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
