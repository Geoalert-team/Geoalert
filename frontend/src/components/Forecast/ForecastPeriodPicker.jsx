import React from 'react';
import { MONTHS, PERIOD_MODES } from './forecastLevels';

/**
 * Which time the likelihood is for: a month, a month in a year, or an exact
 * date (see PERIOD_MODES). One labelled control per part, so it sits in the
 * Analytics and dashboard filter row (fc-field) or among the map's chips.
 *
 * Props:
 *   value        { mode, month, year, date } (defaultPeriod())
 *   onChange     (next value) => void
 *   fieldClass   each control's wrapper class
 *   labelClass   each control's label class; the map hides them (pm-sr)
 *   now          today, for the years offered
 */
export default function ForecastPeriodPicker({ value, onChange, fieldClass = 'fc-field', labelClass, now = new Date() }) {
  const set = (patch) => onChange({ ...value, ...patch });
  // Ten years back to look at what happened, two ahead to plan for
  const thisYear = now.getFullYear();
  const years = Array.from({ length: 13 }, (_, i) => thisYear + 2 - i);

  return (
    <>
      <label className={fieldClass}>
        <span className={labelClass}>Period</span>
        <select value={value.mode} onChange={(e) => set({ mode: e.target.value })}>
          {PERIOD_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </select>
      </label>
      {value.mode === 'date' ? (
        <label className={fieldClass}>
          <span className={labelClass}>Date</span>
          {/* Clearing the field keeps the last date: a forecast needs one */}
          <input type="date" value={value.date} required onChange={(e) => e.target.value && set({ date: e.target.value })} />
        </label>
      ) : (
        <label className={fieldClass}>
          <span className={labelClass}>Month</span>
          <select value={value.month} onChange={(e) => set({ month: Number(e.target.value) })}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </label>
      )}
      {value.mode === 'monthYear' && (
        <label className={fieldClass}>
          <span className={labelClass}>Year</span>
          <select value={value.year} onChange={(e) => set({ year: Number(e.target.value) })}>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
      )}
    </>
  );
}
