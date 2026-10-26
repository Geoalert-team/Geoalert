// What closing a fire asks, checks and sends: the BFP fire log's columns G
// to W. Property type (G-H), injured and fatalities by firefighter and
// civilian, male and female (I-T), estimated damage (U), affected structures
// (V) and the alarm level (W). The server checks the same rules with the
// same words (apps/history/bfp.py close_fields).
//
// Blank means not counted, never 0: a count nobody has yet stays null in the
// record, so an uncounted fire doesn't read as a fire nobody was hurt in.
// There is no written summary: the record is described by its BFP figures
// ("BFP: RESIDENTIAL – SINGLE AND TWO FAMILY DWELLING, 1ST ALARM").

export const INJURED = {
  firefighter: ['injured_ff_male', 'injured_ff_female'],
  civilian: ['injured_civ_male', 'injured_civ_female'],
};
export const FATALITIES = {
  firefighter: ['fatal_ff_male', 'fatal_ff_female'],
  civilian: ['fatal_civ_male', 'fatal_civ_female'],
};
export const COUNT_FIELDS = [
  ...INJURED.firefighter, ...INJURED.civilian, ...FATALITIES.firefighter, ...FATALITIES.civilian,
];

const WHOLE = /^\d+$/;
const blank = (v) => v === null || v === undefined || String(v).trim() === '';
const pesos = (v) => Number(String(v).replace(/,/g, '').trim());

export function emptyFigures() {
  const counts = Object.fromEntries(COUNT_FIELDS.map((k) => [k, '']));
  return {
    property_category: '', property_subcategory: '', ...counts,
    damage_cost: '', structures_affected: '', alarm_level: '',
  };
}

// "NON_RESIDENTIAL" -> "NON RESIDENTIAL"; otherwise as the BFP log writes it
export function bfpLabel(code) {
  return String(code || '').replace(/_/g, ' ');
}

// A new category keeps the sub category only if it belongs to it, and
// picks the only one when there is just one (RESIDENTIAL)
export function withCategory(form, category, options) {
  const subs = options?.property_types?.[category] || [];
  let sub = subs.includes(form.property_subcategory) ? form.property_subcategory : '';
  if (!sub && subs.length === 1) [sub] = subs;
  return { ...form, property_category: category, property_subcategory: sub };
}

// The sum of a group's filled-in counts, or '' when none is filled in
export function groupTotal(form, fields) {
  const known = fields.map((k) => form[k]).filter((v) => !blank(v) && WHOLE.test(String(v).trim()));
  return known.length ? known.reduce((sum, v) => sum + Number(v), 0) : '';
}

export function figuresErrors(form, options) {
  const e = {};
  if (!(options?.alarm_levels || []).includes(form.alarm_level)) e.alarm_level = 'Choose the alarm level.';
  if (!(options?.property_types?.[form.property_category] || []).includes(form.property_subcategory)) {
    e.property_subcategory = 'Choose the property type.';
  }
  [...COUNT_FIELDS, 'structures_affected'].forEach((k) => {
    if (!blank(form[k]) && !WHOLE.test(String(form[k]).trim())) e[k] = 'Enter a whole number, 0 or more.';
  });
  if (!blank(form.damage_cost)) {
    const amount = pesos(form.damage_cost);
    if (!Number.isFinite(amount) || amount < 0) e.damage_cost = 'Enter an amount in pesos, 0 or more.';
  }
  return e;
}

// What hazardsApi.closeFire is given
export function figuresPayload(form) {
  const count = (v) => (blank(v) ? null : Number(String(v).trim()));
  return {
    property_category: form.property_category,
    property_subcategory: form.property_subcategory,
    ...Object.fromEntries(COUNT_FIELDS.map((k) => [k, count(form[k])])),
    structures_affected: count(form.structures_affected),
    damage_cost: blank(form.damage_cost) ? null : pesos(form.damage_cost),
    alarm_level: form.alarm_level,
  };
}
