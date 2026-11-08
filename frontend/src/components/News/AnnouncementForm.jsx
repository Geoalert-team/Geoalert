import React, { useEffect, useRef, useState } from 'react';
import { newsApi } from '../../api/newsApi';

/**
 * Post a new announcement, or edit one: title, text and an optional photo.
 * The server checks everything again (backend apps/news/serializers.py); its
 * messages show under their fields, and what was typed is kept.
 *
 *   post            the announcement being edited, or null for a new one
 *   onSaved(post)   with the saved post as the feed shows it
 *   onClose()
 */
export default function AnnouncementForm({ post, onSaved, onClose }) {
  const editing = Boolean(post);
  const [title, setTitle] = useState(post?.title || '');
  const [body, setBody] = useState(post?.body || '');
  const [photo, setPhoto] = useState(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [preview, setPreview] = useState(post?.photo_url || null);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const titleRef = useRef(null);

  // Focus the title; Escape closes unless saving
  useEffect(() => {
    titleRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape' && !saving) onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose, saving]);

  // A chosen photo's preview, freed when it changes
  useEffect(() => {
    if (!photo) return undefined;
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  function pickPhoto(e) {
    setPhoto(e.target.files?.[0] || null);
    setRemovePhoto(false);
  }

  function dropPhoto() {
    setPhoto(null);
    setPreview(null);
    setRemovePhoto(editing && Boolean(post.photo_url));
  }

  async function save(e) {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      const saved = editing
        ? await newsApi.update(post.id, { title, body, photo, removePhoto })
        : await newsApi.create({ title, body, photo });
      onSaved(saved);
    } catch (err) {
      const data = err.data && typeof err.data === 'object' ? err.data : {};
      const fields = {};
      ['title', 'body', 'photo'].forEach((k) => {
        if (data[k]) fields[k] = Array.isArray(data[k]) ? data[k].join(' ') : String(data[k]);
      });
      if (!Object.keys(fields).length) fields.form = data.error || data.detail || err.message || 'Could not save. Please try again.';
      setErrors(fields);
      setSaving(false);
    }
  }

  return (
    <div className="nw-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !saving) onClose(); }}>
      <form className="nw-dialog" role="dialog" aria-modal="true" aria-labelledby="nw-form-title" onSubmit={save} noValidate>
        <div className="nw-dialog-head">
          <h2 id="nw-form-title">{editing ? 'Edit announcement' : 'New announcement'}</h2>
          <button type="button" className="nw-close" onClick={onClose} aria-label="Close" disabled={saving}>×</button>
        </div>
        {errors.form && <p className="nw-error" role="alert">{errors.form}</p>}

        <label className="nw-field">
          Title
          <input name="title" value={title} maxLength={150} onChange={(e) => setTitle(e.target.value)} ref={titleRef} />
          {errors.title && <span className="nw-field-error">{errors.title}</span>}
        </label>
        <label className="nw-field">
          Text
          <textarea name="body" value={body} maxLength={5000} rows={7} onChange={(e) => setBody(e.target.value)} />
          {errors.body && <span className="nw-field-error">{errors.body}</span>}
        </label>
        <label className="nw-field">
          Photo (optional)
          <input type="file" name="photo" accept="image/jpeg,image/png,image/webp" onChange={pickPhoto} />
          {errors.photo && <span className="nw-field-error">{errors.photo}</span>}
        </label>
        {preview && (
          <div className="nw-preview">
            <img src={preview} alt="Chosen for this announcement" />
            <button type="button" className="nw-btn nw-btn-ghost" onClick={dropPhoto}>Remove photo</button>
          </div>
        )}

        <div className="nw-dialog-actions">
          <button type="button" className="nw-btn nw-btn-ghost" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="nw-btn nw-btn-primary" disabled={saving}>
            {saving ? 'Saving…' : editing ? 'Save' : 'Post'}
          </button>
        </div>
      </form>
    </div>
  );
}
