import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import TutorialVideos from './TutorialVideos';
import { tutorialsApi } from '../../api/tutorialsApi';
import { useAuth } from '../../context/AuthContext';

// The section with the real Add/Edit form and category picker inside it,
// against a small in-memory server: what the picker changes must reach the
// section once the form closes.
jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../api/tutorialsApi', () => ({ tutorialsApi: {
  list: jest.fn(), categories: jest.fn(), remove: jest.fn(), create: jest.fn(), update: jest.fn(),
  checkYouTube: jest.fn(), createCategory: jest.fn(), updateCategory: jest.fn(), removeCategory: jest.fn() } }));

const DRILLS = { id: 'c2', name: 'Drills', description: '', video_count: 1 };
const FIRST_AID = { id: 'c1', name: 'First Aid', description: 'Bandaging and bleeding', video_count: 1 };
const YT = { id: 'v1', title: 'How to treat a fracture', description: '', category: { id: 'c1', name: 'First Aid' },
  source_type: 'youtube', youtube_id: '2v8vlXgGXwE', file_url: null, file_size: null };
const MP4 = { id: 'v2', title: 'Flood drill', description: '', category: { id: 'c2', name: 'Drills' },
  source_type: 'upload', youtube_id: null, file_url: 'https://files/v2.mp4', file_size: 31000000 };

let server;
beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ canPublish: true });
  server = { categories: [DRILLS, FIRST_AID], videos: [YT, MP4] };
  tutorialsApi.list.mockImplementation(() => Promise.resolve(server.videos));
  tutorialsApi.categories.mockImplementation(() => Promise.resolve(server.categories));
  tutorialsApi.removeCategory.mockImplementation((id) => {
    server.categories = server.categories.filter((c) => c.id !== id);
    server.videos = server.videos.filter((v) => v.category.id !== id);
    return Promise.resolve({});
  });
  tutorialsApi.updateCategory.mockImplementation((id, fields) => {
    server.categories = server.categories.map((c) => (c.id === id ? { ...c, ...fields } : c));
    return Promise.resolve({});
  });
});

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<TutorialVideos />); });
  return el;
}
const click = (b) => act(async () => { b.click(); });
const button = (root, text) => [...root.querySelectorAll('button')].find((b) => b.textContent === text);
const inDialog = (el, text) => button(el.querySelector('[role="dialog"]'), text);
async function type(input, value) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}

test("deleting the edited video's category in the picker closes the form and refreshes the section", async () => {
  const el = await render();
  await click(button(el, 'First Aid'));
  await click(el.querySelector('[aria-label="Edit \\"How to treat a fracture\\""]'));
  const form = el.querySelector('.tv-form');
  expect(form.querySelector('h3').textContent).toBe('Edit video');
  await click(button(form, 'Delete'));
  await click(inDialog(el, 'Delete'));
  expect(tutorialsApi.removeCategory).toHaveBeenCalledWith('c1');
  expect(el.querySelector('.tv-form')).toBeNull();   // its video is gone with the category
  expect(el.querySelector('h2').textContent).toBe('Drills');
  expect(el.textContent).not.toMatch('How to treat a fracture');
});

test('a description edited in the picker shows in the header after Cancel', async () => {
  const el = await render();   // Drills, no description yet
  await click(button(el, 'Add videos'));
  const form = el.querySelector('.tv-form');
  await click(button(form, 'Edit category'));
  await type(form.querySelector('[aria-label="Category description"]'), 'What each purok leader does');
  await click(button(form, 'Save'));
  expect(tutorialsApi.updateCategory).toHaveBeenCalledWith('c2', { name: 'Drills', description: 'What each purok leader does' });
  await click(button(form, 'Cancel'));
  expect(el.querySelector('.tv-form')).toBeNull();
  expect(el.querySelector('.tv-category-description').textContent).toBe('What each purok leader does');
});
