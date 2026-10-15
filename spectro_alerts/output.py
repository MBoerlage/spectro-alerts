"""Write candidates.json (for the Claude task) and a simple digest page (GitHub Pages)."""

from __future__ import annotations

import html
import json
from pathlib import Path


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n")


def _row(t: dict) -> str:
    v = t["visibility"]
    mag = "" if t["mag"] is None else f"{t['mag']:.1f}"
    flags = []
    if t["is_new"]:
        flags.append("NEW")
    if t["spectroscopically_confirmed"]:
        flags.append("spectrum reported")
    if v["moon_sep"] is not None and t["moon_warning"]:
        flags.append(f"Moon {v['moon_sep']:.0f}°")
    links = " ".join(
        f'<a href="{html.escape(s["url"])}">{html.escape(s["source"])}</a>'
        for s in t["reports"]
        if s["url"]
    )
    return (
        "<tr>"
        f"<td><b>{html.escape(t['name'])}</b><br><small>{html.escape(t['obj_type'])}</small></td>"
        f"<td>{mag} <small>{html.escape(t['mag_band'] or '')}</small></td>"
        f"<td>{t['ra_hms']}<br>{t['dec_dms']}</td>"
        f"<td>{v['start'] or '-'}–{v['end'] or '-'}<br><small>{v['hours']:.1f} h, "
        f"max {v['max_alt'] or 0:.0f}° at {v['max_alt_time'] or '-'}</small></td>"
        f"<td>{html.escape(', '.join(flags))}</td><td>{links}</td>"
        "</tr>"
    )


VERDICT_COLORS = {"GO": "#1e8e3e", "MAYBE": "#b06d00", "NO-GO": "#c5221f", "UNKNOWN": "#666"}


def _weather_block(w: dict) -> str:
    color = VERDICT_COLORS.get(w.get("verdict", "UNKNOWN"), "#666")
    hours = "".join(
        f'<td title="{html.escape(h["why_not"] or "clear")}" '
        f'style="background:{"#1e8e3e33" if h["clear"] else "#c5221f33"}">'
        f"{h['hour'][:2]}<br><small>{h['cloud_eff']:.0f}%<br>{h['rain_pct']:.0f}%<br>"
        f"{h['gust_mph']:.0f}</small></td>"
        for h in w.get("hours", [])
    )
    strip = (
        f'<table class="wx"><tr><th><small>hour<br>cloud<br>rain<br>gust mph</small></th>'
        f"{hours}</tr></table>"
        if hours
        else ""
    )
    errs = "; ".join(f"{k} failed" for k in w.get("errors", {}))
    link = w.get("clear_outside_url")
    return (
        f'<p class="verdict" style="border-color:{color}"><b style="color:{color}">'
        f"{html.escape(w.get('line', ''))}</b>"
        + (f"<br><small>{html.escape(errs)}</small>" if errs else "")
        + "</p>"
        + strip
        + (
            f'<p class="meta">Visual check: <a href="{html.escape(link)}">Clear Outside</a></p>'
            if link
            else ""
        )
    )


def write_page(path: Path, payload: dict) -> None:
    def table(rows: list[dict]) -> str:
        if not rows:
            return "<p><i>None tonight.</i></p>"
        head = (
            "<tr><th>Object</th><th>Mag</th><th>RA / Dec (J2000)</th>"
            "<th>Window (local)</th><th>Flags</th><th>Sources</th></tr>"
        )
        return f"<table>{head}{''.join(_row(t) for t in rows)}</table>"

    status = " · ".join(
        f"{s['source']}: {'ok' if s['ok'] else 'FAILED'} ({s['fetched']})"
        for s in payload["source_status"]
    )
    night = payload["night"]
    atel = (
        "".join(
            f'<li><a href="{html.escape(i["url"])}">{html.escape(i["title"])}</a></li>'
            for i in payload["atel_recent"]
            if i["of_interest"]
        )
        or "<li><i>None flagged.</i></li>"
    )
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spectro Alerts</title>
<style>
body{{font:15px/1.45 system-ui,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;
color:#1d1d1f;background:#fbfbfa}}
@media (prefers-color-scheme:dark){{body{{color:#e8e8e6;background:#1a1a19}}a{{color:#8ab4f8}}}}
table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}
th,td{{text-align:left;padding:8px 6px;border-bottom:1px solid #8884;vertical-align:top}}
small{{opacity:.7}} .meta{{opacity:.75;font-size:13px}}
.verdict{{border-left:4px solid;padding:8px 12px;margin:16px 0 8px;font-size:16px}}
table.wx{{width:auto}} table.wx td,table.wx th{{text-align:center;padding:4px 8px;border:0}}
</style></head><body>
<h1>Spectro Alerts · {html.escape(payload["site"]["name"])}</h1>
<p class="meta">Generated {payload["generated_utc"]} UTC · darkness {night["dark_start"]} to
{night["dark_end"]} · V ≤ {payload["filters"]["mag_max"]}, at least
{payload["filters"]["min_hours"]} h above {payload["filters"]["min_alt_deg"]}°</p>
{_weather_block(payload.get("weather", {}))}
<h2>Targets tonight ({len(payload["targets"])})</h2>{table(payload["targets"])}
<h2>Watch list ({len(payload["watch"])})</h2>
<p class="meta">Visible tonight but fainter than the ceiling, or brightness unknown.</p>
{table(payload["watch"])}
<h2>Recent ATels of interest</h2><ul>{atel}</ul>
<p class="meta">Sources: {html.escape(status)} ·
<a href="candidates.json">candidates.json</a></p>
</body></html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page)
