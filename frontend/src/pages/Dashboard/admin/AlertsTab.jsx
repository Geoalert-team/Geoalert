import React, { useEffect, useState } from 'react';
import { adminApi } from '../../../api/adminApi';
import { Icon, formatDateTime } from './adminShared';

/**
 * Notification and alert monitoring (WBS 3.8.5).
 *
 * Publishing a hazard fans an alert out to every account in the affected
 * barangays. Until now nothing showed whether it landed â€” an alert that
 * reached nobody looked the same as one that reached everybody. This lists
 * each alert with how many accounts it went to and how many have opened it.
 *
 * Built from the adm- classes the other admin tabs use, so it needs no
 * stylesheet of its own.
 */

const PAGE_SIZE = 20; // matches AlertMonitorView.PAGE_SIZE

const WINDOWS = [
  { value: 1, label: 'Last 24 hours' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
];

const SEVERITY = {
  Red:    { label: 'Extreme',  tone: 'bad' },
  Orange: { label: 'Moderate', tone: 'warn' },
  Green:  { label: 'Low',      tone: 'good' },
};

function SeverityTag({ severity }) {
  const meta = SEVERITY[severity] || { label: severity || 'Unknown', tone: 'neutral' };
  return <span className={`adm-action adm-action-${meta.tone}`}>{meta.label}</span>;
}

function Stat({ value, label, note, tone = 'navy', icon }) {
  return (
    <div className="adm-metric">
      <span className={`adm-metric-icon adm-metric-${tone}`}><Icon name={icon} size={20} /></span>
      <div className="adm-metric-text">
        <span className="adm-metric-label">{label}</span>
        <span className="adm-metric-value">{value ?? 'â€”'}</span>
        {note && <span className="adm-metric-note">{note}</span>}
      </div>
    </div>
  );
}

export default function AlertsTab() {
  const [days, setDays] = useState(7);
  const [severity, setSeverity] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = { days, page };
    if (severity) params.severity = severity;

    adminApi.alerts(params)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setFailed(false);
      })
      .catch(() => { if (!cancelled) { setData(null); setFailed(true); } })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [days, severity, page, reloadKey]);

  function changeWindow(value) {
    setDays(Number(value));
    setPage(1);
  }

  function changeSeverity(value) {
    setSeverity(value);
    setPage(1);
  }

  const summary = data?.summary;
  const results = data?.results || [];
  const count = data?.count || 0;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const from = count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, count);
  const silent = summary?.alerts_with_no_recipients || 0;

  if (failed && !data) {
    return (
      <div className="adm-card adm-empty">
        <Icon name="info" size={28} />
        <p>Alert monitoring is unavailable right now.</p>
        <button
          type="button"
          className="adm-btn adm-btn-outline adm-btn-sm"
          onClick={() => setReloadKey((k) => k + 1)}
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="adm-metrics">
        <Stat
          icon="alert"
          tone="navy"
          label="Alerts issued"
          value={summary?.alerts_issued}
          note={`In the ${WINDOWS.find((w) => w.value === days)?.label.toLowerCase() || 'window'}`}
        />
        <Stat
          icon="mail"
          tone="blue"
          label="Notifications sent"
          value={summary?.notifications_sent}
          note={summary?.accounts_reached != null ? `${summary.accounts_reached} accounts reached` : null}
        />
        <Stat
          icon="userCheck"
          tone="green"
          label="Read"
          value={summary?.read_rate != null ? `${summary.read_rate}%` : 'â€”'}
          note={summary ? `${summary.notifications_read} read Â· ${summary.notifications_unread} unread` : null}
        />
        <Stat
          icon="userX"
          tone="amber"
          label="Reached nobody"
          value={silent}
          note={silent ? 'Check barangay assignments' : 'Every alert had recipients'}
        />
      </div>

      {silent > 0 && (
        <div className="adm-alert adm-alert-warn">
          <Icon name="info" size={18} />
          <span>
            {silent === 1
              ? 'One alert was sent to no accounts at all.'
              : `${silent} alerts were sent to no accounts at all.`}
            {' '}
            That usually means no active account is assigned to the affected barangay.
          </span>
        </div>
      )}

      <div className="adm-card adm-card-flush">
        <div className="adm-toolbar">
          <select
            className="adm-select"
            value={days}
            onChange={(e) => changeWindow(e.target.value)}
            aria-label="Time window"
          >
            {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>

          <select
            className="adm-select"
            value={severity}
            onChange={(e) => changeSeverity(e.target.value)}
            aria-label="Filter by severity"
          >
            <option value="">All severities</option>
            {Object.entries(SEVERITY).map(([code, meta]) => (
              <option key={code} value={code}>{meta.label}</option>
            ))}
          </select>

          <div className="adm-toolbar-cta">
            <button
              type="button"
              className="adm-btn adm-btn-ghost adm-btn-sm"
              onClick={() => setReloadKey((k) => k + 1)}
              disabled={loading}
            >
              <Icon name="refresh" size={15} className={loading ? 'adm-spin' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {loading && !data ? (
          <div className="adm-skeleton">
            {[0, 1, 2, 3, 4].map((i) => <div key={i} className="adm-skeleton-row" />)}
          </div>
        ) : results.length === 0 ? (
          <div className="adm-empty">
            <Icon name="alert" size={28} />
            <p>No alerts were issued in this period.</p>
          </div>
        ) : (
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th>Hazard</th>
                  <th>Severity</th>
                  <th>Issued</th>
                  <th>Sent to</th>
                  <th>Read</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {results.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <div className="adm-person-text">
                        <span className="adm-person-name">
                          {a.hazard_type || 'Hazard'}
                          {a.barangay ? ` Â· ${a.barangay}` : ''}
                        </span>
                        <span className="adm-person-sub">
                          {a.issued_by ? `by ${a.issued_by}` : 'issuer not recorded'}
                          {a.is_sample && ' Â· sample'}
                        </span>
                      </div>
                    </td>
                    <td><SeverityTag severity={a.severity} /></td>
                    <td className="adm-nowrap adm-date">{formatDateTime(a.created_at)}</td>
                    <td>
                      {a.recipients === 0
                        ? <span className="adm-action adm-action-bad">nobody</span>
                        : `${a.recipients} account${a.recipients === 1 ? '' : 's'}`}
                    </td>
                    <td>
                      {a.read_rate == null
                        ? <span className="adm-muted">â€”</span>
                        : (
                          <>
                            <strong>{a.read_rate}%</strong>
                            <span className="adm-muted"> Â· {a.unread} unread</span>
                          </>
                        )}
                    </td>
                    <td className="adm-nowrap">{a.zone_status || 'â€”'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {count > 0 && (
          <div className="adm-pager">
            <span className="adm-table-meta">Showing {from}â€“{to} of {count}</span>
            <div className="adm-row-actions">
              <button
                type="button"
                className="adm-btn adm-btn-outline adm-btn-sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
              >
                <Icon name="chevronLeft" size={15} /> Previous
              </button>
              <button
                type="button"
                className="adm-btn adm-btn-outline adm-btn-sm"
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page >= pages || loading}
              >
                Next <Icon name="chevronRight" size={15} />
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
