"""The Astronomer's Telegram RSS feed.

ATels rarely give a usable current magnitude, so they annotate other objects (matched by
position or name) and are listed as recent headlines for Claude to read.
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser

from .. import http
from ..coords import from_designation, parse_sexagesimal
from ..model import Candidate, SourceResult

log = logging.getLogger(__name__)

SOURCE = "ATel"

# RA = 12:34:56.7, Dec = -12:34:56 / R.A. 12h34m56.7s, Decl. +12d34m56s and similar
_SEX_RE = re.compile(
    r"R\.?\s*A\.?[^0-9+-]{0,20}?"
    r"(\d{1,2}[:h ]\s?\d{1,2}[:m ]\s?\d{1,2}(?:\.\d+)?)s?"
    r"[^0-9+-]{1,30}?(?:Dec\.?|Decl\.?|DEC)[^0-9+-]{0,20}?"
    r"([+-]?\s?\d{1,2}[:d° ]\s?\d{1,2}[:m' ]\s?\d{1,2}(?:\.\d+)?)",
    re.IGNORECASE,
)
_NAME_RE = re.compile(
    r"\b(?:AT|SN)\s?20\d\d[a-z]{1,4}\b|\b(?:PNV|TCP|PSN)\s?J\d{8}[+-]\d{7}\b|"
    r"\bASASSN-\d{2}[a-z]{1,3}\b|\bZTF\d{2}[a-z]{7}\b|\bGaia\d{2}[a-z]{1,3}\b"
)
INTEREST = (
    "nova",
    "outburst",
    "spectroscop",
    "classification",
    "symbiotic",
    "flare",
    "dwarf nova",
    "supernova",
    "be star",
    "brighten",
)


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key)
        if tm:
            return datetime.fromtimestamp(calendar.timegm(tm), tz=timezone.utc)
    return None


def extract_coords(text: str) -> tuple[float, float] | None:
    m = _SEX_RE.search(text)
    if m:
        try:
            return parse_sexagesimal(m.group(1), m.group(2).replace(" ", ""))
        except ValueError:
            pass
    return from_designation(text)


def parse_feed(xml: str, now: datetime, lookback_days: int) -> SourceResult:
    feed = feedparser.parse(xml)
    res = SourceResult(source=SOURCE, fetched=len(feed.entries))
    cutoff = now - timedelta(days=lookback_days)
    for e in feed.entries:
        when = _entry_time(e)
        if when and when < cutoff:
            continue
        title = re.sub(r"\s+", " ", e.get("title", "")).strip()
        summary = re.sub(r"<[^>]+>", " ", e.get("summary", "") or e.get("description", ""))
        summary = re.sub(r"\s+", " ", summary).strip()
        text = f"{title} {summary}"
        names = sorted(set(n.replace(" ", " ") for n in _NAME_RE.findall(text)))
        item = {
            "title": title,
            "url": e.get("link", ""),
            "published": when.isoformat() if when else None,
            "names": names,
            "of_interest": any(w in text.lower() for w in INTEREST),
            "summary": summary[:400],
        }
        res.items.append(item)
        pos = extract_coords(text)
        if pos:
            res.candidates.append(
                Candidate(
                    name=title[:80],
                    ra=pos[0],
                    dec=pos[1],
                    source=SOURCE,
                    url=item["url"],
                    disc_date=when,
                    obj_type="ATel report",
                    extra={"names": names, "title": title},
                )
            )
    return res


def fetch(cfg: dict, now: datetime) -> SourceResult:
    try:
        xml = http.get(cfg["url"]).text
    except Exception as exc:  # noqa: BLE001
        log.error("ATel fetch failed: %s", exc)
        return SourceResult(source=SOURCE, ok=False, error=str(exc))
    return parse_feed(xml, now, cfg.get("lookback_days", 7))
