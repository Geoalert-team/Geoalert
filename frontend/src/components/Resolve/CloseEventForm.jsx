import React, { useCallback, useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import { historyApi } from '../../api/historyApi';
import ZoneReports from './ZoneReports';
import {
  CAUSE_MAX, COUNTS, emptyEventFigures, eventFiguresErrors, eventFiguresPayload, subcategoriesFor,
} from './eventClose';

/**
 * Resolving a flood or landslide: one row of the flood and landslide log
 * (columns G to N), filled in with the barangay's report in view, as a fire
 * is closed with its BFP figures (CloseFireForm). One step: the all-clear
 * goes out, the hazard comes off the public map and one history record is
 * filed with these figures. Opened by ResolveHazardForm for every type but
 * fire. Styled with db- classes.
 */

function Err({ text }) {
  return text ? <span className="db-bfp-err">{text}</span> : null;
}

export default function CloseEventForm({ zoneId, title, hazardType, onCancel, onResolved }) {
  const [form, setForm] = useState(emptyEventFigures);
  const [options, setOptions] = useState(null);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [errors, setErrors] = useState({});
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadOptions = useCallback(() => {
    setOptionsFailed(false);
    historyApi.eventOptions().then(setOptions).catch(() => setOptionsFailed(true));
  }, []);
  useEffect(() => { loadOptions(); }, [loadOptions]);

  const noun = (hazardType || 'hazard').toLowerCase();
  const choices = subcategoriesFor(options, hazardType);

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
    if (errors[key]) setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function check() {
    const found = eventFiguresErrors(form, choices);
    setErrors(found);
    if (Object.keys(found).length) {
      setError(`Some figures need fixing before the ${noun} can be resolved.`);
      return false;
    }
    setError('');
    return true;
  }

  async function submit() {
    if (!check()) { setConfirming(false); return; }
    setBusy(true);
    try {
      const zone = await hazardsApi.update(zoneId, eventFiguresPayload(form));
      onResolved?.(zone);
    } catch (err) {
      // A 400 names the fields; anything else is one message
      const fields = err?.data && typeof err.data === 'object' && !err.data.error ? err.data : null;
      if (fields) setErrors(Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, [].concat(v)[0]])));
      setError(fields ? `Some figures need fixing before the ${noun} can be resolved.`
        : err?.message || 'Could not resolve this hazard. Check your connection and try again.');
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="db-resolve">
      <h3>Resolve the {noun}</h3>
      {title && <p className="db-hint">{title}</p>}

      <p className="db-callout">
        This sends the all-clear, takes the {noun} off the public map and files it as one row of
        the flood and landslide log, with the figures below (columns G to N).
      </p>

      <ZoneReports zoneId={zoneId} />

      {optionsFailed && (
        <div className="db-error" role="alert">
          The sub category list didn&apos;t load.{' '}
          <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={loadOptions}>Try again</button>
        </div>
      )}

      <h4 className="db-bfp-head">Hazard type</h4>
      <div className="db-field-row">
        <label className="db-field" htmlFor="db-ev-category">
          General category
          <input id="db-ev-category" value={(hazardType || '').toUpperCase()} readOnly disabled />
        </label>
        {(!options || choices.length > 0) && (
          <label className="db-field" htmlFor="db-ev-sub">
            Sub category *
            <select
              id="db-ev-sub"
              value={form.hazard_subcategory}
              onChange={(e) => set('hazard_subcategory', e.target.value)}
              disabled={!options}
              aria-invalid={Boolean(errors.hazard_subcategory)}
            >
              <option value="">{options ? 'Choose…' : 'Loading…'}</option>
              {choices.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Err text={errors.hazard_subcategory} />
          </label>
        )}
      </div>

      <label className="db-field" htmlFor="db-ev-cause">
        Cause / weather system
        <input
          id="db-ev-cause"
          maxLength={CAUSE_MAX}
          placeholder="e.g. Typhoon Tino; heavy rain; Mananga River overflow"
          value={form.cause}
          onChange={(e) => set('cause', e.target.value)}
          aria-invalid={Boolean(errors.cause)}
        />
        <Err text={errors.cause} />
      </label>

      {[COUNTS.slice(0, 2), COUNTS.slice(2)].map((pair) => (
        <div className="db-field-row" key={pair[0].key}>
          {pair.map(({ key, label }) => (
            <label className="db-field" htmlFor={`db-ev-${key}`} key={key}>
              {label}
              <input
                id={`db-ev-${key}`}
                type="number"
                min="0"
                step="1"
                inputMode="numeric"
                placeholder="—"
                value={form[key]}
                onChange={(e) => set(key, e.target.value)}
                aria-invalid={Boolean(errors[key])}
              />
              <Err text={errors[key]} />
            </label>
          ))}
        </div>
      ))}

      <label className="db-field" htmlFor="db-ev-summary">
        Impact / description
        <textarea
          id="db-ev-summary"
          rows={3}
          value={form.summary}
          onChange={(e) => set('summary', e.target.value)}
          placeholder="What happened, how far it reached, what response was carried out, when it cleared"
        />
      </label>

      <p className="db-hint">
        Leave a count empty if it isn&apos;t in yet. Empty is recorded as not counted, which is
        not the same as zero.
      </p>

      {error && <p className="db-error" role="alert">{error}</p>}

      {confirming ? (
        <div className="db-confirm">
          <p>
            Resolve this {noun}? The public map will stop showing it, everyone who received its
            alert gets an all-clear, and these figures are filed in history.
          </p>
          <div className="db-btn-row">
            <button type="button" className="db-btn db-btn-primary" onClick={submit} disabled={busy}>
              {busy ? 'Resolving…' : 'Yes, resolve it'}
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
            Resolve and file
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
