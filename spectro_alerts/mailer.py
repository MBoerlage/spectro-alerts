"""Compose the evening digest from candidates.json and send it through Resend.

The recipient comes from the EMAIL_TO secret and the key from RESEND_API_KEY, so neither
appears in this public repository or its logs.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import logging
import os
import sys
from pathlib import Path

import requests

log = logging.getLogger("spectro_alerts.mailer")

RESEND_URL = "https://api.resend.com/emails"
SENDER = "Spectro Alerts <onboarding@resend.dev>"
PAGE_URL = "https://mboerlage.github.io/spectro-alerts/"


def _mag(t: dict) -> str:
    if t["mag"] is None:
        return "mag ?"
    kind = f" ({t['mag_kind']})" if t.get("mag_kind") else ""
    return f"{t['mag']:.1f} {t.get('mag_band') or ''}{kind}".strip()


def _window(t: dict) -> str:
    v = t["visibility"]
    return (
        f"{v['start'] or '-'}-{v['end'] or '-'} ({v['hours']:.1f} h), "
        f"max {v['max_alt'] or 0:.0f} deg at {v['max_alt_time'] or '-'}"
    )


def _notes(t: dict) -> list[str]:
    out = []
    if t.get("is_new"):
        out.append("NEW")
    if t.get("spectroscopically_confirmed"):
        out.append("spectrum already reported")
    if t.get("has_atel"):
        out.append("ATel")
    if t.get("moon_warning"):
        out.append(f"Moon {t['visibility']['moon_sep']:.0f} deg away")
    return out


def _links(t: dict) -> list[tuple[str, str]]:
    seen, out = set(), []
    for r in t.get("reports", []):
        if r.get("url") and r["url"] not in seen:
            seen.add(r["url"])
            out.append((r["source"], r["url"]))
    if t.get("aras_url"):
        out.append(("ARAS spectra", t["aras_url"]))
    return out


SKY_WORDS = {"GO": "YES", "MAYBE": "MAYBE", "NO-GO": "NO", "UNKNOWN": "UNKNOWN"}


def subject(p: dict) -> str:
    """e.g. "SPECTRO ALERT: YES, good skies? MAYBE" (Matt's format, 2026-10-15)."""
    alert = "YES" if p["targets"] else "NO"
    sky = SKY_WORDS.get(p.get("weather", {}).get("verdict", "UNKNOWN"), "UNKNOWN")
    return f"SPECTRO ALERT: {alert}, good skies? {sky}"


def _sections(p: dict) -> list[tuple[str, list[dict], str]]:
    f = p["filters"]
    low = f["mag_max"] + f["watch_margin"]
    return [
        (f"Targets (V <= {f['mag_max']})", p["targets"], "None tonight."),
        (
            f"Bright but poorly placed (to V {low}, under {f['min_hours']} h above "
            f"{f['min_alt_deg']} deg)",
            p.get("poorly_placed", []),
            "",
        ),
        (f"Watch list (to V {low})", p["watch"][:5], ""),
    ]


def text_body(p: dict) -> str:
    w = p.get("weather", {})
    n = p["night"]
    lines = [
        w.get("line", "Weather: unknown"),
        f"Clear Outside: {w.get('clear_outside_url', '')}",
        f"Sunset {n['sunset']}, observing from {n['dark_start']} to {n['dark_end']}.",
        "",
    ]
    for title, rows, empty in _sections(p):
        if not rows and not empty:
            continue
        lines.append(title)
        lines.append("-" * len(title))
        if not rows:
            lines.append(f"  {empty}")
        for t in rows:
            names = ", ".join(x for x in t["names"] if x != t["name"])
            lines.append(f"- {t['name']}" + (f" ({names})" if names else ""))
            lines.append(f"  {t['obj_type']}, {_mag(t)}, {t['ra_hms']} {t['dec_dms']}")
            lines.append(f"  Tonight: {_window(t)}")
            if _notes(t):
                lines.append(f"  {'; '.join(_notes(t))}")
            for src, url in _links(t):
                lines.append(f"  {src}: {url}")
        lines.append("")
    atels = [i for i in p.get("atel_recent", []) if i.get("of_interest")]
    if atels:
        lines.append("RECENT ATELS OF INTEREST")
        lines += [f"- {i['title']}\n  {i['url']}" for i in atels[:5]]
        lines.append("")
    failed = [s for s in p["source_status"] if not s["ok"]]
    if failed:
        lines.append("Sources that failed today: " + ", ".join(s["source"] for s in failed))
    lines.append(f"Full page: {PAGE_URL}")
    return "\n".join(lines) + "\n"


VERDICT_COLORS = {"GO": "#1e8e3e", "MAYBE": "#b06d00", "NO-GO": "#c5221f", "UNKNOWN": "#666666"}
VERDICT_WORDS = {
    "GO": "Clear skies",
    "MAYBE": "Maybe clear",
    "NO-GO": "Not clear",
    "UNKNOWN": "Unknown",
}

# Email clients ignore <style> blocks unevenly, so every style is inline.
FONT = "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"
TH = (
    "text-align:left;padding:6px 8px;font-size:12px;color:#5f6368;font-weight:600;"
    "border-bottom:2px solid #dadce0;white-space:nowrap"
)
TD = "padding:8px;border-bottom:1px solid #eceff1;vertical-align:top;font-size:14px"
GOOD, BAD = "#e6f4ea", "#fce8e6"


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:1px 6px;border-radius:9px;font-size:11px;'
        f'font-weight:600;color:#fff;background:{color};margin-left:4px">{html.escape(text)}</span>'
    )


def _weather_html(w: dict) -> str:
    e = html.escape
    verdict = w.get("verdict", "UNKNOWN")
    color = VERDICT_COLORS.get(verdict, "#666666")
    st = w.get("seven_timer") or {}
    seeing = (
        f'Seeing {e(st["seeing_arcsec"])}" · transparency {st["transparency_best"]}/8 (1 = best)'
        if st.get("seeing_arcsec")
        else ""
    )
    clear = (
        f"clear {w['clear_from']}–{w['clear_to']}"
        if w.get("clear_from")
        else "no clear hour before midnight"
    )
    out = [
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{color};border-radius:8px;margin:0 0 12px"><tr>'
        f'<td style="padding:12px 16px;color:#fff">'
        f'<div style="font-size:20px;font-weight:700">{e(VERDICT_WORDS.get(verdict, verdict))}'
        f" · {e(clear)}</div>"
        + (
            f'<div style="font-size:13px;opacity:.9;margin-top:2px">{seeing}</div>'
            if seeing
            else ""
        )
        + "</td></tr></table>"
    ]
    hours = w.get("hours_night") or w.get("hours", [])
    if hours:
        cell = "padding:4px 2px;text-align:center;font-size:12px"

        def row(label: str, key: str) -> str:
            cells = "".join(
                f'<td style="{cell};background:{GOOD if h["clear"] else BAD}">{h[key]:.0f}</td>'
                for h in hours
            )
            return (
                f'<tr><td style="padding:4px 6px 4px 0;font-size:12px;color:#5f6368;'
                f'white-space:nowrap">{label}</td>{cells}</tr>'
            )

        # Hours that count for the verdict (sunset to midnight) are bold; the rest is extra.
        head = "".join(
            f'<td style="{cell};font-weight:{700 if h.get("in_verdict", True) else 400};'
            f'color:{"#202124" if h.get("in_verdict", True) else "#80868b"}">'
            f"{h['hour'][:2]}</td>"
            for h in hours
        )
        out.append(
            '<table width="100%" cellpadding="0" cellspacing="2" '
            'style="border-collapse:separate;margin:0 0 4px;table-layout:fixed">'
            f'<tr><td style="padding:4px 6px 4px 0;font-size:12px;color:#5f6368;width:52px">'
            f"Hour</td>{head}</tr>"
            + row("Cloud %", "cloud_eff")
            + row("Rain %", "rain_pct")
            + row("Gust mph", "gust_mph")
            + "</table>"
        )
        t = w.get("thresholds", {})
        out.append(
            f'<div style="font-size:12px;color:#5f6368;margin:0 0 4px">Green = clear: cloud '
            f"≤{t.get('max_cloud_pct', 20)}%, rain ≤{t.get('max_rain_pct', 10)}%, gusts "
            f"≤{t.get('max_gust_mph', 15)} mph. Bold hours (sunset–midnight) set the verdict. "
            f'<a href="{e(w.get("clear_outside_url", ""))}">Clear Outside</a></div>'
        )
    return "".join(out)


def _table(rows: list[dict], muted: bool = False) -> str:
    e = html.escape
    head = "".join(
        f'<th style="{TH}">{h}</th>' for h in ("Object", "Mag", "Tonight", "Max alt", "Links")
    )
    body = []
    for t in rows:
        v = t["visibility"]
        badges = ""
        if t.get("is_new"):
            badges += _badge("NEW", "#1a73e8")
        if t.get("confirmed_nova"):
            badges += _badge("confirmed nova", "#c5221f")
        elif t.get("spectroscopically_confirmed"):
            badges += _badge("spectrum", "#7b1fa2")
        if t.get("has_atel"):
            badges += _badge("ATel", "#5f6368")
        if t.get("moon_warning"):
            badges += _badge(f"Moon {v['moon_sep']:.0f}°", "#b06d00")
        alias = ", ".join(x for x in t["names"] if x != t["name"])
        sub = e(t["obj_type"]) + (f" · {e(alias)}" if alias else "")
        mag = "?" if t["mag"] is None else f"{t['mag']:.1f}"
        band = e(t.get("mag_band") or "")
        links = "<br>".join(f'<a href="{e(u)}">{e(s.split()[0])}</a>' for s, u in _links(t))
        body.append(
            "<tr>"
            f'<td style="{TD}"><b>{e(t["name"])}</b>{badges}<br>'
            f'<span style="font-size:12px;color:#5f6368">{sub}<br>'
            f"{t['ra_hms'][:8]} {t['dec_dms'][:9]}</span></td>"
            f'<td style="{TD};white-space:nowrap"><b>{mag}</b><br>'
            f'<span style="font-size:12px;color:#5f6368">{band} {e(t.get("mag_kind") or "")}'
            "</span></td>"
            f'<td style="{TD};white-space:nowrap">{v["start"] or "-"}–{v["end"] or "-"}<br>'
            f'<span style="font-size:12px;color:#5f6368">{v["hours"]:.1f} h</span></td>'
            f'<td style="{TD};white-space:nowrap">{v["max_alt"] or 0:.0f}°<br>'
            f'<span style="font-size:12px;color:#5f6368">at {v["max_alt_time"] or "-"}</span></td>'
            f'<td style="{TD};font-size:12px">{links}</td>'
            "</tr>"
        )
    style = "border-collapse:collapse;width:100%;margin:0 0 8px" + (";opacity:.8" if muted else "")
    rows_html = "".join(body)
    return (
        f'<table cellpadding="0" cellspacing="0" style="{style}"><tr>{head}</tr>{rows_html}</table>'
    )


def html_body(
    p: dict, chart_cid: str | None = None, chart_src: str | None = None, page: bool = False
) -> str:
    """Shared by the email (chart as cid: image) and the GitHub Pages digest (chart as a file).

    On the page everything is listed (no 5-item cap) and the footer links the raw JSON.
    """
    if chart_cid:
        chart_src = f"cid:{chart_cid}"
    e = html.escape
    w = p.get("weather", {})
    n = p["night"]
    f = p["filters"]
    low = f["mag_max"] + f["watch_margin"]
    h2 = 'style="font-size:16px;margin:22px 0 6px"'
    note = 'style="font-size:12px;color:#5f6368;margin:0 0 6px"'
    parts = [
        f'<div style="{FONT};color:#202124;max-width:680px;margin:0 auto">',
        _weather_html(w),
        f"<div {note}>Sunset {n['sunset']} · sunrise {n.get('sunrise') or '-'} · "
        f"observing {n['dark_start']}–{n['dark_end']} "
        f"(Sun below {abs(f['sun_alt_max_deg'])}°) · Tomball</div>",
        f"<h2 {h2}>Targets tonight ({len(p['targets'])})</h2>",
        f"<div {note}>V ≤ {f['mag_max']}, at least {f['min_hours']} h above "
        f"{f['min_alt_deg']}°</div>",
        _table(p["targets"]) if p["targets"] else "<p><i>None tonight.</i></p>",
    ]
    if p.get("poorly_placed"):
        parts += [
            f"<h2 {h2}>Bright but poorly placed ({len(p['poorly_placed'])})</h2>",
            f"<div {note}>V ≤ {low}, but under {f['min_hours']} h above {f['min_alt_deg']}°</div>",
            _table(p["poorly_placed"], muted=True),
        ]
    if p["watch"]:
        parts += [
            f"<h2 {h2}>Watch list ({len(p['watch'])})</h2>",
            f"<div {note}>Visible tonight, V {f['mag_max']}–{low} or brightness unknown</div>",
            _table(p["watch"] if page else p["watch"][:5], muted=True),
        ]
    if chart_src:
        parts += [
            f"<h2 {h2}>Sky tracks tonight</h2>",
            f'<img src="{chart_src}" alt="Polar chart of tonight\'s target tracks" '
            'width="560" style="display:block;width:100%;max-width:560px;height:auto;'
            'border-radius:8px">',
        ]
    atels = [i for i in p.get("atel_recent", []) if i.get("of_interest")]
    if atels:
        parts.append(f"<h2 {h2}>Recent ATels</h2>")
        parts += [
            f'<div style="font-size:13px;margin:0 0 4px"><a href="{e(i["url"])}">'
            f"{e(i['title'])}</a></div>"
            for i in (atels if page else atels[:5])
        ]
    status = " · ".join(
        f"{e(s['source'])} {'✓' if s['ok'] else '✗ failed'}" for s in p["source_status"]
    )
    parts.append(
        f'<div style="font-size:12px;color:#5f6368;border-top:1px solid #eceff1;'
        f'margin-top:22px;padding-top:8px">{status} · '
        + (
            f'generated {p["generated_utc"]} UTC · <a href="candidates.json">candidates.json</a>'
            if page
            else f'<a href="{PAGE_URL}">full digest page</a>'
        )
        + "</div></div>"
    )
    return "".join(parts)


CHART_CID = "sky-chart"


def message(p: dict, to: str, chart: Path | None = None) -> dict:
    """The Resend request body; the sky chart rides along as an inline (cid:) image."""
    has_chart = chart is not None and chart.exists()
    msg = {
        "from": SENDER,
        "to": [to],
        "subject": subject(p),
        "text": text_body(p),
        "html": html_body(p, CHART_CID if has_chart else None),
    }
    if has_chart:
        msg["attachments"] = [
            {
                "content": base64.b64encode(chart.read_bytes()).decode(),
                "filename": "sky.png",
                "content_id": CHART_CID,
                "content_type": "image/png",
            }
        ]
    return msg


def send(p: dict, api_key: str, to: str, chart: Path | None = None) -> str:
    resp = requests.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=message(p, to, chart),
        timeout=30,
    )
    if resp.status_code >= 300:
        # Resend's error text never contains the key; it is safe to print.
        raise RuntimeError(f"Resend {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("id", "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default="docs/candidates.json")
    ap.add_argument("--dry-run", action="store_true", help="print the email instead of sending")
    ap.add_argument("--always", action="store_true", help="send even with no targets (tests)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    payload = json.loads(Path(args.json).read_text())
    if not payload["targets"] and not args.always:
        # Matt wants mail only on nights with at least one target that passes every filter.
        log.info("No targets tonight: no email sent")
        return 0
    if args.dry_run:
        print(subject(payload) + "\n\n" + text_body(payload))
        return 0
    key, to = os.environ.get("RESEND_API_KEY"), os.environ.get("EMAIL_TO")
    if not key or not to:
        log.error("RESEND_API_KEY and EMAIL_TO secrets are both required")
        return 1
    chart = Path(args.json).parent / payload["sky_chart"] if payload.get("sky_chart") else None
    log.info("Sent digest, Resend id %s", send(payload, key, to, chart))
    return 0


if __name__ == "__main__":
    sys.exit(main())
