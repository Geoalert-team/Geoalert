// Reading YouTube links, the same way the backend does
// (backend/apps/tutorials/youtube.py). The form uses this to show a thumbnail
// the moment a link is pasted; the server's copy decides what is saved.

const ID = /^[A-Za-z0-9_-]{11}$/;
const YOUTUBE_HOSTS = new Set(['youtube.com', 'youtube-nocookie.com']);
const PATH_ID_PREFIXES = ['/shorts/', '/embed/'];

const videoId = (candidate) => (candidate && ID.test(candidate) ? candidate : null);

/**
 * The 11-character video ID in a YouTube link, or null. Accepts watch?v=
 * links (www., m. or neither, with any other parameters), youtu.be/<id>,
 * /shorts/<id>, /embed/<id> and a bare ID.
 */
export function parseYouTubeId(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return null;
  if (ID.test(trimmed)) return trimmed;
  let url;
  try {
    url = new URL(trimmed.includes('://') ? trimmed : `https://${trimmed}`);
  } catch {
    return null;
  }
  let host = url.hostname.toLowerCase();
  const prefix = ['www.', 'm.'].find((p) => host.startsWith(p));
  if (prefix) host = host.slice(prefix.length);

  const path = url.pathname;
  if (host === 'youtu.be') return videoId(path.replace(/^\/+/, '').split('/')[0]);
  if (!YOUTUBE_HOSTS.has(host)) return null;
  if (path.replace(/\/+$/, '') === '/watch') return videoId(url.searchParams.get('v'));
  const idPrefix = PATH_ID_PREFIXES.find((p) => path.startsWith(p));
  return idPrefix ? videoId(path.slice(idPrefix.length).split('/')[0]) : null;
}

export const youtubeEmbed = (id) => `https://www.youtube-nocookie.com/embed/${id}`;
export const youtubeThumb = (id) => `https://i.ytimg.com/vi/${id}/mqdefault.jpg`;
export const youtubeWatch = (id) => `https://www.youtube.com/watch?v=${id}`;
