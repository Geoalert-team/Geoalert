import React, { useMemo } from 'react';
import { Line } from 'react-chartjs-2';
import ChartFrame from './ChartFrame';
import { BASE_OPTIONS, INK, axisScales, crosshair } from './chartTheme';
import { withAlpha } from '../../utils/color';

/**
 * Events over time. One series, so no legend — the card's heading names it.
 *
 * A line rather than bars: this answers "is it getting worse?", and sixty
 * monthly bars answer that badly. Points are hidden on a long series and
 * shown on a short one, with a hit radius wider than the mark either way, so
 * the tooltip is catchable without the line turning into beads.
 *
 * Props:
 *   points   [{ label, value }] in time order
 *   height   px
 *   color    line colour (hex), default navy; the fill under it follows
 *   unit     { one, many } naming what is counted, for the tooltip
 *   table    false when the caller shows the numbers in its own table
 *   empty    message when there is nothing to draw
 */
const EVENTS = { one: 'event', many: 'events' };

export default function TrendLine({
  points = [],
  height = 280,
  color = INK.navy,
  unit = EVENTS,
  table = true,
  empty = 'No data for this filter.',
}) {
  const dense = points.length > 24;

  const data = useMemo(() => ({
    labels: points.map((p) => p.label),
    datasets: [{
      label: 'Events',
      data: points.map((p) => p.value),
      borderColor: color,
      borderWidth: 2,
      tension: 0.25,
      // Monotone: the curve never bends above or below the counts it joins
      cubicInterpolationMode: 'monotone',
      fill: true,
      backgroundColor: (ctx) => {
        const { chartArea, ctx: c } = ctx.chart;
        if (!chartArea) return 'transparent';
        const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
        g.addColorStop(0, withAlpha(color, 0.14));
        g.addColorStop(1, withAlpha(color, 0));
        return g;
      },
      pointRadius: dense ? 0 : 4,
      pointHoverRadius: 5,
      pointBackgroundColor: color,
      // A 2px ring in the surface colour, so a point sitting on the line
      // still reads as a point
      pointBorderColor: INK.surface,
      pointBorderWidth: 2,
      pointHitRadius: 14,
    }],
  }), [points, color, dense]);

  const options = useMemo(() => ({
    ...BASE_OPTIONS,
    interaction: { mode: 'index', intersect: false },
    scales: axisScales({ maxTicks: dense ? 8 : 12 }),
    plugins: {
      ...BASE_OPTIONS.plugins,
      tooltip: {
        ...BASE_OPTIONS.plugins.tooltip,
        callbacks: {
          label: (item) => {
            const n = item.parsed.y;
            return ` ${n} ${n === 1 ? unit.one : unit.many}`;
          },
        },
      },
    },
  }), [dense, unit]);

  const valueHead = unit.many.charAt(0).toUpperCase() + unit.many.slice(1);

  return (
    <ChartFrame height={height} rows={points} valueHead={valueHead} table={table} empty={empty}>
      <Line data={data} options={options} plugins={[crosshair]} />
    </ChartFrame>
  );
}