import { randomBytes } from "crypto";

// Redirects user to Zoom OAuth authorization page
export default function handler(req, res) {
  const clientId = (process.env.ZOOM_CLIENT_ID || "").trim();

  if (!clientId) {
    return res.status(500).json({ error: "ZOOM_CLIENT_ID not configured" });
  }

  // Build redirect URI from the actual request host so it works on any environment
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  const protocol = host.includes("localhost") ? "http" : "https";
  const redirectUri = (process.env.ZOOM_REDIRECT_URI || `${protocol}://${host}/api/zoom/callback`).trim();

  // Generate CSRF state token — stored in cookie, validated in callback
  const state = randomBytes(16).toString("hex");

  // Set state in a short-lived, httpOnly, SameSite=Lax cookie
  const cookieMaxAge = 10 * 60; // 10 minutes
  res.setHeader(
    "Set-Cookie",
    `zoom_oauth_state=${state}; Max-Age=${cookieMaxAge}; Path=/api/zoom; HttpOnly; Secure; SameSite=Lax`
  );

  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    state,
  });

  res.redirect(`https://zoom.us/oauth/authorize?${params}`);
}
