import { stackTable, stackedData } from './stackedData';

const rows = [
  { label: '2025', counts: { Fire: 2 } },
  { label: '2026', counts: { Fire: 1, Flood: 3 } },
];

test('one dataset per series, with missing counts as zero', () => {
  const colorFor = (name) => (name === 'Fire' ? '#f00' : '#00f');
  expect(stackedData(rows, ['Fire', 'Flood'], colorFor)).toEqual({
    labels: ['2025', '2026'],
    datasets: [
      { label: 'Fire', data: [2, 1], color: '#f00' },
      { label: 'Flood', data: [0, 3], color: '#00f' },
    ],
  });
});

test('the figures as a table with a total column', () => {
  const { labels, datasets } = stackedData(rows, ['Fire', 'Flood'], () => '#000');
  expect(stackTable(labels, datasets)).toEqual({
    head: ['', 'Fire', 'Flood', 'Total'],
    rows: [['2025', 2, 0, 2], ['2026', 1, 3, 4]],
  });
});

test('series can be relabelled for the legend', () => {
  const { datasets } = stackedData(rows, ['Fire'], () => '#000', (name) => `${name}!`);
  expect(datasets[0].label).toBe('Fire!');
});
