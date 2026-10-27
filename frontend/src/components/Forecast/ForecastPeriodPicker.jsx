import React from 'react';
import { FIRST_YEAR, LAST_YEAR, MONTHS, PERIOD_MODES, YEARS } from './forecastLevels';

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
 *
 * Years run FIRST_YEAR to LAST_YEAR: past ones to look at what happened,
 * coming ones to plan for.
 */
export default function ForecastPeriodPicker({ value, onChange, fieldClass = 'fc-field', labelClass }) {
  const set = (patch) => onChange({ ...value, ...patch });

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
          <input
            type="date"
            value={value.date}
            min={`${FIRST_YEAR}-01-01`}
            max={`${LAST_YEAR}-12-31`}
            required
            onChange={(e) => e.target.value && set({ date: e.target.value })}
          />
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
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
      )}
    </>
  );
}
