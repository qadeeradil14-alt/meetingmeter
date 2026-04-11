from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        license_key = body.get("license_key", "").strip()

        if not license_key:
            self._json({"ok": False, "error": "No license key provided"}, 400)
            return

        try:
            data = urllib.parse.urlencode({
                "product_permalink": "meetingmeter",
                "license_key": license_key,
                "increment_uses_count": "false",
            }).encode()
            req = urllib.request.Request(
                "https://api.gumroad.com/v2/licenses/verify",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())

            if not result.get("success"):
                self._json({"ok": False, "error": "Invalid license key"})
                return

            purchase = result.get("purchase", {})
            if purchase.get("refunded") or purchase.get("chargebacked") or purchase.get("subscription_ended_at"):
                self._json({"ok": False, "error": "License is no longer active"})
                return

            self._json({"ok": True})

        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

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
