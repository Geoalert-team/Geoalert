import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import LatestNews from './LatestNews';
import { newsApi } from '../../api/newsApi';

jest.mock('../../api/newsApi', () => ({ newsApi: { feed: jest.fn() } }));

const post = (id) => ({
  kind: 'announcement', id, title: `Post ${id}`, body: 'Text', photo_url: null, source: 'DRRMO',
  published_at: '2026-11-04T02:00:00+00:00', edited_at: null, can_edit: false,
});

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => jest.clearAllMocks());

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><LatestNews /></MemoryRouter>,
    );
  });
  return el;
}

test('the three newest posts, and a link to all the news', async () => {
  newsApi.feed.mockResolvedValue({ results: [post('a'), post('b'), post('c')], next_before: 'x' });
  const el = await render();
  expect(newsApi.feed).toHaveBeenCalledWith({ limit: 3 });
  expect(el.querySelector('h2').textContent).toBe('Latest updates');
  expect(el.querySelectorAll('.nw-card')).toHaveLength(3);
  const link = el.querySelector('a[href="/news"]');
  expect(link.textContent).toBe('See all news');
  expect(el.querySelector('button')).toBeNull(); // nothing to edit from the home page
});

test('no posts, no section', async () => {
  newsApi.feed.mockResolvedValue({ results: [], next_before: null });
  expect((await render()).innerHTML).toBe('');
});

test('a failed load hides the section', async () => {
  newsApi.feed.mockRejectedValue(new Error('offline'));
  expect((await render()).innerHTML).toBe('');
});
