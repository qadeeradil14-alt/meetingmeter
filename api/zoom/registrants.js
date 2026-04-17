// Fetches attendees for a specific Zoom meeting — combines registrants and meeting_invitees
export default async function handler(req, res) {
  const { access_token, meeting_id } = req.query;

  if (!access_token || !meeting_id) {
    return res.status(400).json({ error: "access_token and meeting_id required" });
  }

  const authHeaders = {
    Authorization: `Bearer ${access_token}`,
    "Content-Type": "application/json",
  };

  const combined = [];
  const seen = new Set();
  let meetingTopic = "";
  let meetingStart = "";

  // 1) Registrants (only present for meetings with registration enabled / webinars)
  try {
    const r = await fetch(
      `https://api.zoom.us/v2/meetings/${meeting_id}/registrants?page_size=100`,
      { headers: authHeaders }
    );
    if (r.ok) {
      const data = await r.json();
      for (const reg of data.registrants || []) {
        const email = (reg.email || "").toLowerCase();
        if (!email || seen.has(email)) continue;
        seen.add(email);
        combined.push({
          first_name: reg.first_name || "",
          last_name:  reg.last_name || "",
          email:      reg.email || "",
        });
      }
    }
  } catch (_) { /* ignore — registrants are optional */ }

  // 2) Meeting invitees from meeting details (only populated on paid Zoom accounts)
  try {
    const r = await fetch(
      `https://api.zoom.us/v2/meetings/${meeting_id}`,
      { headers: authHeaders }
    );
    if (r.ok) {
      const data = await r.json();
      meetingTopic = data?.topic || "";
      meetingStart = data?.start_time || "";
      const invitees = data?.settings?.meeting_invitees || [];
      for (const inv of invitees) {
        const email = (inv.email || "").toLowerCase();
        if (!email || seen.has(email)) continue;
        seen.add(email);
        combined.push({
          first_name: "",
          last_name:  "",
          email:      inv.email,
        });
      }
    }
  } catch (_) { /* ignore */ }

  // Return registrants + meeting metadata so frontend can match against calendar events as a fallback
  res.status(200).json({ registrants: combined, topic: meetingTopic, start_time: meetingStart });
}
