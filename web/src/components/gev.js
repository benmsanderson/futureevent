// Client-side GEV evaluation, ported from precompute/runtime.py and
// precompute/gev.py. Convention matches scipy.stats.genextreme: shape == c.
// For an annual block maximum with z = (x - loc) / scale:
//   c != 0: F(x) = exp(-(1 - c*z)^(1/c)), valid where 1 - c*z > 0
//   c == 0: F(x) = exp(-exp(-z))
// Return period of an annual maximum is T = 1 / (1 - F).

const EPS = 1e-8;

export function gevCdf(x, shape, loc, scale) {
  const z = (x - loc) / scale;
  if (Math.abs(shape) < EPS) return Math.exp(-Math.exp(-z));
  const t = 1 - shape * z;
  if (t <= 0) return shape > 0 ? 1 : 0; // beyond the bounded tail
  return Math.exp(-Math.pow(t, 1 / shape));
}

export function exceedanceProb(x, shape, loc, scale) {
  return 1 - gevCdf(x, shape, loc, scale);
}

export function returnPeriod(x, shape, loc, scale) {
  const p = exceedanceProb(x, shape, loc, scale);
  return p <= 0 ? Infinity : 1 / p;
}

// Inverse CDF (quantile) and the return level for a given period.
export function gevQuantile(f, shape, loc, scale) {
  let z;
  if (Math.abs(shape) < EPS) z = -Math.log(-Math.log(f));
  else z = (1 - Math.pow(-Math.log(f), shape)) / shape;
  return loc + scale * z;
}

export function returnLevel(period, shape, loc, scale) {
  return gevQuantile(1 - 1 / period, shape, loc, scale);
}

// Evaluate an observed value against one region/metric across present and each
// warming level, mirroring runtime.evaluate.
export function evaluate(lookup, region, metric, xObs) {
  const node = lookup.regions[region].metrics[metric];
  const present = node.gev_present;
  const pNow = exceedanceProb(xObs, present.shape, present.loc, present.scale);
  const tNow = pNow <= 0 ? Infinity : 1 / pNow;

  const levels = {};
  for (const [gwl, par] of Object.entries(node.warming_levels)) {
    const p = exceedanceProb(xObs, par.shape, par.loc, par.scale);
    levels[gwl] = {
      exceedanceProb: p,
      returnPeriod: p <= 0 ? Infinity : 1 / p,
      ratioVsPresent: pNow > 0 ? p / pNow : Infinity
    };
  }
  return {
    region, metric, xObs,
    present: {
      gmstAnom: present.ref_gmst_anom,
      exceedanceProb: pNow,
      returnPeriod: tNow
    },
    warmingLevels: levels
  };
}

// Human phrasing helpers for the headline.
export function oneInN(period) {
  if (!isFinite(period)) return "essentially never";
  if (period >= 100) return `about 1-in-${Math.round(period / 10) * 10}`;
  if (period >= 20) return `about 1-in-${Math.round(period / 5) * 5}`;
  if (period >= 3) return `about 1-in-${Math.round(period)}`;
  if (period > 1.2) return `about 1-in-${period.toFixed(1)}`;
  return "almost every year";
}
