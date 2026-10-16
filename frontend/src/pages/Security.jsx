import React, { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { useAuth } from '../context/AuthContext';
import { authApi } from '../api/authApi';
import {
  Avatar, Icon, RoleBadge, Toast, formatDateTime, formatPhone, roleMeta, roleName, timeAgo,
} from './Dashboard/admin/adminShared';
import './css/Dashboard.css';
import './css/AdminDashboard.css';
import './css/Security.css';

function EyeIcon({ off }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {off ? (
        <>
          <path d="M9.9 4.2A10.4 10.4 0 0 1 12 4c6.5 0 10 8 10 8a17.6 17.6 0 0 1-3.2 4.2M6.6 6.6C3.7 8.4 2 12 2 12s3.5 8 10 8a9.7 9.7 0 0 0 5.4-1.6" />
          <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M2 2l20 20" />
        </>
      ) : (
        <>
          <path d="M2 12s3.5-8 10-8 10 8 10 8-3.5 8-10 8S2 12 2 12z" />
          <circle cx="12" cy="12" r="3" />
        </>
      )}
    </svg>
  );
}

function PasswordInput({ id, value, onChange, autoComplete, placeholder }) {
  const [shown, setShown] = useState(false);
  return (
    <div className="sec-pw">
      <input
        id={id}
        type={shown ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
      />
      <button type="button" onClick={() => setShown((s) => !s)} aria-label={shown ? 'Hide password' : 'Show password'} title={shown ? 'Hide' : 'Show'}>
        <EyeIcon off={shown} />
      </button>
    </div>
  );
}

// 0-4, from length and variety of characters
function strength(pw) {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score += 1;
  if (pw.length >= 12) score += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 1;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score += 1;
  return pw.length < 8 ? Math.min(score, 1) : score;
}
const STRENGTH = [
  { label: '', tone: '' },
  { label: 'Weak', tone: 'bad' },
  { label: 'Fair', tone: 'warn' },
  { label: 'Good', tone: 'good' },
  { label: 'Strong', tone: 'good' },
];

function Requirement({ met, children }) {
  return (
    <li className={met ? 'is-met' : ''}>
      <span className="sec-req-dot">{met && <Icon name="check" size={11} strokeWidth={3.5} />}</span>
      {children}
    </li>
  );
}

function CodeInput({ id, value, onChange, autoFocus }) {
  return (
    <input
      id={id}
      className="sec-code-input"
      inputMode="numeric"
      autoComplete="one-time-code"
      maxLength={6}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
      placeholder="000000"
      autoFocus={autoFocus}
    />
  );
}

function ProfileCard({ user }) {
  const meta = roleMeta(user?.role);
  const isAdmin = roleName(user?.role) === 'System_Admin';
  const rows = [
    { icon: 'mail', label: 'Email', value: user?.email },
    { icon: 'phone', label: 'Mobile', value: user?.phone ? formatPhone(user.phone) : null },
    { icon: 'user', label: 'Position', value: user?.position },
    { icon: 'key', label: 'Employee ID', value: user?.employee_id },
    { icon: 'building', label: 'Assigned barangay', value: user?.assigned_barangay?.name },
    { icon: 'clock', label: 'Member since', value: user?.created_at ? formatDateTime(user.created_at).replace(/,\s*\d+:\d+.*$/, '') : null },
  ].filter((r) => r.value);

  return (
    <aside className="adm-card sec-profile">
      <div className="sec-profile-top">
        <Avatar user={user} />
        <div className="sec-profile-name">
          <h2>{user?.full_name || 'Your account'}</h2>
          <RoleBadge role={user?.role} />
        </div>
      </div>
      <p className="sec-profile-role">{meta.description}</p>
      <dl className="sec-profile-list">
        {rows.map((r) => (
          <div key={r.label}>
            <dt><Icon name={r.icon} size={15} />{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      <p className="sec-profile-note">
        <Icon name="info" size={15} />
        {isAdmin ? (
          <span>Edit your profile details from <Link to="/app/dashboard">Dashboard → Users</Link>.</span>
        ) : (
          <span>To change these details, ask your system administrator.</span>
        )}
      </p>
    </aside>
  );
}

export default function Security() {
  const { user, setUser } = useAuth();
  const [toast, setToast] = useState(null);
  const clearToast = useCallback(() => setToast(null), []);
  const notify = (message) => setToast({ id: Date.now(), tone: 'good', message });

  // ---- Change password ----
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState('');

  // ---- 2FA ----
  const [setupData, setSetupData] = useState(null); // { secret, qr_code }
  const [confirmCode, setConfirmCode] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [showDisable, setShowDisable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const score = strength(newPassword);
  const checks = {
    length: newPassword.length >= 8,
    mixed: /[A-Za-z]/.test(newPassword) && /\d/.test(newPassword),
    different: newPassword.length > 0 && newPassword !== currentPassword,
    match: confirmPassword.length > 0 && newPassword === confirmPassword,
  };

  async function changePassword(e) {
    e.preventDefault();
    setPwError('');
    if (!currentPassword) return setPwError('Enter your current password.');
    if (!checks.length) return setPwError('Your new password must be at least 8 characters long.');
    if (!checks.different) return setPwError('Choose a password different from your current one.');
    if (!checks.match) return setPwError('The new passwords do not match.');

    setPwBusy(true);
    try {
      await authApi.changePassword({ current_password: currentPassword, new_password: newPassword });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      notify('Your password has been changed.');
    } catch (err) {
      setPwError(err.message || 'Could not change your password.');
    } finally {
      setPwBusy(false);
    }
  }

  async function startSetup() {
    setError('');
    setBusy(true);
    try {
      setSetupData(await authApi.setup2fa());
      setConfirmCode('');
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
      notify('Two-factor authentication is now on.');
    } catch (err) {
      setError(err.message === 'Incorrect code' ? 'That code didn\'t match. Check the app and try the newest code.' : err.message || 'Incorrect code.');
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
      setShowDisable(false);
      notify('Two-factor authentication is now off.');
    } catch (err) {
      setError(err.message === 'Incorrect code' ? 'That code didn\'t match. Check the app and try the newest code.' : err.message || 'Incorrect code.');
    } finally {
      setBusy(false);
    }
  }

  function copySecret() {
    navigator.clipboard.writeText(setupData.secret).then(() => setCopied(true)).catch(() => {});
  }

  const enabled = !!user?.two_factor_enabled;

  return (
    <div className="db adm sec">
      <PublicNavbar />
      <div className="adm-wrap">
        <header className="adm-header">
          <div>
            <p className="adm-eyebrow">Your account</p>
            <h1>Account and security</h1>
            <p className="adm-lede">Review your profile, change your password and protect your login with a second step.</p>
          </div>
          <div className="adm-header-side">
            <span className={`adm-system ${enabled ? 'is-ok' : 'is-down'}`}>
              <span className="adm-system-dot" />
              Two-factor {enabled ? 'on' : 'off'}
            </span>
            {user?.last_login && (
              <span className="sec-last" title={formatDateTime(user.last_login)}>
                <Icon name="clock" size={15} /> Signed in {timeAgo(user.last_login).toLowerCase()}
              </span>
            )}
          </div>
        </header>

        <div className="sec-grid">
          <ProfileCard user={user} />

          <div className="sec-main">
            {/* ============ CHANGE PASSWORD ============ */}
            <section className="adm-card">
              <div className="sec-card-head">
                <span className="sec-card-icon"><Icon name="key" size={20} /></span>
                <div>
                  <h2>Change password</h2>
                  <p>Use a password you don't use on any other site.</p>
                </div>
              </div>

              <form onSubmit={changePassword} className="sec-pw-form" noValidate>
                <div className="sec-pw-fields">
                  <div className="adm-field">
                    <label htmlFor="sec-current">Current password</label>
                    <PasswordInput id="sec-current" value={currentPassword} onChange={(v) => { setCurrentPassword(v); setPwError(''); }} autoComplete="current-password" />
                  </div>
                  <div className="adm-field">
                    <label htmlFor="sec-new">New password</label>
                    <PasswordInput id="sec-new" value={newPassword} onChange={(v) => { setNewPassword(v); setPwError(''); }} autoComplete="new-password" placeholder="At least 8 characters" />
                    <div className="sec-meter" aria-live="polite">
                      <div className="sec-meter-bars">
                        {[1, 2, 3, 4].map((i) => (
                          <span key={i} className={i <= score ? `is-on is-${STRENGTH[score].tone}` : ''} />
                        ))}
                      </div>
                      <span className={`sec-meter-label is-${STRENGTH[score].tone}`}>{STRENGTH[score].label}</span>
                    </div>
                  </div>
                  <div className="adm-field">
                    <label htmlFor="sec-confirm">Confirm new password</label>
                    <PasswordInput id="sec-confirm" value={confirmPassword} onChange={(v) => { setConfirmPassword(v); setPwError(''); }} autoComplete="new-password" />
                  </div>
                </div>

                <div className="sec-reqs">
                  <p>Your new password needs:</p>
                  <ul>
                    <Requirement met={checks.length}>At least 8 characters</Requirement>
                    <Requirement met={checks.mixed}>Letters and numbers (recommended)</Requirement>
                    <Requirement met={checks.different}>To be different from your current one</Requirement>
                    <Requirement met={checks.match}>To match in both boxes</Requirement>
                  </ul>
                </div>

                {pwError && <div className="adm-alert sec-full" role="alert"><Icon name="info" size={16} />{pwError}</div>}

                <div className="sec-actions sec-full">
                  <button type="submit" className="adm-btn adm-btn-primary" disabled={pwBusy}>
                    {pwBusy ? 'Saving…' : 'Update password'}
                  </button>
                </div>
              </form>
            </section>

            {/* ============ TWO-FACTOR AUTHENTICATION ============ */}
            <section className="adm-card">
              <div className="sec-card-head">
                <span className={`sec-card-icon ${enabled ? 'is-good' : ''}`}><Icon name="shield" size={20} /></span>
                <div>
                  <h2>Two-factor authentication</h2>
                  <p>Sign in with your password plus a 6-digit code from an app on your phone.</p>
                </div>
                <span className={`adm-action ${enabled ? 'adm-action-good' : 'adm-action-neutral'} sec-badge`}>
                  {enabled ? 'On' : 'Off'}
                </span>
              </div>

              {!enabled && !setupData && (
                <div className="sec-2fa-off">
                  <ul className="sec-benefits">
                    <li><Icon name="check" size={15} strokeWidth={3} />Stops someone who learns your password from signing in</li>
                    <li><Icon name="check" size={15} strokeWidth={3} />Works with Google Authenticator, Microsoft Authenticator or similar apps</li>
                    <li><Icon name="check" size={15} strokeWidth={3} />Takes about two minutes to set up</li>
                  </ul>
                  {error && <div className="adm-alert" role="alert"><Icon name="info" size={16} />{error}</div>}
                  <div className="sec-actions">
                    <button type="button" className="adm-btn adm-btn-primary" onClick={startSetup} disabled={busy}>
                      <Icon name="shield" size={16} />
                      {busy ? 'Starting…' : 'Set up two-factor authentication'}
                    </button>
                  </div>
                </div>
              )}

              {setupData && (
                <form onSubmit={confirmSetup} className="sec-setup">
                  <ol className="sec-steps">
                    <li>
                      <span className="adm-step">1</span>
                      <div>
                        <strong>Install an authenticator app</strong>
                        <p>Google Authenticator or Microsoft Authenticator, from your phone's app store.</p>
                      </div>
                    </li>
                    <li>
                      <span className="adm-step">2</span>
                      <div className="sec-step-wide">
                        <strong>Scan this QR code with the app</strong>
                        <div className="sec-qr-row">
                          <img src={setupData.qr_code} alt="QR code for your authenticator app" className="sec-qr" />
                          <div className="sec-secret">
                            <p>Can't scan it? Type this key into the app instead:</p>
                            <code>{setupData.secret}</code>
                            <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" onClick={copySecret}>
                              <Icon name={copied ? 'check' : 'copy'} size={15} />{copied ? 'Copied' : 'Copy key'}
                            </button>
                          </div>
                        </div>
                      </div>
                    </li>
                    <li>
                      <span className="adm-step">3</span>
                      <div>
                        <label htmlFor="sec-confirm-code"><strong>Enter the 6-digit code the app shows</strong></label>
                        <CodeInput id="sec-confirm-code" value={confirmCode} onChange={(v) => { setConfirmCode(v); setError(''); }} autoFocus />
                      </div>
                    </li>
                  </ol>
                  {error && <div className="adm-alert" role="alert"><Icon name="info" size={16} />{error}</div>}
                  <div className="sec-actions">
                    <button type="button" className="adm-btn adm-btn-ghost" onClick={() => { setSetupData(null); setError(''); }} disabled={busy}>Cancel</button>
                    <button type="submit" className="adm-btn adm-btn-primary" disabled={busy || confirmCode.length !== 6}>
                      {busy ? 'Confirming…' : 'Confirm and turn on'}
                    </button>
                  </div>
                </form>
              )}

              {enabled && !setupData && (
                <div className="sec-2fa-on">
                  <div className="sec-on-banner">
                    <Icon name="shield" size={18} />
                    <span>Your account is protected. You'll be asked for a code from your authenticator app each time you sign in.</span>
                  </div>
                  {!showDisable ? (
                    <div className="sec-actions">
                      <button type="button" className="adm-btn adm-btn-ghost sec-danger-link" onClick={() => setShowDisable(true)}>
                        Turn off two-factor authentication
                      </button>
                    </div>
                  ) : (
                    <form onSubmit={disable2fa} className="sec-disable">
                      <label htmlFor="sec-disable-code">Enter a current code from your app to turn it off</label>
                      <CodeInput id="sec-disable-code" value={disableCode} onChange={(v) => { setDisableCode(v); setError(''); }} autoFocus />
                      {error && <div className="adm-alert" role="alert"><Icon name="info" size={16} />{error}</div>}
                      <div className="sec-actions">
                        <button type="button" className="adm-btn adm-btn-ghost" onClick={() => { setShowDisable(false); setDisableCode(''); setError(''); }} disabled={busy}>Cancel</button>
                        <button type="submit" className="adm-btn adm-btn-danger" disabled={busy || disableCode.length !== 6}>
                          {busy ? 'Working…' : 'Turn off'}
                        </button>
                      </div>
                    </form>
                  )}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
      <Toast key={toast?.id} toast={toast} onDone={clearToast} />
    </div>
  );
}