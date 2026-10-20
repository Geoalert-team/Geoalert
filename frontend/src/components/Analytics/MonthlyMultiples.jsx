import React from 'react';
import TrendLine from '../Charts/TrendLine';
import { MEASURES, monthLabel } from './measures';

/**
 * The four measures month by month as small multiples: one small line each,
 * same months along the bottom, every trend visible at once. Each has its
 * own scale (incident reports run far higher than recorded events), so the
 * sub line says to compare shapes. One table below carries every number.
 */
export default function MonthlyMultiples({ monthly = [] }) {
  return (
    <div className="db-card">
      <h2>Month by month</h2>
      <p className="db-card-sub">Each chart has its own scale, so compare their shapes rather than their heights.</p>

      <div className="an-multiples">
        {MEASURES.map((m) => {
          const total = monthly.reduce((sum, r) => sum + r[m.key], 0);
          return (
            <div key={m.key} className="an-multiple">
              <div className="an-multiple-head">
                <h3>{m.label}</h3>
                <span className="an-multiple-total">{total.toLocaleString()} <small>in total</small></span>
              </div>
              <TrendLine
                points={monthly.map((r) => ({ label: monthLabel(r.month), value: r[m.key] }))}
                height={150}
                unit={m.unit}
                table={false}
                empty="No months in this period."
              />
            </div>
          );
        })}
      </div>

      <details className="an-table-wrap">
        <summary>Show the numbers</summary>
        <table className="db-table">
          <thead>
            <tr><th>Month</th>{MEASURES.map((m) => <th key={m.key}>{m.label}</th>)}</tr>
          </thead>
          <tbody>
            {monthly.map((r) => (
              <tr key={r.month}>
                <td>{monthLabel(r.month)}</td>
                {MEASURES.map((m) => <td key={m.key}>{r[m.key]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
