import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import AddVideosForm from './AddVideosForm';
import { tutorialsApi } from '../../api/tutorialsApi';

jest.mock('../../api/tutorialsApi', () => ({ tutorialsApi: {
  categories: jest.fn(), create: jest.fn(), update: jest.fn(), checkYouTube: jest.fn(),
  createCategory: jest.fn(), updateCategory: jest.fn(), removeCategory: jest.fn() } }));

const CATS = [{ id: 'c1', name: 'First Aid', video_count: 10 }];
const file = (name, size = 1000) => Object.defineProperty(new File(['x'], name, { type: 'video/mp4' }), 'size', { value: size });

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  global.URL.createObjectURL = jest.fn(() => 'blob:preview');
  global.URL.revokeObjectURL = jest.fn();
  tutorialsApi.categories.mockResolvedValue(CATS);
  tutorialsApi.checkYouTube.mockImplementation((url) => Promise.resolve(
    { youtube_id: url.slice(-11), status: 'ok', title: `Title ${url.slice(-3)}`, duplicate: null }));
});

async function render(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<AddVideosForm {...props} />); });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);
const click = (b) => act(async () => { b.click(); });
// React listens for 'input' with the native value setter, as a person typing does
async function type(input, value) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
async function pickFiles(el, files) {
  const input = el.querySelector('[aria-label="MP4 files"]');
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
}
const states = (el) => [...el.querySelectorAll('.tv-row-state')].map((s) => s.textContent);
async function change(select, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
  await act(async () => { setter.call(select, value); select.dispatchEvent(new Event('change', { bubbles: true })); });
}
const FRACTURE = { id: 'v1', title: 'Fracture', description: '', category: { id: 'c1', name: 'First Aid' },
  source_type: 'youtube', youtube_id: '2v8vlXgGXwE', file_url: null, file_size: null };

test('links and files go in one batch, titles filled in', async () => {
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 222298112, onClose: jest.fn() });
  expect(el.textContent).toMatch('Uploaded videos use 212.0 MB of the 1 GB shared with report photos.');
  await type(el.querySelector('[aria-label="YouTube links"]'), 'https://youtu.be/aaaaaaaaaaa\nhttps://youtu.be/bbbbbbbbbbb\nhttps://youtu.be/ccccccccccc');
  await click(button(el, 'Add links'));
  await pickFiles(el, [file('flood-drill_2026.mp4'), file('evac.mp4')]);
  const titles = [...el.querySelectorAll('[aria-label="Title"]')].map((i) => i.value);
  expect(titles).toEqual(['Title aaa', 'Title bbb', 'Title ccc', 'flood drill 2026', 'evac']);
  expect(button(el, 'Publish 5 videos').disabled).toBe(false);
});

test('a file over 50 MB is never uploaded and blocks Publish', async () => {
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 0, onClose: jest.fn() });
  await pickFiles(el, [file('big.mp4', 66270000)]);
  expect(states(el)).toEqual(['Too big (63.2 MB, limit 50 MB)']);
  expect(button(el, 'Publish 1 video').disabled).toBe(true);
  expect(tutorialsApi.create).not.toHaveBeenCalled();
});

test('rows are sent one at a time in order; a failed row can be retried alone', async () => {
  let finishFirst;
  tutorialsApi.create
    .mockImplementationOnce((video, onProgress) => new Promise((resolve) => { onProgress(62); finishFirst = resolve; }))
    .mockRejectedValueOnce(new Error("That file isn't an MP4 video."))
    .mockResolvedValueOnce({ id: 'v2' });
  const onClose = jest.fn();
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 0, onClose });
  await pickFiles(el, [file('one.mp4'), file('two.mp4')]);
  await click(button(el, 'Publish 2 videos'));
  expect(el.textContent).toMatch('62%');
  expect(tutorialsApi.create).toHaveBeenCalledTimes(1);
  expect(tutorialsApi.create.mock.calls[0][0]).toMatchObject({ category: 'c1', sourceType: 'upload', title: 'one' });
  await act(async () => { finishFirst({ id: 'v1' }); });
  expect(tutorialsApi.create).toHaveBeenCalledTimes(2);
  expect(el.querySelector('[role="alert"]').textContent).toBe("That file isn't an MP4 video.");
  await click(button(el, 'Retry'));
  expect(tutorialsApi.create).toHaveBeenCalledTimes(3);
  expect(tutorialsApi.create.mock.calls[2][0].title).toBe('two');
  expect(el.textContent).toMatch('2 videos published');
  await click(button(el, 'Add more videos'));
  expect(el.querySelectorAll('[aria-label="Title"]')).toHaveLength(0);
  expect(el.querySelector('select[aria-label="Category"]').value).toBe('c1');
  await click(button(el, 'Done'));
  expect(onClose).toHaveBeenCalledWith(true);
});

test('leaving while uploading asks first', async () => {
  tutorialsApi.create.mockImplementation(() => new Promise(() => {}));
  const onClose = jest.fn();
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 0, onClose });
  await pickFiles(el, [file('one.mp4')]);
  await click(button(el, 'Publish 1 video'));
  jest.spyOn(window, 'confirm').mockReturnValueOnce(false);
  await click(button(el, 'Cancel'));
  expect(window.confirm).toHaveBeenCalledWith('1 video is still uploading. Leave anyway?');
  expect(onClose).not.toHaveBeenCalled();
});

test('editing a YouTube video with a new file switches it to MP4, and is not its own duplicate', async () => {
  tutorialsApi.update.mockResolvedValue({});
  tutorialsApi.checkYouTube.mockResolvedValue({ youtube_id: '2v8vlXgGXwE', status: 'ok', title: 'X', duplicate: 'First Aid' });
  const video = { id: 'v1', title: 'Fracture', description: '', category: { id: 'c1', name: 'First Aid' },
    source_type: 'youtube', youtube_id: '2v8vlXgGXwE', file_url: null, file_size: null };
  const onClose = jest.fn();
  const el = await render({ video, usedBytes: 0, onClose });
  expect(el.querySelector('h3').textContent).toBe('Edit video');
  await type(el.querySelector('[aria-label="YouTube links"]'), 'https://youtu.be/2v8vlXgGXwE');
  await click(button(el, 'Add links'));
  expect(tutorialsApi.checkYouTube).toHaveBeenCalledWith('https://youtu.be/2v8vlXgGXwE');
  expect(states(el)).toEqual(['Ready']);   // not "Already in First Aid": that is this video
  await pickFiles(el, [file('fracture.mp4')]);
  expect(el.querySelectorAll('[aria-label="Title"]')).toHaveLength(1);
  expect(el.querySelector('[aria-label="Title"]').value).toBe('Fracture');
  await click(button(el, 'Save'));
  expect(tutorialsApi.update).toHaveBeenCalledWith('v1', expect.objectContaining({ sourceType: 'upload', title: 'Fracture' }), expect.any(Function));
  expect(onClose).toHaveBeenCalledWith(true);
});

test('editing a video can move it to another category', async () => {
  tutorialsApi.categories.mockResolvedValue([...CATS, { id: 'c2', name: 'Flood Preparedness', video_count: 0 }]);
  tutorialsApi.update.mockResolvedValue({});
  const el = await render({ video: FRACTURE, usedBytes: 0, onClose: jest.fn() });
  await change(el.querySelector('select[aria-label="Category"]'), 'c2');
  await click(button(el, 'Save'));
  expect(tutorialsApi.update).toHaveBeenCalledWith('v1', expect.objectContaining({ category: 'c2' }), expect.any(Function));
});

test('the batch category is locked while videos are sending', async () => {
  tutorialsApi.create.mockImplementation(() => new Promise(() => {}));
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 0, onClose: jest.fn() });
  await pickFiles(el, [file('one.mp4'), file('two.mp4')]);
  await click(button(el, 'Publish 2 videos'));
  expect(el.querySelector('select[aria-label="Category"]').disabled).toBe(true);
  expect(button(el, '+ New category').disabled).toBe(true);
  expect(button(el, 'Edit category').disabled).toBe(true);
  expect(button(el, 'Delete').disabled).toBe(true);
});

// Follows this form's own listener: earlier tests leave forms mid-upload on the page,
// so a beforeunload dispatched to window would be answered by theirs too
test('leaving the page mid-batch still warns until the uploads finish', async () => {
  let finish;
  tutorialsApi.create.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const add = jest.spyOn(window, 'addEventListener');
  const remove = jest.spyOn(window, 'removeEventListener');
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<AddVideosForm defaultCategoryId="c1" usedBytes={0} onClose={jest.fn()} />); });
  await pickFiles(el, [file('one.mp4')]);
  await click(button(el, 'Publish 1 video'));
  const [, warn] = add.mock.calls.find(([type]) => type === 'beforeunload');
  const event = new Event('beforeunload', { cancelable: true });
  warn(event);
  expect(event.defaultPrevented).toBe(true);
  await act(async () => { root.unmount(); });   // e.g. a navbar link inside the app
  expect(remove).not.toHaveBeenCalledWith('beforeunload', warn);
  await act(async () => { finish({ id: 'v1' }); });
  expect(remove).toHaveBeenCalledWith('beforeunload', warn);
  add.mockRestore();
  remove.mockRestore();
});
