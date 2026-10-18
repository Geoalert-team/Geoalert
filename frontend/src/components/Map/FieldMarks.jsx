import React from 'react';

/**
 * "Affected here" / "Clear here": spots checked on the ground while a zone
 * is live. Barangay staff and officers add them; a mark on the wrong side
 * of the outline tells the officer the edge needs moving. Marks never move
 * the zone themselves.
 */

export const MARK_STYLE = {
  Affected: { label: 'Affected here', color: '#1c64f2', fill: '#1c64f2' },
  Clear: { label: 'Clear here', color: '#1f9d55', fill: '#ffffff' },
};

/** Leaflet circle-marker options for a mark; a red ring when it disagrees. */
export function markPathOptions(mark) {
  const s = MARK_STYLE[mark.kind] || MARK_STYLE.Affected;
  return {
    radius: 7,
    color: mark.disagrees ? '#d64545' : s.color,
    weight: mark.disagrees ? 3 : 2,
    fillColor: s.fill,
    fillOpacity: 0.95,
  };
}

/**
 * Summary and buttons inside the zone panel.
 *
 * Props:
 *   marks      [{ kind, disagrees, ... }] for this zone
 *   onMark     (kind) => void   start placing a mark; omitted = read only
 *   marking    the kind being placed now, or null
 */
export function FieldMarksSection({ marks = [], onMark, marking = null }) {
  const affected = marks.filter((m) => m.kind === 'Affected').length;
  const clear = marks.filter((m) => m.kind === 'Clear').length;
  const disagree = marks.filter((m) => m.disagrees).length;

  return (
    <div className="pm-marks">
      <p className="pm-marks-title">Checked on the ground</p>
      <p className="pm-marks-sum">
        {marks.length
          ? `${affected} affected, ${clear} clear.`
          : 'No spots checked yet.'}
        {disagree > 0 && (
          <strong className="pm-marks-warn">
            {' '}{disagree} disagree{disagree === 1 ? 's' : ''} with the outline.
          </strong>
        )}
      </p>
      {onMark && (
        marking ? (
          <p className="pm-marks-hint">
            Tap the map where you checked: {MARK_STYLE[marking].label.toLowerCase()}.
          </p>
        ) : (
          <div className="db-btn-row">
            <button type="button" className="db-btn db-btn-outline" onClick={() => onMark('Affected')}>
              Mark affected spot
            </button>
            <button type="button" className="db-btn db-btn-outline" onClick={() => onMark('Clear')}>
              Mark clear spot
            </button>
          </div>
        )
      )}
    </div>
  );
}
