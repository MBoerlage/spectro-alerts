from types import SimpleNamespace

import pytest
from conftest import FIX, NOW

from spectro_alerts import http
from spectro_alerts.coords import from_designation, parse_sexagesimal
from spectro_alerts.sources import atel, cbat, tns


def test_cbat_parses_rows_and_skips_bad_lines():
    rows = cbat.parse_index((FIX / "tocp.html").read_text())
    desigs = [r["desig"] for r in rows]
    assert "J12345678+1234567" not in desigs  # garbage line skipped
    assert len(rows) == 9
    first = rows[0]
    assert first["prefix"] == "PNV"
    assert first["ra"] == pytest.approx(10.66279, abs=1e-4)
    assert first["dec"] == pytest.approx(41.22383, abs=1e-4)
    assert first["disc_date"].day == 16 and first["disc_date"].hour == 12
    assert first["mag"] == 17.6 and first["band"] == "U"


def test_cbat_fallback_uses_designation_coordinates():
    rows = cbat.parse_index((FIX / "tocp.html").read_text())
    psn = next(r for r in rows if r["desig"] == "J04175427-5636452")
    assert psn["mag"] is None
    assert psn["ra"] == pytest.approx(64.4761, abs=1e-3)
    assert psn["dec"] == pytest.approx(-56.6126, abs=1e-3)


def test_cbat_filters_prefix_age_and_reads_followups(cfg, fake_http):
    res = cbat.fetch(cfg["sources"]["cbat_tocp"], NOW, mag_ceiling=14.0)
    names = {c.name for c in res.candidates}
    assert res.ok
    assert "PSN J01232438+0925545" not in names  # PSN prefix excluded
    assert "TCP J07264579-2745141" not in names  # older than 30 days
    assert "PNV J00423907+4113258" not in names  # 2011
    assert {"TCP J02191736+2857158", "PNV J19450648+1822422"} <= names
    bright = next(c for c in res.candidates if c.name == "TCP J02191736+2857158")
    assert bright.obj_type == "transient"
    assert bright.band == "unfiltered"
    assert bright.extra["spectroscopically_confirmed"] is True
    assert "Balmer emission" in bright.extra["followup_summary"]
    nova = next(c for c in res.candidates if c.name == "PNV J19450648+1822422")
    assert nova.obj_type == "nova candidate" and nova.band == "clear"
    followups = [u for u in fake_http if "followups" in u]
    assert 0 < len(followups) <= cfg["sources"]["cbat_tocp"]["max_followups"]


def test_cbat_failure_is_reported_not_raised(cfg, monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(http, "get", boom)
    res = cbat.fetch(cfg["sources"]["cbat_tocp"], NOW, 14.0)
    assert not res.ok and "down" in res.error


def test_tns_csv_filters_by_discovery_mag_and_bad_coords(cfg, fake_http):
    res = tns.fetch(cfg["sources"]["tns"], NOW)
    names = {c.name for c in res.candidates}
    assert res.ok and res.fetched == 5
    assert names == {"AT 2026afkk", "SN 2026afaa"}  # faint rows and bad RA dropped
    sn = next(c for c in res.candidates if c.name == "SN 2026afaa")
    assert sn.obj_type == "SN Ia" and sn.url.endswith("/object/2026afaa")
    assert sn.ra == pytest.approx(188.9673, abs=1e-3)


def test_tns_non_csv_response_marks_source_failed(cfg, monkeypatch):
    monkeypatch.setattr(http, "get", lambda *a, **k: SimpleNamespace(text="<html>blocked"))
    res = tns.fetch(cfg["sources"]["tns"], NOW)
    assert not res.ok


def test_atel_items_coords_and_lookback():
    res = atel.parse_feed((FIX / "atel.xml").read_text(), NOW, lookback_days=7)
    assert len(res.items) == 3  # Aug telegram is outside the lookback
    first = res.items[0]
    assert "TCP J02191736+2857158" in first["names"] and first["of_interest"]
    assert len(res.candidates) == 2  # two telegrams give coordinates
    cyg = next(c for c in res.candidates if "Cyg X-3" in c.name)
    assert cyg.ra == pytest.approx(308.1074, abs=1e-3)
    assert cyg.dec == pytest.approx(40.9578, abs=1e-3)


def test_coordinate_helpers():
    ra, dec = from_designation("PNV J19450648+1822422")
    assert ra == pytest.approx(296.2770, abs=1e-3)
    assert dec == pytest.approx(18.37839, abs=1e-4)
    ra, dec = parse_sexagesimal("12 35 52.16", "-27:55:56.0")
    assert dec < 0 and ra == pytest.approx(188.9673, abs=1e-3)
