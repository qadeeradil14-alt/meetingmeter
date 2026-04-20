from http.server import BaseHTTPRequestHandler
import json
import time
import datetime
import urllib.request
import urllib.parse
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


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

        # webcal:// is identical to https:// — just a protocol hint for calendar apps
        ics_url = ics_url.replace("webcal://", "https://").replace("webcal+ssl://", "https://")

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
            location = self._field(block, "LOCATION")
            description = self._field(block, "DESCRIPTION")
            attendees = self._attendees(block)

            dtstart_params, dtstart_val = self._field_with_params(block, "DTSTART")
            dtend_params,   dtend_val   = self._field_with_params(block, "DTEND")

            # Fall back to location or first line of description when summary is blank
            if not summary and location:
                summary = location
            elif not summary and description:
                summary = description.splitlines()[0][:60].strip()

            start_ts = self._parse_dt(dtstart_val, dtstart_params)
            end_ts   = self._parse_dt(dtend_val,   dtend_params)

            if not start_ts:
                continue
            # Events starting in the past 6 hours or up to 7 days ahead (tolerant of TZ skew)
            if start_ts < now - 6 * 3600 or start_ts > now + 7 * 86400:
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
                "attendees":    attendees,
            })

        events.sort(key=lambda e: e["start_ts"])
        return events[:10]

    def _attendees(self, text):
        """Extract attendee {name, email} entries from ATTENDEE lines, handling ICS line folding."""
        # Unfold continuation lines first (RFC 5545: lines starting with space/tab)
        unfolded = []
        for line in text.splitlines():
            if line and line[0] in (" ", "\t") and unfolded:
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)

        results = []
        for line in unfolded:
            if not line.upper().startswith("ATTENDEE"):
                continue
            # Split into param part (before colon) and value part (after colon)
            colon_idx = line.find(":")
            param_part = line[:colon_idx] if colon_idx != -1 else line
            mailto_part = line[colon_idx + 1:] if colon_idx != -1 else ""

            cn = ""
            for part in param_part.split(";"):
                if part.upper().startswith("CN="):
                    cn = part[3:].strip().strip('"')
                    break

            email = mailto_part.replace("mailto:", "").replace("MAILTO:", "").strip()
            if "@" not in email:
                email = ""

            # Derive a display name
            if cn and "@" not in cn and len(cn) > 1:
                name = cn
            elif email:
                prefix = email.split("@")[0].split("+")[0]
                # "first.last" -> "First Last"
                parts = [p for p in prefix.split(".") if p]
                name = " ".join(p.capitalize() for p in parts) if parts else prefix.capitalize()
            else:
                name = ""

            if name or email:
                results.append({"name": name, "email": email})
        return results

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

    def _field_with_params(self, text, name):
        """Return (params_string, value_string) for an ICS field, respecting line folding."""
        lines = text.splitlines()
        unfolded = []
        for line in lines:
            if line and line[0] in (" ", "\t") and unfolded:
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)
        for line in unfolded:
            if line.startswith(name + ":") or line.startswith(name + ";"):
                colon = line.find(":")
                if colon == -1:
                    return "", ""
                return line[:colon], line[colon + 1:].strip()
        return "", ""

    def _parse_dt(self, val, params=""):
        if not val:
            return None
        is_utc = val.endswith("Z")
        clean = val.replace("Z", "").replace("T", "").replace("-", "").replace(":", "")
        tzid = ""
        if params:
            for p in params.split(";"):
                if p.upper().startswith("TZID="):
                    tzid = p[5:].strip().strip('"')
                    break
        try:
            if len(clean) >= 14:
                dt = datetime.datetime(
                    int(clean[0:4]), int(clean[4:6]), int(clean[6:8]),
                    int(clean[8:10]), int(clean[10:12]), int(clean[12:14])
                )
            elif len(clean) == 8:
                dt = datetime.datetime(int(clean[0:4]), int(clean[4:6]), int(clean[6:8]))
            else:
                return None

            if is_utc:
                return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
            if tzid and ZoneInfo:
                try:
                    return dt.replace(tzinfo=ZoneInfo(tzid)).timestamp()
                except Exception:
                    pass
            # Floating / unknown-TZ: treat the wallclock AS UTC so it round-trips unchanged
            # to the browser (which will display it in its own local TZ).
            return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
        except Exception:
            return None

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)
