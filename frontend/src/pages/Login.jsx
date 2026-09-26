import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import logo from '../assets/images/logo1.png';
import './css/Login.css';

export default function Login() {
  const { login, verifyLoginCode } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [code, setCode] = useState('');
  const [awaiting2fa, setAwaiting2fa] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Step 1: email + password
  async function handlePasswordSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);

    try {
      const { require2fa } = await login(email, password);

      if (require2fa) {
        setAwaiting2fa(true);
      } else {
        navigate('/app');
      }
    } catch (err) {
      setError(err.message || 'Invalid email or password');
    } finally {
      setBusy(false);
    }
  }

  // Step 2: authenticator code (only if the account has 2FA turned on)
  async function handleCodeSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);

    try {
      await verifyLoginCode(code);
      navigate('/app');
    } catch (err) {
      setError(err.message || 'Incorrect code');
    } finally {
      setBusy(false);
    }
  }

  function backToPasswordStep() {
    setAwaiting2fa(false);
    setCode('');
    setError('');
  }

  return (
    <div className="lg">
      <Link to="/" className="lg-back">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
        Back to home
      </Link>

      <main className="lg-card">
        <div className="lg-brand">
          <span className="lg-logo">
            <img src={logo} alt="" />
          </span>
          <span className="lg-brand-name">GeoAlert</span>
        </div>

        {!awaiting2fa ? (
          /* ============ STEP 1: EMAIL + PASSWORD ============ */
          <form onSubmit={handlePasswordSubmit}>
            <div className="lg-head">
              <h1>Welcome back</h1>
              <p>Log in to your GeoAlert staff account.</p>
            </div>

            <div className="lg-field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="you@example.com"
                required
              />
            </div>

            <div className="lg-field">
              <label htmlFor="password">Password</label>
              <div className="lg-password">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  className="lg-show"
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((s) => !s)}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            {error && <p className="lg-error" role="alert">{error}</p>}

            <button type="submit" className="lg-submit" disabled={busy}>
              {busy ? 'Logging in…' : 'Log in'}
            </button>

            <p className="lg-note">
              Only DRRMO staff and barangay personnel need an account.
              Residents can <Link to="/map">view the hazard map</Link> without logging in.
            </p>
          </form>
        ) : (
          /* ============ STEP 2: AUTHENTICATOR CODE ============ */
          <form onSubmit={handleCodeSubmit}>
            <div className="lg-head">
              <span className="lg-shield" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z" /><path d="M9 12l2 2 4-4" /></svg>
              </span>
              <h1>Verify it's you</h1>
              <p>Open your authenticator app and enter the 6-digit code.</p>
            </div>

            <div className="lg-field">
              <label htmlFor="code">Authenticator code</label>
              <input
                id="code"
                className="lg-code"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                autoComplete="one-time-code"
                autoFocus
                placeholder="000000"
                required
              />
            </div>

            {error && <p className="lg-error" role="alert">{error}</p>}

            <button type="submit" className="lg-submit" disabled={busy || code.length !== 6}>
              {busy ? 'Verifying…' : 'Verify code'}
            </button>

            <button type="button" className="lg-secondary" onClick={backToPasswordStep}>
              Back to login
            </button>
          </form>
        )}
      </main>

      <p className="lg-footer">GeoAlert Disaster Risk Awareness System, Talisay City</p>
    </div>
  );
}