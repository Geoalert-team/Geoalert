import React from 'react';
import { dayLabel, laterDayHint, dayData } from './rainWatchLevels';
import './rainWatch.css';

const FALLBACK = [
  { key: 'today' }, { key: 'tomorrow' }, { key: 'day_after', less_certain: true },
];

// Today / Tomorrow / the day after, plus a hint when a later day is worse
export default function RainWatchDayPicker({ data, value, onChange, activeTypes }) {
  const days = data?.days?.length ? data.days : FALLBACK;
  const hint = laterDayHint(data, activeTypes, value);
  const hintIndex = hint ? days.findIndex((d) => d.key === hint.key) : -1;
  const hintDay = hintIndex >= 0 ? dayLabel(days[hintIndex], hintIndex) : '';
  return (
    <div className="rw-picker-wrap">
      <div className="rw-picker" role="group" aria-label="Day">
        {days.map((day, i) => {
          const label = dayLabel(day, i);
          return (
            <button
              key={day.key}
              type="button"
              className={`pm-chip ${value === day.key ? 'is-active' : ''}`}
              aria-pressed={value === day.key}
              onClick={() => onChange(day.key)}
            >
              {day.less_certain ? `${label} (less certain)` : label}
            </button>
          );
        })}
      </div>
      {hint && dayData(data, hint.key) && (
        <button type="button" className="rw-hint" onClick={() => onChange(hint.key)}>
          {`${hint.level} expected ${hintDay} in ${hint.count} barangay${hint.count === 1 ? '' : 's'} → see ${hintDay}`}
        </button>
      )}
    </div>
  );
}
