import React, { useEffect, useMemo, useState } from 'react';
import { barangaysApi } from '../../../api/barangaysApi';
import {
  BARANGAY_ROLE, Icon, Modal, ROLE_META, SUFFIXES, fieldErrors, phoneDigits, roleMeta, roleName,
} from './adminShared';

const EMPTY = {
  first_name: '', middle_initial: '', last_name: '', suffix: '',
  email: '', phone: '', employee_id: '', position: '',
  role_id: '', assigned_barangay_id: '',
};

// Accounts made before the name fields existed only have full_name;
// split it so the edit form starts filled in.
function formFromUser(user) {
  let first = user.first_name || '';
  let last = user.last_name || '';
  if (!first && !last && user.full_name) {
    const words = user.full_name.trim().split(/\s+/);
    last = words.length > 1 ? words.pop() : '';
    first = words.join(' ');
  }
  const digits = phoneDigits(user.phone);
  return {
    first_name: first,
    middle_initial: user.middle_initial || '',
    last_name: last,
    suffix: user.suffix || '',
    email: user.email || '',
    phone: digits ? `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}` : user.phone || '',
    employee_id: user.employee_id || '',
    position: user.position || '',
    role_id: user.role?.id ? String(user.role.id) : '',
    assigned_barangay_id: user.assigned_barangay?.id ? String(user.assigned_barangay.id) : '',
  };
}

function validate(form, selectedRole) {
  const errors = {};
  if (!form.first_name.trim()) errors.first_name = 'First name is required.';
  if (!form.last_name.trim()) errors.last_name = 'Last name is required.';
  if (form.middle_initial && !/^[A-Za-zÑñ]{1,2}\.?$/.test(form.middle_initial.trim())) {
    errors.middle_initial = 'One or two letters.';
  }
  if (!form.email.trim()) errors.email = 'Email is required.';
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) errors.email = 'Enter a valid email address.';
  if (!form.phone.trim()) errors.phone = 'Mobile number is required.';
  else if (!phoneDigits(form.phone)) errors.phone = 'Enter a valid PH mobile number, e.g. 917 123 4567.';
  if (!form.position.trim()) errors.position = 'Position is required.';
  if (!form.role_id) errors.role = 'Choose a role.';
  if (roleName(selectedRole) === BARANGAY_ROLE && !form.assigned_barangay_id) {
    errors.assigned_barangay = 'Choose the barangay this person works in.';
  }
  return errors;
}

function Field({ label, required, optional, error, hint, children, className = '' }) {
  return (
    <div className={`adm-field ${error ? 'has-error' : ''} ${className}`}>
      <label>
        {label}
        {required && <span className="adm-req" aria-hidden="true">*</span>}
        {optional && <span className="adm-optional">Optional</span>}
      </label>
      {children}
      {error ? <p className="adm-field-error">{error}</p> : hint ? <p className="adm-field-hint">{hint}</p> : null}
    </div>
  );
}

export default function UserFormModal({ user, roles, onClose, onSave }) {
  const editing = Boolean(user);
  const [form, setForm] = useState(() => (editing ? formFromUser(user) : EMPTY));
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [barangays, setBarangays] = useState(null);

  const selectedRole = useMemo(
    () => roles.find((r) => String(r.id) === String(form.role_id)),
    [roles, form.role_id]
  );
  const needsBarangay = roleName(selectedRole) === BARANGAY_ROLE;

  // Barangay names come from the map's GeoJSON endpoint
  useEffect(() => {
    barangaysApi
      .list()
      .then((data) => {
        const features = data?.features || data?.results?.features || [];
        const list = features
          .map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }))
          .filter((b) => b.id != null && b.name)
          .sort((a, b) => a.name.localeCompare(b.name));
        setBarangays(list);
      })
      .catch(() => setBarangays([]));
  }, []);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
    const key = field.replace(/_id$/, '');
    if (errors[key] || errors.form) setErrors((e) => ({ ...e, [key]: undefined, form: undefined }));
  }

  async function submit(e) {
    e.preventDefault();
    const found = validate(form, selectedRole);
    setErrors(found);
    if (Object.keys(found).length) return;

    const payload = {
      first_name: form.first_name.trim(),
      middle_initial: form.middle_initial.replace('.', '').trim(),
      last_name: form.last_name.trim(),
      suffix: form.suffix,
      email: form.email.trim(),
      phone: `+63${phoneDigits(form.phone)}`,
      employee_id: form.employee_id.trim(),
      position: form.position.trim(),
      role_id: Number(form.role_id),
      assigned_barangay_id: needsBarangay ? Number(form.assigned_barangay_id) : null,
    };

    setSaving(true);
    try {
      await onSave(payload);
    } catch (err) {
      setErrors(fieldErrors(err));
      setSaving(false);
    }
  }

  const err = (k) => errors[k];
  const nameOrder = ['System_Admin', 'DRRMO_Officer', 'Barangay_Personnel'];
  const sortedRoles = [...roles].sort((a, b) => nameOrder.indexOf(a.name) - nameOrder.indexOf(b.name));

  return (
    <Modal
      title={editing ? 'Edit account' : 'Add a user'}
      subtitle={
        editing
          ? `Update ${user.full_name || user.email}'s profile, contact details and access.`
          : 'Create an account for DRRMO or barangay personnel. A temporary password is generated when you save.'
      }
      onClose={saving ? () => {} : onClose}
      width={760}
      labelId="adm-user-form-title"
      footer={
        <>
          <p className="adm-foot-note">
            <Icon name="info" size={16} />
            {editing ? 'Changes are recorded in the activity log.' : 'The temporary password is shown only once.'}
          </p>
          <div className="adm-foot-actions">
            <button type="button" className="adm-btn adm-btn-ghost" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" form="adm-user-form" className="adm-btn adm-btn-primary" disabled={saving}>
              {saving ? 'Saving…' : editing ? 'Save changes' : 'Create account'}
            </button>
          </div>
        </>
      }
    >
      <form id="adm-user-form" onSubmit={submit} noValidate>
        {errors.form && (
          <div className="adm-alert" role="alert">
            <Icon name="info" size={16} />
            {errors.form}
          </div>
        )}

        <section className="adm-form-section">
          <div className="adm-form-section-head">
            <span className="adm-step">1</span>
            <div>
              <h3>Personal information</h3>
              <p>Legal name as it appears on government-issued ID.</p>
            </div>
          </div>
          <div className="adm-form-grid adm-grid-name">
            <Field label="First name" required error={err('first_name')}>
              <input
                value={form.first_name}
                onChange={(e) => set('first_name', e.target.value)}
                placeholder="Juan"
                autoComplete="off"
                autoFocus
              />
            </Field>
            <Field label="M.I." error={err('middle_initial')}>
              <input
                value={form.middle_initial}
                onChange={(e) => set('middle_initial', e.target.value.toUpperCase())}
                placeholder="D"
                maxLength={3}
                autoComplete="off"
              />
            </Field>
            <Field label="Last name" required error={err('last_name')}>
              <input
                value={form.last_name}
                onChange={(e) => set('last_name', e.target.value)}
                placeholder="Dela Cruz"
                autoComplete="off"
              />
            </Field>
            <Field label="Suffix" error={err('suffix')}>
              <select value={form.suffix} onChange={(e) => set('suffix', e.target.value)}>
                <option value="">None</option>
                {SUFFIXES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
          </div>
        </section>

        <section className="adm-form-section">
          <div className="adm-form-section-head">
            <span className="adm-step">2</span>
            <div>
              <h3>Contact details</h3>
              <p>Used to sign in and to reach this person during incidents.</p>
            </div>
          </div>
          <div className="adm-form-grid adm-grid-2">
            <Field label="Email address" required error={err('email')} hint="This is their username.">
              <div className="adm-input-icon">
                <Icon name="mail" size={16} />
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => set('email', e.target.value)}
                  placeholder="name@talisaycity.gov.ph"
                  autoComplete="off"
                />
              </div>
            </Field>
            <Field label="Mobile number" required error={err('phone')}>
              <div className="adm-input-prefix">
                <span>+63</span>
                <input
                  type="tel"
                  inputMode="tel"
                  value={form.phone}
                  onChange={(e) => set('phone', e.target.value)}
                  onBlur={() => {
                    // 0917-123-4567 / +639171234567 -> 917 123 4567 (the +63 is shown beside it)
                    const d = phoneDigits(form.phone);
                    if (d) set('phone', `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`);
                  }}
                  placeholder="917 123 4567"
                  autoComplete="off"
                />
              </div>
            </Field>
          </div>
        </section>

        <section className="adm-form-section">
          <div className="adm-form-section-head">
            <span className="adm-step">3</span>
            <div>
              <h3>Role and assignment</h3>
              <p>The role decides what this person can see and do.</p>
            </div>
          </div>

          <div className={`adm-role-picker ${err('role') ? 'has-error' : ''}`} role="radiogroup" aria-label="Role">
            {sortedRoles.length === 0 && <p className="adm-muted">Loading roles…</p>}
            {sortedRoles.map((r) => {
              const meta = ROLE_META[r.name] || roleMeta(r);
              const checked = String(form.role_id) === String(r.id);
              return (
                <label key={r.id} className={`adm-role-option adm-tone-${meta.tone} ${checked ? 'is-checked' : ''}`}>
                  <input
                    type="radio"
                    name="role"
                    value={r.id}
                    checked={checked}
                    onChange={() => set('role_id', String(r.id))}
                  />
                  <span className="adm-role-option-icon"><Icon name={meta.icon} size={18} /></span>
                  <span className="adm-role-option-text">
                    <strong>{meta.label}</strong>
                    <span>{meta.description || r.description}</span>
                  </span>
                  <span className="adm-role-option-check"><Icon name="check" size={14} strokeWidth={3} /></span>
                </label>
              );
            })}
          </div>
          {err('role') && <p className="adm-field-error">{err('role')}</p>}

          <div className="adm-form-grid adm-grid-2" style={{ marginTop: 16 }}>
            <Field label="Position / designation" required error={err('position')}>
              <input
                value={form.position}
                onChange={(e) => set('position', e.target.value)}
                placeholder={(ROLE_META[roleName(selectedRole)] || {}).positionHint || 'e.g. Barangay Secretary'}
                autoComplete="off"
              />
            </Field>
            <Field label="Employee ID" optional error={err('employee_id')}>
              <input
                value={form.employee_id}
                onChange={(e) => set('employee_id', e.target.value)}
                placeholder="e.g. TC-2026-0142"
                autoComplete="off"
              />
            </Field>
            {needsBarangay && (
              <Field
                label="Assigned barangay"
                required
                error={err('assigned_barangay')}
                hint="The barangay this person serves."
                className="adm-span-2"
              >
                <select
                  value={form.assigned_barangay_id}
                  onChange={(e) => set('assigned_barangay_id', e.target.value)}
                  disabled={barangays === null}
                >
                  <option value="">{barangays === null ? 'Loading barangays…' : 'Select a barangay'}</option>
                  {(barangays || []).map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </Field>
            )}
          </div>
        </section>
      </form>
    </Modal>
  );
}