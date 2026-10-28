import {
  emptyEventFigures, eventFiguresErrors, eventFiguresPayload, subcategoriesFor,
} from './eventClose';

const OPTIONS = {
  subcategories: { Flood: ['RIVER OVERFLOW', 'FLASH FLOOD'], Landslide: ['ROAD LANDSLIDE'] },
};
const FLOOD = OPTIONS.subcategories.Flood;
const OK = { ...emptyEventFigures(), hazard_subcategory: 'RIVER OVERFLOW' };

test('each hazard type gets its own sub categories, and a type with no list gets none', () => {
  expect(subcategoriesFor(OPTIONS, 'flood')).toEqual(FLOOD);
  expect(subcategoriesFor(OPTIONS, 'Landslide')).toEqual(['ROAD LANDSLIDE']);
  expect(subcategoriesFor(OPTIONS, 'Earthquake')).toEqual([]);
  expect(subcategoriesFor(null, 'Flood')).toEqual([]);
});

test('a complete form has no errors, with every count left blank', () => {
  expect(eventFiguresErrors(OK, FLOOD)).toEqual({});
});

test('the same checks and words as the server', () => {
  expect(eventFiguresErrors({ ...OK, hazard_subcategory: '' }, FLOOD).hazard_subcategory)
    .toBe('Choose the sub category.');
  expect(eventFiguresErrors({ ...OK, hazard_subcategory: 'ROAD LANDSLIDE' }, FLOOD).hazard_subcategory)
    .toBe('Choose the sub category.');
  expect(eventFiguresErrors({ ...OK, injured: '-1' }, FLOOD).injured).toBe('Enter a whole number, 0 or more.');
  expect(eventFiguresErrors({ ...OK, persons_affected: '2.5' }, FLOOD).persons_affected)
    .toBe('Enter a whole number, 0 or more.');
  expect(eventFiguresErrors({ ...OK, cause: 'x'.repeat(201) }, FLOOD).cause)
    .toBe('Keep the cause under 200 characters.');
});

test('a type with no list is not asked for a sub category', () => {
  expect(eventFiguresErrors(emptyEventFigures(), [])).toEqual({});
});

test('payload resolves the zone; blank counts are null, zero stays zero', () => {
  expect(eventFiguresPayload({
    ...OK, cause: '  Heavy   rain ', injured: '0', fatalities: ' 2 ', summary: ' Knee-deep. ',
  })).toEqual({
    status: 'Resolved', hazard_subcategory: 'RIVER OVERFLOW', cause: 'Heavy rain',
    injured: 0, fatalities: 2, families_affected: null, persons_affected: null, summary: 'Knee-deep.',
  });
});
