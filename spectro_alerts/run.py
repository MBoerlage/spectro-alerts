"""Daily run: collect, cross-match, filter for tonight, write outputs and state.

Usage: python -m spectro_alerts.run [--config config.yaml] [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import astropy.units as u
import yaml
from astropy.coordinates import Angle

from . import __version__, output, visibility
from . import state as state_mod
from .match import attach_atel_by_name, cross_match
from .model import SourceResult
from .sources import atel, cbat, tns

log = logging.getLogger("spectro_alerts")


def collect(cfg: dict, now: datetime) -> list[SourceResult]:
    f = cfg["filters"]
    src = cfg["sources"]
    ceiling = f["mag_max"] + f["watch_margin"]
    results = []
    if src.get("cbat_tocp", {}).get("enabled", True):
        results.append(cbat.fetch(src["cbat_tocp"], now, ceiling))
    if src.get("tns", {}).get("enabled", True):
        results.append(tns.fetch(src["tns"], now))
    if src.get("atel", {}).get("enabled", True):
        results.append(atel.fetch(src["atel"], now))
    return results


def build(
    cfg: dict, results: list[SourceResult], now: datetime, local_date: datetime, state: dict
) -> dict:
    f = cfg["filters"]
    cands = [c for r in results for c in r.candidates]
    atel_items = [i for r in results if r.source == "ATel" for i in r.items]
    objects = cross_match(cands, f["match_radius_arcsec"])
    # An ATel with coordinates but no matching alert is news, not a target.
    objects = [o for o in objects if o.sources != ["ATel"]]
    attach_atel_by_name(objects, atel_items)

    night = visibility.tonight(cfg["site"], f["sun_alt_max_deg"], local_date)
    vis = visibility.evaluate(
        night, [o.ra for o in objects], [o.dec for o in objects], f["min_alt_deg"]
    )

    targets, watch = [], []
    for obj, v in zip(objects, vis, strict=True):
        if v["hours"] < f["min_hours"]:
            continue
        key, is_new = state_mod.update(
            state, state_mod.match_known(state, obj.ra, obj.dec, f["match_radius_arcsec"]), obj, now
        )
        best = obj.best_mag
        first = obj.first_report
        rec = {
            "id": key,
            "name": obj.name,
            "names": obj.names,
            "obj_type": obj.obj_type,
            "ra": round(obj.ra, 6),
            "dec": round(obj.dec, 6),
            "ra_hms": Angle(obj.ra * u.deg).to_string(unit=u.hour, sep=":", precision=2, pad=True),
            "dec_dms": Angle(obj.dec * u.deg).to_string(
                unit=u.deg, sep=":", precision=1, alwayssign=True, pad=True
            ),
            "mag": best.mag if best else None,
            "mag_band": best.band if best else None,
            "mag_kind": best.mag_kind if best else None,
            "mag_source": best.source if best else None,
            "disc_date": first.disc_date.isoformat() if first.disc_date else None,
            "first_source": first.source,
            "is_new": is_new,
            "first_seen_by_pipeline": state["objects"][key]["first_seen"],
            "visibility": v,
            "moon_warning": v["moon_sep"] is not None and v["moon_sep"] < f["moon_min_sep_deg"],
            "reports": [r.to_dict() for r in obj.reports],
            **obj.flags(),
        }
        if rec["mag"] is not None and rec["mag"] <= f["mag_max"]:
            targets.append(rec)
        elif rec["mag"] is None or rec["mag"] <= f["mag_max"] + f["watch_margin"]:
            watch.append(rec)

    def order(t: dict) -> tuple:
        return (t["mag"] if t["mag"] is not None else 99, not t["is_new"])

    targets.sort(key=order)
    watch.sort(key=order)
    return {
        "schema_version": 1,
        "pipeline_version": __version__,
        "generated_utc": now.strftime("%Y-%m-%d %H:%M"),
        "site": cfg["site"],
        "filters": f,
        "night": {
            "date": local_date.strftime("%Y-%m-%d"),
            "dark_start": night.dark_start.strftime("%H:%M") if night.dark_start else None,
            "dark_end": night.dark_end.strftime("%H:%M") if night.dark_end else None,
        },
        "source_status": [
            {
                "source": r.source,
                "ok": r.ok,
                "error": r.error,
                "fetched": r.fetched,
                "candidates": len(r.candidates),
            }
            for r in results
        ],
        "targets": targets,
        "watch": watch,
        "atel_recent": atel_items,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--date", help="local night to plan (YYYY-MM-DD); default today")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = yaml.safe_load(Path(args.config).read_text())
    tz = ZoneInfo(cfg["site"]["timezone"])
    now = datetime.now(timezone.utc)
    local_date = (
        datetime.strptime(args.date, "%Y-%m-%d").replace(hour=12, tzinfo=tz)
        if args.date
        else now.astimezone(tz)
    )

    out_cfg = cfg["output"]
    state_path = Path(out_cfg["state_file"])
    state = state_mod.load(state_path)

    results = collect(cfg, now)
    payload = build(cfg, results, now, local_date, state)

    docs = Path(out_cfg["docs_dir"])
    output.write_json(docs / "candidates.json", payload)
    output.write_page(docs / "index.html", payload)
    (docs / ".nojekyll").touch()
    state_mod.prune(state, now, out_cfg.get("state_keep_days", 90))
    state_mod.save(state_path, state)

    for s in payload["source_status"]:
        log.info(
            "%s: %s, %d rows, %d candidates%s",
            s["source"],
            "ok" if s["ok"] else "FAILED",
            s["fetched"],
            s["candidates"],
            f" ({s['error']})" if s["error"] else "",
        )
    log.info("Targets: %d, watch: %d", len(payload["targets"]), len(payload["watch"]))
    # Fail the workflow only if every source failed.
    return 0 if any(s["ok"] for s in payload["source_status"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
