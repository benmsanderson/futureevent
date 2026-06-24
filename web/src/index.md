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

## Where it gets more likely

The spatial complement: at each cell, how much more likely an event of the local
intensity becomes at a chosen warming level, relative to today. Redder is a
larger increase in the odds.

```js
const grid = await FileAttachment("data/grid_europe.json").json();
```

```js
const mapGwl = grid
  ? view(Inputs.radio(grid.warming_levels, {value: "2.0", label: "Warming level (°C)"}))
  : null;
```

```js
function ratioMap(grid, metric, gwl, width) {
  const cells = grid.metrics[metric].cells.filter(d => d.ratio[gwl] != null);
  const boxes = Object.values(lookup.regions).map(r => ({
    x1: r.bbox[0], y1: r.bbox[1], x2: r.bbox[2], y2: r.bbox[3], name: r.name
  }));
  const maxRatio = Math.max(10, d3.quantile(cells, 0.98, d => d.ratio[gwl]) ?? 10);
  return Plot.plot({
    width,
    height: Math.round(width * 0.62),
    marginLeft: 44,
    aspectRatio: 1 / Math.cos((46 * Math.PI) / 180),
    x: {label: "Longitude", grid: false},
    y: {label: "Latitude", grid: false},
    color: {
      type: "log", scheme: "YlOrRd", clamp: true,
      domain: [1, maxRatio], legend: true,
      label: `× more likely at +${gwl} °C vs today`
    },
    marks: [
      Plot.cell(cells, {
        x: "lon", y: "lat", fill: d => Math.max(1, d.ratio[gwl]), inset: -0.5,
        tip: true,
        channels: {
          "lon": "lon", "lat": "lat",
          "event value (°C)": "x_obs",
          "now (1-in, yr)": "present_rp",
          [`at +${gwl} (1-in, yr)`]: d => d.rp[gwl],
          [`× vs now`]: d => d.ratio[gwl]
        }
      }),
      Plot.rect(boxes, {x1: "x1", y1: "y1", x2: "x2", y2: "y2",
        stroke: "#1a1a1a", strokeWidth: 1.2, fill: "none"}),
      Plot.frame({stroke: "#ccc"})
    ]
  });
}
```

```js
grid && mapGwl
  ? ratioMap(grid, metric, mapGwl, width)
  : html`<div class="note">The spatial probability-ratio map is produced by the
      gridded precompute (<code>output/grid_europe.json</code>). Run
      <code>python -m precompute.grid</code> to enable this panel.</div>`
```

```js
grid
  ? html`<div class="note">${grid.metrics[metric].cells.length} cells on the
      ${grid.grid_deg}° reference grid, ${grid.n_models} CMIP6 models. The boxes
      outline the predefined regions.</div>`
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
