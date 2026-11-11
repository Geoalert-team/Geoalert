import { parseYouTubeId, youtubeWatch } from '../../utils/youtube';

// The rows of the Add videos form: one per pasted link or chosen file, or the
// one video being edited. Kept apart from the form so the rules (what a row
// is, what blocks Publish) can be read and tested on their own.
//
// A row:
//   key          unique, for React and for updating one row
//   videoId      the video being edited, or null for a new one
//   kind         'youtube' | 'upload'
//   categoryId   its own category, or null for the batch's
//   link         the pasted line (YouTube rows)
//   youtubeId    the ID read from it, or null when it isn't a YouTube link
//   file         the chosen File (new uploads), or null
//   title, description
//   check        null | 'pending' | 'ok' | 'not_found' | 'unchecked' (YouTube's answer)
//   duplicate    the category a saved video with this ID is in, or null
//   send         'idle' | 'sending' | 'saving' | 'done' | 'failed'
//   progress     0-100 while uploading
//   error        the server's message when sending failed

export const MAX_VIDEO_BYTES = 50 * 1024 * 1024;
const TITLE_MAX = 120;

let lastKey = 0;
function newRow(fields) {
  lastKey += 1;
  return {
    key: `row-${lastKey}`, videoId: null, kind: 'youtube', categoryId: null, link: '', youtubeId: null,
    file: null, title: '', description: '', check: null, duplicate: null, send: 'idle', progress: 0, error: '',
    ...fields,
  };
}

/** 66270000 -> '63.2' (MB as the size limit counts them) */
export const formatMB = (bytes) => (bytes / 1024 / 1024).toFixed(1);

/** 'flood-drill_2026.mp4' -> 'flood drill 2026' */
export function titleFromFileName(name) {
  return (name || '')
    .replace(/\.[^.]*$/, '')
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, TITLE_MAX);
}

/**
 * New rows for a pasted block of links, one per line. Blank lines are
 * skipped, and so is a video already among `rows` or earlier in the paste.
 * A line that isn't a YouTube link still makes a row, so it shows as refused.
 */
export function rowsFromLinks(text, rows = []) {
  const seen = new Set(rows.map((r) => r.youtubeId).filter(Boolean));
  const added = [];
  (text || '').split('\n').forEach((line) => {
    const link = line.replace(/\r/g, '').trim();
    if (!link) return;
    const youtubeId = parseYouTubeId(link);
    if (youtubeId) {
      if (seen.has(youtubeId)) return;
      seen.add(youtubeId);
    }
    added.push(newRow({ kind: 'youtube', link, youtubeId }));
  });
  return added;
}

export const rowFromFile = (file) => newRow({ kind: 'upload', file, title: titleFromFileName(file.name) });

/** The one row of the form when editing a saved video; its media is kept unless replaced. */
export function rowFromVideo(video) {
  return newRow({
    videoId: video.id,
    kind: video.source_type,
    categoryId: video.category?.id ?? null,
    youtubeId: video.youtube_id || null,
    link: video.youtube_id ? youtubeWatch(video.youtube_id) : '',
    title: video.title || '',
    description: video.description || '',
  });
}

const state = (key, label, blocking) => ({ key, label, blocking });

/** What a row shows beside it, and whether it stops Publish. The first match wins. */
export function rowState(row) {
  if (row.kind === 'youtube' && !row.youtubeId) return state('bad_link', 'Not a YouTube link', true);
  if (row.check === 'not_found') return state('not_found', 'Video not found or private', true);
  // An upload being edited with no new file keeps the one already saved
  if (row.kind === 'upload' && row.file) {
    if (!/\.mp4$/i.test(row.file.name)) return state('not_mp4', 'Not an MP4', true);
    if (row.file.size > MAX_VIDEO_BYTES) {
      return state('too_big', `Too big (${formatMB(row.file.size)} MB, limit 50 MB)`, true);
    }
  }
  if (row.check === 'pending') return state('checking', 'Checking with YouTube…', true);
  if (!row.title.trim()) return state('no_title', 'Needs a title', true);
  if (row.check === 'unchecked') return state('unchecked', "Couldn't check with YouTube", false);
  if (row.duplicate) return state('duplicate', `Already in ${row.duplicate}`, false);
  return state('ready', 'Ready', false);
}
