# France: June 2026 heat in a warming climate

```js
import {evaluate, oneInN, returnLevel} from "./components/gev.js";
const lookup = await FileAttachment("data/lookup.json").json();
const live = await FileAttachment("data/live_france.json").json();
const region = "france";
```

```js
const metric = view(Inputs.radio(
  new Map([
    ["Hottest day (France-wide average)", "regional_mean_tasmax"],
    ["Hottest 3-day spell (France-wide average)", "tx3x"]
  ]),
  {value: "regional_mean_tasmax", label: "Metric"}
));
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
html`<div class="headline">
  The current event (<b>${xObs.toFixed(1)} &deg;C</b>, ${node.name.toLowerCase()},
  peaking ${liveMetric.peak_day}) is
  <b>${oneInN(ev.present.returnPeriod)}</b> in today's climate
  (about ${(100 * ev.present.exceedanceProb).toFixed(1)}% per year).
  At <b>+2 &deg;C</b> of global warming it becomes <b>${oneInN(at2.returnPeriod)}</b>,
  roughly <b>${at2.ratioVsPresent.toFixed(0)}&times;</b> more likely.
</div>`
```

```js
// Local peak: the single hottest metropolitan-France 0.25° gridbox for the
// event (live.france_peak, from the local_txx precompute). Shown only if the
// local-peak precompute has run; the France-wide average above stays the lead.
//
// The framing is adaptive and honest. A local peak is a "rare" story only where
// the hottest cell's own climatology makes the value unusual. For a broad-but-
// moderate event the hottest cell sits in an always-hot region (return period
// ~1 yr), where the exceptional thing is the event's France-wide *extent*, not
// the local peak — so we say that, rather than quoting a misleading 1-in-1 that
// barely shifts with warming. A future event with a genuinely rare local peak
// (rp ≥ 5) gets the "1-in-N now → 1-in-M at +2 °C" framing instead.
const fp = live.france_peak ?? null;
const fpRp = fp?.present?.return_period_years ?? null;
const fp2 = fp?.warming_levels?.["2.0"] ?? null;
const fpLoc = fp
  ? (fp.nearest_place ?? `at ${fp.lat.toFixed(2)}°N, ${Math.abs(fp.lon).toFixed(2)}°${fp.lon < 0 ? "W" : "E"}`)
  : "";
// This block declares variables, so its trailing expression is NOT
// auto-displayed — render explicitly with display().
if (fp) {
  display(fpRp != null && fpRp >= 5
    ? html`<div class="headline headline-local">
        Locally, the peak reached <b>${fp.value.toFixed(1)} &deg;C</b> ${fpLoc}
        — about <b>${oneInN(fpRp)}</b> in today's climate${fp2 && fp2.return_period_years != null
          ? html`, becoming <b>${oneInN(fp2.return_period_years)}</b> at <b>+2 &deg;C</b>` : ""}.
      </div>`
    : html`<div class="headline headline-local">
        Locally, the hottest gridbox reached <b>${fp.value.toFixed(1)} &deg;C</b> ${fpLoc}
        — hot, but not a local record (about what that always-warm spot sees in a
        typical summer). This event's exceptionality is its <b>France-wide extent</b>:
        the area average above is the rare part, not any single local peak.
      </div>`);
}
```

<div class="note">This value is a <b>France-wide average</b> of daily maximum
temperature on a coarse reference footing (1.5°, 6-hourly ERA5) — not a local
reading. Individual stations peak several °C higher (around 42 °C locally in this
event); the area average is lower because it includes cooler regions, coasts, and
high ground. The rarity is computed against a climatology on the <i>same</i>
footing, so the odds are consistent even though the temperature reads below
headline station values.</div>

<div class="note">This places the event in the context of a warming climate. It
is contextualization, not a formal attribution of this specific event.</div>

## How the odds shift along the warming axis

```js
// Short axis labels for each level; historical levels (below the present anomaly)
// are placed before "now" so the axis reads cool → warm.
const SHORT_LABEL = {
  "0.0": "1850–1900", "1.0": "~1 °C", "1.5": "+1.5 °C", "2.0": "+2 °C", "3.0": "+3 °C"
};
// Clamp return periods so an essentially-never historical point (the event can
// exceed the distribution's bound in a cooler climate) still fits the axis.
const RP_CHART_MAX = 400;
const rpLevels = Object.entries(ev.warmingLevels).map(([g, v]) => ({
  gwl: +g, label: SHORT_LABEL[g] ?? `+${g}`, rp: v.returnPeriod
}));
const rpData = [
  ...rpLevels.filter((l) => l.gwl < presentAnom),
  {gwl: presentAnom, label: "now", rp: ev.present.returnPeriod},
  ...rpLevels.filter((l) => l.gwl >= presentAnom)
].sort((a, b) => a.gwl - b.gwl).map((l) => ({
  ...l,
  y: Math.min(l.rp, RP_CHART_MAX),
  text: (!isFinite(l.rp) || l.rp > RP_CHART_MAX)
    ? "never"
    : `1-in-${l.rp < 10 ? l.rp.toFixed(1) : Math.round(l.rp)}`
}));
```

```js
Plot.plot({
  width,
  height: 320,
  marginLeft: 64,
  x: {label: "Global warming level (°C above 1850-1900)", domain: [-0.15, 3.2], grid: true},
  y: {type: "log", label: "Return period (years)", grid: true, domain: [1, RP_CHART_MAX * 1.4]},
  marks: [
    Plot.line(rpData, {x: "gwl", y: "y", stroke: "#b30000", strokeWidth: 2}),
    Plot.dot(rpData, {x: "gwl", y: "y", fill: "#b30000", r: 5}),
    Plot.text(rpData, {x: "gwl", y: "y", text: "text", dy: -12, fontWeight: 600}),
    Plot.ruleX([presentAnom], {stroke: "#888", strokeDasharray: "3,3"})
  ]
})
```

Lower on this axis means rarer. The same event sits near the top of the present
distribution and moves down toward "common" as warming increases.

## The distribution at each warming level

Each panel is the return-level curve for that climate: the value you expect once
per the return period on the horizontal axis. The dashed line marks the current
event; where it crosses each curve is its rarity in that climate.

```js
const panelLevels = Object.entries(node.warming_levels).map(([g, p]) => ({
  gwl: +g, label: SHORT_LABEL[g] ?? `+${g} °C`, par: p
}));
const panels = [
  ...panelLevels.filter((p) => p.gwl < presentAnom),
  {gwl: presentAnom, label: "Now", par: node.gev_present},
  ...panelLevels.filter((p) => p.gwl >= presentAnom)
].sort((a, b) => a.gwl - b.gwl);
const periods = d3.range(0, 1).flatMap(() =>
  d3.ticks(Math.log10(1.2), Math.log10(500), 60).map(e => Math.pow(10, e)));
const curve = panels.flatMap(pl =>
  periods.map(T => ({
    panel: pl.label,
    T,
    value: returnLevel(T, pl.par.shape, pl.par.loc, pl.par.scale)
  })));
```

```js
Plot.plot({
  width,
  height: 260,
  marginLeft: 52,
  marginBottom: 44,
  fx: {label: null, domain: panels.map(p => p.label)},
  x: {type: "log", label: "Return period (years)", ticks: [2, 5, 10, 20, 50, 100, 200], grid: true},
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
// Slider stops: two cooler historical reference climates, "Now", then the
// future warming levels. 0.0 = 1850–1900 pre-industrial; 1.0 ≈ the mid-2010s.
const LEVELS = new Map([
  ["1850–1900", "0.0"], ["Recent (~1 °C)", "1.0"], ["Now", "now"],
  ["+1.5 °C", "1.5"], ["+2 °C", "2.0"], ["+3 °C", "3.0"]
]);
// Return period for display: null means the event exceeds the distribution's
// upper bound in that climate (essentially never).
const fmtRp = (v) => (v == null ? "never" : `1-in-${Math.round(v)}`);
// Human label for a level in a colour-legend / caption context.
const LEVEL_LABEL = {
  "0.0": "in 1850–1900", "1.0": "at ~1 °C (recent past)", "now": "now",
  "1.5": "at +1.5 °C", "2.0": "at +2 °C", "3.0": "at +3 °C"
};
// Ordered slider stops (cool → warm) for the local-peak maps, and their labels.
const LEVEL_KEYS = ["0.0", "1.0", "now", "1.5", "2.0", "3.0"];
const LEVEL_NAMES = ["1850–1900", "Recent ~1 °C", "Now", "+1.5 °C", "+2 °C", "+3 °C"];
const NOW_INDEX = 2;
// Weather-map style discrete bands: filled categories + contour lines.
const TEMP_THRESHOLDS = [21, 24, 27, 30, 33, 36, 39];
const TEMP_COLORS = ["#ffffb2", "#fee391", "#fec44f", "#fe9929", "#ec7014",
  "#cc4c02", "#a40d0d", "#6d0000"];
const RP_THRESHOLDS = [2, 5, 10, 30, 100];
const RP_COLORS = ["#c7ccd1", "#9aa1ab", "#74cddd", "#27a8c4", "#8a63b0", "#5e2d91"];

// Sea/land basemap, projection and frame shared by both maps.
function mapBase(grid, borders, width) {
  const domain = bboxPolygon(grid.bbox);
  const regions = Object.values(lookup.regions).map((r) => bboxPolygon(r.bbox));
  const [x0, y0, x1, y1] = grid.bbox;
  const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  const aspect = ((x1 - x0) * Math.PI / 180) / (mercY(y1) - mercY(y0));
  return {
    width, height: Math.round(width / aspect),
    projection: {type: "mercator", domain},
    under: [Plot.geo(domain, {fill: "#dce7f0"}), Plot.geo(borders, {fill: "#f4f2ec"})],
    over: [
      Plot.geo(borders, {stroke: "#8c949e", strokeWidth: 0.5, fill: "none"}),
      Plot.geo(regions, {stroke: "#1a1a1a", strokeWidth: 1.3, fill: "none"}),
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
  const base = mapBase(g, borders, width);
  const cells = g.metrics[opts.metricKey].cells;
  return Plot.plot({
    ...base,
    color: {type: "threshold", domain: opts.thresholds, range: opts.colors,
      legend: true, label: opts.label, tickFormat: opts.tickFormat},
    marks: [
      ...base.under,
      Plot.contour(cells, {
        x: "lon", y: "lat", fill: opts.field,
        interpolate: "barycentric", blur: 2, thresholds: opts.thresholds,
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
    label: level === "now"
      ? "Local peak reached (°C)"
      : `Local peak of an equally rare event ${LEVEL_LABEL[level]} (°C)`,
    field: (d) => tempAtLevel(d, "local_txx", level),
    channels: {
      "now (°C)": (d) => round1(d.x_obs),
      "1850–1900 (°C)": (d) => round1(tempAtLevel(d, "local_txx", "0.0")),
      "+2 °C (°C)": (d) => round1(tempAtLevel(d, "local_txx", "2.0")),
      "+3 °C (°C)": (d) => round1(tempAtLevel(d, "local_txx", "3.0"))
    }
  });
}

function localRpMap(g, borders, metric, level, width) {
  return localContourMap(g, borders, width, {
    metricKey: metric,
    thresholds: RP_THRESHOLDS, colors: RP_COLORS, iso: "#33333a",
    tickFormat: (d) => `1-in-${d}`,
    label: `How often this event recurs ${level === "now" ? "now" : LEVEL_LABEL[level]} (1-in-N yr)`,
    field: (d) => rpAtLevel(d, level) ?? RP_CAP,
    channels: {
      "now": (d) => fmtRp(d.present_rp),
      "1850–1900": (d) => fmtRp(d.rp["0.0"]),
      "+2 °C": (d) => fmtRp(d.rp["2.0"]),
      "+3 °C": (d) => fmtRp(d.rp["3.0"])
    }
  });
}
```

## The local peak in a warming climate

Two views of the **0.25° local peak** (`local_txx`) over metropolitan France —
how hot an *equally rare* local peak would be, and how *often* this peak recurs —
as the climate shifts. Filled bands with contour lines, weather-map style. Slide
from the pre-industrial **1850–1900** climate up toward **+3 °C**.

```js
const gridHires = await FileAttachment("data/grid_france_hires.json").json();
```

```js
const levelIdx = gridHires
  ? view(Inputs.range([0, 5], {step: 1, value: NOW_INDEX, label: "Global warming",
      format: (i) => LEVEL_NAMES[Math.round(i)]}))
  : NOW_INDEX;
```

```js
const mapLevel = LEVEL_KEYS[Math.round(levelIdx)];
```

```js
html`<div class="note">Showing the <b>${LEVEL_NAMES[Math.round(levelIdx)]}</b> climate.
  <b>Now</b> is today — about <b>+${round1(lookup.metadata.present_gmst_anom)} °C</b> above
  1850&ndash;1900 (a 30-year trend through &approx;2025). <b>Recent &sim;1 °C</b> is the
  climate of the <b>mid-2010s</b> (global warming first reached &sim;1 °C around 2015).
  +1.5/+2/+3 °C are global-warming levels relative to pre-industrial.</div>`
```

### How hot — the local peak temperature

```js
gridHires
  ? localTempMap(gridHires, borders, mapLevel, width)
  : html`<div class="note">The local-peak map comes from the 0.25° precompute
      (<code>output/grid_france_hires.json</code>). Run
      <code>python -m precompute.local_peak</code> to enable it.</div>`
```

```js
gridHires
  ? html`<div class="note">${gridHires.metrics.local_txx.cells.length} cells on a
      ${gridHires.grid_deg}° grid over metropolitan France; present climatology
      ${gridHires.climatology_period.join("&ndash;")}. The hottest cell is
      ${round1(d3.max(gridHires.metrics.local_txx.cells, (d) => d.x_obs))} °C — a 0.25°
      gridbox local daily-max from hourly ERA5T, still ~1&ndash;2 °C under the hottest
      station. Filled bands are 3 °C wide; contour lines mark the band edges.</div>`
  : null
```

### How rare — how often this event recurs (coarse grid)

*Experimental: this panel uses the coarse **1.5° Europe** grid (the France-wide
average metric selected above), not the 0.25° local peak — it shows the dome
footprint more clearly.*

```js
grid ? localRpMap(grid, borders, metric, mapLevel, width) : null
```

```js
grid
  ? html`<div class="note">Return period of the ${node.name.toLowerCase()} against
      each 1.5° cell's own climatology — grey where it is a common value,
      cyan-to-purple where rare. ${grid.n_models} CMIP6 models. Coarse gridbox
      footing, so the absolute °C are below station peaks; the rarity is internally
      consistent.</div>`
  : null
```

## What the current value is built from

```js
const bp = live.blend_provenance;
html`<div class="provenance">
  Live value blends ERA5T reanalysis (through <b>${bp.era5t_last_day}</b>) with the
  ECMWF HRES forecast (cycles ${bp.cycles_used.join(", ")}), bias-corrected by
  ${bp.forecast_bias_vs_era5t} &deg;C onto the reanalysis and shifted
  ${live.era5t_ref_offset} &deg;C onto the reference footing. Peak from
  <b>${liveMetric.peak_source}</b> on ${liveMetric.peak_day}.
  See <a href="./methods">Methods and provenance</a>.
</div>`
```
