import React, { useState } from 'react';
import { tutorialsApi } from '../../api/tutorialsApi';
import DeleteCategoryButton from './DeleteCategoryButton';

/**
 * Pick the category a batch of videos goes in, or make, edit or delete one,
 * without leaving the Add videos form. A category has a name and an optional
 * description (shown under the name on the page). Deleting one deletes its
 * videos too, after the warning (DeleteCategoryButton).
 *
 *   categories   [{ id, name, description, video_count }], A to Z
 *   value        the chosen category's id, or null
 *   onChange(id) select a category (null for none)
 *   onChanged()  a category was created, edited or deleted: fetch them again
 *   disabled     locked, e.g. while the form's videos are sending
 *
 * No <form> here: the picker sits inside the Add videos form.
 */
export default function CategoryPicker({ categories, value, onChange, onChanged, disabled = false }) {
  const [mode, setMode] = useState(null); // null | 'new' | 'edit'
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const busy = working || disabled;
  const chosen = categories.find((c) => c.id === value) || null;

  function open(next) {
    setMode(next);
    setName(next === 'edit' ? chosen.name : '');
    setDescription(next === 'edit' ? chosen.description || '' : '');
    setError('');
  }

  async function submit() {
    const clean = name.trim();
    if (!clean || busy) return;
    setWorking(true);
    setError('');
    const fields = { name: clean, description: description.trim() };
    try {
      if (mode === 'new') {
        const created = await tutorialsApi.createCategory(fields);
        onChange(created.id);
      } else {
        await tutorialsApi.updateCategory(chosen.id, fields);
      }
      setMode(null);
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setWorking(false);
    }
  }

  function onKey(e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
      e.preventDefault();
      submit();
    } else if (e.key === 'Escape') {
      e.stopPropagation();
      setMode(null);
    }
  }

  return (
    <div className="tv-picker">
      <div className="tv-picker-row">
        <span className="tv-field-label" aria-hidden="true">Category</span>
        <select aria-label="Category" value={value || ''} disabled={busy}
          onChange={(e) => onChange(e.target.value || null)}>
          <option value="">Choose a category</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {mode === null && (
          <>
            <button type="button" className="wt-edit-btn" disabled={busy} onClick={() => open('new')}>
              + New category
            </button>
            {chosen && (
              <button type="button" className="wt-edit-btn" disabled={busy} onClick={() => open('edit')}>
                Edit category
              </button>
            )}
            {chosen && (
              <DeleteCategoryButton
                category={chosen}
                label="Delete"
                disabled={busy}
                onDeleted={() => { onChange(null); onChanged(); }}
                onError={setError}
              />
            )}
          </>
        )}
      </div>

      {mode && (
        <div className="tv-picker-edit">
          <input
            type="text"
            aria-label={mode === 'new' ? 'New category name' : 'Category name'}
            placeholder={mode === 'new' ? 'Name, e.g. Typhoon Response' : 'Name'}
            value={name}
            maxLength={60}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={onKey}
          />
          <textarea
            aria-label="Category description"
            placeholder="Description (optional): what these videos teach"
            rows={2}
            value={description}
            maxLength={300}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={onKey}
          />
          <div className="tv-picker-row">
            <button type="button" className="wt-edit-btn" disabled={busy || !name.trim()} onClick={submit}>
              {mode === 'new' ? 'Create' : 'Save'}
            </button>
            <button type="button" className="wt-edit-btn" disabled={busy} onClick={() => setMode(null)}>Cancel</button>
          </div>
        </div>
      )}

      {error && <p className="wt-action-error" role="alert">{error}</p>}
    </div>
  );
}
