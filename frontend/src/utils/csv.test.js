import { csvRow, toCsv, csvFilename } from './csv';

test('quotes commas, quotes and line breaks', () => {
  expect(csvRow(['a', 'b,c', 'say "hi"', 'x\ny'])).toBe('a,"b,c","say ""hi""","x\ny"');
});

test('blanks for null and keeps numbers, including negatives', () => {
  expect(csvRow([null, undefined, 0, -3, 2.5])).toBe(',,0,-3,2.5');
});

test('neutralises spreadsheet formulas', () => {
  expect(csvRow(['=SUM(A1)', '+1+1', '@cmd'])).toBe("'=SUM(A1),'+1+1,'@cmd");
});

test('writes meta then titled sections separated by blank lines', () => {
  const text = toCsv(
    [{ title: 'By type', header: ['Type', 'Count'], rows: [['Flood', 3]] }],
    [['Report', 'Test']],
  );
  expect(text.split('\r\n')).toEqual(['Report,Test', '', 'By type', 'Type,Count', 'Flood,3', '']);
});

test('dated filename', () => {
  expect(csvFilename('hazard-summary', new Date(2026, 9, 5))).toBe('hazard-summary-2026-10-05.csv');
});
