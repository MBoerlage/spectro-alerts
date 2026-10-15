"""Shared HTTP session with a descriptive User-Agent."""

from __future__ import annotations

import requests

USER_AGENT = (
    "SpectroAlerts/0.1 (amateur spectroscopy alert digest; Tomball TX; "
    "https://github.com/MBoerlage/spectro-alerts)"
)
TIMEOUT = 30


def get(url: str, params: dict | None = None, timeout: float = TIMEOUT) -> requests.Response:
    """GET with our User-Agent; raises for HTTP errors."""
    resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp
