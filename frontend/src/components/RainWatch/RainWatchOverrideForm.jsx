import React, { useState } from 'react';
import { rainWatchApi } from '../../api/rainWatchApi';
import { fieldErrors } from '../../pages/Dashboard/admin/adminShared';

const HOUR = 3600000;
const NOTE_MAX = 300;
export const NOTE_REQUIRED = 'Add a note saying where the warning came from.';

// A datetime-local value (like 2026-11-18T14:30) in the browser's own time zone
function toLocalInput(ms) {
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** DRRMO sets a level by hand (a floor: it only raises). onSaved is called after it is stored. */
export default function RainWatchOverrideForm({ onSaved, onCancel }) {
  const [hazard, setHazard] = useState('Both');
  const [level, setLevel] = useState('Orange');
  const [until, setUntil] = useState(() => toLocalInput(Date.now() + 12 * HOUR));
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const found = {};
    const end = until ? new Date(until).getTime() : NaN;
    if (!note.trim()) found.note = NOTE_REQUIRED;
    if (Number.isNaN(end) || end <= Date.now()) found.ends_at = 'Choose a time in the future.';
    else if (end > Date.now() + 72 * HOUR) found.ends_at = 'Choose a time within the next 72 hours.';
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await rainWatchApi.createOverride({ hazard, level, endsAt: new Date(end).toISOString(), note: note.trim() });
      onSaved();
    } catch (err) {
      setErrors(fieldErrors(err));
      setBusy(false);
    }
  }

  const max = toLocalInput(Date.now() + 72 * HOUR);
  return (
    <form className="rw-form" onSubmit={submit} noValidate>
      <div className="rw-form-row">
        <div className="adm-field">
          <label htmlFor="rw-hazard">Hazard</label>
          <select id="rw-hazard" value={hazard} onChange={(e) => setHazard(e.target.value)}>
            <option value="Flood">Flood</option>
            <option value="Landslide">Landslide</option>
            <option value="Both">Both</option>
          </select>
        </div>
        <div className="adm-field">
          <label htmlFor="rw-level">Level</label>
          <select id="rw-level" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="Yellow">Yellow</option>
            <option value="Orange">Orange</option>
            <option value="Red">Red</option>
          </select>
        </div>
      </div>
      <div className={`adm-field ${errors.ends_at ? 'has-error' : ''}`}>
        <label htmlFor="rw-until">Until</label>
        <input id="rw-until" type="datetime-local" value={until} max={max} onChange={(e) => setUntil(e.target.value)} />
        <p className="adm-field-hint">At most 72 hours from now.</p>
        {errors.ends_at && <p className="adm-field-error">{errors.ends_at}</p>}
      </div>
      <div className={`adm-field ${errors.note ? 'has-error' : ''}`}>
        <label htmlFor="rw-note">Note</label>
        <textarea
          id="rw-note"
          rows={3}
          maxLength={NOTE_MAX}
          value={note}
          placeholder="e.g. PAGASA Visayas heavy rainfall warning #3, Orange"
          onChange={(e) => setNote(e.target.value)}
        />
        <p className="adm-field-hint">{note.length}/{NOTE_MAX}. A level set by hand can only raise a colour, never lower one.</p>
        <p className="adm-field-hint">Residents see this note when the level is Orange or Red.</p>
        {errors.note && <p className="adm-field-error">{errors.note}</p>}
      </div>
      {errors.form && <p className="adm-field-error" role="alert">{errors.form}</p>}
      <div className="rw-form-actions">
        <button type="button" className="adm-btn adm-btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
        <button type="submit" className="adm-btn adm-btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Set level'}</button>
      </div>
    </form>
  );
}
