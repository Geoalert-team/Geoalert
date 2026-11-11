import { formatMB, rowFromFile, rowFromVideo, rowState, rowsFromLinks, titleFromFileName } from './videoRows';

const file = (name, size = 1000) => Object.defineProperty(new File(['x'], name), 'size', { value: size });

test('a messy paste makes one row per distinct video', () => {
  const rows = rowsFromLinks('\r\n https://youtu.be/aaaaaaaaaaa \r\n\r\nhttps://www.youtube.com/watch?v=aaaaaaaaaaa\r\nnot a link\nbbbbbbbbbbb\n', []);
  expect(rows.map((r) => r.youtubeId)).toEqual(['aaaaaaaaaaa', null, 'bbbbbbbbbbb']);
  expect(rows[1].link).toBe('not a link');
  expect(rows.every((r) => r.kind === 'youtube' && r.send === 'idle' && r.categoryId === null)).toBe(true);
  expect(new Set(rows.map((r) => r.key)).size).toBe(3);
  expect(rowsFromLinks('https://youtu.be/bbbbbbbbbbb', rows)).toEqual([]);
});

test('titles from file names', () => {
  expect(titleFromFileName('flood-drill_2026.mp4')).toBe('flood drill 2026');
  expect(titleFromFileName('  Evac--Plan__v2.final.MP4')).toBe('Evac Plan v2.final');
  expect(titleFromFileName(`${'a'.repeat(130)}.mp4`)).toHaveLength(120);
});

test('file rows: case, type and size', () => {
  expect(rowState(rowFromFile(file('FLOOD.MP4'))).key).toBe('ready');
  expect(rowFromFile(file('FLOOD.MP4')).title).toBe('FLOOD');
  expect(rowState(rowFromFile(file('drill.mov')))).toEqual({ key: 'not_mp4', label: 'Not an MP4', blocking: true });
  expect(rowState(rowFromFile(file('photo.jpg'))).key).toBe('not_mp4');
  expect(formatMB(66270000)).toBe('63.2');
  expect(rowState(rowFromFile(file('big.mp4', 66270000))).label).toBe('Too big (63.2 MB, limit 50 MB)');
  expect(rowState(rowFromFile(file('edge.mp4', 50 * 1024 * 1024))).key).toBe('ready');
});

test('youtube row states in order', () => {
  const [row] = rowsFromLinks('https://youtu.be/aaaaaaaaaaa', []);
  expect(rowState({ ...row, check: 'pending' })).toEqual({ key: 'checking', label: 'Checking with YouTube…', blocking: true });
  expect(rowState({ ...row, check: 'not_found' }).label).toBe('Video not found or private');
  expect(rowState({ ...row, check: 'ok', title: ' ' }).label).toBe('Needs a title');
  expect(rowState({ ...row, check: 'unchecked', title: 'T' })).toEqual({ key: 'unchecked', label: "Couldn't check with YouTube", blocking: false });
  expect(rowState({ ...row, check: 'ok', title: 'T', duplicate: 'First Aid' })).toEqual({ key: 'duplicate', label: 'Already in First Aid', blocking: false });
  expect(rowState({ ...row, check: 'ok', title: 'T' }).label).toBe('Ready');
  expect(rowState(rowsFromLinks('nope', [])[0]).label).toBe('Not a YouTube link');
});

test('an existing video becomes one editable row', () => {
  const row = rowFromVideo({ id: 'v1', title: 'Drill', description: 'D', category: { id: 'c1', name: 'Drills' },
    source_type: 'upload', youtube_id: null, file_url: 'https://x/v.mp4', file_size: 10 });
  expect(row).toMatchObject({ videoId: 'v1', kind: 'upload', categoryId: 'c1', file: null, title: 'Drill', description: 'D' });
  expect(rowState(row).key).toBe('ready');
});
