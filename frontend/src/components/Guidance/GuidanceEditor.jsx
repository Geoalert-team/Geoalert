import React, { useState } from 'react';
import { guidanceApi } from '../../api/guidanceApi';
import { guidanceError, stepsFrom } from '../../utils/guidance';
import './css/GuidanceEditor.css';

/**
 * Write or edit one guidance article in place, on the What to do page.
 * DRRMO Officers and Admins only; the page decides who sees it.
 *
 * A title and one box per step. Steps are saved as the lines of the body,
 * which is how the page (and the map panel) read them back.
 *
 * Props:
 *   article        { id, title, body } to edit, or null for a new one
 *   hazardTypeId   hazard type id for a new article
 *   phase          'Before' | 'During' | 'After' for a new article
 *   onSaved        called after a successful save
 *   onCancel       called when the officer leaves without saving
 */
export default function GuidanceEditor({ article = null, hazardTypeId, phase, onSaved, onCancel }) {
  const [title, setTitle] = useState(article?.title || '');
  const [steps, setSteps] = useState(() => {
    const existing = article ? stepsFrom(article.body) : [];
    return existing.length ? existing : [''];
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const setStep = (i, value) => setSteps((prev) => prev.map((s, idx) => (idx === i ? value : s)));
  const addStep = () => setSteps((prev) => [...prev, '']);
  // One box always stays, so there is somewhere to type
  const removeStep = (i) => setSteps((prev) => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : ['']));
  const moveStep = (i, by) => setSteps((prev) => {
    const next = [...prev];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    return next;
  });

  async function save(e) {
    e.preventDefault();
    const cleanTitle = title.trim();
    const lines = steps.map((s) => s.trim()).filter(Boolean);
    if (!cleanTitle) { setError('Add a title.'); return; }
    if (!lines.length) { setError('Add at least one step.'); return; }

    setSaving(true);
    setError('');
    try {
      const body = lines.join('\n');
      if (article) {
        await guidanceApi.update(article.id, { title: cleanTitle, body });
      } else {
        await guidanceApi.create({ hazard_type: hazardTypeId, title: cleanTitle, body, timeline_phase: phase });
      }
      onSaved();
    } catch (err) {
      setError(guidanceError(err));
      setSaving(false);
    }
  }

  return (
    <form className="ge" onSubmit={save} aria-label={article ? `Edit ${article.title}` : 'New guidance'}>
      <label className="ge-field">
        Title
        <input type="text" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
      </label>

      <p className="ge-label">Steps</p>
      <ol className="ge-steps">
        {steps.map((step, i) => (
          <li key={i} className="ge-step">
            <span className="ge-step-num" aria-hidden="true">{i + 1}</span>
            <textarea value={step} rows={2} aria-label={`Step ${i + 1}`} onChange={(e) => setStep(i, e.target.value)} />
            <span className="ge-step-tools">
              <button type="button" aria-label={`Move step ${i + 1} up`} onClick={() => moveStep(i, -1)} disabled={i === 0}>↑</button>
              <button type="button" aria-label={`Move step ${i + 1} down`} onClick={() => moveStep(i, 1)} disabled={i === steps.length - 1}>↓</button>
              <button type="button" aria-label={`Remove step ${i + 1}`} onClick={() => removeStep(i)}>✕</button>
            </span>
          </li>
        ))}
      </ol>
      <button type="button" className="ge-add" onClick={addStep}>+ Add step</button>

      {error && <p className="ge-error" role="alert">{error}</p>}

      <div className="ge-actions">
        <button type="submit" className="ge-save" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
        <button type="button" className="ge-cancel" onClick={onCancel} disabled={saving}>Cancel</button>
      </div>
    </form>
  );
}
