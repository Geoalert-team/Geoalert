import React, { useEffect, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { useAuth } from '../context/AuthContext';
import { guidanceApi } from '../api/guidanceApi';
import { hazardsApi } from '../api/hazardsApi';
import './css/Dashboard.css';

const PHASES = ['Before', 'During', 'After'];

export default function GuidanceLibrary() {
  const { canPublish } = useAuth();
  const [guidance, setGuidance] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [filterType, setFilterType] = useState('All');
  const [loading, setLoading] = useState(true);

  const [form, setForm] = useState({ hazard_type: '', title: '', body: '', timeline_phase: 'Before' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    refresh();
    hazardsApi.types().then(setHazardTypes).catch(() => {});
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const data = await guidanceApi.list();
      setGuidance(data.results || data);
    } catch {
      setGuidance([]);
    } finally {
      setLoading(false);
    }
  }

  async function createGuidance(e) {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await guidanceApi.create(form);
      setForm({ hazard_type: '', title: '', body: '', timeline_phase: 'Before' });
      refresh();
    } catch (err) {
      setError(err.message || 'Could not save guidance');
    } finally {
      setSaving(false);
    }
  }

  async function remove(id) {
    if (!window.confirm('Delete this guidance entry?')) return;
    await guidanceApi.remove(id);
    refresh();
  }

  const visible = guidance.filter(
    (g) => filterType === 'All' || (g.hazard_type_detail?.name || g.hazard_type) === filterType
  );

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Guidance library</h1>
          <p>Before / during / after safety steps shown to residents on the map.</p>
        </div>

        <div className="db-tabs" role="tablist">
          {['All', ...hazardTypes.map((t) => t.name)].map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={filterType === name}
              className={`db-tab ${filterType === name ? 'is-active' : ''}`}
              onClick={() => setFilterType(name)}>
              {name}
            </button>
          ))}
        </div>

        <div className={canPublish ? 'db-grid-2' : ''}>
          {canPublish && (
            <form onSubmit={createGuidance} className="db-card">
              <h2>Add guidance</h2>
              <div className="field">
                <label>Hazard type</label>
                <select required value={form.hazard_type} onChange={(e) => setForm({ ...form, hazard_type: e.target.value })}>
                  <option value="">Select…</option>
                  {hazardTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Timeline</label>
                <select value={form.timeline_phase} onChange={(e) => setForm({ ...form, timeline_phase: e.target.value })}>
                  {PHASES.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Title</label>
                <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </div>
              <div className="field">
                <label>Guidance text</label>
                <textarea rows={4} required value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
              </div>
              {error && <p className="error-text">{error}</p>}
              <button className="btn primary" disabled={saving}>{saving ? 'Saving…' : 'Publish guidance'}</button>
            </form>
          )}

          <div className="db-card">
            <h2>All entries</h2>
            {loading ? (
              <p className="db-empty">Loading…</p>
            ) : visible.length === 0 ? (
              <p className="db-empty">No guidance entries yet.</p>
            ) : (
              <div className="db-list">
                {visible.map((g) => (
                  <div key={g.id} className="db-item">
                    <div className="db-item-head">
                      <span className="db-item-title">{g.title}</span>
                      <span className="db-badge">{g.timeline_phase}</span>
                    </div>
                    <div className="db-item-meta">{g.hazard_type_detail?.name || g.hazard_type}</div>
                    <p style={{ fontSize: '.92rem', margin: '8px 0' }}>{g.body}</p>
                    {canPublish && (
                      <button className="db-btn db-btn-danger" onClick={() => remove(g.id)}>Delete</button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}