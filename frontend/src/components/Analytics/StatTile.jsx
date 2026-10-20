import React from 'react';

/** A headline figure: value, what it counts, an optional hint and extra (a sparkline). */
export default function StatTile({ value, label, hint, children }) {
  return (
    <div className="db-stat an-stat">
      <div className="db-stat-value">{value ?? '—'}</div>
      <div className="db-stat-label">{label}</div>
      {hint && <div className="an-stat-hint">{hint}</div>}
      {children}
    </div>
  );
}
