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

  async function changePassword(e) {
    e.preventDefault();
    setPwError('');
    setPwMessage('');

    if (newPassword !== confirmPassword) {
      setPwError('New password and confirmation do not match.');
      return;
    }
    if (newPassword.length < 8) {
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
      setPwMessage('Your password has been changed.');
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
      const data = await authApi.setup2fa();
      setSetupData(data);
    } catch (err) {
      setError(err.message || 'Could not start setup');
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
      setError(err.message || 'Incorrect code');
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
      setError(err.message || 'Incorrect code');
    } finally {
      setBusy(false);
    }
  }

  const enabled = !!user?.two_factor_enabled;

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Security</h1>
          <p>Manage your password and add a second step to your login.</p>
        </div>

        {/* ============ CHANGE PASSWORD ============ */}
        <div className="db-card">
          <h2>Change password</h2>
          <p className="db-card-sub">Update the password you use to log in.</p>

          <form onSubmit={changePassword} style={{ maxWidth: 320 }}>
            <div className="field">
              <label>Current password</label>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div className="field">
              <label>New password</label>
              <input
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="At least 8 characters"
              />
            </div>
            <div className="field">
              <label>Confirm new password</label>
              <input
                type="password"
                required
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>

            {pwError && <p className="error-text">{pwError}</p>}
            {pwMessage && (
              <p style={{ color: 'var(--db-heading, #0f172a)', marginBottom: 12 }}>{pwMessage}</p>
            )}

            <button className="btn primary" disabled={pwBusy}>
              {pwBusy ? 'Saving…' : 'Change password'}
            </button>
          </form>
        </div>

        {/* ============ TWO-FACTOR AUTHENTICATION ============ */}
        {message && <p style={{ color: 'var(--db-heading, #0f172a)', marginBottom: 16 }}>{message}</p>}

        {enabled && !setupData && (
          <div className="db-card">
            <h2>Two-factor authentication is on</h2>
            <p className="db-card-sub">
              You'll be asked for a code from your authenticator app each time you log in.
            </p>
            <form onSubmit={disable2fa} style={{ maxWidth: 320 }}>
              <div className="field">
                <label>Enter a current code to turn it off</label>
                <input
                  inputMode="numeric"
                  maxLength={6}
                  required
                  value={disableCode}
                  onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="000000"
                />
              </div>
              {error && <p className="error-text">{error}</p>}
              <button className="btn" disabled={busy || disableCode.length !== 6}>
                {busy ? 'Working…' : 'Turn off two-factor authentication'}
              </button>
            </form>
          </div>
        )}

        {!enabled && !setupData && (
          <div className="db-card">
            <h2>Two-factor authentication is off</h2>
            <p className="db-card-sub">
              Turning this on means logging in needs your password and a code from an app on your phone.
            </p>
            <button className="btn primary" onClick={startSetup} disabled={busy}>
              {busy ? 'Starting…' : 'Set up two-factor authentication'}
            </button>
          </div>
        )}

        {setupData && (
          <div className="db-card">
            <h2>Scan this with your authenticator app</h2>
            <p className="db-card-sub">
              Use Google Authenticator or any similar app. Can't scan? Enter this code by hand instead:
            </p>
            <code style={{ display: 'block', margin: '8px 0 16px', fontSize: 15, wordBreak: 'break-all' }}>
              {setupData.secret}
            </code>
            <img
              src={setupData.qr_code}
              alt="Scan this QR code with your authenticator app"
              style={{ width: 200, height: 200, marginBottom: 16 }}
            />
            <form onSubmit={confirmSetup} style={{ maxWidth: 320 }}>
              <div className="field">
                <label>Enter the 6-digit code from the app</label>
                <input
                  inputMode="numeric"
                  maxLength={6}
                  required
                  autoFocus
                  value={confirmCode}
                  onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="000000"
                />
              </div>
              {error && <p className="error-text">{error}</p>}
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn primary" disabled={busy || confirmCode.length !== 6}>
                  {busy ? 'Confirming…' : 'Confirm and turn on'}
                </button>
                <button type="button" className="btn" onClick={() => setSetupData(null)} disabled={busy}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}