"""Assemble the lookup JSON: the deliverable of this session.

Wires together the obs-anchored present GEV (ERA5 + observed GMST) and the
CMIP6 ensemble change factors, applies the change factors as per-degree deltas
from the present, and writes a populated lookup matching the agreed schema.

Future-level parameters are built as deltas from the obs-anchored present:
    loc(g)   = loc_present   + median(dloc/dGWL)   * (g - present_gmst_anom)
    scale(g) = scale_present + median(dscale/dGWL) * (g - present_gmst_anom)
    shape(g) = shape_present                        (held constant)
so the future tail inherits the observation-anchored baseline and only the
CMIP6-derived response per degree moves it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os

from . import config, cmip6, era5, gmst


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _warming_level_params(present_params, cf_metric, present_anom):
    """Build {gwl: {loc, scale, shape}} from present params + change factors."""
    loc_p = present_params["loc"]
    scale_p = present_params["scale"]
    shape_p = present_params["shape"]
    dloc = cf_metric["dloc_dGWL"]
    dscale = cf_metric["dscale_dGWL"]
    levels = {}
    for g in config.WARMING_LEVELS:
        delta = g - present_anom
        scale_g = scale_p + (dscale or 0.0) * delta
        scale_g = max(scale_g, 0.05)  # guard positivity at low/high levels
        levels[f"{g:.1f}"] = {
            "loc": round(loc_p + (dloc or 0.0) * delta, 4),
            "scale": round(scale_g, 4),
            "shape": round(shape_p, 4),
        }
    return levels


def build(region_keys=None, models=None, use_cache=True) -> dict:
    region_keys = region_keys or [config.PRIMARY_REGION]
    models = models or cmip6.available_models()

    gmst_series = gmst.load_gmst_anomaly()
    present_anom = gmst.present_anomaly(gmst_series)

    lookup = {
        "metadata": {
            "version": config.__dict__.get("__version__", "0.1.0"),
            "generated": _utc_now_iso(),
            "datasets": {
                "reference": config.ERA5_REFERENCE_LABEL,
                "reference_period": f"{config.ERA5_REF_PERIOD[0]}-"
                                    f"{config.ERA5_REF_PERIOD[1]}",
                "event_value_source": config.ERA5T_LABEL,
                "scaling": "CMIP6 daily tasmax, historical+ssp585, member "
                           f"{config.CMIP6_MEMBER}",
                "scaling_gwl_from": "CMIP6 monthly tas (Amon), per-model GSAT "
                                    "20-yr running mean vs 1850-1900",
            },
            "gwl_baseline": config.GWL_BASELINE,
            "gmst_covariate_source": config.GMST_SOURCE_LABEL,
            "present_gmst_anom": round(present_anom, 4),
            "block": "annual maxima",
            "gev_convention": "scipy.stats.genextreme; shape == c == -xi. "
                              "CDF F(x)=exp(-(1-c*z)^(1/c)), z=(x-loc)/scale; "
                              "c=0 -> Gumbel. Return period = 1/(1-F).",
            "metrics_defined": {k: v["name"] for k, v in config.METRICS.items()},
            "offsets_note": (
                "Reference GEV uses 1.5 deg 6-hourly ERA5 (daily max from "
                "6-hourly sampling biases slightly low); the live event value "
                "uses 0.25 deg hourly ERA5T. Apply the documented product "
                "offset before evaluating a live value."),
            "notes": "obs-anchored NS-GEV present; CMIP6 change-factors for "
                     "future; per-model GWL covariate fit; shape held constant "
                     "across warming levels.",
        },
        "regions": {},
    }

    version = "0.1.0"
    lookup["metadata"]["version"] = version

    for region_key in region_keys:
        rcfg = config.REGIONS[region_key]
        amax = era5.annual_maxima(region_key, use_cache=use_cache)
        cf = cmip6.ensemble_change_factors(region_key, models, use_cache=use_cache)

        region_node = {
            "name": rcfg["name"],
            "bbox": rcfg["bbox"],
            "metrics": {},
        }

        # cross-check obs sensitivity vs ensemble per-degree scaling
        crosschecks = {}

        for mkey, mcfg in config.METRICS.items():
            present_params, ns, stat = era5.present_gev(
                amax[mkey], gmst_series, present_anom)
            cf_metric = cf["by_metric"][mkey]

            wl = _warming_level_params(present_params, cf_metric, present_anom)

            obs_sens = present_params["dloc_dGMST"]
            cmip_sens = cf_metric["dloc_dGWL"]
            flagged = None
            if obs_sens and cmip_sens:
                ratio = obs_sens / cmip_sens
                flagged = (ratio > config.SENSITIVITY_FLAG_RATIO
                           or ratio < 1.0 / config.SENSITIVITY_FLAG_RATIO)
                crosschecks[mkey] = {
                    "obs_dloc_dGMST": round(obs_sens, 4),
                    "cmip_dloc_dGWL": round(cmip_sens, 4),
                    "ratio": round(ratio, 3),
                    "flagged_disagreement": bool(flagged),
                }

            region_node["metrics"][mkey] = {
                "name": mcfg["name"],
                "units": mcfg["units"],
                "gev_present": present_params,
                "fit_diagnostics": {
                    "n_years": int(ns.n),
                    "nllf": round(ns.nllf, 3),
                    "aic": round(ns.aic, 3),
                    "converged": bool(ns.converged),
                    "stationary_loc": round(stat.loc, 4),
                    "stationary_scale": round(stat.scale, 4),
                    "stationary_shape": round(stat.shape, 4),
                },
                "scaling_per_gwl": {
                    "dloc_dGWL": (round(cf_metric["dloc_dGWL"], 4)
                                  if cf_metric["dloc_dGWL"] is not None else None),
                    "dscale_dGWL": (round(cf_metric["dscale_dGWL"], 4)
                                    if cf_metric["dscale_dGWL"] is not None else None),
                    "source": cf_metric["source"],
                    "spread": cf_metric["spread"],
                    "models": cf_metric["models"],
                },
                "warming_levels": wl,
            }

        region_node["sensitivity_crosscheck"] = crosschecks
        region_node["cmip6_models_failed"] = cf.get("failed", [])
        lookup["regions"][region_key] = region_node

    return lookup


def main():
    ap = argparse.ArgumentParser(description="Build the rarity lookup JSON.")
    ap.add_argument("--regions", nargs="*", default=[config.PRIMARY_REGION])
    ap.add_argument("--max-models", type=int, default=None,
                    help="cap the number of CMIP6 models (for quick runs)")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--out", default=os.path.join(config.OUTPUT_DIR, "lookup.json"))
    args = ap.parse_args()

    models = cmip6.available_models()
    if args.max_models:
        models = models[:args.max_models]

    lookup = build(region_keys=args.regions, models=models,
                   use_cache=not args.no_cache)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(lookup, fh, indent=2)
    print(f"wrote {args.out}")
    md = lookup["metadata"]
    print("present GMST anom:", md["present_gmst_anom"])
    for rk, rnode in lookup["regions"].items():
        for mk, mnode in rnode["metrics"].items():
            sp = mnode["scaling_per_gwl"]["spread"]
            print(f"  {rk}/{mk}: n_models={sp['n_models']} "
                  f"dloc/dGWL={mnode['scaling_per_gwl']['dloc_dGWL']} "
                  f"(p17={sp['p17']}, p83={sp['p83']})")
        print("  crosscheck:", rnode["sensitivity_crosscheck"])


if __name__ == "__main__":
    main()
