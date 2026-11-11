import React, { useCallback, useEffect, useRef, useState } from 'react';
import { tutorialsApi } from '../../api/tutorialsApi';
import CategoryPicker from './CategoryPicker';
import VideoEntryRow from './VideoEntryRow';
import { formatMB, rowFromFile, rowFromVideo, rowState, rowsFromLinks } from './videoRows';

const TITLE_MAX = 120;
const plural = (n, one, many) => (n === 1 ? one : many);

/**
 * Add a batch of tutorial videos, or edit one, in place on the What To Do
 * page. The four steps sit on one screen: the category (once, for the
 * batch), the media (YouTube links and MP4 files, side by side), each
 * video's details, and a review of every row before Publish. Rows are sent
 * one at a time, so each shows its own progress and a failed one can be
 * retried alone; the server checks everything again.
 *
 *   video               the video being edited, or null to add videos
 *   defaultCategoryId   the batch's category to start with (the chip chosen on the page)
 *   usedBytes           how much the uploaded videos already take
 *   onClose(changed)    leave the form; changed is true when anything was saved
 */
export default function AddVideosForm({ video = null, defaultCategoryId = null, usedBytes = 0, onClose }) {
  const editing = Boolean(video);
  const [categories, setCategories] = useState([]);
  const [categoryError, setCategoryError] = useState('');
  const [batchCategory, setBatchCategory] = useState(editing ? video.category.id : defaultCategoryId);
  const [links, setLinks] = useState('');
  const [sending, setSending] = useState(false);

  // The rows live in a ref as well as in state, so the send loop and the
  // YouTube checks, which await, always read and write the latest rows
  const initialRows = useRef(null);
  if (initialRows.current === null) initialRows.current = editing ? [rowFromVideo(video)] : [];
  const rowsRef = useRef(initialRows.current);
  const [rows, setRowsState] = useState(initialRows.current);
  const setRows = useCallback((next) => {
    rowsRef.current = next;
    setRowsState(next);
  }, []);
  const patchRow = useCallback((key, patch) => {
    setRows(rowsRef.current.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }, [setRows]);

  const sendingRef = useRef(false);
  const savedRef = useRef(false);
  const closedRef = useRef(false);
  // A category created, edited or deleted in the picker changes what the
  // section shows (its header, its videos), so leaving then counts as a change
  const categoriesChangedRef = useRef(false);
  // Read through a ref: the section passes a new function on every render,
  // and loadCategories must not change (and refetch) because of it
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const editedCategoryId = editing ? video.category.id : null;

  const loadCategories = useCallback(async () => {
    try {
      const list = await tutorialsApi.categories();
      const ids = new Set(list.map((c) => c.id));
      // The edited video's category was deleted, and the video with it: nothing left to edit
      if (editedCategoryId && !ids.has(editedCategoryId)) {
        onCloseRef.current(true);
        return;
      }
      setCategories(list);
      setCategoryError('');
      // A category deleted in the picker is no longer anyone's choice
      setBatchCategory((current) => (current && ids.has(current) ? current : null));
      setRows(rowsRef.current.map((r) => (r.categoryId && !ids.has(r.categoryId) ? { ...r, categoryId: null } : r)));
    } catch (err) {
      setCategoryError(err.message);
    }
  }, [setRows, editedCategoryId]);

  const categoriesChanged = useCallback(() => {
    categoriesChangedRef.current = true;
    loadCategories();
  }, [loadCategories]);

  useEffect(() => { loadCategories(); }, [loadCategories]);

  // ---------- Media in ----------

  async function check(row) {
    patchRow(row.key, { check: 'pending' });
    try {
      const answer = await tutorialsApi.checkYouTube(row.link);
      const current = rowsRef.current.find((r) => r.key === row.key);
      if (!current || current.youtubeId !== row.youtubeId) return; // removed or replaced meanwhile
      const own = editing && answer.youtube_id === video.youtube_id; // not a duplicate of itself
      const fillTitle = answer.status === 'ok' && answer.title && !current.title.trim();
      patchRow(row.key, {
        check: answer.status,
        duplicate: own ? null : answer.duplicate,
        ...(fillTitle ? { title: answer.title.slice(0, TITLE_MAX) } : {}),
      });
    } catch {
      patchRow(row.key, { check: 'unchecked' });
    }
  }

  // Editing: a new link or file replaces the one video's media, keeping its details
  function replaceMedia(media) {
    const next = {
      ...rowsRef.current[0], ...media, check: null, duplicate: null, mediaChanged: true, send: 'idle', error: '',
    };
    setRows([next]);
    if (next.kind === 'youtube' && next.youtubeId) check(next);
  }

  function addLinks() {
    if (editing) {
      // The first line, without de-duplication, which would drop the video's own link
      const [fresh] = rowsFromLinks(links.split('\n').find((l) => l.trim()) || '', []);
      if (fresh) replaceMedia({ kind: 'youtube', link: fresh.link, youtubeId: fresh.youtubeId, file: null });
    } else {
      const added = rowsFromLinks(links, rowsRef.current);
      setRows([...rowsRef.current, ...added]);
      added.filter((r) => r.youtubeId).forEach(check);
    }
    setLinks('');
  }

  function addFiles(list) {
    const files = [...(list || [])];
    if (!files.length) return;
    if (editing) {
      replaceMedia({ kind: 'upload', file: files[0], link: '', youtubeId: null });
    } else {
      // A .mov or a photo still becomes a row, so the staff see it was refused
      setRows([...rowsRef.current, ...files.map(rowFromFile)]);
    }
  }

  // ---------- Sending ----------

  // Editing has one row and no per-row select: the picker is where its category changes
  const categoryOf = (row) => (editing ? batchCategory : row.categoryId ?? batchCategory);

  function payload(row) {
    const details = { category: categoryOf(row), title: row.title.trim(), description: row.description.trim() };
    const media = row.kind === 'youtube' ? { youtubeUrl: row.link } : { file: row.file };
    if (!editing) return { ...details, sourceType: row.kind, ...media };
    return {
      ...details,
      ...(row.kind !== video.source_type ? { sourceType: row.kind } : {}),
      ...(row.mediaChanged ? media : {}),
    };
  }

  async function sendRow(key) {
    const row = rowsRef.current.find((r) => r.key === key);
    patchRow(key, { send: 'sending', progress: 0, error: '' });
    const onProgress = (percent) => {
      patchRow(key, percent >= 100 ? { send: 'saving', progress: 100 } : { progress: percent });
    };
    try {
      if (editing) await tutorialsApi.update(video.id, payload(row), onProgress);
      else await tutorialsApi.create(payload(row), onProgress);
      savedRef.current = true;
      patchRow(key, { send: 'done', progress: 100 });
      return true;
    } catch (err) {
      patchRow(key, { send: 'failed', error: err.message });
      return false;
    }
  }

  async function run(keys) {
    if (sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    // Closing or reloading the tab while videos are uploading asks first. Held
    // by the run, not the form: a link elsewhere in the app unmounts the form
    // but the uploads carry on, and closing the tab then would lose the rest.
    const warn = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    try {
      for (const key of keys) {
        if (closedRef.current) break; // Cancel pressed: the one in flight finishes, the rest wait
        if (!rowsRef.current.some((r) => r.key === key)) continue;
        const saved = await sendRow(key); // one at a time, in order
        if (saved && editing) {
          onClose(true);
          return;
        }
      }
    } finally {
      window.removeEventListener('beforeunload', warn);
      sendingRef.current = false;
      setSending(false);
    }
  }

  const publish = () => run(rowsRef.current.filter((r) => r.send !== 'done').map((r) => r.key));
  const retry = (key) => run([key]);

  // ---------- Leaving ----------

  function leave(changed) {
    if (sendingRef.current) {
      const waiting = rowsRef.current.filter((r) => ['idle', 'sending', 'saving'].includes(r.send)).length;
      const message = `${waiting} ${plural(waiting, 'video is', 'videos are')} still uploading. Leave anyway?`;
      if (!window.confirm(message)) return;
      closedRef.current = true;
      onClose(true);
      return;
    }
    onClose(changed || categoriesChangedRef.current);
  }

  function addMore() {
    setRows([]);
    setLinks('');
  }

  // ---------- What can be pressed ----------

  const pending = rows.filter((r) => r.send !== 'done');
  const blocked = pending.some((r) => rowState(r).blocking);
  const noCategory = pending.some((r) => !categoryOf(r));
  const allDone = !editing && rows.length > 0 && pending.length === 0;
  const doneCount = rows.length - pending.length;

  let publishLabel = 'Publish videos';
  if (editing) publishLabel = 'Save';
  else if (pending.length) publishLabel = `Publish ${pending.length} ${plural(pending.length, 'video', 'videos')}`;

  return (
    <div className="tv-form" aria-label={editing ? 'Edit video' : 'Add videos'} role="region">
      <div className="tv-form-head">
        <h3>{editing ? 'Edit video' : 'Add videos'}</h3>
      </div>

      {/* Locked while sending: the queued videos go where the picker says when Publish was pressed */}
      <CategoryPicker
        categories={categories}
        value={batchCategory}
        disabled={sending}
        onChange={setBatchCategory}
        onChanged={categoriesChanged}
      />
      {categoryError && <p className="wt-action-error" role="alert">{categoryError}</p>}

      <div className="tv-media">
        <div className="tv-media-box">
          <label className="tv-field-label" htmlFor="tv-links">YouTube links</label>
          <textarea
            id="tv-links"
            aria-label="YouTube links"
            rows={3}
            placeholder={editing ? 'Paste a new link to replace this video' : 'Paste one or more links, one per line'}
            value={links}
            onChange={(e) => setLinks(e.target.value)}
          />
          <button type="button" className="wt-edit-btn" disabled={!links.trim()} onClick={addLinks}>Add links</button>
        </div>
        <div
          className="tv-media-box tv-drop"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer?.files); }}
        >
          <span className="tv-field-label">MP4 files</span>
          <p>{editing ? 'Drop an MP4 here to replace this video' : 'Drop MP4 files here'}</p>
          <label className="wt-edit-btn tv-file-btn">
            {editing ? 'Choose a file' : 'Choose files'}
            <input
              type="file"
              accept="video/mp4,.mp4"
              multiple={!editing}
              aria-label="MP4 files"
              onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }}
            />
          </label>
        </div>
      </div>
      <p className="tv-note">
        {`Up to 50 MB each. Uploaded videos use ${formatMB(usedBytes)} MB of the 1 GB shared with report photos.`}
      </p>

      {rows.length > 0 && (
        <ol className="tv-rows">
          {rows.map((row) => (
            <VideoEntryRow
              key={row.key}
              row={row}
              categories={categories}
              single={editing}
              onChange={(patch) => patchRow(row.key, patch)}
              onRemove={() => setRows(rowsRef.current.filter((r) => r.key !== row.key))}
              onRetry={() => retry(row.key)}
            />
          ))}
        </ol>
      )}

      {allDone ? (
        <div className="tv-form-foot" role="status">
          <p className="tv-done">{`${doneCount} ${plural(doneCount, 'video', 'videos')} published`}</p>
          <button type="button" className="wt-edit-btn" onClick={addMore}>Add more videos</button>
          <button type="button" className="tv-primary" onClick={() => onClose(true)}>Done</button>
        </div>
      ) : (
        <div className="tv-form-foot">
          {noCategory && <p className="tv-note">Pick a category first.</p>}
          {/* Once something is published there is nothing to cancel: the button reads Done */}
          <button type="button" className="wt-edit-btn" onClick={() => leave(savedRef.current)}>
            {savedRef.current && !sending ? 'Done' : 'Cancel'}
          </button>
          <button
            type="button"
            className="tv-primary"
            disabled={sending || pending.length === 0 || blocked || noCategory}
            onClick={publish}
          >
            {publishLabel}
          </button>
        </div>
      )}
    </div>
  );
}
