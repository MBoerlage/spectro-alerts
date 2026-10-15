"""Persistent object history (committed to the repo): first seen, sources, magnitudes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import astropy.units as u
from astropy.coordinates import SkyCoord


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"objects": {}}


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def match_known(state: dict, ra: float, dec: float, radius_arcsec: float) -> str | None:
    """Return the state key of a known object at this position, if any."""
    objs = state["objects"]
    if not objs:
        return None
    keys = list(objs)
    known = SkyCoord(
        ra=[objs[k]["ra"] for k in keys] * u.deg, dec=[objs[k]["dec"] for k in keys] * u.deg
    )
    sep = known.separation(SkyCoord(ra=ra * u.deg, dec=dec * u.deg)).arcsec
    i = int(sep.argmin())
    return keys[i] if sep[i] <= radius_arcsec else None


def update(state: dict, key: str | None, obj, run_time: datetime) -> tuple[str, bool]:
    """Record this run's view of an object. Returns (key, is_new)."""
    stamp = run_time.isoformat(timespec="minutes")
    is_new = key is None
    if is_new:
        key = obj.name
        state["objects"][key] = {
            "ra": obj.ra,
            "dec": obj.dec,
            "first_seen": stamp,
            "names": [],
            "sources": [],
            "mags": [],
        }
    rec = state["objects"][key]
    rec["last_seen"] = stamp
    rec["names"] = sorted(set(rec["names"]) | set(obj.names))
    rec["sources"] = sorted(set(rec["sources"]) | set(obj.sources))
    best = obj.best_mag
    if best is not None:
        point = [
            best.disc_date.isoformat(timespec="minutes") if best.disc_date else stamp,
            best.mag,
            best.source,
        ]
        if point not in rec["mags"]:
            rec["mags"].append(point)
    return key, is_new


def prune(state: dict, run_time: datetime, keep_days: int) -> None:
    cutoff = (run_time - timedelta(days=keep_days)).isoformat(timespec="minutes")
    state["objects"] = {
        k: v for k, v in state["objects"].items() if v.get("last_seen", "") >= cutoff
    }
