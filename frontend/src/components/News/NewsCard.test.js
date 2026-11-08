import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import NewsCard from './NewsCard';

const hoursAgo = (h) => new Date(Date.now() - h * 3600 * 1000).toISOString();

const ANNOUNCEMENT = {
  kind: 'announcement', id: 'a1', title: 'Typhoon advisory', body: 'Line one\nLine two', photo_url: null,
  source: 'DRRMO', published_at: hoursAgo(2), edited_at: null, can_edit: false,
};
const ALERT = {
  kind: 'alert', id: 'z1', hazard_type: 'Fire', severity: 'Orange', published_at: hoursAgo(1),
  barangay: 'Home', puroks: ['Purok Near'], status: 'active', map_link: '/map?zone=z1',
};

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

async function render(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><NewsCard {...props} /></MemoryRouter>,
    );
  });
  return el;
}
const buttons = (el) => [...el.querySelectorAll('button')].map((b) => b.textContent.trim());

test('a DRRMO announcement is posted under the city seal, marked official, with when and its text', async () => {
  const el = await render({ post: ANNOUNCEMENT });
  expect(el.querySelector('.nw-office').textContent).toBe('Talisay City DRRMO');
  expect(el.querySelector('.nw-avatar img').getAttribute('src')).toMatch(/logo1/);
  expect(el.querySelector('.nw-official').textContent).toMatch('Official');
  const time = el.querySelector('time');
  expect(time.textContent).toBe('2 hrs ago');
  expect(time.getAttribute('title')).toMatch(/\d{4}/); // the full date on hover
  expect(el.querySelector('h3').textContent).toBe('Typhoon advisory');
  expect(el.querySelector('.nw-body').textContent).toBe('Line one\nLine two');
  expect(el.textContent).not.toMatch(/Edited/);
});

test('a BFP announcement is posted under the fire emblem', async () => {
  const el = await render({ post: { ...ANNOUNCEMENT, source: 'BFP' } });
  expect(el.querySelector('.nw-office').textContent).toBe('BFP Talisay City');
  expect(el.querySelector('.nw-avatar.is-bfp svg')).not.toBeNull();
  expect(el.querySelector('.nw-avatar img')).toBeNull();
});

test('an edited announcement says so', async () => {
  const el = await render({ post: { ...ANNOUNCEMENT, edited_at: hoursAgo(1) } });
  expect(el.textContent).toMatch(/Edited/);
});

test('long text folds behind See more; short text does not', async () => {
  const long = Array.from({ length: 12 }, (_, i) => `Line ${i + 1}`).join('\n');
  const el = await render({ post: { ...ANNOUNCEMENT, body: long } });
  expect(el.querySelector('.nw-body').classList.contains('is-folded')).toBe(true);
  await act(async () => { [...el.querySelectorAll('button')].find((b) => b.textContent === 'See more').click(); });
  expect(el.querySelector('.nw-body').classList.contains('is-folded')).toBe(false);
  expect(buttons(el)).toEqual(['See less']);
  expect(buttons(await render({ post: ANNOUNCEMENT }))).toEqual([]);
});

test('HTML typed into a post shows as text', async () => {
  const el = await render({ post: { ...ANNOUNCEMENT, title: '<b>x</b>', body: '<img src=x onerror=alert(1)>' } });
  expect(el.querySelector('h3').textContent).toBe('<b>x</b>');
  expect(el.querySelector('b')).toBeNull();
  expect(el.querySelector('.nw-body img')).toBeNull();
});

test('an alert post comes from GeoAlert with the hazard badge, level, place, status and the map while active', async () => {
  const el = await render({ post: ALERT });
  expect(el.querySelector('.nw-office').textContent).toBe('GeoAlert Talisay');
  expect(el.querySelector('.nw-avatar-badge svg')).not.toBeNull();
  expect(el.textContent).toMatch('Fire alert (Moderate) for Home · Purok Near');
  expect(el.querySelector('.nw-status').textContent).toBe('Active');
  expect(el.querySelector('a[href="/map?zone=z1"]').textContent).toMatch('View on map');
});

test('an alert whose hazard type is gone still shows', async () => {
  const el = await render({ post: { ...ALERT, hazard_type: null } });
  expect(el.textContent).toMatch('Hazard alert (Moderate) for Home · Purok Near');
});

test('a resolved alert says so and has no map link', async () => {
  const el = await render({ post: { ...ALERT, status: 'resolved', map_link: null } });
  expect(el.querySelector('.nw-status').textContent).toBe('Resolved');
  expect(el.querySelector('a[href^="/map"]')).toBeNull();
});

test('Edit and Delete only on a post the reader may change', async () => {
  const onEdit = jest.fn();
  const onDelete = jest.fn();
  let el = await render({ post: ANNOUNCEMENT, onEdit, onDelete });
  expect(buttons(el)).toEqual([]);
  el = await render({ post: { ...ANNOUNCEMENT, can_edit: true }, onEdit, onDelete });
  expect(buttons(el)).toEqual(['Edit', 'Delete']);
  await act(async () => { el.querySelector('button').click(); });
  expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: 'a1' }));
});
