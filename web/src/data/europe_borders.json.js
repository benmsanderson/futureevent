// Data loader: country outlines for the spatial map basemap.
// Reads the Natural Earth 1:50m countries from the world-atlas npm package and
// emits a GeoJSON FeatureCollection trimmed to the European map domain, so the
// probability-ratio map renders over recognisable land/borders rather than a
// blank background.
//
// IMPORTANT: several countries carry far-flung territories in one feature (e.g.
// France includes Guadeloupe ~-61°E and Réunion ~+56°E). Those must be dropped,
// not just the feature kept — otherwise the feature's longitude span (-68..56)
// blows up the map's fitted extent and shrinks Europe to a dot. We therefore
// clip at the *polygon* (ring-group) level, keeping only the pieces that fall in
// the domain, and round coordinates to ~1 km to keep the payload small.
import {createRequire} from "node:module";
import {feature} from "topojson-client";

const require = createRequire(import.meta.url);
const topo = require("world-atlas/countries-50m.json");

// A margin beyond the gridded precompute domain so coastlines/borders reach the
// frame edge.
const DOMAIN = {lonMin: -12, lonMax: 27, latMin: 34, latMax: 58};

// Sutherland-Hodgman clip of a polygon ring against the axis-aligned domain
// rectangle, so geometry that runs far outside Europe (e.g. Russia east of the
// Urals, which even crosses the antimeridian) is cut at the frame rather than
// stretching the fitted extent. Returns a closed ring, or [] if fully outside.
function clipRing(ring) {
  const {lonMin, lonMax, latMin, latMax} = DOMAIN;
  const pts = ring[0][0] === ring[ring.length - 1][0] &&
              ring[0][1] === ring[ring.length - 1][1]
    ? ring.slice(0, -1) : ring.slice();
  const clip = (input, inside, isect) => {
    const out = [];
    for (let i = 0; i < input.length; i++) {
      const A = input[(i + input.length - 1) % input.length], B = input[i];
      const Ain = inside(A), Bin = inside(B);
      if (Bin) { if (!Ain) out.push(isect(A, B)); out.push(B); }
      else if (Ain) out.push(isect(A, B));
    }
    return out;
  };
  let r = pts;
  r = clip(r, p => p[0] >= lonMin, (a, b) => [lonMin, a[1] + (lonMin - a[0]) / (b[0] - a[0]) * (b[1] - a[1])]);
  r = clip(r, p => p[0] <= lonMax, (a, b) => [lonMax, a[1] + (lonMax - a[0]) / (b[0] - a[0]) * (b[1] - a[1])]);
  r = clip(r, p => p[1] >= latMin, (a, b) => [a[0] + (latMin - a[1]) / (b[1] - a[1]) * (b[0] - a[0]), latMin]);
  r = clip(r, p => p[1] <= latMax, (a, b) => [a[0] + (latMax - a[1]) / (b[1] - a[1]) * (b[0] - a[0]), latMax]);
  return r.length >= 3 ? [...r, r[0]] : [];
}

// Clip every polygon of a feature to the domain; drop empties.
function clipPolygons(geom) {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  const kept = [];
  for (const poly of polys) {
    const outer = clipRing(poly[0]);
    if (!outer.length) continue;
    const rings = [outer];
    for (const hole of poly.slice(1)) {
      const h = clipRing(hole);
      if (h.length) rings.push(h);
    }
    kept.push(rings);
  }
  return kept;
}

const round2 = (c) => typeof c[0] === "number"
  ? [Math.round(c[0] * 100) / 100, Math.round(c[1] * 100) / 100]
  : c.map(round2);

const fc = feature(topo, topo.objects.countries);
const features = [];
for (const f of fc.features) {
  if (f.geometry.type !== "Polygon" && f.geometry.type !== "MultiPolygon") continue;
  const kept = clipPolygons(f.geometry).map(round2);
  if (!kept.length) continue;
  features.push({
    type: "Feature",
    properties: {name: f.properties.name},
    geometry: kept.length === 1
      ? {type: "Polygon", coordinates: kept[0]}
      : {type: "MultiPolygon", coordinates: kept},
  });
}

process.stdout.write(JSON.stringify({type: "FeatureCollection", features}));
