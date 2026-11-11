import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import VideoPlayer from './VideoPlayer';

const YT = { id: 'v1', title: 'How to treat a fracture', source_type: 'youtube', youtube_id: '2v8vlXgGXwE', file_url: null };

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

async function render(video) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<VideoPlayer video={video} onError={() => {}} />); });
  return el;
}
const fire = (node, type) => act(async () => { node.dispatchEvent(new Event(type)); });

// YouTube's player is about 690 KB of script before it can draw its own thumbnail, so
// the page shows the thumbnail itself and loads the player only when someone presses play
test('a YouTube video shows its thumbnail and a play button, not the player', async () => {
  const el = await render(YT);
  expect(el.querySelector('iframe')).toBeNull();
  expect(el.querySelector('img').getAttribute('src')).toBe('https://i.ytimg.com/vi/2v8vlXgGXwE/maxresdefault.jpg');
  expect(el.querySelector('button').getAttribute('aria-label')).toBe('Play: How to treat a fracture');
});

test('pressing play loads the player and starts the video', async () => {
  const el = await render(YT);
  await act(async () => { el.querySelector('button').click(); });
  const frame = el.querySelector('iframe');
  expect(frame.getAttribute('src')).toBe('https://www.youtube-nocookie.com/embed/2v8vlXgGXwE?autoplay=1');
  expect(frame.getAttribute('allow').split('; ')).toContain('autoplay');
  expect(frame.getAttribute('title')).toBe('How to treat a fracture');
  expect(el.querySelector('img')).toBeNull();
});

test('a video without a large thumbnail falls back to the standard one', async () => {
  // Some browsers report YouTube's 404 as an error...
  const failed = await render(YT);
  await fire(failed.querySelector('img'), 'error');
  expect(failed.querySelector('img').getAttribute('src')).toBe('https://i.ytimg.com/vi/2v8vlXgGXwE/hqdefault.jpg');

  // ...others show the 120 by 90 grey placeholder it comes with
  const placeholder = await render(YT);
  const img = placeholder.querySelector('img');
  Object.defineProperty(img, 'naturalWidth', { value: 120 });
  await fire(img, 'load');
  expect(placeholder.querySelector('img').getAttribute('src')).toBe('https://i.ytimg.com/vi/2v8vlXgGXwE/hqdefault.jpg');
});

test('a large thumbnail that loads is kept', async () => {
  const el = await render(YT);
  const img = el.querySelector('img');
  Object.defineProperty(img, 'naturalWidth', { value: 1280 });
  await fire(img, 'load');
  expect(el.querySelector('img').getAttribute('src')).toBe('https://i.ytimg.com/vi/2v8vlXgGXwE/maxresdefault.jpg');
});
