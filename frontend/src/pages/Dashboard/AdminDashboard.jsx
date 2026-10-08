import React, { useCallback, useEffect, useState } from 'react';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { useAuth } from '../../context/AuthContext';
import { adminApi } from '../../api/adminApi';
import UsersTab from './admin/UsersTab';
import LogsTab, { ActionTag } from './admin/LogsTab';
import { Icon, ROLE_META, Toast, roleName, timeAgo } from './admin/adminShared';
import '../css/Dashboard.css';
import '../css/AdminDashboard.css';

const TABS = [
  { key: 'overview', label: 'Overview', icon: 'grid' },
  { key: 'users', label: 'Users', icon: 'users' },
  { key: 'logs', label: 'Activity log', icon: 'list' },
];

function MetricCard({ icon, tone, value, label, note }) {
  return (
    <div className="adm-metric">
      <span className={`adm-metric-icon adm-metric-${tone}`}><Icon name={icon} size={20} /></span>
      <div className="adm-metric-text">
        <span className="adm-metric-label">{label}</span>
        <span className="adm-metric-value">{value ?? '—'}</span>
        {note && <span className="adm-metric-note">{note}</span>}
      </div>
    </div>
  );
}

function Overview({ metrics, users, onAddUser, onOpenTab }) {
  const total = metrics?.total_users ?? users.length;
  const active = metrics?.active_users ?? users.filter((u) => u.is_active).length;
  const inactive = metrics?.inactive_users ?? total - active;

  // Prefer the backend's counts; fall back to counting the loaded user list
  const byRole = metrics?.users_by_role || users.reduce((acc, u) => {
    const key = roleName(u.role) || 'Unassigned';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const activity = metrics?.recent_activity || [];

  return (
    <>
      <div className="adm-metrics">
        <MetricCard icon="users" tone="navy" label="Total accounts" value={total} note={`${Object.keys(byRole).length} roles in use`} />
        <MetricCard
          icon="userCheck"
          tone="green"
          label="Active accounts"
          value={active}
          note={inactive ? `${inactive} deactivated` : 'All accounts can sign in'}
        />
        <MetricCard icon="alert" tone="amber" label="Active hazards" value={metrics?.active_hazards} note="Currently shown on the map" />
        <MetricCard icon="book" tone="blue" label="Published guidance" value={metrics?.published_guidance} note="Visible to residents" />
      </div>

      <div className="adm-overview-grid">
        <section className="adm-card">
          <div className="adm-card-head">
            <div>
              <h2>Recent activity</h2>
              <p>The latest actions taken by administrators.</p>
            </div>
            <button type="button" className="adm-link" onClick={() => onOpenTab('logs')}>
              View all <Icon name="arrowRight" size={14} />
            </button>
          </div>
          {activity.length === 0 ? (
            <div className="adm-empty">
              <Icon name="clock" size={28} />
              <p>No activity recorded yet.</p>
            </div>
          ) : (
            <ul className="adm-feed">
              {activity.map((log) => (
                <li key={log.id} className="adm-feed-item">
                  <div className="adm-feed-main">
                    <ActionTag action={log.action} />
                    <p className="adm-feed-detail">{log.details || '—'}</p>
                  </div>
                  <div className="adm-feed-meta">
                    <span>{log.user_name || log.user_email || 'System'}</span>
                    <span title={new Date(log.created_at).toLocaleString()}>{timeAgo(log.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="adm-side">
          <section className="adm-card">
            <div className="adm-card-head">
              <div>
                <h2>Accounts by role</h2>
                <p>{total} account{total === 1 ? '' : 's'} in total</p>
              </div>
            </div>
            <ul className="adm-roles">
              {Object.entries(ROLE_META).map(([key, meta]) => {
                const n = byRole[key] || 0;
                const pct = total ? Math.round((n / total) * 100) : 0;
                return (
                  <li key={key}>
                    <div className="adm-roles-row">
                      <span className={`adm-roles-icon adm-tone-${meta.tone}`}><Icon name={meta.icon} size={16} /></span>
                      <span className="adm-roles-label">{meta.label}</span>
                      <span className="adm-roles-count">{n}</span>
                    </div>
                    <div className="adm-bar"><span className={`adm-tone-${meta.tone}`} style={{ width: `${pct}%` }} /></div>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="adm-card">
            <div className="adm-card-head">
              <div>
                <h2>Quick actions</h2>
              </div>
            </div>
            <div className="adm-quick">
              <button type="button" className="adm-quick-btn" onClick={onAddUser}>
                <span className="adm-quick-icon"><Icon name="userPlus" size={18} /></span>
                <span><strong>Add a user</strong><small>Create a staff account</small></span>
                <Icon name="chevronRight" size={16} />
              </button>
              <button type="button" className="adm-quick-btn" onClick={() => onOpenTab('users')}>
                <span className="adm-quick-icon"><Icon name="users" size={18} /></span>
                <span><strong>Manage accounts</strong><small>Edit, reset or deactivate</small></span>
                <Icon name="chevronRight" size={16} />
              </button>
              <button type="button" className="adm-quick-btn" onClick={() => onOpenTab('logs')}>
                <span className="adm-quick-icon"><Icon name="list" size={18} /></span>
                <span><strong>Review activity</strong><small>Full audit trail</small></span>
                <Icon name="chevronRight" size={16} />
              </button>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

export default function AdminDashboard() {
  const { user: currentUser } = useAuth();
  const [tab, setTab] = useState('overview');
  const [metrics, setMetrics] = useState(null);
  const [metricsFailed, setMetricsFailed] = useState(false);
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [roles, setRoles] = useState([]);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [formRequest, setFormRequest] = useState(false);
  const [toast, setToast] = useState(null);

  const loadMetrics = useCallback(() => (
    adminApi.metrics()
      .then((m) => { setMetrics(m); setMetricsFailed(false); })
      .catch(() => setMetricsFailed(true))
  ), []);

  const loadUsers = useCallback(() => (
    adminApi.users.list()
      .then((data) => setUsers(data.results || data))
      .catch(() => setUsers([]))
      .finally(() => setUsersLoading(false))
  ), []);

  const refreshAll = useCallback(() => {
    setRefreshing(true);
    return Promise.all([loadMetrics(), loadUsers()]).finally(() => {
      setRefreshing(false);
      setUpdatedAt(new Date());
    });
  }, [loadMetrics, loadUsers]);

  useEffect(() => {
    refreshAll();
    adminApi.roles().then((data) => setRoles(data.results || data)).catch(() => setRoles([]));
  }, [refreshAll]);

  const notify = useCallback((message, tone = 'good') => setToast({ message, tone, id: Date.now() }), []);
  const clearToast = useCallback(() => setToast(null), []);

  const operational = !metricsFailed && (metrics?.system_status || '').toLowerCase() === 'operational';
  const statusText = metricsFailed ? 'Status unavailable' : metrics ? metrics.system_status : 'Checking status…';

  return (
    <div className="db adm">
      <PublicNavbar />
      <div className="adm-wrap">
        <header className="adm-header">
          <div>
            <p className="adm-eyebrow">System administration</p>
            <h1>Admin dashboard</h1>
            <p className="adm-lede">Manage staff accounts, review activity and keep an eye on GeoAlert at a glance.</p>
          </div>
          <div className="adm-header-side">
            <span className={`adm-system ${operational ? 'is-ok' : metricsFailed ? 'is-down' : ''}`}>
              <span className="adm-system-dot" />
              {statusText}
            </span>
            <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" onClick={refreshAll} disabled={refreshing} title="Refresh data">
              <Icon name="refresh" size={15} className={refreshing ? 'adm-spin' : ''} />
              {updatedAt ? `Updated ${updatedAt.toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit' })}` : 'Refresh'}
            </button>
          </div>
        </header>

        <nav className="adm-tabs" role="tablist" aria-label="Admin sections">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              className={`adm-tab ${tab === t.key ? 'is-active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              <Icon name={t.icon} size={16} />
              {t.label}
              {t.key === 'users' && !usersLoading && <span className="adm-tab-count">{users.length}</span>}
            </button>
          ))}
        </nav>

        {tab === 'overview' && (
          metricsFailed && !metrics ? (
            <div className="adm-card adm-empty">
              <Icon name="info" size={28} />
              <p>Metrics are unavailable right now.</p>
              <button type="button" className="adm-btn adm-btn-outline adm-btn-sm" onClick={refreshAll}>Try again</button>
            </div>
          ) : (
            <Overview
              metrics={metrics}
              users={users}
              onOpenTab={setTab}
              onAddUser={() => { setTab('users'); setFormRequest(true); }}
            />
          )
        )}

        {tab === 'users' && (
          <UsersTab
            users={users}
            roles={roles}
            currentUser={currentUser}
            loading={usersLoading}
            onChanged={refreshAll}
            notify={notify}
            formRequest={formRequest}
            clearFormRequest={() => setFormRequest(false)}
          />
        )}

        {tab === 'logs' && <LogsTab />}
      </div>

      <Toast key={toast?.id} toast={toast} onDone={clearToast} />
    </div>
  );
}