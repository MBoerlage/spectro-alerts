"""Compose the evening digest from candidates.json and send it through Resend.

The recipient comes from the EMAIL_TO secret and the key from RESEND_API_KEY, so neither
appears in this public repository or its logs.
"""

from __future__ import annotations

import argparse
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
    kind = " (discovery)" if t.get("mag_kind") == "discovery" else ""
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
    return out


def subject(p: dict) -> str:
    w = p.get("weather", {})
    verdict = w.get("verdict", "UNKNOWN")
    n = len(p["targets"])
    what = f"{n} target{'s' if n != 1 else ''}" if n else "no targets"
    extra = f", {len(p.get('poorly_placed', []))} low" if p.get("poorly_placed") else ""
    return f"{verdict} tonight: {what}{extra} ({p['night']['date']})"


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


def html_body(p: dict) -> str:
    e = html.escape
    w = p.get("weather", {})
    n = p["night"]
    color = VERDICT_COLORS.get(w.get("verdict", "UNKNOWN"), "#666666")
    parts = [
        '<div style="font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;max-width:640px">',
        f'<p style="border-left:4px solid {color};padding:6px 10px;margin:0 0 8px">'
        f'<b style="color:{color}">{e(w.get("line", "Weather: unknown"))}</b></p>',
        f'<p style="margin:0 0 16px;color:#666;font-size:13px">Sunset {n["sunset"]} · observing '
        f"{n['dark_start']}–{n['dark_end']} · "
        f'<a href="{e(w.get("clear_outside_url", ""))}">Clear Outside</a></p>',
    ]
    for title, rows, empty in _sections(p):
        if not rows and not empty:
            continue
        parts.append(f'<h3 style="margin:18px 0 6px">{e(title)}</h3>')
        if not rows:
            parts.append(f"<p><i>{e(empty)}</i></p>")
        for t in rows:
            names = ", ".join(x for x in t["names"] if x != t["name"])
            links = " · ".join(f'<a href="{e(u)}">{e(s)}</a>' for s, u in _links(t))
            notes = "; ".join(_notes(t))
            parts.append(
                '<p style="margin:0 0 12px">'
                f"<b>{e(t['name'])}</b>"
                + (f' <span style="color:#666">({e(names)})</span>' if names else "")
                + f"<br>{e(t['obj_type'])}, <b>{e(_mag(t))}</b>, {t['ra_hms']} {t['dec_dms']}"
                + f"<br>Tonight: {e(_window(t))}"
                + (f"<br><i>{e(notes)}</i>" if notes else "")
                + (f"<br>{links}" if links else "")
                + "</p>"
            )
    atels = [i for i in p.get("atel_recent", []) if i.get("of_interest")]
    if atels:
        parts.append('<h3 style="margin:18px 0 6px">Recent ATels of interest</h3><ul>')
        parts += [f'<li><a href="{e(i["url"])}">{e(i["title"])}</a></li>' for i in atels[:5]]
        parts.append("</ul>")
    failed = [s for s in p["source_status"] if not s["ok"]]
    foot = f'<a href="{PAGE_URL}">Full digest page</a>'
    if failed:
        foot = "Failed today: " + ", ".join(e(s["source"]) for s in failed) + " · " + foot
    parts.append(f'<p style="color:#666;font-size:13px;margin-top:20px">{foot}</p></div>')
    return "".join(parts)


def send(p: dict, api_key: str, to: str) -> str:
    resp = requests.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": SENDER,
            "to": [to],
            "subject": subject(p),
            "text": text_body(p),
            "html": html_body(p),
        },
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
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    payload = json.loads(Path(args.json).read_text())
    if args.dry_run:
        print(subject(payload) + "\n\n" + text_body(payload))
        return 0
    key, to = os.environ.get("RESEND_API_KEY"), os.environ.get("EMAIL_TO")
    if not key or not to:
        log.error("RESEND_API_KEY and EMAIL_TO secrets are both required")
        return 1
    log.info("Sent digest, Resend id %s", send(payload, key, to))
    return 0


if __name__ == "__main__":
    sys.exit(main())
