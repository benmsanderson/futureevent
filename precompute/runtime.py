"""Lookup evaluator.

The frontend (a later session) re-implements this in the browser; it is kept
here in Python so the precompute session can sanity-check the lookup it emits.
Given a region/metric and an observed value x_obs, it returns the return period
and exceedance probability under the present and each future warming level, plus
the probability ratio relative to the present.
"""

from __future__ import annotations

import json

from scipy.stats import genextreme


def _eval(x, shape, loc, scale):
    p = float(genextreme.sf(x, shape, loc=loc, scale=scale))
    return p, (float("inf") if p <= 0 else 1.0 / p)


def evaluate(lookup: dict, region_key: str, metric_key: str, x_obs: float) -> dict:
    """Place x_obs in present and future context for one region/metric."""
    node = lookup["regions"][region_key]["metrics"][metric_key]
    present = node["gev_present"]
    p_now, t_now = _eval(x_obs, present["shape"], present["loc"], present["scale"])

    levels = {}
    for gwl, params in node["warming_levels"].items():
        p, t = _eval(x_obs, params["shape"], params["loc"], params["scale"])
        ratio = (p / p_now) if p_now > 0 else float("inf")
        levels[gwl] = {
            "exceedance_prob": p,
            "return_period_years": t,
            "probability_ratio_vs_present": ratio,
        }

    return {
        "region": region_key,
        "metric": metric_key,
        "x_obs": x_obs,
        "present": {
            "gmst_anom": present.get("ref_gmst_anom"),
            "exceedance_prob": p_now,
            "return_period_years": t_now,
        },
        "warming_levels": levels,
    }


def load_lookup(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def format_report(result: dict) -> str:
    lines = []
    pr = result["present"]
    lines.append(f"{result['region']} / {result['metric']}  x_obs = "
                 f"{result['x_obs']:.2f}")
    lines.append(f"  present (GMST +{pr['gmst_anom']:.2f}): "
                 f"1-in-{pr['return_period_years']:.0f} yr "
                 f"(p={pr['exceedance_prob']:.4f})")
    for gwl, v in result["warming_levels"].items():
        lines.append(f"  +{gwl} degC: 1-in-{v['return_period_years']:.0f} yr "
                     f"(p={v['exceedance_prob']:.4f}), "
                     f"{v['probability_ratio_vs_present']:.1f}x more likely "
                     f"than present")
    return "\n".join(lines)
