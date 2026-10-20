import React from 'react';
import useFontsReady from './useFontsReady';

/**
 * Wraps a chart in a fixed-height box and carries the table fallback.
 *
 * Every chart in GeoAlert ships its numbers as text underneath. A canvas is
 * not readable by a screen reader, does not survive a printed report, and
 * leaves nothing behind when the colours are hard to tell apart — which the
 * moderate-severity amber is, at 2.45:1 against a white card.
 *
 * Props:
 *   height     px, default 260
 *   rows       [{ label, value }] for the table; omit to skip the fallback
 *   valueHead  column heading for the value, default 'Events'
 *   empty      message when there is nothing to draw
 *   table      false to leave the fallback out, when the caller shows the
 *              same numbers in a table of its own
 *   children   the chart itself
 */
export default function ChartFrame({
  height = 260,
  rows = [],
  valueHead = 'Events',
  empty = 'No data for this filter.',
  table = true,
  children,
}) {
  const fontsReady = useFontsReady();

  if (!rows.length) {
    return <p className="db-empty">{empty}</p>;
  }

  return (
    <>
      {/* Remounted once web fonts load, so axis text redraws in the page font */}
      <div key={fontsReady ? 'fonts' : 'fallback'} style={{ height, position: 'relative' }}>{children}</div>

      {table && (
        <details style={{ marginTop: 12 }}>
          <summary
            style={{
              cursor: 'pointer',
              fontSize: '.84rem',
              color: 'var(--db-soft)',
              fontWeight: 600,
            }}
          >
            Show the figures
          </summary>
          <table className="db-table" style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>Label</th>
                <th style={{ textAlign: 'right' }}>{valueHead}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td style={{ textAlign: 'right' }}>
                    {r.value === null || r.value === undefined
                      ? '—'
                      : Number(r.value).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </>
  );
}