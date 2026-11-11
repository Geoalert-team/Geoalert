import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import TutorialVideos from './TutorialVideos';
import { tutorialsApi } from '../../api/tutorialsApi';
import { useAuth } from '../../context/AuthContext';

jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../api/tutorialsApi', () => ({
  tutorialsApi: { list: jest.fn(), categories: jest.fn(), remove: jest.fn(), removeCategory: jest.fn() },
}));
// No JSX inside a jest.mock factory: it may only use what it requires itself
jest.mock('./AddVideosForm', () => {
  const React = require('react');
  return function AddVideosFormStub(props) {
    return React.createElement('div', { className: 'form-stub' },
      props.video ? `editing ${props.video.id}` : `adding in ${props.defaultCategoryId}`,
      React.createElement('button', { type: 'button', onClick: () => props.onClose(true) }, 'stub close'));
  };
});

const FIRST_AID = { id: 'c1', name: 'First Aid', description: 'Bandaging and bleeding', video_count: 1 };
const DRILLS = { id: 'c2', name: 'Drills', description: '', video_count: 1 };
const TYPHOON = { id: 'c3', name: 'Typhoon Response', description: '', video_count: 0 };
const YT = { id: 'v1', title: 'How to treat a fracture', description: 'Keep the limb still', category: { id: 'c1', name: 'First Aid' },
  source_type: 'youtube', youtube_id: '2v8vlXgGXwE', file_url: null, file_size: null };
const MP4 = { id: 'v2', title: 'Flood drill', description: '', category: { id: 'c2', name: 'Drills' },
  source_type: 'upload', youtube_id: null, file_url: 'https://files/v2.mp4', file_size: 31000000 };

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ canPublish: false });
  tutorialsApi.categories.mockResolvedValue([DRILLS, FIRST_AID, TYPHOON]);
  tutorialsApi.list.mockResolvedValue([YT, MP4]);
});

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<TutorialVideos />); });
  return el;
}
const click = (b) => act(async () => { b.click(); });
const chips = (el) => [...el.querySelectorAll('.tv-chip')].map((b) => b.textContent);
const chip = (el, text) => [...el.querySelectorAll('.tv-chip')].find((b) => b.textContent === text);
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);
const inDialog = (el, text) => [...el.querySelector('[role="dialog"]').querySelectorAll('button')].find((b) => b.textContent === text);
const arrow = (el, side) => el.querySelector(`.tv-arrow-${side}`);
const staff = () => useAuth.mockReturnValue({ canPublish: true });

test('the header is the chosen category, opening on the first A to Z', async () => {
  const el = await render();
  expect(el.querySelector('.tv-eyebrow').textContent).toBe('Tutorial videos');
  expect(el.querySelector('h2').textContent).toBe('Drills');
  expect(el.querySelector('.tv-category-description')).toBeNull();   // Drills has none
  expect(el.querySelector('video').getAttribute('src')).toBe('https://files/v2.mp4');
  expect(chips(el)).toEqual(['Drills', 'First Aid']);   // no All; residents don't get the empty one
  await click(chip(el, 'First Aid'));
  expect(el.querySelector('h2').textContent).toBe('First Aid');
  expect(el.querySelector('.tv-category-description').textContent).toBe('Bandaging and bleeding');
  expect(el.querySelector('iframe').getAttribute('src')).toBe('https://www.youtube-nocookie.com/embed/2v8vlXgGXwE');
  expect(el.querySelector('.wt-youtube-link').getAttribute('href')).toBe('https://www.youtube.com/watch?v=2v8vlXgGXwE');
});

test('with two categories both arrows name the other one', async () => {
  const el = await render();
  expect(arrow(el, 'prev').getAttribute('aria-label')).toBe('Previous: First Aid');
  expect(arrow(el, 'next').getAttribute('aria-label')).toBe('Next: First Aid');
  expect(arrow(el, 'next').getAttribute('data-tip')).toBe('Next: First Aid');
  await click(arrow(el, 'next'));
  expect(el.querySelector('h2').textContent).toBe('First Aid');
});

test('the arrows wrap around at the ends', async () => {
  staff();   // staff see all three, the empty one included
  const el = await render();
  expect(arrow(el, 'prev').getAttribute('aria-label')).toBe('Previous: Typhoon Response');
  expect(arrow(el, 'next').getAttribute('aria-label')).toBe('Next: First Aid');
  await click(arrow(el, 'prev'));
  expect(el.querySelector('h2').textContent).toBe('Typhoon Response');
  await click(arrow(el, 'next'));
  expect(el.querySelector('h2').textContent).toBe('Drills');
});

test('one category hides the arrows', async () => {
  tutorialsApi.categories.mockResolvedValue([FIRST_AID]);
  tutorialsApi.list.mockResolvedValue([YT]);
  const el = await render();
  expect(el.querySelector('.tv-arrow')).toBeNull();
  expect(el.querySelector('h2').textContent).toBe('First Aid');
});

test('staff see empty categories, with a message', async () => {
  staff();
  const el = await render();
  expect(chips(el)).toEqual(['Drills', 'First Aid', 'Typhoon Response']);
  await click(chip(el, 'Typhoon Response'));
  expect(el.textContent).toMatch('No videos in this category yet.');
});

test('a failed load offers to try again', async () => {
  tutorialsApi.list.mockRejectedValueOnce(new Error('down'));
  const el = await render();
  expect(el.textContent).toMatch("Couldn't load the videos. Try again.");
  await click(button(el, 'Try again'));
  expect(el.querySelector('video')).not.toBeNull();
});

test('residents see nothing when there are no videos', async () => {
  tutorialsApi.categories.mockResolvedValue([TYPHOON]);
  tutorialsApi.list.mockResolvedValue([]);
  const el = await render();
  expect(el.innerHTML).toBe('');
});

test('an MP4 that fails to play fetches fresh links once, not in a loop', async () => {
  const el = await render();
  await act(async () => { el.querySelector('video').dispatchEvent(new Event('error')); });
  await act(async () => { el.querySelector('video').dispatchEvent(new Event('error')); });
  expect(tutorialsApi.list).toHaveBeenCalledTimes(2);
});

test('residents get no tools; staff get Add, Delete category, and Edit and Delete for the chosen video', async () => {
  let el = await render();
  expect(button(el, 'Add videos')).toBeUndefined();
  expect(button(el, 'Delete category')).toBeUndefined();
  expect(el.querySelector('[aria-label^="Edit"]')).toBeNull();
  staff();
  tutorialsApi.categories.mockResolvedValue([FIRST_AID]);
  tutorialsApi.list.mockResolvedValue([YT, { ...YT, id: 'v3', title: 'Recovery position' }]);
  el = await render();
  expect(button(el, 'Add videos')).toBeDefined();
  expect(button(el, 'Delete category')).toBeDefined();
  const items = () => [...el.querySelectorAll('.wt-playlist > li')];
  expect(el.querySelectorAll('[aria-label^="Edit"]')).toHaveLength(1);
  expect(items()[0].querySelector('[aria-label="Edit \\"How to treat a fracture\\""]')).not.toBeNull();
  expect(items()[1].querySelector('[aria-label^="Edit"]')).toBeNull();
  await click(el.querySelectorAll('.wt-playlist-item')[1]);   // the tools follow the click
  expect(items()[1].querySelector('[aria-label="Delete \\"Recovery position\\""]')).not.toBeNull();
});

test('staff see the section with no categories at all', async () => {
  staff();
  tutorialsApi.categories.mockResolvedValue([]);
  tutorialsApi.list.mockResolvedValue([]);
  const el = await render();
  expect(el.querySelector('h2').textContent).toBe('Tutorial videos');
  expect(el.textContent).toMatch('No videos yet.');
  expect(button(el, 'Add videos')).toBeDefined();
});

test('one form at a time, opened in the shown category; closing with changes reloads', async () => {
  staff();
  const el = await render();
  await click(chip(el, 'First Aid'));
  await click(button(el, 'Add videos'));
  expect(el.querySelector('.form-stub').textContent).toMatch('adding in c1');
  expect(button(el, 'Add videos')).toBeUndefined();
  expect(button(el, 'Delete category')).toBeUndefined();
  expect(el.querySelector('[aria-label^="Edit"]')).toBeNull();
  await click(button(el, 'stub close'));
  expect(tutorialsApi.list).toHaveBeenCalledTimes(2);
  await click(el.querySelector('[aria-label="Edit \\"How to treat a fracture\\""]'));
  expect(el.querySelector('.form-stub').textContent).toMatch('editing v1');
});

test('an edit form closes if its video disappears on a refresh', async () => {
  staff();
  tutorialsApi.list.mockResolvedValueOnce([YT, MP4]).mockResolvedValueOnce([YT]);
  const el = await render();   // opens on Drills, playing the MP4
  await click(el.querySelector('[aria-label="Edit \\"Flood drill\\""]'));
  expect(el.querySelector('.form-stub').textContent).toMatch('editing v2');
  await act(async () => { el.querySelector('video').dispatchEvent(new Event('error')); });   // a refresh
  expect(el.querySelector('.form-stub')).toBeNull();
});

test('deleting a video asks in a dialog first', async () => {
  staff();
  tutorialsApi.list.mockResolvedValueOnce([YT, MP4]).mockResolvedValueOnce([YT]);
  tutorialsApi.remove.mockResolvedValue({});
  const el = await render();   // Drills, the MP4
  await click(el.querySelector('[aria-label="Delete \\"Flood drill\\""]'));
  expect(el.querySelector('.adm-confirm-text').textContent)
    .toBe("Delete 'Flood drill'? Residents will stop seeing it. The uploaded file is deleted too.");
  await click(inDialog(el, 'Cancel'));
  expect(el.querySelector('[role="dialog"]')).toBeNull();
  expect(tutorialsApi.remove).not.toHaveBeenCalled();
  await click(el.querySelector('[aria-label="Delete \\"Flood drill\\""]'));
  await click(inDialog(el, 'Delete'));
  expect(tutorialsApi.remove).toHaveBeenCalledWith('v2');
  expect(el.querySelector('[role="dialog"]')).toBeNull();
  expect(el.textContent).toMatch('No videos in this category yet.');   // staff stay on the now-empty Drills
});

test('Delete category warns, deletes it with its videos, and shows the first category left', async () => {
  staff();
  tutorialsApi.categories.mockResolvedValueOnce([DRILLS, FIRST_AID]).mockResolvedValueOnce([FIRST_AID]);
  tutorialsApi.list.mockResolvedValueOnce([YT, MP4]).mockResolvedValueOnce([YT]);
  tutorialsApi.removeCategory.mockResolvedValue({});
  const el = await render();   // Drills
  await click(button(el, 'Delete category'));
  expect(el.querySelector('.adm-confirm-text').textContent).toBe(
    "Are you sure you want to delete 'Drills'? This action is permanent and will automatically delete all videos contained within this category.",
  );
  await click(inDialog(el, 'Delete'));
  expect(tutorialsApi.removeCategory).toHaveBeenCalledWith('c2');
  expect(el.querySelector('h2').textContent).toBe('First Aid');
  expect(el.querySelector('iframe')).not.toBeNull();
});

test('a failed delete says why', async () => {
  staff();
  tutorialsApi.categories.mockResolvedValue([FIRST_AID]);
  tutorialsApi.list.mockResolvedValue([YT]);
  tutorialsApi.remove.mockRejectedValue(new Error("Your account isn't allowed to do this."));
  const el = await render();
  await click(el.querySelector('[aria-label^="Delete \\""]'));
  await click(inDialog(el, 'Delete'));
  expect(el.querySelector('.wt-action-error').textContent).toBe("Your account isn't allowed to do this.");
});

test('an open Delete category dialog closes rather than switch to another category', async () => {
  staff();
  const BANDAGING = { id: 'c0', name: 'Bandaging', description: '', video_count: 1 };
  const SLING = { ...YT, id: 'v9', title: 'Make a sling', category: { id: 'c0', name: 'Bandaging' } };
  tutorialsApi.categories.mockResolvedValueOnce([DRILLS, FIRST_AID]).mockResolvedValueOnce([BANDAGING, DRILLS, FIRST_AID]);
  tutorialsApi.list.mockResolvedValueOnce([YT, MP4]).mockResolvedValueOnce([SLING, YT, MP4]);
  const el = await render();   // Drills, playing the MP4
  await click(button(el, 'Delete category'));
  expect(el.querySelector('.adm-confirm-text').textContent).toMatch("'Drills'");
  // A background refresh brings a category that sorts first (another officer made it)
  await act(async () => { el.querySelector('video').dispatchEvent(new Event('error')); });
  expect(el.querySelector('[role="dialog"]')).toBeNull();
  expect(tutorialsApi.removeCategory).not.toHaveBeenCalled();
});
