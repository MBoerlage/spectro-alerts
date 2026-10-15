"""ASAS-SN transient list (Ohio State): the survey's own discoveries and recoveries.

ASAS-SN finds many of the bright galactic novae that never reach CBAT and are reported only to
TNS (which blocks GitHub). The public page is one large HTML table, newest first, refreshed
every few days. Columns: ASAS-SN ID, other IDs, ATel, RA, Dec, discovery (UT, fractional day),
V/g magnitude, three image/catalog links, spectroscopic class, comments.

The magnitude column sometimes holds values that are not magnitudes (negative numbers on
recoveries of known objects), so only plausible magnitudes are used. Flares on M dwarfs fade
within hours and are skipped.
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

SOURCE = "ASAS-SN"
PAGE = "https://www.astronomy.ohio-state.edu/asassn/transients.html"
_ROW = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
_CELL = re.compile(r"(?is)<td[^>]*>(.*?)</td>")
_HREF = re.compile(r'(?i)href="([^"]+)"')
MAG_RANGE = (3.0, 22.0)  # anything outside is not a magnitude


def _clean(cell: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", cell))).strip()


def _disc(s: str) -> datetime | None:
    """'2026-10-9.85' -> datetime (UTC)."""
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(\.\d+)?$", s.strip())
    if not m:
        return None
    try:  # the table has typos such as day 31 in a 30-day month
        base = datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    except ValueError:
        return None
    return base + timedelta(days=float(m[4] or 0))


def _names(asassn_id: str, other: str) -> tuple[str, list[str]]:
    others = [
        n.strip(" ()=\"'")
        for n in re.split(r"[()=,]", other)
        if n.strip(" ()=\"'-") and not n.strip().startswith("---")
    ]
    ids = ([asassn_id] if asassn_id and not asassn_id.startswith("-") else []) + others
    # Prefer a variable-star or TNS name for display, keep the ASAS-SN ID as an alias.
    display = next((n for n in others if re.match(r"^V\d+ [A-Z][a-z]{2}$", n)), None)
    display = display or (ids[0] if ids else "")
    return display, [n for n in ids if n != display]


def _kind(comment: str) -> str:
    c = comment.lower()
    if "nova" in c and "supernova" not in c and "sn candidate" not in c:
        return "nova" if "known" in c else "nova candidate"
    if "cv candidate" in c:
        return "CV outburst"
    if "sn candidate" in c or "supernova" in c:
        m = re.search(r"type ([^,]+)", comment, re.I)
        return f"SN {m.group(1).strip()}" if m else "SN candidate"
    if "tde" in c:
        return "TDE candidate"
    return comment.split(",")[0][:40] or "transient"


def parse(html: str) -> list[dict]:
    if "ASAS-SN" not in html or "Discovery" not in html:
        raise ValueError("ASAS-SN transient page: table header not found (page changed?)")
    rows = []
    for m in _ROW.finditer(html):
        raw = _CELL.findall(m.group(1))
        if len(raw) < 12:
            continue
        cells = [_clean(c) for c in raw]
        rows.append(
            {
                "id": cells[0],
                "other": cells[1],
                "atel_url": next(iter(_HREF.findall(raw[2])), ""),
                "ra": cells[3],
                "dec": cells[4],
                "discovery": cells[5],
                "mag": cells[6],
                "spec_class": cells[10].strip("-"),
                "comment": cells[11],
            }
        )
    return rows


def rows_to_candidates(
    rows: list[dict], mag_ceiling: float, now: datetime, lookback_days: int
) -> list[Candidate]:
    since = now - timedelta(days=lookback_days)
    out = []
    for r in rows:
        disc = _disc(r["discovery"])
        if disc is None or disc < since:
            continue
        if "flare" in r["comment"].lower():
            continue
        try:
            mag = float(r["mag"])
        except ValueError:
            continue
        if not (MAG_RANGE[0] <= mag <= mag_ceiling):
            continue
        # CV-candidate rows sometimes carry an amplitude (e.g. 3.6) in the magnitude column; only
        # a nova is believable that bright.
        if mag < 6.0 and "nova" not in r["comment"].lower():
            continue
        try:
            ra, dec = parse_sexagesimal(r["ra"], r["dec"])
        except ValueError as exc:
            log.warning("ASAS-SN: bad coordinates for %s: %s", r["id"], exc)
            continue
        # Recoveries of known objects carry the original discovery date in the comment.
        orig = re.search(r"discovered (\d{4})/(\d{2})/(\d{2})", r["comment"])
        first = _disc(f"{orig[1]}-{orig[2]}-{orig[3]}") if orig else None
        first = first or disc
        name, aliases = _names(r["id"], r["other"])
        if not name:
            continue
        out.append(
            Candidate(
                name=name,
                ra=ra,
                dec=dec,
                source=SOURCE,
                url=PAGE,
                mag=mag,
                band="V/g",
                mag_kind="ASAS-SN",
                disc_date=first,
                obj_type=r["spec_class"] or _kind(r["comment"]),
                extra={
                    "names": aliases,
                    "comment": r["comment"],
                    "asassn_date": disc.strftime("%Y-%m-%d %H:%M"),
                    "atel_url": r["atel_url"],
                    "spectroscopically_confirmed": bool(r["spec_class"]),
                },
            )
        )
    return out


def fetch(cfg: dict, now: datetime, mag_ceiling: float) -> SourceResult:
    try:
        rows = parse(http.get(cfg.get("url", PAGE), timeout=90).text)
    except Exception as exc:  # noqa: BLE001
        log.error("ASAS-SN fetch failed: %s", exc)
        return SourceResult(source=SOURCE, ok=False, error=str(exc))
    cands = rows_to_candidates(rows, mag_ceiling, now, cfg.get("lookback_days", 30))
    return SourceResult(source=SOURCE, candidates=cands, fetched=len(rows))
