"""
Auth API — single serverless function, path-dispatched to stay within
Vercel Hobby's 12-function limit.

Routes handled:
  POST /api/auth/sign-in   — verify email code → issue session token + Pro status
  GET  /api/auth/profile   — validate session token → current Pro status (called on page load)
  POST /api/auth/sign-out  — stateless ack (client clears token from localStorage)

Session tokens are stateless HMAC-SHA256 signed payloads, expire in 30 days.
No database required — signature prevents forgery.
"""
from __future__ import annotations
import os
import json
import time
import hmac
import hashlib
import base64
import fcntl
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

VERIFY_SECRET = os.environ.get("VERIFY_SECRET", "").strip()
STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "").strip()
SESSION_TTL   = 30 * 24 * 60 * 60   # 30 days

ALLOWED_ORIGINS = {"https://agendaburn.com", "https://www.agendaburn.com"}

# ── rate limiter (per-email, file-based, per-container) ───────────────────────
_RL_DIR          = "/tmp/rl_auth"
_RL_MAX_ATTEMPTS = 5          # max sign-in attempts
_RL_WINDOW       = 600        # per 10 minutes

def _is_rate_limited(email: str) -> bool:
    os.makedirs(_RL_DIR, exist_ok=True)
    key  = hashlib.sha256(email.encode()).hexdigest()[:20]
    path = f"{_RL_DIR}/{key}.json"
    now  = time.time()
    try:
        with open(path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = json.load(f)
            except Exception:
                data = []
            data = [t for t in data if now - t < _RL_WINDOW]
            if len(data) >= _RL_MAX_ATTEMPTS:
                f.seek(0); json.dump(data, f); f.truncate()
                return True
            data.append(now)
            f.seek(0); json.dump(data, f); f.truncate()
            return False
    except FileNotFoundError:
        with open(path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump([now], f)
        return False


# ── crypto helpers ─────────────────────────────────────────────────────────────

def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def hmac_sign(payload_bytes: bytes) -> bytes:
    return hmac.new(VERIFY_SECRET.encode(), payload_bytes, hashlib.sha256).digest()


# ── challenge verification (same as verify-code.py) ───────────────────────────

def verify_challenge(email: str, code: str, challenge: str) -> tuple[bool, str]:
    try:
        payload_b64, sig_b64 = challenge.split(".", 1)
    except ValueError:
        return False, "Malformed challenge"
    try:
        payload_bytes = b64u_decode(payload_b64)
        expected_sig  = hmac_sign(payload_bytes)
        actual_sig    = b64u_decode(sig_b64)
    except Exception:
        return False, "Invalid challenge encoding"
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


# ── session token ──────────────────────────────────────────────────────────────

def make_session_token(email: str) -> str:
    exp     = int(time.time()) + SESSION_TTL
    payload = json.dumps({"email": email, "exp": exp, "type": "session"},
                         separators=(",", ":")).encode()
    sig     = hmac_sign(payload)
    return f"{b64u(payload)}.{b64u(sig)}"

def verify_session_token(token: str) -> tuple[bool, str, str]:
    """Return (ok, email, error_msg)."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return False, "", "Malformed token"
    try:
        payload_bytes = b64u_decode(payload_b64)
        expected_sig  = hmac_sign(payload_bytes)
        actual_sig    = b64u_decode(sig_b64)
    except Exception:
        return False, "", "Invalid token encoding"
    if not hmac.compare_digest(expected_sig, actual_sig):
        return False, "", "Invalid token signature"
    try:
        payload = json.loads(payload_bytes.decode())
    except Exception:
        return False, "", "Invalid token payload"
    if payload.get("type") != "session":
        return False, "", "Wrong token type"
    if int(payload.get("exp", 0)) < int(time.time()):
        return False, "", "Session expired. Please sign in again."
    email = payload.get("email", "").strip().lower()
    if not email:
        return False, "", "Token missing email"
    return True, email, ""


# ── Stripe helper ──────────────────────────────────────────────────────────────

def stripe_get_active_sub(email: str) -> tuple[bool, int]:
    """Return (has_active_sub, current_period_end)."""
    creds   = base64.b64encode(f"{STRIPE_SECRET}:".encode()).decode()
    url     = "https://api.stripe.com/v1/customers?email=" + urllib.parse.quote(email) + "&limit=5"
    req     = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        customers = json.loads(resp.read())
    for customer in customers.get("data", []):
        cid     = customer["id"]
        sub_url = f"https://api.stripe.com/v1/subscriptions?customer={cid}&status=active&limit=1"
        sub_req = urllib.request.Request(sub_url, headers={"Authorization": f"Basic {creds}"})
        with urllib.request.urlopen(sub_req, timeout=10) as sub_resp:
            subs = json.loads(sub_resp.read())
        if subs.get("data"):
            return True, subs["data"][0].get("current_period_end", 0)
    return False, 0


# ── route handlers ─────────────────────────────────────────────────────────────

def handle_sign_in(body: dict) -> tuple[dict, int]:
    email     = body.get("email", "").strip().lower()
    code      = body.get("code", "").strip()
    challenge = body.get("challenge", "").strip()

    if not email or not code or not challenge:
        return {"ok": False, "error": "Missing email, code, or challenge"}, 400
    if not VERIFY_SECRET:
        return {"ok": False, "error": "Server misconfigured"}, 500
    if _is_rate_limited(email):
        return {"ok": False, "error": "Too many attempts. Please wait 10 minutes."}, 429

    ok, err = verify_challenge(email, code, challenge)
    if not ok:
        return {"ok": False, "error": err}, 403

    pro, period_end = False, 0
    if STRIPE_SECRET:
        try:
            pro, period_end = stripe_get_active_sub(email)
        except Exception:
            pass   # Stripe outage — still issue token, Pro defaults to False

    token = make_session_token(email)
    return {"ok": True, "token": token, "email": email, "pro": pro, "period_end": period_end}, 200


def handle_profile(auth_header: str) -> tuple[dict, int]:
    if not auth_header.startswith("Bearer "):
        return {"ok": False, "error": "Missing Authorization header"}, 401
    token = auth_header[len("Bearer "):].strip()

    if not VERIFY_SECRET:
        return {"ok": False, "error": "Server misconfigured"}, 500

    ok, email, err = verify_session_token(token)
    if not ok:
        return {"ok": False, "error": err}, 401

    pro, period_end = False, 0
    if STRIPE_SECRET:
        try:
            pro, period_end = stripe_get_active_sub(email)
        except Exception:
            # Stripe outage — token valid but Pro unknown; client keeps cached state
            return {"ok": True, "email": email, "pro": None, "period_end": 0}, 200

    return {"ok": True, "email": email, "pro": pro, "period_end": period_end}, 200


def handle_sign_out() -> tuple[dict, int]:
    return {"ok": True}, 200


# ── Vercel handler class ───────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def _get_action(self):
        """Resolve action from query param (set by vercel.json dest) or URL path."""
        parsed = urllib.parse.urlparse(self.path)
        qs     = urllib.parse.parse_qs(parsed.query)
        action = qs.get("action", [""])[0]
        if not action:
            # Fallback: derive from path (e.g. /api/auth/sign-in → sign-in)
            path = parsed.path.rstrip("/")
            action = path.split("/")[-1]
        return action

    def do_GET(self):
        action = self._get_action()
        if action == "profile":
            data, status = handle_profile(self.headers.get("Authorization", ""))
        else:
            data, status = {"ok": False, "error": "Not found"}, 404
        self._json(data, status)

    def do_POST(self):
        action = self._get_action()
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        if action == "sign-in":
            data, status = handle_sign_in(body)
        elif action == "sign-out":
            data, status = handle_sign_out()
        elif action == "profile":
            data, status = handle_profile(self.headers.get("Authorization", ""))
        else:
            data, status = {"ok": False, "error": "Not found"}, 404
        self._json(data, status)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        origin  = self.headers.get("Origin", "")
        allowed = origin if origin in ALLOWED_ORIGINS else "https://agendaburn.com"
        self.send_header("Access-Control-Allow-Origin",  allowed)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Vary", "Origin")

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
