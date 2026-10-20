import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import { installPrintResize } from './printResize';

/**
 * One place for every chart in GeoAlert: palette, type scale, axis styling
 * and the two small plugins the charts rely on.
 *
 * Chart.js draws to a canvas, so it cannot read the CSS custom properties in
 * Dashboard.css. The hex values below mirror those tokens; if a token changes
 * there, change it here too.
 */

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

// Printed and PDF copies get charts drawn for the print layout
installPrintResize(ChartJS);

/* ---------- Ink: text and furniture, never series identity ---------- */
export const INK = {
  heading: '#1c2e4a', // --db-heading
  body:    '#43516a', // --db-body
  soft:    '#6a778d', // --db-soft
  line:    '#dde3ec', // --db-line
  surface: '#ffffff', // --db-white
  navy:    '#1c2e4a', // --db-navy
};

/* ---------- Categorical: which hazard, not how bad ----------
 * Flood and Fire are the map's own colours. Landslide is NOT: the map's
 * earth brown (#8d5a2b) fails as a chart colour twice over — its chroma is
 * low enough to read as grey against a white card, and it sits 7.6 ΔE from
 * Fire's orange under protanopia, which is below the separation floor.
 * #8a5a00 keeps the earth reading, clears the chroma floor and lifts the
 * pair to a passing distance. Pins keep the original brown; only charts
 * use this.
 */
export const HAZARD_SERIES = {
  Flood:     '#1e88e5',
  Fire:      '#f4511e',
  Landslide: '#8a5a00',
  Other:     '#43516a',
};

export function hazardSeriesColor(name) {
  if (!name) return HAZARD_SERIES.Other;
  const key = Object.keys(HAZARD_SERIES).find(
    (k) => k.toLowerCase() === String(name).toLowerCase(),
  );
  return HAZARD_SERIES[key] || HAZARD_SERIES.Other;
}

/* ---------- Status: how bad, reserved — never reused as a series ---------- */
export const SEVERITY_SERIES = {
  Red:    '#d64545', // --db-high
  Orange: '#d99a00', // --db-medium
  Green:  '#1f9d55', // --db-low
};

// Defined with the severity order in utils/severity.js, which tests can load
export { SEVERITY_LABEL } from '../../utils/severity';

export function severitySeriesColor(code) {
  return SEVERITY_SERIES[code] || INK.soft;
}

/* ---------- Shared type scale ---------- */
// The page's body face (loaded by the navbar stylesheet), so axis text
// matches the text around the chart
const FONT = {
  family: "'Atkinson Hyperlegible', 'Segoe UI', system-ui, -apple-system, sans-serif",
  size: 12,
};

/* ---------- Tooltip, styled to match the db- cards ---------- */
export const TOOLTIP = {
  backgroundColor: INK.heading,
  titleColor: '#ffffff',
  bodyColor: '#e8edf5',
  padding: 10,
  cornerRadius: 8,
  displayColors: true,
  boxWidth: 10,
  boxHeight: 10,
  boxPadding: 4,
  titleFont: { ...FONT, weight: '700' },
  bodyFont: FONT,
};

/**
 * Vertical rule under the cursor on a line chart, so a reading can be traced
 * down to its month. Chart.js has no crosshair of its own.
 */
export const crosshair = {
  id: 'geoalertCrosshair',
  afterDatasetsDraw(chart) {
    const active = chart.tooltip?.getActiveElements?.() || [];
    if (!active.length) return;
    const { ctx, chartArea } = chart;
    const x = active[0].element.x;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.lineWidth = 1;
    ctx.strokeStyle = INK.line;
    ctx.stroke();
    ctx.restore();
  },
};

/**
 * Prints each bar's value at its end. Keeps the numbers visible without a
 * third dependency, and carries the labelling that the amber severity colour
 * needs — at 2.45:1 against white it cannot be the only thing distinguishing
 * a bar.
 */
export const barValues = {
  id: 'geoalertBarValues',
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    const horizontal = chart.options.indexAxis === 'y';
    ctx.save();
    ctx.fillStyle = INK.body;
    ctx.font = `700 11px ${FONT.family}`;
    ctx.textBaseline = 'middle';

    chart.data.datasets.forEach((dataset, i) => {
      const meta = chart.getDatasetMeta(i);
      if (meta.hidden) return;
      meta.data.forEach((bar, index) => {
        const value = dataset.data[index];
        if (value === null || value === undefined) return;
        const text = Number(value).toLocaleString();
        if (horizontal) {
          ctx.textAlign = 'left';
          ctx.fillText(text, bar.x + 6, bar.y);
        } else {
          ctx.textAlign = 'center';
          ctx.fillText(text, bar.x, bar.y - 9);
        }
      });
    });
    ctx.restore();
  },
};

/* ---------- Axes: recessive, so the data reads first ---------- */
export function axisScales({ horizontal = false, maxTicks } = {}) {
  const valueAxis = {
    beginAtZero: true,
    border: { display: false },
    grid: { color: INK.line, drawTicks: false },
    ticks: {
      color: INK.soft,
      font: FONT,
      padding: 8,
      // Counts are whole events; half an incident is not a thing
      precision: 0,
    },
  };

  const labelAxis = {
    border: { color: INK.line },
    grid: { display: false },
    ticks: {
      color: INK.soft,
      font: FONT,
      padding: 6,
      autoSkip: true,
      maxTicksLimit: maxTicks,
      maxRotation: 0,
    },
  };

  return horizontal
    ? { x: valueAxis, y: labelAxis }
    : { x: labelAxis, y: valueAxis };
}

export const BASE_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 220 },
  // A resize redraws at once: the root duration above would otherwise
  // animate it, and a print snapshot taken mid-way shows squeezed lines
  transitions: { resize: { animation: { duration: 0 } } },
  plugins: {
    legend: { display: false },
    tooltip: TOOLTIP,
  },
};