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
    <div className="login-page">

      {/* Left Green Section */}
      <div className="login-brand">
        <div className="brand-content">
          <div className="brand-icon">G</div>

          <h1>GeoAlert</h1>

          <p>
            Community Geospatial Hazard Guidance
            and Risk Awareness System
          </p>

          <div className="brand-line"></div>

          <span>
            Stay informed. Stay prepared. Stay safe.
          </span>
        </div>
      </div>

      {/* Right White Section */}
      <div className="login-section">
        {!awaiting2fa ? (
          <form
            onSubmit={handlePasswordSubmit}
            className="login-card"
          >
            <div className="login-header">
              <h2>Welcome back</h2>
              <p>Log in to your GeoAlert account</p>
            </div>

            <div className="login-field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="Enter your email"
                required
              />
            </div>

            <div className="login-field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="Enter your password"
                required
              />
            </div>

            {error && (
              <div className="login-error">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="login-button"
              disabled={busy}
            >
              {busy ? 'Logging in...' : 'Log in'}
            </button>

            <p className="login-footer">
              GeoAlert Disaster Risk Awareness System
            </p>
          </form>
        ) : (
          <form
            onSubmit={handleCodeSubmit}
            className="login-card"
          >
            <div className="login-header">
              <div className="security-icon">✓</div>

              <h2>Verify your account</h2>

              <p>
                Open your authenticator app and enter
                the 6-digit security code.
              </p>
            </div>

            <div className="login-field">
              <label htmlFor="code">Authenticator code</label>

              <input
                id="code"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) =>
                  setCode(e.target.value.replace(/\D/g, ''))
                }
                autoComplete="one-time-code"
                autoFocus
                placeholder="000000"
                className="code-input"
                required
              />
            </div>

            {error && (
              <div className="login-error">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="login-button"
              disabled={busy || code.length !== 6}
            >
              {busy ? 'Verifying...' : 'Verify code'}
            </button>

            <button
              type="button"
              className="back-button"
              onClick={() => {
                setAwaiting2fa(false);
                setCode('');
                setError('');
              }}
            >
              Back to login
            </button>
          </form>
        )}
      </div>

    </div>
  );
}
