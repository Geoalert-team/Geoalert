import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../api/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setError(err.message || 'Invalid email or password');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <form onSubmit={handleSubmit} style={{ width: 360, border: '1px solid var(--line)', background: 'var(--panel)', padding: 26 }}>
        <h2 style={{ margin: '0 0 4px' }}>Log in</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: '0 0 20px' }}>
          POST /api/auth/login/
        </p>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 autoComplete="username" required />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" required />
        </div>
        <div className="error-text">{error}</div>
        <button className="btn primary" style={{ width: '100%' }} disabled={busy}>
          {busy ? 'Logging inâ€¦' : 'Log in'}
        </button>
      </form>
    </div>
  );
}
