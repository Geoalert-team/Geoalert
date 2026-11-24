// Shapes for StackedBars, kept apart from the chart so they can be tested
// without a canvas.

/**
 * rows      [{ label, counts: { [series]: n } }]
 * series    series names, in stack order
 * colorFor  series name -> hex
 * nameFor   series name -> legend label (default: the name itself)
 * -> { labels, datasets: [{ label, data, color }] }, a missing count as 0
 */
export function stackedData(rows, series, colorFor, nameFor = (s) => s) {
  return {
    labels: rows.map((r) => r.label),
    datasets: series.map((s) => ({
      label: nameFor(s),
      data: rows.map((r) => (r.counts && r.counts[s]) || 0),
      color: colorFor(s),
    })),
  };
}

/** The figures as { head, rows }, one row per label with a Total column. */
export function stackTable(labels, datasets) {
  return {
    head: ['', ...datasets.map((d) => d.label), 'Total'],
    rows: labels.map((label, i) => {
      const values = datasets.map((d) => d.data[i] || 0);
      return [label, ...values, values.reduce((a, b) => a + b, 0)];
    }),
  };
}
