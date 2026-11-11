import React, { useCallback, useEffect, useRef, useState } from 'react';
import { tutorialsApi } from '../../api/tutorialsApi';
import { useAuth } from '../../context/AuthContext';
import { youtubeThumb, youtubeWatch } from '../../utils/youtube';
import AddVideosForm from './AddVideosForm';
import ConfirmBox from './ConfirmBox';
import DeleteCategoryButton from './DeleteCategoryButton';
import VideoPlayer from './VideoPlayer';
import './css/TutorialVideos.css';

const ARROW_PATHS = { prev: 'M15 5l-7 7 7 7', next: 'M9 5l7 7-7 7' };

/**
 * The What To Do page's tutorial videos, one category at a time: its name
 * and description as the header, ‹ › arrows and chips to move between
 * categories, the player, and the category's videos beside it.
 *
 * Residents see only categories that have videos. DRRMO officers and admins
 * (canPublish) also see empty ones, and manage everything here: Add videos,
 * Delete category (with its videos), and Edit and Delete for the chosen
 * video. One form at a time, opened in place at the top of the section.
 */
export default function TutorialVideos() {
  const { canPublish } = useAuth();
  const [videos, setVideos] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [chosenId, setChosenId] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [editing, setEditing] = useState(null); // null | 'new' | a video id
  const [actionError, setActionError] = useState('');
  const [confirming, setConfirming] = useState(null); // the video waiting on the delete dialog
  const [deleting, setDeleting] = useState(false);
  const formRef = useRef(null);
  // Videos whose MP4 already failed once and were given fresh links
  const retried = useRef(new Set());

  // quiet: refresh what is shown without the loading message (fresh links, after a change)
  const load = useCallback(async (quiet = false) => {
    if (!quiet) {
      setLoading(true);
      setFailed(false);
    }
    try {
      const [list, cats] = await Promise.all([tutorialsApi.list(), tutorialsApi.categories()]);
      setVideos(list);
      setCategories(cats);
      setFailed(false);
    } catch {
      if (!quiet) setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // The form opens at the top of the section; bring it into view
  useEffect(() => {
    if (editing !== null) formRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [editing]);

  // A video being edited that is gone after a refresh (deleted elsewhere): close its form
  useEffect(() => {
    if (editing && editing !== 'new' && !loading && !videos.some((v) => v.id === editing)) setEditing(null);
  }, [editing, videos, loading]);

  // Residents only get categories with something to watch; staff get every one
  const shownCategories = canPublish ? categories : categories.filter((c) => c.video_count > 0);
  // A chosen category that is gone falls back to the first one
  const current = shownCategories.find((c) => c.id === chosenId) || shownCategories[0] || null;
  const shown = current ? videos.filter((v) => v.category.id === current.id) : [];
  // A deleted video's place goes to the first one still shown
  const active = shown.find((v) => v.id === activeId) || shown[0] || null;
  const usedBytes = videos.reduce((sum, v) => sum + (v.file_size || 0), 0);
  const tools = canPublish && editing === null && !loading && !failed;

  // The neighbours for the arrows, wrapping around at the ends
  const at = current ? shownCategories.indexOf(current) : -1;
  const count = shownCategories.length;
  const prev = count > 1 ? shownCategories[(at - 1 + count) % count] : null;
  const next = count > 1 ? shownCategories[(at + 1) % count] : null;

  function go(category) {
    setChosenId(category.id);
    setActiveId(null); // the category's first video plays
  }

  // An MP4's signed link lasts an hour: when one fails to play, fetch fresh
  // links, once per video, so a broken file can't loop
  function refreshLinks(video) {
    if (retried.current.has(video.id)) return;
    retried.current.add(video.id);
    load(true);
  }

  function openForm(target) {
    setActionError('');
    setEditing(target);
  }

  function closeForm(changed) {
    setEditing(null);
    if (changed) load(true);
  }

  async function deleteVideo() {
    setDeleting(true);
    setActionError('');
    try {
      await tutorialsApi.remove(confirming.id);
      await load(true);
    } catch (err) {
      setActionError(err.message);
    } finally {
      setDeleting(false);
      setConfirming(null);
    }
  }

  if (!loading && !failed && shownCategories.length === 0 && !canPublish) return null;

  const editedVideo = editing && editing !== 'new' ? videos.find((v) => v.id === editing) || null : null;

  const arrowButton = (side, target) => {
    const tip = `${side === 'prev' ? 'Previous' : 'Next'}: ${target.name}`;
    return (
      <button type="button" className={`tv-arrow tv-arrow-${side}`} aria-label={tip} data-tip={tip}
        onClick={() => go(target)}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ARROW_PATHS[side]} /></svg>
      </button>
    );
  };

  return (
    <section className="ph-section" aria-labelledby="tv-heading">
      <div className="ph-container">
        <div className="ph-section-head tv-head">
          {current ? (
            <>
              <p className="tv-eyebrow">Tutorial videos</p>
              <div className="tv-title-row">
                {prev && arrowButton('prev', prev)}
                <h2 id="tv-heading">{current.name}</h2>
                {next && arrowButton('next', next)}
              </div>
              {current.description && <p className="tv-category-description">{current.description}</p>}
            </>
          ) : (
            <>
              <h2 id="tv-heading">Tutorial videos</h2>
              <p>Short lessons. Watch and share them with your family.</p>
            </>
          )}
        </div>

        {!loading && !failed && (shownCategories.length > 0 || tools) && (
          <div className="tv-nav-row">
            <div className="tv-chips" role="group" aria-label="Video categories">
              {shownCategories.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`tv-chip ${current && current.id === c.id ? 'is-active' : ''}`}
                  aria-pressed={Boolean(current && current.id === c.id)}
                  onClick={() => go(c)}
                >
                  {c.name}
                </button>
              ))}
            </div>
            {tools && (
              <div className="tv-staff-tools">
                <button type="button" className="wt-edit-btn" onClick={() => openForm('new')}>Add videos</button>
                {current && (
                  // Keyed by category: if a refresh changes the category shown while the
                  // warning is open, the dialog closes instead of pointing at another one
                  <DeleteCategoryButton
                    key={current.id}
                    category={current}
                    onDeleted={() => { setActionError(''); load(true); }}
                    onError={setActionError}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {editing !== null && (
          <div ref={formRef}>
            <AddVideosForm
              video={editedVideo}
              defaultCategoryId={current ? current.id : null}
              usedBytes={usedBytes}
              onClose={closeForm}
            />
          </div>
        )}

        {actionError && <p className="wt-action-error" role="alert">{actionError}</p>}

        {loading ? (
          <p className="wt-muted">Loading videos…</p>
        ) : failed ? (
          <div className="wt-error" role="alert">
            <p>Couldn't load the videos. Try again.</p>
            <button type="button" className="wt-retry" onClick={() => load()}>Try again</button>
          </div>
        ) : !current ? (
          <p className="wt-muted">No videos yet.</p>
        ) : !active ? (
          <p className="wt-muted">No videos in this category yet.</p>
        ) : (
          <div className="wt-videos">
            <div className="wt-player">
              <VideoPlayer
                key={`${active.id}:${active.file_url || ''}`}
                video={active}
                onError={() => refreshLinks(active)}
              />
              <div className="wt-player-info">
                <div>
                  <span className="wt-video-tag">{active.category.name}</span>
                  <h3>{active.title}</h3>
                  {active.description && <p className="tv-description">{active.description}</p>}
                </div>
                {active.source_type === 'youtube' && (
                  <a
                    className="wt-youtube-link"
                    href={youtubeWatch(active.youtube_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Watch on YouTube
                  </a>
                )}
              </div>
            </div>

            <ul className="wt-playlist" aria-label={`${current.name} videos`}>
              {shown.map((video) => (
                <li key={video.id}>
                  <button
                    type="button"
                    className={`wt-playlist-item ${video.id === active.id ? 'is-active' : ''}`}
                    aria-current={video.id === active.id}
                    onClick={() => setActiveId(video.id)}
                  >
                    {video.source_type === 'youtube' ? (
                      <img src={youtubeThumb(video.youtube_id)} alt="" loading="lazy" />
                    ) : (
                      <span className="tv-thumb-mp4" aria-hidden="true">
                        <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                      </span>
                    )}
                    <span>
                      <strong>{video.title}</strong>
                      <small>{video.category.name}{video.source_type === 'upload' ? ' · MP4' : ''}</small>
                    </span>
                  </button>
                  {/* Staff tools for the chosen video only, under its card (not inside it: a
                      button can't hold buttons). Click another video and they follow it. */}
                  {tools && video.id === active.id && (
                    <div className="tv-item-tools">
                      <button
                        type="button"
                        className="wt-edit-btn"
                        aria-label={`Edit "${video.title}"`}
                        onClick={() => openForm(video.id)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="wt-edit-btn wt-edit-btn-danger"
                        aria-label={`Delete "${video.title}"`}
                        onClick={() => setConfirming(video)}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {confirming && (
          <ConfirmBox
            title="Delete video"
            message={`Delete '${confirming.title}'? Residents will stop seeing it.${
              confirming.source_type === 'upload' ? ' The uploaded file is deleted too.' : ''}`}
            confirmLabel="Delete"
            danger
            busy={deleting}
            onConfirm={deleteVideo}
            onCancel={() => { if (!deleting) setConfirming(null); }}
          />
        )}
      </div>
    </section>
  );
}
