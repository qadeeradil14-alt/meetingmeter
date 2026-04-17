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

  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
  });

  res.redirect(`https://zoom.us/oauth/authorize?${params}`);
}
