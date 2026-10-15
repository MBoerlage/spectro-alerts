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

V ≤ 10 (adjustable, the practical StarEx LR limit), at least 1 h above 20° after nautical twilight (Sun below −12°) from Tomball, Moon
separation warning below 30°, 5 arcsec cross-match radius. Objects up to 2 mag fainter go on
a watch list.

## Sky check

Each run rates sunset to midnight with Open-Meteo hourly forecasts: an hour is clear when
effective cloud (low and mid at full weight, high at half) is at most 20%, rain chance at most
10% and gusts at most 15 mph. At least one clear hour in a row gives GO. 7Timer! ASTRO is a
second opinion (MAYBE when they disagree) and adds seeing and transparency. The digest links
Clear Outside for a visual check. Thresholds are in the `weather` section of `config.yaml`.

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

## Email

After each run the workflow emails the digest through [Resend](https://resend.com)
(`python -m spectro_alerts.mailer`; add `--dry-run` to print it instead). It needs two
repository secrets: `RESEND_API_KEY` and `EMAIL_TO`. Manual runs have a "Email the digest"
box to untick for silent test runs.
