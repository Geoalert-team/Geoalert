import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import NewsCard from './NewsCard';

const ANNOUNCEMENT = {
  kind: 'announcement', id: 'a1', title: 'Typhoon advisory', body: 'Line one\nLine two', photo_url: null,
  source: 'DRRMO', published_at: '2026-11-04T02:00:00+00:00', edited_at: null, can_edit: false,
};
const ALERT = {
  kind: 'alert', id: 'z1', hazard_type: 'Fire', severity: 'Orange', published_at: '2026-11-04T01:00:00+00:00',
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

test('an announcement shows its office, title, date and text with its line breaks', async () => {
  const el = await render({ post: ANNOUNCEMENT });
  expect(el.querySelector('.nw-source').textContent).toBe('DRRMO');
  expect(el.querySelector('h3').textContent).toBe('Typhoon advisory');
  expect(el.textContent).toMatch(/Nov 4, 2026/);
  const body = el.querySelector('.nw-body');
  expect(body.textContent).toBe('Line one\nLine two');
  expect(el.textContent).not.toMatch(/edited/);
});

test('an edited announcement says so', async () => {
  const el = await render({ post: { ...ANNOUNCEMENT, edited_at: '2026-11-04T03:00:00+00:00' } });
  expect(el.textContent).toMatch(/edited/);
});

test('HTML typed into a post shows as text', async () => {
  const el = await render({ post: { ...ANNOUNCEMENT, title: '<b>x</b>', body: '<img src=x onerror=alert(1)>' } });
  expect(el.querySelector('h3').textContent).toBe('<b>x</b>');
  expect(el.querySelector('b')).toBeNull();
  expect(el.querySelector('img')).toBeNull();
});

test('an alert post names the hazard, level and place, with the map while active', async () => {
  const el = await render({ post: ALERT });
  expect(el.textContent).toMatch('Fire alert (Moderate) for Home · Purok Near');
  expect(el.querySelector('.nw-status').textContent).toBe('Active');
  expect(el.querySelector('a[href="/map?zone=z1"]')).not.toBeNull();
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
