import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import UsersTab from './UsersTab';
import { adminApi } from '../../../api/adminApi';

jest.mock('../../../api/adminApi', () => ({
  adminApi: { users: { create: jest.fn(), update: jest.fn(), resendInvite: jest.fn(), resetPassword: jest.fn() } },
}));
// The form itself has its own tests; here it only hands a filled-in payload back
jest.mock('./UserFormModal', () => ({
  __esModule: true,
  default: ({ onSave }) => require('react').createElement('button', {
    'data-testid': 'form-save',
    onClick: () => onSave({ first_name: 'Juan', last_name: 'Dela Cruz', email: 'juan@example.com' }).catch(() => {}),
  }, 'save'),
}));

const ROLE = { id: 2, name: 'DRRMO_Officer' };
const pending = {
  id: 'p1', full_name: 'Juan Dela Cruz', email: 'juan@example.com', role: ROLE,
  is_active: true, invite_pending: true, last_login: null,
};
const active = {
  id: 'a1', full_name: 'Ana Reyes', email: 'ana@example.com', role: ROLE,
  is_active: true, invite_pending: false, last_login: null,
};

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });
let root;
afterEach(async () => {
  await act(async () => { root?.unmount(); });
  document.body.innerHTML = '';
});

async function render(props = {}) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const notify = jest.fn();
  const onChanged = jest.fn();
  root = createRoot(el);
  await act(async () => {
    root.render(
      <UsersTab
        users={[pending, active]} roles={[ROLE]} currentUser={{ id: 'me' }} loading={false}
        onChanged={onChanged} notify={notify} formRequest={false} clearFormRequest={() => {}}
        {...props}
      />,
    );
  });
  return { el, notify, onChanged };
}
const click = (node) => act(async () => { node.click(); });
const button = (scope, text) => [...scope.querySelectorAll('button')].find((b) => b.textContent.trim() === text);
const rowOf = (el, name) => [...el.querySelectorAll('tbody tr')].find((r) => r.textContent.includes(name));
const addUser = async (el) => {
  await click(button(el, 'Add user'));
  await click(el.querySelector('[data-testid="form-save"]'));
};

test('a pending account says so and can be sent a new invite; an active one cannot', async () => {
  adminApi.users.resendInvite.mockResolvedValue({ message: 'ok' });
  const { el, notify } = await render();
  expect(rowOf(el, 'Juan').textContent).toContain('Invite pending');
  expect(rowOf(el, 'Ana').textContent).toContain('Active');
  expect(rowOf(el, 'Ana').querySelector('[title="Resend invite"]')).toBeNull();

  await click(rowOf(el, 'Juan').querySelector('[title="Resend invite"]'));
  expect(document.body.textContent).toContain('Any earlier invite link stops working.');
  await click(button(document.body, 'Resend invite'));
  expect(adminApi.users.resendInvite).toHaveBeenCalledWith('p1');
  expect(notify).toHaveBeenCalledWith('Sent a new invite to juan@example.com.');
});

test('the status filter separates pending accounts from active ones', async () => {
  const { el } = await render();
  const select = el.querySelector('select[aria-label="Filter by status"]');
  for (const [value, shown, hidden] of [['pending', 'Juan', 'Ana'], ['active', 'Ana', 'Juan']]) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, value);
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(rowOf(el, shown)).toBeDefined();
    expect(rowOf(el, hidden)).toBeUndefined();
  }
});

test('creating an account shows that the invite went, and never a password', async () => {
  adminApi.users.create.mockResolvedValue({
    user: { id: 'n1', full_name: 'Juan Dela Cruz', email: 'juan@example.com', employee_id: 'DRRMO-0012' },
    invite_sent: true,
  });
  const { el } = await render({ users: [] });
  await addUser(el);
  const dialog = document.body.querySelector('[aria-labelledby="adm-invite-title"]');
  expect(dialog.textContent).toContain('Invite sent');
  expect(dialog.textContent).toContain('It works once, for 3 days.');
  expect(document.body.textContent).not.toMatch(/temporary password/i);
  await click(button(dialog, 'Done'));
});

test('when the invite email fails, the admin can retry or fall back to a temporary password', async () => {
  adminApi.users.create.mockResolvedValue({
    user: { id: 'n1', full_name: 'Juan Dela Cruz', email: 'juan@example.com' }, invite_sent: false,
  });
  adminApi.users.resendInvite.mockRejectedValueOnce({ data: { error: 'Still down.' } }).mockResolvedValueOnce({});
  adminApi.users.resetPassword.mockResolvedValue({ temporary_password: 'Tmp-Pass-123' });
  const { el } = await render({ users: [] });
  await addUser(el);
  const dialog = () => document.body.querySelector('[aria-labelledby="adm-invite-title"]');
  expect(dialog().textContent).toContain("couldn't be sent");

  await click(button(dialog(), 'Try sending again'));
  expect(dialog().textContent).toContain('Still down.');
  await click(button(dialog(), 'Try sending again'));
  expect(dialog().textContent).toContain('Invite sent');
  await click(button(dialog(), 'Done'));

  // A fresh failure, this time taking the temporary password
  await addUser(el);
  await click(button(dialog(), 'Give a temporary password'));
  expect(adminApi.users.resetPassword).toHaveBeenCalledWith('n1');
  expect(dialog()).toBeNull();
  expect(document.body.textContent).toContain('Tmp-Pass-123');
});
