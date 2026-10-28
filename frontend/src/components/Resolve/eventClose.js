// What resolving a flood or landslide asks, checks and sends: one row of the
// flood and landslide log, the way closing a fire is one row of the BFP fire
// log. The sub category (column H, from the log's list for the hazard type),
// the cause or weather system (I), injured, fatalities, families and persons
// affected (J-M) and what happened (N). The server checks the same rules with
// the same words (apps/history/flood_landslide.py close_fields).
//
// Blank means not counted, never 0: a count nobody has yet stays null in the
// record, so an uncounted flood doesn't read as one nobody was hurt in.

export const COUNTS = [
  { key: 'injured', label: 'Injured' },
  { key: 'fatalities', label: 'Fatalities' },
  { key: 'families_affected', label: 'Families affected' },
  { key: 'persons_affected', label: 'Persons affected' },
];
export const CAUSE_MAX = 200;

const WHOLE = /^\d+$/;
const blank = (v) => v === null || v === undefined || String(v).trim() === '';
// As the server reads text: runs of spaces are one space
const squeeze = (v) => String(v || '').replace(/\s+/g, ' ').trim();

export function emptyEventFigures() {
  return {
    hazard_subcategory: '', cause: '', summary: '',
    ...Object.fromEntries(COUNTS.map(({ key }) => [key, ''])),
  };
}

// The log's sub categories for this hazard type (its name), or [] for a type
// it has no list for, which is then not asked for one
export function subcategoriesFor(options, hazardType) {
  const lists = options?.subcategories || {};
  const name = Object.keys(lists).find((k) => k.toLowerCase() === String(hazardType || '').toLowerCase());
  return name ? lists[name] : [];
}

export function eventFiguresErrors(form, choices) {
  const e = {};
  if (choices.length && !choices.includes(form.hazard_subcategory)) e.hazard_subcategory = 'Choose the sub category.';
  if (squeeze(form.cause).length > CAUSE_MAX) e.cause = `Keep the cause under ${CAUSE_MAX} characters.`;
  COUNTS.forEach(({ key }) => {
    if (!blank(form[key]) && !WHOLE.test(String(form[key]).trim())) e[key] = 'Enter a whole number, 0 or more.';
  });
  return e;
}

// What hazardsApi.update is given to resolve the zone
export function eventFiguresPayload(form) {
  const count = (v) => (blank(v) ? null : Number(String(v).trim()));
  return {
    status: 'Resolved',
    hazard_subcategory: form.hazard_subcategory,
    cause: squeeze(form.cause),
    ...Object.fromEntries(COUNTS.map(({ key }) => [key, count(form[key])])),
    summary: form.summary.trim(),
  };
}
