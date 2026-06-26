"""Gridded probability-ratio field for the spatial map.

Mirrors the point method at every cell of a Europe domain on the 1.5 deg
reference grid:

  - present: obs-anchored non-stationary GEV per cell from ERA5 (GMST covariate),
    evaluated at the present GMST anomaly;
  - future: CMIP6 ensemble-median per-cell change factors (dloc/dGWL, dscale/dGWL)
    from per-model non-stationary GEV fits with the model GWL as covariate;
  - event field: the ERA5T + ECMWF forecast blend per cell, regridded to the
    reference grid and placed on the reference footing.

The output ``output/grid_<domain>.json`` carries, per cell and metric, the event
value, the present return period, and the probability ratio at each warming
level. Per-model GWL series are reused from the cmip6 raw cache (GWL is global,
region-independent), so this step only re-reads the regional tasmax fields.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import xarray as xr

from . import config, blend, cmip6, era5, forecast, gmst, metrics
from .gev import exceedance_prob, fit_nonstationary, return_level

DOMAIN = {"name": "europe", "bbox": [-10.0, 36.0, 25.0, 56.0]}
MIN_YEARS = 40
# The per-cell GEV fits parallelise cleanly across cells, but on a shared fat
# node we must stay under the good-neighbour ceiling (config.MAX_WORKERS), not
# grab every core. Cap to MAX_WORKERS (and never more than cores-1).
_FIT_WORKERS = max(1, min(config.MAX_WORKERS, (os.cpu_count() or 2) - 1))


# --------------------------------------------------------------------------
# Per-cell annual maxima and GEV fitting
# --------------------------------------------------------------------------
def _annual_max_field(daily: xr.DataArray, window_days: int,
                      min_days: int = 300) -> xr.DataArray:
    """(time, lat, lon) daily degC -> (year, lat, lon) annual block maxima."""
    if window_days > 1:
        daily = daily.rolling(time=window_days, min_periods=window_days).mean()
    counts = daily.notnull().resample(time="YE").sum()
    amax = daily.resample(time="YE").max().where(counts >= min_days)
    amax = amax.assign_coords(year=amax["time"].dt.year)
    return amax.swap_dims({"time": "year"}).drop_vars("time")


def _fit_cell(payload):
    """Worker: fit one cell. payload = (j, i, y, g, fit_scale)."""
    j, i, y, g, fit_scale = payload
    try:
        f = fit_nonstationary(y, g, covariate_name="cov",
                              fit_scale_covariate=fit_scale)
    except Exception:  # noqa: BLE001
        return (j, i, None)
    return (j, i, (f.shape, f.loc0, f.dloc, f.scale0, f.dscale))


def _fit_field(amax: xr.DataArray, cov: pd.Series, fit_scale: bool,
               min_years: int = MIN_YEARS):
    """Fit a non-stationary GEV at every cell (parallel); return param arrays.

    ``min_years`` is the minimum number of valid annual maxima a cell needs to be
    fit. It defaults to the 1.5 deg reference's MIN_YEARS (40, suited to the
    63-year record); the 0.25 deg local_txx climatology passes a lower value to
    match its shorter (e.g. 1991-2020) period.
    """
    la, lo = metrics.lat_name(amax), metrics.lon_name(amax)
    years = amax["year"].values
    g = cov.reindex(years).values
    lats, lons = amax[la].values, amax[lo].values
    vals = amax.transpose("year", la, lo).values  # (year, nlat, nlon)
    _, nlat, nlon = vals.shape
    shape = np.full((nlat, nlon), np.nan)
    loc0 = np.full((nlat, nlon), np.nan)
    dloc = np.full((nlat, nlon), np.nan)
    scale0 = np.full((nlat, nlon), np.nan)
    dscale = np.full((nlat, nlon), np.nan)

    jobs = []
    for j in range(nlat):
        for i in range(nlon):
            y = vals[:, j, i]
            m = np.isfinite(y) & np.isfinite(g)
            if m.sum() >= min_years:
                jobs.append((j, i, y[m], g[m], fit_scale))

    if _FIT_WORKERS > 1 and len(jobs) > 8:
        with ProcessPoolExecutor(max_workers=_FIT_WORKERS) as ex:
            results = ex.map(_fit_cell, jobs, chunksize=8)
            collected = list(results)
    else:
        collected = [_fit_cell(p) for p in jobs]

    for j, i, params in collected:
        if params is None:
            continue
        shape[j, i], loc0[j, i], dloc[j, i], scale0[j, i], dscale[j, i] = params
    return {"lats": lats, "lons": lons, "shape": shape, "loc0": loc0,
            "dloc": dloc, "scale0": scale0, "dscale": dscale}


# --------------------------------------------------------------------------
# ERA5 present grid
# --------------------------------------------------------------------------
def era5_present_grid(use_cache: bool = True) -> dict:
    cache = os.path.join(config.CACHE_DIR, f"grid_era5_{DOMAIN['name']}.json")
    if use_cache and os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)

    gmst_series = gmst.load_gmst_anomaly()
    ds = era5._open_reference()
    da = ds[config.ERA5_TAS_VAR]
    da.attrs.setdefault("units", "K")
    sub = metrics.subset_bbox(da, DOMAIN["bbox"])
    # canonical reference grid in a single -180..180 longitude frame
    daily = _to_180(metrics.to_celsius(metrics.daily_tasmax(sub))).load()

    out = {"present_gmst_anom": float(gmst.present_anomaly(gmst_series)),
           "metrics": {}}
    for mkey, mcfg in config.METRICS.items():
        amax = _annual_max_field(daily, mcfg["window_days"])
        fit = _fit_field(amax, gmst_series, config.OBS_FIT_SCALE_COVARIATE)
        out["lats"] = fit["lats"].tolist()
        out["lons"] = fit["lons"].tolist()
        out["metrics"][mkey] = {k: np.asarray(fit[k]).tolist()
                                for k in ("shape", "loc0", "dloc", "scale0", "dscale")}
    with open(cache, "w") as fh:
        json.dump(out, fh)
    return out


# --------------------------------------------------------------------------
# CMIP6 per-model grid change factors -> ensemble median
# --------------------------------------------------------------------------
def _model_gwl_cached(model: str) -> pd.Series:
    """Reuse the per-model GWL from the cmip6 raw cache if present, else compute."""
    raw = os.path.join(config.CACHE_DIR,
                       f"cmip6_raw_{config.PRIMARY_REGION}_{model}.json")
    if os.path.exists(raw):
        with open(raw) as fh:
            d = json.load(fh)
        return pd.Series({int(y): v for y, v in d["gwl"].items()})
    return cmip6.model_gwl(model)


def _model_grid(model: str, ref_lats, ref_lons, use_cache: bool = True) -> dict | None:
    """Per-model change factors on the reference grid.

    The model annual maxima are interpolated to the reference grid first, so the
    GEV is fit at the ~320 reference cells rather than at the model's native
    resolution (which can be many thousands of cells for a high-resolution
    model). The fit is therefore on the common target grid.
    """
    cache = os.path.join(config.CACHE_DIR, f"grid_cmip6_{DOMAIN['name']}_{model}.json")
    if use_cache and os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)
    try:
        gwl = _model_gwl_cached(model)
        parts = {m: [] for m in config.METRICS}
        for exp in config.CMIP6_EXPERIMENTS:
            z = cmip6._zstore(model, exp, config.CMIP6_TASMAX_TABLE, "tasmax",
                              config.CMIP6_MEMBER)
            if z is None:
                return None
            dam = cmip6._open(z)["tasmax"]
            dam.attrs.setdefault("units", "K")
            # skip downloading any post-2100 extension (some ssp585 runs reach
            # 2300); the change-factor fit is capped at 2100 regardless
            dam = dam.sel(time=slice(None, str(config.CMIP6_FIT_END_YEAR)))
            subm = _to_180(metrics.subset_bbox(dam, DOMAIN["bbox"]))
            la, lo = metrics.lat_name(subm), metrics.lon_name(subm)
            # sample the model to the reference cells (nearest) before loading,
            # so only ~320 cells are materialised rather than the full native
            # high-resolution field
            subm = subm.sel({la: ref_lats, lo: ref_lons}, method="nearest")
            daily = metrics.to_celsius(metrics.daily_tasmax(subm)).load()
            daily = daily.assign_coords({la: ref_lats, lo: ref_lons})
            for mkey, mcfg in config.METRICS.items():
                parts[mkey].append(_annual_max_field(daily, mcfg["window_days"]))
    except Exception as exc:  # noqa: BLE001
        print(f"  {model} grid read failed: {repr(exc)[:120]}")
        return None

    res = {"metrics": {}}
    for mkey in config.METRICS:
        amax = xr.concat(parts[mkey], dim="year").sortby("year")
        amax = amax.sel(year=amax["year"] <= config.CMIP6_FIT_END_YEAR)
        fit = _fit_field(amax, gwl, config.MODEL_FIT_SCALE_COVARIATE)
        res["metrics"][mkey] = {"dloc": np.asarray(fit["dloc"]).tolist(),
                                "dscale": np.asarray(fit["dscale"]).tolist()}
    with open(cache, "w") as fh:
        json.dump(res, fh)
    return res


def cmip6_change_factor_grid(models, ref_lats, ref_lons,
                             use_cache: bool = True) -> dict:
    """Ensemble-median per-cell dloc/dGWL and dscale/dGWL on the reference grid."""
    stacks = {m: {"dloc": [], "dscale": []} for m in config.METRICS}
    used = []
    for model in models:
        mg = _model_grid(model, ref_lats, ref_lons, use_cache=use_cache)
        if mg is None:
            continue
        used.append(model)
        for mkey in config.METRICS:
            stacks[mkey]["dloc"].append(np.array(mg["metrics"][mkey]["dloc"]))
            stacks[mkey]["dscale"].append(np.array(mg["metrics"][mkey]["dscale"]))
    out = {"models": used, "metrics": {}}
    for mkey in config.METRICS:
        dloc = np.nanmedian(np.stack(stacks[mkey]["dloc"]), axis=0)
        dscale = np.nanmedian(np.stack(stacks[mkey]["dscale"]), axis=0)
        out["metrics"][mkey] = {"dloc": dloc.tolist(), "dscale": dscale.tolist()}
    return out


# --------------------------------------------------------------------------
# Event field per cell (ERA5T + forecast blend, regridded to the reference grid)
# --------------------------------------------------------------------------
def _daily_field_window(open_fn, var, start, end) -> xr.DataArray:
    ds = open_fn()
    da = ds[var].sel(time=slice(start, end))
    da.attrs.setdefault("units", "K")
    sub = metrics.subset_bbox(da, DOMAIN["bbox"])
    return metrics.to_celsius(metrics.daily_tasmax(sub)).load()


def _to_180(da: xr.DataArray) -> xr.DataArray:
    """Express longitude in -180..180 and sort, so all products share a frame."""
    lo = metrics.lon_name(da)
    return da.assign_coords({lo: (((da[lo] + 180) % 360) - 180)}).sortby(lo)


def _forecast_field(date, cycle) -> xr.DataArray:
    """Sub-daily 2t over the domain for one cycle -> daily max field (degC)."""
    steps = [s for s in forecast.available_steps(date, cycle) if s <= 240]
    fields = [metrics.subset_bbox(forecast._fetch_2t_field(date, cycle, s),
                                  DOMAIN["bbox"]) for s in steps]
    sd = xr.concat(fields, dim="time").sortby("time")
    return metrics.to_celsius(metrics.daily_tasmax(sd))


def _domain_bias(obs: xr.DataArray, fc: xr.DataArray) -> float:
    """Domain-mean forecast-minus-ERA5T over coinciding days (0 if none)."""
    common = sorted(set(pd.to_datetime(obs["time"].values))
                    & set(pd.to_datetime(fc["time"].values)))
    if len(common) < 2:
        return 0.0
    diffs = [float(fc.sel(time=d).mean()) - float(obs.sel(time=d).mean())
             for d in common]
    return float(np.mean(diffs))


def event_field(ref_lats, ref_lons, era5t_ref_offset: float) -> tuple[dict, str]:
    """Per-cell event value (reference footing) for each metric on the ref grid.

    The blended 0.25 deg daily field is interpolated to the reference grid cell
    centres. Returns ``({metric: (lat, lon) numpy array}, peak_day)`` where the
    arrays are index-aligned with ref_lats / ref_lons and ``peak_day`` is the
    ISO date on which the domain-mean daily field peaked (the day the area
    average was hottest), so callers can record which day the event field came
    from.
    """
    today = blend.config_today()
    start = (today - dt.timedelta(days=20)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    obs = _to_180(_daily_field_window(
        lambda: xr.open_zarr(config.ERA5T_STORE, chunks={"time": 240},
                             storage_options={"token": "anon"}),
        config.ERA5_TAS_VAR, start, end))
    la, lo = metrics.lat_name(obs), metrics.lon_name(obs)
    # The ERA5T zarr time axis runs into the future with NaN placeholders, so the
    # raw time-max would report the *window end* as the last reanalysis day. ERA5T
    # fills the whole domain per timestep, so keep only days that actually carry
    # data; their max is the true last reanalysis day.
    has_data = obs.notnull().any(dim=[la, lo])
    obs = obs.isel(time=has_data.values)
    era5t_last = np.datetime64(pd.Timestamp(obs["time"].values.max()).normalize())
    print(f"[event_field] ERA5T reanalysis last day: "
          f"{pd.Timestamp(era5t_last).date()}")

    # Guard: when re-running for reanalysis, abort if the event peak is still in
    # the forecast part of the blend. Set FE_REQUIRE_ERA5T_THROUGH=YYYY-MM-DD
    # (e.g. the event peak day) to assert reanalysis has cleared it.
    require = os.environ.get("FE_REQUIRE_ERA5T_THROUGH")
    if require and era5t_last < np.datetime64(require.strip()):
        raise RuntimeError(
            f"ERA5T reanalysis only reaches {pd.Timestamp(era5t_last).date()}, "
            f"need >= {require.strip()}: the event peak is still forecast-sourced. "
            "Aborting so a forecast blend is not mistaken for reanalysis.")

    cycles = blend.choose_cycles(pd.Timestamp(era5t_last).date())
    fc = xr.concat([_to_180(_forecast_field(d, c)) for d, c in cycles], dim="time")
    fc = fc.groupby("time").first()  # newest-cycle-wins (newest concatenated first)
    fc = fc - _domain_bias(obs, fc)  # onto the ERA5T footing

    # the reference grid is already in the -180..180 frame
    obs_r = obs.interp({la: ref_lats, lo: ref_lons})
    fc_r = fc.interp({la: ref_lats, lo: ref_lons})
    fc_future = fc_r.sel(time=fc_r["time"] > era5t_last)
    blended = xr.concat([obs_r, fc_future], dim="time").sortby("time")
    blended = blended.groupby("time").first()  # dedupe overlap, keep ERA5T

    # domain-mean argmax: the day the area-average daily field peaked
    domain_mean = blended.mean(dim=[la, lo])
    peak_idx = int(domain_mean.argmax("time"))
    peak_day = str(pd.Timestamp(domain_mean["time"].values[peak_idx]).date())

    out = {}
    for mkey, mcfg in config.METRICS.items():
        series = blended
        if mcfg["window_days"] > 1:
            series = blended.rolling(time=mcfg["window_days"],
                                     min_periods=mcfg["window_days"]).mean()
        peak = series.max("time") - era5t_ref_offset  # reference footing
        out[mkey] = peak.transpose(la, lo).values
    return out, peak_day


# --------------------------------------------------------------------------
# Assemble grid JSON
# --------------------------------------------------------------------------
def _event_from_grid(path: str, ref_lats, ref_lons):
    """Reuse a previously computed event field (x_obs) from a grid JSON.

    Lets the GEV fields be recomputed (e.g. for new warming levels) without
    re-running the ERA5T + ECMWF forecast blend, which keeps the live event value
    fixed and avoids the GRIB toolchain. Cells are matched to the reference grid
    by nearest lat/lon; reference cells absent from the source stay NaN.
    """
    with open(path) as fh:
        g = json.load(fh)
    fields = {}
    for mkey in config.METRICS:
        arr = np.full((len(ref_lats), len(ref_lons)), np.nan)
        for c in g["metrics"][mkey]["cells"]:
            j = int(np.argmin(np.abs(ref_lats - c["lat"])))
            i = int(np.argmin(np.abs(ref_lons - c["lon"])))
            arr[j, i] = c["x_obs"]
        fields[mkey] = arr
    return fields, float(g.get("era5t_ref_offset", 0.0))


def build_grid(models=None, use_cache: bool = True, reuse_event: str | None = None) -> dict:
    models = models or cmip6.available_models()
    present = era5_present_grid(use_cache=use_cache)
    present_anom = present["present_gmst_anom"]
    ref_lats = np.array(present["lats"])
    ref_lons = np.array(present["lons"])
    cf = cmip6_change_factor_grid(models, ref_lats, ref_lons, use_cache=use_cache)

    event_peak_day = None
    if reuse_event:
        ev, off = _event_from_grid(reuse_event, ref_lats, ref_lons)
    else:
        from .live_value import era5t_ref_offset as _offset_fn
        off = _offset_fn(config.PRIMARY_REGION)
        ev, event_peak_day = event_field(ref_lats, ref_lons, off)

    # Historical (cooler) reference levels plus the future warming levels.
    levels = sorted(set(config.HISTORICAL_LEVELS) | set(config.WARMING_LEVELS))
    out = {
        "schema": "grid/0.1",
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "domain": DOMAIN["name"],
        "bbox": DOMAIN["bbox"],
        "grid_deg": 1.5,
        "present_gmst_anom": round(present_anom, 4),
        "warming_levels": [f"{g:.1f}" for g in levels],
        "n_models": len(cf["models"]),
        "era5t_ref_offset": round(off, 3),
        "event_peak_day": event_peak_day,
        "metrics": {},
    }

    for mkey in config.METRICS:
        pm = present["metrics"][mkey]
        shape = np.array(pm["shape"]); loc0 = np.array(pm["loc0"])
        dlocG = np.array(pm["dloc"]); scale0 = np.array(pm["scale0"])
        dscaleG = np.array(pm["dscale"])
        cfm = cf["metrics"][mkey]
        dloc_gwl = np.array(cfm["dloc"]); dscale_gwl = np.array(cfm["dscale"])
        xobs = ev[mkey]  # (nlat, nlon) index-aligned with ref_lats/ref_lons

        cells = []
        for j, lat in enumerate(ref_lats):
            for i, lon in enumerate(ref_lons):
                sh = shape[j, i]
                if not np.isfinite(sh) or not np.isfinite(xobs[j, i]):
                    continue
                loc_p = loc0[j, i] + dlocG[j, i] * present_anom
                scale_p = scale0[j, i] + dscaleG[j, i] * present_anom
                if not (np.isfinite(loc_p) and np.isfinite(scale_p)) or scale_p <= 0:
                    continue
                x = float(xobs[j, i])
                p_now = exceedance_prob(x, sh, loc_p, scale_p)
                rp = {}
                ratio = {}
                rl = {}  # temperature of an equally rare (present-return-period) event
                for g in levels:
                    delta = g - present_anom
                    loc_g = loc_p + (dloc_gwl[j, i] if np.isfinite(dloc_gwl[j, i]) else 0.0) * delta
                    scale_g = scale_p + (dscale_gwl[j, i] if np.isfinite(dscale_gwl[j, i]) else 0.0) * delta
                    scale_g = max(scale_g, 0.05)
                    p_g = exceedance_prob(x, sh, loc_g, scale_g)
                    rp[f"{g:.1f}"] = config.cap_rp(None if p_g <= 0 else 1.0 / p_g)
                    _r = (p_g / p_now) if p_now > 0 else None
                    ratio[f"{g:.1f}"] = (round(_r, 3)
                                         if _r is not None and np.isfinite(_r)
                                         else None)
                    # The value that keeps the present return period (1/p_now)
                    # under the warmed distribution: an equally rare event, hotter.
                    # Degenerate when the event is common now (p_now ~ 1 -> the
                    # "return level" is the lower tail, -inf); emit null there.
                    rl_g = (return_level(1.0 / p_now, sh, loc_g, scale_g)
                            if 0 < p_now < 1 else float("nan"))
                    rl[f"{g:.1f}"] = round(rl_g, 2) if np.isfinite(rl_g) else None
                cells.append({
                    "lat": round(float(lat), 3), "lon": round(float(lon), 3),
                    "x_obs": round(x, 2),
                    "present_rp": config.cap_rp(None if p_now <= 0 else 1.0 / p_now),
                    "present_p": round(p_now, 5),
                    "rp": rp, "ratio": ratio, "rl": rl,
                })
        out["metrics"][mkey] = {"name": config.METRICS[mkey]["name"],
                                "units": config.METRICS[mkey]["units"],
                                "cells": cells}
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Build the gridded probability map.")
    ap.add_argument("--max-models", type=int, default=None)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--reuse-event", default=None,
                    help="path to an existing grid JSON whose event field (x_obs) "
                         "is reused instead of re-running the forecast blend")
    ap.add_argument("--out", default=os.path.join(config.OUTPUT_DIR,
                                                  "grid_europe.json"))
    args = ap.parse_args()
    models = cmip6.available_models()
    if args.max_models:
        models = models[:args.max_models]
    grid = build_grid(models=models, use_cache=not args.no_cache,
                      reuse_event=args.reuse_event)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(grid, fh)
    n = len(grid["metrics"]["regional_mean_tasmax"]["cells"])
    print(f"wrote {args.out}: {n} cells, {grid['n_models']} models")


if __name__ == "__main__":
    main()
