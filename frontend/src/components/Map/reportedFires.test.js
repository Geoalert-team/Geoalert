import { awaitingDrrmo, reportSpots } from './reportedFires';

const report = (extra = {}) => ({
  id: 'r1', status: 'Pending', hazard_zone: null, latitude: null, longitude: null, puroks: [], ...extra,
});

test('a pin at every purok the report names', () => {
  const spots = reportSpots(report({
    latitude: 10.25, longitude: 123.83,
    puroks: [{ id: 4, name: 'Purok Ilang-Ilang', lat: 10.251, lng: 123.831 }, { id: 5, name: 'Sitio Bato', lat: 10.252, lng: 123.832 }],
  }));
  expect(spots).toEqual([
    { key: 'r1-4', position: [10.251, 123.831], place: 'Purok Ilang-Ilang' },
    { key: 'r1-5', position: [10.252, 123.832], place: 'Sitio Bato' },
  ]);
});

test('the dropped pin when the report names no purok', () => {
  expect(reportSpots(report({ latitude: 10.25, longitude: 123.83 })))
    .toEqual([{ key: 'r1', position: [10.25, 123.83], place: null }]);
});

test('no spot when the report has neither', () => {
  expect(reportSpots(report())).toEqual([]);
  expect(reportSpots(report({ puroks: [{ id: 4, name: 'No pin', lat: null, lng: null }] }))).toEqual([]);
});

test('only a pending report with no zone is waiting for DRRMO', () => {
  expect(awaitingDrrmo(report())).toBe(true);
  expect(awaitingDrrmo(report({ hazard_zone: 'z1' }))).toBe(false);
  expect(awaitingDrrmo(report({ status: 'Validated' }))).toBe(false);
  expect(awaitingDrrmo(report({ status: 'Rejected' }))).toBe(false);
});
