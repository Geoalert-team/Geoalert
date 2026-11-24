import React, { useState } from 'react';
import { SEVERITY_WORD, smallChanceText } from '../Forecast/forecastLevels';
import { severityInfo } from './hazardInfo';

const TOP = 5;

/**
 * A barangay's puroks by their chance of a fire in the period ("Likely by
 * month"), from the fire risk model's purok rows: the 5 most likely, then
 * "Show all". Each shows its level word, its chance and, when its figures
 * are uncertain, "Limited data".
 *
 * rows        the barangay's `purok_results` rows (/api/history/forecast/)
 * purokNames  purok id (string) → name
 */
export default function LikelyPuroks({ rows, purokNames }) {
  const [all, setAll] = useState(false);
  const sorted = [...(rows || [])].sort((a, b) => b.probability - a.probability || a.purok_id - b.purok_id);
  if (!sorted.length) {
    return <p className="pm-muted">No purok figures for this barangay in this period.</p>;
  }
  const shown = all ? sorted : sorted.slice(0, TOP);
  return (
    <>
      <ul className="pm-likely-list">
        {shown.map((r) => {
          const sev = severityInfo(r.level);
          return (
            <li key={r.purok_id}>
              <span className="pm-likely-dot" style={{ background: sev.color }} aria-hidden="true" />
              <span className="pm-likely-name">
                <strong>{purokNames?.get(String(r.purok_id)) || `Area ${r.purok_id}`}</strong>
                {r.limited_data && <small className="pm-likely-tag">Limited data</small>}
              </span>
              <span className="pm-likely-figure">
                {SEVERITY_WORD[r.level] || r.level}, {smallChanceText(r.probability)}
              </span>
            </li>
          );
        })}
      </ul>
      {sorted.length > TOP && (
        <button type="button" className="pm-likely-more" onClick={() => setAll((v) => !v)}>
          {all ? `Show the top ${TOP}` : `Show all ${sorted.length}`}
        </button>
      )}
    </>
  );
}
