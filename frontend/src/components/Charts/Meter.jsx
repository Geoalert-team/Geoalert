import React from 'react';

/**
 * One share out of 100%: a big value, a filled track and a caption. For a
 * ratio against its limit a meter reads faster than a pie or a bare number.
 *
 * A missing share (nothing was sent, nothing was submitted) shows a dash and
 * an empty track, never 0%: "nobody opened it" and "nothing to open" are
 * different findings.
 *
 * Props:
 *   value         share from 0 to 1, or null
 *   label         what the share is of
 *   caption       the counts behind it
 *   emptyCaption  shown instead of caption when value is null
 */

/** 0.644 -> 64; null, undefined or NaN -> null; clamped to 0..100 */
export function meterPercent(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  return Math.min(100, Math.max(0, Math.round(value * 100)));
}

export default function Meter({ value, label, caption, emptyCaption }) {
  const pct = meterPercent(value);
  const meter = pct === null ? {} : {
    role: 'meter',
    'aria-label': label,
    'aria-valuemin': 0,
    'aria-valuemax': 100,
    'aria-valuenow': pct,
    'aria-valuetext': `${pct}%`,
  };

  return (
    <div className="an-meter">
      <div className="an-meter-head">
        <span className="an-big">{pct === null ? '—' : `${pct}%`}</span>
        <span className="an-meter-label">{label}</span>
      </div>
      <div className="an-meter-track" {...meter}>
        {pct !== null && <div className="an-meter-fill" style={{ width: `${pct}%` }} />}
      </div>
      <small>{pct === null ? emptyCaption : caption}</small>
    </div>
  );
}
