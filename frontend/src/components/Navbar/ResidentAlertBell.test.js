import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import ResidentAlertBell from './ResidentAlertBell';
import { hazardsApi } from '../../api/hazardsApi';

jest.mock('../../api/hazardsApi', () => ({ hazardsApi: { listTagged: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { window.localStorage.clear(); });

const SEEN_KEY = 'geoalert.seenHazardAlerts';
const zone = (id, props) => ({ type: 'Feature', id, geometry: null, properties: { status: 'Active', ...props } });
const FEED = {
  features: [
    zone('g1', { severity: 'Green', hazard_type_name: 'Flood', barangay_name: 'Pooc', activated_at: new Date().toISOString() }),
    zone('r1', { severity: 'Red', hazard_type_name: 'Fire', barangay_name: 'Bulacao' }),
  ],
};

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

async function render(answer) {
  hazardsApi.listTagged.mockImplementation(answer);
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ResidentAlertBell />
        <Where />
      </MemoryRouter>,
    );
  });
  return el;
}
const feed = (data) => () => Promise.resolve({ data, etag: null });
const badge = (el) => el.querySelector('.pn-bell-badge')?.textContent ?? null;
const openPanel = (el) => act(() => { el.querySelector('.pn-bell-btn').click(); });

test('the badge counts alerts this browser has not seen; opening the panel clears it', async () => {
  const el = await render(feed(FEED));
  expect(badge(el)).toBe('2');
  expect(el.querySelector('.pn-bell-btn').getAttribute('aria-label')).toBe('Hazard alerts, 2 new');

  openPanel(el);
  expect(badge(el)).toBeNull();
  expect(JSON.parse(window.localStorage.getItem(SEEN_KEY)).sort()).toEqual(['g1:Green', 'r1:Red']);
  // Still marked new while the panel is open, worst first
  const titles = [...el.querySelectorAll('.nb-item-title')].map((t) => t.textContent);
  expect(titles).toEqual(['Fire alert · Extreme risk', 'Flood alert · Low risk']);
  expect(el.querySelectorAll('.nb-item.is-unread')).toHaveLength(2);
  expect(el.querySelector('.nb-count').textContent).toBe('2 new');
  expect(el.querySelector('.nb-item-content').textContent).toMatch(/^In Bulacao\./);
});

test('remembers what was seen; a zone raised to a higher level is new again', async () => {
  window.localStorage.setItem(SEEN_KEY, JSON.stringify(['g1:Green', 'r1:Orange']));
  const el = await render(feed(FEED));
  expect(badge(el)).toBe('1');
  openPanel(el);
  expect([...el.querySelectorAll('.nb-item.is-unread .nb-item-title')].map((t) => t.textContent))
    .toEqual(['Fire alert · Extreme risk']);
});

test('tapping an alert opens its zone on the map', async () => {
  const el = await render(feed(FEED));
  openPanel(el);
  act(() => { el.querySelector('.nb-item').click(); });
  expect(el.querySelector('[data-testid="where"]').textContent).toBe('/map?zone=r1');
  expect(el.querySelector('.nb-panel')).toBeNull();
});

test('no active hazards: no badge, and the panel says so', async () => {
  const el = await render(feed({ features: [] }));
  expect(badge(el)).toBeNull();
  openPanel(el);
  expect(el.querySelector('.nb-empty strong').textContent).toBe('No active hazard alerts');
});

test('a failed load is never shown as "no alerts"', async () => {
  const el = await render(() => Promise.reject(new Error('offline')));
  expect(badge(el)).toBeNull();
  openPanel(el);
  expect(el.querySelector('.nb-empty strong').textContent).toBe('Checking for hazard alerts…');
});
