import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import GuidanceSteps from './GuidanceSteps';
import { useAuth } from '../../context/AuthContext';

jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../api/hazardsApi', () => ({
  hazardsApi: { types: () => Promise.resolve([{ id: 1, name: 'Flood' }]) },
}));
jest.mock('../../api/guidanceApi', () => ({
  guidanceApi: {
    list: () => Promise.resolve([{
      id: 'a1', title: 'Prepare', body: 'Move valuables upstairs', timeline_phase: 'Before', created_at: '2026-10-01T00:00:00Z',
    }]),
  },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

async function render(canPublish) {
  useAuth.mockReturnValue({ canPublish });
  const el = document.createElement('div');
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><GuidanceSteps type="Flood" /></MemoryRouter>,
    );
  });
  return el;
}

test('officers edit on What to do, at the hazard and phase they are reading', async () => {
  const el = await render(true);
  expect(el.textContent).toContain('Move valuables upstairs');
  const link = [...el.querySelectorAll('a')].find((a) => a.textContent === 'Edit on What to do');
  expect(link.getAttribute('href')).toBe('/what-to-do?hazard=Flood&phase=before');
  expect([...el.querySelectorAll('button')].some((b) => /Edit guidance|Add guidance/.test(b.textContent))).toBe(false);
});

test('residents read the steps with no edit link', async () => {
  const el = await render(false);
  expect(el.textContent).toContain('Move valuables upstairs');
  expect(el.textContent).not.toContain('Edit on What to do');
});
