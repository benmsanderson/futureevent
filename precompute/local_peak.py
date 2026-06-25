"""Local-peak (TXx) metric: the France-peak headline + France-only 0.25 deg map.

This is the heavy follow-up that gives the tool a *local* peak-temperature
representation (station-scale ~40-44 degC) alongside the existing France-wide
average (~31 degC). The headline ``france_peak`` is the single hottest
metropolitan-France 0.25 deg cell for the event, its present return period, and
how that rarity shifts along the warming axis.

Method (parallels grid.py, but at 0.25 deg off ERA5T rather than 1.5 deg off the
conservative reference store):

  - present: per-cell non-stationary GEV of the cached ERA5T 0.25 deg annual TXx
    (``era5t_hires``), GMST covariate, evaluated at the present GMST anomaly;
  - future: CMIP6 ensemble-median per-cell change factors (dloc/dGWL,
    dscale/dGWL), the coarse model fields sampled to the 0.25 deg grid -- a
    documented approximation (coarse change factor on a fine present fit);
  - event: the ERA5T + ECMWF forecast blend kept native at 0.25 deg over France
    (``grid.event_field``). Because the local_txx climatology is itself ERA5T
    0.25 deg, the event sits on that same footing -- NO reference offset (the
    1.5 deg pipeline needs one; this one does not).

Metropolitan France is isolated with a Natural Earth France mask (regionmask),
so the peak search excludes Spain/Italy/sea inside the bbox.

``local_txx`` is deliberately kept out of ``config.METRICS`` so the existing
regional point-lookup and grid pipelines emit byte-identical output.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os

import numpy as np
import xarray as xr

from . import config, cmip6, era5t_hires, gmst, grid, metrics
from .gev import exceedance_prob, return_level

DOMAIN = era5t_hires.DOMAIN  # {"name": "france", "bbox": france bbox}
# 1991-2020 gives 30 annual maxima; a cell needs most of them to be fit.
MIN_YEARS_LOCAL = 25
# A handful of major metropolitan-France cities to label the peak ("near X").
_CITIES = {
    "Paris": (48.86, 2.35), "Lyon": (45.76, 4.84), "Marseille": (43.30, 5.37),
    "Toulouse": (43.60, 1.44), "Bordeaux": (44.84, -0.58), "Nantes": (47.22, -1.55),
    "Lille": (50.63, 3.06), "Strasbourg": (48.58, 7.75), "Nice": (43.70, 7.27),
    "Montpellier": (43.61, 3.88), "Nimes": (43.84, 4.36), "Avignon": (43.95, 4.81),
    "Clermont-Ferrand": (45.78, 3.08), "Dijon": (47.32, 5.04), "Tours": (47.39, 0.69),
    "Orleans": (47.90, 1.90), "Limoges": (45.83, 1.26), "Pau": (43.30, -0.37),
}


# --------------------------------------------------------------------------
# Present 0.25 deg local_txx GEV climatology
# --------------------------------------------------------------------------
def present_local_gev(period=era5t_hires.CLIMATOLOGY_PERIOD,
                      use_cache: bool = True) -> tuple:
    """Per-cell present non-stationary GEV from the cached ERA5T annual TXx.

    Returns (present_gmst_anom, fit) where fit has lats/lons and per-cell
    shape/loc0/dloc/scale0/dscale arrays (grid._fit_field layout).
    """
    amax = era5t_hires.annual_txx_field(period=period, use_cache=use_cache)
    g = gmst.load_gmst_anomaly()
    present_anom = float(gmst.present_anomaly(g))
    fit = grid._fit_field(amax, g, config.OBS_FIT_SCALE_COVARIATE,
                          min_years=MIN_YEARS_LOCAL)
    return present_anom, fit


# --------------------------------------------------------------------------
# CMIP6 change factors at 0.25 deg (coarse model -> fine grid, documented approx)
# --------------------------------------------------------------------------
def _model_local_grid(model: str, ref_lats, ref_lons,
                      use_cache: bool = True) -> dict | None:
    """Per-model dloc/dGWL, dscale/dGWL for local_txx on the 0.25 deg grid.

    The coarse model tasmax is sampled (nearest) to the 0.25 deg cells before the
    per-cell NS-GEV fit, so a model's few France gridcells are replicated across
    the fine cells they cover. Mirrors grid._model_grid for a single window=1
    metric over the France domain; caches per model so a killed run resumes.
    """
    cache = os.path.join(config.CACHE_DIR,
                         f"cmip6_local_{DOMAIN['name']}_{model}.json")
    if use_cache and os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)
    try:
        gwl = grid._model_gwl_cached(model)
        parts = []
        for exp in config.CMIP6_EXPERIMENTS:
            z = cmip6._zstore(model, exp, config.CMIP6_TASMAX_TABLE, "tasmax",
                              config.CMIP6_MEMBER)
            if z is None:
                return None
            dam = cmip6._open(z)["tasmax"]
            dam.attrs.setdefault("units", "K")
            dam = dam.sel(time=slice(None, str(config.CMIP6_FIT_END_YEAR)))
            subm = grid._to_180(metrics.subset_bbox(dam, DOMAIN["bbox"]))
            la, lo = metrics.lat_name(subm), metrics.lon_name(subm)
            subm = subm.sel({la: ref_lats, lo: ref_lons}, method="nearest")
            daily = metrics.to_celsius(metrics.daily_tasmax(subm)).load()
            daily = daily.assign_coords({la: ref_lats, lo: ref_lons})
            parts.append(grid._annual_max_field(daily, window_days=1))
    except Exception as exc:  # noqa: BLE001 - log and skip a bad model
        print(f"  {model} local grid read failed: {repr(exc)[:120]}")
        return None

    amax = xr.concat(parts, dim="year").sortby("year")
    amax = amax.sel(year=amax["year"] <= config.CMIP6_FIT_END_YEAR)
    # ~150-250 model years -> the default min_years (40) is appropriate here.
    fit = grid._fit_field(amax, gwl, config.MODEL_FIT_SCALE_COVARIATE)
    res = {"dloc": np.asarray(fit["dloc"]).tolist(),
           "dscale": np.asarray(fit["dscale"]).tolist()}
    with open(cache, "w") as fh:
        json.dump(res, fh)
    return res


def local_change_factors(models, ref_lats, ref_lons,
                         use_cache: bool = True) -> dict:
    """Ensemble-median per-cell dloc/dGWL and dscale/dGWL at 0.25 deg."""
    dloc_stack, dscale_stack, used = [], [], []
    for model in models:
        mg = _model_local_grid(model, ref_lats, ref_lons, use_cache=use_cache)
        if mg is None:
            continue
        used.append(model)
        dloc_stack.append(np.array(mg["dloc"]))
        dscale_stack.append(np.array(mg["dscale"]))
    return {
        "models": used,
        "dloc": np.nanmedian(np.stack(dloc_stack), axis=0),
        "dscale": np.nanmedian(np.stack(dscale_stack), axis=0),
    }


# --------------------------------------------------------------------------
# Metropolitan-France mask
# --------------------------------------------------------------------------
def france_mask(ref_lats, ref_lons) -> np.ndarray:
    """Boolean (nlat, nlon) mask: True for metropolitan-France 0.25 deg cells.

    Uses the Natural Earth France polygon; overseas territories fall outside the
    France bbox so the mask is metropolitan-only (Corsica included).
    """
    import regionmask
    ne = regionmask.defined_regions.natural_earth_v5_0_0.countries_50
    m = ne.mask(np.asarray(ref_lons), np.asarray(ref_lats))
    return (m.values == ne.map_keys("France"))


def _nearest_place(lat: float, lon: float, max_deg: float = 0.7):
    best, bestd = None, max_deg
    for name, (cy, cx) in _CITIES.items():
        d = ((lat - cy) ** 2 + (lon - cx) ** 2) ** 0.5
        if d < bestd:
            best, bestd = name, d
    return f"near {best}" if best else None


# --------------------------------------------------------------------------
# Event field at 0.25 deg over France
# --------------------------------------------------------------------------
def _event_field_local(ref_lats, ref_lons, reuse_event: str | None):
    """Per-cell event TXx (degC, ERA5T 0.25 deg footing) over the France grid.

    local_txx climatology IS ERA5T 0.25 deg, so the event sits on that footing
    directly: pass offset 0.0 to grid.event_field (the forecast is still bias-
    corrected onto ERA5T inside event_field). ``reuse_event`` reloads a prior
    hi-res grid JSON's x_obs to skip the live forecast blend.
    """
    if reuse_event and os.path.exists(reuse_event):
        with open(reuse_event) as fh:
            g = json.load(fh)
        arr = np.full((len(ref_lats), len(ref_lons)), np.nan)
        for c in g["metrics"]["local_txx"]["cells"]:
            j = int(np.argmin(np.abs(np.array(ref_lats) - c["lat"])))
            i = int(np.argmin(np.abs(np.array(ref_lons) - c["lon"])))
            arr[j, i] = c["x_obs"]
        return arr, g.get("event_peak_day")
    # window=1 (regional_mean_tasmax key) gives the per-cell peak daily max.
    ev = grid.event_field(np.asarray(ref_lats), np.asarray(ref_lons),
                          era5t_ref_offset=0.0)
    return ev["regional_mean_tasmax"], None


# --------------------------------------------------------------------------
# Assemble france_peak + France-only 0.25 deg grid
# --------------------------------------------------------------------------
def build_local_peak(models=None, use_cache: bool = True,
                     reuse_event: str | None = None,
                     event_peak_day: str | None = None) -> dict:
    models = models or cmip6.available_models()
    present_anom, fit = present_local_gev(use_cache=use_cache)
    ref_lats = np.asarray(fit["lats"])
    ref_lons = np.asarray(fit["lons"])
    cf = local_change_factors(models, ref_lats, ref_lons, use_cache=use_cache)
    xobs, ev_peak_day = _event_field_local(ref_lats, ref_lons, reuse_event)
    event_peak_day = event_peak_day or ev_peak_day
    mask = france_mask(ref_lats, ref_lons)

    shape = np.array(fit["shape"]); loc0 = np.array(fit["loc0"])
    dloc = np.array(fit["dloc"]); scale0 = np.array(fit["scale0"])
    dscale = np.array(fit["dscale"])
    cf_dloc = cf["dloc"]; cf_dscale = cf["dscale"]
    levels = sorted(set(config.HISTORICAL_LEVELS) | set(config.WARMING_LEVELS))

    cells = []
    peak = None  # (value, lat, lon, present_block, warming_block)
    for j, lat in enumerate(ref_lats):
        for i, lon in enumerate(ref_lons):
            if not mask[j, i]:
                continue
            sh = shape[j, i]
            if not np.isfinite(sh) or not np.isfinite(xobs[j, i]):
                continue
            loc_p = loc0[j, i] + dloc[j, i] * present_anom
            scale_p = scale0[j, i] + dscale[j, i] * present_anom
            if not (np.isfinite(loc_p) and np.isfinite(scale_p)) or scale_p <= 0:
                continue
            x = float(xobs[j, i])
            p_now = exceedance_prob(x, sh, loc_p, scale_p)
            rp, ratio, rl, levblock = {}, {}, {}, {}
            for gwl in levels:
                delta = gwl - present_anom
                lg = loc_p + (cf_dloc[j, i] if np.isfinite(cf_dloc[j, i]) else 0.0) * delta
                sg = scale_p + (cf_dscale[j, i] if np.isfinite(cf_dscale[j, i]) else 0.0) * delta
                sg = max(sg, 0.05)
                p_g = exceedance_prob(x, sh, lg, sg)
                key = f"{gwl:.1f}"
                rp[key] = None if p_g <= 0 else round(1.0 / p_g, 2)
                ratio[key] = round(p_g / p_now, 3) if p_now > 0 else None
                rl_g = (return_level(1.0 / p_now, sh, lg, sg)
                        if 0 < p_now < 1 else float("nan"))
                rl[key] = round(rl_g, 2) if np.isfinite(rl_g) else None
                levblock[key] = {
                    "return_period_years": rp[key],
                    "exceedance_prob": round(p_g, 6),
                    "probability_ratio_vs_present": ratio[key],
                }
            cell = {
                "lat": round(float(lat), 3), "lon": round(float(lon), 3),
                "x_obs": round(x, 2),
                "present_rp": None if p_now <= 0 else round(1.0 / p_now, 2),
                "present_p": round(p_now, 6),
                "rp": rp, "ratio": ratio, "rl": rl,
            }
            cells.append(cell)
            if peak is None or x > peak[0]:
                peak = (x, float(lat), float(lon), p_now, levblock)

    if peak is None:
        raise RuntimeError("no valid metropolitan-France cell found for france_peak")

    x, plat, plon, p_now, levblock = peak
    france_peak = {
        "metric": "local_txx",
        "value": round(x, 2),
        "lat": round(plat, 3), "lon": round(plon, 3),
        "nearest_place": _nearest_place(plat, plon),
        "peak_day": event_peak_day,
        "present": {
            "return_period_years": None if p_now <= 0 else round(1.0 / p_now, 2),
            "exceedance_prob": round(p_now, 6),
            "gmst_anom": round(present_anom, 4),
        },
        "warming_levels": levblock,
        "note": ("hottest single metropolitan-France 0.25 deg ERA5T cell; "
                 "ERA5 gridbox values run ~1-2 degC below the hottest station "
                 "(known cool bias)."),
    }
    grid_out = {
        "schema": "grid_hires/0.1",
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "domain": DOMAIN["name"],
        "bbox": DOMAIN["bbox"],
        "grid_deg": 0.25,
        "present_gmst_anom": round(present_anom, 4),
        "warming_levels": [f"{g:.1f}" for g in levels],
        "n_models": len(cf["models"]),
        "climatology_period": list(era5t_hires.CLIMATOLOGY_PERIOD),
        "event_peak_day": event_peak_day,
        "metrics": {"local_txx": {
            "name": "Local daily maximum temperature (per-cell TXx)",
            "units": "degC", "cells": cells}},
    }
    return {"france_peak": france_peak, "grid": grid_out}


def _merge_into_live(france_peak: dict, live_path: str):
    """Add france_peak to live_<region>.json, leaving everything else intact."""
    with open(live_path) as fh:
        live = json.load(fh)
    # default the peak_day to the event's regional peak day if not set
    if not france_peak.get("peak_day"):
        rm = live.get("metrics", {}).get("regional_mean_tasmax", {})
        france_peak["peak_day"] = rm.get("peak_day")
    live["france_peak"] = france_peak
    # fail loud on any non-finite that would break JSON.parse in the browser
    with open(live_path, "w") as fh:
        json.dump(live, fh, indent=2, allow_nan=False)


def main():
    ap = argparse.ArgumentParser(
        description="Build the local-peak (TXx) france_peak headline + hi-res map.")
    ap.add_argument("--max-models", type=int, default=None)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--reuse-event", default=None,
                    help="path to a prior grid_france_hires.json whose event "
                         "field (x_obs) is reused instead of the forecast blend")
    ap.add_argument("--live", default=os.path.join(config.OUTPUT_DIR,
                                                   "live_france.json"))
    ap.add_argument("--grid-out", default=os.path.join(config.OUTPUT_DIR,
                                                       "grid_france_hires.json"))
    args = ap.parse_args()
    models = cmip6.available_models()
    if args.max_models:
        models = models[:args.max_models]
    res = build_local_peak(models=models, use_cache=not args.no_cache,
                           reuse_event=args.reuse_event)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    with open(args.grid_out, "w") as fh:
        json.dump(res["grid"], fh, allow_nan=False)
    if os.path.exists(args.live):
        _merge_into_live(res["france_peak"], args.live)
    fp = res["france_peak"]
    print(f"france_peak: {fp['value']} degC {fp['nearest_place']} "
          f"({fp['lat']}, {fp['lon']}), present 1-in-"
          f"{fp['present']['return_period_years']} yr")
    print(f"wrote {args.grid_out}: "
          f"{len(res['grid']['metrics']['local_txx']['cells'])} France cells, "
          f"{res['grid']['n_models']} models")


if __name__ == "__main__":
    main()
