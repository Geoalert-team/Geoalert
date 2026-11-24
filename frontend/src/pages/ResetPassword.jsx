import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { authApi } from '../api/authApi';
import logo from '../assets/images/logo1.png';
import './css/Login.css';

// The two emailed links this page serves. The bad-link and done texts match
// the server's replies (apps/accounts/password_reset.py, invite.py).
const MODES = {
  reset: {
    path: '/reset-password',
    title: 'Choose a new password',
    lead: "Pick a password you don't use anywhere else.",
    badLink: 'This link has expired or was already used.',
    done: 'Password changed. Log in with your new password.',
    submit: 'Save new password',
    check: (uid, token) => authApi.checkResetLink(uid, token),
    save: (uid, token, password) => authApi.confirmPasswordReset(uid, token, password),
  },
  invite: {
    path: '/set-password',
    title: 'Set up your account',
    lead: "Choose the password you'll use to sign in to GeoAlert Talisay. Pick one you don't use anywhere else.",
    badLink: 'This invite link has expired or was already used.',
    badHelp: "Already set your password? Log in. If not, ask your system administrator to send you a new invite.",
    done: 'Your password is set. Log in with your email and new password.',
    submit: 'Set password',
    check: (uid, token) => authApi.checkInvite(uid, token),
    save: (uid, token, password) => authApi.acceptInvite(uid, token, password),
  },
};

/**
 * Choose a password from an emailed link: a reset link
 * (/reset-password/:uid/:token) or, with `invite`, a new account's invite
 * (/set-password/:uid/:token), where the owner picks their first password.
 * The link is checked first, so an expired or used one says so before
 * anything is typed. Saving does not sign the person in: they log in next,
 * 2FA included.
 *
 * As soon as the page has read the uid and token it moves them out of the
 * address into the history entry's state (/reset-password or /set-password),
 * as Django's own reset view does: a reset abandoned on a shared office computer then
 * leaves no working link in the address bar or the browser history.
 */
export default function ResetPassword({ invite = false }) {
  const mode = invite ? MODES.invite : MODES.reset;
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
    if (fromUrl) navigate(mode.path, { replace: true, state: fromUrl });
  }, [fromUrl?.uid, fromUrl?.token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (fromUrl) return undefined; // checked once the token has left the address
    if (!uid || !token) {
      setStage('invalid');
      return undefined;
    }
    let cancelled = false;
    setStage('checking');
    mode.check(uid, token)
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
      await mode.save(uid, token, password);
      setStage('done');
    } catch (err) {
      if (err?.message === mode.badLink) setStage('invalid'); // expired while the form was open
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
          <span className="lg-brand-name">GeoAlert Talisay</span>
        </div>

        <div className="lg-head">
          <h1>{mode.title}</h1>
          {stage === 'form' && <p>{mode.lead}</p>}
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
            <p className="lg-error" role="alert">{mode.badLink}</p>
            {invite ? (
              <>
                <p className="lg-note">{mode.badHelp}</p>
                <Link to="/login" className="lg-submit lg-submit-link">Go to log in</Link>
              </>
            ) : (
              <Link to="/forgot-password" className="lg-submit lg-submit-link">Send a new link</Link>
            )}
          </>
        )}

        {stage === 'done' && (
          <>
            <p className="lg-done" role="status">{mode.done}</p>
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
              {busy ? 'Saving…' : mode.submit}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
