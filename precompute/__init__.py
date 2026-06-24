"""Offline precompute pipeline for the future-climate rarity tool.

This package reads bias-relevant observational and model data, fits
non-stationary GEV distributions, derives per-degree change factors from CMIP6,
and emits a compact static lookup that the (separate) frontend session consumes.

Modules:
  config        fixed regions, metrics, warming levels, dataset identifiers
  gmst          observed global-mean temperature covariate (vs 1850-1900)
  metrics       daily tasmax, regional mean, TX3x, annual block maxima helpers
  gev           stationary and non-stationary GEV fitting and evaluation
  era5          ERA5 reference annual block maxima and obs-anchored present GEV
  cmip6         CMIP6 per-model GWL covariate fits and ensemble change factors
  build_lookup  orchestration; assembles the lookup JSON
  runtime       lookup evaluator (return period, exceedance, probability ratio)
  sanity_check  feed an observed event value and report present-day rarity
"""

__version__ = "0.1.0"
