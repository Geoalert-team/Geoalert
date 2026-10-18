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
 *   generate(taps, context) -> [[lat, lng], ...] | null
 *
 * A method turns the officer's taps into corners and returns them. That is
 * ALL it does. It never builds the publish payload, never calls the API,
 * never sets severity, and never decides who gets alerted. The panel owns
 * all of that.
 *
 * Keeping that line means every method ends as an ordinary polygon, so
 * alerts, barangay routing, grading, reports, reshaping, the duplicate check
 * and the Extreme approval hold all keep working without knowing which
 * method produced the shape. Break the contract and each of those has to
 * learn about every method separately.
 *
 * Returning null means "I can't make a shape from these taps yet" — not an
 * error. The panel keeps showing the drawing help until a shape appears.
 *
 * `available()` keeps a half-finished method off an officer's screen. The
 * picker only appears once a hazard type has more than one method, so adding
 * the first smart method is what makes it visible.
 */

/** Tap corners directly. Always present, for every hazard type. */
export const HAND = 'hand';

const METHODS = [
  {
    key: HAND,
    label: 'Draw by hand',
    // Shown in the drawing card while this method is selected.
    help: 'Follow the edge of the affected area. Drag a corner to move it. '
        + 'Corners near a barangay line or the coast snap onto it; hold Alt '
        + 'to place one freely.',
    // null = offered for every hazard type
    types: null,
    // The failsafe is never unavailable: if the data behind a smart method
    // is missing, the officer can always still draw.
    available: () => true,
    // The taps already are the corners, so there is nothing to generate.
    generate: null,
  },

  // Smart methods get added here. Sketch of the next one, for reference:
  //
  // {
  //   key: 'slide-path',
  //   label: 'Slide path from the top',
  //   help: 'Tap where the slope failed, and the toe if you can see it.',
  //   types: ['Landslide'],
  //   available: (ctx) => Boolean(ctx.rasters?.slope),
  //   generate: (taps, ctx) => pathCorners(taps, ctx.rasters.slope),
  // },
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
 * The method a hazard type should open on: its first smart method, falling
 * back to hand drawing. Registry order decides, so the preferred method for
 * a type goes above the others.
 */
export function defaultMethodFor(typeName, context = {}) {
  const usable = methodsFor(typeName, context);
  const smart = usable.find((m) => m.key !== HAND);
  return (smart || usable[0] || byKey.get(HAND)).key;
}
