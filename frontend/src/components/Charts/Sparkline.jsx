import React from 'react';

/**
 * A tile-sized trend: one 2px navy line and a dot on the latest value, no
 * axes. It gives a count its shape over the period; the exact monthly
 * numbers are in the Month by month table, and the <title> names the low and
 * high months for anyone who cannot see the line.
 *
 * Drawn as SVG in CSS colours rather than with Chart.js: dozens of tiny
 * canvases cost more than they show.
 *
 * Props:
 *   points  [{ label, value }] in time order; fewer than 2 draws nothing
 *   label   what is counted, for the <title>
 *   width, height  viewBox size; the SVG scales to its box keeping its shape
 */

const fmt = (n) => Number(n.toFixed(1));

/** "x,y x,y …" for a polyline; the highest value touches the top. */
export function sparkPoints(values, width, height, pad = 2) {
  if (values.length < 2) return '';
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const step = (width - 2 * pad) / (values.length - 1);
  return values
    .map((v, i) => {
      const y = hi === lo ? height / 2 : pad + ((hi - v) / (hi - lo)) * (height - 2 * pad);
      return `${fmt(pad + i * step)},${fmt(y)}`;
    })
    .join(' ');
}

/** "lowest 2 in Jan 2026, highest 10 in Nov 2025"; first month on ties. */
export function sparkSummary(points) {
  if (!points.length) return '';
  let low = points[0];
  let high = points[0];
  points.forEach((p) => {
    if (p.value < low.value) low = p;
    if (p.value > high.value) high = p;
  });
  return `lowest ${low.value} in ${low.label}, highest ${high.value} in ${high.label}`;
}

export default function Sparkline({ points = [], label, width = 120, height = 32 }) {
  const line = sparkPoints(points.map((p) => p.value), width, height, 3);
  if (!line) return null;
  const [lastX, lastY] = line.split(' ').pop().split(',');

  return (
    <svg className="an-spark" viewBox={`0 0 ${width} ${height}`} role="img">
      <title>{`${label}: ${sparkSummary(points)}`}</title>
      <polyline
        points={line}
        fill="none"
        stroke="var(--db-navy)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* A ring in the surface colour keeps the dot readable on the line */}
      <circle cx={lastX} cy={lastY} r="2.5" fill="var(--db-navy)" stroke="var(--db-white)" strokeWidth="1.5" />
    </svg>
  );
}
