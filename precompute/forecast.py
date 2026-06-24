"""ECMWF open-data forecast: live tasmax for days the reanalysis has not reached.

ERA5T lags real time by about five to seven days, so the peak of an unfolding
heatwave is not yet in the reanalysis. This module pulls the latest ECMWF IFS
HRES (deterministic) open-data forecast of 2 m temperature, computes the same
daily-tasmax regional-mean metrics as the reference pipeline, and hands them to
the blend (see blend.py) which stitches them onto the observed ERA5T days.

Data path: the real-time open forecasts are mirrored anonymously on the AWS Open
Data bucket ``ecmwf-forecasts`` (ECMWF's own host is not reachable from this
environment's egress policy). Each step is a single GRIB2 file with a ``.index``
JSON-lines sidecar giving per-message byte offsets, so a single parameter (2t) is
fetched with an HTTP range request rather than downloading the ~120 MB file.

Notes and limitations:
  - HRES is deterministic; the ENS ensemble (stream ``enfo``) would give a
    probabilistic live value and is the natural next step.
  - 2t is instantaneous at each step (3-hourly to 144 h, then 6-hourly); the
    daily maximum is estimated from those samples, as for the 6-hourly ERA5
    reference. Any residual sampling bias is absorbed by the forecast-vs-ERA5T
    bias correction in the blend.
  - Real-time open data is a rolling archive (about a week); the blend therefore
    operates on the latest available cycle.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import xarray as xr

from . import config, metrics

S3_BASE = "https://ecmwf-forecasts.s3.amazonaws.com/"
_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_UA = {"User-Agent": "futureevent-precompute/0.1"}
OPER_PREFIX = "ifs/0p25/oper/"


def _http(url: str, range_header: str | None = None, timeout: int = 90,
          retries: int = 6) -> bytes:
    headers = dict(_UA)
    if range_header:
        headers["Range"] = range_header
    delay = 1.0
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=headers),
                timeout=timeout).read()
        except urllib.error.HTTPError as exc:
            # S3 throttling (503 Slow Down) and transient 5xx: back off and retry
            if exc.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 20.0)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 20.0)
                continue
            raise
    raise RuntimeError("unreachable")


def _s3_list(prefix: str, delimiter: bool = True):
    """Return (common_prefixes, keys) for an anonymous S3 v2 listing."""
    prefixes, keys, token = [], [], None
    while True:
        url = (f"{S3_BASE}?list-type=2&max-keys=1000&prefix="
               f"{urllib.parse.quote(prefix)}")
        if delimiter:
            url += "&delimiter=/"
        if token:
            url += "&continuation-token=" + urllib.parse.quote(token)
        root = ET.fromstring(_http(url, timeout=60))
        prefixes += [e.find(_S3_NS + "Prefix").text
                     for e in root.findall(_S3_NS + "CommonPrefixes")]
        keys += [e.find(_S3_NS + "Key").text
                 for e in root.findall(_S3_NS + "Contents")]
        nxt = root.find(_S3_NS + "NextContinuationToken")
        if nxt is None:
            break
        token = nxt.text
    return prefixes, keys


def latest_oper_cycle() -> tuple[str, str]:
    """Latest (date, cycle) e.g. ("20251019", "00z") with HRES oper output."""
    date_prefixes, _ = _s3_list("")
    date_prefixes = [p for p in date_prefixes if re.fullmatch(r"\d{8}/", p)]
    for date_p in reversed(date_prefixes):              # newest date first
        cycles, _ = _s3_list(date_p)
        for cycle_p in reversed(cycles):                # newest cycle first
            _, keys = _s3_list(cycle_p + OPER_PREFIX, delimiter=False)
            if any(k.endswith(".grib2") for k in keys):
                date = date_p.strip("/")
                cycle = cycle_p.strip("/").split("/")[-1]
                return date, cycle
    raise RuntimeError("no ECMWF oper forecast found in the open-data bucket")


def _oper_dir(date: str, cycle: str) -> str:
    return f"{date}/{cycle}/{OPER_PREFIX}"


def available_steps(date: str, cycle: str) -> list[int]:
    _, keys = _s3_list(_oper_dir(date, cycle), delimiter=False)
    steps = {int(m.group(1)) for k in keys if k.endswith(".grib2")
             for m in [re.search(r"-(\d+)h-", k)] if m}
    return sorted(steps)


def _file_stem(date: str, cycle: str, step: int) -> str:
    hh = cycle.replace("z", "")
    return f"{_oper_dir(date, cycle)}{date}{hh}0000-{step}h-oper-fc"


def _index_2t(date: str, cycle: str, step: int):
    """(grib_url, offset, length) of the surface 2t message for this step."""
    stem = _file_stem(date, cycle, step)
    txt = _http(S3_BASE + stem + ".index", timeout=60).decode()
    for line in txt.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("param") == "2t" and rec.get("levtype") == "sfc":
            return S3_BASE + stem + ".grib2", int(rec["_offset"]), int(rec["_length"])
    raise KeyError(f"2t not found in index for step {step}h")


def _fetch_2t_field(date: str, cycle: str, step: int) -> xr.DataArray:
    """Range-read and decode the global 2t field for one step (in degC)."""
    url, off, length = _index_2t(date, cycle, step)
    raw = _http(url, range_header=f"bytes={off}-{off + length - 1}")
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "m.grib2")
        with open(fp, "wb") as fh:
            fh.write(raw)
        ds = xr.open_dataset(fp, engine="cfgrib", backend_kwargs={"indexpath": ""})
        da = ds["t2m"].load()
    vt = pd.Timestamp(ds.valid_time.values)
    da = da.expand_dims(time=[vt])
    da = da.drop_vars([c for c in ("valid_time", "time", "step", "number",
                                   "surface", "heightAboveGround")
                       if c in da.coords and c != "time"], errors="ignore")
    da.attrs["units"] = "K"
    return da


def region_subdaily_2t(region_key: str, date: str, cycle: str,
                       max_lead_hours: int = 240, workers: int = 4) -> xr.DataArray:
    """Sub-daily 2t over the region for the latest cycle, concatenated by time."""
    bbox = config.REGIONS[region_key]["bbox"]
    steps = [s for s in available_steps(date, cycle) if s <= max_lead_hours]

    def one(step):
        field = _fetch_2t_field(date, cycle, step)
        return metrics.subset_bbox(field, bbox)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        parts = list(ex.map(one, steps))
    out = xr.concat(parts, dim="time").sortby("time")
    return out


def daily_regional_mean(region_key: str, date: str | None = None,
                        cycle: str | None = None, max_lead_hours: int = 240,
                        min_samples_per_day: int = 4) -> tuple[pd.Series, dict]:
    """Forecast daily regional-mean tasmax (degC), indexed by date.

    Returns (series, provenance). Days with fewer than ``min_samples_per_day``
    sub-daily samples (typically the final partial day) are dropped.
    """
    if date is None or cycle is None:
        date, cycle = latest_oper_cycle()
    sub = region_subdaily_2t(region_key, date, cycle, max_lead_hours)
    daily = metrics.daily_tasmax(sub)
    daily = metrics.to_celsius(daily)
    reg = metrics.regional_mean(daily).load()
    counts = sub.notnull().any(dim=[d for d in sub.dims if d != "time"]) \
        .resample(time="1D").sum().reindex(time=reg.time)
    ser = pd.Series(reg.values, index=pd.to_datetime(reg.time.values).date)
    keep = counts.values >= min_samples_per_day
    ser = ser[keep]
    prov = {
        "source": "ECMWF IFS HRES open-data (AWS mirror), 0.25 deg, 2t",
        "init_date": date,
        "init_cycle": cycle,
        "max_lead_hours": max_lead_hours,
        "forecast_days": [str(d) for d in ser.index],
    }
    return ser, prov


if __name__ == "__main__":
    d, c = latest_oper_cycle()
    print("latest oper cycle:", d, c, "steps to 240h:",
          [s for s in available_steps(d, c) if s <= 240][:5], "...")
    ser, prov = daily_regional_mean(config.PRIMARY_REGION, d, c, max_lead_hours=240)
    print("forecast daily regional-mean tasmax (degC):")
    print(ser.round(2).to_string())
    print("provenance:", {k: v for k, v in prov.items() if k != "forecast_days"})
