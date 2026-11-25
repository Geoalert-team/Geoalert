import { PUROK_COLOR, PUROK_HOVER, PUROK_SELECTED, isContainer, purokAt, purokStyle, purokTooltip, puroksOf } from './purokStyle';

const feature = (props) => ({ type: 'Feature', properties: props, geometry: null });

describe('purokStyle', () => {
  test('every outline is a solid violet line, whatever its source', () => {
    ['estimated', 'community', 'official'].forEach((source) => {
      const s = purokStyle(feature({ source }));
      expect(s.color).toBe(PUROK_COLOR);
      expect(s.dashArray).toBeNull();
    });
  });

  test('just the line: nothing covers the map inside', () => {
    expect(purokStyle(feature({ source: 'estimated' })).fill).toBe(false);
  });

  test('the hovered purok is tinted and its line thickened', () => {
    expect(PUROK_HOVER.fillOpacity).toBeGreaterThan(0);
    expect(PUROK_HOVER.weight).toBeGreaterThan(purokStyle(feature({ source: 'estimated' })).weight);
  });

  test('the selected purok is drawn bold and solid', () => {
    const s = { ...purokStyle(feature({ source: 'estimated' })), ...PUROK_SELECTED };
    expect(s.weight).toBeGreaterThan(PUROK_HOVER.weight);
    expect(s.dashArray).toBeNull();
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

  test('a purok wins over the sitio drawn around it; the sitio has its own part', () => {
    const nested = {
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', properties: { name: 'Sitio Laray', members: 2 },
          geometry: { type: 'MultiPolygon', coordinates: [[square(0, 0, 30, 10)]] } },
        { type: 'Feature', properties: { name: 'Purok Sambag', members: 0 },
          geometry: { type: 'MultiPolygon', coordinates: [[square(0, 0, 10, 10)]] } },
      ],
    };
    expect(purokAt(nested, 5, 5).properties.name).toBe('Purok Sambag');
    expect(purokAt(nested, 25, 5).properties.name).toBe('Sitio Laray');
  });
});

describe('sitios drawn around their puroks', () => {
  const sitio = { properties: { name: 'Sitio Laray', members: 3, source: 'estimated', confidence: 'high' } };
  const purok = { properties: { name: 'Purok Sambag', members: 0, source: 'estimated', confidence: 'low' } };

  test('isContainer', () => {
    expect(isContainer(sitio)).toBe(true);
    expect(isContainer(purok)).toBe(false);
    expect(isContainer({ properties: {} })).toBe(false);
  });

  test('a sitio gets a thicker line and no fill', () => {
    expect(purokStyle(sitio)).toMatchObject({ weight: 3, fill: false });
    expect(purokStyle(purok).weight).toBe(1.5);
  });

  test('its tooltip says how many puroks it holds', () => {
    expect(purokTooltip(sitio)).toContain('3 puroks inside');
    expect(purokTooltip({ properties: { ...sitio.properties, members: 1 } })).toContain('1 purok inside');
    expect(purokTooltip(purok)).not.toContain('inside');
  });
});

describe('purokTooltip', () => {
  test('shows the name, sitio and barangay, and nothing about how the outline was made', () => {
    const html = purokTooltip(feature({
      name: 'Purok Sambag', parent: 'Sitio Laray', source: 'estimated', confidence: 'high', barangay_name: 'San Roque',
    }));
    expect(html).toBe('<strong>Purok Sambag</strong><br>Sitio Laray · San Roque');
  });

  test('never calls an outline estimated, approximate, unofficial or unidentified', () => {
    [
      { name: 'Purok Okra', source: 'estimated', confidence: 'low', barangay_name: 'Dumlog' },
      { name: 'Near Tanke National High School', source: 'estimated', confidence: '', barangay_name: 'Tangke' },
      { name: 'Purok Lapu', source: 'community', barangay_name: 'Bulacao' },
    ].forEach((p) => {
      const html = purokTooltip(feature(p));
      expect(html).toContain(`<strong>${p.name}</strong>`);
      expect(html).not.toMatch(/estimat|approximate|official|not identified/i);
    });
  });

  test('an official purok shows its sitio and barangay', () => {
    const html = purokTooltip(feature({ name: 'Purok Sambag', parent: 'Laray', source: 'official', barangay_name: 'San Roque' }));
    expect(html).toContain('<strong>Purok Sambag</strong>');
    expect(html).toContain('Laray · San Roque');
    expect(html).toBe('<strong>Purok Sambag</strong><br>Laray · San Roque');
  });

  test('names are shown as text, never run as HTML', () => {
    const html = purokTooltip(feature({ name: '<img src=x onerror=alert(1)>', source: 'official', barangay_name: 'Tangke' }));
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});
