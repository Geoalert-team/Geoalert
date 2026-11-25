import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import LayerControl from './LayerControl';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const TYPES = [{ name: 'Flood', active_count: 2, severity_counts: { Red: 1, Orange: 1 } }];

function render(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  act(() => {
    createRoot(el).render(
      <LayerControl types={TYPES} active={new Set(['Flood'])} onToggle={() => {}} onAll={() => {}}
        onNone={() => {}} {...props} />,
    );
  });
  return el;
}
const purokBox = (el) => el.querySelector('#pm-layer-puroks');

describe('LayerControl purok outlines', () => {
  test('shows a ticked box that calls back when changed', () => {
    const onTogglePuroks = jest.fn();
    const el = render({ showPuroks: true, onTogglePuroks });
    expect(purokBox(el).checked).toBe(true);
    act(() => { purokBox(el).click(); });
    expect(onTogglePuroks).toHaveBeenCalledTimes(1);
  });

  test('never calls the lines estimates', () => {
    const el = render({ showPuroks: true, onTogglePuroks: () => {} });
    expect(el.textContent).not.toMatch(/estimat|official/i);
  });

  test('says how to see them, since they only show inside a selected barangay', () => {
    const el = render({ showPuroks: true, onTogglePuroks: () => {} });
    expect(el.textContent).toContain('Select a barangay to see its puroks');
  });

  test('is still there when no hazard layers are available', () => {
    const el = render({ types: [], showPuroks: false, onTogglePuroks: () => {} });
    expect(purokBox(el)).not.toBeNull();
    expect(purokBox(el).checked).toBe(false);
  });

  test('is left out when the map gives no way to toggle it', () => {
    expect(purokBox(render({}))).toBeNull();
  });
});
