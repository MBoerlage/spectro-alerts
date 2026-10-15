"""Write candidates.json and the GitHub Pages digest, which uses the email's layout."""

from __future__ import annotations

import json
from pathlib import Path

from . import mailer


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n")


def write_page(path: Path, payload: dict) -> None:
    body = mailer.html_body(payload, chart_src=payload.get("sky_chart"), page=True)
    date = payload["night"]["date"]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spectro Alerts</title>
<style>body{{margin:0;padding:20px 16px 40px;background:#ffffff}}
h1{{font:700 22px/1.3 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
color:#202124;max-width:680px;margin:0 auto 4px}}
.sub{{font:13px -apple-system,Segoe UI,Roboto,sans-serif;color:#5f6368;max-width:680px;
margin:0 auto 14px}}</style></head><body>
<h1>Spectro Alerts · Tomball</h1>
<div class="sub">{mailer.subject(payload)} · night of {date}</div>
{body}
</body></html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page)
