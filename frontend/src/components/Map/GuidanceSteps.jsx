import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { guidanceApi } from '../../api/guidanceApi';
import { hazardsApi } from '../../api/hazardsApi';
import { guidanceFor, hazardKey } from './hazardInfo';

const PHASES = ['Before', 'During', 'After'];

// Hazard types rarely change, so look them up once and reuse the result
let typesPromise = null;
function loadTypes() {
  if (!typesPromise) {
    typesPromise = hazardsApi
      .types()
      .then((data) => (Array.isArray(data) ? data : data?.results || []))
      .catch((err) => {
        typesPromise = null;
        throw err;
      });
  }
  return typesPromise;
}

async function fetchList(hazardTypeId) {
  const data = await guidanceApi.list({ hazard_type: hazardTypeId });
  const list = Array.isArray(data) ? data : data?.results || [];
  return list.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
}

// One line of the body = one numbered step
function stepsFrom(body = '') {
  return body.split('\n').map((s) => s.trim()).filter(Boolean);
}

// Combines several articles' steps into one list with no repeated lines.
// This is the actual fix: two guidance rows for the same hazard type + phase
// (e.g. saved twice, or a stray leftover row) used to just get concatenated,
// so a line stored in both showed up twice.
function dedupe(lines) {
  const seen = new Set();
  return lines.filter((line) => {
    const key = line.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function messageFor(err) {
  const status = err?.response?.status;
  if (status === 401 || status === 403) {
    return 'Only DRRMO Officers and Admins can edit guidance. Try logging in again.';
  }
  return 'Something went wrong. Please try again.';
}

export default function GuidanceSteps({ type }) {
  const { canPublish } = useAuth();
  const [hazardType, setHazardType] = useState(null); // { id, name } from the database
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState('During');
  const [editing, setEditing] = useState(false);
  const [draftSteps, setDraftSteps] = useState(['']);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Load this hazard type's published guidance whenever the tab opens
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setEditing(false);
    setError('');

    (async () => {
      try {
        const types = await loadTypes();
        const match =
          types.find((t) => t.name.toLowerCase() === type.toLowerCase()) ||
          types.find((t) => hazardKey(t.name) === hazardKey(type));
        if (!match) throw new Error('Unknown hazard type');

        const list = await fetchList(match.id);
        if (cancelled) return;
        setHazardType({ id: match.id, name: match.name });
        setArticles(list);
        setPhase(PHASES.find((p) => list.some((a) => a.timeline_phase === p)) || 'During');
      } catch {
        if (!cancelled) {
          setHazardType(null);
          setArticles([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [type]);

  const hasLive = articles.length > 0;
  const phaseArticles = articles.filter((a) => a.timeline_phase === phase);
  const liveSteps = dedupe(phaseArticles.flatMap((a) => stepsFrom(a.body)));
  const steps = hasLive ? liveSteps : guidanceFor(type);

  // What the editor starts with for a given phase — one box per step,
  // duplicates already removed so old repeated rows don't reappear.
  function seedFor(p) {
    const existing = dedupe(
      articles.filter((a) => a.timeline_phase === p).flatMap((a) => stepsFrom(a.body)),
    );
    if (existing.length) return existing;
    return hasLive ? [''] : [...guidanceFor(type)];
  }

  function startEdit() {
    setDraftSteps(seedFor(phase));
    setError('');
    setEditing(true);
  }

  function changePhaseInEditor(p) {
    setPhase(p);
    setDraftSteps(seedFor(p));
    setError('');
  }

  function updateDraftStep(i, value) {
    setDraftSteps((prev) => prev.map((s, idx) => (idx === i ? value : s)));
  }

  function removeDraftStep(i) {
    setDraftSteps((prev) => prev.filter((_, idx) => idx !== i));
  }

  function addDraftStep() {
    setDraftSteps((prev) => [...prev, '']);
  }

  async function save() {
    const lines = dedupe(draftSteps.map((s) => s.trim()).filter(Boolean));
    if (lines.length === 0) {
      setError('Add at least one step.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const body = lines.join('\n');
      const [first, ...rest] = phaseArticles;
      if (first) {
        await guidanceApi.update(first.id, { body });
        for (const extra of rest) await guidanceApi.remove(extra.id); // combined into the first
      } else {
        await guidanceApi.create({
          hazard_type: hazardType.id,
          title: `${hazardType.name} – ${phase}`,
          body,
          timeline_phase: phase,
        });
      }
      setArticles(await fetchList(hazardType.id));
      setEditing(false);
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setSaving(false);
    }
  }

  async function removePhase() {
    if (!window.confirm(`Remove the ${phase} guidance for ${hazardType.name}? Residents will no longer see it.`)) return;
    setSaving(true);
    setError('');
    try {
      for (const a of phaseArticles) await guidanceApi.remove(a.id);
      setArticles(await fetchList(hazardType.id));
      setEditing(false);
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setSaving(false);
    }
  }

  const phaseTabs = (onPick) => (
    <div className="pm-phase-tabs" role="group" aria-label="Guidance phase">
      {PHASES.map((p) => (
        <button
          key={p}
          type="button"
          className={`pm-phase-tab ${phase === p ? 'is-active' : ''}`}
          aria-pressed={phase === p}
          onClick={() => onPick(p)}
        >
          {p}
        </button>
      ))}
    </div>
  );

  if (loading) return <p className="pm-muted">Loading steps…</p>;

  /* ---------- Editor (DRRMO Officer / Admin only) ---------- */
  if (editing) {
    return (
      <div className="pm-guide">
        {phaseTabs(changePhaseInEditor)}
        <div className="pm-guide-form">
          <label>
            {hazardType.name} steps for {phase.toLowerCase()}
          </label>
          <p className="pm-guide-hint">
            One box per step. This applies to every {hazardType.name.toLowerCase()} zone.
          </p>

          <ol className="pm-guide-steps">
            {draftSteps.map((step, i) => (
              <li key={i} className="pm-guide-step">
                <span className="pm-guide-step-num" aria-hidden="true">{i + 1}</span>
                <textarea
                  value={step}
                  onChange={(e) => updateDraftStep(i, e.target.value)}
                  rows={2}
                  aria-label={`Step ${i + 1}`}
                />
                <button
                  type="button"
                  className="pm-guide-remove"
                  aria-label={`Remove step ${i + 1}`}
                  onClick={() => removeDraftStep(i)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
                </button>
              </li>
            ))}
          </ol>

          <button type="button" className="pm-btn pm-btn-outline pm-guide-add" onClick={addDraftStep}>
            + Add step
          </button>

          {phaseArticles.length > 1 && (
            <p className="pm-guide-hint">
              This phase had {phaseArticles.length} separate guidance entries — saving combines
              them into one and removes any repeated steps.
            </p>
          )}
          {error && <p className="pm-guide-error" role="alert">{error}</p>}
        </div>
        <div className="pm-guide-tools">
          <button type="button" className="pm-btn pm-btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save guidance'}
          </button>
          <button type="button" className="pm-btn pm-btn-outline" onClick={() => setEditing(false)} disabled={saving}>
            Cancel
          </button>
          {phaseArticles.length > 0 && (
            <button type="button" className="pm-guide-link" onClick={removePhase} disabled={saving}>
              Remove {phase.toLowerCase()} guidance
            </button>
          )}
        </div>
      </div>
    );
  }

  /* ---------- Normal view (everyone) ---------- */
  return (
    <div className="pm-guide">
      {hasLive && phaseTabs(setPhase)}
      {steps.length > 0 ? (
        <ol className="pm-steps">
          {steps.map((step, i) => (
            <li key={`${i}-${step}`}>{step}</li>
          ))}
        </ol>
      ) : (
        <p className="pm-muted">No guidance has been published for this phase yet.</p>
      )}
      {canPublish && hazardType && (
        <div className="pm-guide-tools">
          <button type="button" className="pm-btn pm-btn-outline" onClick={startEdit}>
            {steps.length > 0 ? 'Edit guidance' : 'Add guidance'}
          </button>
        </div>
      )}
    </div>
  );
}