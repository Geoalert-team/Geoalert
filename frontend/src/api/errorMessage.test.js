import { errorMessage } from './errorMessage';

const res = (status, data) => ({ response: { status, data } });

test('uses the server message when there is one', () => {
  expect(errorMessage(res(400, { error: 'This hazard has already been withdrawn.' })))
    .toBe('This hazard has already been withdrawn.');
});

test('uses DRF detail', () => {
  expect(errorMessage(res(403, { detail: 'Authentication credentials were not provided.' })))
    .toBe('Authentication credentials were not provided.');
});

test('uses the first field error from a validation body', () => {
  expect(errorMessage(res(400, { geometry: ['The outlined area is entirely outside Talisay City.'] })))
    .toBe('The outlined area is entirely outside Talisay City.');
});

test('never shows axios text for an HTML 500 page', () => {
  const msg = errorMessage({ message: 'Request failed with status code 500', ...res(500, '<!DOCTYPE html>...') });
  expect(msg).not.toMatch(/status code/);
  expect(msg).toMatch(/server/);
});

test('explains a busy database', () => {
  expect(errorMessage(res(503, ''))).toMatch(/busy/);
});

test('explains being offline', () => {
  expect(errorMessage({ message: 'Network Error' })).toMatch(/Can't reach the GeoAlert Talisay server/);
});
