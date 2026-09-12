import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { guidanceApi } from '../api/mockApi';
import Navbar from '../components/Navbar';

const HAZARD_OPTIONS = ['Flood', 'Fire', 'Landslide'];

export default function GuidanceLibrary() {
  const { user, canPublish } = useAuth();
  const [articles, setArticles] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [title, setTitle] = useState('');
  const [hazardType, setHazardType] = useState(HAZARD_OPTIONS[0]);
  const [body, setBody] = useState('');

  useEffect(() => { refresh(); }, []);
  async function refresh() { setArticles(await guidanceApi.list()); }

  function startNew() { setEditing(null); setTitle(''); setHazardType(HAZARD_OPTIONS[0]); setBody(''); setShowForm(true); }
  function startEdit(a) { setEditing(a.id); setTitle(a.title); setHazardType(a.hazard_type); setBody(a.body); setShowForm(true); }

  async function save(e) {
    e.preventDefault();
    if (editing) await guidanceApi.update(editing, { title, hazard_type: hazardType, body });
    else await guidanceApi.create({ title, hazard_type: hazardType, body, created_by: user?.full_name || user?.email });
    setShowForm(false);
    refresh();
  }

  async function remove(id) {
    if (window.confirm('Delete this guidance article?')) { await guidanceApi.remove(id); refresh(); }
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
          Mock data â€” no backend yet (apps/guidance is still empty in Django).
        </p>

        {showForm && (
          <form onSubmit={save} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 18, marginBottom: 24 }}>
            <h3 style={{ marginTop: 0 }}>{editing ? 'Edit article' : 'New article'}</h3>
            <div className="field">
              <label>Title</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} required />
            </div>
            <div className="field">
              <label>Hazard type</label>
              <select value={hazardType} onChange={(e) => setHazardType(e.target.value)}>
                {HAZARD_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
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
                <span style={{ fontSize: 11.5, color: 'var(--accent)' }}>{a.hazard_type}</span>
              </div>
              <p style={{ fontSize: 13, margin: '8px 0' }}>{a.body}</p>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                By {a.created_by} Â· updated {new Date(a.updated_at).toLocaleDateString()}
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
