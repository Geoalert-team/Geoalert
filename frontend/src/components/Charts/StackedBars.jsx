import React, { useMemo } from 'react';
import { Bar } from 'react-chartjs-2';
import ChartFrame from './ChartFrame';
import { BASE_OPTIONS, INK, axisScales } from './chartTheme';
import { stackTable } from './stackedData';

/**
 * Counts split by series in one bar: hazard types per month, severities per
 * hazard type. Build `labels` and `datasets` with stackedData().
 *
 * The tooltip lists every series in the bar and its total, and the figures
 * table underneath carries a column per series, so the split is readable
 * without telling the colours apart.
 *
 * Props:
 *   labels      category labels, in order
 *   datasets    [{ label, data, color }]
 *   horizontal  bars run left to right (default false)
 *   height      px; horizontal charts size from the row count when omitted
 *   valueHead   what is counted, for the table caption
 *   empty       message when every value is 0
 *   maxTicks    most labels on the category axis
 */
export default function StackedBars({
  labels = [],
  datasets = [],
  horizontal = false,
  height,
  valueHead = 'Events',
  empty = 'No records for these filters.',
  maxTicks,
}) {
  const total = datasets.reduce((sum, d) => sum + d.data.reduce((a, b) => a + (b || 0), 0), 0);
  const resolved = height || (horizontal ? Math.max(160, labels.length * 40 + 80) : 280);

  const data = useMemo(() => ({
    labels,
    datasets: datasets.map((d) => ({
      label: d.label,
      data: d.data,
      backgroundColor: d.color,
      // A 1px ring in the surface colour keeps stacked segments apart
      borderColor: INK.surface,
      borderWidth: 1,
      barPercentage: 0.8,
      categoryPercentage: 0.86,
    })),
  }), [labels, datasets]);

  const several = datasets.length > 1;
  const options = useMemo(() => {
    const scales = axisScales({ horizontal, maxTicks });
    scales.x.stacked = true;
    scales.y.stacked = true;
    const value = (item) => (horizontal ? item.parsed.x : item.parsed.y);
    return {
      ...BASE_OPTIONS,
      indexAxis: horizontal ? 'y' : 'x',
      interaction: { mode: 'index', intersect: false },
      scales,
      plugins: {
        ...BASE_OPTIONS.plugins,
        legend: {
          display: several,
          position: 'bottom',
          labels: { boxWidth: 10, boxHeight: 10, color: INK.body, padding: 14 },
        },
        tooltip: {
          ...BASE_OPTIONS.plugins.tooltip,
          // A segment of 0 adds nothing to the reading
          filter: (item) => value(item) > 0,
          callbacks: {
            label: (item) => ` ${item.dataset.label}: ${Number(value(item)).toLocaleString()}`,
            footer: (items) => (several
              ? `Total: ${items.reduce((sum, item) => sum + value(item), 0).toLocaleString()}`
              : ''),
          },
        },
      },
    };
  }, [horizontal, maxTicks, several]);

  const table = stackTable(labels, datasets);
  // ChartFrame draws the empty message when it gets no rows
  const rows = total > 0 ? labels.map((label) => ({ label })) : [];

  return (
    <>
      <ChartFrame height={resolved} rows={rows} empty={empty} table={false}>
        <Bar data={data} options={options} />
      </ChartFrame>
      {total > 0 && (
        <details className="ra-figures">
          <summary>Show the figures</summary>
          <div className="ra-table-scroll">
            <table className="db-table">
              <caption className="ra-sr">{valueHead}</caption>
              <thead>
                <tr>{table.head.map((h, i) => <th key={h || i} className={i ? 'ra-num' : ''}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {table.rows.map((r) => (
                  <tr key={r[0]}>
                    {r.map((v, i) => (
                      <td key={i} className={i ? 'ra-num' : ''}>{i ? Number(v).toLocaleString() : v}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </>
  );
}
