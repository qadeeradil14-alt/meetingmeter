// Proxies Zoom meetings API — avoids CORS issues from the browser
export default async function handler(req, res) {
  const { access_token } = req.query;

  if (!access_token) {
    return res.status(400).json({ error: "access_token required" });
  }

  try {
    // Fetch the list of recent/upcoming meetings for the authenticated user
    const meetingsRes = await fetch(
      "https://api.zoom.us/v2/users/me/meetings?type=upcoming&page_size=25",
      {
        headers: {
          Authorization: `Bearer ${access_token}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (!meetingsRes.ok) {
      const err = await meetingsRes.text();
      return res.status(meetingsRes.status).json({ error: err });
    }

    const data = await meetingsRes.json();
    res.status(200).json(data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
