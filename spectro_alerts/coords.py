"""Coordinate helpers: sexagesimal parsing and coordinates encoded in designations."""

from __future__ import annotations

import re

_DESIG = re.compile(r"J(\d{2})(\d{2})(\d{2})(\d{2})([+-])(\d{2})(\d{2})(\d{2})(\d)")


def hms_to_deg(h: float, m: float, s: float) -> float:
    return 15.0 * (abs(h) + m / 60.0 + s / 3600.0)


def dms_to_deg(sign: str, d: float, m: float, s: float) -> float:
    val = abs(d) + m / 60.0 + s / 3600.0
    return -val if sign == "-" else val


def parse_sexagesimal(ra: str, dec: str) -> tuple[float, float]:
    """Parse 'hh:mm:ss.s' / 'hh mm ss.s' style RA and '+dd:mm:ss' Dec into degrees."""
    rp = re.split(r"[:\s hms]+", ra.strip())
    rp = [p for p in rp if p]
    dec = dec.strip()
    sign = "-" if dec.startswith("-") else "+"
    dp = re.split(r"[:\s d'\"m s]+", dec.lstrip("+-"))
    dp = [p for p in dp if p]
    if len(rp) < 3 or len(dp) < 3:
        raise ValueError(f"bad sexagesimal: {ra!r} {dec!r}")
    return (
        hms_to_deg(float(rp[0]), float(rp[1]), float(rp[2])),
        dms_to_deg(sign, float(dp[0]), float(dp[1]), float(dp[2])),
    )


def from_designation(desig: str) -> tuple[float, float] | None:
    """Decode a CBAT-style 'Jhhmmssss+ddmmsss' designation into degrees."""
    m = _DESIG.search(desig)
    if not m:
        return None
    hh, mm, ss, sf, sign, dd, dm, ds, dsf = m.groups()
    ra = hms_to_deg(int(hh), int(mm), float(f"{ss}.{sf}"))
    dec = dms_to_deg(sign, int(dd), int(dm), float(f"{ds}.{dsf}"))
    return ra, dec
