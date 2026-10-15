"""Polar sky chart of tonight's tracks: azimuth around (N up, E right), altitude inward.

One coloured line per object over the observing window, with a dot on every full hour and
the start time labelled. Targets are solid; poorly placed objects are dashed.
"""

from __future__ import annotations

from pathlib import Path

import astropy.units as u
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.coordinates import SkyCoord  # noqa: E402

from .visibility import Night  # noqa: E402

BG = "#37474a"
GRID = "#9aa7a9"
TEXT = "#e8eaed"
# Distinct colours that stay readable on the dark background.
COLORS = [
    "#ffd54f",
    "#4fc3f7",
    "#ff8a65",
    "#aed581",
    "#ce93d8",
    "#f06292",
    "#80cbc4",
    "#fff176",
    "#90caf9",
    "#bcaaa4",
]


def draw(night: Night, objects: list[dict], min_alt: float, path: Path, title: str = "") -> bool:
    """objects: dicts with name, ra, dec and an optional 'dashed' flag. Returns True if drawn."""
    if not objects or not night.dark.any():
        return False
    idx = np.flatnonzero(night.dark)
    times = night.times[idx]
    frame = night.frame[idx]
    local = [t.to_datetime(timezone=night.tz) for t in times]

    fig = plt.figure(figsize=(5.0, 6.0), dpi=150, facecolor=BG)
    ax = fig.add_axes([0.08, 0.3, 0.84, 0.62], projection="polar", facecolor=BG)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)  # clockwise: N, E, S, W as seen on a sky map from the ground
    ax.set_rlim(0, 90)
    ax.set_rticks(range(10, 91, 10))
    ax.set_yticklabels([])
    for r, lab in ((30, "60°"), (60, "30°"), (90 - min_alt, f"{min_alt:.0f}°")):
        ax.text(np.radians(22), r, lab, color=GRID, fontsize=8, ha="left", va="center")
    ax.set_thetagrids(range(0, 360, 45), ["N", "45", "E", "135", "S", "225", "W", "315"])
    ax.tick_params(colors=TEXT, labelsize=11, pad=1)
    ax.grid(color=GRID, alpha=0.35, linewidth=0.7)
    ax.spines["polar"].set_color(GRID)
    # Below the horizon limit: shaded ring.
    theta = np.linspace(0, 2 * np.pi, 361)
    ax.fill_between(theta, 90 - min_alt, 90, color="#000000", alpha=0.25, linewidth=0)

    handles = []
    for i, obj in enumerate(objects[: len(COLORS)]):
        c = COLORS[i]
        aa = SkyCoord(obj["ra"] * u.deg, obj["dec"] * u.deg).transform_to(frame)
        alt, az = aa.alt.deg, aa.az.rad
        up = alt > 0
        if not up.any():
            continue
        r = np.where(up, 90 - alt, np.nan)
        ls = "--" if obj.get("dashed") else "-"
        (line,) = ax.plot(az, r, ls, color=c, linewidth=2.6, label=obj["name"])
        handles.append(line)
        hours = [k for k, t in enumerate(local) if t.minute == 0 and up[k]]
        ax.plot(az[hours], r[hours], "o", color=c, markersize=3.5)
        first = int(np.flatnonzero(up)[0])
        ax.annotate(
            local[first].strftime("%H:%M"),
            (az[first], r[first]),
            xytext=(4, 4),
            textcoords="offset points",
            color=c,
            fontsize=9,
        )
    if not handles:
        plt.close(fig)
        return False
    if title:
        fig.text(0.5, 0.965, title, color=TEXT, ha="center", fontsize=13, weight="bold")
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.22),
        ncol=1 if len(handles) <= 4 else 2,
        frameon=False,
        labelcolor=TEXT,
        fontsize=11,
        handlelength=2.4,
    )
    fig.text(
        0.5,
        0.235,
        "Dots on the hour; dashed = poorly placed; shaded = below horizon limit",
        color=GRID,
        ha="center",
        fontsize=8,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return True
