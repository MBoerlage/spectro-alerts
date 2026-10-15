"""Shared fixtures: real-format samples served instead of network calls."""

from __future__ import annotations

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
    return yaml.safe_load((ROOT / "config.yaml").read_text())


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
        elif "astronomerstelegram" in url:
            body = (FIX / "atel.xml").read_text()
        else:
            raise AssertionError(f"unexpected URL {url}")
        return SimpleNamespace(text=body)

    monkeypatch.setattr(http, "get", fake_get)
    return calls
