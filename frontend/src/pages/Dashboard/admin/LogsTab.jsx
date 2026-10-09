import React, { useEffect, useState } from 'react';
import { adminApi } from '../../../api/adminApi';
import { ACTION_META, Icon, actionMeta, formatDateTime } from './adminShared';

const PAGE_SIZE = 25; // matches AuditLogPagination on the backend

export function ActionTag({ action }) {
  const meta = actionMeta(action);
  return (
    <span className={`adm-action adm-action-${meta.tone}`}>
      <Icon name={meta.icon} size={14} strokeWidth={2.4} />
      {meta.label}
    </span>
  );
}

export default function LogsTab() {
  const [filters, setFilters] = useState({ action: '', date_from: '', date_to: '' });
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = { page };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    adminApi
      .logs(params)
      .then((res) => {
        if (cancelled) return;
        // Paginated ({count, results}) or a plain list from older backends
        setData(Array.isArray(res) ? { count: res.length, results: res } : res);
        setFailed(false);
      })
      .catch(() => { if (!cancelled) { setData({ count: 0, results: [] }); setFailed(true); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters, page]);

  function setFilter(key, value) {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  }

  const results = data?.results || [];
  const count = data?.count || 0;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const from = count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, count);
  const filtersOn = filters.action || filters.date_from || filters.date_to;

  return (
    <div className="adm-card adm-card-flush">
      <div className="adm-toolbar">
        <select className="adm-select" value={filters.action} onChange={(e) => setFilter('action', e.target.value)} aria-label="Filter by action">
          <option value="">All actions</option>
          {Object.entries(ACTION_META).map(([key, meta]) => (
            <option key={key} value={key}>{meta.label}</option>
          ))}
        </select>
        <label className="adm-date">
          <span>From</span>
          <input type="date" value={filters.date_from} max={filters.date_to || undefined} onChange={(e) => setFilter('date_from', e.target.value)} />
        </label>
        <label className="adm-date">
          <span>To</span>
          <input type="date" value={filters.date_to} min={filters.date_from || undefined} onChange={(e) => setFilter('date_to', e.target.value)} />
        </label>
        {filtersOn && (
          <button type="button" className="adm-link" onClick={() => { setFilters({ action: '', date_from: '', date_to: '' }); setPage(1); }}>
            Clear filters
          </button>
        )}
      </div>

      <div className="adm-table-meta">
        {loading ? 'Loading activity…' : count === 0 ? 'No entries' : `Showing ${from}–${to} of ${count} entries`}
      </div>

      <div className="adm-table-wrap">
        <table className="adm-table adm-table-logs">
          <thead>
            <tr>
              <th>Action</th>
              <th>Details</th>
              <th>Performed by</th>
              <th>IP address</th>
              <th>Date and time</th>
            </tr>
          </thead>
          <tbody>
            {loading && results.length === 0 && [0, 1, 2, 3].map((i) => (
              <tr key={i} className="adm-skeleton-row">
                {[0, 1, 2, 3, 4].map((j) => <td key={j}><span className="adm-skeleton" /></td>)}
              </tr>
            ))}
            {!loading && results.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <div className="adm-empty">
                    <Icon name="list" size={28} />
                    <p>{failed ? 'The activity log could not be loaded.' : filtersOn ? 'No activity matches these filters.' : 'No activity recorded yet.'}</p>
                  </div>
                </td>
              </tr>
            )}
            {results.map((log) => (
              <tr key={log.id} className={loading ? 'is-loading' : ''}>
                <td className="adm-nowrap"><ActionTag action={log.action} /></td>
                <td className="adm-log-detail">{log.details || log.detail || '—'}</td>
                <td>
                  <div className="adm-contact">
                    <span>{log.user_name || 'System'}</span>
                    {log.user_email && <span className="adm-person-sub">{log.user_email}</span>}
                  </div>
                </td>
                <td className="adm-mono adm-muted">{log.ip_address || '—'}</td>
                <td className="adm-nowrap adm-muted">{formatDateTime(log.created_at || log.timestamp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="adm-pager">
          <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
            <Icon name="chevronLeft" size={16} /> Previous
          </button>
          <span>Page {page} of {pages}</span>
          <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" disabled={page >= pages || loading} onClick={() => setPage((p) => p + 1)}>
            Next <Icon name="chevronRight" size={16} />
          </button>
        </div>
      )}
    </div>
  );
}