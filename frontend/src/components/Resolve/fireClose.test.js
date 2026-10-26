import {
  COUNT_FIELDS, bfpLabel, emptyFigures, figuresErrors, figuresPayload, groupTotal, withCategory,
} from './fireClose';

const OPTIONS = {
  property_types: { RESIDENTIAL: ['SINGLE AND TWO FAMILY DWELLING'], NON_STRUCTURAL: ['RUBBISH', 'GRASS'] },
  alarm_levels: ['1ST ALARM', '2ND ALARM'],
};
const OK = {
  ...emptyFigures(), alarm_level: '1ST ALARM', property_category: 'RESIDENTIAL',
  property_subcategory: 'SINGLE AND TWO FAMILY DWELLING',
};

test('a complete form has no errors, with every count left blank', () => {
  expect(figuresErrors(OK, OPTIONS)).toEqual({});
});

test('the same checks and words as the server', () => {
  expect(figuresErrors({ ...OK, alarm_level: '' }, OPTIONS).alarm_level).toBe('Choose the alarm level.');
  expect(figuresErrors({ ...OK, property_subcategory: 'GRASS' }, OPTIONS).property_subcategory)
    .toBe('Choose the property type.');
  expect(figuresErrors({ ...OK, injured_ff_male: '-1' }, OPTIONS).injured_ff_male).toBe('Enter a whole number, 0 or more.');
  expect(figuresErrors({ ...OK, fatal_civ_female: '1.5' }, OPTIONS).fatal_civ_female).toBe('Enter a whole number, 0 or more.');
  expect(figuresErrors({ ...OK, structures_affected: 'two' }, OPTIONS).structures_affected)
    .toBe('Enter a whole number, 0 or more.');
  expect(figuresErrors({ ...OK, damage_cost: 'x' }, OPTIONS).damage_cost).toBe('Enter an amount in pesos, 0 or more.');
  expect(figuresErrors({ ...OK, damage_cost: '-5' }, OPTIONS).damage_cost).toBe('Enter an amount in pesos, 0 or more.');
  expect(figuresErrors({ ...OK, damage_cost: '75,000.50' }, OPTIONS)).toEqual({});
});

test('payload keeps blanks as null, never 0', () => {
  const p = figuresPayload({ ...OK, injured_civ_male: '2', fatal_ff_male: '0', damage_cost: '75,000' });
  expect(p).toMatchObject({
    injured_civ_male: 2, fatal_ff_male: 0, injured_ff_male: null, structures_affected: null,
    damage_cost: 75000, alarm_level: '1ST ALARM',
  });
  COUNT_FIELDS.forEach((k) => expect(p).toHaveProperty(k));
  expect(p).not.toHaveProperty('summary'); // described by its BFP figures instead
});

test('a group total adds what is filled in, and stays blank when nothing is', () => {
  expect(groupTotal({ ...OK, injured_ff_male: '2', injured_ff_female: '1' }, ['injured_ff_male', 'injured_ff_female'])).toBe(3);
  expect(groupTotal({ ...OK, injured_ff_male: '0' }, ['injured_ff_male', 'injured_ff_female'])).toBe(0);
  expect(groupTotal(OK, ['injured_ff_male', 'injured_ff_female'])).toBe('');
});

test('choosing a category keeps a sub category only if it belongs, and picks the only one', () => {
  expect(withCategory({ ...OK, property_subcategory: 'GRASS' }, 'RESIDENTIAL', OPTIONS).property_subcategory)
    .toBe('SINGLE AND TWO FAMILY DWELLING');
  expect(withCategory(OK, 'NON_STRUCTURAL', OPTIONS)).toMatchObject({ property_category: 'NON_STRUCTURAL', property_subcategory: '' });
});

test('BFP codes read as the log writes them, without underscores', () => {
  expect(bfpLabel('NON_RESIDENTIAL')).toBe('NON RESIDENTIAL');
  expect(bfpLabel('1ST ALARM')).toBe('1ST ALARM');
});
