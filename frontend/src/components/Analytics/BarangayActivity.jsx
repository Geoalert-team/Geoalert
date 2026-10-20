import React, { useMemo, useState } from 'react';
import { sortBarangays } from './barangaySort';

/**
 * Every barangay with activity in the period: zones published and incident
 * reports in one row, so one barangay's two numbers sit side by side. Each
 * count carries a thin bar scaled to its column, and either column sorts.
 *
 * Ten rows show until "Show all" is pressed. The rest stay in the table,
 * hidden by CSS, so a printed copy always carries every barangay.
 */

const COLUMNS = [
  { key: 'zones', label: 'Zones' },
  { key: 'incidents', label: 'Incident reports' },
];
const TOP = 10;

export default function BarangayActivity({ rows = [] }) {
  const [sortKey, setSortKey] = useState('zones');
  const [expanded, setExpanded] = useState(false);

  const sorted = useMemo(() => sortBarangays(rows, sortKey), [rows, sortKey]);
  const max = useMemo(() => Object.fromEntries(
    COLUMNS.map((c) => [c.key, Math.max(0, ...rows.map((r) => r[c.key]))]),
  ), [rows]);

  if (!rows.length) {
    return <p className="db-empty">No zones or incident reports in this period.</p>;
  }

  return (
    <>
      <div className="ba-wrap">
        <table className={`db-table ba-table${expanded ? ' is-expanded' : ''}`}>
          <thead>
            <tr>
              <th scope="col">Barangay</th>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col" aria-sort={sortKey === c.key ? 'descending' : 'none'}>
                  <button type="button" className="ba-sort" onClick={() => setSortKey(c.key)}>
                    {c.label}
                    {sortKey === c.key && <span aria-hidden="true"> ↓</span>}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={r.barangay} className={i >= TOP ? 'ba-more' : undefined}>
                <td>{r.barangay}</td>
                {COLUMNS.map((c) => (
                  <td key={c.key} className="ba-count">
                    <span className="ba-num">{r[c.key].toLocaleString()}</span>
                    <span className="ba-track" aria-hidden="true">
                      <span
                        className="ba-bar"
                        style={{ width: `${max[c.key] ? (r[c.key] / max[c.key]) * 100 : 0}%` }}
                      />
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > TOP && (
        <button
          type="button"
          className="db-btn db-btn-outline db-btn-sm ba-toggle db-no-print"
          aria-expanded={expanded}
          onClick={() => setExpanded((e) => !e)}
        >
          {expanded ? 'Show top 10' : `Show all ${rows.length} barangays`}
        </button>
      )}
    </>
  );
}
