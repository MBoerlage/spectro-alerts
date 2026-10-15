"""CBAT Transient Object Confirmation Page (TOCP).

The index is a fixed-width <pre> block listing every unconfirmed object since 2011, oldest
first. The RSS feed (tocp.xml) stopped updating in Aug 2026, so we parse the HTML.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from .. import http
from ..coords import dms_to_deg, from_designation, hms_to_deg
from ..model import Candidate, SourceResult

log = logging.getLogger(__name__)

SOURCE = "CBAT TOCP"
FOLLOWUP_BASE = "http://cbat.eps.harvard.edu/unconf/followups/"

_NUM = r"\d{1,2}(?:\.\d*)?"
LINE_RE = re.compile(
    r"^(?P<prefix>[A-Z]{3})\s+(?P<desig>J\d{8}[+-]\d{7})\s+"
    rf"(?P<y>\d{{4}})\s+(?P<mo>\d{{1,2}})\s+(?P<d>{_NUM})\s*\*?\s+"
    rf"(?P<rah>\d{{1,2}})\s+(?P<ram>\d{{1,2}})\s+(?P<ras>{_NUM})\s+"
    rf"(?P<sign>[+-])(?P<decd>\d{{1,2}})\s+(?P<decm>\d{{1,2}})\s+(?P<decs>{_NUM})"
    rf"(?:\s+(?P<mag>{_NUM}))?(?:\s+(?P<band>[A-Za-z]{{1,2}})\b)?(?P<rest>.*)$"
)

BAND_NAMES = {
    "U": "unfiltered",
    "C": "clear",
    "V": "V",
    "R": "R",
    "B": "B",
    "I": "I",
    "G": "G",
    "H": "H-alpha",
    "P": "photographic",
    "K": "K",
    "Z": "z",
}
PREFIX_TYPES = {"PNV": "nova candidate", "TCP": "transient", "PSN": "supernova candidate"}
CONFIRM_WORDS = ("spectrum", "spectra", "spectroscop", "classical nova", "confirmed", "classif")


def _fraction_day_to_datetime(y: int, mo: int, d: float) -> datetime:
    day = int(d)
    return datetime(y, mo, day, tzinfo=timezone.utc) + timedelta(days=d - day)


_FALLBACK_RE = re.compile(
    rf"^(?P<prefix>[A-Z]{{3}})\s+(?P<desig>J\d{{8}}[+-]\d{{7}})\s+"
    rf"(?P<y>\d{{4}})\s+(?P<mo>\d{{1,2}})\s+(?P<d>{_NUM})"
)


def _fallback_row(line: str) -> dict | None:
    """Recover a row with mangled RA/Dec columns: position from the designation."""
    m = _FALLBACK_RE.match(line)
    pos = from_designation(line) if m else None
    if not m or not pos:
        return None
    try:
        disc = _fraction_day_to_datetime(int(m["y"]), int(m["mo"]), float(m["d"]))
    except ValueError:
        return None
    log.info("CBAT: used designation coordinates for %s", m["desig"])
    return {
        "prefix": m["prefix"],
        "desig": m["desig"],
        "disc_date": disc,
        "ra": pos[0],
        "dec": pos[1],
        "mag": None,
        "band": "",
        "rest": line[m.end() :].strip(),
    }


def parse_index(html: str) -> list[dict]:
    """Parse the TOCP index into row dicts. Bad lines are logged and skipped."""
    soup = BeautifulSoup(html, "html.parser")
    pres = soup.find_all("pre")
    text = "\n".join(p.get_text() for p in pres) if pres else soup.get_text()
    rows = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not re.match(r"^[A-Z]{3}\s+J\d", line):
            continue  # header, ruler, blank
        m = LINE_RE.match(line)
        if not m:
            row = _fallback_row(line)
            if row:
                rows.append(row)
            else:
                log.warning("CBAT: could not parse line: %s", line)
            continue
        g = m.groupdict()
        try:
            disc = _fraction_day_to_datetime(int(g["y"]), int(g["mo"]), float(g["d"]))
            ra = hms_to_deg(int(g["rah"]), int(g["ram"]), float(g["ras"]))
            dec = dms_to_deg(g["sign"], int(g["decd"]), int(g["decm"]), float(g["decs"]))
        except ValueError as exc:
            log.warning("CBAT: bad values in line (%s): %s", exc, line)
            continue
        rest = (g["rest"] or "").strip()
        rows.append(
            {
                "prefix": g["prefix"],
                "desig": g["desig"],
                "disc_date": disc,
                "ra": ra,
                "dec": dec,
                "mag": float(g["mag"]) if g["mag"] else None,
                "band": (g["band"] or "").upper(),
                "rest": rest,
            }
        )
    return rows


def _followup_summary(desig: str) -> dict:
    """Read an object's follow-up page; keep the tail and flag spectroscopic mentions."""
    url = f"{FOLLOWUP_BASE}{desig}.html"
    text = BeautifulSoup(http.get(url, timeout=15).text, "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text).strip()
    low = text.lower()
    return {
        "followup_summary": text[-800:],
        "spectroscopically_confirmed": any(w in low for w in CONFIRM_WORDS),
    }


def fetch(cfg: dict, now: datetime, mag_ceiling: float) -> SourceResult:
    res = SourceResult(source=SOURCE)
    try:
        html = http.get(cfg["url"]).text
        rows = parse_index(html)
    except Exception as exc:  # noqa: BLE001 - one source failing must not stop the run
        log.error("CBAT fetch failed: %s", exc)
        return SourceResult(source=SOURCE, ok=False, error=str(exc))

    res.fetched = len(rows)
    max_age = timedelta(days=cfg.get("max_age_days", 30))
    prefixes = set(cfg.get("prefixes", ["PNV", "TCP"]))
    followups_left = cfg.get("max_followups", 10) if cfg.get("fetch_followups") else 0

    for r in rows:
        if r["prefix"] not in prefixes:
            continue
        if now - r["disc_date"] > max_age:
            continue
        name = f"{r['prefix']} {r['desig']}"
        url = f"{FOLLOWUP_BASE}{r['desig']}.html"
        band = BAND_NAMES.get(r["band"], r["band"] or "V")
        cand = Candidate(
            name=name,
            ra=r["ra"],
            dec=r["dec"],
            source=SOURCE,
            url=url,
            mag=r["mag"],
            band=band,
            mag_kind="discovery",
            disc_date=r["disc_date"],
            obj_type=PREFIX_TYPES.get(r["prefix"], "transient"),
            extra={"band_letter": r["band"], "columns": r["rest"]},
        )
        bright_enough = r["mag"] is not None and r["mag"] <= mag_ceiling
        if followups_left > 0 and bright_enough:
            followups_left -= 1
            try:
                cand.extra.update(_followup_summary(r["desig"]))
            except Exception as exc:  # noqa: BLE001
                log.warning("CBAT follow-up failed for %s: %s", name, exc)
        res.candidates.append(cand)
    return res
