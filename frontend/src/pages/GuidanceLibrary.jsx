import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { guidanceApi } from '../api/guidanceApi';
import { hazardsApi } from '../api/hazardsApi';
import Navbar from '../components/Navbar';

const PHASE_OPTIONS = ['Before', 'During', 'After'];

export default function GuidanceLibrary() {
  const { canPublish } = useAuth();
  const [articles, setArticles] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [title, setTitle] = useState('');
  const [hazardType, setHazardType] = useState('');
  const [phase, setPhase] = useState(PHASE_OPTIONS[0]);
  const [body, setBody] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    refresh();
    loadHazardTypes();
  }, []);

  async function refresh() {
    try {
      setArticles(await guidanceApi.list());
    } catch (err) {
      setError(err.message || 'Failed to load guidance articles');
    }
  }

  async function loadHazardTypes() {
    try {
      const data = await hazardsApi.types();
      // Defensive: handle both a plain array and a paginated { results: [...] } shape.
      const list = Array.isArray(data) ? data : data.results || [];
      setHazardTypes(list);
      if (list.length && !hazardType) setHazardType(list[0].id);
    } catch (err) {
      setError(err.message || 'Failed to load hazard types');
    }
  }

  function startNew() {
    setEditing(null);
    setTitle('');
    setHazardType(hazardTypes[0]?.id || '');
    setPhase(PHASE_OPTIONS[0]);
    setBody('');
    setShowForm(true);
  }

  function startEdit(a) {
    setEditing(a.id);
    setTitle(a.title);
    setHazardType(a.hazard_type);
    setPhase(a.timeline_phase);
    setBody(a.body);
    setShowForm(true);
  }

  async function save(e) {
    e.preventDefault();
    setError(null);
    const payload = {
      title,
      hazard_type: hazardType,
      timeline_phase: phase,
      body,
    };
    try {
      if (editing) await guidanceApi.update(editing, payload);
      else await guidanceApi.create(payload);
      setShowForm(false);
      refresh();
    } catch (err) {
      setError(err.message || 'Failed to save article');
    }
  }

  async function remove(id) {
    if (!window.confirm('Unpublish this guidance article?')) return;
    try {
      await guidanceApi.remove(id);
      refresh();
    } catch (err) {
      setError(err.message || 'Failed to delete article');
    }
  }

  function hazardTypeName(id) {
    return hazardTypes.find((h) => h.id === id)?.name || id;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 780, margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <h2 style={{ margin: 0 }}>Guidance library</h2>
          {canPublish && <button className="btn primary" onClick={startNew}>Add guidance</button>}
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          Live data from the guidance API.
        </p>

        {error && (
          <div style={{ color: 'var(--danger, #c0392b)', fontSize: 13, marginBottom: 12 }}>{error}</div>
        )}

        {showForm && (
          <form onSubmit={save} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 18, marginBottom: 24 }}>
            <h3 style={{ marginTop: 0 }}>{editing ? 'Edit article' : 'New article'}</h3>
            <div className="field">
              <label>Title</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} required />
            </div>
            <div className="field">
              <label>Hazard type</label>
              <select value={hazardType} onChange={(e) => setHazardType(e.target.value)} required>
                {hazardTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Timeline phase</label>
              <select value={phase} onChange={(e) => setPhase(e.target.value)}>
                {PHASE_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Guidance text</label>
              <textarea rows={4} required value={body} onChange={(e) => setBody(e.target.value)} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn" type="button" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn primary">{editing ? 'Save changes' : 'Publish'}</button>
            </div>
          </form>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {articles.map((a) => (
            <div key={a.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                <strong>{a.title}</strong>
                <span style={{ fontSize: 11.5, color: 'var(--accent)' }}>
                  {a.hazard_type_detail?.name || hazardTypeName(a.hazard_type)} · {a.timeline_phase}
                </span>
              </div>
              <p style={{ fontSize: 13, margin: '8px 0' }}>{a.body}</p>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                Updated {new Date(a.updated_at).toLocaleDateString()}
              </div>
              {canPublish && (
                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                  <button className="btn" onClick={() => startEdit(a)}>Edit</button>
                  <button className="btn" onClick={() => remove(a.id)}>Delete</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}