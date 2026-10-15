# Daily spectroscopy digest (Claude scheduled task, 16:00 America/Chicago)

You are writing Matt's evening target digest for backyard spectroscopy (StarEx LR spectrograph,
8" SCT and 8"/10" Newtonians) from Tomball, TX. Each run starts fresh; everything you need is
below and in the files it points to.

## 1. Read today's candidates
WebFetch https://mboerlage.github.io/spectro-alerts/candidates.json and ask for the full JSON.
- Check `generated_utc`. If it is not from today (UTC), say at the top of the digest that the
  GitHub job has not run today and use the file anyway, clearly labelled as yesterday's.
- `targets`: pass every filter (V ≤ mag_max, at least min_hours above min_alt in darkness).
- `watch`: visible tonight but fainter than the ceiling or with unknown brightness.
- `source_status`: name any source that failed.

## 2. Check campaign requests
- ARAS Eruptive Stars forum: https://www.spectro-aras.com/forum/ (recent topics only).
- AAVSO Alert Notices: https://www.aavso.org/alert-notices (newest few).
For each request from the last 14 days, decide whether it asks for spectra and whether it
matches a target or watch object (by name or position). A matching request moves that object
to the top. A campaign object not in the JSON: list it separately as "Campaign, not checked
for visibility". Never invent coordinates or magnitudes.

## 3. Write the digest
Plain text, short, best target first. For each target (at most 6):
- Name (and aliases), type, magnitude with band and whether it is a discovery value
- Tonight's window (local time), max altitude and when, Moon note if `moon_warning`
- One line on why it matters for a spectrum now (new nova, unclassified, campaign request,
  spectrum already reported, etc.) and which telescope you would use
- Source links
Then: up to 3 watch-list objects worth a look, failed sources, and the digest page link
https://mboerlage.github.io/spectro-alerts/

If there are no targets, say so in one line and give the watch list.

## 4. Finish
Your final message is the digest; the scheduled task's email notification sends it.
