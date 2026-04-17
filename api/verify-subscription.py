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
        last4 = body.get("last4", "").strip()

        if not STRIPE_SECRET:
            self._json({"ok": False, "error": "Server misconfigured"}, 500)
            return

        # Verify by checkout session ID
        if session_id:
            result = self._verify_session(session_id)
            self._json(result)
            return

        # Verify by email + last4 card digits
        if email:
            if not last4:
                # Step 1: check email has a subscription (but don't unlock)
                result = self._verify_email(email)
                if result.get("ok"):
                    # Email is known — ask for last4 to prove ownership
                    self._json({"ok": False, "needs_last4": True})
                    return
                self._json(result)
                return

            # Step 2: verify last4 matches the card on file
            if not self._verify_last4(email, last4):
                self._json({"ok": False, "error": "Last 4 digits don't match the card on file"})
                return

            # Last4 matched — confirm subscription still active
            result = self._verify_email(email)
            self._json(result)
            return

        self._json({"ok": False, "error": "Provide session_id or email"}, 400)

    def _verify_last4(self, email, last4):
        try:
            import base64
            creds = base64.b64encode(f"{STRIPE_SECRET}:".encode()).decode()

            # Find customer
            url = "https://api.stripe.com/v1/customers?email=" + urllib.parse.quote(email) + "&limit=5"
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Basic {creds}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                customers = json.loads(resp.read())

            for customer in customers.get("data", []):
                cid = customer["id"]
                # Check payment methods for this customer
                pm_url = f"https://api.stripe.com/v1/payment_methods?customer={cid}&type=card&limit=10"
                pm_req = urllib.request.Request(pm_url)
                pm_req.add_header("Authorization", f"Basic {creds}")
                with urllib.request.urlopen(pm_req, timeout=10) as pm_resp:
                    pms = json.loads(pm_resp.read())
                for pm in pms.get("data", []):
                    card = pm.get("card", {})
                    if card.get("last4") == last4:
                        return True
            return False
        except Exception:
            return False

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
