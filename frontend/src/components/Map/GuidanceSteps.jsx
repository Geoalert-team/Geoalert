import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { guidanceApi } from '../../api/guidanceApi';
import { hazardsApi } from '../../api/hazardsApi';
import { stepsFrom } from '../../utils/guidance';
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

// Combines several articles' steps into one list with no repeated lines.
// Two guidance rows for the same hazard type + phase (e.g. saved twice, or a
// stray leftover row) used to just get concatenated, so a line stored in
// both showed up twice.
function dedupe(lines) {
  const seen = new Set();
  return lines.filter((line) => {
    const key = line.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * The published guidance for one hazard type, in the map's hazard panel:
 * pick a phase, read its steps. Read-only here. DRRMO Officers and Admins
 * edit guidance on the What to do page, article by article, so the link
 * below opens that page at this hazard and phase.
 */
export default function GuidanceSteps({ type }) {
  const { canPublish } = useAuth();
  const [hazardType, setHazardType] = useState(null); // { id, name } from the database
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState('During');

  // Load this hazard type's published guidance whenever the tab opens
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

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

  if (loading) return <p className="pm-muted">Loading steps…</p>;

  return (
    <div className="pm-guide">
      {hasLive && (
        <div className="pm-phase-tabs" role="group" aria-label="Guidance phase">
          {PHASES.map((p) => (
            <button
              key={p}
              type="button"
              className={`pm-phase-tab ${phase === p ? 'is-active' : ''}`}
              aria-pressed={phase === p}
              onClick={() => setPhase(p)}
            >
              {p}
            </button>
          ))}
        </div>
      )}
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
          <Link
            className="pm-btn pm-btn-outline"
            to={`/what-to-do?hazard=${encodeURIComponent(hazardType.name)}&phase=${phase.toLowerCase()}`}
          >
            Edit on What to do
          </Link>
        </div>
      )}
    </div>
  );
}
