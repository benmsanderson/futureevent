# Handover: refresh the June 2026 event on ERA5T reanalysis (centre on 24 June)

Pick this up **on the cluster, once ARCO-ERA5/ERA5T reanalysis covers 24 June 2026**
(it lags real time by ~5 days, so expect it to be readable from roughly the start
of July 2026). Self-contained: assumes no memory of the chat that produced it.

## Why

The local-peak temperature map (`local_txx`, "How hot it gets") and the
France-peak headline currently **understate this event**. Example: the Toulouse
0.25° gridbox reads `x_obs = 36.3 °C` with `present_rp = 1.6`, while stations ran
**> 40 °C for ~24–26 June**. Roughly 3 °C of that gap is the legitimate ERA5
gridbox cool bias + the map's contour blur; the remaining ~3 °C is almost
certainly because **`x_obs` is a forecast blend, not reanalysis**:

- The committed artifacts were generated **2026-06-25**, when 24 June was still in
  the **ECMWF forecast** part of the blend, not the ERA5T reanalysis part.
- `event_peak_day` is `None` in `output/grid_france_hires.json` — the event field
  never recorded which day peaked (see "Bug to fix" below), a tell that the peak
  was not pinned.
- `present_rp = 1.6` means the GEV treats 36 °C as a near-typical Toulouse year — a
  genuine 40 °C+ day would be far rarer.

Once reanalysis covers the peak, re-running the **event field only** (the
expensive 1991–2020 climatology stays cached) should raise `x_obs` toward the
observed values and let the maps/headline read at the intended station scale.

## Goal

Re-run the event field against **reanalysis** with the event **centred on
24 June 2026**, regenerate the three event-dependent artifacts, fix
`event_peak_day`, and re-validate against known station readings. The climatology
fits and CMIP6 change factors are unchanged and must **not** be recomputed.

## What re-runs vs what is reused

| Component | Action | Why |
| --- | --- | --- |
| 1991–2020 `local_txx` climatology (`era5t_hires.annual_txx_field`, per-year cache in `CACHE_DIR`) | **Reuse** | Unchanged; it is the ~1.1 TB read we must not repeat. |
| CMIP6 per-cell change factors (`local_peak.local_change_factors`, cached) | **Reuse** | Unchanged. |
| Coarse GEV fits / `lookup.json` | **Reuse** | Present distributions unchanged. |
| **Event field** (`grid.event_field`, 20-day window, cheap) | **Re-run on reanalysis** | This is the only thing that was forecast-based. |
| `output/grid_france_hires.json` (`local_txx`, France-peak) | **Regenerate** | New `x_obs` per cell + correct `event_peak_day`. |
| `output/grid_europe.json` (`regional_mean_tasmax`, `tx3x`) | **Regenerate** | New event values drive the headline France-wide value + RP maps. |
| `output/live_france.json` (live event values + `france_peak`) | **Regenerate** | Headline numbers. |

## Centre the event on 24 June

`grid.event_field` ([precompute/grid.py:264](precompute/grid.py)) reads a 20-day
window ending `blend.config_today()` and takes the **per-cell max** (TXx) over it.
`config_today()` ([precompute/blend.py:175](precompute/blend.py)) is intentionally
overridable. The window must (a) include 24 June and (b) lie entirely within
reanalysis so no day is forecast-sourced.

Pin it deterministically (do **not** rely on wall-clock "today"):

1. Add an env override to `config_today()` — read e.g. `FE_TODAY` (`YYYY-MM-DD`)
   and fall back to `datetime.now(UTC).date()`. Set `FE_TODAY=2026-07-02` (or
   later — any date by which reanalysis has cleared 24 June). The 20-day window
   then spans ~12 June–2 July, covering the whole heatwave, and
   `era5t_last >= 24 June` so the blend uses **reanalysis** for the peak with the
   forecast tail dropped (`fc_future` is empty when `today` is well past the lag).
2. Confirm the read is reanalysis-only for the peak: log `era5t_last` and assert
   `era5t_last >= 2026-06-24`. Abort if 24 June is still forecast.

Per-cell-max semantics are correct to keep (TXx = each cell's hottest day in the
window); "centred on 24 June" means the **domain** peak day should land on/near
24 June — record and report it (next section), don't hard-clip every cell to a
single calendar day.

## Bug to fix: `event_peak_day` is `None`

On a fresh (non-`--reuse-event`) run, `local_peak._event_field_local`
([precompute/local_peak.py:168](precompute/local_peak.py)) gets its peak day from
`grid.event_field`, but `event_field` returns only `{metric: array}` and **no day**
— so `ev_peak_day` is `None` and propagates to the JSON metadata.

Fix: have `event_field` also return the **domain-mean argmax day** of the blended
series (the day the area-average peaked), thread it through `build_local_peak`'s
return, and verify it serialises as `2026-06-24` (or the true peak). The front end
already surfaces `peak_day`, so this also un-blanks that.

## Commands (cluster, good-neighbour: ≤ 24 CPUs)

`config.MAX_WORKERS` caps every pool at 24 (override only downward via
`FE_MAX_WORKERS`). Do not exceed it on the shared node.

```bash
# 0. Sanity: confirm reanalysis covers 24 June before doing anything heavy.
python -c "import xarray as xr, pandas as pd; from precompute import config; \
ds=xr.open_zarr(config.ERA5T_STORE, storage_options={'token':'anon'}); \
print('ERA5T last time:', pd.Timestamp(ds.time.values.max()))"   # must be >= 2026-06-25

# 1. Regenerate the coarse grid + live event on reanalysis (event field re-run,
#    GEV fits reused). NOTE: no --reuse-event here — we WANT the fresh event.
FE_TODAY=2026-07-02 python -m precompute.grid          # -> output/grid_europe.json, live_france.json

# 2. Regenerate the fine local_txx grid + France-peak (climatology cache reused).
FE_TODAY=2026-07-02 python -m precompute.local_peak    # -> output/grid_france_hires.json, merges france_peak

# (era5t_hires climatology should hit the per-year cache and not re-read 1.1 TB;
#  if CACHE_DIR was not carried over, the climatology re-read is the expensive
#  part — budget ~2 min/year x 30 years, still <= 24 workers.)
```

## Validation (before committing)

- **`event_peak_day` is set** (≈ `2026-06-24`) in `grid_france_hires.json` and
  `live_france.json`, not `null`.
- **Toulouse rises**: the cell nearest 43.6 °N, 1.44 °E should move from ~36.3 °C
  toward the low-40s minus the ~2 °C ERA5 gridbox bias (expect ~38–40 °C); its
  `present_rp` should climb above ~1.6 accordingly.
- **France peak** (`max x_obs`) should exceed the current 37.1 °C if the event was
  hotter in reanalysis than in the forecast.
- **Headline France-wide average** (`live_france.json`) and its present return
  period — note any shift from the current ~30.5 °C / ~1-in-12.
- **Spot-check vs stations** for 24 June (Toulouse-Blagnac, Bordeaux, Carcassonne)
  and confirm the residual gap is consistent with the documented ERA5 gridbox bias
  (~1–2 °C), not several degrees.
- `allow_nan=False` still holds (all values finite; `null` never `Infinity`/`NaN`).

## Commit

- `output/grid_europe.json`, `output/grid_france_hires.json`,
  `output/live_france.json` (regenerated).
- `precompute/grid.py`, `precompute/blend.py`, `precompute/local_peak.py` (the
  `FE_TODAY` override + `event_peak_day` plumbing).
- Update `output/RESULTS.md`: the local-peak section currently concludes "broad
  but locally moderate, no cell over ~37 °C" from the **forecast** snapshot —
  revise with the reanalysis numbers and the 24 June peak day.

## Front-end follow-up (after data lands; do in the web repo)

- A push to the deploy branch touching `output/**` auto-rebuilds GitHub Pages
  (`.github/workflows/deploy-web.yml`), so the live site refreshes on commit.
- Revisit the temp-map framing once `x_obs` reflects reanalysis: if locals now
  read near-record, the "hot, but not a local record / exceptional for its
  France-wide extent" copy in `web/src/index.md` may need softening.
- Consider a small on-map caveat that values are 0.25° gridbox figures running
  ~1–2 °C below station peaks, so 38 ≠ 40 is not read as an error.
