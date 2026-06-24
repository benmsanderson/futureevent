"""Fixed configuration for the precompute pipeline.

Everything that defines "the event menu" lives here so the pipeline stays
parameterised by region and metric while shipping the single-event path first.
No auto-detection: regions and metrics are a small precommitted menu.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Output / cache locations
# --------------------------------------------------------------------------
# Heavy reads are cached as intermediate artefacts so the lookup can be
# re-assembled cheaply without re-downloading from the buckets.
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(PKG_DIR)
OUTPUT_DIR = os.path.join(REPO_DIR, "output")
CACHE_DIR = os.environ.get("FE_CACHE_DIR", os.path.join(REPO_DIR, "cache"))

# --------------------------------------------------------------------------
# Warming-level axis (degrees C relative to 1850-1900)
# --------------------------------------------------------------------------
WARMING_LEVELS = [1.5, 2.0, 3.0]
GWL_BASELINE = "1850-1900"

# --------------------------------------------------------------------------
# Data sources
# --------------------------------------------------------------------------
# Reference / present-day distribution: ARCO-ERA5 on GCS, read anonymously.
# The 0.25 deg hourly store is chunked one timestep per chunk (whole globe),
# which makes a multi-decade regional time series a terabyte-scale read. The
# 1.5 deg 6-hourly conservative store is chunked 8 timesteps per chunk and is
# tractable (a few minutes for the full record), so it is the v1 reference.
# The cost is a coarser grid and 6-hourly (not hourly) sampling of the daily
# maximum; both are documented offsets recorded in the lookup metadata.
ERA5_REFERENCE_STORE = (
    "gs://gcp-public-data-arco-era5/ar/"
    "1959-2022-6h-240x121_equiangular_with_poles_conservative.zarr"
)
ERA5_REFERENCE_LABEL = (
    "ARCO-ERA5 ar/1959-2022-6h-240x121 conservative (1.5 deg, 6-hourly)"
)
ERA5_TAS_VAR = "2m_temperature"
ERA5_REF_PERIOD = (1959, 2021)  # full years available in the reference store

# Near-real-time store for the live event value (ERA5T). The 0.25 deg hourly
# store extends to the present; a short window is a cheap read even though it
# downloads whole-globe chunks per hour.
ERA5T_STORE = (
    "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
)
ERA5T_LABEL = "ARCO-ERA5 ar/full_37-1h-0p25deg-chunk-1.zarr-v3 (0.25 deg, hourly)"

# Future scaling: Pangeo CMIP6 zarr collection via the cloud catalog.
CMIP6_CATALOG = "https://storage.googleapis.com/cmip6/pangeo-cmip6.json"
CMIP6_EXPERIMENTS = ["historical", "ssp585"]
CMIP6_MEMBER = "r1i1p1f1"
CMIP6_TASMAX_TABLE = "day"
CMIP6_TAS_TABLE = "Amon"  # monthly tas for the per-model GWL (GSAT) series
# Some models extend ssp585 to 2300; cap the change-factor fit at the standard
# CMIP6 horizon so the per-degree slope reflects the relevant 0-5 degC regime
# rather than being dominated by far-future warming.
CMIP6_FIT_END_YEAR = 2100

# Observed GMST covariate. The Met Office HadCRUT5 host is not reachable from
# this environment's egress policy; NOAAGlobalTemp (GCAG), an accepted
# equivalent, is mirrored on a reachable host and spans 1850-present, which lets
# us re-reference to 1850-1900 directly.
GMST_SOURCE_URL = (
    "https://raw.githubusercontent.com/datasets/global-temp/main/data/annual.csv"
)
GMST_SOURCE_NAME = "GCAG"  # NOAAGlobalTemp land+ocean global mean
GMST_SOURCE_LABEL = (
    "NOAAGlobalTemp (GCAG) annual global mean, re-referenced to 1850-1900 "
    "(stands in for HadCRUT5; Met Office host not reachable in this build)"
)
GMST_BASELINE = (1850, 1900)
# Window used to report the "present" GMST anomaly (recent multi-year mean,
# robust to a single noisy or partial year).
GMST_PRESENT_WINDOW = (2015, 2024)

# --------------------------------------------------------------------------
# Regions (simple lat/lon bounding boxes; bbox = [lon_min, lat_min, lon_max,
# lat_max] to match the lookup schema). Longitudes are in -180..180 here and
# converted to the dataset convention at read time.
# --------------------------------------------------------------------------
REGIONS = {
    "france": {
        "name": "France (metropolitan)",
        "bbox": [-5.0, 41.0, 9.5, 51.5],
    },
    "central_europe": {
        "name": "Central Europe",
        "bbox": [2.0, 44.0, 17.0, 54.0],
    },
}

# Region processed end to end for the v1 milestone.
PRIMARY_REGION = "france"

# --------------------------------------------------------------------------
# Metrics. Both are annual block maxima of a daily-resolution series so the
# GEV block-maxima fit is well posed.
#   regional_mean_tasmax  annual max of the area-weighted regional-mean daily
#                         tasmax (the hottest single day, regionally averaged)
#   tx3x                  annual max of the 3-day running mean of that same
#                         regional-mean daily tasmax (hottest 3-day spell)
# --------------------------------------------------------------------------
METRICS = {
    "regional_mean_tasmax": {
        "name": "Regional-mean daily maximum temperature",
        "window_days": 1,
        "units": "degC",
    },
    "tx3x": {
        "name": "Hottest 3-day mean of regional-mean daily tasmax (TX3x)",
        "window_days": 3,
        "units": "degC",
    },
}

# --------------------------------------------------------------------------
# GEV fitting choices
# --------------------------------------------------------------------------
# Observed fit: location linear in the GMST covariate, scale and shape constant
# (63 annual maxima do not robustly support a non-stationary scale).
OBS_FIT_SCALE_COVARIATE = False
# Model fits: ~250 annual maxima per model support a non-stationary scale, so we
# let both location and scale vary linearly in the model GWL.
MODEL_FIT_SCALE_COVARIATE = True

# Cross-check flag: warn if the obs dloc/dGMST and the CMIP median dloc/dGWL
# disagree by more than this factor (either direction).
SENSITIVITY_FLAG_RATIO = 2.0
