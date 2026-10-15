"""David Bishop's "Latest Supernovae" (Rochester Astronomy), active-objects list.

Stands in for TNS, which blocks GitHub's servers: it mirrors TNS supernovae and
extragalactic novae and adds the latest reported magnitude, which TNS's export lacks.
The page is published as a plain table meant for automated parsing (snactive.html).
Galactic objects are not listed there; Mukai's nova list covers those.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape

from .. import http
from ..coords import parse_sexagesimal
from ..model import Candidate, SourceResult

log = logging.getLogger(__name__)

SOURCE = "Rochester"
MAIN_PAGE = "https://www.rochesterastronomy.org/supernova.html"
COLUMNS = [
    "name",
    "host",
    "ra",
    "dec",
    "offset",
    "latest_mag",
    "last_observed",
    "type",
    "z",
    "max_mag",
    "max_date",
    "first_observed",
    "discoverers",
    "aka",
]
_ROW = re.compile(r"(?is)<tr>(.*?)</tr>")
_CELL = re.compile(r"(?is)<td[^>]*>(.*?)</td>")


def _date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s.strip()[:10], "%Y/%m/%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _display_name(raw: str) -> str:
    raw = raw.strip()
    if raw.upper().startswith("AT"):
        return "AT " + raw[2:].strip()
    return "SN " + raw if raw[:2].isdigit() else raw


def parse(html: str) -> list[dict]:
    """Rows of the active-objects table as dicts. Raises if the table is not there."""
    start = html.find("<th>SN</th>")
    if start < 0:
        raise ValueError("Rochester active list: table header not found (page changed?)")
    rows = []
    for m in _ROW.finditer(html, start):
        cells = [unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in _CELL.findall(m.group(1))]
        if len(cells) < len(COLUMNS):
            continue
        rows.append(dict(zip(COLUMNS, cells[: len(COLUMNS)], strict=True)))
    return rows


def rows_to_candidates(
    rows: list[dict], mag_ceiling: float, now: datetime, max_age_days: int
) -> list[Candidate]:
    out, seen = [], set()
    for r in rows:
        stale = r["latest_mag"].endswith("*")  # Bishop marks observations over a month old
        try:
            mag = float(r["latest_mag"].rstrip("*:"))
        except ValueError:
            continue
        last = _date(r["last_observed"])
        if mag > mag_ceiling or stale or (last and now - last > timedelta(days=max_age_days)):
            continue
        name = _display_name(r["name"])
        if name in seen:
            continue
        try:
            ra, dec = parse_sexagesimal(r["ra"], r["dec"])
        except ValueError as exc:
            log.warning("Rochester: bad coordinates for %s: %s", name, exc)
            continue
        seen.add(name)
        kind = r["type"] if r["type"] not in ("", "unk") else "unclassified"
        obj_type = (
            "extragalactic nova" if kind == "EGN" else f"SN {kind}" if name[:2] == "SN" else kind
        )
        out.append(
            Candidate(
                name=name,
                ra=ra,
                dec=dec,
                source=SOURCE,
                url=f"{MAIN_PAGE}#{r['name'].replace('AT', '').strip()}",
                mag=mag,
                band="",
                mag_kind="latest",
                disc_date=last or _date(r["first_observed"]),
                obj_type=obj_type,
                extra={
                    "names": [a.strip() for a in r["aka"].split(",") if a.strip()][:4],
                    "host": r["host"],
                    "first_observed": r["first_observed"],
                    "last_observed": r["last_observed"],
                    "max_mag": r["max_mag"],
                    "redshift": r["z"],
                },
            )
        )
    return out


def fetch(cfg: dict, now: datetime, mag_ceiling: float) -> SourceResult:
    try:
        rows = parse(http.get(cfg["url"], timeout=60).text)
    except Exception as exc:  # noqa: BLE001
        log.error("Rochester fetch failed: %s", exc)
        return SourceResult(source=SOURCE, ok=False, error=str(exc))
    cands = rows_to_candidates(rows, mag_ceiling, now, cfg.get("max_age_days", 30))
    return SourceResult(source=SOURCE, candidates=cands, fetched=len(rows))
