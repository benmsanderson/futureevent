---
title: France · June 2026 heat in a warming climate
---

```js
import {evaluate, oneInN, returnLevel} from "./components/gev.js";
import {STR, locPhrase} from "./components/i18n.js";
const lookup = await FileAttachment("data/lookup.json").json();
const live = await FileAttachment("data/live_france.json").json();
const region = "france";
```

```js
// Language toggle (English default), persisted across reloads. `lang` is "en"|"fr".
const langInput = Inputs.radio(new Map([["English", "en"], ["Français", "fr"]]), {
  value: (typeof localStorage !== "undefined" && localStorage.getItem("fe-lang")) || "en"
});
langInput.classList.add("lang-toggle");
langInput.addEventListener("input", () => {
  try { localStorage.setItem("fe-lang", langInput.value); } catch (e) {}
});
const lang = view(langInput);
```

```js
const T = STR[lang];
// Observable Framework has no `md` global; our dictionary strings carry trusted
// inline HTML, so render them by setting innerHTML on an element.
const el = (tag, htmlStr, cls) => {
  const e = document.createElement(tag);
  e.innerHTML = htmlStr;
  if (cls) e.className = cls;
  return e;
};
```

```js
display(el("h1", T.title))
```

```js
const metric = view(Inputs.radio(T.metricOptions,
  {value: "regional_mean_tasmax", label: T.metricLabel}));
```

```js
const node = lookup.regions[region].metrics[metric];
const liveMetric = live.metrics[metric];
const xObs = liveMetric.x_obs_reference_footing;
const ev = evaluate(lookup, region, metric, xObs);
const presentAnom = lookup.metadata.present_gmst_anom;
const at2 = ev.warmingLevels["2.0"];
```

```js
display(el("div", T.headline({
  xObs: xObs.toFixed(1),
  day: liveMetric.peak_day,
  rpNow: oneInN(ev.present.returnPeriod, lang),
  pct: (100 * ev.present.exceedanceProb).toFixed(0),
  rp2: oneInN(at2.returnPeriod, lang),
  ratio: at2.ratioVsPresent.toFixed(0)
}), "headline"))
```

```js
// Local peak: the single hottest metropolitan-France 0.25° gridbox for the
// event (live.france_peak, from the local_txx precompute). Shown only if the
// local-peak precompute has run; the France-wide average above stays the lead.
//
// The framing is adaptive and honest, with three regimes for the hottest cell:
//   1. always-hot region (rp ~1 yr): the local peak is not the story — the
//      event's France-wide *extent* is — so we say that.
//   2. genuinely rare and on-scale (5 ≤ rp < cap): "1-in-N now → 1-in-M at +2 °C".
//   3. off the charts (rp at the RP_DISPLAY_CAP, here 1000): the value is so far
//      out of that cell's range that the per-cell GEV is capped/degenerate — and
//      the +2 °C number is capped too, so the now→+2 comparison is meaningless.
//      We say "off the charts" and drop the comparison rather than print
//      "1-in-1000 becoming 1-in-1000", which reads as nonsense.
const RP_DISPLAY_CAP = 1000; // matches precompute config.RP_DISPLAY_CAP
const fp = live.france_peak ?? null;
const fpRp = fp?.present?.return_period_years ?? null;
const fp2 = fp?.warming_levels?.["2.0"] ?? null;
const fp2Rp = fp2?.return_period_years ?? null;
const fpLoc = locPhrase(fp, lang);
// Render an HTML string inside the styled local-headline box.
const localBox = (s) => display(el("div", s, "headline headline-local"));
if (fp) {
  const value = fp.value.toFixed(1);
  if (fpRp != null && fpRp >= RP_DISPLAY_CAP) {
    // regime 3: off the charts
    localBox(T.localOffCharts({value, loc: fpLoc, cap: RP_DISPLAY_CAP}));
  } else if (fpRp != null && fpRp >= 5) {
    // regime 2: genuinely rare and on-scale. Only show the +2 °C shift when it is
    // a meaningful, non-capped, lower value (warming makes the event more common).
    const showShift = fp2Rp != null && fp2Rp < fpRp && fp2Rp < RP_DISPLAY_CAP;
    localBox(T.localRare({value, loc: fpLoc,
      rpText: oneInN(fpRp, lang), rp2Text: oneInN(fp2Rp, lang), showShift}));
  } else {
    // regime 1: always-hot cell — extent is the story
    localBox(T.localExtent({value, loc: fpLoc}));
  }
}
```

```js
// Forecast caveat — shown only while the event peak is still forecast-sourced
// (peak_source is a forecast cycle, not "ERA5T"). Auto-hides once reanalysis
// covers the peak and the live data refreshes.
if (!/ERA5T/i.test(liveMetric.peak_source ?? "")) {
  display(el("div", T.forecastNotice, "forecast-notice"));
}
```

```js
display(el("div", T.note1, "note"));
display(el("div", T.note2, "note"));
```

```js
display(el("h2", T.headingOdds))
```

```js
// Short axis labels for each level; historical levels (below the present anomaly)
// are placed before "now" so the axis reads cool → warm.
const SHORT_LABEL = T.shortLabel;
// Clamp return periods so an essentially-never historical point (the event can
// exceed the distribution's bound in a cooler climate) still fits the axis.
const RP_CHART_MAX = 400;
const rpLevels = Object.entries(ev.warmingLevels).map(([g, v]) => ({
  gwl: +g, label: SHORT_LABEL[g] ?? `+${g}`, rp: v.returnPeriod
}));
const rpData = [
  ...rpLevels.filter((l) => l.gwl < presentAnom),
  {gwl: presentAnom, label: T.now, rp: ev.present.returnPeriod},
  ...rpLevels.filter((l) => l.gwl >= presentAnom)
].sort((a, b) => a.gwl - b.gwl).map((l) => ({
  ...l,
  y: Math.min(l.rp, RP_CHART_MAX),
  text: (!isFinite(l.rp) || l.rp > RP_CHART_MAX)
    ? T.fmtRp(null)
    : T.tickOneIn(l.rp < 10 ? l.rp.toFixed(1) : Math.round(l.rp))
}));
```

```js
Plot.plot({
  width,
  height: 320,
  marginLeft: 64,
  x: {label: T.axisWarming, domain: [-0.15, 3.2], grid: true},
  y: {type: "log", label: T.axisReturnPeriod, grid: true, domain: [1, RP_CHART_MAX * 1.4]},
  marks: [
    Plot.line(rpData, {x: "gwl", y: "y", stroke: "#b30000", strokeWidth: 2}),
    Plot.dot(rpData, {x: "gwl", y: "y", fill: "#b30000", r: 5}),
    Plot.text(rpData, {x: "gwl", y: "y", text: "text", dy: -12, fontWeight: 600}),
    Plot.ruleX([presentAnom], {stroke: "#888", strokeDasharray: "3,3"})
  ]
})
```

```js
display(el("p", T.rpCaption))
```

```js
display(el("h2", T.headingSameHeat))
```

```js
display(el("p", T.panelIntro))
```

```js
const panelLevels = Object.entries(node.warming_levels).map(([g, p]) => ({
  gwl: +g, label: SHORT_LABEL[g] ?? `+${g} °C`, par: p
}));
const panels = [
  ...panelLevels.filter((p) => p.gwl < presentAnom),
  {gwl: presentAnom, label: T.now, par: node.gev_present},
  ...panelLevels.filter((p) => p.gwl >= presentAnom)
].sort((a, b) => a.gwl - b.gwl);
const periods = d3.range(0, 1).flatMap(() =>
  d3.ticks(Math.log10(1.2), Math.log10(500), 60).map(e => Math.pow(10, e)));
const curve = panels.flatMap(pl =>
  periods.map(Tp => ({
    panel: pl.label,
    T: Tp,
    value: returnLevel(Tp, pl.par.shape, pl.par.loc, pl.par.scale)
  })));
```

```js
Plot.plot({
  width,
  height: 260,
  marginLeft: 52,
  marginBottom: 44,
  fx: {label: null, domain: panels.map(p => p.label)},
  x: {type: "log", label: T.axisReturnPeriod, ticks: [2, 5, 10, 20, 50, 100, 200], grid: true},
  y: {label: `${node.units === "degC" ? "°C" : node.units}`, grid: true},
  marks: [
    Plot.line(curve, {fx: "panel", x: "T", y: "value", stroke: "#b30000", strokeWidth: 1.8}),
    Plot.ruleY([xObs], {stroke: "#222", strokeDasharray: "4,3"}),
    Plot.frame({stroke: "#ddd"})
  ]
})
```

```js
const borders = await FileAttachment("data/europe_borders.json").json();
// Coarse 1.5° Europe grid — used (experimentally) for the return-period map.
const grid = await FileAttachment("data/grid_europe.json").json();
```

```js
// Shared map plumbing for both spatial panels.

// Build a closed-ring GeoJSON polygon from a [lonMin, latMin, lonMax, latMax]
// bbox. The ring must be wound clockwise (in lon/lat with north up) so d3-geo /
// Plot treats the *rectangle* as the polygon interior; counter-clockwise winding
// is read as the complement (whole globe minus the box), which fits the
// projection to the world and shrinks the map to a dot.
function bboxPolygon([x0, y0, x1, y1]) {
  return {type: "Polygon", coordinates: [[
    [x0, y0], [x0, y1], [x1, y1], [x1, y0], [x0, y0]
  ]]};
}

// Per-cell GEV tails can blow up just under a bounded upper limit (a single cell
// can read 1-in-100000); clamp so colour and tooltips stay sane.
const RP_CAP = 200;
const RP_COLOUR_MAX = 100;
const round1 = (x) => Math.round(x * 10) / 10;
// Return period for display: null means the event exceeds the distribution's
// upper bound in that climate (essentially never). Localised via the string table.
const fmtRp = T.fmtRp;
// Human label for a level in a colour-legend / caption context.
const LEVEL_LABEL = T.levelLabel;
// Ordered slider stops (cool → warm) for the local-peak maps; keys are
// language-neutral, names are localised.
const LEVEL_KEYS = ["0.0", "1.0", "now", "1.5", "2.0", "3.0"];
const LEVEL_NAMES = T.levelNames;
const NOW_INDEX = 2;
// Plain-language readout for each slider stop: the warming amount (bold, neutral)
// and a one-line, localised description of what that climate is.
const GWL_DEG = ["0 °C", "+1 °C", `+${round1(lookup.metadata.present_gmst_anom)} °C`,
  "+1.5 °C", "+2 °C", "+3 °C"];
const GWL_BLURB = T.gwlBlurb;
// Weather-map style discrete bands: filled categories + contour lines.
const TEMP_THRESHOLDS = [21, 24, 27, 30, 33, 36, 39];
const TEMP_COLORS = ["#ffffb2", "#fee391", "#fec44f", "#fe9929", "#ec7014",
  "#cc4c02", "#a40d0d", "#6d0000"];
const RP_THRESHOLDS = [2, 5, 10, 30, 100];
// Return-period bins run frequent → rare (short → long return period). Colour
// runs deep purple (happens all the time) → grey (once-in-a-lifetime), so the
// striking purple marks where today's heat is already routine.
const RP_COLORS = ["#5e2d91", "#8a63b0", "#27a8c4", "#74cddd", "#9aa1ab", "#c7ccd1"];

// Sea/land basemap, projection and frame. `box` (a [lon0,lat0,lon1,lat1] bbox)
// overrides the framing — used to clip the coarse Europe grid to France.
function mapBase(grid, borders, width, box) {
  const bb = box ?? grid.bbox;
  const domain = bboxPolygon(bb);
  const [x0, y0, x1, y1] = bb;
  const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  const aspect = ((x1 - x0) * Math.PI / 180) / (mercY(y1) - mercY(y0));
  return {
    width, height: Math.round(width / aspect),
    projection: {type: "mercator", domain},
    under: [Plot.geo(domain, {fill: "#dce7f0"}), Plot.geo(borders, {fill: "#f4f2ec"})],
    over: [
      Plot.geo(borders, {stroke: "#8c949e", strokeWidth: 0.6, fill: "none"}),
      Plot.frame({stroke: "#ccc"})
    ]
  };
}

function rpAtLevel(d, level) {
  const v = level === "now" ? d.present_rp : d.rp[level];
  return v == null ? null : Math.min(v, RP_CAP);
}

// Per-°C location response of the metric's distribution (how much a fixed return
// level shifts per degree of global warming), from the obs-anchored point fit.
function intensityScaling(metric) {
  // Null for metrics that live only in the grid (e.g. local_txx) and have no
  // point fit in the lookup.
  const node = lookup.regions[region].metrics[metric];
  return node ? node.scaling_per_gwl.dloc_dGWL : null;
}

// Temperature of an *equally rare* event at a warming level. Prefer the gridded
// per-cell return level (d.rl); otherwise fall back to the regional intensity
// scaling. For a degenerate cell (null rl) of a grid-only metric there is no
// scaling, so leave it unshaded (NaN → transparent in the raster).
function tempAtLevel(d, metric, level) {
  if (level === "now") return d.x_obs;
  if (d.rl && d.rl[level] != null) return d.rl[level];
  const s = intensityScaling(metric);
  return s == null ? NaN : d.x_obs + s * (Number(level) - lookup.metadata.present_gmst_anom);
}

// Weather-map style local-peak field: filled discrete bands plus thin contour
// lines, from the 0.25° local_txx grid. `field` picks the quantity per cell.
function localContourMap(g, borders, width, opts) {
  const base = mapBase(g, borders, width, opts.bbox);
  const cells = g.metrics[opts.metricKey].cells;
  return Plot.plot({
    ...base,
    color: {type: "threshold", domain: opts.thresholds, range: opts.colors,
      legend: true, label: opts.label, tickFormat: opts.tickFormat},
    marks: [
      ...base.under,
      // Base fill. A raster paints every pixel, so a *uniform* field still fills:
      // at +3 °C every cell is already 1-in-1, and Plot.contour alone draws
      // nothing when there are no bands to contour (which made the +3 °C map look
      // blank instead of solidly "happens all the time"). Coarse pixelSize keeps
      // it cheap.
      Plot.raster(cells, {
        x: "lon", y: "lat", fill: opts.field,
        interpolate: "barycentric", pixelSize: 6, blur: opts.blur ?? 2,
        clip: borders
      }),
      // Smooth weather-style band edges on top; its opaque fill covers the raster
      // wherever the field actually varies, so banded regions look identical.
      Plot.contour(cells, {
        x: "lon", y: "lat", fill: opts.field,
        interpolate: "barycentric", pixelSize: 6, blur: opts.blur ?? 2,
        thresholds: opts.thresholds,
        stroke: opts.iso, strokeWidth: 0.5, strokeOpacity: 0.5, clip: borders
      }),
      ...base.over,
      Plot.dot(cells, {x: "lon", y: "lat", r: 5, fill: "transparent", stroke: "none",
        tip: true, channels: opts.channels})
    ]
  });
}

function localTempMap(g, borders, level, width) {
  return localContourMap(g, borders, width, {
    metricKey: "local_txx",
    thresholds: TEMP_THRESHOLDS, colors: TEMP_COLORS, iso: "#7f2704",
    tickFormat: (d) => `${d}°`,
    label: level === "now" ? T.tempMapNow : T.tempMapLevel(LEVEL_LABEL[level]),
    field: (d) => tempAtLevel(d, "local_txx", level),
    channels: {
      [`${T.now} (°C)`]: (d) => round1(d.x_obs),
      "1850–1900 (°C)": (d) => round1(tempAtLevel(d, "local_txx", "0.0")),
      "+2 °C (°C)": (d) => round1(tempAtLevel(d, "local_txx", "2.0")),
      "+3 °C (°C)": (d) => round1(tempAtLevel(d, "local_txx", "3.0"))
    }
  });
}

function localRpMap(g, borders, metric, level, width) {
  return localContourMap(g, borders, width, {
    metricKey: metric,
    bbox: lookup.regions[region].bbox, // clip the coarse Europe grid to France
    blur: 7, // wider averaging kernel — smooths the coarse 1.5° field
    thresholds: RP_THRESHOLDS, colors: RP_COLORS, iso: "#33333a",
    tickFormat: (d) => T.tickOneIn(d),
    label: T.rpMapLabel(level === "now" ? T.now : LEVEL_LABEL[level]),
    field: (d) => rpAtLevel(d, level) ?? RP_CAP,
    channels: {
      [T.now]: (d) => fmtRp(d.present_rp),
      "1850–1900": (d) => fmtRp(d.rp["0.0"]),
      "+2 °C": (d) => fmtRp(d.rp["2.0"]),
      "+3 °C": (d) => fmtRp(d.rp["3.0"])
    }
  });
}
```

```js
display(el("h2", T.headingSeeHeat))
```

```js
display(el("p", T.seeHeatIntro))
```

```js
const gridHires = await FileAttachment("data/grid_france_hires.json").json();
```

```js
const levelIdx = view(Inputs.range([0, 5], {step: 1, value: NOW_INDEX, label: T.sliderLabel}));
```

```js
const mapLevel = LEVEL_KEYS[Math.round(levelIdx)];
```

```js
html`<div class="gwl-readout">
  <div class="gwl-deg">${GWL_DEG[Math.round(levelIdx)]}<small> ${T.ofGlobalWarming}</small></div>
  <div class="gwl-sub"><b>${LEVEL_NAMES[Math.round(levelIdx)]}</b> — ${GWL_BLURB[Math.round(levelIdx)]}</div>
</div>`
```

```js
const mapView = view((() => {
  const r = Inputs.radio([T.tabHot, T.tabOften], {value: T.tabHot});
  r.classList.add("map-tabs");
  return r;
})());
```

```js
// Read-this-first guidance, above the map so it isn't missed. Phrased to keep the
// "comparable event, not average summer" anchor explicit for both views.
display(el("div", mapView === T.tabHot ? T.mapGuideHot : T.mapGuideOften, "map-guide"))
```

```js
mapView === T.tabHot
  ? localTempMap(gridHires, borders, mapLevel, width)
  : localRpMap(grid, borders, metric, mapLevel, width)
```

```js
display(el("h2", T.headingBuilt))
```

```js
const bp = live.blend_provenance;
display(el("div", T.provenance({
  era5t: bp.era5t_last_day,
  cycles: bp.cycles_used.join(", "),
  bias: bp.forecast_bias_vs_era5t,
  offset: live.era5t_ref_offset,
  src: liveMetric.peak_source,
  day: liveMetric.peak_day
}), "provenance"))
```
