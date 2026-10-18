/**
 * How an officer turns what they observed into a hazard polygon.
 *
 * Each hazard spreads in its own way — flood by low ground, landslide down a
 * slope, fire between neighbouring houses — so one freehand tool expresses
 * none of them well. This registry is where smarter methods get added, one
 * entry at a time.
 *
 * THE CONTRACT, which every method must keep:
 *
 *   generate(taps, context) -> [[lat, lng], ...]
 *                            | { corners: [[lat, lng], ...] | null, note }
 *                            | null
 *
 * A method turns what the officer gave it (a tap, a water depth, reports
 * already on file) into corners and returns them, optionally with a short
 * note for the officer. That is ALL it does. It never builds the publish
 * payload, never calls the API, never sets severity, and never decides who
 * gets alerted. The panel owns all of that.
 *
 * Keeping that line means every method ends as an ordinary polygon, so
 * alerts, barangay routing, grading, reports, reshaping, the duplicate check
 * and the Extreme approval hold all keep working without knowing which
 * method produced the shape. Break the contract and each of those has to
 * learn about every method separately.
 *
 * Returning null (or corners: null) means "I can't make a shape from this
 * yet" — not an error. The panel keeps showing the method's help.
 *
 * Every generated shape lands on the map as ordinary corners the officer
 * can drag before publishing: the system proposes, the officer decides.
 * All methods are rule-based (terrain arithmetic, geometry, records on
 * file). None of them is AI.
 *
 * `available(ctx)` keeps a method off the screen when the data behind it is
 * missing. `seed: true` means a tap on the map is the method's starting
 * point rather than a corner. The picker only appears once a hazard type has
 * more than one usable method.
 */

import { floodFromDepth } from '../../utils/terrain';
import { hullAround } from '../../utils/gridGeometry';

/** Tap corners directly. Always present, for every hazard type. */
export const HAND = 'hand';
export const FLOOD_DEPTH = 'flood-depth';
export const REPORTS = 'reports';
export const PAST = 'past';

// How far around each reported spot the zone reaches, in metres
export const REPORT_RADIUS_M = 40;

// Water depths an officer can tell by eye, in metres
export const DEPTH_PRESETS = [
  { label: 'Ankle', value: 0.15 },
  { label: 'Knee', value: 0.5 },
  { label: 'Waist', value: 1.0 },
  { label: 'Chest', value: 1.4 },
];

const METHODS = [
  {
    key: FLOOD_DEPTH,
    label: 'From water depth',
    help: 'Tap where you saw the water and pick how deep it was. The water is spread over the '
        + 'low ground around that spot: deeper water reaches further, and rising ground stops it. '
        + 'Tap again to move the spot; drag corners to fix the edge.',
    types: ['Flood'],
    seed: true,
    // Needs terrain.png in the hazard index
    available: (ctx) => Boolean(ctx.hasTerrain),
    generate: (taps, ctx) => {
      if (!taps.length) return null;
      return floodFromDepth(ctx.terrain, taps[taps.length - 1], ctx.depthM);
    },
  },
  {
    key: REPORTS,
    label: 'Around reported spots',
    help: 'Wraps the zone around where reporters pinned this hazard in the last three days. '
        + 'Drag corners to fix the edge.',
    types: null,
    seed: false,
    available: (ctx) => (ctx.reports || []).length > 0,
    generate: (taps, ctx) => {
      const spots = (ctx.reports || []).map((r) => [r.latitude, r.longitude]);
      if (!spots.length) return null;
      return {
        corners: hullAround(spots, REPORT_RADIUS_M),
        note: `Drawn around ${spots.length} reported spot${spots.length === 1 ? '' : 's'}, `
          + `${REPORT_RADIUS_M} m around each.`,
      };
    },
  },
  {
    key: HAND,
    label: 'Draw by hand',
    // Shown in the drawing card while this method is selected.
    help: 'Follow the edge of the affected area. Drag a corner to move it. '
        + 'Corners near a barangay line or the coast snap onto it; hold Alt '
        + 'to place one freely.',
    // null = offered for every hazard type
    types: null,
    seed: false,
    // The failsafe is never unavailable: if the data behind a smart method
    // is missing, the officer can always still draw.
    available: () => true,
    // The taps already are the corners, so there is nothing to generate.
    generate: null,
  },
  {
    key: PAST,
    label: 'Start from a past zone',
    help: 'Tap where the hazard is. The nearest past zone of this type is loaded as a starting '
        + 'shape; pick another below if a different one fits better, then drag corners to match today.',
    types: null,
    seed: true,
    available: () => true,
    generate: (taps, ctx) => {
      if (!taps.length) return null;
      const zone = (ctx.pastZones || [])[ctx.pastPick || 0];
      if (!zone) {
        return {
          corners: null,
          note: ctx.pastZones ? 'No past zone of this type within 600 m of that spot.' : 'Looking for past zones…',
        };
      }
      return { corners: zone.corners, note: null };
    },
  },

  // Next candidate: a landslide path traced downhill from the failure point,
  // using the slope already computed for the susceptibility layer.
];

const byKey = new Map(METHODS.map((m) => [m.key, m]));

/** The method with this key, or the hand-drawing failsafe. */
export function methodByKey(key) {
  return byKey.get(key) || byKey.get(HAND);
}

/**
 * Methods an officer can pick for this hazard type right now, in registry
 * order. Hand drawing is always among them.
 *
 * @param {string|undefined} typeName  'Flood' | 'Landslide' | 'Fire' | ...
 * @param {object} context             what the available() checks look at
 */
export function methodsFor(typeName, context = {}) {
  return METHODS.filter((m) => {
    if (m.types && (!typeName || !m.types.includes(typeName))) return false;
    return m.available(context);
  });
}

/**
 * The method a hazard type should open on: the first usable method in
 * registry order. Methods that build from evidence (terrain, reports) sit
 * above hand drawing; "start from a past zone" sits below it, so it is
 * offered but never chosen for the officer.
 */
export function defaultMethodFor(typeName, context = {}) {
  const usable = methodsFor(typeName, context);
  return (usable[0] || byKey.get(HAND)).key;
}

/** Normalise what generate() returned into { corners, note }. */
export function runMethod(method, taps, context) {
  if (!method?.generate) return { corners: null, note: null };
  const out = method.generate(taps, context);
  if (!out) return { corners: null, note: null };
  if (Array.isArray(out)) return { corners: out, note: null };
  return { corners: out.corners || null, note: out.note || null };
}
