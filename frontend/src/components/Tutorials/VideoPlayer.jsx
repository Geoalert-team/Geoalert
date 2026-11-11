import React, { useState } from 'react';
import { youtubeEmbed, youtubeLargeThumb, youtubeStandardThumb } from '../../utils/youtube';

// What YouTube sends, with a 404, for a video that has no large thumbnail: a grey 120 by 90 image
const PLACEHOLDER_WIDTH = 120;
const PLAY_PATH = 'M8 5v14l11-7z';

/**
 * A YouTube video shows its thumbnail and a play button first. YouTube's
 * player is about 690 KB of script before it can draw anything, so the empty
 * frame used to sit there while it loaded; now the 30 to 100 KB thumbnail
 * shows at once, and residents who only browse never download the player.
 * Pressing play loads it in the privacy-enhanced (youtube-nocookie) frame and
 * starts the video.
 */
function YouTubeVideo({ video }) {
  const [playing, setPlaying] = useState(false);
  const [large, setLarge] = useState(true);

  if (playing) {
    return (
      <iframe
        src={`${youtubeEmbed(video.youtube_id)}?autoplay=1`}
        title={video.title}
        allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
      />
    );
  }
  return (
    <button type="button" className="tv-poster" aria-label={`Play: ${video.title}`} onClick={() => setPlaying(true)}>
      <img
        src={large ? youtubeLargeThumb(video.youtube_id) : youtubeStandardThumb(video.youtube_id)}
        alt=""
        onError={() => setLarge(false)}
        onLoad={(e) => { if (e.currentTarget.naturalWidth <= PLACEHOLDER_WIDTH) setLarge(false); }}
      />
      <span className="tv-poster-play" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d={PLAY_PATH} /></svg>
      </span>
    </button>
  );
}

/**
 * Plays one tutorial video: a YouTube video (above), or an uploaded MP4 in
 * the browser's own player.
 *
 *   video     { title, source_type, youtube_id, file_url }
 *   onError   called when an MP4 can't be played, e.g. its signed link expired
 */
export default function VideoPlayer({ video, onError }) {
  return (
    <div className="wt-player-frame">
      {video.source_type === 'youtube' ? (
        // Keyed so another video starts again from its thumbnail
        <YouTubeVideo key={video.youtube_id} video={video} />
      ) : (
        <video controls preload="metadata" src={video.file_url} aria-label={video.title} onError={onError} />
      )}
    </div>
  );
}
