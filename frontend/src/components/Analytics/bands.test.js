import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ActivityBand from './ActivityBand';
import ResponseBand from './ResponseBand';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

function render(node) {
  const el = document.createElement('div');
  act(() => { createRoot(el).render(node); });
  return el;
}

const kpis = {
  active_zones_now: 4, zones_published: 66, zones_retracted: 2, alerts_issued: 87, extreme_alerts: 16,
  incidents_submitted: 146, incidents_pending: 6, incidents_validated: 104, incidents_rejected: 29,
  recorded_events: 34, notices_sent: 1914, notices_read: 1225, read_rate: 0.64, review_rate: 0.91,
  median_minutes_to_read: 47, median_minutes_to_review: 185, median_minutes_zone_active: 3260,
};
const monthly = [
  { month: '2026-08', zones: 2, alerts: 3, incidents: 5, events: 1 },
  { month: '2026-09', zones: 9, alerts: 12, incidents: 19, events: 5 },
];

test('activity: five tiles, a trend on the four period counts, hints as before', () => {
  const el = render(<ActivityBand kpis={kpis} monthly={monthly} />);
  expect(el.querySelectorAll('.db-stat')).toHaveLength(5);
  expect(el.querySelectorAll('svg.an-spark')).toHaveLength(4);
  expect(el.textContent).toContain('Active zones now');
  expect(el.textContent).toContain('2 more withdrawn as errors');
  expect(el.textContent).toContain('16 Extreme');
  expect(el.textContent).toContain('6 still pending');
});

test('activity: no pending reports reads "none pending"', () => {
  const el = render(<ActivityBand kpis={{ ...kpis, incidents_pending: 0 }} monthly={monthly} />);
  expect(el.textContent).toContain('none pending');
});

test('response: two meters with their counts', () => {
  const el = render(<ResponseBand kpis={kpis} />);
  const meters = el.querySelectorAll('[role="meter"]');
  expect(meters).toHaveLength(2);
  expect(meters[0].getAttribute('aria-valuenow')).toBe('64');
  expect(el.textContent).toContain('1,225 of 1,914 sent');
  expect(el.textContent).toContain('104 validated, 29 rejected');
  expect(el.textContent).toContain('3 h 5 min');
});

test('response: nothing sent or submitted shows dashes and says why', () => {
  const el = render(<ResponseBand kpis={{ ...kpis, read_rate: null, review_rate: null }} />);
  expect(el.querySelectorAll('[role="meter"]')).toHaveLength(0);
  expect(el.textContent).toContain('None sent in this period');
  expect(el.textContent).toContain('None submitted in this period');
  expect(el.textContent).not.toContain('NaN');
});
