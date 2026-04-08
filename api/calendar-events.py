from http.server import BaseHTTPRequestHandler
import json
import time
import datetime
import urllib.request
import urllib.parse


class handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        ics_url = params.get("ics_url", [""])[0].strip()

        if not ics_url:
            self._json({"ok": False, "error": "Missing ics_url parameter"}, 400)
            return

        try:
            req = urllib.request.Request(ics_url)
            req.add_header("User-Agent", "MeetingMeter/1.0")
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            self._json({"ok": False, "error": f"Could not fetch calendar: {str(e)}"}, 502)
            return

        events = self._parse_ics(raw)
        self._json({"ok": True, "events": events})

    def _parse_ics(self, raw):
        now = time.time()
        events = []

        blocks = raw.split("BEGIN:VEVENT")
        for block in blocks[1:]:
            end_idx = block.find("END:VEVENT")
            if end_idx == -1:
                continue
            block = block[:end_idx]

            summary  = self._field(block, "SUMMARY")
            dtstart  = self._field(block, "DTSTART")
            dtend    = self._field(block, "DTEND")
            location = self._field(block, "LOCATION")

            start_ts = self._parse_dt(dtstart)
            end_ts   = self._parse_dt(dtend)

            if not start_ts:
                continue
            # Events starting in the past hour or up to 7 days ahead
            if start_ts < now - 3600 or start_ts > now + 7 * 86400:
                continue

            duration_min = int((end_ts - start_ts) / 60) if end_ts else 60

            dt_obj  = datetime.datetime.fromtimestamp(start_ts)
            display = dt_obj.strftime("%a %b %-d, %-I:%M %p")

            events.append({
                "summary":      summary or "Untitled Event",
                "start":        display,
                "start_ts":     start_ts,
                "duration_min": max(1, duration_min),
                "location":     location,
            })

        events.sort(key=lambda e: e["start_ts"])
        return events[:10]

    def _field(self, text, name):
        lines = text.splitlines()
        result = []
        capturing = False
        for line in lines:
            if line.startswith(name + ":") or line.startswith(name + ";"):
                capturing = True
                result.append(line.split(":", 1)[-1].strip())
            elif capturing and line and line[0] in (" ", "\t"):
                result[-1] += line[1:]
            else:
                capturing = False
        return "".join(result) if result else ""

    def _parse_dt(self, val):
        if not val:
            return None
        val = val.split(";")[-1]
        val = val.replace("Z", "").replace("T", "").replace("-", "").replace(":", "")
        try:
            if len(val) >= 14:
                dt = datetime.datetime(
                    int(val[0:4]), int(val[4:6]), int(val[6:8]),
                    int(val[8:10]), int(val[10:12]), int(val[12:14])
                )
                return dt.timestamp()
            elif len(val) == 8:
                dt = datetime.datetime(int(val[0:4]), int(val[4:6]), int(val[6:8]))
                return dt.timestamp()
        except Exception:
            pass
        return None

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)
