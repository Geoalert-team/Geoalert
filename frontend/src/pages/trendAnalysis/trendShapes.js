// Hazard ordering shared by the Trend Analysis sections and its CSV.

const ORDER = ['Fire', 'Flood', 'Landslide'];
export const UNSPECIFIED = 'Unspecified';

function rank(name) {
  if (name === UNSPECIFIED) return [2, 0, ''];
  const i = ORDER.indexOf(name);
  return i >= 0 ? [0, i, ''] : [1, 0, name];
}

/** Fire, Flood, Landslide, then others by name, Unspecified last. */
export function sortHazards(names) {
  return [...names].sort((a, b) => {
    const [x, y] = [rank(a), rank(b)];
    return x[0] - y[0] || x[1] - y[1] || x[2].localeCompare(y[2]);
  });
}

/** The hazard types a trends answer counts (the server lists those in play). */
export function hazardsIn(trends) {
  const names = new Set();
  [...(trends.series || []), ...(trends.month_of_year || [])]
    .forEach((row) => Object.keys(row.counts || {}).forEach((n) => names.add(n)));
  return sortHazards(names);
}
