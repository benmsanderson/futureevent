"""Produce the live event value: blend ERA5T + ECMWF forecast and evaluate it.

This is the small, frequently-run job (distinct from the heavy precompute) that
emits ``output/live_<region>.json``: the current blended event value on the
reference footing, where it falls under the present and each future warming
level, and full provenance (cycles used, bias, offsets, per-day source). The
frontend reads the static lookup plus this live value; it does no live data
access itself.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os

import pandas as pd

from . import config, blend, runtime, sanity_check


def _offset_cache_path(region_key: str, month: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"offset_{region_key}_{month}.json")


def era5t_ref_offset(region_key: str, month: str = "2021-06",
                     use_cache: bool = True) -> float:
    """ERA5T-vs-reference product offset for a region (cached).

    Estimated over a shared summer month (the reference store ends in 2021, so
    the month must predate that). Positive means the live 0.25 deg product reads
    warmer than the 1.5 deg reference.
    """
    cache = _offset_cache_path(region_key, month)
    if use_cache and os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)["offset"]
    last = pd.Period(month, "M").days_in_month
    off = sanity_check.product_offset(region_key, f"{month}-01", f"{month}-{last:02d}")
    with open(cache, "w") as fh:
        json.dump({"offset": off, "month": month}, fh)
    return off


def build_live(region_key: str, lookup_path: str, offset_month: str = "2021-06",
               recent_days: int = 20, max_lead_hours: int = 240) -> dict:
    lookup = runtime.load_lookup(lookup_path)
    offset = era5t_ref_offset(region_key, offset_month)
    res = blend.live_event_value(region_key, lookup, offset,
                                 recent_days=recent_days,
                                 max_lead_hours=max_lead_hours)
    bl = res["blend"]
    out = {
        "schema": "live_event_value/0.1",
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": region_key,
        "region_name": config.REGIONS[region_key]["name"],
        "lookup_version": lookup["metadata"]["version"],
        "footing_note": (
            "Event value placed on the 1.5 deg 6-hourly reference footing: "
            "forecast bias-corrected onto ERA5T, then shifted by the "
            "ERA5T-vs-reference product offset."),
        "era5t_ref_offset": round(offset, 3),
        "offset_month": offset_month,
        "blend_provenance": {
            "today": bl["today"],
            "era5t_last_day": bl["era5t_last_day"],
            "cycles_used": bl["cycles_used"],
            "forecast_bias_vs_era5t": bl["forecast_bias_vs_era5t"],
            "bias_overlap_days": bl["bias_overlap_days"],
            "bias_flag": bl["bias_flag"],
            "leading_gap_days": bl["leading_gap_days"],
            "interior_missing_days": bl["interior_missing_days"],
            "source_by_day": bl["source_by_day"],
        },
        "metrics": {
            mkey: {
                "name": config.METRICS[mkey]["name"],
                "units": config.METRICS[mkey]["units"],
                "x_obs_reference_footing": mres["x_obs_reference_footing"],
                "peak_day": mres["peak_day"],
                "peak_source": mres["peak_source"],
                "present": mres["evaluation"]["present"],
                "warming_levels": mres["evaluation"]["warming_levels"],
            }
            for mkey, mres in res["metrics"].items()
        },
    }
    return out


def _print_summary(live: dict):
    print(f"=== live event: {live['region_name']} "
          f"(today {live['blend_provenance']['today']}) ===")
    bp = live["blend_provenance"]
    print(f"ERA5T last day: {bp['era5t_last_day']}; cycles: {bp['cycles_used']}; "
          f"forecast bias vs ERA5T: {bp['forecast_bias_vs_era5t']} degC; "
          f"ERA5T-ref offset: {live['era5t_ref_offset']} degC")
    if bp["leading_gap_days"] or bp["interior_missing_days"]:
        print(f"  gaps: leading={bp['leading_gap_days']} "
              f"interior={bp['interior_missing_days']}")
    for mkey, m in live["metrics"].items():
        p = m["present"]
        print(f"\n{mkey}: peak {m['x_obs_reference_footing']} degC on "
              f"{m['peak_day']} [{m['peak_source']}]")
        print(f"  present (GMST +{p['gmst_anom']}): 1-in-"
              f"{p['return_period_years']:.0f} yr (p={p['exceedance_prob']:.4f})")
        for gwl, v in m["warming_levels"].items():
            r = v["probability_ratio_vs_present"]
            rtxt = "n/a (impossible now)" if r is None else f"{r:.1f}x vs present"
            print(f"  +{gwl} degC: 1-in-{v['return_period_years']:.0f} yr, {rtxt}")


def main():
    ap = argparse.ArgumentParser(description="Emit the live blended event value.")
    ap.add_argument("--region", default=config.PRIMARY_REGION)
    ap.add_argument("--lookup", default=os.path.join(config.OUTPUT_DIR, "lookup.json"))
    ap.add_argument("--offset-month", default="2021-06")
    ap.add_argument("--recent-days", type=int, default=20)
    ap.add_argument("--max-lead-hours", type=int, default=240)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    live = build_live(args.region, args.lookup, offset_month=args.offset_month,
                      recent_days=args.recent_days,
                      max_lead_hours=args.max_lead_hours)
    out = args.out or os.path.join(config.OUTPUT_DIR, f"live_{args.region}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        # fail loud on any non-finite that would break JSON.parse in the browser
        json.dump(live, fh, indent=2, allow_nan=False)
    _print_summary(live)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
