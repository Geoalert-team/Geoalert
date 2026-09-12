import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../api/authApi';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/Navbar';

export default function Security() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [setupData, setSetupData] = useState(null);
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function startSetup() {
    setError('');
    setBusy(true);
    try {
      const res = await authApi.setup2fa();
      setSetupData(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmSetup(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await authApi.confirm2fa(code);
      setUser({ ...user, otp_enabled: true });
      setSetupData(null);
      setCode('');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function disable(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await authApi.disable2fa(code);
      setUser({ ...user, otp_enabled: false });
      setCode('');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ padding: 24, maxWidth: 420 }}>
        <button className="btn" style={{ marginBottom: 16 }} onClick={() => navigate('/')}>â† Back</button>
        <h2>Two-factor authentication</h2>

        {user.otp_enabled ? (
          <>
            <p style={{ color: 'var(--text-muted)' }}>2FA is currently <strong style={{ color: 'var(--sev-green)' }}>enabled</strong> on your account.</p>
            <form onSubmit={disable}>
              <div className="field">
                <label>Enter a current code to turn it off</label>
                <input inputMode="numeric" maxLength={6} value={code}
                       onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} required />
              </div>
              <div className="error-text">{error}</div>
              <button className="btn" disabled={busy || code.length !== 6}>Disable 2FA</button>
            </form>
          </>
        ) : setupData ? (
          <>
            <p style={{ color: 'var(--text-muted)' }}>Scan this with Google Authenticator, Authy, or similar.</p>
            <div style={{ background: '#fff', padding: 16, display: 'inline-block', marginBottom: 12 }}>
              <QRCodeSVG value={setupData.otpauth_url} size={180} />
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Can't scan? Enter this key manually: <code>{setupData.secret}</code>
            </p>
            <form onSubmit={confirmSetup}>
              <div className="field">
                <label>Enter the 6-digit code from the app</label>
                <input inputMode="numeric" maxLength={6} value={code}
                       onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} autoFocus required />
              </div>
              <div className="error-text">{error}</div>
              <button className="btn primary" disabled={busy || code.length !== 6}>Confirm and enable</button>
            </form>
          </>
        ) : (
          <>
            <p style={{ color: 'var(--text-muted)' }}>2FA is currently <strong>off</strong>. Turn it on to require an authenticator code at every login.</p>
            <button className="btn primary" onClick={startSetup} disabled={busy}>Set up 2FA</button>
          </>
        )}
      </div>
    </div>
  );
}
