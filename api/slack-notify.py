from http.server import BaseHTTPRequestHandler

ALLOWED_ORIGINS = {"https://agendaburn.com", "https://www.agendaburn.com"}
import json
import urllib.request
import urllib.error


class handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _cors(self):
        origin = self.headers.get("Origin", "")
        allowed = origin if (origin in ALLOWED_ORIGINS or origin.endswith(".vercel.app")) else "https://agendaburn.com"
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.send_header("Vary", "Origin")
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

        # Card button sends a pre-formatted message — forward it directly
        message = body.get("message", "")
        if message:
            payload = {"text": message}
        else:
            # Structured format from debrief / save-modal buttons
            title     = body.get("title", "Untitled Meeting")
            duration  = body.get("duration", "00:00:00")
            currency  = body.get("currency", "USD")

            # Accept total_cost as a pre-formatted string OR cost as a raw number
            cost_raw = body.get("total_cost") if body.get("total_cost") is not None else body.get("cost", 0)
            if isinstance(cost_raw, (int, float)):
                total_cost = f"${cost_raw:,.2f}"
            else:
                total_cost = str(cost_raw) if cost_raw else "$0.00"

            attendees = body.get("attendees", [])
            attendee_lines = "\n".join(
                f"  • {a.get('name', '?')} ({a.get('role', '')}) — {a.get('cost', '')}"
                for a in attendees
            ) or "  No attendees recorded."

            payload = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"💸 AgendaBurn: {title}"}
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Duration*\n{duration}"},
                            {"type": "mrkdwn", "text": f"*Total Cost*\n:moneybag: *{total_cost}*"},
                        ]
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Attendee Breakdown*\n{attendee_lines}"}
                    },
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": "Sent by *AgendaBurn* — Know the real cost of every meeting."}]
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
