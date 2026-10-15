"""Koji Mukai's list of recent galactic novae (NASA GSFC).

Only spectroscopically confirmed novae are listed, with official names (e.g. V488 Sge),
peak magnitude and links to ARAS spectra. It catches galactic novae that were reported only
to TNS and never reached CBAT, which matters while TNS blocks GitHub. It lags discovery by
days to weeks, so it complements CBAT rather than replacing it.
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

SOURCE = "Mukai novae"
_ROW = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
_CELL = re.compile(r"(?is)<td[^>]*>(.*?)</td>")
_HREF = re.compile(r'(?i)href="([^"]+)"')


def _text_parts(cell: str) -> list[str]:
    parts = re.split(r"(?i)<br\s*/?>|</br>", cell)
    return [t for t in (unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in parts) if t]


def _peak(s: str) -> tuple[float | None, str]:
    """'7.1' -> (7.1, 'V'); 'r=13.8' -> (13.8, 'r')."""
    m = re.match(r"^\s*(?:([A-Za-z]+)\s*=\s*)?(\d+(?:\.\d+)?)", s)
    if not m:
        return None, ""
    return float(m.group(2)), m.group(1) or "V"


def parse(html: str) -> list[dict]:
    if "Position" not in html or "Peak" not in html:
        raise ValueError("Mukai nova list: table header not found (page changed?)")
    rows = []
    for m in _ROW.finditer(html):
        cells = _CELL.findall(m.group(1))
        if len(cells) < 4:
            continue
        names = _text_parts(cells[0])
        pos = _text_parts(cells[1])
        if not names or len(pos) < 2:
            continue
        links = _HREF.findall(cells[0])
        notes = cells[5] if len(cells) > 5 else ""
        aras = [u for u in _HREF.findall(notes) if "aras" in u.lower()]
        rows.append(
            {
                "name": names[0],
                "aliases": names[1:],
                "ra": pos[0],
                "dec": pos[1],
                "discovery": unescape(re.sub(r"<[^>]+>", "", cells[2])).strip(),
                "peak": unescape(re.sub(r"<[^>]+>", "", cells[3])).strip(),
                "url": links[0] if links else "",
                "aras_url": aras[0] if aras else "",
            }
        )
    return rows


def rows_to_candidates(
    rows: list[dict], mag_ceiling: float, now: datetime, lookback_days: int
) -> list[Candidate]:
    out = []
    since = now - timedelta(days=lookback_days)
    for r in rows:
        try:
            disc = datetime.strptime(r["discovery"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if disc < since:
            continue
        peak, band = _peak(r["peak"])
        if peak is None or peak > mag_ceiling:
            continue
        try:
            ra, dec = parse_sexagesimal(r["ra"], r["dec"])
        except ValueError as exc:
            log.warning("Mukai: bad coordinates for %s: %s", r["name"], exc)
            continue
        out.append(
            Candidate(
                name=r["name"],
                ra=ra,
                dec=dec,
                source=SOURCE,
                url=r["url"],
                mag=peak,
                band=band,
                mag_kind="peak",
                disc_date=disc,
                obj_type="nova (confirmed)",
                extra={
                    "names": [a for a in r["aliases"] if not a.lower().startswith("nova in")],
                    "spectroscopically_confirmed": True,
                    "aras_url": r["aras_url"],
                },
            )
        )
    return out


def fetch(cfg: dict, now: datetime, mag_ceiling: float) -> SourceResult:
    try:
        rows = parse(http.get(cfg["url"], timeout=60).text)
    except Exception as exc:  # noqa: BLE001
        log.error("Mukai fetch failed: %s", exc)
        return SourceResult(source=SOURCE, ok=False, error=str(exc))
    cands = rows_to_candidates(rows, mag_ceiling, now, cfg.get("lookback_days", 30))
    return SourceResult(source=SOURCE, candidates=cands, fetched=len(rows))
