"""Clear-sky check for the evening window (sunset to midnight local).

Open-Meteo (hourly cloud layers, rain chance, gusts) makes the GO / NO-GO call. 7Timer! ASTRO
(3-hourly) is a second opinion and adds seeing and transparency; if the two disagree the
verdict is MAYBE. Clear Outside is linked for a visual check.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import http

log = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SEVEN_TIMER_URL = "https://www.7timer.info/bin/astro.php"
OM_VARS = (
    "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
    "precipitation_probability,wind_speed_10m,wind_gusts_10m,dew_point_2m,temperature_2m"
)
# 7Timer cloudcover index -> upper bound of the cloud percentage band.
SEVEN_TIMER_CLOUD_MAX = {1: 6, 2: 19, 3: 31, 4: 44, 5: 56, 6: 69, 7: 81, 8: 94, 9: 100}
SEEING_ARCSEC = {
    1: "<0.5",
    2: "0.5-0.75",
    3: "0.75-1",
    4: "1-1.25",
    5: "1.25-1.5",
    6: "1.5-2",
    7: "2-2.5",
    8: ">2.5",
}


def fetch(site: dict, cfg: dict) -> dict:
    """Fetch raw forecasts. Never raises; errors are reported per source."""
    raw: dict = {"open_meteo": None, "seven_timer": None, "errors": {}}
    try:
        raw["open_meteo"] = http.get(
            OPEN_METEO_URL,
            params={
                "latitude": site["lat"],
                "longitude": site["lon"],
                "hourly": OM_VARS,
                "wind_speed_unit": "mph",
                "temperature_unit": "fahrenheit",
                "timezone": site["timezone"],
                "forecast_days": 2,
            },
        ).json()
    except Exception as exc:  # noqa: BLE001
        log.error("Open-Meteo failed: %s", exc)
        raw["errors"]["Open-Meteo"] = str(exc)
    if cfg.get("seven_timer", True):
        try:
            raw["seven_timer"] = http.get(
                SEVEN_TIMER_URL,
                params={
                    "lon": site["lon"],
                    "lat": site["lat"],
                    "ac": 0,
                    "unit": "metric",
                    "output": "json",
                    "tzshift": 0,
                },
            ).json()
        except Exception as exc:  # noqa: BLE001
            log.error("7Timer failed: %s", exc)
            raw["errors"]["7Timer"] = str(exc)
    return raw


def effective_cloud(low: float, mid: float, high: float, high_weight: float) -> float:
    """Combine layers assuming random overlap; thin high cloud counts at high_weight."""
    clear = (1 - low / 100) * (1 - mid / 100) * (1 - high_weight * high / 100)
    return round(100 * (1 - clear), 1)


def _window(sunset: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = sunset.replace(minute=0, second=0, microsecond=0)
    end = (
        (sunset + timedelta(days=1))
        .astimezone(tz)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    if sunset.hour < 12:  # never happens for an evening sunset, but keep the window sane
        end = start + timedelta(hours=6)
    return start, end


def assess_open_meteo(
    data: dict, start: datetime, end: datetime, tz: ZoneInfo, cfg: dict
) -> list[dict]:
    h = data["hourly"]
    hours = []
    for i, t in enumerate(h["time"]):
        when = datetime.fromisoformat(t).replace(tzinfo=tz)
        if not (start <= when < end):
            continue

        def val(key: str, idx: int = i) -> float:
            v = h.get(key, [None] * (idx + 1))[idx]
            return 0.0 if v is None else float(v)

        eff = effective_cloud(
            val("cloud_cover_low"),
            val("cloud_cover_mid"),
            val("cloud_cover_high"),
            cfg["high_cloud_weight"],
        )
        rain = val("precipitation_probability")
        gust = val("wind_gusts_10m")
        reasons = []
        if eff > cfg["max_cloud_pct"]:
            reasons.append(f"cloud {eff:.0f}%")
        if rain > cfg["max_rain_pct"]:
            reasons.append(f"rain {rain:.0f}%")
        if gust > cfg["max_gust_mph"]:
            reasons.append(f"gusts {gust:.0f} mph")
        hours.append(
            {
                "hour": when.strftime("%H:%M"),
                "cloud_eff": eff,
                "cloud_low": val("cloud_cover_low"),
                "cloud_mid": val("cloud_cover_mid"),
                "cloud_high": val("cloud_cover_high"),
                "rain_pct": rain,
                "wind_mph": val("wind_speed_10m"),
                "gust_mph": gust,
                "temp_f": val("temperature_2m"),
                "dew_point_f": val("dew_point_2m"),
                "clear": not reasons,
                "why_not": ", ".join(reasons),
            }
        )
    return hours


def assess_seven_timer(data: dict, start: datetime, end: datetime, cfg: dict) -> dict:
    init = datetime.strptime(data["init"], "%Y%m%d%H").replace(tzinfo=timezone.utc)
    pts = []
    for d in data.get("dataseries", []):
        when = init + timedelta(hours=d["timepoint"])
        # Each point covers roughly +-1.5 h; keep points centred within the window.
        if start - timedelta(minutes=90) <= when < end + timedelta(minutes=90):
            cloud = SEVEN_TIMER_CLOUD_MAX.get(d.get("cloudcover", 9), 100)
            pts.append(
                {
                    "time_utc": when.strftime("%Y-%m-%d %H:%M"),
                    "cloud_max_pct": cloud,
                    "seeing": d.get("seeing"),
                    "transparency": d.get("transparency"),
                    "prec_type": d.get("prec_type", "none"),
                    "clear": cloud <= cfg["max_cloud_pct"] and d.get("prec_type") == "none",
                }
            )
    if not pts:
        return {"points": [], "mostly_clear": None}
    seeing = [p["seeing"] for p in pts if p["seeing"]]
    transp = [p["transparency"] for p in pts if p["transparency"]]
    best_seeing = min(seeing) if seeing else None
    return {
        "points": pts,
        "mostly_clear": sum(p["clear"] for p in pts) * 2 >= len(pts),
        "seeing_best": best_seeing,
        "seeing_arcsec": SEEING_ARCSEC.get(best_seeing),
        "transparency_best": min(transp) if transp else None,
    }


def _longest_clear(hours: list[dict]) -> tuple[int, int]:
    best, run_start = (-1, -1), None
    for i, h in enumerate([*hours, {"clear": False}]):
        if h["clear"] and run_start is None:
            run_start = i
        elif not h["clear"] and run_start is not None:
            if best[0] < 0 or i - run_start > best[1] - best[0] + 1:
                best = (run_start, i - 1)
            run_start = None
    return best


def assess(raw: dict, sunset: datetime | None, site: dict, cfg: dict) -> dict:
    tz = ZoneInfo(site["timezone"])
    co_url = f"https://clearoutside.com/forecast/{site['lat']:.2f}/{site['lon']:.2f}"
    out = {
        "verdict": "UNKNOWN",
        "line": "",
        "window": None,
        "clear_from": None,
        "clear_to": None,
        "hours": [],
        "seven_timer": None,
        "errors": raw.get("errors", {}),
        "clear_outside_url": co_url,
        "thresholds": cfg,
    }
    if sunset is None:
        out["line"] = "UNKNOWN: no sunset computed"
        return out
    start, end = _window(sunset, tz)
    out["window"] = f"{start:%H:%M}-{end:%H:%M}"

    st = None
    if raw.get("seven_timer"):
        try:
            st = assess_seven_timer(raw["seven_timer"], start, end, cfg)
            out["seven_timer"] = st
        except (KeyError, ValueError) as exc:
            out["errors"]["7Timer"] = f"unreadable: {exc}"

    if raw.get("open_meteo"):
        try:
            out["hours"] = assess_open_meteo(raw["open_meteo"], start, end, tz, cfg)
        except (KeyError, ValueError) as exc:
            out["errors"]["Open-Meteo"] = f"unreadable: {exc}"

    hours = out["hours"]
    if hours:
        i0, i1 = _longest_clear(hours)
        clear_hours = 0 if i0 < 0 else i1 - i0 + 1
        if clear_hours >= cfg["min_clear_hours"]:
            out["clear_from"] = hours[i0]["hour"]
            out["clear_to"] = (
                datetime.strptime(hours[i1]["hour"], "%H:%M") + timedelta(hours=1)
            ).strftime("%H:%M")
            seg = hours[i0 : i1 + 1]
            out["verdict"] = "GO"
            detail = (
                f"clear {out['clear_from']}-{out['clear_to']}, "
                f"cloud ≤{max(h['cloud_eff'] for h in seg):.0f}%, "
                f"gusts ≤{max(h['gust_mph'] for h in seg):.0f} mph"
            )
        else:
            out["verdict"] = "NO-GO"
            worst = max(hours, key=lambda h: h["cloud_eff"])
            reasons = sorted({h["why_not"] for h in hours if h["why_not"]})
            detail = f"no clear hour block; {'; '.join(reasons[:3]) or worst['why_not']}"
        if st and st.get("mostly_clear") is not None:
            agree = st["mostly_clear"] == (out["verdict"] == "GO")
            if not agree:
                detail += "; 7Timer disagrees"
                out["verdict"] = "MAYBE"
        if st and st.get("seeing_arcsec"):
            detail += (
                f'; seeing {st["seeing_arcsec"]}", '
                f"transparency {st['transparency_best']}/8 (7Timer, 1 = best)"
            )
        out["line"] = f"{out['verdict']}: {detail}"
    elif st and st.get("mostly_clear") is not None:
        out["verdict"] = "MAYBE"
        out["line"] = (
            "MAYBE: Open-Meteo unavailable; 7Timer says "
            f"{'mostly clear' if st['mostly_clear'] else 'mostly cloudy'}"
        )
    else:
        out["line"] = "UNKNOWN: no forecast available"
    return out
