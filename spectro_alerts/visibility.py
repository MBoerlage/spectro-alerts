"""Tonight's visibility from the observing site: darkness, altitude window and the Moon."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.time import Time
from astropy.utils import iers

# Arcminute accuracy is plenty here; never fail a run over IERS table downloads.
iers.conf.auto_download = False
iers.conf.iers_degraded_accuracy = "warn"

STEP_MIN = 5


@dataclass
class Night:
    tz: ZoneInfo
    times: Time
    dark: np.ndarray
    frame: AltAz
    location: EarthLocation
    sun_alt: np.ndarray

    @property
    def sunset(self) -> datetime | None:
        """First sample with the Sun's upper limb below the horizon (-0.833 deg)."""
        idx = np.flatnonzero(self.sun_alt < -0.833)
        return self.times[idx[0]].to_datetime(timezone=self.tz) if idx.size else None

    @property
    def sunrise(self) -> datetime | None:
        """First sample after sunset with the Sun's upper limb back above the horizon."""
        down = np.flatnonzero(self.sun_alt < -0.833)
        if not down.size:
            return None
        up = np.flatnonzero(self.sun_alt[down[0] :] >= -0.833)
        return self.times[down[0] + up[0]].to_datetime(timezone=self.tz) if up.size else None

    @property
    def dark_start(self) -> datetime | None:
        idx = np.flatnonzero(self.dark)
        return self.times[idx[0]].to_datetime(timezone=self.tz) if idx.size else None

    @property
    def dark_end(self) -> datetime | None:
        idx = np.flatnonzero(self.dark)
        return self.times[idx[-1]].to_datetime(timezone=self.tz) if idx.size else None


def tonight(site: dict, sun_alt_max: float, local_date: datetime | None = None) -> Night:
    """Sample 16:00 local to 09:00 local next morning in 5-minute steps."""
    tz = ZoneInfo(site["timezone"])
    base = (local_date or datetime.now(tz)).astimezone(tz)
    start = base.replace(hour=16, minute=0, second=0, microsecond=0)
    n = int((17 * 60) / STEP_MIN) + 1
    stamps = [start + timedelta(minutes=STEP_MIN * i) for i in range(n)]
    times = Time(stamps)
    loc = EarthLocation(
        lat=site["lat"] * u.deg, lon=site["lon"] * u.deg, height=site.get("height_m", 0) * u.m
    )
    frame = AltAz(obstime=times, location=loc)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sun_alt = get_body("sun", times, loc).transform_to(frame).alt.deg
    return Night(
        tz=tz, times=times, dark=sun_alt < sun_alt_max, frame=frame, location=loc, sun_alt=sun_alt
    )


def _longest_run(mask: np.ndarray) -> tuple[int, int]:
    """Start and end index (inclusive) of the longest True run; (-1, -1) if none."""
    best = (-1, -1)
    start = None
    for i, v in enumerate(np.append(mask, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if best[0] < 0 or (i - 1 - start) > (best[1] - best[0]):
                best = (start, i - 1)
            start = None
    return best


def evaluate(night: Night, ras: list[float], decs: list[float], min_alt: float) -> list[dict]:
    """Per target: hours visible, window, max altitude, Moon separation and illumination."""
    if not ras:
        return []
    targets = SkyCoord(ra=np.array(ras) * u.deg, dec=np.array(decs) * u.deg)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        alt = targets[:, None].transform_to(night.frame[None, :]).alt.deg
        moon = get_body("moon", night.times, night.location)
        sun = get_body("sun", night.times, night.location)
    elong = moon.separation(sun).deg
    illum = (1 - np.cos(np.radians(elong))) / 2
    out = []
    for k in range(len(ras)):
        ok = night.dark & (alt[k] >= min_alt)
        i0, i1 = _longest_run(ok)
        hours = 0.0 if i0 < 0 else (i1 - i0) * STEP_MIN / 60.0
        res = {
            "hours": round(hours, 2),
            "start": None,
            "end": None,
            "max_alt": None,
            "max_alt_time": None,
            "moon_sep": None,
            "moon_illum": None,
        }
        if i0 >= 0:
            seg = alt[k][i0 : i1 + 1]
            j = i0 + int(np.argmax(seg))
            mid = (i0 + i1) // 2
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                sep = float(targets[k].separation(moon[mid]).deg)
            res.update(
                start=night.times[i0].to_datetime(timezone=night.tz).strftime("%H:%M"),
                end=night.times[i1].to_datetime(timezone=night.tz).strftime("%H:%M"),
                max_alt=round(float(alt[k][j]), 1),
                max_alt_time=night.times[j].to_datetime(timezone=night.tz).strftime("%H:%M"),
                moon_sep=round(sep, 1),
                moon_illum=round(float(illum[mid]), 2),
            )
        out.append(res)
    return out
