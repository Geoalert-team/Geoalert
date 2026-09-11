import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function Guidance() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: '', hazard_type: '', content: '', is_active: true });
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');

  const load = () => api.guidance().then((d) => setItems(d.results || d || [])).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  function change(e) {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm({ ...form, [e.target.name]: value });
  }

  async function save(e) {
    e.preventDefault();
    setError('');
    try {
      if (editing) await api.updateGuidance(editing, form);
      else await api.createGuidance(form);
      setEditing(null);
      setForm({ title: '', hazard_type: '', content: '', is_active: true });
      load();
    } catch (e) { setError(e.message); }
  }

  function edit(item) {
    setEditing(item.id);
    setForm({
      title: item.title || '',
      hazard_type: item.hazard_type || '',
      content: item.content || '',
      is_active: item.is_active !== false,
    });
  }

  async function remove(id) {
    if (!window.confirm('Delete this guidance item?')) return;
    try { await api.deleteGuidance(id); load(); } catch (e) { setError(e.message); }
  }

  return (
    <div className="feature-page">
      <h2>Safety Guidance</h2>
      <p className="muted">DRRMO Officer can create, edit, activate, and remove safety instructions.</p>

      <form onSubmit={save} className="card">
        <div className="form-grid">
          <div className="field"><label>Title</label><input name="title" value={form.title} onChange={change} required /></div>
          <div className="field"><label>Hazard type</label><input name="hazard_type" value={form.hazard_type} onChange={change} placeholder="Flood / Fire / Landslide" /></div>
          <div className="field full"><label>Safety instructions</label><textarea name="content" rows="6" value={form.content} onChange={change} required /></div>
          <label className="check"><input type="checkbox" name="is_active" checked={form.is_active} onChange={change} /> Active</label>
        </div>
        <div className="error-text">{error}</div>
        <button className="btn primary">{editing ? 'Save changes' : 'Publish guidance'}</button>
        {editing && <button type="button" className="btn" onClick={() => { setEditing(null); setForm({ title: '', hazard_type: '', content: '', is_active: true }); }}>Cancel</button>}
      </form>

      <div className="card">
        <h3>Guidance content</h3>
        {items.map((item) => (
          <div className="list-row" key={item.id}>
            <div><strong>{item.title}</strong><div className="muted">{item.hazard_type}</div><p>{item.content}</p></div>
            <div className="actions"><button className="btn" onClick={() => edit(item)}>Edit</button><button className="btn" onClick={() => remove(item.id)}>Delete</button></div>
          </div>
        ))}
      </div>
    </div>
  );
}
