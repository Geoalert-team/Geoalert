import { activeAlerts, alertKey, placesText, unseenAlerts } from './hazardAlerts';

const zone = (id, props) => ({ type: 'Feature', id, geometry: null, properties: { status: 'Active', ...props } });

test('worst severity first, then newest first', () => {
  const alerts = activeAlerts({
    type: 'FeatureCollection',
    features: [
      zone('a', { severity: 'Green', activated_at: '2026-10-26T09:00:00Z' }),
      zone('b', { severity: 'Orange', activated_at: '2026-10-26T08:00:00Z' }),
      zone('c', { severity: 'Red', activated_at: '2026-10-25T08:00:00Z' }),
      zone('d', { severity: 'Orange', activated_at: '2026-10-26T10:00:00Z' }),
    ],
  });
  expect(alerts.map((a) => a.id)).toEqual(['c', 'd', 'b', 'a']);
});

test('names every barangay the zone reaches, else the one it is filed under', () => {
  const [reaching, filed] = activeAlerts({
    features: [
      zone('a', {
        severity: 'Red',
        barangay_name: 'Bulacao',
        verifications: [{ barangay_name: 'Bulacao' }, { barangay_name: 'Pooc' }, { barangay_name: 'Pooc' }],
      }),
      zone('b', { severity: 'Orange', barangay_name: 'Lawaan I', verifications: [] }),
    ],
  });
  expect(reaching.barangays).toEqual(['Bulacao', 'Pooc']);
  expect(filed.barangays).toEqual(['Lawaan I']);
});

test('skips zones that are not Active, and reads the id from properties too', () => {
  const alerts = activeAlerts({
    features: [
      zone('a', { severity: 'Red', status: 'Resolved' }),
      { type: 'Feature', properties: { id: 'b', status: 'Active', severity: 'Green', is_sample: true } },
    ],
  });
  expect(alerts).toHaveLength(1);
  expect(alerts[0]).toMatchObject({ id: 'b', type: 'Hazard', sample: true });
});

test('no feed, no alerts', () => {
  expect(activeAlerts(null)).toEqual([]);
  expect(activeAlerts({ results: { features: [] } })).toEqual([]);
});

test('an alert is new until seen, and new again when its severity changes', () => {
  const moderate = { id: 'a', severity: 'Orange' };
  const other = { id: 'b', severity: 'Green' };
  expect(unseenAlerts([moderate, other], [])).toEqual([moderate, other]);
  expect(unseenAlerts([moderate, other], [alertKey(moderate)])).toEqual([other]);
  const raised = { id: 'a', severity: 'Red' };
  expect(unseenAlerts([raised], [alertKey(moderate)])).toEqual([raised]);
});

test('placesText lists a few places, then counts the rest', () => {
  expect(placesText([])).toBe('Talisay City');
  expect(placesText(['Bulacao'])).toBe('Bulacao');
  expect(placesText(['Bulacao', 'Pooc'])).toBe('Bulacao and Pooc');
  expect(placesText(['Bulacao', 'Pooc', 'Lagtang'])).toBe('Bulacao, Pooc and Lagtang');
  expect(placesText(['Bulacao', 'Pooc', 'Lagtang', 'Tabunok'])).toBe('Bulacao, Pooc and 2 more');
});
