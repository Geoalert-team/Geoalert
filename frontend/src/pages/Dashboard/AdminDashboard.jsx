import React, { useEffect, useState } from 'react';
import { usersApi, settingsApi, logsApi } from '../../api/mockApi';
import Navbar from '../../components/Navbar';

const TABS = ['Users', 'Settings', 'Logs & Performance'];
const ROLE_OPTIONS = ['System_Admin', 'DRRMO_Officer', 'Barangay_Personnel'];

export default function AdminDashboard() {
  const [tab, setTab] = useState('Users');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 880, margin: '0 auto', width: '100%' }}>
        <h2 style={{ marginBottom: 4 }}>Admin dashboard</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 16 }}>
          Mock data â€” no backend yet. Real accounts today can only be managed via Django's /django-admin/.
        </p>
        <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
          {TABS.map((t) => (
            <button key={t} className="btn" style={{ borderColor: tab === t ? 'var(--accent)' : 'var(--line)', color: tab === t ? 'var(--accent)' : 'var(--text)' }}
                    onClick={() => setTab(t)}>{t}</button>
          ))}
        </div>
        {tab === 'Users' && <UsersTab />}
        {tab === 'Settings' && <SettingsTab />}
        {tab === 'Logs & Performance' && <LogsTab />}
      </div>
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState(ROLE_OPTIONS[2]);

  useEffect(() => { refresh(); }, []);
  async function refresh() { setUsers(await usersApi.list()); }

  async function createUser(e) {
    e.preventDefault();
    await usersApi.create({ full_name: fullName, email, role });
    setFullName(''); setEmail(''); setShowForm(false);
    refresh();
  }

  async function toggleActive(u) {
    await usersApi.setActive(u.id, !u.is_active);
    refresh();
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn primary" onClick={() => setShowForm((s) => !s)}>{showForm ? 'Cancel' : 'Add user'}</button>
      </div>
      {showForm && (
        <form onSubmit={createUser} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 16, marginBottom: 16 }}>
          <div className="field"><label>Full name</label><input value={fullName} onChange={(e) => setFullName(e.target.value)} required /></div>
          <div className="field"><label>Email</label><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
          <div className="field">
            <label>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <button className="btn primary">Create</button>
        </form>
      )}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--text-muted)', borderBottom: '1px solid var(--line)' }}>
            <th style={{ padding: 8 }}>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderBottom: '1px solid var(--line)' }}>
              <td style={{ padding: 8 }}>{u.full_name}</td>
              <td>{u.email}</td>
              <td>{u.role}</td>
              <td style={{ color: u.is_active ? 'var(--sev-green)' : 'var(--sev-red)' }}>{u.is_active ? 'Active' : 'Deactivated'}</td>
              <td><button className="btn" onClick={() => toggleActive(u)}>{u.is_active ? 'Deactivate' : 'Reactivate'}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SettingsTab() {
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => { settingsApi.get().then(setSettings); }, []);
  if (!settings) return <p style={{ color: 'var(--text-muted)' }}>Loadingâ€¦</p>;

  async function save(e) {
    e.preventDefault();
    await settingsApi.update(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <form onSubmit={save} style={{ maxWidth: 420 }}>
      <div className="field">
        <label>Site name</label>
        <input value={settings.site_name} onChange={(e) => setSettings({ ...settings, site_name: e.target.value })} />
      </div>
      <div className="field">
        <label>Failed logins before lockout</label>
        <input type="number" value={settings.alert_lock_threshold}
               onChange={(e) => setSettings({ ...settings, alert_lock_threshold: Number(e.target.value) })} />
      </div>
      <div className="field">
        <label>Lockout duration (minutes)</label>
        <input type="number" value={settings.lock_duration_minutes}
               onChange={(e) => setSettings({ ...settings, lock_duration_minutes: Number(e.target.value) })} />
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 16 }}>
        <input type="checkbox" checked={settings.maintenance_mode}
               onChange={(e) => setSettings({ ...settings, maintenance_mode: e.target.checked })} />
        Maintenance mode
      </label>
      <button className="btn primary">Save settings</button>
      {saved && <span style={{ marginLeft: 10, color: 'var(--sev-green)', fontSize: 12.5 }}>Saved</span>}
    </form>
  );
}

function LogsTab() {
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState(null);

  useEffect(() => { logsApi.list().then(setLogs); logsApi.metrics().then(setMetrics); }, []);

  const levelColor = { INFO: 'var(--text-muted)', WARNING: 'var(--sev-orange)', ERROR: 'var(--sev-red)' };

  return (
    <div>
      {metrics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 20 }}>
          {[
            ['Uptime', `${metrics.uptime_pct}%`],
            ['Avg response', `${metrics.avg_response_ms} ms`],
            ['Active sessions', metrics.active_sessions],
            ['Database', metrics.db_status],
          ].map(([label, value]) => (
            <div key={label} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 12 }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{value}</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{label}</div>
            </div>
          ))}
        </div>
      )}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--text-muted)', borderBottom: '1px solid var(--line)' }}>
            <th style={{ padding: 8 }}>Time</th><th>Level</th><th>Message</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id} style={{ borderBottom: '1px solid var(--line)' }}>
              <td style={{ padding: 8 }}>{new Date(l.timestamp).toLocaleString()}</td>
              <td style={{ color: levelColor[l.level] }}>{l.level}</td>
              <td>{l.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
