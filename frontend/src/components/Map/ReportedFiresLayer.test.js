import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import ReportedFiresLayer from './ReportedFiresLayer';
import { reportsApi } from '../../api/reportApi';

const mockMap = { setView: jest.fn(), getZoom: () => 13 };
jest.mock('react-leaflet', () => {
  const R = require('react');
  return {
    Marker: R.forwardRef(({ children, title }, ref) => {
      R.useImperativeHandle(ref, () => ({ openPopup: () => {} }));
      return <div className="marker" title={title}>{children}</div>;
    }),
    Popup: ({ children }) => <div className="popup">{children}</div>,
    useMap: () => mockMap,
  };
});
jest.mock('../../api/reportApi', () => ({ reportsApi: { pendingFires: jest.fn() } }));

const REPORTS = [
  { id: 'r1', status: 'Pending', hazard_zone: null, description: 'Smoke behind the chapel',
    barangay_details: { name: 'Linao' }, created_at: new Date().toISOString(), latitude: null, longitude: null,
    puroks: [{ id: 7, name: 'Purok Mahogany', lat: 10.24, lng: 123.85 }] },
  // Already put on the map by DRRMO: not a reported pin
  { id: 'r2', status: 'Pending', hazard_zone: 'z9', barangay_details: { name: 'Tabunok' },
    created_at: new Date().toISOString(), latitude: 10.25, longitude: 123.84, puroks: [] },
  // No place at all: nothing to pin
  { id: 'r3', status: 'Pending', hazard_zone: null, barangay_details: { name: 'Pooc' },
    created_at: new Date().toISOString(), latitude: null, longitude: null, puroks: [] },
];

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  mockMap.setView = jest.fn();
  reportsApi.pendingFires.mockImplementation(() => Promise.resolve(REPORTS));
});

async function render(props = {}) {
  const el = document.createElement('div');
  await act(async () => {
    createRoot(el).render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ReportedFiresLayer {...props} />
    </MemoryRouter>);
  });
  return el;
}

test('asks for the last day of pending fire reports and pins only those waiting for DRRMO', async () => {
  const onCount = jest.fn();
  const el = await render({ onCount });
  expect(reportsApi.pendingFires).toHaveBeenCalledWith(24);
  const markers = [...el.querySelectorAll('.marker')];
  expect(markers.map((m) => m.title)).toEqual(['Reported fire, not confirmed: Purok Mahogany, Linao']);
  expect(onCount).toHaveBeenLastCalledWith(1);
  expect(el.textContent).toContain("residents haven't been alerted");
  expect([...el.querySelectorAll('a')].map((a) => a.textContent)).toEqual(['Open dashboard']);
});

test('a report link zooms to its pin and says it was found', async () => {
  const onFocused = jest.fn();
  await render({ focusId: 'r1', onFocused });
  expect(mockMap.setView).toHaveBeenCalledWith([10.24, 123.85], 17);
  expect(onFocused).toHaveBeenCalledWith(true);
});

test('a link to a report DRRMO already decided says it is no longer waiting', async () => {
  const onFocused = jest.fn();
  await render({ focusId: 'r2', onFocused });
  expect(mockMap.setView).not.toHaveBeenCalled();
  expect(onFocused).toHaveBeenCalledWith(false);
});
