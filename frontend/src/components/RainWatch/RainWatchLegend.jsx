import React from 'react';
import {
  RAIN_WATCH_NOTE, RAIN_WATCH_CREDITS, hoursSince, rainLevel, updatedText,
} from './rainWatchLevels';
import './rainWatch.css';

const hasLevel = (data, level) => (data?.days || []).some((d) => (d.barangays || []).some(
  (b) => b.flood?.level === level || b.landslide?.level === level,
));

// The legend block for the Next 3 days view: colours, age, disclaimer, credits
// failed: the request for the rain watch failed and there is no earlier answer
export default function RainWatchLegend({ data, failed = false, now = Date.now() }) {
  const hours = hoursSince(data?.updated_at, now);
  const outOfDate = hours == null || !!data?.stale;
  const age = hours == null
    ? (!data && failed ? 'Rain watch could not be loaded. Trying again.' : 'No forecast yet')
    : data.stale
      ? `Out of date: last forecast ${Math.floor(hours)} h ago`
      : updatedText(data.updated_at, now);
  // Yellow only reaches staff, so its row shows only when the answer has some
  const rows = ['Red', 'Orange', ...(hasLevel(data, 'Yellow') ? ['Yellow'] : []), 'none', ...(outOfDate ? ['unknown'] : [])];
  return (
    <div className="rw-legend">
      <p className="pm-legend-title">Rain watch: next 3 days</p>
      <ul>
        {rows.map((k) => (
          <li key={k}>
            <span
              className="pm-legend-swatch"
              style={{
                background: rainLevel(k).color || 'transparent',
                opacity: k === 'unknown' ? 0.5 : 1,
                border: k === 'none' ? '1px dashed #9aa3b2' : undefined,
              }}
            />
            {rainLevel(k).label}
          </li>
        ))}
      </ul>
      <p className={`pm-legend-note ${outOfDate ? 'rw-stale' : ''}`}>{age}</p>
      <p className="pm-legend-note">{RAIN_WATCH_NOTE}</p>
      <p className="pm-legend-note">{RAIN_WATCH_CREDITS}</p>
    </div>
  );
}
