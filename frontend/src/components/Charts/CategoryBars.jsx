import React, { useMemo } from 'react';
import { Bar } from 'react-chartjs-2';
import ChartFrame from './ChartFrame';
import { BASE_OPTIONS, INK, axisScales, barValues } from './chartTheme';

/**
 * Magnitude across a handful of named things — hazard types, severities,
 * barangays.
 *
 * Horizontal by default: category names are words, and words laid along the
 * bottom axis either collide or turn sideways. Every bar carries its value
 * as text, which is also what lets the moderate-severity amber be used at
 * all; at 2.45:1 against a white card it cannot be the only thing telling
 * two bars apart.
 *
 * Props:
 *   rows        [{ label, value, color }]
 *   horizontal  default true
 *   height      px; omit to size from the row count
 *   valueHead   table heading for the value column
 *   empty       message when there is nothing to draw
 *   thin        slimmer bars, for compact cards
 */
export default function CategoryBars({
  rows = [],
  horizontal = true,
  height,
  valueHead = 'Events',
  empty = 'No data for this filter.',
  thin = false,
}) {
  const resolved = height || Math.max(160, rows.length * (horizontal ? 38 : 46) + 60);

  const data = useMemo(() => ({
    labels: rows.map((r) => r.label),
    datasets: [{
      label: valueHead,
      data: rows.map((r) => r.value),
      backgroundColor: rows.map((r) => r.color || INK.brand),
      // A 2px ring in the surface colour keeps adjacent bars from fusing
      borderColor: INK.surface,
      borderWidth: 2,
      borderRadius: 4,
      borderSkipped: false,
      barPercentage: thin ? 0.6 : 0.75,
      categoryPercentage: 0.82,
    }],
  }), [rows, valueHead, thin]);

  const options = useMemo(() => {
    const scales = axisScales({ horizontal });
    // Leave room at the end of the bar for the printed value
    if (horizontal) scales.x.grace = '12%';
    else scales.y.grace = '14%';

    return {
      ...BASE_OPTIONS,
      indexAxis: horizontal ? 'y' : 'x',
      scales,
      plugins: {
        ...BASE_OPTIONS.plugins,
        tooltip: {
          ...BASE_OPTIONS.plugins.tooltip,
          callbacks: {
            label: (item) => {
              const n = horizontal ? item.parsed.x : item.parsed.y;
              return ` ${Number(n).toLocaleString()}`;
            },
          },
        },
      },
    };
  }, [horizontal]);

  return (
    <ChartFrame height={resolved} rows={rows} valueHead={valueHead} empty={empty}>
      <Bar data={data} options={options} plugins={[barValues]} />
    </ChartFrame>
  );
}