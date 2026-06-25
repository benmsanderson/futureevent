# Handover: local-peak (TXx) metric + France-peak headline

**Purpose.** Add a *local* peak-temperature representation to the tool so the
displayed severity matches what people read in the news (station-scale ~40–42 °C),
instead of only the France-wide average (~31 °C) the tool currently shows. The
headline deliverable is a **"France peak" readout**: the hottest local daily-max
in metropolitan France for the event, its rarity now, and how that rarity shifts
along the warming axis. Optionally extend the spatial maps to 0.25° local peaks.

This is the heavy follow-up (item **(1)**) discussed after we shipped honest
labelling (item (3)). It is being moved to a **cluster** because it needs a
0.25°-resolution read of a terabyte-scale store. **Hard constraint: use at most
24 CPUs (good-neighbour policy).**

---

## 0. Orientation — what this repo is

A static "extreme-heat in a warming climate" contextualization tool. Two halves:

- **`precompute/`** (Python): reads ERA5 + CMIP6, fits non-stationary GEVs, writes
  JSON artifacts to `output/`.
- **`web/`** (Observable Framework): reads those JSON files, renders the page. The
  frontend does *no* data access — everything comes from `output/*.json`.

Current artifacts the frontend consumes (the **data contract**):

| file | shape (relevant parts) |
|---|---|
| `output/lookup.json` | `metadata` + `regions.<r>.metrics.<m>.{gev_present, warming_levels{level:{loc,scale,shape}}, scaling_per_gwl, fit_diagnostics}` |
| `output/live_france.json` | `metrics.<m>.{x_obs_reference_footing, peak_day, present:{return_period_years,exceedance_prob,gmst_anom}, warming_levels{level:{return_period_years,exceedance_prob,probability_ratio_vs_present}}}` |
| `output/grid_europe.json` | `bbox, grid_deg, present_gmst_anom, warming_levels[], n_models, metrics.<m>.cells[]{lat,lon,x_obs,present_rp,present_p,rp{},ratio{},rl{}}` |

Levels currently in the data: `0.0` (1850–1900), `1.0` (~recent), `now` (present
≈ +1.36 °C, the trend-based baseline — see §7), `1.5`, `2.0`, `3.0`.

### Key precompute modules

- `config.py` — all knobs: data stores, `METRICS`, `REGIONS`, `WARMING_LEVELS`,
  `HISTORICAL_LEVELS`, `GMST_*`, fit flags. **Two ERA5 stores defined here:**
  - `ERA5_REFERENCE_STORE` — **1.5°, 6-hourly** conservative (the current
    climatology footing; tractable, ~minutes to read full record).
  - `ERA5T_STORE` — **0.25°, hourly** (`...full_37-1h-0p25deg-chunk-1.zarr-v3`).
    **Chunked one timestep per chunk, whole globe.** This is the local-peak source
    and the reason this job is heavy (see §3).
- `era5.py` — `_open_reference()`, `annual_maxima()`, `present_gev()`.
- `cmip6.py` — intake-esm catalog, `_zstore/_open`, `model_gwl()`,
  `ensemble_change_factors()`, `available_models()` (24 models).
- `metrics.py` — `subset_bbox`, `to_celsius`, `daily_tasmax`, regional-mean
  helpers, `lat_name/lon_name`, rolling-window for TX3x.
- `gev.py` — `fit_nonstationary` (GMST covariate), `fit_stationary`,
  `exceedance_prob`, `return_period`, `return_level` (all via
  `scipy.stats.genextreme`; **shape == genextreme `c` == −ξ**).
- `grid.py` — the existing **1.5° spatial grid** (closest analogue to what you'll
  build). Read this first. `era5_present_grid()` fits a per-cell NS-GEV from the
  reference store; `cmip6_change_factor_grid()` fits per-model change factors and
  takes the ensemble median, sampled to the reference grid; `event_field()` builds
  the per-cell event value from the ERA5T+forecast blend; `build_grid()` assembles
  cells. `--reuse-event` reuses a prior event field to skip the forecast (§7).
- `blend.py` / `forecast.py` — the live event blend: ERA5T (0.25° hourly) +
  ECMWF IFS HRES open-data forecast (GRIB, via cfgrib). `live_value.py` writes
  `live_<region>.json`; `era5t_ref_offset()` is the ERA5T-vs-reference product
  offset.
- `build_lookup.py` — point-lookup assembly. `rebase_present_level.py` — offline
  re-base of the point artifacts (no heavy reads) when only the present level or
  the level set changes.

---

## 1. What "local peak" means here

- **New metric `local_txx`**: per-cell *local* daily maximum temperature (TXx),
  i.e. annual maximum of each cell's own daily-max — **not** the regional mean.
  Source: the **0.25° hourly** store (captures the afternoon peak and resolves
  cities away from the coast). Contrast with the existing `regional_mean_tasmax`
  (area-averaged over France, 1.5° 6-hourly footing).
- **France peak (headline)**: the single hottest `local_txx` 0.25° cell inside
  **metropolitan France** on the event's peak day, with its present return period
  and its rarity at each warming level. Expect ~40–42 °C (still ~1–2 °C under the
  hottest station, ERA5's known gridbox cool bias — note this honestly).

---

## 2. Deliverables (in priority order)

1. **France-peak headline** (the powerful bit). Add to `live_france.json`:
   ```jsonc
   "france_peak": {
     "metric": "local_txx",
     "value": 41.6,                  // degC, hottest metropolitan-France 0.25° cell
     "lat": 47.3, "lon": -1.4,
     "nearest_place": "near Nantes", // optional, from a small city list
     "peak_day": "2026-06-24",
     "present": { "return_period_years": 38.0, "exceedance_prob": 0.026, "gmst_anom": 1.3603 },
     "warming_levels": {
       "0.0": { "return_period_years": null, "exceedance_prob": 0.0, "probability_ratio_vs_present": null },
       "1.0": { ... }, "1.5": { ... }, "2.0": { ... }, "3.0": { ... }
     }
   }
   ```
   Frontend (`web/src/index.md`, headline block ~lines 29–38): add a sentence —
   *"Locally, the peak reached **41.6 °C** near Nantes — about **1-in-38** today,
   becoming **1-in-N** at +2 °C."* Keep the existing France-average headline and
   its honest-labelling note (already shipped); this **adds** the local peak.

2. **Present `local_txx` GEV climatology at 0.25°** over the analysis domain,
   parallel to `era5_present_grid()` but at 0.25° and using each cell's own
   daily-max (TXx), not a regional mean. This is what makes (1) possible.

3. **(Optional / heavier) 0.25° local-peak maps.** Because the read is chunked
   globally per timestep, spatial subsetting does **not** reduce read cost (§3) —
   so once you've paid for the present climatology read over the domain, building
   0.25° maps is mostly extra *fitting*, not extra *reading*. Add `local_txx` to
   `grid_europe.json` (or a new `grid_europe_hires.json`) and wire a metric toggle
   in the maps. Decide with the owner whether to do full Europe or France-only.

---

## 3. Why the cluster — the cost model

`ERA5T_STORE` is chunked **one timestep per chunk, whole globe** (0.25° → a
1440×721 field, ~4 MB, per hourly step). Consequences:

- **Any multi-decade time series — even a single point — requires reading the
  whole record**, because every timestep lives in its own global chunk. Spatial
  subsetting trims memory, **not** read volume.
- A 30-year hourly read ≈ 30 × 365 × 24 ≈ 2.6 × 10⁵ global chunks ≈ **~1 TB**.
- Therefore: do **one** big read+reduce to **daily max over the domain**, cache
  it, and do all fitting/iteration from the cache. The read is the expensive,
  one-time step.

**Check first:** is there a pre-aggregated **daily** 0.25° ARCO-ERA5 product
(daily max / daily mean 2m temperature)? If so, use it — it removes the 24× hourly
penalty. If not, read hourly and reduce.

### Resource plan (≤ 24 CPUs — enforce this)

- One global cap. Suggest a config knob, e.g. `config.MAX_WORKERS = int(os.environ.get("FE_MAX_WORKERS", "24"))`, and use it everywhere.
- **`grid.py` currently sets `_FIT_WORKERS = max(1, (os.cpu_count() or 2) - 1)`** —
  on a fat cluster node this blows past 24. **Change it to `min(MAX_WORKERS, ...)`.**
  Audit every `ProcessPoolExecutor` / `cpu_count()` for the same.
- Dask for the read+reduce: `LocalCluster(n_workers=…, threads_per_worker=…)` with
  `n_workers × threads_per_worker ≤ 24`. The read is IO-bound (favour threads); the
  GEV fits are CPU-bound (favour processes). A reasonable split: read with ~8
  workers × 3 threads; fit with 24 processes × 1 thread. Never exceed 24 total.
- Set Dask temp/spill to node-local scratch, not `$HOME`.

### Suggested staging (each cached so it's resumable — see §7 on caches)

1. **Read+reduce** ERA5T 0.25° hourly → **daily-max** over the domain → **annual
   TXx** per cell. Cache the annual-TXx field (Europe 0.25°, 30–60 yr ≈ a few
   hundred MB; trivially cacheable as netCDF/zarr under `cache/`). *This is the
   ~TB read.*
2. **Fit** NS-GEV per 0.25° cell from the cached annual maxima (GMST covariate;
   `gev.fit_nonstationary`, scale held constant for obs per
   `config.OBS_FIT_SCALE_COVARIATE = False`). ~10⁴ cells, embarrassingly parallel.
3. **CMIP6 change factors at 0.25°.** Reuse `cmip6.py` / the `grid.py` approach
   (24 models, ensemble-median `dloc/dscale per °GWL`). Models are coarse
   (~1–2.5°); interpolate the change-factor fields to 0.25° (bilinear/nearest) —
   applying coarse change factors to a fine present fit is a **documented
   approximation**; state it in `RESULTS.md` and the methods page.
4. **Event field at 0.25°.** The blend (`blend.live_event_value`) already runs at
   0.25° hourly + forecast; currently `grid.event_field()` regrids it to 1.5°.
   Add a path that keeps native 0.25° over the domain (needs cfgrib/eccodes — see
   §7 env). Find the hottest **metropolitan-France** cell → the France peak.
5. **Assemble** `france_peak` (and optional 0.25° map cells) → JSON.

---

## 4. France masking

"Metropolitan France" must exclude Spain/Italy/sea inside the bbox. Reuse the
country geometry we already vendor: `web/src/data/europe_borders.json.js` builds a
clipped GeoJSON from `world-atlas` (the `France` feature is metropolitan-only after
our antimeridian/overseas clipping). Point-in-polygon the 0.25° cells against the
France polygon (e.g. `shapely`/`regionmask`, or a simple ray-cast) to restrict the
France-peak search. France bbox for a first cut: `[-5.0, 41.0, 9.5, 51.5]`
(`config.REGIONS["france"]["bbox"]`).

---

## 5. Frontend wiring (light)

- **Headline**: read `live.france_peak`, render the local-peak sentence + a small
  return-period sparkline or a "1-in-N now → 1-in-M at +2 °C" phrase. Reuse
  `oneInN()` from `web/src/components/gev.js`.
- **Optional maps**: add `local_txx` to the metric toggle and to the
  intensity/frequency maps. The map code already supports per-cell `rl`/`rp`/`x_obs`
  and a level slider including the historical stops; a higher-res `grid_*.json`
  drops in with no structural change (heavier payload — consider downsampling for
  display or topojson-style quantization).

---

## 6. Acceptance criteria

- `france_peak.value` lands in a defensible range for the event (~40–42 °C; note
  the residual ERA5 cool bias vs stations).
- The France-peak rarity is monotonic along the axis (rarer in the past, common in
  the future) and uses the **same** present baseline as the rest of the tool
  (1.3603; see §7).
- The existing France-average headline, line plots, and maps are **unchanged and
  still work**.
- **All emitted JSON is finite** — `null`, never `Infinity`/`NaN` (see §7).
  `node -e "require('./output/live_france.json')"` must parse.
- Peak job CPU usage stays **≤ 24** (verify with `htop`/the scheduler).
- `RESULTS.md` + the methods page document: the new metric, the 0.25° source, the
  coarse-change-factor-on-fine-present approximation, and the ERA5-vs-station gap.

---

## 7. Gotchas / lessons already learned (read before coding)

- **JSON non-finite kills the browser.** Python's `json.dump` writes `Infinity`/
  `-Infinity`/`NaN`, which `JSON.parse` rejects (we hit this twice). Emit **`null`**
  for: return periods beyond the GEV bound (`p ≤ 0`), `isf` lower-tail (`-inf` when
  `p_now ≥ 1`, i.e. common cells), and any non-finite. Guard every value; consider
  `json.dump(..., allow_nan=False)` to fail loud in testing.
- **Present baseline is trend-based.** `gmst.present_anomaly()` returns the end
  point of a 30-yr OLS trend (≈ **1.3603 °C**), not a decadal mean — keep using it
  so the France peak is consistent with everything else. (`config.GMST_*`,
  `[[present-day-gmst-trend-method]]`.)
- **`--reuse-event` pattern.** `grid.py build_grid(reuse_event=...)` recomputes
  GEV fields while reusing a prior event field, so you can iterate the climatology
  without re-running the forecast blend (no cfgrib needed, live event fixed). Mirror
  this for the hi-res job: separate the expensive present-climatology read from the
  cheap re-assembly.
- **Caches resume.** `cache/` (gitignored) holds the ERA5 present fit and per-CMIP6
  model fits; per-model files mean a killed run resumes from where it stopped. Cache
  the 0.25° daily/annual-max field the same way so the TB read happens once.
- **GEV convention**: `shape == genextreme c == −ξ`; `shape > 0` ⇒ bounded above
  (events can be "beyond the bound" ⇒ exceedance 0 ⇒ never). `return_level(T, …)`
  is the quantile (always finite within the support).
- **d3-geo ring winding** (frontend only): bbox polygons must be wound **clockwise**
  (lon/lat, north up) or d3 reads them as the global complement.

### Environment

A working local venv used **Python 3.9** with: `numpy pandas scipy xarray "zarr<3"
gcsfs dask intake-esm aiohttp requests`. **No cfgrib/eccodes needed** unless you
re-run the live blend/forecast (step §3.4) — that needs `cfgrib eccodes` (the
ecCodes C library; conda is the path of least resistance on a cluster). `requirements.txt`
lists the full set. ARCO-ERA5 (GCS) and the Pangeo CMIP6 catalog are public/anon
(`storage_options={"token": "anon"}`).

### Reproduce the current state on the cluster

```bash
git clone <this repo>; cd futureevent
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt        # add cfgrib/eccodes via conda if doing the blend
# sanity: open the stores
python -c "from precompute import era5, cmip6; era5._open_reference(); print(len(cmip6.available_models()))"
```

---

## 8. Open questions for the owner (decide before/at kickoff)

1. **Climatology period** for the 0.25° present fit — full **1959–2021** (max
   sample, biggest read) or **1991–2020** (30 maxima, ~half the read)? GEV is fine
   with 30; more is better for the tail.
2. **Maps at 0.25°?** Headline France-peak is the must-have. Full-Europe 0.25° maps
   are "almost free on read but heavy on fit + payload" — do them, or France-only,
   or skip for v1?
3. **"France peak" definition** — hottest single 0.25° cell in metropolitan France
   on the peak day (proposed), or a small-area (e.g. 99th-percentile cell) to avoid
   one-gridbox noise?
4. **Headline framing** — show local peak *and* France-average side by side, or
   lead with the local peak and relegate the average?
