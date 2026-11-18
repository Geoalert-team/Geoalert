import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { rainWatchApi } from '../../api/rainWatchApi';
import { Modal, Toast, formatDateTime } from '../../pages/Dashboard/admin/adminShared';
import RainWatchOverrideForm from './RainWatchOverrideForm';
import { dayLabel, rainLevel, updatedText, withClientStale } from './rainWatchLevels';
import './rainWatch.css';

const REFRESH_MS = 5 * 60 * 1000;
const CLOCK_MS = 60 * 1000;
const HAZARDS = [['flood', 'Flood'], ['landslide', 'Landslide']];

// Label for one PAGASA alert: exactly one of four
function alertLabel(a) {
  if (a.applied) return 'Applied';
  if (a.covers_talisay === false) return 'Not for Talisay';
  if (a.mapped === false) return 'New kind: please review';
  return 'Not applied';
}

// True when every part outside the table rows is known (not out of date)
function othersKnown(data, rows) {
  const shown = new Set(rows.map((r) => r.key));
  return (data?.days || []).every((d) => (d.barangays || []).every((b) => (
    ['flood', 'landslide'].every((f) => shown.has(`${b.id}-${f}`) || !b[f] || b[f].level !== 'unknown')
  )));
}

// Barangay x hazard rows with any level above Green on any day
function buildRows(data) {
  const days = data?.days || [];
  if (!days.length) return [];
  const rows = [];
  (days[0].barangays || []).forEach((b) => {
    HAZARDS.forEach(([field, hazard]) => {
      const cells = days.map((d) => (d.barangays || []).find((x) => x.id === b.id)?.[field] || null);
      if (!cells.some((c) => c && rainLevel(c.level).rank > 0)) return;
      rows.push({ key: `${b.id}-${field}`, name: b.name, hazard, cells });
    });
  });
  return rows;
}

function Cell({ part }) {
  if (!part) return <td className="rw-cell">–</td>;
  const lv = rainLevel(part.level);
  const text = part.level === 'unknown' ? 'Out of date' : lv.rank < 0 ? '–' : lv.label;
  const title = (part.reasons || []).join('; ') || undefined;
  return (
    <td className="rw-cell" title={title}>
      {lv.color && lv.rank > 0 ? (
        <span className="rw-chip" style={{ background: lv.color, color: part.level === 'Yellow' ? '#3a2e00' : '#fff' }}>{text}</span>
      ) : text}
      {lv.rank > 0 && (part.reasons || []).map((r) => <small key={r} className="rw-reason">{r}</small>)}
    </td>
  );
}

export default function RainWatchCard() {
  const [raw, setRaw] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [form, setForm] = useState(false);
  const [cancelling, setCancelling] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const clearToast = useCallback(() => setToast(null), []);
  // Re-read the clock every minute, so the age and the old-colours check never freeze
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), CLOCK_MS);
    return () => clearInterval(t);
  }, []);

  const load = useCallback((background) => (
    rainWatchApi.get(background ? { background: true } : undefined)
      .then((d) => { setRaw(d); setFailed(false); })
      .catch(() => setFailed(true))
      .finally(() => setLoaded(true))
  ), []);

  useEffect(() => {
    load(false);
    const t = setInterval(() => load(true), REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const data = useMemo(() => withClientStale(raw, now), [raw, now]);
  const rows = useMemo(() => buildRows(data), [data]);
  const days = data?.days || [];
  const overrides = (data?.overrides || []).filter((o) => !o.cancelled_at);
  const alerts = data?.pagasa_alerts || [];

  async function confirmCancel() {
    setBusy(true);
    try {
      await rainWatchApi.cancelOverride(cancelling.id);
      setCancelling(null);
      setToast({ id: Date.now(), tone: 'good', message: 'Level cancelled.' });
      await load(false);
    } catch (err) {
      setToast({ id: Date.now(), tone: 'bad', message: err?.message || 'Could not cancel the level.' });
    }
    setBusy(false);
  }

  function saved() {
    setForm(false);
    setToast({ id: Date.now(), tone: 'good', message: 'Level set.' });
    load(false);
  }

  return (
    <section className="adm-card rw-card">
      <div className="drm-section-head">
        <div>
          <h2>Rain watch</h2>
          <p>
            Flood and landslide colours for the next 3 days.{' '}
            {data?.updated_at != null && <span>{updatedText(data.updated_at, now)}.</span>}
            {failed && raw && <span className="rw-stale"> Could not refresh. Trying again.</span>}
            {data && (data.stale || data.updated_at == null) && (
              <span className="rw-stale"> {data.updated_at == null ? 'No forecast yet.' : 'Out of date.'}</span>
            )}
          </p>
        </div>
        <button type="button" className="adm-btn adm-btn-outline adm-btn-sm" onClick={() => setForm(true)}>
          Set a level by hand
        </button>
      </div>

      {!loaded && <p className="rw-muted">Loading…</p>}
      {loaded && failed && !raw && <p className="rw-stale">Could not load the rain watch.</p>}

      {data && (
        <>
          {rows.length > 0 && (
            <div className="rw-table-wrap">
              <table className="rw-table">
                <thead>
                  <tr>
                    <th>Barangay</th>
                    <th>Hazard</th>
                    {days.map((d, i) => <th key={d.key}>{dayLabel(d, i)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.key}>
                      <td>{r.name}</td>
                      <td>{r.hazard}</td>
                      {r.cells.map((c, i) => <Cell key={days[i].key} part={c} />)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="rw-muted">
            {data.stale
              ? 'Forecast colours are hidden while the forecast is out of date.'
              : othersKnown(data, rows) ? 'All other barangays: Green' : 'Other barangays: forecast out of date'}
          </p>

          <h3 className="rw-sub">PAGASA alerts</h3>
          {alerts.length === 0 ? <p className="rw-muted">No PAGASA alerts stored.</p> : (
            <ul className="rw-list">
              {alerts.map((a) => (
                <li key={a.identifier}>
                  <strong>{a.headline || a.event}</strong>
                  <span className="rw-muted"> {a.severity} · until {formatDateTime(a.expires)}</span>
                  <span className={`rw-badge ${a.applied ? 'is-applied' : ''}`}>{alertLabel(a)}</span>
                </li>
              ))}
            </ul>
          )}

          <h3 className="rw-sub">Levels set by hand</h3>
          {overrides.length === 0 ? <p className="rw-muted">None active.</p> : (
            <ul className="rw-list">
              {overrides.map((o) => (
                <li key={o.id}>
                  <strong>{o.hazard} {o.level}</strong>
                  <span className="rw-muted"> until {formatDateTime(o.ends_at)} · {o.created_by_name}</span>
                  <div className="rw-note">{o.note}</div>
                  <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" onClick={() => setCancelling(o)}>Cancel</button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {form && (
        <Modal title="Set a level by hand" onClose={() => setForm(false)} width={480} labelId="rw-form-title">
          <RainWatchOverrideForm onSaved={saved} onCancel={() => setForm(false)} />
        </Modal>
      )}
      {cancelling && (
        <Modal
          title="Cancel this level?"
          onClose={() => !busy && setCancelling(null)}
          width={440}
          labelId="rw-cancel-title"
          footer={(
            <>
              <button type="button" className="adm-btn adm-btn-ghost" onClick={() => setCancelling(null)} disabled={busy}>Keep it</button>
              <button type="button" className="adm-btn adm-btn-danger" onClick={confirmCancel} disabled={busy}>Cancel override</button>
            </>
          )}
        >
          <p>{cancelling.hazard} {cancelling.level} until {formatDateTime(cancelling.ends_at)} will stop raising the colours straight away.</p>
        </Modal>
      )}
      <Toast key={toast?.id} toast={toast} onDone={clearToast} />
    </section>
  );
}
