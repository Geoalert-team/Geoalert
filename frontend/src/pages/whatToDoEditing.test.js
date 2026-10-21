import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import WhatToDo from './WhatToDo';
import { useAuth } from '../context/AuthContext';
import { guidanceApi } from '../api/guidanceApi';

jest.mock('../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../components/Navbar/PublicNavbar', () => () => null);
jest.mock('../api/hazardsApi', () => ({
  hazardsApi: { types: () => Promise.resolve([{ id: 1, name: 'Flood' }, { id: 2, name: 'Landslide' }, { id: 3, name: 'Fire' }]) },
}));
jest.mock('../api/guidanceApi', () => ({
  guidanceApi: { list: jest.fn(), remove: jest.fn(), create: jest.fn(), update: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  guidanceApi.list.mockResolvedValue([{
    id: 'a1', title: 'Prepare your home', body: 'Move valuables upstairs\nClear drains',
    timeline_phase: 'Before', hazard_type_detail: { name: 'Flood' }, created_at: '2026-10-01T00:00:00Z',
  }]);
});

async function render(canPublish, url = '/what-to-do?hazard=Flood&phase=before') {
  useAuth.mockReturnValue({ canPublish, user: canPublish ? { role: { name: 'DRRMO_Officer' } } : null });
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={[url]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><WhatToDo /></MemoryRouter>,
    );
  });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);
const click = (b) => act(async () => { b.click(); });

test('residents see the guidance with no edit controls', async () => {
  const el = await render(false);
  expect(el.textContent).toContain('Prepare your home');
  ['Add guidance', 'Edit', 'Delete'].forEach((t) => expect(button(el, t)).toBeUndefined());
});

test('officers get Add guidance, and Edit and Delete on each card', async () => {
  const el = await render(true);
  expect(button(el, 'Add guidance')).toBeDefined();
  expect(button(el, 'Edit')).toBeDefined();
  expect(button(el, 'Delete')).toBeDefined();
});

test('Delete asks first, and only hides the article when confirmed', async () => {
  guidanceApi.remove.mockResolvedValue({});
  const confirm = jest.spyOn(window, 'confirm');
  const el = await render(true);

  confirm.mockReturnValueOnce(false);
  await click(button(el, 'Delete'));
  expect(guidanceApi.remove).not.toHaveBeenCalled();

  confirm.mockReturnValueOnce(true);
  const before = guidanceApi.list.mock.calls.length;
  await click(button(el, 'Delete'));
  expect(confirm).toHaveBeenLastCalledWith('Remove this guidance? Residents will no longer see it.');
  expect(guidanceApi.remove).toHaveBeenCalledWith('a1');
  expect(guidanceApi.list.mock.calls.length).toBeGreaterThan(before); // reloaded
  confirm.mockRestore();
});

test('Edit opens the card in place with its own title and steps', async () => {
  const el = await render(true);
  await click(button(el, 'Edit'));
  expect(el.querySelector('form.ge input').value).toBe('Prepare your home');
  expect([...el.querySelectorAll('form.ge textarea')].map((t) => t.value)).toEqual(['Move valuables upstairs', 'Clear drains']);
});

test('Add guidance opens an empty form for the hazard and phase being viewed', async () => {
  guidanceApi.create.mockResolvedValue({});
  const el = await render(true);
  await click(button(el, 'Add guidance'));
  expect(el.querySelector('form.ge input').value).toBe('');
});

test('First aid stays fixed: no edit controls even for officers', async () => {
  const el = await render(true, '/what-to-do?hazard=Flood&phase=firstaid');
  expect(button(el, 'Add guidance')).toBeUndefined();
});

test('one form at a time: while editing, Add and the other card buttons step aside', async () => {
  const el = await render(true);
  await click(button(el, 'Edit'));
  expect(button(el, 'Add guidance')).toBeUndefined();
  expect(button(el, 'Delete')).toBeUndefined();
  await click(button(el, 'Cancel'));
  expect(button(el, 'Add guidance')).toBeDefined();
});
