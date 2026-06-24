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


def present_anomaly(series: pd.Series | None = None) -> float:
    """Present-day GMST anomaly: mean over the configured recent window."""
    if series is None:
        series = load_gmst_anomaly()
    w0, w1 = config.GMST_PRESENT_WINDOW
    return float(series.loc[w0:w1].mean())


if __name__ == "__main__":
    s = load_gmst_anomaly()
    print("years", s.index.min(), "to", s.index.max())
    print("1850-1900 mean (should be ~0):", round(s.loc[1850:1900].mean(), 4))
    print("recent:", s.tail(6).round(3).to_dict())
    print("present anomaly (window mean):", round(present_anomaly(s), 3))
