# Methods and provenance

```js
const lookup = await FileAttachment("data/lookup.json").json();
const md = lookup.metadata;
```

This tool places an observed or forecast heat extreme in the context of a
warming climate. It is **contextualization, not attribution**: it does not make a
formal causal statement about this specific event, but shows how rare an event of
this magnitude is now and how rare it becomes at higher global warming levels.

## Method in brief

- **Present-day rarity is observation-anchored.** A non-stationary GEV is fit to
  observed annual block maxima of the event metric, with the observed global-mean
  temperature anomaly (relative to 1850-1900) as a covariate, so the present-day
  distribution accounts for warming to date. The current-climate return period
  comes from observations, not from model tails. The present-day GMST level is
  the end point of a linear trend over the most recent 30 complete years, which
  estimates warming *now* rather than a flat decadal mean (centred several years
  in the past), following the Indicators of Global Climate Change.
- **Future panels come from CMIP6 change factors.** The model ensemble is used
  only for the response: the shift in GEV location and scale per degree of
  additional global warming. Those per-degree change factors are applied to the
  observation-anchored GEV as deltas from the present.
- **A global-warming-level axis**, not scenario-by-year: +1.5, +2, +3 °C relative
  to 1850-1900.

## Two representations: France-wide average vs local peak

The headline figure and the first two maps use **France-wide / coarse-gridbox
averages** of daily maximum temperature on the 1.5° 6-hourly reference footing.
This is honest about scale: it reads several °C below the station values in the
news, because it averages cooler regions, coasts, and high ground.

Alongside it the tool shows a **local peak** (`local_txx`): the per-cell annual
maximum daily-max on the **0.25° hourly ERA5T** product, over metropolitan
France. This resolves the afternoon peak and inland cities, so it reads much
closer to station-scale heat. The **France-peak headline** is the single hottest
metropolitan-France 0.25° cell for the event.

- **Source / footing.** `local_txx` is fit directly on ERA5T 0.25° hourly, so the
  event value sits on that same native footing — no reference-product offset (the
  1.5° pipeline needs one; this one does not). The present climatology uses the
  1991–2020 period (30 annual maxima).
- **Future shift — a documented approximation.** CMIP6 change factors are fit at
  the models' native (coarse, ~1–2.5°) resolution and then interpolated to the
  0.25° grid before being applied as deltas to the fine present fit. Applying a
  coarse change factor to a fine present distribution is an approximation: it
  carries the large-scale warming response, not fine-scale changes in the
  response itself.
- **ERA5 vs stations.** Even the 0.25° local peak is a gridbox mean, so it runs
  roughly **1–2 °C below the hottest individual station** (a known ERA5 cool
  bias). The displayed local-peak value is honest about being a gridbox figure,
  not a station record.
- **Metropolitan France only.** Cells are masked to the Natural Earth France
  polygon, excluding Spain, Italy, and sea inside the bounding box.

## Data sources

```js
html`<table class="prov">
  <tr><th>Reference distribution</th><td>${md.datasets.reference} (${md.datasets.reference_period})</td></tr>
  <tr><th>Live event value</th><td>${md.datasets.event_value_source}, blended with ECMWF IFS HRES open data</td></tr>
  <tr><th>Future scaling</th><td>${md.datasets.scaling}</td></tr>
  <tr><th>Warming level</th><td>${md.datasets.scaling_gwl_from}</td></tr>
  <tr><th>Observed GMST covariate</th><td>${md.gmst_covariate_source}</td></tr>
  <tr><th>Present GMST anomaly</th><td>+${md.present_gmst_anom} °C vs ${md.gwl_baseline}
    ${md.present_gmst_rate_per_decade ? html` (warming ${md.present_gmst_rate_per_decade} °C/decade)` : ""}</td></tr>
  ${md.present_gmst_method ? html`<tr><th>Present level method</th><td>${md.present_gmst_method}</td></tr>` : ""}
</table>`
```

${md.present_gmst_citation ? html`<p class="note">Present-day warming is estimated
as the end point of a trend rather than a flat decadal mean, following the
Indicators of Global Climate Change: ${md.present_gmst_citation}.</p>` : ""}

## CMIP6 models used

```js
const models = lookup.regions.france.metrics.regional_mean_tasmax.scaling_per_gwl.models;
html`<p>${models.length} models (member r1i1p1f1, historical + ssp585):
  <span class="models">${models.join(", ")}</span>.</p>`
```

## Sensitivity cross-check

The observed GMST sensitivity is kept as a check against the CMIP per-degree
scaling; a large disagreement is flagged rather than averaged over.

```js
const cc = lookup.regions.france.sensitivity_crosscheck;
html`<table class="prov">
  <tr><th>Metric</th><th>Observed dloc/dGMST</th><th>CMIP dloc/dGWL</th><th>Ratio</th><th>Flagged</th></tr>
  ${Object.entries(cc).map(([k, v]) => html`<tr>
    <td>${k}</td><td>${v.obs_dloc_dGMST}</td><td>${v.cmip_dloc_dGWL}</td>
    <td>${v.ratio}</td><td>${v.flagged_disagreement ? "yes" : "no"}</td></tr>`)}
</table>`
```

## Documented offsets

${html`<p>${lookup.metadata.offsets_note}</p>`}

## Statistical convention

${html`<p>${lookup.metadata.gev_convention}</p>`}

## Licensing and citation

ERA5 is produced by the Copernicus Climate Change Service (C3S); use is governed
by the Copernicus licence and ERA5 should be cited per the C3S terms. CMIP6 data
are made available under the terms of the participating modelling groups; the
ssp585 and historical experiments and the listed source models should be cited
per CMIP6 / WCRP terms. ECMWF open data is published under CC-BY-4.0. The
NOAAGlobalTemp series stands in for HadCRUT5 in this build. The present-day
warming level follows the Indicators of Global Climate Change (Forster et al.,
2024, _Earth Syst. Sci. Data_ **16**, 2625–2658,
[doi:10.5194/essd-16-2625-2024](https://doi.org/10.5194/essd-16-2625-2024)).
