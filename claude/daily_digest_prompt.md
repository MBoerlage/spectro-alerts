# Daily spectroscopy digest (Claude scheduled task, 16:00 America/Chicago)

You are writing Matt's evening target digest for backyard spectroscopy (StarEx LR spectrograph,
8" SCT and 8"/10" Newtonians) from Tomball, TX. Each run starts fresh; everything you need is
below and in the files it points to.

## 1. Read today's candidates
WebFetch https://raw.githubusercontent.com/MBoerlage/spectro-alerts/main/docs/candidates.json
and ask for the full JSON.
- Check `generated_utc`. If it is not from today (UTC), say at the top of the digest that the
  GitHub job has not run today and use the file anyway, clearly labelled as yesterday's.
- `targets`: pass every filter (V ≤ mag_max, at least min_hours above min_alt in darkness).
- `watch`: visible tonight but fainter than the ceiling or with unknown brightness.
- `source_status`: name any source that failed.
- `weather`: the clear-sky verdict for sunset to midnight (GO / MAYBE / NO-GO / UNKNOWN), its
  one-line summary in `line`, hourly detail in `hours`, and a Clear Outside link.

## 1b. TNS fallback (only if TNS failed in `source_status`)
TNS blocks requests from GitHub's servers. WebFetch
https://www.wis-tns.org/search?date_start%5Bdate%5D=YYYY-MM-DD&date_end%5Bdate%5D=YYYY-MM-DD&discovery_mag_max=15&num_page=500&format=csv
with date_start 30 days before today and date_end tomorrow (UTC), and ask for every row's Name,
RA, DEC, Obj. Type, Discovery Mag/Flux and Discovery Date verbatim. Keep rows with discovery
magnitude ≤ `filters.mag_max` + `filters.watch_margin`. Match them to targets/watch objects by
name or by RA/Dec within a few arcseconds. Any TNS object not already in the JSON goes in its own
short section, "TNS, not visibility-checked", with RA/Dec, magnitude and type. Do not guess its
visibility.

## 2. Check campaign requests
- ARAS Eruptive Stars forum: https://www.spectro-aras.com/forum/ (recent topics only).
- AAVSO Alert Notices: https://www.aavso.org/alert-notices (newest few).
For each request from the last 14 days, decide whether it asks for spectra and whether it
matches a target or watch object (by name or position). A matching request moves that object
to the top. A campaign object not in the JSON: list it separately as "Campaign, not checked
for visibility". Never invent coordinates or magnitudes.

## 3. Write the digest
Start with the sky verdict line exactly as in `weather.line`, then the Clear Outside link. If the
verdict is NO-GO, say so plainly in the email subject-style first line ("NO-GO tonight: ...")
and keep the rest brief. Plain text, short, best target first. For each target (at most 6):
- Name (and aliases), type, magnitude with band and whether it is a discovery value
- Tonight's window (local time), max altitude and when, Moon note if `moon_warning`
- One line on why it matters for a spectrum now (new nova, unclassified, campaign request,
  spectrum already reported, etc.) and which telescope you would use
- Source links
Then: up to 3 watch-list objects worth a look, failed sources, and the digest page link
https://mboerlage.github.io/spectro-alerts/ (if it does not load, GitHub Pages is not on yet;
link https://github.com/MBoerlage/spectro-alerts/blob/main/docs/candidates.json instead).

If there are no targets, say so in one line and give the watch list.

## 4. Finish
Your final message is the digest; the scheduled task's email notification sends it.
