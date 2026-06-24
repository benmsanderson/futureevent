"""Sanity-check the lookup against the live event.

Pulls the June 2026 central-Europe / France heatwave value from ERA5T, places it
in present and future context via the lookup, and reports the present-day return
period for comparison against WWA-style published numbers.

It also estimates the product offset between the reference GEV product
(1.5 deg, 6-hourly) and the live ERA5T product (0.25 deg, hourly) over a shared
summer month, so the live value can be compared on the reference footing.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import xarray as xr

from . import config, metrics, runtime


def _open_era5t() -> xr.Dataset:
    return xr.open_zarr(config.ERA5T_STORE, chunks={"time": 240},
                        storage_options={"token": "anon"})


def _daily_regmean_window(store_open_fn, var, bbox, start, end) -> xr.DataArray:
    ds = store_open_fn()
    da = ds[var].sel(time=slice(start, end))
    da.attrs.setdefault("units", "K")
    sub = metrics.subset_bbox(da, bbox)
    reg = metrics.daily_regional_mean(sub)
    return reg.dropna("time")


def event_values(region_key: str, start: str, end: str) -> dict:
    """Peak daily regional-mean and peak 3-day mean over the event window."""
    bbox = config.REGIONS[region_key]["bbox"]
    reg = _daily_regmean_window(_open_era5t, config.ERA5_TAS_VAR, bbox, start, end)
    if reg.time.size == 0:
        raise RuntimeError(f"no ERA5T data available for {start}..{end}")
    daily_peak = float(reg.max())
    tx3 = metrics.rolling_window_mean(reg, 3)
    tx3_peak = float(tx3.max()) if np.isfinite(tx3).any() else float("nan")
    return {
        "available_days": int(reg.time.size),
        "first_day": str(reg.time.values[0])[:10],
        "last_day": str(reg.time.values[-1])[:10],
        "regional_mean_tasmax": daily_peak,
        "tx3x": tx3_peak,
    }


def product_offset(region_key: str, month_start: str, month_end: str) -> float:
    """Mean daily regional-mean difference (ERA5T minus reference) for a month.

    A positive value means the live 0.25 deg hourly product reads warmer than the
    1.5 deg 6-hourly reference; subtract it from a live value to compare on the
    reference footing.
    """
    bbox = config.REGIONS[region_key]["bbox"]
    ref = _daily_regmean_window(
        lambda: xr.open_zarr(config.ERA5_REFERENCE_STORE, chunks={"time": 240},
                             storage_options={"token": "anon"}),
        config.ERA5_TAS_VAR, bbox, month_start, month_end)
    live = _daily_regmean_window(_open_era5t, config.ERA5_TAS_VAR, bbox,
                                 month_start, month_end)
    ref_d = pd.Series(ref.values, index=pd.to_datetime(ref.time.values).date)
    live_d = pd.Series(live.values, index=pd.to_datetime(live.time.values).date)
    common = ref_d.index.intersection(live_d.index)
    if len(common) == 0:
        return float("nan")
    return float((live_d.loc[common] - ref_d.loc[common]).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookup", default="output/lookup.json")
    ap.add_argument("--region", default=config.PRIMARY_REGION)
    ap.add_argument("--start", default="2026-06-01")
    ap.add_argument("--end", default="2026-06-23")
    ap.add_argument("--offset-month", default="2021-06",
                    help="YYYY-MM shared month for the product-offset estimate")
    ap.add_argument("--x-obs", type=float, default=None,
                    help="override the event value (degC) instead of ERA5T")
    ap.add_argument("--no-offset", action="store_true")
    args = ap.parse_args()

    lookup = runtime.load_lookup(args.lookup)

    if args.x_obs is not None:
        ev = {"regional_mean_tasmax": args.x_obs, "tx3x": args.x_obs,
              "note": "x_obs override"}
    else:
        ev = event_values(args.region, args.start, args.end)
    print("event window:", ev)

    offset = float("nan")
    if not args.no_offset and args.x_obs is None:
        om = args.offset_month
        y, m = om.split("-")
        last = pd.Period(om, "M").days_in_month
        offset = product_offset(args.region, f"{om}-01", f"{om}-{last:02d}")
        print(f"product offset (ERA5T minus reference) for {om}: "
              f"{offset:+.2f} degC")

    for metric_key in config.METRICS:
        x = ev[metric_key]
        if not np.isfinite(x):
            continue
        print(f"\n=== {metric_key} ===")
        res_raw = runtime.evaluate(lookup, args.region, metric_key, x)
        print("raw live value:")
        print(runtime.format_report(res_raw))
        if np.isfinite(offset):
            res_adj = runtime.evaluate(lookup, args.region, metric_key, x - offset)
            print(f"offset-adjusted to reference footing (x={x - offset:.2f}):")
            print(runtime.format_report(res_adj))


if __name__ == "__main__":
    main()
