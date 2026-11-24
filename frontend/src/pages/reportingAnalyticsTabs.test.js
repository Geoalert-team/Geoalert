import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import ReportingAnalytics from './ReportingAnalytics';

// The tab wiring is under test; each panel is a stub
jest.mock('../components/Navbar/PublicNavbar', () => () => null);
jest.mock('./Reports', () => () => <p>REPORTS</p>);
jest.mock('./Analytics', () => () => <p>ANALYTICS</p>);
jest.mock('./PredictiveModels', () => () => <p>MODELS</p>);

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

async function renderAt(url) {
  const el = document.createElement('div');
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={[url]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ReportingAnalytics />
      </MemoryRouter>,
    );
  });
  return el;
}

const selected = (el) => el.querySelector('[role="tab"][aria-selected="true"]').textContent;

test('the third tab is Predictive models and ?tab=models opens it', async () => {
  const el = await renderAt('/app/reports?tab=models');
  expect([...el.querySelectorAll('[role="tab"]')].map((t) => t.textContent))
    .toEqual(['Reports', 'Analytics', 'Predictive models']);
  expect(selected(el)).toBe('Predictive models');
  expect(el.textContent).toContain(
    'How the prediction models were built and tested, and whether there is enough data to improve them.',
  );
  expect(el.querySelector('#ra-panel-models').hidden).toBe(false);
  expect(el.textContent).toContain('MODELS');
});

test('an unknown tab still opens Reports', async () => {
  const el = await renderAt('/app/reports?tab=nope');
  expect(selected(el)).toBe('Reports');
  expect(el.querySelector('#ra-panel-models')).toBeNull(); // not opened yet, so not mounted
});
