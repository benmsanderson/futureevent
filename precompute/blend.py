"""Blend ERA5T observations with the ECMWF forecast into one live event value.

The live daily-tasmax regional-mean series is assembled from, in order of
preference for any given day:

  1. ERA5T reanalysis, for days it has already ingested (up to ~5-7 days ago);
  2. the freshest ECMWF HRES forecast, for the most recent and near-future days;
  3. an older forecast cycle, to fill the gap between ERA5T's last day and the
     freshest cycle's start, and to overlap ERA5T so a forecast-vs-observation
     bias can be estimated.

Footing: the reference GEV lives on the 1.5 deg 6-hourly ERA5 product. The
forecast is first bias-corrected onto the ERA5T footing (using days where a
forecast and ERA5T coincide), then the whole blended series is shifted by the
ERA5T-vs-reference product offset so the event value can be read against the
lookup. Where no forecast/ERA5T overlap exists the forecast bias is set to zero
and flagged, since the HRES analysis and ERA5T are near-identical near-real-time
analyses of the same observations.
"""

from __future__ import annotations

import datetime as dt
import os
import re

import numpy as np
import pandas as pd
import xarray as xr

from . import config, forecast, metrics, runtime


# --------------------------------------------------------------------------
# ERA5T observed daily series
# --------------------------------------------------------------------------
def era5t_daily(region_key: str, start: str, end: str) -> pd.Series:
    """Observed daily regional-mean tasmax (degC), indexed by date."""
    bbox = config.REGIONS[region_key]["bbox"]
    ds = xr.open_zarr(config.ERA5T_STORE, chunks={"time": 240},
                      storage_options={"token": "anon"})
    da = ds[config.ERA5_TAS_VAR].sel(time=slice(start, end))
    da.attrs.setdefault("units", "K")
    sub = metrics.subset_bbox(da, bbox)
    reg = metrics.daily_regional_mean(sub).dropna("time")
    return pd.Series(reg.values, index=pd.to_datetime(reg.time.values).date)


# --------------------------------------------------------------------------
# Forecast cycle selection
# --------------------------------------------------------------------------
def _cycle_initday(date: str) -> dt.date:
    return dt.datetime.strptime(date, "%Y%m%d").date()


def choose_cycles(era5t_last_day: dt.date,
                  today: dt.date | None = None) -> list[tuple[str, str]]:
    """Pick the freshest cycle plus an older anchor that overlaps ERA5T.

    The anchor is the most recent cycle initialised at least two days before
    ERA5T's last observed day, so its early steps coincide with ERA5T (bias) and
    its horizon spans the gap up to the freshest cycle.

    When ``today`` is given, any cycle *issued after* ``today`` is dropped. In
    normal live operation ``today`` is now, so the freshest real cycle is issued
    on/before it and nothing is dropped. But when ``today`` is pinned in the past
    (the reanalysis refresh, ``FE_TODAY``), the real "latest" cycle is weeks ahead
    of the event window; its forecast days would otherwise be folded into the
    per-cell TXx max and silently contaminate the event field with out-of-window
    (e.g. high-summer) temperatures. Dropping it leaves a pure-reanalysis window.
    """
    date_prefixes, _ = forecast._s3_list("")
    date_prefixes = [p for p in date_prefixes if re.fullmatch(r"\d{8}/", p)]
    cycles: list[tuple[str, str]] = []
    for date_p in reversed(date_prefixes):
        cyc, _ = forecast._s3_list(date_p)
        for cycle_p in reversed(cyc):
            date = date_p.strip("/")
            cycle = cycle_p.strip("/").split("/")[-1]
            cycles.append((date, cycle))
        if len(cycles) > 40:
            break
    # newest first; keep only those with an oper grib set
    latest = forecast.latest_oper_cycle()
    chosen = [latest]
    # anchor: most recent long-horizon run (00z/12z reach 360h, vs 144h for
    # 06z/18z) initialised at least two days before ERA5T's last day, so it
    # overlaps ERA5T for the bias and spans the gap up to the freshest cycle.
    for date, cycle in cycles:
        if (date, cycle) == latest:
            continue
        if cycle not in ("00z", "12z"):
            continue
        if _cycle_initday(date) <= era5t_last_day - dt.timedelta(days=2):
            _, keys = forecast._s3_list(forecast._oper_dir(date, cycle),
                                        delimiter=False)
            if any(k.endswith(".grib2") for k in keys):
                chosen.append((date, cycle))
                break
    if today is not None:
        chosen = [(d, c) for d, c in chosen if _cycle_initday(d) <= today]
    return chosen


# --------------------------------------------------------------------------
# Blend
# --------------------------------------------------------------------------
def build_blend(region_key: str, recent_days: int = 40,
                max_lead_hours: int = 240) -> dict:
    """Assemble the blended live daily series and provenance for a region."""
    today = config_today()
    start = (today - dt.timedelta(days=recent_days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")  # ERA5T lags today; no future data to read

    obs = era5t_daily(region_key, start, end)
    era5t_last = max(obs.index)

    cycles = choose_cycles(era5t_last, today=today)
    # newest-cycle-wins map of forecast day -> (value, init)
    fc_value: dict[dt.date, float] = {}
    fc_source: dict[dt.date, str] = {}
    fc_provs = []
    for date, cycle in cycles:
        ser, prov = forecast.daily_regional_mean(
            region_key, date, cycle, max_lead_hours=max_lead_hours)
        fc_provs.append(prov)
        for day, val in ser.items():
            # prefer the cycle that is newest among those covering this day;
            # cycles is ordered newest-first, so only fill if unset
            if day not in fc_value:
                fc_value[day] = float(val)
                fc_source[day] = f"{date} {cycle}"

    fc = pd.Series(fc_value).sort_index()

    # forecast-vs-ERA5T bias from coinciding days
    overlap = sorted(set(fc.index) & set(obs.index))
    if len(overlap) >= 2:
        bias = float(np.mean([fc[d] - obs[d] for d in overlap]))
        bias_flag = None
    else:
        bias = 0.0
        bias_flag = "no_forecast_obs_overlap; forecast bias assumed 0"
    fc_adj = fc - bias  # onto the ERA5T footing

    # blended ERA5T footing: ERA5T for observed days, forecast after
    blended = obs.copy()
    source = {day: "ERA5T" for day in obs.index}
    for day, val in fc_adj.items():
        if day > era5t_last:
            blended[day] = val
            source[day] = fc_source[day]
    blended = blended.sort_index()

    # interior holes: days inside the span with no value from ERA5T or forecast
    span = pd.date_range(min(blended.index), max(blended.index), freq="D").date
    holes = [str(d) for d in span if d not in set(blended.index)]

    return {
        "region": region_key,
        "today": today.isoformat(),
        "era5t_last_day": era5t_last.isoformat(),
        "cycles_used": [f"{d} {c}" for d, c in cycles],
        "forecast_bias_vs_era5t": round(bias, 3),
        "bias_overlap_days": [str(d) for d in overlap],
        "bias_flag": bias_flag,
        "leading_gap_days": [str(d) for d in _gap_days(era5t_last, fc.index)],
        "interior_missing_days": holes,
        "blended_era5t_footing": {str(k): float(v) for k, v in blended.items()},
        "source_by_day": {str(k): source[k] for k in blended.index},
        "forecast_provenance": fc_provs,
    }


def _gap_days(era5t_last: dt.date, fc_days) -> list[dt.date]:
    if not len(fc_days):
        return []
    first_fc = min(fc_days)
    gap = []
    d = era5t_last + dt.timedelta(days=1)
    while d < first_fc:
        gap.append(d)
        d += dt.timedelta(days=1)
    return gap


def config_today() -> dt.date:
    """Today's date (UTC), or a pinned date from ``FE_TODAY`` (YYYY-MM-DD).

    Isolated so it can be overridden in tests and pinned deterministically for a
    reanalysis re-run: setting ``FE_TODAY`` fixes the 20-day event window and the
    forecast-cycle selection to a chosen day (e.g. once ERA5T has cleared the
    event peak), instead of relying on wall-clock "today".
    """
    pinned = os.environ.get("FE_TODAY")
    if pinned:
        return dt.date.fromisoformat(pinned.strip())
    return dt.datetime.now(dt.timezone.utc).date()


# --------------------------------------------------------------------------
# Live event value + evaluation
# --------------------------------------------------------------------------
def live_event_value(region_key: str, lookup: dict, era5t_ref_offset: float,
                     recent_days: int = 40, max_lead_hours: int = 240) -> dict:
    """Blend, put on the reference footing, extract event values, evaluate."""
    bl = build_blend(region_key, recent_days=recent_days,
                     max_lead_hours=max_lead_hours)
    blended = pd.Series({pd.to_datetime(k).date(): v
                         for k, v in bl["blended_era5t_footing"].items()}
                        ).sort_index()

    # reference footing = ERA5T footing minus the ERA5T-vs-reference offset
    ref_footing = blended - era5t_ref_offset
    daily_da = xr.DataArray(ref_footing.values,
                            coords={"time": pd.to_datetime(list(ref_footing.index))},
                            dims="time")

    results = {}
    for mkey, mcfg in config.METRICS.items():
        windowed = metrics.rolling_window_mean(daily_da, mcfg["window_days"])
        vals = pd.Series(windowed.values, index=ref_footing.index).dropna()
        if vals.empty:
            continue
        peak_day = vals.idxmax()
        x_obs = float(vals.max())
        ev = runtime.evaluate(lookup, region_key, mkey, x_obs)
        results[mkey] = {
            "x_obs_reference_footing": round(x_obs, 3),
            "peak_day": str(peak_day),
            "peak_source": bl["source_by_day"].get(str(peak_day), "unknown"),
            "evaluation": ev,
        }

    return {
        "blend": bl,
        "era5t_ref_offset": era5t_ref_offset,
        "metrics": results,
    }
