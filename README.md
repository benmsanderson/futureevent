# Future-climate rarity context for extreme heat events (precompute pipeline)

Offline precompute that places an observed or forecast heat extreme in the
context of bias-informed CMIP6 data, with the headline focus on how rare the
event becomes in future climates, expressed on a global-warming-level (GWL)
axis. Test case: the June 2026 central Europe / France heatwave.

This repository is the precompute session only. It reads zarr from public
buckets, fits GEVs, derives per-GWL change factors, and emits a compact static
lookup (`output/lookup.json`). The frontend is a separate, later session that
consumes the lookup and needs no live data dependency.

## Scientific method

- Present-day rarity is observation-anchored. A non-stationary GEV is fit to the
  observed annual block maxima of the event metric, with the observed GMST
  anomaly (vs 1850-1900) as covariate, so the present-day distribution accounts
  for warming to date. The current-climate return period comes from
  observations, not from model tails.
- Future panels come from CMIP6 change factors. The ensemble is used only for
  the response: the shift in GEV location and scale per degree of additional
  global warming. Those per-GWL change factors are applied to the obs-anchored
  GEV as deltas from the present.
- GWL axis, not SSP-by-year. Headline levels: +1.5, +2, +3 degrees C relative to
  1850-1900.
- The present-day GMST sensitivity from the obs fit (`dloc/dGMST`) is kept as a
  cross-check against the CMIP-derived per-degree scaling (`dloc/dGWL`); a large
  disagreement is flagged, not silently averaged over.

## Data sources

| Role | Source | Notes |
| --- | --- | --- |
| Reference / present distribution | ARCO-ERA5 `ar/1959-2022-6h-240x121` conservative | 1.5 deg, 6-hourly; read anonymously via gcsfs |
| Live event value (observed) | ARCO-ERA5 `full_37-1h-0p25deg-chunk-1.zarr-v3` | 0.25 deg, hourly ERA5T, ~5-7 day latency |
| Live event value (forecast) | ECMWF IFS HRES open data, AWS mirror `s3://ecmwf-forecasts` | 0.25 deg, deterministic 2t; ECMWF host not reachable, AWS mirror is |
| Future scaling | Pangeo CMIP6 (intake-esm), daily `tasmax`, historical + ssp585 | 24 models, member r1i1p1f1 |
| Model GWL | CMIP6 monthly `tas` (Amon), per-model GSAT 20-yr running mean | crossing computed, not tabulated |
| Observed GMST covariate | NOAAGlobalTemp (GCAG), re-referenced to 1850-1900 | stands in for HadCRUT5 (Met Office host not reachable here) |

### Why a coarse reference grid

The 0.25 deg hourly ARCO-ERA5 store is chunked one timestep per chunk (whole
globe), so a multi-decade regional time series would be a terabyte-scale read.
The 1.5 deg 6-hourly conservative store is chunked 8 timesteps per chunk and the
full 1959-2021 regional record reads in a few minutes. The cost is a coarser
grid and 6-hourly (not hourly) sampling of the daily maximum, which biases the
daily maximum slightly low. The live event value uses the 0.25 deg hourly store,
so there is a documented product offset between the reference GEV and the live
value; `sanity_check.py` estimates it over a shared summer month.

## Event metrics and regions

Metrics (both as annual block maxima):

- `regional_mean_tasmax`: annual max of the area-weighted regional-mean daily
  tasmax (the hottest single day, regionally averaged).
- `tx3x`: annual max of the 3-day running mean of that regional-mean daily
  tasmax (the hottest 3-day spell).

Regions are fixed lat/lon boxes (`france`, `central_europe`); see
`precompute/config.py`. France is the v1 milestone region.

## Output: the lookup schema

`output/lookup.json` matches the agreed contract: per region and metric it
carries the obs-anchored present GEV (`gev_present`), the CMIP6 change factors
(`scaling_per_gwl` with ensemble median and 17/83 spread), and the future GEV
parameters at each warming level (`warming_levels`). Fit diagnostics, the model
list, reference periods, dataset versions, and the obs-vs-CMIP sensitivity
cross-check are recorded for traceability.

GEV convention: parameters are in the `scipy.stats.genextreme` convention, where
`shape == c == -xi`. The annual-maximum CDF is, with `z = (x - loc) / scale`:

```
c != 0:  F(x) = exp( -(1 - c*z)**(1/c) )    valid where 1 - c*z > 0
c == 0:  F(x) = exp( -exp(-z) )
```

Return period of an annual block maximum is `T(x) = 1 / (1 - F(x))`.

## Live event value: ERA5T + ECMWF forecast blend

The frontend needs one current value per region/metric. ERA5T lags real time by
about 5-7 days, so a heatwave that is peaking now is not yet in the reanalysis.
`live_value.py` produces the current value by blending, in order of preference
for each day:

1. ERA5T reanalysis for days already observed;
2. the freshest ECMWF HRES forecast for the most recent and near-future days;
3. an older long-horizon forecast cycle (00z/12z, to 360 h) to fill the gap
   between ERA5T's last day and the freshest cycle, and to overlap ERA5T.

Footing is handled in two steps: the forecast is bias-corrected onto the ERA5T
footing using days where a forecast and ERA5T coincide (the forecast reads about
0.85 degC cooler, since 2t is sampled 3-6 hourly rather than hourly), then the
whole blended series is shifted by the ERA5T-vs-reference product offset
(about +0.88 degC for France) so the event value can be read against the lookup.
The output `output/live_<region>.json` carries the event value, its present and
future evaluation, and full provenance (cycles used, bias, offset, per-day
source). This is the small frequently-run job, separate from the heavy
precompute. ENS (probabilistic) is the natural next addition; v1 uses HRES.

## Running

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# build the lookup (France, all available CMIP6 models)
python -m precompute.build_lookup --regions france --out output/lookup.json

# emit the live blended event value (ERA5T + ECMWF forecast)
python -m precompute.live_value --region france

# sanity-check the GEV against a historical record value
python -m precompute.sanity_check --lookup output/lookup.json --region france \
    --x-obs 30.9
```

Heavy reads are cached under `cache/` (per-region ERA5 block maxima, per-model
CMIP6 change factors, the product offset), so re-assembling the lookup is cheap
after the first run. Use `--no-cache` to force a re-read.

On the cluster the environment is managed with `pixi` (the `cfgrib`/`eccodes`
GRIB toolchain installs cleanly from conda-forge); `pixi install` then prefix the
commands with `pixi run`. `pixi.toml` and `pixi.lock` are committed; the
materialised env under `.pixi/` is not.

### Local peak (TXx): France-peak headline and 0.25 deg map

```bash
# heavy, one-time: stream ERA5T 0.25 deg hourly to cached annual TXx (1991-2020).
# This is the ~1.1 TB read; it is transfer-bound, not disk-bound (it streams the
# whole-globe-per-timestep store, keeps only France, writes ~0 bytes of global
# data), and self-caps at FE_MAX_WORKERS (default 24) for a shared node.
pixi run python -m precompute.era5t_hires

# France-peak headline (merged into live_france.json) + France-only 0.25 deg map
# (output/grid_france_hires.json): CMIP6 change factors + present fit + event blend.
pixi run python -m precompute.local_peak           # --reuse-event to skip the forecast
```

## Processed data (what is committed vs regenerated)

The repo stays small: the conda env (`.pixi/`, ~1.3 GB) is ignored, and `cache/`
is ignored by default. The one exception is the **ERA5T 0.25 deg annual-TXx
fields** (`cache/era5t_txx_*.nc`, ~600 KB total): they distil the ~1.1 TB read
into a few hundred KB, so they are committed as the durable copy of the expensive
processed data and deploys never re-read the cloud for them. The small JSON the
frontend consumes (`output/*.json`, the data contract) is also committed.
Everything else under `cache/` (CMIP6 per-model fits, GMST, offsets, logs) is
cheap to regenerate and stays ignored. A full checkout is therefore ~1 MB.

## Module map

| Module | Responsibility |
| --- | --- |
| `config` | fixed regions, metrics, warming levels, dataset identifiers |
| `gmst` | observed GMST covariate (annual anomaly vs 1850-1900) |
| `metrics` | bbox subset, daily tasmax, regional mean, TX3x, annual maxima |
| `gev` | stationary and non-stationary GEV fit and evaluation |
| `era5` | ERA5 annual block maxima and the obs-anchored present GEV |
| `cmip6` | per-model GWL covariate fits and ensemble change factors |
| `era5t_hires` | streaming ERA5T 0.25 deg reader: cached annual TXx over France |
| `local_peak` | local_txx France-peak headline + France-only 0.25 deg grid |
| `build_lookup` | orchestration; assembles `output/lookup.json` |
| `runtime` | lookup evaluator (return period, exceedance, probability ratio) |
| `forecast` | ECMWF IFS HRES open-data fetch (range-read 2t per step) |
| `blend` | ERA5T + forecast blend onto the reference footing |
| `live_value` | emits `output/live_<region>.json` (blended value + evaluation) |
| `sanity_check` | feed an event value and report present-day rarity; product offset |

## Conventions and scope

This tool is contextualization, not attribution. Prose avoids em-dashes. The
pipeline is parameterised by region and metric (tier-2 ready) but ships the
single-event France path first.

## Frontend (`web/`)

A static Observable Framework site (built to plain HTML/JS, deployed to GitHub
Pages) consumes `output/lookup.json`, `output/live_<region>.json`, and the
gridded `output/grid_<domain>.json`. It needs no backend and no runtime data
access: `web/src/components/gev.js` is a direct port of `precompute/runtime.py`,
so return periods are recomputed in the browser. Pages: the event page (headline
odds/frequency, return-period-vs-warming chart, distribution small-multiples,
probability-ratio map) and a methods/provenance page, with the "contextualization,
not attribution" framing throughout.

```bash
cd web && npm install
# offline only: pre-populate the npm cache (CI reaches jsdelivr and skips this)
node prebundle.mjs
npm run build      # static site in web/dist
npm run dev        # local preview
```
