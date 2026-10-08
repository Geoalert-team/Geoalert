import React, { useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { useAuth } from '../context/AuthContext';
import { authApi } from '../api/authApi';
import './css/Dashboard.css';

export default function Security() {
  const { user, setUser } = useAuth();

  // ---- Change password ----
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPasswords, setShowPasswords] = useState(false);
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState('');
  const [pwMessage, setPwMessage] = useState('');

  // ---- 2FA ----
  const [setupData, setSetupData] = useState(null); // { secret, qr_code }
  const [confirmCode, setConfirmCode] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const longEnough = newPassword.length >= 8;
  const matches = newPassword.length > 0 && newPassword === confirmPassword;
  const differs = newPassword.length > 0 && newPassword !== currentPassword;
  const canSubmitPassword = currentPassword && longEnough && matches && differs;

  async function changePassword(e) {
    e.preventDefault();
    setPwError('');
    setPwMessage('');

    if (!matches) {
      setPwError('New password and confirmation do not match.');
      return;
    }
    if (!longEnough) {
      setPwError('New password must be at least 8 characters long.');
      return;
    }

    setPwBusy(true);
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setShowPasswords(false);
      setPwMessage('Your password has been changed. You stayed logged in.');
    } catch (err) {
      setPwError(err.message || 'Could not change your password.');
    } finally {
      setPwBusy(false);
    }
  }

  async function startSetup() {
    setError('');
    setMessage('');
    setBusy(true);
    try {
      setSetupData(await authApi.setup2fa());
    } catch (err) {
      setError(err.message || 'Could not start setup.');
    } finally {
      setBusy(false);
    }
  }

  async function confirmSetup(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const data = await authApi.confirm2fa(confirmCode);
      setUser(data.user);
      setSetupData(null);
      setConfirmCode('');
      setMessage('Two-factor authentication is now on.');
    } catch (err) {
      setError(err.message || 'That code was not accepted. Try the next one your app shows.');
    } finally {
      setBusy(false);
    }
  }

  async function disable2fa(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const data = await authApi.disable2fa(disableCode);
      setUser(data.user);
      setDisableCode('');
      setMessage('Two-factor authentication is now off.');
    } catch (err) {
      setError(err.message || 'That code was not accepted. Try the next one your app shows.');
    } finally {
      setBusy(false);
    }
  }

  const enabled = !!user?.two_factor_enabled;
  const onlyDigits = (v) => v.replace(/\D/g, '').slice(0, 6);

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Security</h1>
          <p>Manage your password and add a second step to your login.</p>
        </div>

        <div className="db-grid-2">
          {/* ============ CHANGE PASSWORD ============ */}
          <div className="db-card">
            <h2>Change password</h2>
            <p className="db-card-sub">Update the password you use to log in.</p>

            <form onSubmit={changePassword}>
              <label className="db-field" htmlFor="sec-current">
                Current password
                <input
                  id="sec-current"
                  type={showPasswords ? 'text' : 'password'}
                  required
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </label>

              <label className="db-field" htmlFor="sec-new" style={{ marginTop: 12 }}>
                New password
                <input
                  id="sec-new"
                  type={showPasswords ? 'text' : 'password'}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </label>

              <label className="db-field" htmlFor="sec-confirm" style={{ marginTop: 12 }}>
                Confirm new password
                <input
                  id="sec-confirm"
                  type={showPasswords ? 'text' : 'password'}
                  required
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </label>

              <div style={{ margin: '10px 0 12px' }}>
                <button
                  type="button"
                  className="db-link-btn"
                  onClick={() => setShowPasswords((s) => !s)}
                >
                  {showPasswords ? 'Hide passwords' : 'Show passwords'}
                </button>
              </div>

              <ul className="db-reqs">
                <li className={longEnough ? 'is-met' : ''}>At least 8 characters</li>
                <li className={matches ? 'is-met' : ''}>Both new password fields match</li>
                <li className={differs ? 'is-met' : ''}>Different from your current password</li>
              </ul>

              {pwError && <p className="db-error" role="alert">{pwError}</p>}
              {pwMessage && <p className="db-success" role="status">{pwMessage}</p>}

              <button className="db-btn db-btn-primary" disabled={pwBusy || !canSubmitPassword}>
                {pwBusy ? 'Saving…' : 'Change password'}
              </button>
            </form>
          </div>

          {/* ============ TWO-FACTOR AUTHENTICATION ============ */}
          <div className="db-card">
            <div className="db-item-head" style={{ marginBottom: 4 }}>
              <h2>Two-factor authentication</h2>
              <span className={`db-badge ${enabled ? 'db-badge-low' : 'db-badge-inactive-status'}`}>
                {enabled ? 'On' : 'Off'}
              </span>
            </div>

            {message && <p className="db-success" role="status">{message}</p>}

            {/* --- Already on: offer to turn it off --- */}
            {enabled && !setupData && (
              <>
                <p className="db-card-sub">
                  Each login asks for a code from your authenticator app as well as your password.
                </p>
                <form onSubmit={disable2fa}>
                  <label className="db-field db-otp" htmlFor="sec-disable">
                    Enter a current code to turn it off
                    <input
                      id="sec-disable"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      required
                      value={disableCode}
                      onChange={(e) => setDisableCode(onlyDigits(e.target.value))}
                      placeholder="000000"
                    />
                  </label>
                  <p className="db-hint" style={{ marginTop: 8 }}>
                    Confirming with a live code proves the app is still in your hands.
                  </p>
                  {error && <p className="db-error" role="alert">{error}</p>}
                  <button
                    className="db-btn db-btn-danger"
                    disabled={busy || disableCode.length !== 6}
                  >
                    {busy ? 'Working…' : 'Turn off two-factor authentication'}
                  </button>
                </form>
              </>
            )}

            {/* --- Off: offer to set it up --- */}
            {!enabled && !setupData && (
              <>
                <p className="db-card-sub">
                  With this on, logging in needs your password plus a six-digit code from an app on
                  your phone. If someone learns your password, it is still not enough to get in.
                </p>
                <p className="db-callout">
                  You'll need an authenticator app first — Google Authenticator, Microsoft
                  Authenticator or Authy all work.
                </p>
                {error && <p className="db-error" role="alert">{error}</p>}
                <button className="db-btn db-btn-primary" onClick={startSetup} disabled={busy}>
                  {busy ? 'Starting…' : 'Set up two-factor authentication'}
                </button>
              </>
            )}

            {/* --- Mid-setup: scan and confirm --- */}
            {setupData && (
              <>
                <p className="db-card-sub">
                  Scan this with your authenticator app, then type the code it shows.
                </p>

                <div className="db-qr">
                  <img src={setupData.qr_code} alt="QR code for your authenticator app" />
                </div>

                <details style={{ marginBottom: 14 }}>
                  <summary className="db-link-btn" style={{ textDecoration: 'none' }}>
                    Can't scan it? Enter the key by hand
                  </summary>
                  <div className="db-code" style={{ marginTop: 8 }}>{setupData.secret}</div>
                </details>

                <form onSubmit={confirmSetup}>
                  <label className="db-field db-otp" htmlFor="sec-confirm-code">
                    Six-digit code from the app
                    <input
                      id="sec-confirm-code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      required
                      autoFocus
                      value={confirmCode}
                      onChange={(e) => setConfirmCode(onlyDigits(e.target.value))}
                      placeholder="000000"
                    />
                  </label>
                  <p className="db-hint" style={{ marginTop: 8 }}>
                    Codes change every 30 seconds. If one is rejected, wait for the next.
                  </p>
                  {error && <p className="db-error" role="alert">{error}</p>}
                  <div className="db-btn-row">
                    <button
                      className="db-btn db-btn-primary"
                      disabled={busy || confirmCode.length !== 6}
                    >
                      {busy ? 'Confirming…' : 'Confirm and turn on'}
                    </button>
                    <button
                      type="button"
                      className="db-btn db-btn-outline"
                      onClick={() => { setSetupData(null); setError(''); }}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}