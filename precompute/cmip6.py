"""CMIP6 change factors: per-degree GEV response from the model ensemble.

The models are confined to what they are good at: the response of the extreme
distribution per degree of additional global warming. For each model we:

  1. build the regional annual block-maxima series of each metric over
     historical + ssp585 (daily tasmax, subset to the region);
  2. build the model's own global warming level GWL(year): the 20-year running
     mean of its annual global-mean tas (GSAT) anomaly vs 1850-1900;
  3. fit a non-stationary GEV to the maxima with GWL as the covariate, giving
     that model's dloc/dGWL and dscale/dGWL.

The ensemble median of those slopes (with 17th/83rd percentile spread) is the
change factor applied to the obs-anchored present-day GEV.
"""

from __future__ import annotations

import json
import os
import warnings

import numpy as np
import pandas as pd
import xarray as xr

from . import config, metrics
from .gev import fit_nonstationary

warnings.filterwarnings("ignore", category=FutureWarning)

_CATALOG = None


def _catalog():
    global _CATALOG
    if _CATALOG is None:
        import intake
        _CATALOG = intake.open_esm_datastore(config.CMIP6_CATALOG)
    return _CATALOG


def _zstore(model, experiment, table, variable, member):
    df = _catalog().df
    sel = df[(df.source_id == model) & (df.experiment_id == experiment)
             & (df.table_id == table) & (df.variable_id == variable)
             & (df.member_id == member)]
    if len(sel) == 0:
        return None
    return sel.zstore.values[0]


def available_models() -> list[str]:
    """Models with the required daily tasmax for historical and ssp585."""
    df = _catalog().df
    d = df[(df.table_id == config.CMIP6_TASMAX_TABLE)
           & (df.variable_id == "tasmax")
           & (df.member_id == config.CMIP6_MEMBER)]
    sets = [set(d[d.experiment_id == e].source_id) for e in config.CMIP6_EXPERIMENTS]
    common = set.intersection(*sets)
    return sorted(common)


def _open(zstore) -> xr.Dataset:
    return xr.open_zarr(zstore, storage_options={"token": "anon"}, chunks={})


# --------------------------------------------------------------------------
# Per-model warming-level series GWL(year)
# --------------------------------------------------------------------------
def _annual_global_mean_tas(zstore) -> pd.Series:
    ds = _open(zstore)
    ta = ds["tas"]
    la = metrics.lat_name(ta)
    w = np.cos(np.deg2rad(ta[la]))
    gm = ta.weighted(w).mean(dim=(metrics.lat_name(ta), metrics.lon_name(ta)),
                             skipna=True)
    ann = gm.groupby("time.year").mean().load()
    return pd.Series(ann.values, index=ann["year"].values.astype(int))


def model_gwl(model: str) -> pd.Series:
    """GWL(year): 20-year running mean of annual GSAT anomaly vs 1850-1900."""
    parts = []
    for exp in config.CMIP6_EXPERIMENTS:
        z = _zstore(model, exp, config.CMIP6_TAS_TABLE, "tas", config.CMIP6_MEMBER)
        if z is None:
            raise FileNotFoundError(f"{model} {exp} Amon tas missing")
        parts.append(_annual_global_mean_tas(z))
    gsat = pd.concat(parts).sort_index()
    gsat = gsat[~gsat.index.duplicated(keep="first")]
    b0, b1 = config.GMST_BASELINE
    gsat = gsat - gsat.loc[b0:b1].mean()
    return gsat.rolling(20, center=True, min_periods=20).mean().dropna()


# --------------------------------------------------------------------------
# Per-model regional annual block maxima
# --------------------------------------------------------------------------
def model_annual_maxima(model: str, region_key: str) -> dict[str, pd.Series]:
    bbox = config.REGIONS[region_key]["bbox"]
    series_by_metric: dict[str, list[pd.Series]] = {m: [] for m in config.METRICS}
    for exp in config.CMIP6_EXPERIMENTS:
        z = _zstore(model, exp, config.CMIP6_TASMAX_TABLE, "tasmax",
                    config.CMIP6_MEMBER)
        if z is None:
            raise FileNotFoundError(f"{model} {exp} day tasmax missing")
        ds = _open(z)
        da = ds["tasmax"]
        da.attrs.setdefault("units", "K")
        sub = metrics.subset_bbox(da, bbox)
        daily_regmean = metrics.daily_regional_mean(sub)
        for mkey, mcfg in config.METRICS.items():
            series_by_metric[mkey].append(
                metrics.annual_max_for_window(daily_regmean, mcfg["window_days"]))
    return {m: pd.concat(parts).sort_index() for m, parts in series_by_metric.items()}


# --------------------------------------------------------------------------
# Per-model cache and change-factor fit
# --------------------------------------------------------------------------
def _model_cache_path(model: str, region_key: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"cmip6_raw_{region_key}_{model}.json")


def model_raw_series(model: str, region_key: str, use_cache: bool = True) -> dict:
    """Per-model raw GWL and annual-maxima series, cached (the expensive reads).

    {"gwl": {year: gwl}, "amax": {metric: {year: value}}}
    """
    cache = _model_cache_path(model, region_key)
    if use_cache and os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)
    gwl = model_gwl(model)
    amax = model_annual_maxima(model, region_key)
    raw = {
        "gwl": {int(y): float(v) for y, v in gwl.items()},
        "amax": {m: {int(y): float(v) for y, v in s.items()}
                 for m, s in amax.items()},
    }
    with open(cache, "w") as fh:
        json.dump(raw, fh, indent=2)
    return raw


def process_model(model: str, region_key: str, use_cache: bool = True) -> dict:
    """Return per-model change factors for each metric (fit on cached raw series).

    {metric: {dloc_dGWL, dscale_dGWL, shape, n, gwl_min, gwl_max, converged}}
    """
    raw = model_raw_series(model, region_key, use_cache=use_cache)
    gwl = pd.Series({int(y): v for y, v in raw["gwl"].items()})
    amax = {m: pd.Series({int(y): v for y, v in d.items()})
            for m, d in raw["amax"].items()}
    end_year = config.CMIP6_FIT_END_YEAR
    result: dict[str, dict] = {}
    for mkey, series in amax.items():
        series = series[series.index <= end_year]
        years = series.index.values
        g = gwl.reindex(years).values
        mask = np.isfinite(g)
        ys, gs = series.values[mask], g[mask]
        if ys.size < 40:
            continue
        fit = fit_nonstationary(ys, gs, covariate_name="GWL",
                                fit_scale_covariate=config.MODEL_FIT_SCALE_COVARIATE)
        result[mkey] = {
            "dloc_dGWL": float(fit.dloc),
            "dscale_dGWL": float(fit.dscale),
            "shape": float(fit.shape),
            "n": int(fit.n),
            "gwl_min": float(np.nanmin(gs)),
            "gwl_max": float(np.nanmax(gs)),
            "converged": bool(fit.converged),
        }
    return result


def _percentile(values, q):
    return float(np.percentile(values, q)) if len(values) else None


def ensemble_change_factors(region_key: str, models: list[str],
                            use_cache: bool = True) -> dict:
    """Aggregate per-model slopes into ensemble change factors per metric."""
    per_metric: dict[str, dict[str, list]] = {
        m: {"dloc": [], "dscale": [], "shape": [], "models": []}
        for m in config.METRICS}
    failed = []
    for model in models:
        try:
            res = process_model(model, region_key, use_cache=use_cache)
        except Exception as exc:  # noqa: BLE001 - log and skip a bad model
            failed.append((model, repr(exc)[:160]))
            continue
        for mkey, vals in res.items():
            per_metric[mkey]["dloc"].append(vals["dloc_dGWL"])
            per_metric[mkey]["dscale"].append(vals["dscale_dGWL"])
            per_metric[mkey]["shape"].append(vals["shape"])
            per_metric[mkey]["models"].append(model)

    out = {"by_metric": {}, "failed": failed}
    for mkey, acc in per_metric.items():
        dloc = np.array(acc["dloc"])
        dscale = np.array(acc["dscale"])
        out["by_metric"][mkey] = {
            "dloc_dGWL": _percentile(dloc, 50),
            "dscale_dGWL": _percentile(dscale, 50),
            "source": "CMIP6 ensemble median (per-model GWL covariate NS-GEV)",
            "spread": {
                "p17": _percentile(dloc, 17),
                "p83": _percentile(dloc, 83),
                "dscale_p17": _percentile(dscale, 17),
                "dscale_p83": _percentile(dscale, 83),
                "n_models": int(len(acc["models"])),
            },
            "models": acc["models"],
            "shape_median": _percentile(np.array(acc["shape"]), 50),
        }
    return out


if __name__ == "__main__":
    region = config.PRIMARY_REGION
    models = available_models()
    print("available models:", len(models))
    # validate on two models
    for m in models[:2]:
        res = process_model(m, region, use_cache=True)
        print(m, {k: {kk: round(vv, 3) if isinstance(vv, float) else vv
                      for kk, vv in v.items()} for k, v in res.items()})
