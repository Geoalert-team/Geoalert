import React, { useEffect } from 'react';

/* ---------- Roles ---------- */

export const ROLE_META = {
  System_Admin: {
    label: 'System Administrator',
    short: 'System Admin',
    tone: 'admin',
    icon: 'shield',
    description: 'Full access. Manages accounts, system settings and the audit log.',
    positionHint: 'e.g. IT Officer',
  },
  DRRMO_Officer: {
    label: 'DRRMO Officer',
    short: 'DRRMO Officer',
    tone: 'drrmo',
    icon: 'alert',
    description: 'Validates incident reports, manages hazards and publishes guidance.',
    positionHint: 'e.g. Disaster Risk Reduction Officer II',
  },
  Barangay_Personnel: {
    label: 'Barangay Personnel',
    short: 'Barangay Personnel',
    tone: 'brgy',
    icon: 'building',
    description: 'Submits incident reports for the barangay they are assigned to.',
    positionHint: 'e.g. Barangay Secretary',
  },
};

export const BARANGAY_ROLE = 'Barangay_Personnel';

export function roleName(role) {
  return role?.name || role || '';
}

export function roleMeta(role) {
  const name = roleName(role);
  return ROLE_META[name] || { label: name || 'No role', short: name || 'No role', tone: 'none', icon: 'user' };
}

export const SUFFIXES = ['Jr.', 'Sr.', 'II', 'III', 'IV', 'V'];

/* ---------- Audit log actions ---------- */

export const ACTION_META = {
  CREATE_USER: { label: 'Created account', tone: 'good', icon: 'userPlus' },
  EDIT_USER: { label: 'Edited account', tone: 'info', icon: 'edit' },
  ACTIVATE_USER: { label: 'Activated account', tone: 'good', icon: 'check' },
  DEACTIVATE_USER: { label: 'Deactivated account', tone: 'bad', icon: 'userX' },
  RESET_PASSWORD: { label: 'Reset password', tone: 'warn', icon: 'key' },
};

export function actionMeta(action) {
  if (ACTION_META[action]) return ACTION_META[action];
  const text = (action || 'Activity').replace(/_/g, ' ').toLowerCase();
  return { label: text.charAt(0).toUpperCase() + text.slice(1), tone: 'neutral', icon: 'dot' };
}

/* ---------- Formatting ---------- */

export function initials(user) {
  const first = user?.first_name || '';
  const last = user?.last_name || '';
  if (first || last) return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
  const words = (user?.full_name || user?.email || '?').trim().split(/\s+/);
  return (words.length > 1 ? words[0][0] + words[words.length - 1][0] : words[0].slice(0, 2)).toUpperCase();
}

// '+639171234567' -> '+63 917 123 4567'
export function formatPhone(phone) {
  const m = /^\+63(\d{3})(\d{3})(\d{4})$/.exec(phone || '');
  return m ? `+63 ${m[1]} ${m[2]} ${m[3]}` : phone || '';
}

// Whatever was typed -> the 10 digits after +63, or null if it isn't a PH mobile number
export function phoneDigits(value) {
  let d = (value || '').replace(/\D/g, '');
  if (d.startsWith('63')) d = d.slice(2);
  else if (d.startsWith('0')) d = d.slice(1);
  return /^9\d{9}$/.test(d) ? d : null;
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return d.toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

export function timeAgo(value) {
  if (!value) return 'Never';
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`;
  return new Date(value).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' });
}

// DRF returns { field: ['message'] } or { error: 'message' }; flatten to { field: 'message' }
export function fieldErrors(err) {
  const data = err?.data;
  if (!data || typeof data !== 'object') return { form: err?.message || 'Something went wrong. Please try again.' };
  const out = {};
  Object.entries(data).forEach(([key, value]) => {
    const message = Array.isArray(value) ? value.join(' ') : String(value);
    if (key === 'error' || key === 'detail' || key === 'non_field_errors') out.form = message;
    else out[key.replace(/_id$/, '')] = message;
  });
  return out;
}

/* ---------- Icons (24px stroke icons) ---------- */

const PATHS = {
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" /></>,
  userCheck: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="m16 11 2 2 4-4" /></>,
  userPlus: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M19 8v6M22 11h-6" /></>,
  userX: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="m17 8 5 5M22 8l-5 5" /></>,
  alert: <><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></>,
  book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z" /><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" /></>,
  shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></>,
  building: <><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></>,
  key: <><circle cx="7.5" cy="15.5" r="5.5" /><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3" /></>,
  power: <><path d="M18.4 6.6a9 9 0 1 1-12.8 0" /><path d="M12 2v10" /></>,
  refresh: <><path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" /><path d="M3 12A9 9 0 0 1 18.5 5.7L21 8" /><path d="M21 3v5h-5M3 21v-5h5" /></>,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  check: <path d="M20 6 9 17l-5-5" />,
  copy: <><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>,
  info: <><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></>,
  mail: <><rect x="2" y="4" width="20" height="16" rx="2" /><path d="m22 7-10 6L2 7" /></>,
  phone: <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z" />,
  chevronLeft: <path d="m15 18-6-6 6-6" />,
  chevronRight: <path d="m9 18 6-6-6-6" />,
  arrowRight: <path d="M5 12h14M13 5l7 7-7 7" />,
  clock: <><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></>,
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  dot: <circle cx="12" cy="12" r="3" />,
};

export function Icon({ name, size = 18, className = '', strokeWidth = 2 }) {
  return (
    <svg
      className={`adm-icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name] || PATHS.dot}
    </svg>
  );
}

/* ---------- Small building blocks ---------- */

export function RoleBadge({ role }) {
  const meta = roleMeta(role);
  return <span className={`adm-role adm-tone-${meta.tone}`}>{meta.short}</span>;
}

export function StatusBadge({ active }) {
  return (
    <span className={`adm-status ${active ? 'is-active' : 'is-inactive'}`}>
      <span className="adm-status-dot" />
      {active ? 'Active' : 'Inactive'}
    </span>
  );
}

export function Avatar({ user, size = 'md' }) {
  return (
    <span className={`adm-avatar adm-avatar-${size} adm-tone-${roleMeta(user?.role).tone}`} aria-hidden="true">
      {initials(user)}
    </span>
  );
}

// Modal shell: Escape closes, the page behind doesn't scroll, clicks on the backdrop close.
export function Modal({ title, subtitle, onClose, children, footer, width = 640, labelId }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose();
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const id = labelId || 'adm-modal-title';
  return (
    <div className="adm-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="adm-modal" role="dialog" aria-modal="true" aria-labelledby={id} style={{ maxWidth: width }}>
        <div className="adm-modal-head">
          <div>
            <h2 id={id}>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button type="button" className="adm-icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
        <div className="adm-modal-body">{children}</div>
        {footer && <div className="adm-modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ title, message, confirmLabel, danger, busy, onConfirm, onCancel }) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      width={440}
      labelId="adm-confirm-title"
      footer={
        <>
          <button type="button" className="adm-btn adm-btn-ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={`adm-btn ${danger ? 'adm-btn-danger' : 'adm-btn-primary'}`}
            onClick={onConfirm}
            disabled={busy}
            autoFocus
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <p className="adm-confirm-text">{message}</p>
    </Modal>
  );
}

export function Toast({ toast, onDone }) {
  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(onDone, 3500);
    return () => clearTimeout(t);
  }, [toast, onDone]);
  if (!toast) return null;
  return (
    <div className={`adm-toast ${toast.tone === 'bad' ? 'is-bad' : ''}`} role="status">
      <Icon name={toast.tone === 'bad' ? 'info' : 'check'} />
      {toast.message}
    </div>
  );
}