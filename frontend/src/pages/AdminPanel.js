import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function AdminPanel() {
  const [users, setUsers] = useState([]);
  const [settings, setSettings] = useState({});
  const [logs, setLogs] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [form, setForm] = useState({ email: '', password: '', role: 'Barangay_Personnel' });
  const [error, setError] = useState('');

  function load() {
    api.users().then((d) => setUsers(d.results || d || [])).catch((e) => setError(e.message));
    api.systemSettings().then(setSettings).catch((e) => setError(e.message));
    api.systemLogs().then((d) => setLogs(d.results || d || [])).catch((e) => setError(e.message));
    api.systemPerformance().then(setPerformance).catch((e) => setError(e.message));
  }

  useEffect(() => { load(); }, []);

  async function addUser(e) {
    e.preventDefault();
    try {
      await api.createUser(form);
      setForm({ email: '', password: '', role: 'Barangay_Personnel' });
      load();
    } catch (e) { setError(e.message); }
  }

  async function deactivate(id) {
    try { await api.deactivateUser(id); load(); } catch (e) { setError(e.message); }
  }

  async function saveSettings() {
    try { await api.updateSystemSettings(settings); } catch (e) { setError(e.message); }
  }

  return (
    <div className="feature-page">
      <h2>System Administration</h2>
      <p className="muted">User management, system settings, performance monitoring, and logs.</p>
      <div className="error-text">{error}</div>

      <div className="card">
        <h3>Create user</h3>
        <form onSubmit={addUser} className="form-grid">
          <div className="field"><label>Email</label><input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required /></div>
          <div className="field"><label>Temporary password</label><input type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} required /></div>
          <div className="field"><label>Role</label><select value={form.role} onChange={e => setForm({...form, role: e.target.value})}><option>Barangay_Personnel</option><option>DRRMO_Officer</option><option>System_Admin</option></select></div>
          <div><button className="btn primary">Create user</button></div>
        </form>
      </div>

      <div className="card">
        <h3>Users</h3>
        {users.map(u => <div className="list-row" key={u.id}><div><strong>{u.email}</strong><div className="muted">{u.role?.name || u.role} Â· {u.is_active === false ? 'Inactive' : 'Active'}</div></div>{u.is_active !== false && <button className="btn" onClick={() => deactivate(u.id)}>Deactivate</button>}</div>)}
      </div>

      <div className="card">
        <h3>System settings</h3>
        {Object.entries(settings || {}).map(([key, value]) => (
          <div className="field" key={key}><label>{key}</label><input value={String(value ?? '')} onChange={e => setSettings({...settings, [key]: e.target.value})} /></div>
        ))}
        <button className="btn primary" onClick={saveSettings}>Save settings</button>
      </div>

      <div className="card">
        <h3>Performance</h3>
        {performance ? Object.entries(performance).map(([key, value]) => <div className="list-row" key={key}><span>{key}</span><strong>{String(value)}</strong></div>) : <p className="muted">No performance data.</p>}
      </div>

      <div className="card">
        <h3>System logs</h3>
        {logs.length ? logs.map((log, i) => <div className="list-row" key={log.id || i}><div><strong>{log.action || log.event || 'System event'}</strong><div className="muted">{log.user_email || log.user} Â· {log.created_at || log.timestamp}</div></div><span>{log.status || ''}</span></div>) : <p className="muted">No logs available.</p>}
      </div>
    </div>
  );
}
