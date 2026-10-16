import React from 'react';
import { hazardIconPath, hazardColor, SEVERITY } from './hazardInfo';

/**
 * F6's layer control: a checkbox per hazard type so several can be shown at
 * once. The old chips were single-select, which meant choosing Flood hid Fire
 * — the opposite of a unified display.
 *
 * Props:
 *   types      [{ name, active_count, severity_counts }] from /api/hazards/layers/,
 *              or a locally-counted fallback when that call fails
 *   active     Set of visible hazard type names
 *   onToggle(name)
 *   onAll()    show every layer
 *   onNone()   hide every layer
 *   failed     true when the counts couldn't be loaded
 *   onRetry()
 */

export default function LayerControl({ types, active, onToggle, onAll, onNone, failed, onRetry }) {
  const allOn = types.length > 0 && types.every((t) => active.has(t.name));
  const noneOn = active.size === 0;

  if (types.length === 0) {
    return (
      <div className="pm-layers" role="group" aria-label="Hazard layers">
        <p className="pm-layers-empty">No hazard layers available at this time.</p>
        {failed && (
          <button type="button" className="pm-layers-retry" onClick={onRetry}>
            Reload layers
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="pm-layers" role="group" aria-label="Hazard layers">
      <div className="pm-layers-head">
        <span className="pm-layers-title">Hazard layers</span>
        <button type="button" className="pm-layers-link" onClick={allOn ? onNone : onAll}>
          {allOn ? 'Hide all' : 'Show all'}
        </button>
      </div>

      <ul className="pm-layers-list">
        {types.map((t) => {
          const on = active.has(t.name);
          const id = `pm-layer-${t.name.toLowerCase().replace(/\W+/g, '-')}`;
          const counts = t.severity_counts || {};
          return (
            <li key={t.name}>
              <input
                id={id}
                type="checkbox"
                checked={on}
                onChange={() => onToggle(t.name)}
              />
              <label htmlFor={id}>
                <span className="pm-layers-icon" style={{ color: hazardColor(t.name) }} aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d={hazardIconPath(t.name)} /></svg>
                </span>
                <span className="pm-layers-name">{t.name}</span>
                <span className="pm-layers-count" title={
                  ['Red', 'Orange', 'Green']
                    .map((s) => `${SEVERITY[s].label}: ${counts[s] ?? 0}`)
                    .join(' · ')
                }>
                  {t.active_count ?? 0}
                </span>
              </label>
              {on && (t.active_count ?? 0) > 0 && (
                <span className="pm-layers-dots" aria-hidden="true">
                  {['Red', 'Orange', 'Green'].map((s) =>
                    counts[s] ? (
                      <span key={s} className="pm-layers-dot" style={{ background: SEVERITY[s].color }} />
                    ) : null,
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {noneOn && (
        <p className="pm-layers-note">Every layer is hidden. Tick one to see hazards again.</p>
      )}
      {failed && (
        <button type="button" className="pm-layers-retry" onClick={onRetry}>
          Counts unavailable — reload
        </button>
      )}
    </div>
  );
}