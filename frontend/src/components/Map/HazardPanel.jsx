import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { severityInfo, hazardIconPath, hazardColor, DRRMO_HOTLINE } from './hazardInfo';
import GuidanceSteps from './GuidanceSteps';
import ResolveHazardForm from '../Resolve/ResolveHazardForm';
import { historyApi } from '../../api/historyApi';
// The resolve form is built from db- classes; .db-scope below supplies the
// tokens so it looks right inside the map panel too.
import '../../pages/css/Dashboard.css';

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'todo', label: 'What to do' },
  { key: 'history', label: 'History' },
];

function formatDate(iso) {
  if (!iso) return 'Not recorded';
  return new Date(iso).toLocaleDateString('en-PH', { year: 'numeric', month: 'long', day: 'numeric' });
}

const HISTORY_PAGE = 5; // records fetched per "Show more"

// Pages already fetched this session, keyed "barangayId|type" ("" = all types),
// so flipping between chips or pins doesn't refetch. Cleared when a hazard is
// resolved, since that adds a record.
const historyCache = new Map();
export function clearHistoryCache() {
  historyCache.clear();
}

// A blank count means nobody counted, which is not the same as zero
function countText(label, value) {
  if (value === null || value === undefined) return `${label}: not counted`;
  return `${label}: ${Number(value).toLocaleString()}`;
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

// Every past incident in this hazard's barangay, one hazard type at a time,
// loaded a page at a time
function PastIncidents({ item }) {
  const [type, setType] = useState(item.type); // '' = all types
  const [entry, setEntry] = useState(null);    // { count, items, typeCounts }
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const barangayId = item.barangayId;

  // Start on the selected hazard's type whenever another hazard is opened
  useEffect(() => {
    setType(item.type);
  }, [item.id, item.type]);

  const key = `${barangayId}|${type}`;

  const loadPage = useCallback((current) => {
    setLoading(true);
    setFailed(false);
    return historyApi
      .page({
        barangay: barangayId,
        hazard_type_name: type || undefined,
        limit: HISTORY_PAGE,
        offset: current ? current.items.length : 0,
      })
      .then((data) => {
        const next = {
          count: data.count,
          typeCounts: data.type_counts || [],
          items: [...(current ? current.items : []), ...(data.results || [])],
        };
        historyCache.set(key, next);
        return next;
      })
      .finally(() => setLoading(false));
  }, [barangayId, type, key]);

  useEffect(() => {
    if (barangayId == null) return undefined;
    const cached = historyCache.get(key);
    if (cached) {
      setEntry(cached);
      return undefined;
    }
    let cancelled = false;
    setEntry(null);
    loadPage(null)
      .then((next) => { if (!cancelled) setEntry(next); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [barangayId, key, loadPage]);

  function showMore() {
    loadPage(entry).then(setEntry).catch(() => setFailed(true));
  }

  if (barangayId == null) {
    return <p className="pm-muted">This hazard isn't inside a mapped barangay, so there are no area records to show.</p>;
  }
  if (failed && !entry) return <p className="pm-muted">Past records could not be loaded right now. Please try again later.</p>;
  if (!entry) return <p className="pm-muted">Loading past records…</p>;

  // One chip per type on record, the selected hazard's type first, then All
  const counts = new Map(entry.typeCounts.map((t) => [t.name, t.count]));
  const names = [item.type, ...entry.typeCounts.map((t) => t.name).filter((n) => n !== item.type)];
  const total = entry.typeCounts.reduce((sum, t) => sum + t.count, 0);
  const chips = [
    ...names.map((n) => ({ value: n, label: n, count: counts.get(n) || 0 })),
    ...(names.length > 1 ? [{ value: '', label: 'All', count: total }] : []),
  ];
  const left = entry.count - entry.items.length;
  const what = type ? `${type.toLowerCase()} incident` : 'incident';

  return (
    <>
      <div className="pm-history-chips" role="group" aria-label="Hazard type">
        {chips.map((c) => (
          <button
            key={c.value || 'all'}
            type="button"
            className={`pm-history-chip ${type === c.value ? 'is-active' : ''}`}
            aria-pressed={type === c.value}
            onClick={() => setType(c.value)}
          >
            {c.label} <span>{c.count}</span>
          </button>
        ))}
      </div>

      <p className="pm-history-summary">
        {entry.count === 0
          ? `No past ${what}s on record in ${item.location}.`
          : `${plural(entry.count, `past ${what}`)} on record in ${item.location}, newest first.`}
      </p>

      {entry.items.length > 0 && (
        <ul className="pm-timeline pm-history-list">
          {entry.items.map((r) => {
            const rsev = severityInfo(r.severity_level);
            const rtype = r.hazard_type_detail?.name || r.hazard_type_detail?.properties?.name;
            return (
              <li key={r.id}>
                <span className="pm-timeline-dot" style={{ background: rsev.color }} />
                <div>
                  <strong>
                    {formatDate(r.occurred_at)}
                    {r.is_sample && <em className="pm-history-sample">Sample</em>}
                  </strong>
                  <span>{!type && rtype ? `${rtype}, ` : ''}{rsev.label}</span>
                  {r.description && <p className="pm-history-desc">{r.description}</p>}
                  <span className="pm-history-counts">
                    {countText('People displaced', r.total_displaced)} · {countText('Casualties', r.total_casualties)}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {left > 0 && (
        <button type="button" className="pm-history-more" onClick={showMore} disabled={loading}>
          {loading ? 'Loading…' : `Show ${Math.min(HISTORY_PAGE, left)} more (${left} left)`}
        </button>
      )}
      {failed && entry && <p className="pm-muted">More records could not be loaded. Please try again.</p>}
    </>
  );
}

// Every hazard zone covering the spot the user clicked, most serious first, so
// overlapping zones can be read one after another instead of only the top pin.
function HazardStack({ stack, current, onPick }) {
  const pos = Math.max(0, stack.findIndex((h) => h.id === current.id));
  const step = (by) => onPick(stack[(pos + by + stack.length) % stack.length]);

  return (
    <nav className="pm-stack" aria-label="Hazards at this spot">
      <div className="pm-stack-head">
        <strong>{stack.length} hazards here</strong>
        <div className="pm-stack-step">
          <button type="button" onClick={() => step(-1)} aria-label="Previous hazard">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
          </button>
          <span aria-live="polite">{pos + 1} of {stack.length}</span>
          <button type="button" onClick={() => step(1)} aria-label="Next hazard">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
          </button>
        </div>
      </div>
      <ul className="pm-stack-list">
        {stack.map((h) => {
          const hsev = severityInfo(h.severity);
          const active = h.id === current.id;
          return (
            <li key={h.id}>
              <button
                type="button"
                className={`pm-stack-item ${active ? 'is-active' : ''}`}
                aria-current={active ? 'true' : undefined}
                onClick={() => onPick(h)}
                style={active ? { borderColor: hsev.color } : undefined}
              >
                <span className="pm-stack-icon" style={{ color: hazardColor(h.type) }} aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d={hazardIconPath(h.type)} /></svg>
                </span>
                <span className="pm-stack-text">
                  <strong>{h.type}</strong>
                  <small>
                    <span className="pm-overlap-dot" style={{ background: hsev.color }} />
                    {hsev.label}
                  </small>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

// Slides in from the left (desktop) or up from the bottom (mobile).
// stack: the hazards at the clicked spot (including item); onPick switches between them.
export default function HazardPanel({ item, open, onClose, onResolved, stack = [], onPick }) {
  const [tab, setTab] = useState('overview');
  const [resolving, setResolving] = useState(false);
  const closeRef = useRef(null);
  const { canPublish } = useAuth();

  // Go back to the Overview tab and move focus into the panel whenever a new pin is chosen
  useEffect(() => {
    setTab('overview');
    setResolving(false);
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [item?.id, open]);

  const sev = item ? severityInfo(item.severity) : null;
  const others = item ? stack.filter((h) => h.id !== item.id) : [];
  const worst = stack[0]; // the stack is sorted most serious first

  // Only DRRMO/Admin can close out a hazard, and only one that's still live.
  const canResolve =
    canPublish && item && !item.sample && (item.status || 'Active') === 'Active';

  return (
    <aside className={`pm-panel ${open ? 'is-open' : ''}`} aria-label="Hazard details">
      {item && (
        <div className="pm-panel-inner">
          {/* ---------- Header ---------- */}
          <div className="pm-panel-head">
            <div className="pm-panel-icon" style={{ background: sev.tint, color: hazardColor(item.type) }} aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d={hazardIconPath(item.type)} /></svg>
            </div>
            <div className="pm-panel-title">
              <h2>{item.location}</h2>
              <p>{item.type} hazard in Talisay City</p>
            </div>
            <button ref={closeRef} type="button" className="pm-panel-close" onClick={onClose}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              <span className="pm-visually-hidden">Close details</span>
            </button>
          </div>

          {others.length > 0 && onPick && <HazardStack stack={stack} current={item} onPick={onPick} />}

          <span className="pm-badge" style={{ background: sev.tint, color: sev.text }}>
            <span className="pm-badge-dot" style={{ background: sev.color }} />
            {sev.label}
          </span>

          {item.sample && (
            <p className="pm-sample-note">Sample data generated for testing. This is not a real hazard.</p>
          )}

          {/* ---------- Tabs ---------- */}
          <div className="pm-tabs" role="tablist" aria-label="Hazard information">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`pm-tab-${t.key}`}
                aria-selected={tab === t.key}
                aria-controls={`pm-tabpanel-${t.key}`}
                className={`pm-tab ${tab === t.key ? 'is-active' : ''}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div
            className="pm-tabpanel"
            role="tabpanel"
            id={`pm-tabpanel-${tab}`}
            aria-labelledby={`pm-tab-${tab}`}
          >
            {tab === 'overview' && (
              <>
                <h3>{sev.label} {item.type.toLowerCase()} advisory</h3>
                <p>{item.description || 'No description has been added for this area yet.'}</p>
                <div className="pm-callout" style={{ background: sev.tint, borderColor: sev.color, color: sev.text }}>
                  <strong>{sev.label}:</strong> {sev.advice}
                </div>
                {others.length > 0 && (
                  <div className="pm-overlap">
                    <strong>
                      This area overlaps {others.length === 1 ? 'another hazard zone' : `${others.length} other hazard zones`}.
                    </strong>
                    <p>
                      {worst && worst.id !== item.id
                        ? <>Follow the most serious one: {worst.type.toLowerCase()}, {severityInfo(worst.severity).label.toLowerCase()}.</>
                        : <>This is the most serious one here, so follow its advice.</>}
                    </p>
                  </div>
                )}

                <dl className="pm-facts">
                  <div>
                    <dt>Status</dt>
                    <dd>{item.status || 'Active'}</dd>
                  </div>
                  <div>
                    <dt>Active since</dt>
                    <dd>{formatDate(item.activatedAt)}</dd>
                  </div>
                </dl>

                {/* ---------- DRRMO: close the hazard out ---------- */}
                {canResolve && (
                  <div className="db-scope db-embed">
                    {resolving ? (
                      <ResolveHazardForm
                        zoneId={item.id}
                        title={`${item.type} · ${item.location}`}
                        onCancel={() => setResolving(false)}
                        onResolved={(zone) => {
                          setResolving(false);
                          clearHistoryCache(); // the resolved zone is now a past record
                          onResolved?.(zone);
                        }}
                      />
                    ) : (
                      <button type="button" className="db-btn db-btn-outline" onClick={() => setResolving(true)}>
                        Mark as resolved
                      </button>
                    )}
                  </div>
                )}
              </>
            )}

            {tab === 'todo' && (
              <>
                <h3>What to do</h3>
                <GuidanceSteps type={item.type} />
                <div className="pm-panel-actions">
                  <a className="pm-btn pm-btn-primary" href={DRRMO_HOTLINE.tel}>
                    Call DRRMO {DRRMO_HOTLINE.label}
                  </a>
                  {/* Carries the hazard through, so the guidance library opens on this
                      hazard instead of whatever it shows by default. */}
                  <Link
                    className="pm-btn pm-btn-outline"
                    to={`/what-to-do?hazard=${encodeURIComponent(item.type)}`}
                  >
                    Full safety guide
                  </Link>
                </div>
              </>
            )}

            {tab === 'history' && (
              <>
                <h3>Now</h3>
                <ul className="pm-timeline">
                  <li>
                    <span className="pm-timeline-dot" style={{ background: sev.color }} />
                    <div>
                      <strong>Marked {sev.label.toLowerCase()}</strong>
                      <span>{formatDate(item.activatedAt)}</span>
                    </div>
                  </li>
                </ul>
                <h3 className="pm-history-heading">Area disaster history</h3>
                <PastIncidents item={item} />
              </>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}