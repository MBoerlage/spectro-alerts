"""Cross-match candidates from all sources into one record per sky position."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord

from .model import Candidate

# Earlier entries win as the object's display name when several sources report it.
SOURCE_PRIORITY = ["CBAT TOCP", "TNS", "ATel"]


@dataclass
class TargetObject:
    """All reports of one object, merged."""

    name: str
    ra: float
    dec: float
    reports: list[Candidate] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        out: list[str] = []
        for r in self.reports:
            for n in [r.name, *r.extra.get("names", [])]:
                if n and n not in out and r.source != "ATel":
                    out.append(n)
            if r.source == "ATel":
                for n in r.extra.get("names", []):
                    if n not in out:
                        out.append(n)
        return out

    @property
    def sources(self) -> list[str]:
        return sorted({r.source for r in self.reports}, key=_prio)

    @property
    def best_mag(self) -> Candidate | None:
        """Brightness to judge by: the most recent report that has a magnitude."""
        with_mag = [r for r in self.reports if r.mag is not None]
        if not with_mag:
            return None
        far_past = datetime.min.replace(tzinfo=None)
        return max(
            with_mag, key=lambda r: r.disc_date.replace(tzinfo=None) if r.disc_date else far_past
        )

    @property
    def first_report(self) -> Candidate:
        dated = [r for r in self.reports if r.disc_date]
        return min(dated, key=lambda r: r.disc_date) if dated else self.reports[0]

    @property
    def obj_type(self) -> str:
        for r in sorted(self.reports, key=lambda r: _prio(r.source)):
            if r.obj_type and r.obj_type not in ("unclassified", "ATel report", "transient"):
                return r.obj_type
        return self.reports[0].obj_type

    def flags(self) -> dict[str, Any]:
        return {
            "spectroscopically_confirmed": any(
                r.extra.get("spectroscopically_confirmed") for r in self.reports
            ),
            "has_atel": any(r.source == "ATel" for r in self.reports),
        }


def _prio(source: str) -> int:
    return SOURCE_PRIORITY.index(source) if source in SOURCE_PRIORITY else len(SOURCE_PRIORITY)


def cross_match(cands: list[Candidate], radius_arcsec: float) -> list[TargetObject]:
    """Group candidates within radius (friends-of-friends) into TargetObjects."""
    if not cands:
        return []
    coords = SkyCoord(ra=[c.ra for c in cands] * u.deg, dec=[c.dec for c in cands] * u.deg)
    parent = list(range(len(cands)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    i1, i2, _, _ = coords.search_around_sky(coords, radius_arcsec * u.arcsec)
    for a, b in zip(i1, i2, strict=True):
        ra_, rb_ = find(int(a)), find(int(b))
        if ra_ != rb_:
            parent[rb_] = ra_

    groups: dict[int, list[Candidate]] = {}
    for i, c in enumerate(cands):
        groups.setdefault(find(i), []).append(c)

    objects = []
    for members in groups.values():
        members.sort(key=lambda c: _prio(c.source))
        lead = members[0]
        ras = np.array([m.ra for m in members if m.source != "ATel"] or [lead.ra])
        decs = np.array([m.dec for m in members if m.source != "ATel"] or [lead.dec])
        objects.append(
            TargetObject(
                name=lead.name, ra=float(np.mean(ras)), dec=float(np.mean(decs)), reports=members
            )
        )
    return objects


def attach_atel_by_name(objects: list[TargetObject], atel_items: list[dict]) -> None:
    """Link ATel headlines that mention an object's name but gave no coordinates."""
    for obj in objects:
        keys = {n.replace(" ", "").lower() for n in obj.names}
        for item in atel_items:
            if any(n.replace(" ", "").lower() in keys for n in item["names"]):
                links = obj.reports[0].extra.setdefault("atel_links", [])
                if item["url"] not in links:
                    links.append(item["url"])
