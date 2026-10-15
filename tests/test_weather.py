import json
from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import FIX, LOCAL_DATE, NOW

from spectro_alerts import run, weather

TZ = ZoneInfo("America/Chicago")
SITE = {"lat": 30.0972, "lon": -95.6161, "timezone": "America/Chicago"}
SUNSET = datetime(2026, 10, 15, 18, 55, tzinfo=TZ)


def _raw(om=True, st=True):
    return {
        "open_meteo": json.loads((FIX / "open_meteo.json").read_text()) if om else None,
        "seven_timer": json.loads((FIX / "seven_timer.json").read_text()) if st else None,
        "errors": {},
    }


def test_effective_cloud_weights_high_cloud_less():
    assert weather.effective_cloud(0, 0, 0, 0.5) == 0
    assert weather.effective_cloud(20, 0, 0, 0.5) == 20
    assert weather.effective_cloud(0, 0, 40, 0.5) == 20
    assert 30 < weather.effective_cloud(20, 20, 0, 0.5) < 40  # overlap, not a plain sum


def test_go_tonight_with_7timer_agreeing(cfg):
    w = weather.assess(_raw(), SUNSET, SITE, cfg["weather"])
    assert w["window"] == "18:00-00:00"
    assert [h["hour"] for h in w["hours"]][:2] == ["18:00", "19:00"] and len(w["hours"]) == 6
    assert not w["hours"][0]["clear"] and "cloud 22%" in w["hours"][0]["why_not"]
    assert w["verdict"] == "GO"
    assert (w["clear_from"], w["clear_to"]) == ("19:00", "00:00")
    assert w["line"].startswith("GO: clear 19:00-00:00")
    assert "seeing" in w["line"] and w["seven_timer"]["mostly_clear"]
    assert w["clear_outside_url"].endswith("/30.10/-95.62")


def test_no_go_when_gusty(cfg):
    c = dict(cfg["weather"], max_gust_mph=5)
    w = weather.assess(_raw(st=False), SUNSET, SITE, c)
    assert w["verdict"] == "NO-GO" and "gusts" in w["line"]


def test_maybe_when_sources_disagree(cfg):
    raw = _raw()
    for d in raw["seven_timer"]["dataseries"]:
        d["cloudcover"] = 8
    w = weather.assess(raw, SUNSET, SITE, cfg["weather"])
    assert w["verdict"] == "MAYBE" and "7Timer disagrees" in w["line"]


def test_fallbacks_when_sources_missing(cfg):
    w = weather.assess(_raw(om=False), SUNSET, SITE, cfg["weather"])
    assert w["verdict"] == "MAYBE" and "Open-Meteo unavailable" in w["line"]
    w = weather.assess(_raw(om=False, st=False), SUNSET, SITE, cfg["weather"])
    assert w["verdict"] == "UNKNOWN"


def test_fetch_and_build_include_weather(cfg, fake_http):
    raw = weather.fetch(cfg["site"], cfg["weather"])
    assert raw["open_meteo"] and raw["seven_timer"] and not raw["errors"]
    payload = run.build(cfg, run.collect(cfg, NOW), NOW, LOCAL_DATE, {"objects": {}}, raw)
    assert payload["weather"]["verdict"] == "GO"
    assert payload["night"]["sunset"].startswith("18:")


def test_hours_night_runs_to_sunrise_but_verdict_stays_evening(cfg):
    sunrise = SUNSET.replace(day=SUNSET.day + 1, hour=7, minute=24)
    w = weather.assess(_raw(), SUNSET, SITE, cfg["weather"], sunrise)
    night = w["hours_night"]
    assert night[0]["hour"] == w["hours"][0]["hour"] and night[-1]["hour"] == "07:00"
    assert len(night) > len(w["hours"])
    assert all(h["in_verdict"] for h in night[: len(w["hours"])])
    assert not any(h["in_verdict"] for h in night[len(w["hours"]) :])
    # Same verdict as without the extra hours.
    assert w["verdict"] == weather.assess(_raw(), SUNSET, SITE, cfg["weather"])["verdict"]
