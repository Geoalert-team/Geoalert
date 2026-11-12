import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import UserFormModal from './UserFormModal';
import { adminApi } from '../../../api/adminApi';

jest.mock('../../../api/adminApi', () => ({
  adminApi: { users: { nextEmployeeIds: jest.fn() } },
}));
jest.mock('../../../api/barangaysApi', () => ({
  barangaysApi: { list: () => Promise.resolve({ features: [] }) },
}));

const ROLES = [
  { id: 1, name: 'System_Admin' },
  { id: 2, name: 'DRRMO_Officer' },
  { id: 3, name: 'Barangay_Personnel' },
  { id: 4, name: 'BFP_Personnel' },
];
const NEXT = {
  System_Admin: 'ADMIN-0005', DRRMO_Officer: 'DRRMO-0012',
  Barangay_Personnel: 'BRGY-0020', BFP_Personnel: 'BFP-0003',
};

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  adminApi.users.nextEmployeeIds.mockResolvedValue(NEXT);
  Object.assign(navigator, { clipboard: { writeText: jest.fn(() => Promise.resolve()) } });
});

async function render(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(<UserFormModal roles={ROLES} onClose={() => {}} onSave={() => {}} {...props} />);
  });
  return el;
}
const idBox = (el) => el.querySelector('.adm-id-copy');
const pickRole = (el, id) => act(async () => { el.querySelector(`input[name="role"][value="${id}"]`).click(); });

test('a new account shows the real next ID for the chosen role, never "Automatic"', async () => {
  const el = await render({});
  expect(el.innerHTML).not.toMatch(/automatic/i);
  expect(idBox(el).disabled).toBe(true);
  expect(idBox(el).textContent).toBe('Choose a role first');

  await pickRole(el, 2);
  expect(idBox(el).disabled).toBe(false);
  expect(idBox(el).textContent).toContain('DRRMO-0012');

  await pickRole(el, 3);
  expect(idBox(el).textContent).toContain('BRGY-0020');
  expect(el.innerHTML).not.toMatch(/automatic/i);
});

test('clicking the ID copies it', async () => {
  const el = await render({});
  await pickRole(el, 4);
  await act(async () => { idBox(el).click(); });
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith('BFP-0003');
  expect(idBox(el).textContent).toContain('Copied');
});

test('an existing account shows its own ID and does not ask for the next one', async () => {
  const user = {
    id: 'u1', email: 'a@test.ph', first_name: 'Ana', last_name: 'Cruz', phone: '+639171234567',
    position: 'Officer', employee_id: 'DRRMO-0003', role: { id: 2, name: 'DRRMO_Officer' },
  };
  const el = await render({ user });
  expect(adminApi.users.nextEmployeeIds).not.toHaveBeenCalled();
  expect(idBox(el).textContent).toContain('DRRMO-0003');
  await act(async () => { idBox(el).click(); });
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith('DRRMO-0003');
});

test('clicking the ID does not submit the form', async () => {
  const onSave = jest.fn();
  const el = await render({ onSave });
  await pickRole(el, 2);
  await act(async () => { idBox(el).click(); });
  expect(onSave).not.toHaveBeenCalled();
});
