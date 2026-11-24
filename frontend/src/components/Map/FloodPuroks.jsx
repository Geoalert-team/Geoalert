import React, { useState } from 'react';
import { FLOOD_WORD, NOT_ASSESSED } from '../Forecast/forecastLevels';
import { severityInfo } from './hazardInfo';

const TOP = 5;
const RANK = { Red: 3, Orange: 2, Green: 1 };

/**
 * A barangay's puroks by flood susceptibility ("Likely by month" with Flood
 * ticked), from the flood model's rows: the 5 most flood-prone, then "Show
 * all"; the areas not assessed are grouped under their reason. Susceptibility
 * says how flood-prone an area is, not that a flood is coming.
 *
 * rows        the barangay's `flood_results` rows (/api/history/forecast/)
 * purokNames  purok id (string) → name
 */
export default function FloodPuroks({ rows, purokNames }) {
  const [all, setAll] = useState(false);
  if (!(rows || []).length) {
    return <p className="pm-muted">No flood levels for this barangay.</p>;
  }
  const assessed = rows.filter((r) => r.level)
    .sort((a, b) => RANK[b.level] - RANK[a.level] || a.purok_id - b.purok_id);
  const reasons = new Map();
  rows.filter((r) => !r.level).forEach((r) => {
    reasons.set(r.not_assessed_reason, (reasons.get(r.not_assessed_reason) || 0) + 1);
  });
  const shown = all ? assessed : assessed.slice(0, TOP);
  return (
    <>
      {assessed.length > 0 && (
        <ul className="pm-likely-list">
          {shown.map((r) => (
            <li key={r.purok_id}>
              <span className="pm-likely-dot" style={{ background: severityInfo(r.level).color }} aria-hidden="true" />
              <span className="pm-likely-name">
                <strong>{purokNames?.get(String(r.purok_id)) || `Area ${r.purok_id}`}</strong>
                {r.uncertain && <small className="pm-likely-tag">Uncertain</small>}
                {r.estimated_outline && <small className="pm-likely-tag">Estimated outline</small>}
              </span>
              <span className="pm-likely-figure">{FLOOD_WORD[r.level]}</span>
            </li>
          ))}
        </ul>
      )}
      {assessed.length > TOP && (
        <button type="button" className="pm-likely-more" onClick={() => setAll((v) => !v)}>
          {all ? `Show the top ${TOP}` : `Show all ${assessed.length}`}
        </button>
      )}
      {reasons.size > 0 && (
        <div className="pm-muted">
          <strong>{NOT_ASSESSED}</strong>
          <ul className="pm-flood-reasons">
            {[...reasons].map(([reason, n]) => <li key={reason}>{`${reason} (${n})`}</li>)}
          </ul>
        </div>
      )}
    </>
  );
}
