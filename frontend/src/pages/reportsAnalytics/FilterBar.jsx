import React, { useEffect, useState } from 'react';
import {
  describeFilters, isDefault, namesFor, presetsFor, rangeError, resolveRange, sameFilters,
} from './filters';

/**
 * Period, hazard type and barangay. The page holds the applied filters (in
 * the address); changes come back through onChange as patches.
 *
 *   mode 'live'   (Trend Analysis) a chip or a list choice applies at once;
 *                 a typed date applies when the field is left or on Enter,
 *                 not on every keystroke (a half-typed year is not a query)
 *   mode 'apply'  (Reports & Analytics) choices collect in a draft and go
 *                 out together on Apply, so a report is generated, and
 *                 logged, once for one set of filters
 *   kind          'reports' or 'trends': which presets to offer
 */
export default function FilterBar({
  filters, onChange, onReset, hazardTypes = [], barangays = [], today, kind = 'reports', mode = 'live',
}) {
  const apply = mode === 'apply';
  const [draft, setDraft] = useState(filters);
  const [dates, setDates] = useState({ from: filters.from, to: filters.to });
  const appliedKey = JSON.stringify(filters);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setDraft(filters); setDates({ from: filters.from, to: filters.to }); }, [appliedKey]);

  const shown = apply ? draft : filters;
  const dirty = apply && !sameFilters(draft, filters);
  const error = rangeError(apply ? draft : filters, today);
  const names = namesFor(filters, hazardTypes, barangays);
  const sortedBarangays = [...barangays].sort((a, b) => String(a.name).localeCompare(String(b.name)));

  function change(patch) {
    if (apply) setDraft((d) => ({ ...d, ...patch }));
    else onChange(patch);
  }

  function pickPeriod(key) {
    if (key === shown.period) return;
    // Dates belong to Custom only: leaving it clears them from the draft, so
    // returning to the applied preset leaves nothing to apply
    if (key !== 'custom') { change(apply ? { period: key, from: '', to: '' } : { period: key }); return; }
    // Start a custom range from the one on screen, so it can be nudged
    const { from, to } = resolveRange(shown, today);
    change({ period: 'custom', from: from || '', to });
  }

  function typeDate(key, value) {
    if (apply) change({ [key]: value });
    else setDates((d) => ({ ...d, [key]: value }));
  }

  function commitDate(key) {
    if (!apply && dates[key] !== filters[key]) onChange({ [key]: dates[key] });
  }

  const dateValue = (key) => (apply ? draft[key] : dates[key]);

  return (
    <section className="ra-filters db-no-print" aria-label="Filters">
      <div className="ra-filter-row">
        <div className="ra-presets" role="group" aria-label="Period">
          {presetsFor(kind).map((p) => (
            <button
              key={p.key}
              type="button"
              className={`ra-chip ${shown.period === p.key ? 'is-active' : ''}`}
              aria-pressed={shown.period === p.key}
              onClick={() => pickPeriod(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="ra-selects">
          <label className="db-field">Hazard
            <select value={shown.hazard} onChange={(e) => change({ hazard: e.target.value })}>
              <option value="">All hazards</option>
              {hazardTypes.map((t) => <option key={t.id} value={String(t.id)}>{t.name}</option>)}
            </select>
          </label>
          <label className="db-field">Barangay
            <select value={shown.barangay} onChange={(e) => change({ barangay: e.target.value })}>
              <option value="">All barangays</option>
              {sortedBarangays.map((b) => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
            </select>
          </label>
        </div>
      </div>

      {shown.period === 'custom' && (
        <div className="ra-custom">
          {['from', 'to'].map((key) => (
            <label key={key} className="db-field">{key === 'from' ? 'From' : 'To'}
              <input
                type="date"
                min="1900-01-01"
                max="2100-12-31"
                value={dateValue(key)}
                onChange={(e) => typeDate(key, e.target.value)}
                onBlur={() => commitDate(key)}
                onKeyDown={(e) => { if (e.key === 'Enter') commitDate(key); }}
              />
            </label>
          ))}
        </div>
      )}
      {error && <p className="db-error ra-filter-error" role="alert">{error}</p>}

      <div className="ra-showing">
        <p aria-live="polite">
          Showing: <strong>{describeFilters(filters, names, today)}</strong>
          {dirty && <span className="ra-pending"> · Not applied yet</span>}
        </p>
        <div className="ra-filter-actions">
          {!isDefault(filters, kind) && (
            <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={onReset}>Reset</button>
          )}
          {apply && (
            <button type="button" className="db-btn db-btn-primary db-btn-sm" disabled={!dirty || !!error}
              onClick={() => onChange(draft)}>
              Apply
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
