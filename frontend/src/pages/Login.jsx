import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { login, verifyLoginCode } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [awaiting2fa, setAwaiting2fa] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handlePasswordSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const { require2fa } = await login(email, password);
      if (require2fa) {
        setAwaiting2fa(true);
      } else {
        navigate('/');
      }
    } catch (err) {
      setError(err.message || 'Invalid email or password');
    } finally {
      setBusy(false);
    }
  }

  async function handleCodeSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await verifyLoginCode(code);
      navigate('/');
    } catch (err) {
      setError(err.message || 'Incorrect code');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      {!awaiting2fa ? (
        <form onSubmit={handlePasswordSubmit} style={{ width: 360, border: '1px solid var(--line)', background: 'var(--panel)', padding: 26 }}>
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
      ) : (
        <form onSubmit={handleCodeSubmit} style={{ width: 360, border: '1px solid var(--line)', background: 'var(--panel)', padding: 26 }}>
          <h2 style={{ margin: '0 0 4px' }}>Enter your code</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: '0 0 20px' }}>
            Open your authenticator app and enter the 6-digit code for this account.
          </p>
          <div className="field">
            <label htmlFor="code">Authenticator code</label>
            <input id="code" inputMode="numeric" maxLength={6} value={code}
                   onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                   autoComplete="one-time-code" autoFocus required />
          </div>
          <div className="error-text">{error}</div>
          <button className="btn primary" style={{ width: '100%' }} disabled={busy || code.length !== 6}>
            {busy ? 'Verifyingâ€¦' : 'Verify'}
          </button>
        </form>
      )}
    </div>
  );
}
