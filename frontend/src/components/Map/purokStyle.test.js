import { PUROK_COLOR, PUROK_HOVER, hasEstimates, purokAt, purokStyle, purokTooltip, puroksOf } from './purokStyle';

const feature = (props) => ({ type: 'Feature', properties: props, geometry: null });

describe('purokStyle', () => {
  test('estimated outlines are dashed violet', () => {
    const s = purokStyle(feature({ source: 'estimated' }));
    expect(s.color).toBe(PUROK_COLOR);
    expect(s.dashArray).toBe('5 4');
  });

  test('just the line: nothing covers the map inside', () => {
    expect(purokStyle(feature({ source: 'estimated' })).fill).toBe(false);
  });

  test("official outlines are solid: they're the real lines", () => {
    expect(purokStyle(feature({ source: 'official' })).dashArray).toBeNull();
  });

  test('the hovered purok is tinted and its line thickened', () => {
    expect(PUROK_HOVER.fillOpacity).toBeGreaterThan(0);
    expect(PUROK_HOVER.weight).toBeGreaterThan(purokStyle(feature({ source: 'estimated' })).weight);
  });
});

describe('puroksOf', () => {
  const GEO = {
    type: 'FeatureCollection',
    features: [
      feature({ barangay: 21, name: 'Area 1' }),
      feature({ barangay: 21, name: 'Area 2' }),
      feature({ barangay: 4, name: 'Area 1' }),
    ],
  };

  test("only the selected barangay's puroks", () => {
    expect(puroksOf(GEO, 21).features.map((f) => f.properties.name)).toEqual(['Area 1', 'Area 2']);
    expect(puroksOf(GEO, '4').features).toHaveLength(1);
  });

  test('nothing when no barangay is selected, or it has no puroks', () => {
    expect(puroksOf(GEO, null)).toBeNull();
    expect(puroksOf(GEO, 99)).toBeNull();
    expect(puroksOf(null, 21)).toBeNull();
  });
});

describe('purokAt', () => {
  const square = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]];
  const GEO = {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { name: 'Area 1' },
        geometry: { type: 'MultiPolygon', coordinates: [[square(0, 0, 10, 10), square(4, 4, 6, 6)]] } },
      { type: 'Feature', properties: { name: 'Area 2' },
        geometry: { type: 'MultiPolygon', coordinates: [[square(4, 4, 6, 6)], [square(20, 0, 30, 10)]] } },
    ],
  };
  const at = (lng, lat) => purokAt(GEO, lng, lat)?.properties.name ?? null;

  test('finds the purok under a point', () => {
    expect(at(1, 1)).toBe('Area 1');
    expect(at(25, 5)).toBe('Area 2');
  });

  test('a hole belongs to whatever fills it, not the purok around it', () => {
    expect(at(5, 5)).toBe('Area 2');
  });

  test('nothing outside every purok', () => {
    expect(at(15, 5)).toBeNull();
    expect(purokAt(null, 1, 1)).toBeNull();
  });
});

describe('purokTooltip', () => {
  test('an estimated area says so, with its barangay', () => {
    const html = purokTooltip(feature({ name: 'Area 3', source: 'estimated', barangay_name: 'Tangke' }));
    expect(html).toContain('<strong>Area 3</strong>');
    expect(html).toContain('Estimated purok area');
    expect(html).toContain('Tangke');
  });

  test('an official purok shows its sitio and barangay', () => {
    const html = purokTooltip(feature({ name: 'Purok Sambag', parent: 'Laray', source: 'official', barangay_name: 'San Roque' }));
    expect(html).toContain('<strong>Purok Sambag</strong>');
    expect(html).toContain('Laray · San Roque');
    expect(html).not.toContain('Estimated');
  });

  test('names are shown as text, never run as HTML', () => {
    const html = purokTooltip(feature({ name: '<img src=x onerror=alert(1)>', source: 'official', barangay_name: 'Tangke' }));
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});

describe('hasEstimates', () => {
  test('true while any outline is not official', () => {
    expect(hasEstimates({ features: [feature({ source: 'official' }), feature({ source: 'estimated' })] })).toBe(true);
  });

  test('false once every outline is official, or when there are none', () => {
    expect(hasEstimates({ features: [feature({ source: 'official' })] })).toBe(false);
    expect(hasEstimates(null)).toBe(false);
  });
});
