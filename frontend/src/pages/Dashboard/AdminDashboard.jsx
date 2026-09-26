import React, { useEffect, useState } from 'react';
import { adminApi } from '../../api/adminApi';
import Navbar from '../../components/Navbar';

const TABS = ['Users', 'Logs & Performance'];
const ROLE_OPTIONS = [
  { id: 1, name: 'System_Admin' },
  { id: 2, name: 'DRRMO_Officer' },
  { id: 3, name: 'Barangay_Personnel' },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState('Users');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 880, margin: '0 auto', width: '100%' }}>
        <h2 style={{ marginBottom: 4 }}>Admin dashboard</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 16 }}>
          Manage GeoAlert user accounts and review system activity.
        </p>
        <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
          {TABS.map((t) => (
            <button key={t} className="btn" style={{ borderColor: tab === t ? 'var(--accent)' : 'var(--line)', color: tab === t ? 'var(--accent)' : 'var(--text)' }}
                    onClick={() => setTab(t)}>{t}</button>
          ))}
        </div>
        {tab === 'Users' && <UsersTab />}
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
  const [roleId, setRoleId] = useState(ROLE_OPTIONS[2].id);
  const [tempPassword, setTempPassword] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { refresh(); }, []);
  async function refresh() {
    try {
      setUsers(await adminApi.users.list());
    } catch {
      setUsers([]);
    }
  }

  async function createUser(e) {
    e.preventDefault();
    setError('');
    try {
      const res = await adminApi.users.create({ full_name: fullName, email, role_id: roleId });
      setTempPassword(res.temporary_password);
      setFullName(''); setEmail(''); setShowForm(false);
      refresh();
    } catch (err) {
      setError(err.message || 'Could not create user');
    }
  }

  async function toggleActive(u) {
    if (u.is_active) {
      await adminApi.users.deactivate(u.id);
    } else {
      await adminApi.users.update(u.id, { is_active: true });
    }
    refresh();
  }

  async function resetPassword(u) {
    const res = await adminApi.users.resetPassword(u.id);
    setTempPassword(res.temporary_password);
  }

  return (
    <div>
      {tempPassword && (
        <div style={{ border: '1px solid var(--sev-green)', background: 'var(--panel)', padding: 12, marginBottom: 16, fontSize: 13 }}>
          Temporary password: <strong>{tempPassword}</strong>
          <button className="btn" style={{ marginLeft: 12 }} onClick={() => setTempPassword(null)}>Dismiss</button>
        </div>
      )}
      {error && <div style={{ color: 'var(--sev-red)', fontSize: 13, marginBottom: 12 }}>{error}</div>}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn primary" onClick={() => setShowForm((s) => !s)}>{showForm ? 'Cancel' : 'Add user'}</button>
      </div>
      {showForm && (
        <form onSubmit={createUser} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 16, marginBottom: 16 }}>
          <div className="field"><label>Full name</label><input value={fullName} onChange={(e) => setFullName(e.target.value)} required /></div>
          <div className="field"><label>Email</label><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
          <div className="field">
            <label>Role</label>
            <select value={roleId} onChange={(e) => setRoleId(Number(e.target.value))}>
              {ROLE_OPTIONS.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
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
              <td>{u.role?.name}</td>
              <td style={{ color: u.is_active ? 'var(--sev-green)' : 'var(--sev-red)' }}>{u.is_active ? 'Active' : 'Deactivated'}</td>
              <td style={{ display: 'flex', gap: 6 }}>
                <button className="btn" onClick={() => toggleActive(u)}>{u.is_active ? 'Deactivate' : 'Reactivate'}</button>
                <button className="btn" onClick={() => resetPassword(u)}>Reset password</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LogsTab() {
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    adminApi.logs().then((res) => setLogs(res.results || [])).catch(() => setLogs([]));
    adminApi.metrics().then(setMetrics).catch(() => setMetrics(null));
  }, []);

  return (
    <div>
      {metrics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 20 }}>
          {[
            ['Total users', metrics.total_users],
            ['Active users', metrics.active_users],
            ['Active hazards', metrics.active_hazards],
            ['Published guidance', metrics.published_guidance],
            ['System status', metrics.system_status],
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
            <th style={{ padding: 8 }}>Time</th><th>User</th><th>Action</th><th>Details</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id} style={{ borderBottom: '1px solid var(--line)' }}>
              <td style={{ padding: 8 }}>{new Date(l.created_at).toLocaleString()}</td>
              <td>{l.user_name}</td>
              <td>{l.action}</td>
              <td>{l.details}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}