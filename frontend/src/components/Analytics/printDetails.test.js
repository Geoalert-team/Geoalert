import React, { act, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import usePrintOpensDetails from './usePrintOpensDetails';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

function Panel() {
  const ref = useRef(null);
  usePrintOpensDetails(ref);
  return (
    <div ref={ref}>
      <details id="closed"><summary>Numbers</summary><table /></details>
      <details id="already" open><summary>Figures</summary><table /></details>
    </div>
  );
}

test('printing opens every closed table, then puts them back', () => {
  const el = document.createElement('div');
  act(() => { createRoot(el).render(<Panel />); });
  const closed = el.querySelector('#closed');
  const already = el.querySelector('#already');

  act(() => { window.dispatchEvent(new Event('beforeprint')); });
  expect(closed.open).toBe(true);

  act(() => { window.dispatchEvent(new Event('afterprint')); });
  expect(closed.open).toBe(false);
  expect(already.open).toBe(true);
});
