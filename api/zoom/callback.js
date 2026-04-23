// Handles Zoom OAuth callback — exchanges code for token, redirects to app
export default async function handler(req, res) {
  const { code, error, state } = req.query;

  if (error) {
    return res.redirect(`/app?zoom_error=${encodeURIComponent(error)}`);
  }

  // CSRF: validate state parameter against the cookie set in auth.js
  const cookieHeader = req.headers.cookie || "";
  const cookieState = cookieHeader
    .split(";")
    .map(c => c.trim())
    .find(c => c.startsWith("zoom_oauth_state="))
    ?.split("=")[1] || "";

  if (!state || !cookieState || state !== cookieState) {
    return res.redirect(`/app?zoom_error=${encodeURIComponent("Invalid OAuth state — possible CSRF. Please try connecting again.")}`);
  }

  // Clear the state cookie now that it's been validated
  res.setHeader("Set-Cookie", "zoom_oauth_state=; Max-Age=0; Path=/api/zoom; HttpOnly; Secure; SameSite=Lax");

  if (!code) {
    return res.redirect(`/app?zoom_error=${encodeURIComponent("No authorization code received")}`);
  }

  const clientId     = (process.env.ZOOM_CLIENT_ID || "").trim();
  const clientSecret = (process.env.ZOOM_CLIENT_SECRET || "").trim();
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  const protocol = host.includes("localhost") ? "http" : "https";
  const redirectUri  = (process.env.ZOOM_REDIRECT_URI || `${protocol}://${host}/api/zoom/callback`).trim();

  if (!clientId || !clientSecret) {
    return res.status(500).json({ error: "Zoom credentials not configured" });
  }

  try {
    const credentials = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");
    const tokenRes = await fetch("https://zoom.us/oauth/token", {
      method: "POST",
      headers: {
        "Authorization": `Basic ${credentials}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri,
      }),
    });

    if (!tokenRes.ok) {
      const err = await tokenRes.text();
      // Log diagnostic info (without exposing full credentials)
      console.error("Zoom token exchange failed:", {
        error: err,
        clientIdPrefix: clientId.substring(0, 6),
        clientIdLength: clientId.length,
        clientSecretLength: clientSecret.length,
        redirectUri: redirectUri,
        host: host,
      });
      return res.redirect(`/app?zoom_error=${encodeURIComponent("Token exchange failed: " + err)}`);
    }

    const tokenData = await tokenRes.json();

    // Pass token back to frontend via URL fragment (not query string — keeps it out of server logs)
    const token = encodeURIComponent(JSON.stringify({
      access_token:  tokenData.access_token,
      refresh_token: tokenData.refresh_token,
      expires_in:    tokenData.expires_in,
      obtained_at:   Date.now(),
    }));

    res.redirect(`/app?zoom_token=${token}`);
  } catch (e) {
    res.redirect(`/app?zoom_error=${encodeURIComponent(e.message)}`);
  }
}
