import React, { useEffect, useState } from 'react';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { adminApi } from '../../api/adminApi';
import '../css/Dashboard.css';

const TABS = ['Overview', 'Users', 'Logs'];

const METRIC_DISPLAY = [
  { key: 'total_users', label: 'Total users', icon: '👥' },
  { key: 'active_users', label: 'Active users', icon: '✅' },
  { key: 'active_hazards', label: 'Active hazards', icon: '⚠️' },
  { key: 'published_guidance', label: 'Published guidance', icon: '📘' },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState('Overview');
  const [metrics, setMetrics] = useState(null);
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const [newUser, setNewUser] = useState({ full_name: '', email: '', role_id: '' });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  // Shown after creating a user or resetting a password — the backend only
  // returns the plain temporary password this one time, so it has to be
  // shown now or it's gone.
  const [revealedPassword, setRevealedPassword] = useState(null); // { email, password }
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    adminApi.metrics().then(setMetrics).catch(() => setMetrics(null)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (tab === 'Users') {
      refreshUsers();
      if (roles.length === 0) {
        adminApi.roles().then((data) => {
          const list = data.results || data;
          setRoles(list);
          if (list[0]) setNewUser((u) => (u.role_id ? u : { ...u, role_id: list[0].id }));
        }).catch(() => setRoles([]));
      }
    }
    if (tab === 'Logs') adminApi.logs().then(setLogs).catch(() => setLogs([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function refreshUsers() {
    try {
      const data = await adminApi.users.list();
      setUsers(data.results || data);
    } catch {
      setUsers([]);
    }
  }

  async function createUser(e) {
    e.preventDefault();
    setError('');
    setCreating(true);
    try {
      const result = await adminApi.users.create(newUser);
      setRevealedPassword({ email: newUser.email, password: result.temporary_password });
      setCopied(false);
      setNewUser({ full_name: '', email: '', role_id: roles[0]?.id || '' });
      refreshUsers();
    } catch (err) {
      setError(err.message || 'Could not create user');
    } finally {
      setCreating(false);
    }
  }

  async function deactivate(id) {
    if (!window.confirm('Deactivate this account?')) return;
    await adminApi.users.deactivate(id);
    refreshUsers();
  }

  async function resetPassword(id, email) {
    const result = await adminApi.users.resetPassword(id);
    setRevealedPassword({ email, password: result.temporary_password });
    setCopied(false);
  }

  function copyPassword() {
    navigator.clipboard.writeText(revealedPassword.password).then(() => setCopied(true));
  }

  const recentActivity = metrics?.recent_activity || [];
  const isOperational = (metrics?.system_status || '').toLowerCase() === 'operational';

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Admin dashboard</h1>
          <p>System-wide metrics, user accounts, and activity logs.</p>
        </div>

        <div className="db-tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              className={`db-tab ${tab === t ? 'is-active' : ''}`}
              onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>

        {tab === 'Overview' && (
          loading ? (
            <p style={{ color: 'var(--db-soft)' }}>Loading metrics…</p>
          ) : metrics ? (
            <>
              <div className="db-status-row">
                <span className={`db-status-dot ${isOperational ? '' : 'is-down'}`} />
                <span style={{ fontSize: '.88rem', color: 'var(--db-soft)' }}>
                  System status: <strong style={{ color: 'var(--db-heading)' }}>{metrics.system_status}</strong>
                </span>
              </div>

              <div className="db-stats">
                {METRIC_DISPLAY.map(({ key, label, icon }) => (
                  <div key={key} className="db-metric">
                    <span className="db-metric-icon" aria-hidden="true">{icon}</span>
                    <div>
                      <div className="db-metric-value">{metrics[key] ?? '—'}</div>
                      <div className="db-metric-label">{label}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="db-card">
                <h2>Recent activity</h2>
                <p className="db-card-sub">The last few actions taken by any admin.</p>
                {recentActivity.length === 0 ? (
                  <p className="db-empty">No activity recorded yet.</p>
                ) : (
                  <div className="db-activity">
                    {recentActivity.map((log) => (
                      <div key={log.id} className="db-activity-item">
                        <span className="db-activity-dot" />
                        <div className="db-activity-body">
                          <div className="db-activity-title">
                            {(log.action || '').replace(/_/g, ' ')}
                          </div>
                          <div className="db-activity-meta">
                            {log.user_name || log.user_email} · {new Date(log.created_at).toLocaleString()}
                          </div>
                          {log.details && <div className="db-activity-meta">{log.details}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <p style={{ color: 'var(--db-soft)' }}>Metrics unavailable right now.</p>
          )
        )}

        {tab === 'Users' && (
          <div className="db-grid-2">
            <div>
              {revealedPassword && (
                <div className="db-card db-reveal" style={{ marginBottom: 16 }}>
                  <h2>Temporary password for {revealedPassword.email}</h2>
                  <p className="db-card-sub" style={{ marginBottom: 0 }}>
                    This is shown once. Copy it now and share it with the user securely.
                  </p>
                  <div className="db-reveal-row">
                    <code className="db-code">{revealedPassword.password}</code>
                    <button type="button" className="db-btn db-btn-outline" onClick={copyPassword}>
                      {copied ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                  <button
                    type="button"
                    className="db-btn db-btn-outline"
                    style={{ marginTop: 12 }}
                    onClick={() => setRevealedPassword(null)}
                  >
                    Dismiss
                  </button>
                </div>
              )}

              <form onSubmit={createUser} className="db-card">
                <h2>Add a user</h2>
                <p className="db-card-sub">Create an account for barangay or DRRMO personnel.</p>
                <div className="field">
                  <label>Full name</label>
                  <input required value={newUser.full_name}
                    onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })} />
                </div>
                <div className="field">
                  <label>Email</label>
                  <input type="email" required value={newUser.email}
                    onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} />
                </div>
                <div className="field">
                  <label>Role</label>
                  <select
                    required
                    value={newUser.role_id}
                    onChange={(e) => setNewUser({ ...newUser, role_id: e.target.value })}
                  >
                    {roles.length === 0 && <option value="">Loading roles…</option>}
                    {roles.map((r) => (
                      <option key={r.id} value={r.id}>{r.name}</option>
                    ))}
                  </select>
                </div>
                {error && <p className="error-text">{error}</p>}
                <button className="btn primary" disabled={creating || roles.length === 0}>
                  {creating ? 'Creating…' : 'Create user'}
                </button>
              </form>
            </div>

            <div className="db-card">
              <h2>All users</h2>
              <p className="db-card-sub">{users.length} account{users.length === 1 ? '' : 's'}</p>
              {users.length === 0 ? (
                <p className="db-empty">No users yet.</p>
              ) : (
                <table className="db-table">
                  <thead>
                    <tr><th>Name</th><th>Email</th><th>Role</th><th /></tr>
                  </thead>
                  <tbody>
                    {users.map((u) => {
                      const isSelf = currentUser && String(currentUser.id) === String(u.id);
                      const busy = statusBusyId === u.id;
                      return (
                        <tr key={u.id}>
                          <td>{u.full_name}</td>
                          <td>{u.email}</td>
                          <td>{u.role?.name || u.role}</td>
                          <td>
                            <span className={`db-badge ${u.is_active ? 'db-badge-active-status' : 'db-badge-inactive-status'}`}>
                              {u.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </td>
                          <td>
                            <div className="db-btn-row">
                              <button className="db-btn db-btn-outline" onClick={() => resetPassword(u.id, u.email)}>
                                Reset password
                              </button>
                              {u.is_active ? (
                                <button
                                  className="db-btn db-btn-danger"
                                  disabled={isSelf || busy}
                                  title={isSelf ? "You can't deactivate your own account" : undefined}
                                  onClick={() => deactivate(u.id)}
                                >
                                  {busy ? 'Working…' : 'Deactivate'}
                                </button>
                              ) : (
                                <button
                                  className="db-btn db-btn-primary"
                                  disabled={busy}
                                  onClick={() => activate(u.id)}
                                >
                                  {busy ? 'Working…' : 'Activate'}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {tab === 'Logs' && (
          <div className="db-card">
            <h2>Audit logs</h2>
            <p className="db-card-sub">Recent system activity.</p>
            {logs.length === 0 ? (
              <p className="db-empty">No activity recorded yet.</p>
            ) : (
              <div className="db-activity">
                {(logs.results || logs).map((log) => (
                  <div key={log.id} className="db-activity-item">
                    <span className="db-activity-dot" />
                    <div className="db-activity-body">
                      <div className="db-activity-title">{(log.action || log.event || '').replace(/_/g, ' ')}</div>
                      <div className="db-activity-meta">
                        {log.actor_name || log.user_name || log.user} · {new Date(log.created_at || log.timestamp).toLocaleString()}
                      </div>
                      {(log.detail || log.details) && (
                        <div className="db-activity-meta">{log.detail || log.details}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}