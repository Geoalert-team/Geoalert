import React, { useEffect, useMemo, useState } from 'react';
import { adminApi } from '../../../api/adminApi';
import UserFormModal from './UserFormModal';
import {
  Avatar, ConfirmDialog, Icon, Modal, ROLE_META, RoleBadge, StatusBadge,
  fieldErrors, formatPhone, roleName, timeAgo,
} from './adminShared';

const PAGE_SIZE = 10;

function CredentialsDialog({ info, onClose }) {
  const [copied, setCopied] = useState('');

  function copy(text, what) {
    navigator.clipboard.writeText(text).then(() => setCopied(what)).catch(() => setCopied(''));
  }

  const idLine = info.employeeId ? `Employee ID: ${info.employeeId}\n` : '';
  const loginDetails = `GeoAlert Talisay staff account\n${idLine}Email: ${info.email}\nTemporary password: ${info.password}\nPlease change your password after signing in.`;

  return (
    <Modal
      title={info.created ? 'Account created' : 'Password reset'}
      subtitle={[info.name, info.employeeId, info.email].filter(Boolean).join(' · ')}
      onClose={onClose}
      width={480}
      labelId="adm-cred-title"
      footer={
        <>
          <button type="button" className="adm-btn adm-btn-ghost" onClick={() => copy(loginDetails, 'all')}>
            <Icon name="copy" size={16} />
            {copied === 'all' ? 'Copied' : 'Copy login details'}
          </button>
          <button type="button" className="adm-btn adm-btn-primary" onClick={onClose}>Done</button>
        </>
      }
    >
      <div className="adm-cred">
        <span className="adm-cred-badge"><Icon name={info.created ? 'userCheck' : 'key'} size={22} /></span>
        <p className="adm-cred-label">Temporary password</p>
        <div className="adm-cred-row">
          <code>{info.password}</code>
          <button type="button" className="adm-btn adm-btn-outline adm-btn-sm" onClick={() => copy(info.password, 'pw')}>
            <Icon name={copied === 'pw' ? 'check' : 'copy'} size={15} />
            {copied === 'pw' ? 'Copied' : 'Copy'}
          </button>
        </div>
        <div className="adm-alert adm-alert-warn">
          <Icon name="info" size={16} />
          This password is shown only once. Share it with the user privately and ask them to change it after signing in.
        </div>
      </div>
    </Modal>
  );
}

// After Add a user: the account has no password until its owner sets one
// from the emailed link. If the email didn't go, offer another try or a
// temporary password the admin passes on, as before invites existed.
function InviteDialog({ info, busy, onClose, onResend, onTemporary }) {
  const { sent } = info;
  return (
    <Modal
      title={sent ? 'Invite sent' : 'Account created, invite not sent'}
      subtitle={[info.name, info.employeeId, info.email].filter(Boolean).join(' · ')}
      onClose={busy ? () => {} : onClose}
      width={480}
      labelId="adm-invite-title"
      footer={sent ? (
        <button type="button" className="adm-btn adm-btn-primary" onClick={onClose}>Done</button>
      ) : (
        <>
          <button type="button" className="adm-btn adm-btn-ghost" onClick={onTemporary} disabled={Boolean(busy)}>
            <Icon name="key" size={16} />
            {busy === 'temporary' ? 'Working…' : 'Give a temporary password'}
          </button>
          <button type="button" className="adm-btn adm-btn-primary" onClick={onResend} disabled={Boolean(busy)}>
            {busy === 'resend' ? 'Sending…' : 'Try sending again'}
          </button>
        </>
      )}
    >
      <div className="adm-cred">
        <span className={`adm-cred-badge ${sent ? '' : 'is-warn'}`}><Icon name={sent ? 'mail' : 'alert'} size={22} /></span>
        {sent ? (
          <>
            <p className="adm-invite-text">
              We emailed <strong>{info.email}</strong> a link to set their own password. It works once, for 3 days.
            </p>
            <p className="adm-invite-text is-soft">
              Until they use it, the account shows as Invite pending and can't sign in. If the email doesn't arrive,
              check the address, then use Resend invite in the list.
            </p>
          </>
        ) : (
          <div className="adm-alert adm-alert-warn">
            <Icon name="info" size={16} />
            The account was created, but the invite email to {info.email} couldn't be sent. Try again, or give
            them a temporary password to sign in with instead.
          </div>
        )}
        {info.error && (
          <div className="adm-alert" role="alert">
            <Icon name="info" size={16} />
            {info.error}
          </div>
        )}
      </div>
    </Modal>
  );
}

export default function UsersTab({ users, roles, currentUser, loading, onChanged, notify, formRequest, clearFormRequest }) {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const [editing, setEditing] = useState(null); // null = closed, {} = new, user = edit
  const [confirm, setConfirm] = useState(null); // { kind, user }
  const [busy, setBusy] = useState(false);
  const [credentials, setCredentials] = useState(null);
  const [invite, setInvite] = useState(null); // { id, name, employeeId, email, sent, error }
  const [inviteBusy, setInviteBusy] = useState(''); // '' | 'resend' | 'temporary'

  // The Overview tab's "Add a user" button opens the form here
  const formOpen = editing !== null || formRequest;
  const formUser = editing && editing.id ? editing : null;

  function closeForm() {
    setEditing(null);
    clearFormRequest();
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users.filter((u) => {
      if (roleFilter && roleName(u.role) !== roleFilter) return false;
      if (statusFilter === 'active' && !(u.is_active && !u.invite_pending)) return false;
      if (statusFilter === 'pending' && !(u.is_active && u.invite_pending)) return false;
      if (statusFilter === 'inactive' && u.is_active) return false;
      if (!q) return true;
      return [u.full_name, u.email, u.position, u.employee_id, u.phone, u.assigned_barangay?.name]
        .some((v) => (v || '').toLowerCase().includes(q));
    });
  }, [users, search, roleFilter, statusFilter]);

  useEffect(() => { setPage(1); }, [search, roleFilter, statusFilter]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageUsers = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function save(payload) {
    if (formUser) {
      const result = await adminApi.users.update(formUser.id, payload);
      closeForm();
      const name = `${payload.first_name} ${payload.last_name}`;
      // A corrected email on an account still waiting for its invite gets a new one there
      if (result?.invite_sent === true) {
        notify(`Saved changes to ${name}'s account and sent a new invite to ${result.email}.`);
      } else if (result?.invite_sent === false) {
        notify(`Saved changes, but the invite to ${result.email} couldn't be sent. Use Resend invite to try again.`, 'bad');
      } else {
        notify(`Saved changes to ${name}'s account.`);
      }
    } else {
      const result = await adminApi.users.create(payload);
      closeForm();
      setInvite({
        id: result.user?.id,
        name: result.user?.full_name,
        employeeId: result.user?.employee_id,
        email: result.user?.email || payload.email,
        sent: Boolean(result.invite_sent),
      });
    }
    onChanged();
  }

  async function resendFromDialog() {
    setInviteBusy('resend');
    try {
      await adminApi.users.resendInvite(invite.id);
      setInvite((i) => ({ ...i, sent: true, error: '' }));
      onChanged();
    } catch (err) {
      setInvite((i) => ({ ...i, error: fieldErrors(err).form || "The invite still couldn't be sent." }));
    } finally {
      setInviteBusy('');
    }
  }

  async function temporaryFromDialog() {
    setInviteBusy('temporary');
    try {
      const result = await adminApi.users.resetPassword(invite.id);
      setCredentials({
        created: true, name: invite.name, employeeId: invite.employeeId,
        email: invite.email, password: result.temporary_password,
      });
      setInvite(null);
      onChanged();
    } catch (err) {
      setInvite((i) => ({ ...i, error: fieldErrors(err).form || 'That action failed. Please try again.' }));
    } finally {
      setInviteBusy('');
    }
  }

  async function runConfirm() {
    const { kind, user } = confirm;
    setBusy(true);
    try {
      if (kind === 'reset') {
        const result = await adminApi.users.resetPassword(user.id);
        setCredentials({
          created: false, name: user.full_name, employeeId: user.employee_id,
          email: user.email, password: result.temporary_password,
        });
      } else if (kind === 'resend') {
        await adminApi.users.resendInvite(user.id);
        notify(`Sent a new invite to ${user.email}.`);
      } else if (kind === 'deactivate') {
        await adminApi.users.deactivate(user.id);
        notify(`${user.full_name} can no longer sign in.`);
      } else if (kind === 'activate') {
        await adminApi.users.update(user.id, { is_active: true });
        notify(`${user.full_name} can sign in again.`);
      }
      setConfirm(null);
      onChanged();
    } catch (err) {
      setConfirm(null);
      notify(fieldErrors(err).form || 'That action failed. Please try again.', 'bad');
    } finally {
      setBusy(false);
    }
  }

  const filtersOn = search || roleFilter || statusFilter;

  return (
    <>
      <div className="adm-card adm-card-flush">
        <div className="adm-toolbar">
          <div className="adm-search">
            <Icon name="search" size={16} />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, email, position, barangay…"
              aria-label="Search users"
            />
          </div>
          <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} aria-label="Filter by role" className="adm-select">
            <option value="">All roles</option>
            {Object.entries(ROLE_META).map(([key, meta]) => (
              <option key={key} value={key}>{meta.label}</option>
            ))}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status" className="adm-select">
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="pending">Invite pending</option>
            <option value="inactive">Inactive</option>
          </select>
          <button type="button" className="adm-btn adm-btn-primary adm-toolbar-cta" onClick={() => setEditing({})}>
            <Icon name="plus" size={16} strokeWidth={2.5} />
            Add user
          </button>
        </div>

        <div className="adm-table-meta">
          {loading
            ? 'Loading accounts…'
            : filtersOn
              ? `Showing ${filtered.length} of ${users.length} accounts`
              : `${users.length} account${users.length === 1 ? '' : 's'}`}
          {filtersOn && (
            <button type="button" className="adm-link" onClick={() => { setSearch(''); setRoleFilter(''); setStatusFilter(''); }}>
              Clear filters
            </button>
          )}
        </div>

        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Contact</th>
                <th>Role</th>
                <th>Barangay</th>
                <th>Status</th>
                <th>Last sign-in</th>
                <th className="adm-th-actions"><span className="adm-sr">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {loading && users.length === 0 && [0, 1, 2].map((i) => (
                <tr key={i} className="adm-skeleton-row">
                  {[0, 1, 2, 3, 4, 5, 6].map((j) => <td key={j}><span className="adm-skeleton" /></td>)}
                </tr>
              ))}
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <div className="adm-empty">
                      <Icon name="users" size={28} />
                      <p>{users.length === 0 ? 'No accounts yet.' : 'No accounts match these filters.'}</p>
                    </div>
                  </td>
                </tr>
              )}
              {pageUsers.map((u) => {
                const isSelf = currentUser && String(currentUser.id) === String(u.id);
                return (
                  <tr key={u.id} className={u.is_active ? '' : 'is-inactive'}>
                    <td>
                      <div className="adm-person">
                        <Avatar user={u} />
                        <div className="adm-person-text">
                          <span className="adm-person-name">
                            {u.full_name || '—'}
                            {isSelf && <span className="adm-you">You</span>}
                          </span>
                          <span className="adm-person-sub">
                            {u.position || 'No position set'}
                            {u.employee_id && <> · <span className="adm-emp">{u.employee_id}</span></>}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="adm-contact">
                        <span>{u.email}</span>
                        <span className="adm-person-sub">{u.phone ? formatPhone(u.phone) : 'No mobile number'}</span>
                      </div>
                    </td>
                    <td><RoleBadge role={u.role} /></td>
                    <td className="adm-nowrap">{u.assigned_barangay?.name || <span className="adm-muted">—</span>}</td>
                    <td><StatusBadge active={u.is_active} pending={u.invite_pending} /></td>
                    <td className="adm-nowrap adm-muted" title={u.last_login ? new Date(u.last_login).toLocaleString() : undefined}>
                      {timeAgo(u.last_login)}
                    </td>
                    <td>
                      <div className="adm-row-actions">
                        <button type="button" className="adm-icon-btn" title="Edit account" aria-label={`Edit ${u.full_name}`} onClick={() => setEditing(u)}>
                          <Icon name="edit" size={16} />
                        </button>
                        {u.is_active && u.invite_pending && (
                          <button type="button" className="adm-icon-btn" title="Resend invite" aria-label={`Resend invite to ${u.full_name}`} onClick={() => setConfirm({ kind: 'resend', user: u })}>
                            <Icon name="mail" size={16} />
                          </button>
                        )}
                        <button type="button" className="adm-icon-btn" title="Reset password" aria-label={`Reset password for ${u.full_name}`} onClick={() => setConfirm({ kind: 'reset', user: u })}>
                          <Icon name="key" size={16} />
                        </button>
                        {u.is_active ? (
                          <button
                            type="button"
                            className="adm-icon-btn adm-icon-btn-danger"
                            title={isSelf ? "You can't deactivate your own account" : 'Deactivate account'}
                            aria-label={`Deactivate ${u.full_name}`}
                            disabled={isSelf}
                            onClick={() => setConfirm({ kind: 'deactivate', user: u })}
                          >
                            <Icon name="power" size={16} />
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="adm-icon-btn adm-icon-btn-good"
                            title="Activate account"
                            aria-label={`Activate ${u.full_name}`}
                            onClick={() => setConfirm({ kind: 'activate', user: u })}
                          >
                            <Icon name="power" size={16} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {pages > 1 && (
          <div className="adm-pager">
            <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <Icon name="chevronLeft" size={16} /> Previous
            </button>
            <span>Page {page} of {pages}</span>
            <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Next <Icon name="chevronRight" size={16} />
            </button>
          </div>
        )}
      </div>

      {formOpen && (
        <UserFormModal user={formUser} roles={roles} onClose={closeForm} onSave={save} />
      )}

      {confirm && (
        <ConfirmDialog
          busy={busy}
          onCancel={() => !busy && setConfirm(null)}
          onConfirm={runConfirm}
          {...{
            reset: {
              title: confirm.user.invite_pending ? 'Give a temporary password?' : 'Reset password?',
              message: confirm.user.invite_pending
                ? `${confirm.user.full_name} hasn't set a password yet. You'll get a temporary password to give them, and their invite link will stop working.`
                : `${confirm.user.full_name}'s current password will stop working right away. You'll get a new temporary password to give them.`,
              confirmLabel: confirm.user.invite_pending ? 'Give temporary password' : 'Reset password',
            },
            resend: {
              title: 'Resend invite?',
              message: `We'll email ${confirm.user.email} a new link to set their password. Any earlier invite link stops working.`,
              confirmLabel: 'Resend invite',
            },
            deactivate: {
              title: 'Deactivate account?',
              message: `${confirm.user.full_name} won't be able to sign in until the account is activated again. Their reports and history are kept.`,
              confirmLabel: 'Deactivate',
              danger: true,
            },
            activate: {
              title: 'Activate account?',
              message: `${confirm.user.full_name} will be able to sign in again with their existing password.`,
              confirmLabel: 'Activate',
            },
          }[confirm.kind]}
        />
      )}

      {invite && (
        <InviteDialog
          info={invite}
          busy={inviteBusy}
          onClose={() => setInvite(null)}
          onResend={resendFromDialog}
          onTemporary={temporaryFromDialog}
        />
      )}

      {credentials && <CredentialsDialog info={credentials} onClose={() => setCredentials(null)} />}
    </>
  );
}