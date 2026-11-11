import React from 'react';
import { youtubeEmbed } from '../../utils/youtube';

/**
 * Plays one tutorial video: a YouTube video in the privacy-enhanced
 * (youtube-nocookie) frame, or an uploaded MP4 in the browser's own player.
 *
 *   video     { title, source_type, youtube_id, file_url }
 *   onError   called when an MP4 can't be played, e.g. its signed link expired
 */
export default function VideoPlayer({ video, onError }) {
  return (
    <div className="wt-player-frame">
      {video.source_type === 'youtube' ? (
        <iframe
          src={youtubeEmbed(video.youtube_id)}
          title={video.title}
          allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          loading="lazy"
        />
      ) : (
        <video controls preload="metadata" src={video.file_url} aria-label={video.title} onError={onError} />
      )}
    </div>
  );
}
