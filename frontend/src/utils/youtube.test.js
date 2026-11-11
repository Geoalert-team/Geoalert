import { parseYouTubeId, youtubeEmbed, youtubeThumb, youtubeWatch } from './youtube';

// The same cases as the backend's reader (backend/tests/test_tutorial_videos.py)
const ID = '2v8vlXgGXwE';
const ACCEPTED = [
  ID, `https://www.youtube.com/watch?v=${ID}`, `https://youtube.com/watch?v=${ID}&t=42s`,
  `https://m.youtube.com/watch?v=${ID}&list=PL123`, `https://www.youtube.com/watch?feature=share&v=${ID}`,
  `https://youtu.be/${ID}`, `https://youtu.be/${ID}?si=abc`, `https://www.youtube.com/shorts/${ID}`,
  `https://www.youtube.com/embed/${ID}`, `https://www.youtube-nocookie.com/embed/${ID}`,
  `  www.youtube.com/watch?v=${ID}  `, `http://youtube.com/watch?v=${ID}`,
  `HTTPS://WWW.YOUTUBE.COM/watch?v=${ID}`,
];
const REFUSED = [
  null, '', '   ', 'https://vimeo.com/123456789', 'https://www.youtube.com/@TalisayDRRMO',
  'https://www.youtube.com/playlist?list=PL123', 'https://www.youtube.com/watch?v=short',
  'https://youtu.be/2v8vlXgGXw!', `https://notyoutube.com/watch?v=${ID}`,
  `https://youtube.com.evil.example/watch?v=${ID}`, `${ID}X`,
];

test.each(ACCEPTED)('%s gives the id', (text) => expect(parseYouTubeId(text)).toBe(ID));
test.each(REFUSED)('%s gives null', (text) => expect(parseYouTubeId(text)).toBeNull());

test('the three urls', () => {
  expect(youtubeEmbed(ID)).toBe(`https://www.youtube-nocookie.com/embed/${ID}`);
  expect(youtubeThumb(ID)).toBe(`https://i.ytimg.com/vi/${ID}/mqdefault.jpg`);
  expect(youtubeWatch(ID)).toBe(`https://www.youtube.com/watch?v=${ID}`);
});
