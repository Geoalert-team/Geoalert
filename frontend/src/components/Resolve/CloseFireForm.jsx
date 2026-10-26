import React, { useCallback, useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import { historyApi } from '../../api/historyApi';
import ZoneReports from './ZoneReports';
import {
  FATALITIES, INJURED, bfpLabel, emptyFigures, figuresErrors, figuresPayload, groupTotal, withCategory,
} from './fireClose';

/**
 * Resolving a fire: the BFP fire log's columns G to W, filled in with the
 * barangay's report in view. One step: the all-clear goes out, the fire
 * comes off the public map and one history record is filed with these
 * figures. Opened by ResolveHazardForm for fire zones, so the map panel and
 * the dashboard's active zones card both get it. Styled with db- classes.
 */

function Err({ text }) {
  return text ? <span className="db-bfp-err">{text}</span> : null;
}

// Firefighter and civilian rows, male / female / total columns: the
// spreadsheet's Injured (I-N) or Fatalities (O-T) block
function CountGrid({ title, groups, form, errors, onChange, idPrefix }) {
  const rows = [['Firefighter', groups.firefighter], ['Civilian', groups.civilian]];
  return (
    <fieldset className="db-bfp-grid">
      <legend>{title}</legend>
      <span />
      <span className="db-bfp-col">Male</span>
      <span className="db-bfp-col">Female</span>
      <span className="db-bfp-col">Total</span>
      {rows.map(([label, [male, female]]) => (
        <React.Fragment key={label}>
          <span className="db-bfp-row">{label}</span>
          {[male, female].map((key, i) => (
            <input
              key={key}
              id={`${idPrefix}-${key}`}
              type="number"
              min="0"
              step="1"
              inputMode="numeric"
              placeholder="—"
              aria-label={`${title}: ${label.toLowerCase()}, ${i ? 'female' : 'male'}`}
              aria-invalid={Boolean(errors[key])}
              value={form[key]}
              onChange={(e) => onChange(key, e.target.value)}
            />
          ))}
          <output className="db-bfp-total" aria-label={`${title}: ${label.toLowerCase()}, total`}>
            {groupTotal(form, [male, female]) === '' ? '—' : groupTotal(form, [male, female])}
          </output>
        </React.Fragment>
      ))}
      <Err text={[...groups.firefighter, ...groups.civilian].map((k) => errors[k]).find(Boolean)} />
    </fieldset>
  );
}

export default function CloseFireForm({ zoneId, title, onCancel, onResolved }) {
  const [form, setForm] = useState(emptyFigures);
  const [options, setOptions] = useState(null);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [errors, setErrors] = useState({});
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadOptions = useCallback(() => {
    setOptionsFailed(false);
    historyApi.bfpOptions().then(setOptions).catch(() => setOptionsFailed(true));
  }, []);
  useEffect(() => { loadOptions(); }, [loadOptions]);

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
    if (errors[key]) setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function chooseCategory(category) {
    setForm((f) => withCategory(f, category, options));
    setErrors((e) => ({ ...e, property_subcategory: undefined }));
  }

  function check() {
    const found = figuresErrors(form, options);
    setErrors(found);
    if (Object.keys(found).length) {
      setError('Some figures need fixing before the fire can be closed.');
      return false;
    }
    setError('');
    return true;
  }

  async function submit() {
    if (!check()) { setConfirming(false); return; }
    setBusy(true);
    try {
      const res = await hazardsApi.closeFire(zoneId, figuresPayload(form));
      onResolved?.(res.zone);
    } catch (err) {
      // A 400 names the fields; anything else is one message
      const fields = err?.data && typeof err.data === 'object' && !err.data.error ? err.data : null;
      if (fields) setErrors(Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, [].concat(v)[0]])));
      setError(fields ? 'Some figures need fixing before the fire can be closed.'
        : err?.message || 'Could not close this fire. Check your connection and try again.');
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  const categories = Object.keys(options?.property_types || {});
  const subs = options?.property_types?.[form.property_category] || [];

  return (
    <div className="db-resolve">
      <h3>Close the fire</h3>
      {title && <p className="db-hint">{title}</p>}

      <p className="db-callout">
        This sends the all-clear, takes the fire off the public map and files it as one row of
        the BFP fire log, with the figures below (columns G to W).
      </p>

      <ZoneReports zoneId={zoneId} />

      {optionsFailed && (
        <div className="db-error" role="alert">
          The BFP lists didn&apos;t load.{' '}
          <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={loadOptions}>Try again</button>
        </div>
      )}

      <h4 className="db-bfp-head">Property type</h4>
      <div className="db-field-row">
        <label className="db-field" htmlFor="db-bfp-category">
          General category *
          <select
            id="db-bfp-category"
            value={form.property_category}
            onChange={(e) => chooseCategory(e.target.value)}
            disabled={!options}
          >
            <option value="">{options ? 'Choose…' : 'Loading…'}</option>
            {categories.map((c) => <option key={c} value={c}>{bfpLabel(c)}</option>)}
          </select>
        </label>
        <label className="db-field" htmlFor="db-bfp-sub">
          Sub category *
          <select
            id="db-bfp-sub"
            value={form.property_subcategory}
            onChange={(e) => set('property_subcategory', e.target.value)}
            disabled={!form.property_category}
            aria-invalid={Boolean(errors.property_subcategory)}
          >
            <option value="">{form.property_category ? 'Choose…' : 'Choose the category first'}</option>
            {subs.map((s) => <option key={s} value={s}>{bfpLabel(s)}</option>)}
          </select>
          <Err text={errors.property_subcategory} />
        </label>
      </div>

      <CountGrid title="Injured" groups={INJURED} form={form} errors={errors} onChange={set} idPrefix="db-bfp-inj" />
      <CountGrid title="Fatalities" groups={FATALITIES} form={form} errors={errors} onChange={set} idPrefix="db-bfp-fat" />

      <div className="db-field-row">
        <label className="db-field" htmlFor="db-bfp-damage">
          Estimated cost of damage (PHP)
          <input
            id="db-bfp-damage"
            inputMode="decimal"
            placeholder="—"
            value={form.damage_cost}
            onChange={(e) => set('damage_cost', e.target.value)}
            aria-invalid={Boolean(errors.damage_cost)}
          />
          <Err text={errors.damage_cost} />
        </label>
        <label className="db-field" htmlFor="db-bfp-structures">
          Affected structures
          <input
            id="db-bfp-structures"
            type="number"
            min="0"
            step="1"
            inputMode="numeric"
            placeholder="—"
            value={form.structures_affected}
            onChange={(e) => set('structures_affected', e.target.value)}
            aria-invalid={Boolean(errors.structures_affected)}
          />
          <Err text={errors.structures_affected} />
        </label>
      </div>

      <label className="db-field" htmlFor="db-bfp-alarm">
        Alarm *
        <select
          id="db-bfp-alarm"
          value={form.alarm_level}
          onChange={(e) => set('alarm_level', e.target.value)}
          disabled={!options}
          aria-invalid={Boolean(errors.alarm_level)}
        >
          <option value="">{options ? 'Choose…' : 'Loading…'}</option>
          {(options?.alarm_levels || []).map((a) => <option key={a} value={a}>{bfpLabel(a)}</option>)}
        </select>
        <Err text={errors.alarm_level} />
      </label>

      <p className="db-hint">
        Leave a count empty if it isn&apos;t in yet. Empty is recorded as not counted, which is
        not the same as zero.
      </p>

      {error && <p className="db-error" role="alert">{error}</p>}

      {confirming ? (
        <div className="db-confirm">
          <p>
            Close this fire? The public map will stop showing it, everyone who received its alert
            gets an all-clear, and these figures are filed in history.
          </p>
          <div className="db-btn-row">
            <button type="button" className="db-btn db-btn-primary" onClick={submit} disabled={busy}>
              {busy ? 'Closing…' : 'Yes, close it'}
            </button>
            <button type="button" className="db-btn db-btn-outline" onClick={() => setConfirming(false)} disabled={busy}>
              Go back
            </button>
          </div>
        </div>
      ) : (
        <div className="db-btn-row">
          <button
            type="button"
            className="db-btn db-btn-primary"
            onClick={() => { if (check()) setConfirming(true); }}
            disabled={busy || !options}
          >
            Close and file
          </button>
          {onCancel && (
            <button type="button" className="db-btn db-btn-outline" onClick={onCancel} disabled={busy}>
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}
