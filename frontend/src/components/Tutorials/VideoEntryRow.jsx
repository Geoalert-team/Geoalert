import React, { useEffect, useState } from 'react';
import { youtubeThumb } from '../../utils/youtube';
import { formatMB, rowState } from './videoRows';

/**
 * One video in the Add videos form: its preview, title, description and
 * category, what stops it from being published, and how its upload is going.
 * Props in, events out; the form does the saving.
 *
 *   row            see videoRows.js
 *   categories     [{ id, name }] for the row's own category
 *   onChange(patch), onRemove(), onRetry()
 *   single         editing one video: no remove button, no per-row category
 */
export default function VideoEntryRow({ row, categories, onChange, onRemove, onRetry, single = false }) {
  const [preview, setPreview] = useState(null);

  // A chosen file plays here before it is uploaded, so one the browser
  // can't play shows up now rather than on the public page
  useEffect(() => {
    if (!row.file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(row.file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [row.file]);

  const state = rowState(row);
  const busy = row.send === 'sending' || row.send === 'saving';
  const done = row.send === 'done';
  const locked = busy || done;

  let status = state.label;
  if (row.send === 'sending') status = 'Uploading';
  else if (row.send === 'saving') status = 'Saving…';
  else if (done) status = 'Done';
  else if (row.send === 'failed') status = 'Not saved';

  const tone = done ? 'done' : row.send === 'failed' || state.blocking ? 'bad' : 'ok';

  return (
    <li className={`tv-row tv-row-${tone}`}>
      <div className="tv-row-thumb">
        {row.kind === 'youtube' && row.youtubeId ? (
          <img src={youtubeThumb(row.youtubeId)} alt="" />
        ) : preview ? (
          <video src={preview} muted controls preload="metadata" aria-label={`Preview of ${row.file.name}`} />
        ) : (
          <span className="tv-thumb-mp4" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
          </span>
        )}
      </div>

      <div className="tv-row-fields">
        <p className="tv-row-source">
          {row.kind === 'youtube'
            ? `YouTube · ${row.link}`
            : row.file ? `MP4 · ${formatMB(row.file.size)} MB · ${row.file.name}` : 'MP4 · the uploaded file is kept'}
        </p>
        <input
          type="text"
          aria-label="Title"
          placeholder="Title"
          value={row.title}
          maxLength={120}
          disabled={locked}
          onChange={(e) => onChange({ title: e.target.value })}
        />
        <textarea
          aria-label="Description"
          placeholder="About this video (optional)"
          rows={2}
          value={row.description}
          maxLength={500}
          disabled={locked}
          onChange={(e) => onChange({ description: e.target.value })}
        />
        {!single && (
          <select
            aria-label="Row category"
            value={row.categoryId || ''}
            disabled={locked}
            onChange={(e) => onChange({ categoryId: e.target.value || null })}
          >
            <option value="">Batch category</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
      </div>

      <div className="tv-row-status">
        <span className="tv-row-state">{status}</span>
        {busy && (
          <span className="tv-progress" aria-label="Upload progress">
            <span className="tv-progress-bar" style={{ width: `${row.progress}%` }} />
            <span className="tv-progress-text">{row.send === 'saving' ? 'Saving…' : `${row.progress}%`}</span>
          </span>
        )}
        {row.send === 'failed' && (
          <>
            <p className="tv-row-error" role="alert">{row.error}</p>
            <button type="button" className="wt-edit-btn" onClick={onRetry}>Retry</button>
          </>
        )}
        {!single && !locked && (
          <button type="button" className="tv-row-remove" aria-label="Remove row" onClick={onRemove}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14 M10 11v6 M14 11v6 M7 7l1 12h8l1-12 M9 7V4h6v3" /></svg>
          </button>
        )}
      </div>
    </li>
  );
}
