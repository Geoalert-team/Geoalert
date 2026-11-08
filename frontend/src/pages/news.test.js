import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import News from './News';
import { newsApi } from '../api/newsApi';
import { useAuth } from '../context/AuthContext';

jest.mock('../components/Navbar/PublicNavbar', () => () => null);
jest.mock('../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../api/newsApi', () => ({
  newsApi: { feed: jest.fn(), create: jest.fn(), update: jest.fn(), remove: jest.fn() },
}));

const post = (id, extra = {}) => ({
  kind: 'announcement', id, title: `Post ${id}`, body: 'Text', photo_url: null, source: 'DRRMO',
  published_at: '2026-11-04T02:00:00+00:00', edited_at: null, can_edit: false, ...extra,
});

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: null, canPostNews: false });
  newsApi.feed.mockResolvedValue({ results: [post('a'), post('b')], next_before: null });
});

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><News /></MemoryRouter>,
    );
  });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent.trim() === text);
const titles = (el) => [...el.querySelectorAll('.nw-card h3')].map((h) => h.textContent);
async function type(input, value) {
  await act(async () => {
    const proto = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

test('an official header with the city seal, and placeholder cards while loading', async () => {
  newsApi.feed.mockReturnValueOnce(new Promise(() => {})); // never answers
  const el = await render();
  expect(el.querySelector('h1').textContent).toBe('News & Advisories');
  expect(el.querySelector('.nw-header img').getAttribute('src')).toMatch(/logo1/);
  expect(el.querySelectorAll('.nw-skeleton').length).toBeGreaterThan(0);
  expect(el.textContent).not.toMatch('Loading');
});

test('the feed loads, and Load more appends the next page until the end', async () => {
  newsApi.feed
    .mockResolvedValueOnce({ results: [post('a'), post('b')], next_before: '2026-11-04T01:00:00+00:00' })
    .mockResolvedValueOnce({ results: [post('c')], next_before: null });
  const el = await render();
  expect(titles(el)).toEqual(['Post a', 'Post b']);
  await act(async () => { button(el, 'Load more').click(); });
  expect(newsApi.feed).toHaveBeenLastCalledWith({ before: '2026-11-04T01:00:00+00:00' });
  expect(titles(el)).toEqual(['Post a', 'Post b', 'Post c']);
  expect(button(el, 'Load more')).toBeUndefined();
});

test('a failed load says so and can be tried again', async () => {
  newsApi.feed.mockRejectedValueOnce(new Error('offline'));
  const el = await render();
  expect(el.textContent).toMatch("Couldn't load the news.");
  await act(async () => { button(el, 'Try again').click(); });
  expect(titles(el)).toEqual(['Post a', 'Post b']);
});

test('New announcement only for those who may post', async () => {
  let el = await render();
  expect(button(el, 'New announcement')).toBeUndefined();
  useAuth.mockReturnValue({ user: { role: { name: 'BFP_Personnel' } }, canPostNews: true });
  el = await render();
  expect(button(el, 'New announcement')).toBeDefined();
});

test('posting adds the new announcement first; a server error stays under its field', async () => {
  useAuth.mockReturnValue({ user: { role: { name: 'DRRMO_Officer' } }, canPostNews: true });
  newsApi.create
    .mockRejectedValueOnce(Object.assign(new Error('Bad request'),
      { data: { title: 'Ensure this field has no more than 150 characters.' } }))
    .mockResolvedValueOnce(post('new', { title: 'Typhoon advisory', can_edit: true }));
  const el = await render();
  await act(async () => { button(el, 'New announcement').click(); });
  await type(el.querySelector('input[name="title"]'), 'Typhoon advisory');
  await type(el.querySelector('textarea[name="body"]'), 'Stay indoors.');

  await act(async () => { button(el, 'Post').click(); });
  expect(newsApi.create).toHaveBeenCalledWith({ title: 'Typhoon advisory', body: 'Stay indoors.', photo: null });
  expect(el.textContent).toMatch('Ensure this field has no more than 150 characters.');
  expect(el.querySelector('input[name="title"]').value).toBe('Typhoon advisory');

  await act(async () => { button(el, 'Post').click(); });
  expect(titles(el)[0]).toBe('Typhoon advisory');
  expect(el.querySelector('input[name="title"]')).toBeNull();
});

test('the delete dialog takes focus and Escape closes it', async () => {
  useAuth.mockReturnValue({ user: { role: { name: 'DRRMO_Officer' } }, canPostNews: true });
  newsApi.feed.mockResolvedValue({ results: [post('a', { can_edit: true })], next_before: null });
  const el = await render();
  await act(async () => { button(el, 'Delete').click(); });
  expect(el.querySelector('[role="alertdialog"]').contains(document.activeElement)).toBe(true);
  await act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
  expect(el.querySelector('[role="alertdialog"]')).toBeNull();
  expect(newsApi.remove).not.toHaveBeenCalled();
});

test('posting after the feed failed to load shows the new post', async () => {
  useAuth.mockReturnValue({ user: { role: { name: 'DRRMO_Officer' } }, canPostNews: true });
  newsApi.feed.mockRejectedValueOnce(new Error('offline'));
  newsApi.create.mockResolvedValueOnce(post('new', { title: 'Typhoon advisory', can_edit: true }));
  const el = await render();
  await act(async () => { button(el, 'New announcement').click(); });
  await type(el.querySelector('input[name="title"]'), 'Typhoon advisory');
  await type(el.querySelector('textarea[name="body"]'), 'Stay indoors.');
  await act(async () => { button(el, 'Post').click(); });
  expect(titles(el)).toEqual(['Typhoon advisory']);
});

test('Delete asks first, then removes the post', async () => {
  useAuth.mockReturnValue({ user: { role: { name: 'DRRMO_Officer' } }, canPostNews: true });
  newsApi.feed.mockResolvedValue({ results: [post('a', { can_edit: true }), post('b')], next_before: null });
  newsApi.remove.mockResolvedValue(null);
  const el = await render();
  await act(async () => { button(el, 'Delete').click(); });
  expect(newsApi.remove).not.toHaveBeenCalled();
  await act(async () => { button(el, 'Delete post').click(); });
  expect(newsApi.remove).toHaveBeenCalledWith('a');
  expect(titles(el)).toEqual(['Post b']);
});
