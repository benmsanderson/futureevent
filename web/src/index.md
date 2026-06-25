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
    ["Hottest day (regional mean)", "regional_mean_tasmax"],
    ["Hottest 3 days (TX3x)", "tx3x"]
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

<div class="note">This places the event in the context of a warming climate. It
is contextualization, not a formal attribution of this specific event.</div>

## How the odds shift along the warming axis

```js
const rpData = [
  {level: presentAnom, label: "now", rp: ev.present.returnPeriod, kind: "now"},
  ...Object.entries(ev.warmingLevels).map(([g, v]) => ({
    level: +g, label: `+${g}`, rp: v.returnPeriod, kind: "future"
  }))
];
```

```js
Plot.plot({
  width,
  height: 320,
  marginLeft: 64,
  x: {label: "Global warming level (°C above 1850-1900)", domain: [1, 3.2], grid: true},
  y: {type: "log", label: "Return period (years)", grid: true,
      domain: [1, Math.max(120, ev.present.returnPeriod * 1.2)]},
  marks: [
    Plot.line(rpData, {x: "level", y: "rp", stroke: "#b30000", strokeWidth: 2}),
    Plot.dot(rpData, {x: "level", y: "rp", fill: "#b30000", r: 5}),
    Plot.text(rpData, {x: "level", y: "rp", text: d => `1-in-${d.rp < 10 ? d.rp.toFixed(1) : Math.round(d.rp)}`,
      dy: -12, fontWeight: 600}),
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
const panels = [
  {key: "present", label: "Now", par: node.gev_present},
  ...Object.entries(node.warming_levels).map(([g, p]) => ({key: g, label: `+${g} °C`, par: p}))
];
const periods = d3.range(0, 1).flatMap(() =>
  d3.ticks(Math.log10(1.2), Math.log10(500), 60).map(e => Math.pow(10, e)));
const curve = panels.flatMap(pl =>
  periods.map(T => ({
    panel: pl.label,
    order: pl.key === "present" ? 0 : +pl.key,
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
const grid = await FileAttachment("data/grid_europe.json").json();
const borders = await FileAttachment("data/europe_borders.json").json();
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
const LEVELS = new Map([
  ["Now", "now"], ["+1.5 °C", "1.5"], ["+2 °C", "2.0"], ["+3 °C", "3.0"]
]);

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
  return lookup.regions[region].metrics[metric].scaling_per_gwl.dloc_dGWL;
}

// Temperature of an *equally rare* event at a warming level. If the gridded
// precompute supplies per-cell return levels (d.rl), use them; otherwise shift
// the observed value by the regional intensity scaling (a uniform first-order
// approximation pending the gridded return-level rebuild).
function tempAtLevel(d, metric, level) {
  if (level === "now") return d.x_obs;
  if (d.rl && d.rl[level] != null) return d.rl[level];
  return d.x_obs + intensityScaling(metric) * (Number(level) - lookup.metadata.present_gmst_anom);
}
```

## How hot — an equally rare event in a warmer world

This map holds the event's **rarity** fixed and asks how **hot** it would be.
*Now* is the temperature the event actually reached; drag **Global warming**
upward and each cell shows how hot an *equally rare* event becomes as the climate
warms — the same once-in-a-generation heat, hotter.

```js
const heatLevel = grid
  ? view(Inputs.radio(LEVELS, {value: "now", label: "Global warming"}))
  : null;
```

```js
function intensityMap(grid, borders, metric, level, width) {
  const base = mapBase(grid, borders, width);
  const cells = grid.metrics[metric].cells;
  // Fix the colour domain across all levels so the warmer-world shift is visible.
  const lo = d3.min(cells, (d) => d.x_obs);
  const hi = d3.max(cells, (d) => tempAtLevel(d, metric, "3.0"));
  return Plot.plot({
    ...base,
    color: {
      type: "linear", scheme: "YlOrRd", clamp: true, domain: [lo, hi], legend: true,
      label: level === "now"
        ? "Temperature reached (°C)"
        : `Temperature of an equally rare event at +${level} °C`
    },
    marks: [
      ...base.under,
      Plot.raster(cells, {
        x: "lon", y: "lat", fill: (d) => tempAtLevel(d, metric, level),
        interpolate: "barycentric", blur: 3, clip: borders
      }),
      ...base.over,
      Plot.dot(cells, {
        x: "lon", y: "lat", r: 6, fill: "transparent", stroke: "none", tip: true,
        channels: {
          "lon": "lon", "lat": "lat",
          "held rarity (1-in)": (d) => Math.round(Math.min(d.present_rp, RP_CAP)),
          "now (°C)": (d) => round1(d.x_obs),
          "+1.5 (°C)": (d) => round1(tempAtLevel(d, metric, "1.5")),
          "+2 (°C)": (d) => round1(tempAtLevel(d, metric, "2.0")),
          "+3 (°C)": (d) => round1(tempAtLevel(d, metric, "3.0"))
        }
      })
    ]
  });
}
```

```js
grid
  ? intensityMap(grid, borders, metric, heatLevel, width)
  : html`<div class="note">The spatial maps come from the gridded precompute
      (<code>output/grid_europe.json</code>). Run
      <code>python -m precompute.grid</code> to enable them.</div>`
```

```js
grid
  ? html`<div class="note">${grid.metrics[metric].cells.length} cells on the
      ${grid.grid_deg}° reference grid. ${grid.metrics[metric].cells[0]?.rl
        ? "Equally-rare temperatures are per-cell return levels from the grid."
        : html`The warmer-world shift is approximated from the regional intensity
            response (${round1(intensityScaling(metric))} °C per °C of global
            warming, uniform across the map); per-cell return levels would come
            from the gridded precompute.`}</div>`
  : null
```

## How often — this event in a warmer world

This map holds the event's **temperature** fixed and asks how **often** it
recurs. A neutral grey scale (kept distinct from the temperature map) shows the
return period: darker is rarer. As warming rises, today's rare extreme (dark)
fades toward an ordinary year.

```js
const freqLevel = grid
  ? view(Inputs.radio(LEVELS, {value: "now", label: "Global warming"}))
  : null;
```

```js
function frequencyMap(grid, borders, metric, level, width) {
  const base = mapBase(grid, borders, width);
  const cells = grid.metrics[metric].cells;
  return Plot.plot({
    ...base,
    color: {
      type: "log", scheme: "Greys", clamp: true,
      domain: [1, RP_COLOUR_MAX], legend: true,
      ticks: [1, 3, 10, 30, 100], tickFormat: (n) => `1-in-${n}`,
      label: level === "now"
        ? "Return period now — darker is rarer"
        : `Return period at +${level} °C — darker is rarer`
    },
    marks: [
      ...base.under,
      Plot.raster(cells, {
        x: "lon", y: "lat", fill: (d) => rpAtLevel(d, level),
        interpolate: "barycentric", blur: 3, clip: borders
      }),
      ...base.over,
      Plot.dot(cells, {
        x: "lon", y: "lat", r: 6, fill: "transparent", stroke: "none", tip: true,
        channels: {
          "lon": "lon", "lat": "lat",
          "event (°C)": "x_obs",
          "now (1-in)": (d) => Math.round(Math.min(d.present_rp, RP_CAP)),
          "+1.5 (1-in)": (d) => Math.round(d.rp["1.5"]),
          "+2 (1-in)": (d) => Math.round(d.rp["2.0"]),
          "+3 (1-in)": (d) => Math.round(d.rp["3.0"])
        }
      })
    ]
  });
}
```

```js
grid ? frequencyMap(grid, borders, metric, freqLevel, width) : null
```

```js
grid
  ? html`<div class="note">${grid.metrics[metric].cells.length} cells on the
      ${grid.grid_deg}° reference grid, ${grid.n_models} CMIP6 models. Ordinary
      cells (a 1-in-1 day now) sit pale; the event's rare footprint shows dark and
      fades as warming rises. Deep-tail per-cell return periods are clamped at
      1-in-${RP_CAP}.</div>`
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
