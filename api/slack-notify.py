from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error


class handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._json({"ok": False, "error": "Invalid request body"}, 400)
            return

        webhook_url = body.get("webhook_url", "").strip()
        if not webhook_url or not webhook_url.startswith("https://hooks.slack.com/"):
            self._json({"ok": False, "error": "Invalid Slack webhook URL"}, 400)
            return

        title       = body.get("title", "Untitled Meeting")
        duration    = body.get("duration", "00:00:00")
        total_cost  = body.get("total_cost", "$0.00")
        currency    = body.get("currency", "USD")
        attendees   = body.get("attendees", [])

        attendee_lines = "\n".join(
            f"  • {a.get('name', '?')} ({a.get('role', '')}) — {a.get('cost', '$0.00')}"
            for a in attendees
        ) or "  No attendees recorded."

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"💸 MeetingMeter: {title}"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Duration*\n{duration}"},
                        {"type": "mrkdwn", "text": f"*Total Cost*\n:moneybag: *{total_cost}* {currency}"},
                    ]
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Attendee Breakdown*\n{attendee_lines}"}
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Sent by *MeetingMeter* — Know the real cost of every meeting."}]
                }
            ]
        }

        data = json.dumps(payload).encode()
        req  = urllib.request.Request(webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read().decode()
                self._json({"ok": resp_body.strip() == "ok", "response": resp_body})
        except urllib.error.HTTPError as e:
            self._json({"ok": False, "error": f"Slack returned HTTP {e.code}: {e.read().decode()}"}, 502)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 502)

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)
