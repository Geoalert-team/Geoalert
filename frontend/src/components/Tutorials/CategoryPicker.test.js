import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import CategoryPicker from './CategoryPicker';
import { tutorialsApi } from '../../api/tutorialsApi';

jest.mock('../../api/tutorialsApi', () => ({
  tutorialsApi: { createCategory: jest.fn(), updateCategory: jest.fn(), removeCategory: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

async function render(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<CategoryPicker {...props} />); });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);
const inDialog = (el, text) => [...el.querySelector('[role="dialog"]').querySelectorAll('button')].find((b) => b.textContent === text);
const click = (b) => act(async () => { b.click(); });
// React listens for 'input' with the native value setter, as a person typing does
async function type(input, value) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
async function change(select, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
  await act(async () => { setter.call(select, value); select.dispatchEvent(new Event('change', { bubbles: true })); });
}

const CATS = [
  { id: 'c2', name: 'Drills', description: '', video_count: 0 },
  { id: 'c1', name: 'First Aid', description: 'Bandaging basics', video_count: 10 },
];
const WARNING = "Are you sure you want to delete 'First Aid'? This action is permanent and will automatically delete all videos contained within this category.";

test('lists the categories and selects one', async () => {
  const onChange = jest.fn();
  const el = await render({ categories: CATS, value: null, onChange, onChanged: jest.fn() });
  expect([...el.querySelectorAll('option')].map((o) => o.textContent)).toEqual(['Choose a category', 'Drills', 'First Aid']);
  await change(el.querySelector('select'), 'c1');
  expect(onChange).toHaveBeenCalledWith('c1');
});

test('creates a category with a description and selects it', async () => {
  tutorialsApi.createCategory.mockResolvedValue({ id: 'c3', name: 'Typhoon Response', description: 'Before, during and after', video_count: 0 });
  const onChange = jest.fn(); const onChanged = jest.fn();
  const el = await render({ categories: CATS, value: null, onChange, onChanged });
  await click(button(el, '+ New category'));
  await type(el.querySelector('[aria-label="New category name"]'), 'Typhoon Response');
  await type(el.querySelector('[aria-label="Category description"]'), 'Before, during and after');
  await click(button(el, 'Create'));
  expect(tutorialsApi.createCategory).toHaveBeenCalledWith({ name: 'Typhoon Response', description: 'Before, during and after' });
  expect(onChange).toHaveBeenCalledWith('c3');
  expect(onChanged).toHaveBeenCalled();
});

test("shows the server's message when a name is taken", async () => {
  tutorialsApi.createCategory.mockRejectedValue(new Error('There is already a category called First Aid.'));
  const el = await render({ categories: CATS, value: null, onChange: jest.fn(), onChanged: jest.fn() });
  await click(button(el, '+ New category'));
  await type(el.querySelector('[aria-label="New category name"]'), 'first aid');
  await click(button(el, 'Create'));
  expect(el.querySelector('[role="alert"]').textContent).toBe('There is already a category called First Aid.');
});

test('edits the chosen category, starting from its name and description', async () => {
  tutorialsApi.updateCategory.mockResolvedValue({});
  const onChanged = jest.fn();
  const el = await render({ categories: CATS, value: 'c1', onChange: jest.fn(), onChanged });
  await click(button(el, 'Edit category'));
  expect(el.querySelector('[aria-label="Category name"]').value).toBe('First Aid');
  expect(el.querySelector('[aria-label="Category description"]').value).toBe('Bandaging basics');
  await type(el.querySelector('[aria-label="Category description"]'), 'Bandaging, bleeding and slings');
  await click(button(el, 'Save'));
  expect(tutorialsApi.updateCategory).toHaveBeenCalledWith('c1', { name: 'First Aid', description: 'Bandaging, bleeding and slings' });
  expect(onChanged).toHaveBeenCalled();
});

test('a category with videos can be deleted, after the warning', async () => {
  tutorialsApi.removeCategory.mockResolvedValue({});
  const onChange = jest.fn(); const onChanged = jest.fn();
  const el = await render({ categories: CATS, value: 'c1', onChange, onChanged });
  await click(button(el, 'Delete'));
  expect(el.querySelector('.adm-confirm-text').textContent).toBe(WARNING);
  await click(inDialog(el, 'Cancel'));
  expect(el.querySelector('[role="dialog"]')).toBeNull();
  expect(tutorialsApi.removeCategory).not.toHaveBeenCalled();
  await click(button(el, 'Delete'));
  await click(inDialog(el, 'Delete'));
  expect(tutorialsApi.removeCategory).toHaveBeenCalledWith('c1');
  expect(onChange).toHaveBeenLastCalledWith(null);
  expect(onChanged).toHaveBeenCalled();
});
