import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import GuidanceEditor from './GuidanceEditor';
import { guidanceApi } from '../../api/guidanceApi';

jest.mock('../../api/guidanceApi', () => ({
  guidanceApi: { create: jest.fn(), update: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

async function mount(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<GuidanceEditor hazardTypeId={1} phase="Before" onSaved={jest.fn()} onCancel={jest.fn()} {...props} />); });
  return el;
}
// React listens for 'input' with the native value setter, as a person typing does
async function type(input, value) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
const button = (el, name) => [...el.querySelectorAll('button')].find((b) => (b.getAttribute('aria-label') || b.textContent) === name);
const click = (b) => act(async () => { b.click(); });
const stepBoxes = (el) => [...el.querySelectorAll('textarea')];

test('a new article is saved for the hazard and phase being viewed', async () => {
  guidanceApi.create.mockResolvedValue({ id: 'n1' });
  const onSaved = jest.fn();
  const el = await mount({ onSaved });
  await type(el.querySelector('input'), 'Prepare your home');
  await type(stepBoxes(el)[0], 'Move valuables upstairs');
  await click(button(el, '+ Add step'));
  await type(stepBoxes(el)[1], '  Clear drains  ');
  await click(button(el, 'Save'));
  expect(guidanceApi.create).toHaveBeenCalledWith({
    hazard_type: 1, title: 'Prepare your home', body: 'Move valuables upstairs\nClear drains', timeline_phase: 'Before',
  });
  expect(onSaved).toHaveBeenCalled();
});

test('editing starts from the article and saves its new title and step order', async () => {
  guidanceApi.update.mockResolvedValue({});
  const el = await mount({ article: { id: 'a1', title: 'Old title', body: 'First\nSecond' } });
  expect(el.querySelector('input').value).toBe('Old title');
  expect(stepBoxes(el).map((t) => t.value)).toEqual(['First', 'Second']);
  await type(el.querySelector('input'), 'New title');
  await click(button(el, 'Move step 2 up'));
  await click(button(el, 'Save'));
  expect(guidanceApi.update).toHaveBeenCalledWith('a1', { title: 'New title', body: 'Second\nFirst' });
});

test('a step can be removed, but one box always stays', async () => {
  const el = await mount({ article: { id: 'a1', title: 'T', body: 'Only step' } });
  await click(button(el, 'Remove step 1'));
  expect(stepBoxes(el)).toHaveLength(1);
  expect(stepBoxes(el)[0].value).toBe('');
});

test('a title and at least one step are required', async () => {
  const el = await mount({});
  await click(button(el, 'Save'));
  expect(el.textContent).toContain('Add a title.');
  await type(el.querySelector('input'), 'Title');
  await click(button(el, 'Save'));
  expect(el.textContent).toContain('Add at least one step.');
  expect(guidanceApi.create).not.toHaveBeenCalled();
});

test('a refused save says why, and the form stays open to try again', async () => {
  guidanceApi.create.mockRejectedValue(Object.assign(new Error('Forbidden'), { status: 403 }));
  const onSaved = jest.fn();
  const el = await mount({ onSaved });
  await type(el.querySelector('input'), 'Title');
  await type(stepBoxes(el)[0], 'Step');
  await click(button(el, 'Save'));
  expect(el.textContent).toContain('Only DRRMO Officers and Admins can edit guidance. Try logging in again.');
  expect(onSaved).not.toHaveBeenCalled();
  expect(button(el, 'Save').disabled).toBe(false);
});

test('Cancel leaves without saving', async () => {
  const onCancel = jest.fn();
  const el = await mount({ onCancel });
  await click(button(el, 'Cancel'));
  expect(onCancel).toHaveBeenCalled();
  expect(guidanceApi.create).not.toHaveBeenCalled();
});
