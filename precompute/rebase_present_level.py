"""Re-base the committed point artifacts onto a new present-day GMST level.

When *only* the definition of the present-day GMST anomaly changes (e.g. moving
from a flat decadal mean to a trend end point) the obs-anchored GEV fits and the
CMIP6 change factors are unchanged -- only the GMST level at which "present" is
evaluated moves. The full ``build_lookup`` / ``live_value`` pipeline reads
terabyte-scale ERA5/CMIP6 stores, so this utility reproduces exactly the part of
that pipeline that depends on the present level, working purely from the already
committed artifacts. It is the offline equivalent of re-running the point
precompute after a present-level change.

What it touches:
  * ``output/lookup.json``   -- gev_present.loc / ref_gmst_anom and the
                                warming-level loc/scale (re-based deltas), plus
                                the present-level metadata.
  * ``output/live_<r>.json`` -- present / warming-level return periods and
                                probability ratios (event value x_obs unchanged).

What it does NOT touch:
  * ``output/grid_europe.json`` -- the gridded map stores only derived return
    periods per cell, not the per-cell GEV parameters, so it cannot be re-based
    from its own output. Re-run ``python -m precompute.grid`` to refresh it.

The present level itself is computed here the same way as
``precompute.gmst.present_trend`` (trend end point over the last
``GMST_TREND_YEARS`` complete years), in pure Python so this script has no
scientific-stack dependency.

Run from the repo root:  ``python -m precompute.rebase_present_level``
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import urllib.request

from . import config


# --------------------------------------------------------------------------
# Present-day GMST anomaly (mirrors precompute.gmst, pure-Python)
# --------------------------------------------------------------------------
def _load_gmst_anomaly() -> dict:
    """{year: anomaly degC vs 1850-1900} from the configured GCAG source."""
    cache = os.path.join(config.CACHE_DIR, "gmst_source.csv")
    if os.path.exists(cache):
        with open(cache) as fh:
            text = fh.read()
    else:
        req = urllib.request.Request(
            config.GMST_SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=90).read().decode()
    rows = [r for r in csv.DictReader(io.StringIO(text))
            if r.get("Source") == config.GMST_SOURCE_NAME]
    series = {int(r["Year"]): float(r["Mean"]) for r in rows}
    b0, b1 = config.GMST_BASELINE
    base = sum(series[y] for y in series if b0 <= y <= b1) / (b1 - b0 + 1)
    return {y: v - base for y, v in series.items()}


def present_trend() -> dict:
    """Trend end point over the last GMST_TREND_YEARS complete years."""
    anom = _load_gmst_anomaly()
    years = sorted(anom)
    if config.GMST_PRESENT_DROP_PARTIAL_YEAR and len(years) > 1:
        years = years[:-1]  # newest annual value is a running, partial year
    years = years[-config.GMST_TREND_YEARS:]
    xs = [float(y) for y in years]
    ys = [anom[y] for y in years]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    year_end = xs[-1]
    return {
        "anomaly": intercept + slope * year_end,
        "rate_per_decade": slope * 10.0,
        "year_start": int(xs[0]),
        "year_end": int(year_end),
        "n_years": n,
    }


# --------------------------------------------------------------------------
# GEV evaluation (genextreme convention, shape == c; mirrors runtime / gev.js)
# --------------------------------------------------------------------------
_EPS = 1e-8


def _gev_sf(x: float, shape: float, loc: float, scale: float) -> float:
    z = (x - loc) / scale
    if abs(shape) < _EPS:
        cdf = math.exp(-math.exp(-z))
    else:
        t = 1.0 - shape * z
        if t <= 0:
            cdf = 1.0 if shape > 0 else 0.0
        else:
            cdf = math.exp(-(t ** (1.0 / shape)))
    return 1.0 - cdf


# --------------------------------------------------------------------------
# Re-base the lookup
# --------------------------------------------------------------------------
def _warming_levels(loc_p, scale_p, shape_p, dloc_gwl, dscale_gwl, new_anom):
    """Mirror build_lookup._warming_level_params at the new present anomaly."""
    levels = {}
    for g in config.WARMING_LEVELS:
        delta = g - new_anom
        scale_g = scale_p + (dscale_gwl or 0.0) * delta
        scale_g = max(scale_g, 0.05)  # guard positivity, matches build_lookup
        levels[f"{g:.1f}"] = {
            "loc": round(loc_p + (dloc_gwl or 0.0) * delta, 4),
            "scale": round(scale_g, 4),
            "shape": round(shape_p, 4),
        }
    return levels


def rebase_lookup(lookup: dict, new_anom: float, trend: dict) -> dict:
    md = lookup["metadata"]
    md["present_gmst_anom"] = round(new_anom, 4)
    md["present_gmst_method"] = (
        f"end point of an OLS linear trend over the last {trend['n_years']} "
        f"complete years ({trend['year_start']}-{trend['year_end']}); estimates "
        f"present-day forced warming rather than a flat decadal mean (which lags "
        f"the present)")
    md["present_gmst_rate_per_decade"] = round(trend["rate_per_decade"], 3)
    md["present_gmst_citation"] = config.GMST_PRESENT_CITATION

    for region in lookup["regions"].values():
        for node in region["metrics"].values():
            gp = node["gev_present"]
            old_anom = gp["ref_gmst_anom"]
            # obs present GEV is linear in GMST: only the location moves (scale
            # and shape are held constant for the obs fit).
            gp["loc"] = round(gp["loc"] + gp["dloc_dGMST"] * (new_anom - old_anom), 4)
            gp["ref_gmst_anom"] = round(new_anom, 4)
            sp = node["scaling_per_gwl"]
            node["warming_levels"] = _warming_levels(
                gp["loc"], gp["scale"], gp["shape"],
                sp["dloc_dGWL"], sp["dscale_dGWL"], new_anom)
    return lookup


def rebase_live(live: dict, lookup: dict, new_anom: float) -> dict:
    """Recompute present/warming evaluations against the re-based lookup.

    The event value (x_obs on the reference footing) is unchanged; only its
    placement under the present and future warming levels moves.
    """
    region = live["region"]
    rnode = lookup["regions"][region]["metrics"]
    for mkey, m in live["metrics"].items():
        x = m["x_obs_reference_footing"]
        gp = rnode[mkey]["gev_present"]
        p_now = _gev_sf(x, gp["shape"], gp["loc"], gp["scale"])
        m["present"] = {
            "gmst_anom": round(new_anom, 4),
            "exceedance_prob": p_now,
            "return_period_years": (math.inf if p_now <= 0 else 1.0 / p_now),
        }
        levels = {}
        for gwl, par in rnode[mkey]["warming_levels"].items():
            p = _gev_sf(x, par["shape"], par["loc"], par["scale"])
            levels[gwl] = {
                "exceedance_prob": p,
                "return_period_years": (math.inf if p <= 0 else 1.0 / p),
                "probability_ratio_vs_present": (p / p_now if p_now > 0 else math.inf),
            }
        m["warming_levels"] = levels
    return live


def main():
    trend = present_trend()
    new_anom = trend["anomaly"]
    print(f"present GMST anomaly (trend end point "
          f"{trend['year_start']}-{trend['year_end']}, {trend['n_years']} yr): "
          f"{new_anom:.4f} degC  (rate {trend['rate_per_decade']:.3f} degC/decade)")

    lookup_path = os.path.join(config.OUTPUT_DIR, "lookup.json")
    with open(lookup_path) as fh:
        lookup = json.load(fh)
    old_anom = lookup["metadata"]["present_gmst_anom"]
    rebase_lookup(lookup, new_anom, trend)
    with open(lookup_path, "w") as fh:
        json.dump(lookup, fh, indent=2)
    print(f"re-based {lookup_path}: present_gmst_anom {old_anom} -> "
          f"{lookup['metadata']['present_gmst_anom']}")

    for region in lookup["regions"]:
        live_path = os.path.join(config.OUTPUT_DIR, f"live_{region}.json")
        if not os.path.exists(live_path):
            continue
        with open(live_path) as fh:
            live = json.load(fh)
        rebase_live(live, lookup, new_anom)
        with open(live_path, "w") as fh:
            json.dump(live, fh, indent=2)
        pr = live["metrics"]["regional_mean_tasmax"]["present"]
        print(f"re-based {live_path}: present 1-in-"
              f"{pr['return_period_years']:.0f} yr (p={pr['exceedance_prob']:.4f})")

    print("\nNOTE: output/grid_europe.json is NOT re-based here (it stores only "
          "derived per-cell return periods, not the per-cell GEV parameters). "
          "Re-run `python -m precompute.grid` to refresh the spatial map.")


if __name__ == "__main__":
    main()
