"""ERA5 reference: annual block maxima and the obs-anchored present GEV.

Reads the ARCO-ERA5 reference store anonymously, subsets a region, builds the
daily regional-mean tasmax once, and derives the annual block-maxima series for
each metric. The obs-anchored present-day GEV is the non-stationary fit of those
maxima against the observed GMST anomaly, evaluated at the present anomaly.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import xarray as xr

from . import config, gmst, metrics
from .gev import fit_nonstationary, fit_stationary


def _open_reference() -> xr.Dataset:
    return xr.open_zarr(config.ERA5_REFERENCE_STORE,
                        chunks={"time": 2400},
                        storage_options={"token": "anon"})


def _amax_cache_path(region_key: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"era5_amax_{region_key}.json")


def annual_maxima(region_key: str, use_cache: bool = True) -> dict[str, pd.Series]:
    """Annual block-maxima series for every metric, for one region.

    Returns {metric_key: Series(indexed by year)}. Cached to disk as JSON.
    """
    cache = _amax_cache_path(region_key)
    if use_cache and os.path.exists(cache):
        with open(cache) as fh:
            raw = json.load(fh)
        return {m: pd.Series({int(y): v for y, v in d.items()})
                for m, d in raw.items()}

    bbox = config.REGIONS[region_key]["bbox"]
    ds = _open_reference()
    da = ds[config.ERA5_TAS_VAR]
    da.attrs.setdefault("units", "K")
    sub = metrics.subset_bbox(da, bbox)
    daily_regmean = metrics.daily_regional_mean(sub)

    out: dict[str, pd.Series] = {}
    for mkey, mcfg in config.METRICS.items():
        out[mkey] = metrics.annual_max_for_window(
            daily_regmean, mcfg["window_days"])

    with open(cache, "w") as fh:
        json.dump({m: {int(y): float(v) for y, v in s.items()}
                   for m, s in out.items()}, fh, indent=2)
    return out


def present_gev(amax: pd.Series, gmst_anom: pd.Series, present_anom: float):
    """Fit the obs-anchored non-stationary GEV and evaluate it at the present.

    Returns (present_params, ns_fit, stationary_fit) where present_params is the
    dict stored under ``gev_present`` in the lookup.
    """
    years = amax.index.values
    g = gmst_anom.reindex(years).values
    ns = fit_nonstationary(amax.values, g, covariate_name="GMST",
                           fit_scale_covariate=config.OBS_FIT_SCALE_COVARIATE)
    stat = fit_stationary(amax.values)
    shape, loc, scale = ns.params_at(present_anom)
    present_params = {
        "loc": round(loc, 4),
        "scale": round(scale, 4),
        "shape": round(shape, 4),
        "covariate": "GMST",
        "dloc_dGMST": round(ns.dloc, 4),
        "ref_gmst_anom": round(present_anom, 4),
    }
    return present_params, ns, stat


if __name__ == "__main__":
    region = config.PRIMARY_REGION
    g = gmst.load_gmst_anomaly()
    present = gmst.present_anomaly(g)
    am = annual_maxima(region)
    for mkey, s in am.items():
        params, ns, stat = present_gev(s, g, present)
        print(f"[{region}/{mkey}] n={len(s)} "
              f"range={s.min():.1f}..{s.max():.1f} degC")
        print("   present GEV:", params)
        print(f"   dloc/dGMST={ns.dloc:.3f} degC/degC  shape={ns.shape:.3f} "
              f"stationary loc={stat.loc:.2f} scale={stat.scale:.2f}")
