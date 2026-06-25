"""Streaming ERA5T 0.25 deg reader: per-cell annual TXx over a domain.

The 0.25 deg hourly ERA5T store is chunked **one global timestep per chunk**
(721x1440, ~4 MB each), so a multi-decade read transfers the whole global field
per hour (~1.1 TB for 1991-2020) regardless of spatial subset -- subsetting
trims memory, not transfer. But the transfer is *streamed*: each ~4 MB global
chunk is fetched, subset to the domain in memory, folded into the reduction, and
discarded. **Nothing global ever lands on disk** (verified: a streaming France
read writes 0 bytes of temp). Only the small reduced annual-TXx field is cached.

We process one calendar year at a time and cache each year's reduced field so a
killed run resumes (mirroring the per-model cmip6 cache pattern). Concurrency is
capped at ``config.MAX_WORKERS`` (good-neighbour policy on a shared node).

This is the heavy, one-time step behind the ``local_txx`` metric (the per-cell
local daily maximum, contrast with the area-averaged ``regional_mean_tasmax``).
"""

from __future__ import annotations

import argparse
import os

import dask
import numpy as np
import xarray as xr

from . import config, metrics

# France-only domain for v1 (headline France-peak + France-only 0.25 deg map).
DOMAIN = {"name": "france", "bbox": config.REGIONS["france"]["bbox"]}

# Climatology period (owner decision): 30 annual maxima, ~1.1 TB one-time read.
CLIMATOLOGY_PERIOD = (1991, 2020)

# Require most of the year present before a year enters the block-maxima series
# (guards a partial first/last year; 1991-2020 reanalysis years are complete).
_MIN_VALID_HOURS = 300 * 24


def _open_era5t() -> xr.Dataset:
    """Open the 0.25 deg hourly store, streaming chunks to memory.

    Plain ``gs://`` + anonymous token reads each chunk into memory and discards
    it. **Never** wrap this in an fsspec ``simplecache::``/``filecache::`` URL --
    that would persist every fetched chunk (~TB) to disk and blow the node's
    space budget. ``chunks={"time": 168}`` groups a week of hourly steps per dask
    task to cut task overhead; each task still fetches its 168 global chunks.
    """
    return xr.open_zarr(config.ERA5T_STORE, chunks={"time": 168},
                        storage_options={"token": "anon"})


def _to_180(da: xr.DataArray) -> xr.DataArray:
    """Express longitude in -180..180 and sort (shared frame with grid.py)."""
    lo = metrics.lon_name(da)
    return da.assign_coords({lo: (((da[lo] + 180) % 360) - 180)}).sortby(lo)


def _annual_txx_year(var: xr.DataArray, year: int, bbox) -> tuple:
    """Per-cell annual TXx (degC) and valid-hour count for one year over bbox.

    Annual max of each cell's *daily* max equals annual max of the hourly field,
    so for the 1-day window we reduce straight to the yearly max -- no daily
    resample graph needed. The reduction streams: only domain-subset, reduced
    fields are held; global chunks are fetched and dropped.
    """
    da = var.sel(time=slice(f"{year}-01-01", f"{year}-12-31"))
    sub = metrics.subset_bbox(da, bbox)
    sub.attrs.setdefault("units", "K")  # set so to_celsius doesn't trigger a
    sub = metrics.to_celsius(sub)       # spurious .min() compute on the lazy array
    txx = sub.max("time")
    valid = sub.notnull().sum("time")
    # Threaded scheduler (IO-bound) capped at MAX_WORKERS: bounds concurrent
    # chunk fetches and holds intermediates in memory (no disk spill).
    txx, valid = dask.compute(txx, valid, scheduler="threads",
                              num_workers=config.MAX_WORKERS)
    return _to_180(txx), _to_180(valid)


def annual_txx_field(period=CLIMATOLOGY_PERIOD, use_cache: bool = True,
                     verbose: bool = True) -> xr.DataArray:
    """(year, lat, lon) annual TXx over the France domain, cached per year.

    Returns a DataArray named ``local_txx`` in degC. Each year is cached as a
    small netCDF under ``config.CACHE_DIR`` so a killed run resumes.
    """
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    ds = _open_era5t()
    var = ds[config.ERA5_TAS_VAR]
    fields = []
    for year in range(period[0], period[1] + 1):
        cache = os.path.join(config.CACHE_DIR,
                             f"era5t_txx_{DOMAIN['name']}_{year}.nc")
        if use_cache and os.path.exists(cache):
            fields.append(xr.open_dataarray(cache))
            continue
        txx, valid = _annual_txx_year(var, year, DOMAIN["bbox"])
        txx = txx.where(valid >= _MIN_VALID_HOURS)
        txx = txx.assign_coords(year=year).expand_dims("year")
        txx.name = "local_txx"
        txx.to_netcdf(cache)
        if verbose:
            print(f"  {year}: France-domain TXx max "
                  f"{float(txx.max()):.1f} degC -> cached "
                  f"{os.path.basename(cache)}")
        fields.append(txx)
    return xr.concat(fields, dim="year").sortby("year")


def main():
    ap = argparse.ArgumentParser(
        description="Stream-read ERA5T 0.25 deg and cache annual TXx over France.")
    ap.add_argument("--start", type=int, default=CLIMATOLOGY_PERIOD[0])
    ap.add_argument("--end", type=int, default=CLIMATOLOGY_PERIOD[1])
    ap.add_argument("--no-cache", action="store_true",
                    help="recompute every year even if a cache file exists")
    args = ap.parse_args()
    field = annual_txx_field(period=(args.start, args.end),
                             use_cache=not args.no_cache)
    nlat, nlon = field.sizes[metrics.lat_name(field)], field.sizes[metrics.lon_name(field)]
    print(f"annual TXx field: {field.sizes['year']} years x {nlat}x{nlon} cells; "
          f"domain max {float(field.max()):.1f} degC")


if __name__ == "__main__":
    main()
