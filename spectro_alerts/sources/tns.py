"""Transient Name Server via its public CSV search export (no key needed).

Phase 2 can switch to the authenticated API (bot key in a GitHub secret) for classification
reports; the public export already gives names, positions, types and discovery magnitudes.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from .. import http
from ..coords import parse_sexagesimal
from ..model import Candidate, SourceResult

log = logging.getLogger(__name__)

SOURCE = "TNS"
SEARCH_URL = "https://www.wis-tns.org/search"


def parse_csv(text: str) -> list[dict]:
    if not text.lstrip().startswith('"ID"'):
        raise ValueError("TNS did not return CSV (blocked or page changed)")
    return list(csv.DictReader(io.StringIO(text)))


def _to_float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _to_dt(s: str) -> datetime | None:
    try:
        return datetime.strptime(s.strip()[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (AttributeError, ValueError):
        return None


def rows_to_candidates(
    rows: list[dict], disc_mag_max: float, since: datetime | None = None
) -> list[Candidate]:
    out = []
    for row in rows:
        mag = _to_float(row.get("Discovery Mag/Flux", ""))
        if mag is None or mag > disc_mag_max:
            continue
        disc = _to_dt(row.get("Discovery Date (UT)", ""))
        if since and disc and disc < since:
            continue  # TNS sometimes returns older objects; keep only the lookback window
        try:
            ra, dec = parse_sexagesimal(row["RA"], row["DEC"])
        except (KeyError, ValueError) as exc:
            log.warning("TNS: bad coordinates for %s: %s", row.get("Name"), exc)
            continue
        name = row["Name"].strip()
        objname = name.split(" ", 1)[-1]
        out.append(
            Candidate(
                name=name,
                ra=ra,
                dec=dec,
                source=SOURCE,
                url=f"https://www.wis-tns.org/object/{objname}",
                mag=mag,
                band=row.get("Discovery Filter", ""),
                mag_kind="discovery",
                disc_date=disc,
                obj_type=row.get("Obj. Type", "").strip() or "unclassified",
                extra={
                    "host": row.get("Host Name", ""),
                    "redshift": row.get("Redshift", ""),
                    "reporting_group": row.get("Reporting Group/s", ""),
                    "internal_name": row.get("Disc. Internal Name", ""),
                },
            )
        )
    return out


def fetch(cfg: dict, now: datetime) -> SourceResult:
    since = now - timedelta(days=cfg.get("lookback_days", 30))
    # Explicit date range: the discovered_period_* parameters were ignored when combined
    # with the magnitude cut (tested 2026-10-15).
    params = {
        "date_start[date]": since.strftime("%Y-%m-%d"),
        "date_end[date]": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
        "discovery_mag_max": cfg.get("disc_mag_max", 15.0),
        "num_page": 500,
        "format": "csv",
    }
    try:
        rows = parse_csv(http.get(SEARCH_URL, params=params).text)
    except Exception as exc:  # noqa: BLE001
        log.error("TNS fetch failed: %s", exc)
        return SourceResult(source=SOURCE, ok=False, error=str(exc))
    cands = rows_to_candidates(rows, cfg.get("disc_mag_max", 15.0), since)
    return SourceResult(source=SOURCE, candidates=cands, fetched=len(rows))
