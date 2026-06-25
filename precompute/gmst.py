"""Observed global-mean surface temperature (GMST) covariate.

Provides the annual observed GMST anomaly relative to 1850-1900, used as the
covariate in the obs-anchored non-stationary GEV. The series is fetched once and
cached locally.

Source note: the Met Office HadCRUT5 host is blocked by this environment's
egress policy, so we use NOAAGlobalTemp (the GCAG series), an accepted GMST
equivalent that spans 1850-present. Because it spans the baseline, we can
re-reference its anomalies to 1850-1900 directly rather than relying on a
published offset.
"""

from __future__ import annotations

import io
import os
import urllib.request

import numpy as np
import pandas as pd

from . import config


def _cache_path() -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, "gmst_source.csv")


def _download() -> pd.DataFrame:
    path = _cache_path()
    if os.path.exists(path):
        with open(path, "r") as fh:
            text = fh.read()
    else:
        req = urllib.request.Request(
            config.GMST_SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=90).read().decode()
        with open(path, "w") as fh:
            fh.write(text)
    return pd.read_csv(io.StringIO(text))


def load_gmst_anomaly() -> pd.Series:
    """Annual GMST anomaly (degC) vs 1850-1900, indexed by integer year.

    The chosen source series is re-referenced so that the 1850-1900 mean is
    zero; values are therefore directly comparable to CMIP6 GWLs.
    """
    df = _download()
    # The datahub series carries multiple sources in long format.
    if "Source" in df.columns:
        df = df[df["Source"] == config.GMST_SOURCE_NAME]
    df = df.rename(columns={c: c.strip() for c in df.columns})
    year_col = "Year"
    val_col = "Mean" if "Mean" in df.columns else df.columns[-1]
    s = pd.Series(df[val_col].values.astype(float),
                  index=df[year_col].values.astype(int)).sort_index()
    s = s[~s.index.duplicated(keep="last")]

    b0, b1 = config.GMST_BASELINE
    baseline = s.loc[b0:b1].mean()
    return s - baseline


def _complete_years(series: pd.Series) -> pd.Series:
    """Drop the newest annual value when it is a running, partial year.

    The source series is updated through the year, so its final entry is a
    year-to-date mean rather than a full calendar year. Including it would bias a
    trend fit toward whatever part of the year has elapsed, so it is dropped.
    """
    s = series.dropna()
    if config.GMST_PRESENT_DROP_PARTIAL_YEAR and len(s) > 1:
        s = s.iloc[:-1]
    return s


def present_trend(series: pd.Series | None = None) -> dict:
    """Trend-based estimate of the present-day GMST anomaly.

    Fits an ordinary-least-squares linear trend to the most recent
    ``config.GMST_TREND_YEARS`` complete years and evaluates it at the final
    (most recent complete) year. Following the Indicators of Global Climate
    Change (Forster et al., 2024), the present level is the *end point of the
    trend* rather than a flat decadal mean: the latter is centred several years
    in the past and so lags the present forced warming. Returns the end-point
    anomaly (degC vs 1850-1900), the current decadal warming rate, and the
    fitted window.
    """
    if series is None:
        series = load_gmst_anomaly()
    window = _complete_years(series).tail(config.GMST_TREND_YEARS)
    years = window.index.to_numpy(dtype=float)
    vals = window.to_numpy(dtype=float)
    slope, intercept = np.polyfit(years, vals, 1)
    year_end = float(years[-1])
    return {
        "anomaly": float(intercept + slope * year_end),
        "rate_per_decade": float(slope * 10.0),
        "year_start": int(years[0]),
        "year_end": int(year_end),
        "n_years": int(len(window)),
    }


def present_anomaly(series: pd.Series | None = None) -> float:
    """Present-day GMST anomaly (degC vs 1850-1900): the trend end point."""
    return present_trend(series)["anomaly"]


if __name__ == "__main__":
    s = load_gmst_anomaly()
    print("years", s.index.min(), "to", s.index.max())
    print("1850-1900 mean (should be ~0):", round(s.loc[1850:1900].mean(), 4))
    print("recent:", s.tail(6).round(3).to_dict())
    pt = present_trend(s)
    print(f"present anomaly (trend end point, {pt['year_start']}-{pt['year_end']}, "
          f"{pt['n_years']} yr): {pt['anomaly']:.3f} degC")
    print(f"current warming rate: {pt['rate_per_decade']:.3f} degC/decade")
