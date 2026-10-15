"""Shared fixtures: real-format samples served instead of network calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import yaml

from spectro_alerts import http

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent

NOW = datetime(2026, 10, 15, 20, 30, tzinfo=timezone.utc)  # 15:30 CDT run
LOCAL_DATE = datetime(2026, 10, 15, 12, tzinfo=ZoneInfo("America/Chicago"))


@pytest.fixture
def cfg() -> dict:
    c = yaml.safe_load((ROOT / "config.yaml").read_text())
    # Tests pin the ceiling so they don't change when the config is tuned.
    c["filters"]["mag_max"] = 12.0
    # The original pipeline tests run on CBAT + TNS + ATel; the stand-in sources have their own.
    c["sources"]["tns"]["enabled"] = True
    c["sources"]["rochester"]["enabled"] = False
    c["sources"]["mukai"]["enabled"] = False
    return c


@pytest.fixture
def fake_http(monkeypatch):
    """Route http.get to fixture files by URL; record calls; no network."""
    calls: list[str] = []

    def fake_get(url, params=None, timeout=30):
        calls.append(url)
        if "tocp.html" in url:
            body = (FIX / "tocp.html").read_text()
        elif "followups" in url:
            body = (FIX / "followup.html").read_text()
        elif "wis-tns" in url:
            body = (FIX / "tns.csv").read_text()
        elif "open-meteo" in url:
            return SimpleNamespace(json=lambda: json.loads((FIX / "open_meteo.json").read_text()))
        elif "7timer" in url:
            return SimpleNamespace(json=lambda: json.loads((FIX / "seven_timer.json").read_text()))
        elif "rochesterastronomy" in url:
            body = (FIX / "rochester_active.html").read_text(encoding="latin-1")
        elif "Koji.Mukai" in url:
            body = (FIX / "mukai_novae.html").read_text()
        elif "astronomerstelegram" in url:
            body = (FIX / "atel.xml").read_text()
        else:
            raise AssertionError(f"unexpected URL {url}")
        return SimpleNamespace(text=body)

    monkeypatch.setattr(http, "get", fake_get)
    return calls
