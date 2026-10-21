import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { authApi } from '../api/authApi';
import logo from '../assets/images/logo1.png';
import './css/Login.css';

// The same words whatever happened, so the page can't be used to learn
// which emails have accounts
const GENERIC = "If an account with that email exists, we've sent a link to reset its password. It works for 1 hour.";
const LIMIT = 'Too many reset requests. Try again in a little while.';

/**
 * Forgot password: ask for a reset link by email. The backend sends a
 * one-time link that works for 1 hour (apps/accounts/password_reset.py).
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await authApi.requestPasswordReset(email.trim());
      setSent(true);
    } catch (err) {
      if (err?.status === 429) setError(LIMIT);
      else setSent(true); // any other failure: same answer, nothing about the account leaks
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lg">
      <Link to="/login" className="lg-back">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
        Back to log in
      </Link>

      <main className="lg-card">
        <div className="lg-brand">
          <span className="lg-logo"><img src={logo} alt="" /></span>
          <span className="lg-brand-name">GeoAlert</span>
        </div>

        <div className="lg-head">
          <h1>Forgot your password?</h1>
          <p>Enter your account's email and we'll send you a link to choose a new one.</p>
        </div>

        {sent ? (
          <p className="lg-done" role="status">{GENERIC}</p>
        ) : (
          <form onSubmit={handleSubmit}>
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

            {error && <p className="lg-error" role="alert">{error}</p>}

            <button type="submit" className="lg-submit" disabled={busy}>
              {busy ? 'Sending…' : 'Send reset link'}
            </button>
          </form>
        )}

        <p className="lg-note"><Link to="/login">Back to log in</Link></p>
      </main>
    </div>
  );
}
