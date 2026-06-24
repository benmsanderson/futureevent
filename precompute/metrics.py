"""Region and metric helpers.

These operate on an xarray.DataArray of (sub-)daily near-surface maximum
temperature with a time dimension and latitude/longitude dimensions. Dimension
names differ between datasets (ERA5 uses latitude/longitude, CMIP6 uses
lat/lon), so they are detected rather than assumed.

The pipeline path for a metric is:
    subset_bbox -> daily_tasmax -> regional_mean -> rolling window -> annual_max
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

_LAT_NAMES = ("latitude", "lat", "y")
_LON_NAMES = ("longitude", "lon", "x")


def _coord_name(da: xr.DataArray, candidates) -> str:
    for c in candidates:
        if c in da.coords or c in da.dims:
            return c
    raise KeyError(f"none of {candidates} found in {list(da.coords)}")


def lat_name(da: xr.DataArray) -> str:
    return _coord_name(da, _LAT_NAMES)


def lon_name(da: xr.DataArray) -> str:
    return _coord_name(da, _LON_NAMES)


def subset_bbox(da: xr.DataArray, bbox) -> xr.DataArray:
    """Subset to bbox = [lon_min, lat_min, lon_max, lat_max].

    bbox longitudes are in -180..180. The dataset may use 0..360, in which case
    the western part of the box wraps past 0; both conventions are handled.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    la, lo = lat_name(da), lon_name(da)

    lat_vals = da[la].values
    if lat_vals[0] > lat_vals[-1]:  # descending latitude
        da = da.sel({la: slice(lat_max, lat_min)})
    else:
        da = da.sel({la: slice(lat_min, lat_max)})

    lon_vals = da[lo].values
    if float(np.nanmax(lon_vals)) > 180.0:
        # dataset is 0..360; translate the requested bounds
        wmin = lon_min % 360.0
        wmax = lon_max % 360.0
        if wmin <= wmax:
            mask = (da[lo] >= wmin) & (da[lo] <= wmax)
        else:  # box wraps across the 0/360 seam
            mask = (da[lo] >= wmin) | (da[lo] <= wmax)
        da = da.where(mask, drop=True)
    else:
        da = da.sel({lo: slice(lon_min, lon_max)})
    return da


def to_celsius(da: xr.DataArray) -> xr.DataArray:
    """Convert Kelvin to Celsius if the data look like Kelvin."""
    units = str(da.attrs.get("units", "")).lower()
    if units in ("k", "kelvin") or float(da.min()) > 150.0:
        da = da - 273.15
        da.attrs["units"] = "degC"
    return da


def _is_subdaily(da: xr.DataArray) -> bool:
    """True if the time step is shorter than ~23 hours (i.e. sub-daily)."""
    t = da["time"].values
    if t.size < 3:
        return False
    # median spacing in hours, robust to a missing step
    deltas = np.diff(t[:50]).astype("timedelta64[m]").astype(float) / 60.0
    return float(np.median(deltas)) < 23.0


def daily_tasmax(da: xr.DataArray) -> xr.DataArray:
    """Aggregate a (sub-)daily series to the daily maximum.

    For hourly or 6-hourly ERA5 this takes the max over each day (an estimate of
    the true daily maximum; coarser sampling biases it slightly low). For data
    already at daily resolution (CMIP6 tasmax) resampling would build a huge
    one-group-per-day graph for no benefit, so it is skipped.
    """
    if not _is_subdaily(da):
        return da
    return da.resample(time="1D").max()


def regional_mean(da: xr.DataArray) -> xr.DataArray:
    """Area-weighted (cos latitude) mean over the spatial dimensions.

    cos-latitude weights account for converging meridians; NaN cells (e.g.
    masked ocean in a model land field) are skipped by the weighted mean.
    """
    la, lo = lat_name(da), lon_name(da)
    weights = np.cos(np.deg2rad(da[la]))
    return da.weighted(weights).mean(dim=(la, lo), skipna=True)


def rolling_window_mean(series_da: xr.DataArray, window_days: int) -> xr.DataArray:
    """Centred-trailing running mean of a 1-D daily time series."""
    if window_days <= 1:
        return series_da
    return series_da.rolling(time=window_days, center=False,
                             min_periods=window_days).mean()


def annual_max(series_da: xr.DataArray, min_days: int = 300) -> pd.Series:
    """Annual block maxima as a pandas Series indexed by integer year.

    Years with fewer than ``min_days`` valid daily values are dropped so a
    partial first or last year does not enter the block-maxima fit.
    """
    counts = series_da.notnull().resample(time="YE").sum()
    amax = series_da.resample(time="YE").max()
    years = amax["time"].dt.year.values
    vals = amax.values
    cnt = counts.values
    out = pd.Series(vals, index=years.astype(int))
    out = out[cnt >= min_days]
    return out.dropna()


def daily_regional_mean(tasmax_subdaily: xr.DataArray) -> xr.DataArray:
    """Region-subset (sub-)daily tasmax -> daily regional-mean series in degC.

    This is the expensive reduction (it triggers the read); compute it once and
    reuse it across metrics that differ only in the running-window length.
    """
    daily = daily_tasmax(tasmax_subdaily)
    daily = to_celsius(daily)
    reg = regional_mean(daily)
    return reg.load()


def annual_max_for_window(daily_regmean: xr.DataArray, window_days: int,
                          min_days: int = 300) -> pd.Series:
    """Annual block maxima of a running-window mean of the daily regional mean."""
    windowed = rolling_window_mean(daily_regmean, window_days)
    return annual_max(windowed, min_days=min_days)


def metric_annual_max(tasmax_subdaily: xr.DataArray, window_days: int,
                      min_days: int = 300) -> pd.Series:
    """Full metric path: daily max -> regional mean -> window -> annual max.

    ``tasmax_subdaily`` is already subset to the region. Output units are degC.
    """
    reg = daily_regional_mean(tasmax_subdaily)
    return annual_max_for_window(reg, window_days, min_days=min_days)
