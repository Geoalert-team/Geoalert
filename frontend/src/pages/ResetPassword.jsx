import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { authApi } from '../api/authApi';
import logo from '../assets/images/logo1.png';
import './css/Login.css';

const BAD_LINK = 'This link has expired or was already used.';
const DONE = 'Password changed. Log in with your new password.';

/**
 * Choose a new password from an emailed reset link
 * (/reset-password/:uid/:token). The link is checked first, so an expired
 * or used one says so before anything is typed. Saving does not sign the
 * person in: they log in next, 2FA included.
 *
 * As soon as the page has read the uid and token it moves them out of the
 * address into the history entry's state (/reset-password), as Django's own
 * reset view does: a reset abandoned on a shared office computer then
 * leaves no working link in the address bar or the browser history.
 */
export default function ResetPassword() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const fromUrl = params.uid && params.token ? { uid: params.uid, token: params.token } : null;
  const link = fromUrl || location.state || null; // { uid, token }
  const uid = link?.uid;
  const token = link?.token;

  // checking | invalid | error (couldn't check) | form | done
  const [stage, setStage] = useState('checking');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (fromUrl) navigate('/reset-password', { replace: true, state: fromUrl });
  }, [fromUrl?.uid, fromUrl?.token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (fromUrl) return undefined; // checked once the token has left the address
    if (!uid || !token) {
      setStage('invalid');
      return undefined;
    }
    let cancelled = false;
    setStage('checking');
    authApi.checkResetLink(uid, token)
      .then((d) => { if (!cancelled) setStage(d?.valid ? 'form' : 'invalid'); })
      .catch((err) => {
        if (cancelled) return;
        // Not a verdict on the link: offline, or too many attempts from here
        setError(err?.message || 'Something went wrong. Please try again.');
        setStage('error');
      });
    return () => { cancelled = true; };
    // Boolean(fromUrl) too: the uid and token are the same before and after
    // they leave the address, so without it the check would never run
  }, [uid, token, attempt, Boolean(fromUrl)]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirm) {
      setError("The passwords don't match.");
      return;
    }
    setBusy(true);
    setError('');
    try {
      await authApi.confirmPasswordReset(uid, token, password);
      setStage('done');
    } catch (err) {
      if (err?.message === BAD_LINK) setStage('invalid'); // expired while the form was open
      else setError(err?.message || 'Something went wrong. Please try again.');
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
          <h1>Choose a new password</h1>
          {stage === 'form' && <p>Pick a password you don't use anywhere else.</p>}
        </div>

        {stage === 'checking' && <p className="lg-note">Checking your link…</p>}

        {stage === 'error' && (
          <>
            <p className="lg-error" role="alert">{error}</p>
            <button
              type="button"
              className="lg-submit"
              onClick={() => { setError(''); setAttempt((a) => a + 1); }}>
              Try again
            </button>
          </>
        )}

        {stage === 'invalid' && (
          <>
            <p className="lg-error" role="alert">{BAD_LINK}</p>
            <Link to="/forgot-password" className="lg-submit lg-submit-link">Send a new link</Link>
          </>
        )}

        {stage === 'done' && (
          <>
            <p className="lg-done" role="status">{DONE}</p>
            <Link to="/login" className="lg-submit lg-submit-link">Log in</Link>
          </>
        )}

        {stage === 'form' && (
          <form onSubmit={handleSubmit}>
            <div className="lg-field">
              <label htmlFor="new-password">New password</label>
              <div className="lg-password">
                <input
                  id="new-password"
                  type={show ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
                <button type="button" className="lg-show" aria-pressed={show} onClick={() => setShow((s) => !s)}>
                  {show ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            <div className="lg-field">
              <label htmlFor="confirm-password">Confirm new password</label>
              <input
                id="confirm-password"
                type={show ? 'text' : 'password'}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            {error && <p className="lg-error" role="alert">{error}</p>}

            <button type="submit" className="lg-submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save new password'}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
