// CSV export for reports (F7). Built in the browser from the report the
// officer is looking at, so the file always matches the screen.
//
// A report is several small tables, so the file is written as sections: a
// title line, a header row, the rows, then a blank line. Excel and Google
// Sheets both open that as one sheet with the tables one under another.

function cell(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  // Quote anything with a comma, quote or line break; double inner quotes.
  // A leading = + - @ would be read by a spreadsheet as a formula, so it
  // is prefixed with an apostrophe (OWASP CSV injection advice).
  const safe = /^[=+\-@\t\r]/.test(text) && !/^-?\d+(\.\d+)?$/.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function csvRow(values) {
  return values.map(cell).join(',');
}

/**
 * sections: [{ title, header: [...], rows: [[...], ...] }]
 * meta: [[label, value], ...] written first, e.g. who generated it and when
 */
export function toCsv(sections, meta = []) {
  const lines = meta.map((m) => csvRow(m));
  if (lines.length) lines.push('');
  sections.forEach((s) => {
    if (s.title) lines.push(csvRow([s.title]));
    if (s.header) lines.push(csvRow(s.header));
    (s.rows || []).forEach((r) => lines.push(csvRow(r)));
    lines.push('');
  });
  return lines.join('\r\n');
}

/** Save text as a .csv download. The BOM makes Excel read it as UTF-8 (ñ in barangay names). */
export function downloadCsv(filename, text) {
  const blob = new Blob(['﻿', text], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** report-name-2026-10-19.csv */
export function csvFilename(name, when = new Date()) {
  const d = new Date(when);
  const pad = (n) => String(n).padStart(2, '0');
  return `${name}-${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}.csv`;
}
