import React, { useEffect, useState } from 'react';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { adminApi } from '../../api/adminApi';
import '../css/Dashboard.css';

const TABS = ['Overview', 'Users', 'Logs'];

export default function AdminDashboard() {
  const [tab, setTab] = useState('Overview');
  const [metrics, setMetrics] = useState(null);
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const [newUser, setNewUser] = useState({ full_name: '', email: '', role_id: '' });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    adminApi.metrics().then(setMetrics).catch(() => setMetrics(null)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (tab === 'Users') refreshUsers();
    if (tab === 'Logs') adminApi.logs().then(setLogs).catch(() => setLogs([]));
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
      await adminApi.users.create(newUser);
      setNewUser({ full_name: '', email: '', role_id: '' });
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

  async function resetPassword(id) {
    await adminApi.users.resetPassword(id);
    window.alert('A password reset was triggered for this user.');
  }

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
              {/* Simple number/string/boolean fields become stat cards.
                  Arrays/objects (e.g. a list of recent users) are NOT
                  stat cards — dumping raw JSON there breaks the layout. */}
              <div className="db-stats">
                {Object.entries(metrics)
                  .filter(([, value]) => value === null || typeof value !== 'object')
                  .map(([key, value]) => (
                    <div key={key} className="db-stat">
                      <div className="db-stat-value">{String(value)}</div>
                      <div className="db-stat-label">{key.replace(/_/g, ' ')}</div>
                    </div>
                  ))}
              </div>

              {/* Any array/object fields render as their own readable card
                  instead of being skipped silently or JSON-dumped. */}
              {Object.entries(metrics)
                .filter(([, value]) => value !== null && typeof value === 'object')
                .map(([key, value]) => (
                  <div key={key} className="db-card">
                    <h2>{key.replace(/_/g, ' ')}</h2>
                    {Array.isArray(value) ? (
                      value.length === 0 ? (
                        <p className="db-empty">Nothing here yet.</p>
                      ) : (
                        <div className="db-list">
                          {value.map((item, i) => (
                            <div key={item.id ?? i} className="db-item">
                              {typeof item === 'object' && item !== null ? (
                                Object.entries(item).map(([k, v]) => (
                                  <div key={k} className="db-item-meta">
                                    <strong style={{ color: 'var(--db-heading)' }}>{k.replace(/_/g, ' ')}:</strong>{' '}
                                    {typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}
                                  </div>
                                ))
                              ) : (
                                <span>{String(item)}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )
                    ) : (
                      <div className="db-list">
                        {Object.entries(value).map(([k, v]) => (
                          <div key={k} className="db-item">
                            <div className="db-item-title">{k.replace(/_/g, ' ')}</div>
                            <div className="db-item-meta">
                              {typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
            </>
          ) : (
            <p style={{ color: 'var(--db-soft)' }}>Metrics unavailable right now.</p>
          )
        )}

        {tab === 'Users' && (
          <div className="db-grid-2">
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
                <label>Role ID</label>
                <input required value={newUser.role_id}
                  onChange={(e) => setNewUser({ ...newUser, role_id: e.target.value })}
                  placeholder="e.g. 2 for DRRMO Officer" />
              </div>
              {error && <p className="error-text">{error}</p>}
              <button className="btn primary" disabled={creating}>
                {creating ? 'Creating…' : 'Create user'}
              </button>
            </form>

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
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td>{u.full_name}</td>
                        <td>{u.email}</td>
                        <td>{u.role?.name || u.role}</td>
                        <td>
                          <div className="db-btn-row">
                            <button className="db-btn db-btn-outline" onClick={() => resetPassword(u.id)}>Reset password</button>
                            <button className="db-btn db-btn-danger" onClick={() => deactivate(u.id)}>Deactivate</button>
                          </div>
                        </td>
                      </tr>
                    ))}
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
              <div className="db-list">
                {(logs.results || logs).map((log) => (
                  <div key={log.id} className="db-item">
                    <div className="db-item-head">
                      <span className="db-item-title">{log.action || log.event}</span>
                      <span className="db-item-meta">
                        {new Date(log.created_at || log.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <div className="db-item-meta">
                      {log.actor_name || log.user} {log.detail ? `— ${log.detail}` : ''}
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