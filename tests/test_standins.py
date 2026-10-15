from datetime import datetime, timezone

import pytest
from conftest import FIX, LOCAL_DATE, NOW

from spectro_alerts import run
from spectro_alerts.sources import asassn, mukai, rochester


def test_rochester_parses_latest_magnitudes_and_skips_stale():
    rows = rochester.parse((FIX / "rochester_active.html").read_text(encoding="latin-1"))
    assert rows[0]["name"] == "2026sqf" and rows[0]["latest_mag"] == "12.5"
    cands = rochester.rows_to_candidates(rows, 16.5, NOW, 40)
    names = [c.name for c in cands]
    assert names[:3] == ["SN 2026sqf", "SN 2026aaiv", "AT 2026aaom"]
    assert "AT 2026zsr" not in names  # "16.2*" = last observation over a month old
    sn = cands[0]
    assert sn.mag == 12.5 and sn.mag_kind == "latest" and sn.obj_type == "SN Ia-CSM"
    assert sn.ra == pytest.approx(159.69984, abs=1e-4) and "AT2026uxt" in sn.extra["names"]
    assert cands[2].obj_type == "extragalactic nova"
    # Last seen 2026-09-15: dropped with a 30-day limit.
    assert "AT 2026aaom" not in [c.name for c in rochester.rows_to_candidates(rows, 16.5, NOW, 30)]
    # The magnitude ceiling applies to the latest magnitude.
    assert [c.name for c in rochester.rows_to_candidates(rows, 12.9, NOW, 30)] == ["SN 2026sqf"]


def test_rochester_layout_change_is_reported():
    with pytest.raises(ValueError):
        rochester.parse("<html>new layout</html>")


def test_mukai_parses_confirmed_novae_with_aras_links():
    rows = mukai.parse((FIX / "mukai_novae.html").read_text())
    by = {r["name"]: r for r in rows}
    assert by["V488 Sge"]["aliases"] == ["Nova Sagittae 2026", "PNV J19450648+1822422"]
    assert by["V488 Sge"]["aras_url"].endswith("novasge2026.html")
    late = datetime(2026, 9, 20, tzinfo=timezone.utc)
    cands = mukai.rows_to_candidates(rows, 14.0, late, 60)
    names = [c.name for c in cands]
    assert "V488 Sge" in names and "V2104 Aql" not in names  # July: outside 60 days
    v488 = next(c for c in cands if c.name == "V488 Sge")
    assert v488.mag == 7.1 and v488.mag_kind == "peak" and v488.band == "V"
    assert v488.extra["spectroscopically_confirmed"]
    everything = [c.name for c in mukai.rows_to_candidates(rows, 14.0, late, 400)]
    assert "AT 2026stb" not in everything  # peak 16.0 is too faint
    assert "PRIME26ahygn" not in everything  # malformed Dec "57..9" is skipped, not fatal
    assert "AT2026lck" in everything  # "r=13.8" peak is read with its band


def test_mukai_layout_change_is_reported():
    with pytest.raises(ValueError):
        mukai.parse("<html>moved</html>")


def test_pipeline_with_standins_and_mukai_name_wins(cfg, fake_http):
    cfg["sources"]["tns"]["enabled"] = False
    cfg["sources"]["rochester"]["enabled"] = True
    cfg["sources"]["mukai"]["enabled"] = True
    cfg["sources"]["mukai"]["lookback_days"] = 90
    payload = run.build(cfg, run.collect(cfg, NOW), NOW, LOCAL_DATE, {"objects": {}})
    status = {s["source"]: s["ok"] for s in payload["source_status"]}
    assert status == {"CBAT TOCP": True, "Rochester": True, "Mukai novae": True, "ATel": True}
    listed = payload["targets"] + payload["watch"] + payload["poorly_placed"]
    names = {t["name"] for t in listed} | {s["name"] for s in payload["skipped"]}
    assert "SN 2026aaiv" in names  # Rochester object
    # The CBAT fixture's PNV J19450648+1822422 is V488 Sge: Mukai's name and ARAS link win.
    v488 = next(t for t in listed if t["name"] == "V488 Sge")
    assert "PNV J19450648+1822422" in v488["names"]
    assert v488["confirmed_nova"] and v488["aras_url"].endswith("novasge2026.html")


def test_asassn_reads_bright_novae_and_skips_flares_and_junk_magnitudes():
    rows = asassn.parse((FIX / "asassn_transients.html").read_text())
    assert len(rows) == 9
    when = datetime(2026, 9, 20, tzinfo=timezone.utc)
    cands = {c.name: c for c in asassn.rows_to_candidates(rows, 14.0, when, 60)}
    assert set(cands) == {"ASASSN-26fc", "V488 Sge"}
    fc = cands["ASASSN-26fc"]
    assert fc.extra["names"] == ["AT 2026abbx"] and fc.obj_type == "nova candidate"
    assert fc.mag == 12.14 and fc.ra == pytest.approx(268.02829, abs=1e-4)
    v488 = cands["V488 Sge"]
    assert v488.obj_type == "nova" and "PNV J19450648+1822422" in v488.extra["names"]
    # Recovery row: first-report date comes from the comment, not ASAS-SN's own detection.
    assert v488.disc_date.date().isoformat() == "2026-08-25"
    # ASASSN-26ez (M-dwarf flare) and the negative "magnitudes" never become candidates.
    later = datetime(2026, 10, 15, tzinfo=timezone.utc)
    names = {c.name for c in asassn.rows_to_candidates(rows, 30.0, later, 400)}
    assert "ASASSN-26ez" not in names and "ASASSN-26fl" not in names
    assert "AT2026adgn" not in names and "ASASSN-26no" in names


def test_asassn_layout_change_is_reported():
    with pytest.raises(ValueError):
        asassn.parse("<html>maintenance</html>")
