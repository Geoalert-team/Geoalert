import React, { useEffect, useMemo, useState } from 'react';
import { adminApi } from '../../../api/adminApi';
import { Icon } from './adminShared';

// Which group each setting belongs to, by its key prefix
const GROUPS = [
  { prefix: 'auth.', title: 'Sign-in and lockout' },
  { prefix: 'session.', title: 'Sessions' },
  { prefix: 'alerts.', title: 'Extreme alerts' },
];

/**
 * F8 System configuration panel. A System Administrator changes the
 * limits the system runs on: lockout, session length and the Extreme-alert
 * timings. The server checks every value against its allowed range and
 * writes each change to the activity log; a change takes effect within a
 * minute, without a restart.
 */
export default function SettingsTab() {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState({});
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [failed, setFailed] = useState(false);

  function load() {
    setFailed(false);
    adminApi.settings()
      .then((d) => {
        setSettings(d.settings);
        setDraft(Object.fromEntries(d.settings.map((s) => [s.key, String(s.value)])));
      })
      .catch(() => setFailed(true));
  }
  useEffect(load, []);

  const changed = useMemo(
    () => (settings || []).filter((s) => String(s.value) !== String(draft[s.key] ?? '').trim()),
    [settings, draft],
  );

  async function save(e) {
    e.preventDefault();
    if (!changed.length) return;
    setBusy(true);
    setErrors({});
    setMessage('');
    try {
      const values = Object.fromEntries(changed.map((s) => [s.key, draft[s.key].trim()]));
      const d = await adminApi.saveSettings(values);
      setSettings(d.settings);
      setDraft(Object.fromEntries(d.settings.map((s) => [s.key, String(s.value)])));
      setMessage(d.changed.length
        ? `Saved ${d.changed.length} change${d.changed.length === 1 ? '' : 's'}. They take effect within a minute.`
        : 'Nothing changed.');
    } catch (err) {
      const body = err?.response?.data || err?.data;
      if (body?.errors) setErrors(body.errors);
      else setMessage(err?.message || 'Could not save the settings.');
    } finally {
      setBusy(false);
    }
  }

  function resetToDefault(s) {
    setDraft((d) => ({ ...d, [s.key]: String(s.default) }));
  }

  if (failed) {
    return (
      <section className="adm-card">
        <p>Could not load the settings.</p>
        <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" onClick={load}>Try again</button>
      </section>
    );
  }
  if (!settings) return <section className="adm-card"><p>Loading settings…</p></section>;

  return (
    <form className="adm-card adm-settings" onSubmit={save} noValidate>
      <div className="adm-card-head">
        <div>
          <h2>System configuration</h2>
          <p>
            Limits the system runs on. Each value is checked against its allowed range, and every
            change is recorded in the activity log.
          </p>
        </div>
      </div>

      {GROUPS.map((g) => (
        <fieldset key={g.prefix} className="adm-settings-group">
          <legend>{g.title}</legend>
          {settings.filter((s) => s.key.startsWith(g.prefix)).map((s) => {
            const id = `set-${s.key.replace(/\W/g, '-')}`;
            const isChanged = changed.some((c) => c.key === s.key);
            return (
              <div key={s.key} className={`adm-field adm-setting ${errors[s.key] ? 'has-error' : ''}`}>
                <label htmlFor={id}>{s.label}</label>
                <div className="adm-setting-row">
                  <input
                    id={id}
                    type="number"
                    min={s.min}
                    max={s.max}
                    step={1}
                    value={draft[s.key] ?? ''}
                    onChange={(e) => setDraft((d) => ({ ...d, [s.key]: e.target.value }))}
                    disabled={busy}
                    aria-describedby={`${id}-help`}
                  />
                  <span className="adm-setting-unit">{s.unit}</span>
                  {String(draft[s.key]) !== String(s.default) && (
                    <button type="button" className="adm-link" onClick={() => resetToDefault(s)} disabled={busy}>
                      Use default ({s.default})
                    </button>
                  )}
                  {isChanged && <span className="adm-setting-changed">changed</span>}
                </div>
                <p id={`${id}-help`} className="adm-setting-help">
                  {s.help} Allowed: {s.min} to {s.max} {s.unit}.
                </p>
                {errors[s.key] && <p className="adm-field-error">{errors[s.key]}</p>}
              </div>
            );
          })}
        </fieldset>
      ))}

      {message && (
        <p className="adm-setting-msg" role="status"><Icon name="info" size={16} /> {message}</p>
      )}

      <div className="adm-settings-actions">
        <button type="submit" className="adm-btn adm-btn-primary" disabled={busy || !changed.length}>
          {busy ? 'Saving…' : `Save${changed.length ? ` ${changed.length} change${changed.length === 1 ? '' : 's'}` : ''}`}
        </button>
        <button
          type="button"
          className="adm-btn adm-btn-ghost"
          onClick={() => { setDraft(Object.fromEntries(settings.map((s) => [s.key, String(s.value)]))); setErrors({}); }}
          disabled={busy || !changed.length}
        >
          Undo changes
        </button>
      </div>
    </form>
  );
}
