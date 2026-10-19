import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { FieldMarksSection } from './FieldMarks';
import { severityInfo, hazardIconPath, hazardColor, DRRMO_HOTLINE } from './hazardInfo';
import GuidanceSteps from './GuidanceSteps';
import ResolveHazardForm from '../Resolve/ResolveHazardForm';
import RetractHazardForm from '../Resolve/RetractHazardForm';
import { hazardsApi } from '../../api/hazardsApi';
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
/**
 * Who received this zone's latest alert and who has opened it, by barangay,
 * for the officers deciding whether to phone anyone. Collapsed to one line
 * until opened.
 */
function DeliveryReceipts({ zoneId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    setData(null);
    setError('');
    hazardsApi.receipts(zoneId)
      .then((d) => live && setData(d))
      .catch((err) => live && setError(err.message || 'Could not load who has read the alert.'));
    return () => { live = false; };
  }, [zoneId]);

  if (error) return <p className="db-hint">{error}</p>;
  if (!data) return <p className="db-hint">Checking who has read the alert…</p>;
  if (!data.alert) return <p className="db-hint">No alert has been sent for this zone yet.</p>;

  const unread = data.sent - data.opened;
  return (
    <details className="hp-receipts">
      <summary>
        Alert opened by <strong>{data.opened} of {data.sent}</strong>
        {unread > 0 ? ` · ${unread} not yet` : ' · everyone'}
      </summary>
      <ul>
        {data.groups.map((g) => (
          <li key={g.name}>
            <span className="hp-receipts-name">{g.name}</span>{' '}
            <span className={g.opened === g.sent ? 'hp-receipts-ok' : 'hp-receipts-wait'}>
              {g.opened}/{g.sent} opened
            </span>
            {g.unread.length > 0 && (
              <small>Not opened: {g.unread.join(', ')}</small>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

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
export default function HazardPanel({
  item, open, onClose, onResolved, onRetracted, onVerified, onReshape, onChanged, stack = [], onPick,
  marks = null, onMark, marking = null,
}) {
  const [tab, setTab] = useState('overview');
  // 'resolve' when the hazard is over, 'retract' when it should never have
  // been published. Only one form is ever open.
  const [closing, setClosing] = useState(null);
  // Ground confirmation, for barangay personnel standing in the hazard
  const [answering, setAnswering] = useState(null); // 'Confirmed' | 'Disputed'
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [verifyError, setVerifyError] = useState('');
  // DRRMO changing the severity of a live zone
  const [sevPick, setSevPick] = useState(null);
  const [sevBusy, setSevBusy] = useState(false);
  const [sevMsg, setSevMsg] = useState('');
  // DRRMO's reply to a dispute
  const [reviewNote, setReviewNote] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState('');
  const closeRef = useRef(null);
  const { canPublish, user } = useAuth();

  // Go back to the Overview tab and move focus into the panel whenever a new pin is chosen
  useEffect(() => {
    setTab('overview');
    setClosing(null);
    setAnswering(null);
    setNote('');
    setVerifyError('');
    setReviewNote('');
    setReviewError('');
    setSevPick(null);
    setSevMsg('');
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [item?.id, open]);

  const sev = item ? severityInfo(item.severity) : null;
  const others = item ? stack.filter((h) => h.id !== item.id) : [];
  const worst = stack[0]; // the stack is sorted most serious first

  // Only DRRMO/Admin can close out a hazard, and only one that's still live.
  // Sample hazards are resolvable on purpose: they are real rows in the
  // database, and walking a seeded hazard through to a historical record is
  // how the resolve flow gets demonstrated without waiting for a real one.
  const canResolve = canPublish && item && (item.status || 'Active') === 'Active';

  // Only barangay personnel confirm, and only while the hazard is live. The
  // backend also checks the zone actually touches their barangay — the panel
  // can't know that reliably, so it offers the buttons and shows the server's
  // refusal if they are not the right barangay.
  const role = user?.role?.name || user?.role;
  const canConfirm =
    role === 'Barangay_Personnel' && item && (item.status || 'Active') === 'Active';

  // This user's own barangay's answer, if they gave one. Other barangays
  // the zone crosses keep their own answers.
  const answers = item?.verifications || [];
  const myAnswer = answers.find((v) => String(v.barangay) === String(user?.assigned_barangay));
  const disputed = item?.verificationStatus === 'Disputed';
  const canReview = canResolve && disputed && !item?.reviewNote;

  async function saveSeverity() {
    if (!item || !sevPick || sevPick === item.severity) { setSevPick(null); return; }
    setSevBusy(true);
    setSevMsg('');
    try {
      const zone = await hazardsApi.update(item.id, { severity: sevPick });
      setSevPick(null);
      // Raising to Extreme waits for a second officer, like a new Extreme alert
      if (zone.approval?.required) {
        const due = zone.approval.due_at
          ? new Date(zone.approval.due_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
          : '';
        setSevMsg(`Sent for approval. Another officer has to approve raising this to Extreme${due ? `, or it is raised on its own at ${due}` : ''}.`);
      } else {
        setSevMsg('Severity changed. Every barangay will be asked to confirm it again.');
      }
      onChanged?.(zone);
    } catch (err) {
      setSevMsg(err?.message || 'Could not change the severity.');
    } finally {
      setSevBusy(false);
    }
  }

  async function submitReview() {
    if (!item) return;
    setReviewing(true);
    setReviewError('');
    try {
      const zone = await hazardsApi.review(item.id, reviewNote.trim());
      setReviewNote('');
      onVerified?.(zone);
    } catch (err) {
      setReviewError(err?.message || 'Could not save the review.');
    } finally {
      setReviewing(false);
    }
  }

  async function submitVerification() {
    if (!answering || !item) return;
    setSaving(true);
    setVerifyError('');
    try {
      const zone = await hazardsApi.verify(item.id, { status: answering, note: note.trim() });
      setAnswering(null);
      setNote('');
      onVerified?.(zone);
    } catch (err) {
      // axiosClient flattens the server error into err.message
      setVerifyError(err?.message || 'Could not save that. Check your connection and try again.');
    } finally {
      setSaving(false);
    }
  }

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
                {/* The hatched ring on the map, said in words */}
                {item.cordonM && (
                  <div className="pm-cordon-note" style={{ borderColor: sev.color }}>
                    <strong>Cordon: keep clear within {item.cordonM} m</strong>
                    <p>
                      The hatched ring around this {item.type.toLowerCase()} is a safety cordon.
                      Leave it and stay out until officials say it is safe.
                    </p>
                  </div>
                )}
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

                {/* Ground confirmation, one line per barangay that answered.
                    Deliberately silent while nobody has: "nobody has been out
                    to look yet" is not news to a reader standing in the
                    hazard, and it crowded the panel. */}
                {answers.length > 0 && answers.map((v) => (
                  <p key={v.barangay} className={v.status === 'Disputed' ? 'pm-disputed' : 'pm-verified'}>
                    <strong>
                      {v.status === 'Disputed' ? 'Disputed' : 'Confirmed'} by {v.barangay_name}
                    </strong>
                    {v.answered_by_name ? ` (${v.answered_by_name})` : ''}
                    {v.note ? ` — "${v.note}"` : '.'}
                  </p>
                ))}
                {answers.length > 0 && disputed && !item.reviewNote && (
                  <p className="pm-disputed">Treat this advisory with caution until DRRMO reviews it.</p>
                )}
                {disputed && item.reviewNote && (
                  <p className="pm-verified">
                    <strong>DRRMO reviewed the dispute and kept this alert</strong>
                    {item.reviewedByName ? ` (${item.reviewedByName})` : ''}: "{item.reviewNote}"
                  </p>
                )}

                {/* Answers given before each barangay kept its own */}
                {answers.length === 0 && item.verificationStatus === 'Confirmed' && (
                  <p className="pm-verified">
                    <strong>Confirmed on the ground</strong>
                    {item.verifiedByName ? ` by ${item.verifiedByName}` : ''}
                    {item.verificationNote ? ` — "${item.verificationNote}"` : '.'}
                  </p>
                )}
                {answers.length === 0 && item.verificationStatus === 'Disputed' && (
                  <p className="pm-disputed">
                    <strong>Disputed by the barangay</strong>
                    {item.verificationNote ? ` — "${item.verificationNote}"` : '.'}
                    {' '}Treat this advisory with caution until DRRMO reviews it.
                  </p>
                )}

                {/* ---------- Spots checked on the ground (staff) ---------- */}
                {marks && (item.status || 'Active') === 'Active' && (
                  <FieldMarksSection marks={marks} onMark={onMark} marking={marking} />
                )}

                {/* ---------- Barangay: answer for the ground ---------- */}
                {canConfirm && (
                  <div className="db-scope db-embed">
                    {answering ? (
                      <div className="db-confirm">
                        <p>
                          {answering === 'Confirmed'
                            ? 'Confirm that this hazard is on the ground as described?'
                            : 'Report that this hazard is not there as described?'}
                        </p>
                        <label className="db-field" htmlFor="pm-verify-note">
                          What did you see? (optional)
                          <textarea
                            id="pm-verify-note"
                            rows={2}
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            placeholder={answering === 'Confirmed'
                              ? 'Water about knee deep along the national road'
                              : 'Road is clear, no landslide seen as of this morning'}
                          />
                        </label>
                        {verifyError && <p className="db-error" role="alert">{verifyError}</p>}
                        <div className="db-btn-row">
                          <button
                            type="button"
                            className="db-btn db-btn-primary db-btn-sm"
                            onClick={submitVerification}
                            disabled={saving}
                          >
                            {saving
                              ? 'Saving…'
                              : answering === 'Confirmed' ? 'Yes, confirm' : 'Yes, dispute'}
                          </button>
                          <button
                            type="button"
                            className="db-btn db-btn-outline db-btn-sm"
                            onClick={() => { setAnswering(null); setVerifyError(''); }}
                            disabled={saving}
                          >
                            Go back
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="db-hint" style={{ marginBottom: 8 }}>
                          {myAnswer
                            ? `Your barangay ${myAnswer.status === 'Confirmed' ? 'confirmed' : 'disputed'} this. Has it changed?`
                            : 'You are barangay personnel. Is this hazard there as described?'}
                        </p>
                        {verifyError && <p className="db-error" role="alert">{verifyError}</p>}
                        <div className="db-btn-row">
                          <button
                            type="button"
                            className="db-btn db-btn-outline db-btn-sm"
                            onClick={() => setAnswering('Confirmed')}
                          >
                            {myAnswer?.status === 'Disputed'
                              ? 'Change to confirmed'
                              : myAnswer?.status === 'Confirmed' ? 'Confirm again' : 'Confirm it is there'}
                          </button>
                          <button
                            type="button"
                            className="db-btn db-btn-outline db-btn-sm"
                            onClick={() => setAnswering('Disputed')}
                          >
                            {myAnswer?.status === 'Confirmed' ? 'Change to disputed' : 'Dispute'}
                          </button>
                        </div>
                      </>
                    )}
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

                {/* ---------- DRRMO: a raise to Extreme waiting for approval ---------- */}
                {canResolve && item.pendingSeverity === 'Red' && (
                  <p className="pm-disputed">
                    <strong>Raise to Extreme waiting for a second officer.</strong>{' '}
                    It stays {sev.label.toLowerCase()} until another officer approves it.
                  </p>
                )}

                {/* ---------- DRRMO: answer a dispute ---------- */}
                {canReview && !closing && (
                  <div className="db-scope db-embed">
                    <p className="db-hint" style={{ marginBottom: 8 }}>
                      A barangay disputed this. If you checked and it stays as it
                      is, say why. Otherwise withdraw it or edit its area.
                    </p>
                    <label className="db-field" htmlFor="pm-review-note">
                      What did you check?
                      <textarea
                        id="pm-review-note"
                        rows={2}
                        value={reviewNote}
                        onChange={(e) => setReviewNote(e.target.value)}
                        placeholder="Called the barangay captain; water is still rising upstream"
                      />
                    </label>
                    {reviewError && <p className="db-error" role="alert">{reviewError}</p>}
                    <button
                      type="button"
                      className="db-btn db-btn-outline db-btn-sm"
                      onClick={submitReview}
                      disabled={reviewing || reviewNote.trim().length < 5}
                    >
                      {reviewing ? 'Saving…' : 'Keep it, with this note'}
                    </button>
                  </div>
                )}

                {/* ---------- DRRMO: close the hazard out ---------- */}
                {canResolve && (
                  <div className="db-scope db-embed">
                    <DeliveryReceipts zoneId={item.id} />
                    {closing === 'resolve' && (
                      <ResolveHazardForm
                        zoneId={item.id}
                        title={`${item.type} · ${item.location}`}
                        onCancel={() => setClosing(null)}
                        onResolved={(zone) => {
                          setClosing(null);
                          clearHistoryCache(); // the resolved zone is now a past record
                          onResolved?.(zone);
                        }}
                      />
                    )}

                    {closing === 'retract' && (
                      <RetractHazardForm
                        zoneId={item.id}
                        title={`${item.type} · ${item.location}`}
                        onCancel={() => setClosing(null)}
                        onRetracted={(zone) => {
                          setClosing(null);
                          // No history cache to clear: a withdrawal files no
                          // historical record, which is the whole point.
                          onRetracted?.(zone);
                        }}
                      />
                    )}

                    {!closing && (
                      <>
                        <div className="db-btn-row">
                          <button type="button" className="db-btn db-btn-outline" onClick={() => setClosing('resolve')}>
                            Mark as resolved
                          </button>
                          <button type="button" className="db-btn db-btn-outline" onClick={() => setClosing('retract')}>
                            Published in error
                          </button>
                          {onReshape && (
                            <button type="button" className="db-btn db-btn-outline" onClick={() => onReshape(item)}>
                              Edit area
                            </button>
                          )}
                          <button type="button" className="db-btn db-btn-outline" onClick={() => { setSevMsg(''); setSevPick(item.severity); }}>
                            Change severity
                          </button>
                        </div>
                        {sevPick && (
                          <div className="db-confirm" style={{ marginTop: 10 }}>
                            <p>New severity</p>
                            <div className="db-btn-row">
                              {['Green', 'Orange', 'Red'].map((code) => (
                                <button
                                  key={code}
                                  type="button"
                                  className={`db-btn db-btn-sm ${sevPick === code ? 'db-btn-primary' : 'db-btn-outline'}`}
                                  aria-pressed={sevPick === code}
                                  onClick={() => setSevPick(code)}
                                >
                                  {severityInfo(code).label}
                                </button>
                              ))}
                            </div>
                            {sevPick === 'Red' && item.severity !== 'Red' && (
                              <p className="db-hint" style={{ marginTop: 6 }}>
                                Raising to Extreme needs a second officer. It stays
                                at its current level until then.
                              </p>
                            )}
                            <div className="db-btn-row" style={{ marginTop: 8 }}>
                              <button type="button" className="db-btn db-btn-primary db-btn-sm" onClick={saveSeverity} disabled={sevBusy || sevPick === item.severity}>
                                {sevBusy ? 'Saving…' : 'Save'}
                              </button>
                              <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={() => setSevPick(null)} disabled={sevBusy}>
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                        {sevMsg && <p className="db-hint" role="status" style={{ marginTop: 8 }}>{sevMsg}</p>}
                        <p className="db-hint" style={{ marginTop: 8 }}>
                          Resolve a hazard that happened and is over — it becomes a
                          historical record. Withdraw one that should never have gone
                          out; nothing is filed as an incident.
                        </p>
                      </>
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