import json

from conftest import LOCAL_DATE, NOW

from spectro_alerts import output, run
from spectro_alerts.match import cross_match
from spectro_alerts.model import Candidate


def test_cross_match_merges_within_radius_only():
    a = Candidate("TCP J1", 34.82233, 28.95439, "CBAT TOCP", mag=11.5)
    b = Candidate("AT 2026x", 34.82238, 28.95442, "TNS", mag=11.6)  # ~0.2" away
    c = Candidate("far", 34.83, 28.96, "TNS", mag=11.0)  # ~35" away
    objs = cross_match([a, b, c], radius_arcsec=5)
    assert len(objs) == 2
    merged = next(o for o in objs if len(o.reports) == 2)
    assert merged.name == "TCP J1"  # CBAT name wins
    assert set(merged.sources) == {"CBAT TOCP", "TNS"}


def test_full_build_targets_watch_and_state(cfg, fake_http):
    state = {"objects": {}}
    results = run.collect(cfg, NOW)
    payload = run.build(cfg, results, NOW, LOCAL_DATE, state)

    names = {t["name"] for t in payload["targets"]}
    # TCP J0219 (11.5, Triangulum) is up all night from Tomball in October.
    assert "TCP J02191736+2857158" in names
    tcp = next(t for t in payload["targets"] if t["name"] == "TCP J02191736+2857158")
    assert set(tcp["names"]) >= {"TCP J02191736+2857158", "AT 2026afkk"}
    assert {"CBAT TOCP", "TNS", "ATel"} <= {r["source"] for r in tcp["reports"]}
    assert tcp["spectroscopically_confirmed"] and tcp["has_atel"]
    assert tcp["visibility"]["hours"] >= 1 and tcp["is_new"]
    assert tcp["first_source"] == "CBAT TOCP"

    # Sgr nova candidate is low in the SW after nautical twilight but still gets over 1 h.
    sgr = next(t for t in payload["targets"] if "J18251276" in t["name"])
    assert 1.0 <= sgr["visibility"]["hours"] < 2.5 and sgr["visibility"]["start"] == "19:45"
    # SN 2026afaa (13.9, Coma) is a daytime object in October: never up, so skipped.
    assert payload["poorly_placed"] == []
    assert any(s["name"] == "SN 2026afaa" for s in payload["skipped"])
    # 12.2 mag And transient: just fainter than V 12 -> watch list.
    assert any(t["name"] == "TCP J00560713+4301406" for t in payload["watch"])
    # ATel-only objects (Cyg X-3) are news, not targets.
    assert all("Cyg X-3" not in t["name"] for t in payload["targets"] + payload["watch"])
    assert all(s["ok"] for s in payload["source_status"])

    # Second run: same object is an update, not new.
    payload2 = run.build(cfg, run.collect(cfg, NOW), NOW, LOCAL_DATE, state)
    tcp2 = next(t for t in payload2["targets"] if t["name"] == "TCP J02191736+2857158")
    assert not tcp2["is_new"] and tcp2["id"] == tcp["id"]


def test_bright_but_short_window_is_reported_not_dropped(cfg, fake_http):
    cfg["filters"]["min_hours"] = 3.0  # makes the low Sgr object fail the window
    payload = run.build(cfg, run.collect(cfg, NOW), NOW, LOCAL_DATE, {"objects": {}})
    names = [t["name"] for t in payload["poorly_placed"]]
    assert any("J18251276" in n for n in names)
    assert all("J18251276" not in t["name"] for t in payload["targets"] + payload["watch"])
    low = next(t for t in payload["poorly_placed"] if "J18251276" in t["name"])
    assert low["visibility"]["hours"] > 0 and low["id"] is None


def test_outputs_written(cfg, fake_http, tmp_path):
    payload = run.build(cfg, run.collect(cfg, NOW), NOW, LOCAL_DATE, {"objects": {}})
    output.write_json(tmp_path / "candidates.json", payload)
    output.write_page(tmp_path / "index.html", payload)
    data = json.loads((tmp_path / "candidates.json").read_text())
    assert data["schema_version"] == 1 and data["targets"]
    page = (tmp_path / "index.html").read_text()
    assert "TCP J02191736+2857158" in page and "Targets tonight" in page
