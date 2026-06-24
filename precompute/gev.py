"""Stationary and non-stationary GEV fitting and evaluation.

Convention
----------
We use scipy.stats.genextreme throughout, whose shape parameter ``c`` relates to
the standard extreme-value index xi by ``c = -xi``. The lookup stores ``shape``
== this scipy ``c``. The CDF of an annual block maximum is, with
z = (x - loc) / scale:

    c != 0:  F(x) = exp( -(1 - c * z) ** (1 / c) ),   valid where 1 - c*z > 0
    c == 0:  F(x) = exp( -exp(-z) )

so a frontend can evaluate it without scipy. The return period of a value x for
annual block maxima is T(x) = 1 / (1 - F(x)) = 1 / SF(x).

Non-stationary model
--------------------
location and (optionally) scale are linear in a covariate G:

    loc(G)   = loc0 + dloc * G
    scale(G) = scale0 + dscale * G      (scale held constant if dscale not fit)
    shape    = c                         (held constant)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.stats import genextreme

_BIG = 1e12
_MIN_SCALE = 1e-6


# --------------------------------------------------------------------------
# Stationary fit
# --------------------------------------------------------------------------
@dataclass
class StationaryGEV:
    shape: float  # scipy genextreme c
    loc: float
    scale: float
    n: int
    nllf: float

    def asdict(self) -> dict:
        return asdict(self)


def fit_stationary(y: np.ndarray) -> StationaryGEV:
    """Fit a stationary GEV by MLE (scipy's fit, which is L-moment seeded)."""
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    c, loc, scale = genextreme.fit(y)
    nllf = -np.sum(genextreme.logpdf(y, c, loc=loc, scale=scale))
    return StationaryGEV(shape=float(c), loc=float(loc), scale=float(scale),
                         n=int(y.size), nllf=float(nllf))


# --------------------------------------------------------------------------
# Non-stationary fit (covariate in location, optionally in scale)
# --------------------------------------------------------------------------
@dataclass
class NonStationaryGEV:
    shape: float       # scipy genextreme c (constant)
    loc0: float        # location intercept
    dloc: float        # d location / d covariate
    scale0: float      # scale intercept
    dscale: float      # d scale / d covariate (0.0 if not fit)
    fit_scale_covariate: bool
    covariate_name: str
    n: int
    nllf: float
    aic: float
    converged: bool

    def loc_at(self, g: float) -> float:
        return self.loc0 + self.dloc * g

    def scale_at(self, g: float) -> float:
        return self.scale0 + self.dscale * g

    def params_at(self, g: float) -> tuple[float, float, float]:
        """Return (shape, loc, scale) of the stationary GEV at covariate g."""
        return self.shape, self.loc_at(g), self.scale_at(g)

    def asdict(self) -> dict:
        return asdict(self)


def _nll_nonstationary(params, y, g, fit_scale_cov):
    c = params[0]
    loc0, dloc, scale0 = params[1], params[2], params[3]
    loc = loc0 + dloc * g
    if fit_scale_cov:
        dscale = params[4]
        scale = scale0 + dscale * g
    else:
        scale = np.full_like(g, scale0)
    if np.any(scale <= _MIN_SCALE):
        return _BIG
    ll = genextreme.logpdf(y, c, loc=loc, scale=scale)
    if not np.all(np.isfinite(ll)):
        return _BIG
    return -float(np.sum(ll))


def fit_nonstationary(y: np.ndarray, g: np.ndarray, covariate_name: str,
                      fit_scale_covariate: bool = False) -> NonStationaryGEV:
    """Fit a non-stationary GEV with location (and optionally scale) linear in g.

    Parameters
    ----------
    y : array of block maxima
    g : array of covariate values, same length as y
    covariate_name : label stored on the result (e.g. "GMST", "GWL")
    fit_scale_covariate : if True, scale is also linear in g
    """
    y = np.asarray(y, dtype=float)
    g = np.asarray(g, dtype=float)
    mask = np.isfinite(y) & np.isfinite(g)
    y, g = y[mask], g[mask]
    n = y.size

    # Seed from a stationary fit plus an OLS slope of y on g for the location.
    base = fit_stationary(y)
    slope = float(np.polyfit(g, y, 1)[0]) if np.ptp(g) > 0 else 0.0
    if fit_scale_covariate:
        x0 = [base.shape, base.loc, slope, base.scale, 0.0]
    else:
        x0 = [base.shape, base.loc, slope, base.scale]

    res = minimize(_nll_nonstationary, x0, args=(y, g, fit_scale_covariate),
                   method="Nelder-Mead",
                   options={"maxiter": 20000, "xatol": 1e-7, "fatol": 1e-9})
    p = res.x
    dscale = float(p[4]) if fit_scale_covariate else 0.0
    k = len(p)  # number of free parameters
    nllf = float(res.fun)
    aic = 2 * k + 2 * nllf
    return NonStationaryGEV(
        shape=float(p[0]), loc0=float(p[1]), dloc=float(p[2]),
        scale0=float(p[3]), dscale=dscale,
        fit_scale_covariate=fit_scale_covariate, covariate_name=covariate_name,
        n=int(n), nllf=nllf, aic=float(aic), converged=bool(res.success))


# --------------------------------------------------------------------------
# Evaluation helpers (work on plain (shape, loc, scale) triples)
# --------------------------------------------------------------------------
def exceedance_prob(x: float, shape: float, loc: float, scale: float) -> float:
    """Annual exceedance probability P(X > x) = survival function."""
    return float(genextreme.sf(x, shape, loc=loc, scale=scale))


def return_period(x: float, shape: float, loc: float, scale: float) -> float:
    """Return period in years for an annual block maximum value x."""
    p = exceedance_prob(x, shape, loc, scale)
    if p <= 0.0:
        return float("inf")
    return 1.0 / p


def return_level(period: float, shape: float, loc: float, scale: float) -> float:
    """Value with the given return period (inverse of return_period)."""
    p = 1.0 / period
    return float(genextreme.isf(p, shape, loc=loc, scale=scale))
