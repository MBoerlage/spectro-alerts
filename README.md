# Spectro Alerts

Daily transient alerts for backyard spectroscopy from Tomball, TX. It goes to the original
sources (CBAT, TNS, ATel) instead of waiting for relayed notices, keeps only objects bright
enough for a StarEx LR and visible tonight, and publishes the result for an evening digest.

## How it runs

1. **GitHub Actions, 20:30 UTC (15:30 CDT / 14:30 CST):** `python -m spectro_alerts.run`
   fetches every source, cross-matches by position, applies the filters in `config.yaml`, and
   commits `docs/candidates.json`, `docs/index.html` and `state/objects.json`.
2. **GitHub Pages** serves `docs/` at https://mboerlage.github.io/spectro-alerts/.
3. **Claude scheduled task, 16:00 America/Chicago:** follows `claude/daily_digest_prompt.md`,
   adds ARAS/AAVSO campaign requests, writes the digest and emails it.

## Sources (Phase 1)

| Source | How | Notes |
| --- | --- | --- |
| CBAT TOCP | Parses the `tocp.html` index (plain http) and follow-up pages | The RSS feed stopped updating in Aug 2026. PNV and TCP only; TNS covers supernovae. |
| TNS | Public CSV search export | Discovery magnitude only. Phase 2: authenticated API with a bot key in a GitHub secret. |
| ATel | RSS | Annotates objects by position or name; listed as recent headlines. |

## Filters (`config.yaml`)

V ≤ 12 (adjustable), at least 1 h above 20° during astronomical darkness from Tomball, Moon
separation warning below 30°, 5 arcsec cross-match radius. Objects up to 2 mag fainter go on
a watch list.

## Local use

```bash
pip install -r requirements.txt pytest ruff
python -m pytest -q
python -m spectro_alerts.run --date 2026-10-15
```

## Outputs

- `docs/candidates.json`: targets, watch list, recent ATels, per-source status.
- `docs/index.html`: the same as a readable page.
- `state/objects.json`: first-seen dates, names, sources and magnitude history (90 days).
