import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { hazardsApi } from '../../api/hazardsApi';
import { reportsApi } from '../../api/reportApi';
import { hazardColor, hazardIconPath } from '../../components/Map/hazardInfo';
import { Icon, Modal, Toast, fieldErrors, formatDateTime, timeAgo } from './admin/adminShared';
import ActiveZonesCard from '../../components/Resolve/ActiveZonesCard';
import '../css/Dashboard.css';
import '../css/AdminDashboard.css';
import '../css/DRRMODashboard.css';

const STATUS_TABS = [
  { key: 'Pending', label: 'Pending' },
  { key: 'Validated', label: 'Validated' },
  { key: 'Rejected', label: 'Rejected' },
  { key: 'All', label: 'All reports' },
];

const SORTS = {
  newest: { label: 'Newest first', fn: (a, b) => new Date(b.created_at) - new Date(a.created_at) },
  oldest: { label: 'Oldest first', fn: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
  impact: { label: 'Most people affected', fn: (a, b) => affected(b) - affected(a) },
};

function affected(r) {
  return (r.casualties_dead || 0) + (r.casualties_injured || 0) + (r.casualties_missing || 0) + (r.displaced || 0);
}

const typeName = (r) => r.hazard_type_details?.name || 'Incident';
const barangayName = (r) => r.barangay_details?.name || '';
const reporterName = (r) => r.reporter_name || r.submitted_by_name || 'Unknown reporter';

function HazardIcon({ type, size = 'md' }) {
  const color = hazardColor(type) || '#43516a';
  return (
    <span className={`drm-hazard-icon drm-hazard-${size}`} style={{ color, background: `${color}1a` }} aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round">
        <path d={hazardIconPath(type)} />
      </svg>
    </span>
  );
}

function StatusTag({ status }) {
  const tone = { Pending: 'warn', Validated: 'good', Rejected: 'bad' }[status] || 'neutral';
  return <span className={`adm-action adm-action-${tone}`}>{status}</span>;
}

function ImpactChips({ report, large }) {
  const items = [
    { label: 'Dead', value: report.casualties_dead, tone: 'bad' },
    { label: 'Injured', value: report.casualties_injured, tone: 'warn' },
    { label: 'Missing', value: report.casualties_missing, tone: 'warn' },
    { label: 'Displaced', value: report.displaced, tone: 'info' },
  ];
  if (large) {
    return (
      <div className="drm-impact-grid">
        {items.map((i) => (
          <div key={i.label} className={`drm-impact-box ${i.value > 0 ? `is-${i.tone}` : ''}`}>
            <span className="drm-impact-value">{i.value ?? 0}</span>
            <span className="drm-impact-label">{i.label}</span>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="drm-chips">
      {items.map((i) => (
        <span key={i.label} className={`drm-chip ${i.value > 0 ? `is-${i.tone}` : ''}`}>
          <strong>{i.value ?? 0}</strong> {i.label.toLowerCase()}
        </span>
      ))}
    </div>
  );
}

function ReviewDialog({ report, decision, onCancel, onDone }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const validating = decision === 'Validated';

  async function submit() {
    setBusy(true);
    setError('');
    try {
      await reportsApi.review(report.id, { status: decision, review_note: note.trim() });
      onDone(decision);
    } catch (err) {
      setError(fieldErrors(err).form || 'The review could not be saved. Please try again.');
      setBusy(false);
    }
  }

  return (
    <Modal
      title={validating ? 'Validate this report?' : 'Reject this report?'}
      subtitle={`${typeName(report)}${barangayName(report) ? ` · ${barangayName(report)}` : ''} · reported by ${reporterName(report)}`}
      onClose={busy ? () => {} : onCancel}
      width={520}
      labelId="drm-review-title"
      footer={
        <>
          <button type="button" className="adm-btn adm-btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
          <button
            type="button"
            className={`adm-btn ${validating ? 'adm-btn-primary' : 'adm-btn-danger'}`}
            onClick={submit}
            disabled={busy}
          >
            <Icon name={validating ? 'check' : 'x'} size={16} strokeWidth={2.5} />
            {busy ? 'Saving…' : validating ? 'Validate report' : 'Reject report'}
          </button>
        </>
      }
    >
      <div className="drm-review">
        <p className="drm-review-text">
          {validating
            ? 'Validating confirms the incident happened as reported. It moves to your validated reports.'
            : 'Rejecting marks the report as not accurate or not actionable. The reporter can see your reason.'}
        </p>
        <div className="adm-field">
          <label htmlFor="drm-review-note">
            {validating ? 'Note' : 'Reason for rejecting'}
            <span className="adm-optional">{validating ? 'Optional' : 'Recommended'}</span>
          </label>
          <textarea
            id="drm-review-note"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={validating ? 'e.g. Confirmed with the barangay captain by phone.' : 'e.g. Duplicate of an earlier report from the same barangay.'}
            autoFocus
          />
        </div>
        {error && (
          <div className="adm-alert" role="alert"><Icon name="info" size={16} />{error}</div>
        )}
      </div>
    </Modal>
  );
}

function ReportDetail({ report, onClose, onReview }) {
  const place = [report.barangay_details?.name, report.barangay_details?.municipality].filter(Boolean).join(', ');
  return (
    <Modal
      title={`${typeName(report)} report`}
      subtitle={place || 'Barangay not specified'}
      onClose={onClose}
      width={680}
      labelId="drm-detail-title"
      footer={
        report.status === 'Pending' ? (
          <>
            <button type="button" className="adm-btn adm-btn-ghost" onClick={onClose}>Close</button>
            <button type="button" className="adm-btn adm-btn-ghost drm-btn-reject" onClick={() => onReview(report, 'Rejected')}>
              <Icon name="x" size={16} strokeWidth={2.5} /> Reject
            </button>
            <button type="button" className="adm-btn adm-btn-primary" onClick={() => onReview(report, 'Validated')}>
              <Icon name="check" size={16} strokeWidth={2.5} /> Validate
            </button>
          </>
        ) : (
          <button type="button" className="adm-btn adm-btn-primary" onClick={onClose}>Close</button>
        )
      }
    >
      <div className="drm-detail">
        <div className="drm-detail-top">
          <HazardIcon type={typeName(report)} size="lg" />
          <div>
            <StatusTag status={report.status} />
            <p className="drm-detail-when">
              Submitted {formatDateTime(report.created_at)} · {timeAgo(report.created_at)}
            </p>
          </div>
        </div>

        <section className="drm-detail-section">
          <h3>What was reported</h3>
          <p className="drm-detail-desc">{report.description || 'No description given.'}</p>
        </section>

        <section className="drm-detail-section">
          <h3>People affected</h3>
          <ImpactChips report={report} large />
        </section>

        <section className="drm-detail-section">
          <h3>Submission details</h3>
          <dl className="drm-dl">
            <dt>Reported by</dt><dd>{reporterName(report)}</dd>
            {report.agency && (<><dt>Agency</dt><dd>{report.agency}</dd></>)}
            {report.position && (<><dt>Position</dt><dd>{report.position}</dd></>)}
            {report.severity_estimate && (<><dt>Severity estimate</dt><dd>{report.severity_estimate}</dd></>)}
            <dt>Report ID</dt><dd className="adm-mono">{report.id}</dd>
            {report.reviewed_at && (<>
              <dt>Reviewed by</dt><dd>{report.reviewed_by_name || 'Unknown'}</dd>
              <dt>Reviewed</dt><dd>{formatDateTime(report.reviewed_at)}</dd>
            </>)}
            {report.review_note && (<><dt>Review note</dt><dd>{report.review_note}</dd></>)}
          </dl>
        </section>
      </div>
    </Modal>
  );
}

function ReportRow({ report, onOpen, onReview }) {
  const type = typeName(report);
  const brgy = barangayName(report);
  return (
    <li className="drm-report">
      <button type="button" className="drm-report-main" onClick={() => onOpen(report)}>
        <HazardIcon type={type} />
        <div className="drm-report-body">
          <div className="drm-report-head">
            <span className="drm-report-title">
              {type}
              <span className="drm-report-place">{brgy ? ` · ${brgy}` : ' · Barangay not set'}</span>
            </span>
            <StatusTag status={report.status} />
          </div>
          <p className="drm-report-desc">{report.description || 'No description given.'}</p>
          <ImpactChips report={report} />
          <p className="drm-report-meta">
            <span>{reporterName(report)}</span>
            {report.agency && <span>{report.agency}</span>}
            {report.severity_estimate && <span>Severity: {report.severity_estimate}</span>}
            <span title={formatDateTime(report.created_at)}>{timeAgo(report.created_at)}</span>
          </p>
        </div>
      </button>
      <div className="drm-report-actions">
        <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" onClick={() => onOpen(report)}>
          View
        </button>
        {report.status === 'Pending' && (
          <>
            <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm drm-btn-reject" onClick={() => onReview(report, 'Rejected')}>
              <Icon name="x" size={15} strokeWidth={2.5} /> Reject
            </button>
            <button type="button" className="adm-btn adm-btn-primary adm-btn-sm" onClick={() => onReview(report, 'Validated')}>
              <Icon name="check" size={15} strokeWidth={2.5} /> Validate
            </button>
          </>
        )}
      </div>
    </li>
  );
}

export default function DRRMODashboard() {
  const [hazards, setHazards] = useState(null);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(null);

  const [tab, setTab] = useState('Pending');
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [barangayFilter, setBarangayFilter] = useState('');
  const [sort, setSort] = useState('newest');

  const [selected, setSelected] = useState(null); // report in the full view
  const [reviewing, setReviewing] = useState(null); // { report, decision }
  const [toast, setToast] = useState(null);

  const load = useCallback(() => {
    setRefreshing(true);
    return Promise.all([
      reportsApi.list()
        .then((data) => { setReports(Array.isArray(data) ? data : data.results || []); setFailed(false); })
        .catch(() => { setReports([]); setFailed(true); }),
      hazardsApi.list()
        .then(setHazards)
        .catch(() => setHazards({ features: [] })),
    ]).finally(() => {
      setLoading(false);
      setRefreshing(false);
      setUpdatedAt(new Date());
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  const clearToast = useCallback(() => setToast(null), []);

  // Counts for the stat cards and tabs
  const counts = useMemo(() => {
    const c = { Pending: 0, Validated: 0, Rejected: 0, All: reports.length };
    reports.forEach((r) => { if (c[r.status] !== undefined) c[r.status] += 1; });
    return c;
  }, [reports]);

  const pending = useMemo(() => reports.filter((r) => r.status === 'Pending'), [reports]);
  const peopleAffected = pending.reduce((sum, r) => sum + affected(r), 0);
  const oldestPending = pending.reduce((old, r) => (!old || new Date(r.created_at) < new Date(old) ? r.created_at : old), null);
  const activeHazards = hazards?.features?.length;

  // Filter options come from the reports themselves
  const typeOptions = useMemo(() => [...new Set(reports.map(typeName))].sort(), [reports]);
  const barangayOptions = useMemo(() => [...new Set(reports.map(barangayName).filter(Boolean))].sort(), [reports]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return reports
      .filter((r) => tab === 'All' || r.status === tab)
      .filter((r) => !typeFilter || typeName(r) === typeFilter)
      .filter((r) => !barangayFilter || barangayName(r) === barangayFilter)
      .filter((r) => {
        if (!q) return true;
        return [typeName(r), barangayName(r), r.description, reporterName(r), r.agency, r.position, r.severity_estimate, r.id]
          .some((v) => (v || '').toLowerCase().includes(q));
      })
      .sort(SORTS[sort].fn);
  }, [reports, tab, typeFilter, barangayFilter, search, sort]);

  const filtersOn = search || typeFilter || barangayFilter;

  function clearFilters() {
    setSearch('');
    setTypeFilter('');
    setBarangayFilter('');
  }

  function openReview(report, decision) {
    setReviewing({ report, decision });
  }

  function reviewDone(decision) {
    const { report } = reviewing;
    setReviewing(null);
    setSelected(null);
    setToast({
      id: Date.now(),
      tone: 'good',
      message: `${typeName(report)} report${barangayName(report) ? ` from ${barangayName(report)}` : ''} ${decision === 'Validated' ? 'validated' : 'rejected'}.`,
    });
    load();
  }

  return (
    <div className="db adm drm">
      <PublicNavbar />
      <div className="adm-wrap">
        <header className="adm-header">
          <div>
            <p className="adm-eyebrow">Disaster Risk Reduction and Management Office</p>
            <h1>DRRMO dashboard</h1>
            <p className="adm-lede">Review incident reports from barangay personnel and keep track of active hazard zones.</p>
          </div>
          <div className="adm-header-side">
            <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" onClick={load} disabled={refreshing} title="Refresh data">
              <Icon name="refresh" size={15} className={refreshing ? 'adm-spin' : ''} />
              {updatedAt ? `Updated ${updatedAt.toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit' })}` : 'Refresh'}
            </button>
            <Link to="/map" className="adm-btn adm-btn-primary adm-btn-sm drm-map-link">
              Open hazard map <Icon name="arrowRight" size={15} />
            </Link>
          </div>
        </header>

        <div className="adm-metrics">
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-amber"><Icon name="clock" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Awaiting review</span>
              <span className="adm-metric-value">{loading ? '—' : counts.Pending}</span>
              <span className="adm-metric-note">
                {counts.Pending ? `Oldest waiting ${timeAgo(oldestPending).toLowerCase()}` : 'All caught up'}
              </span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-navy"><Icon name="alert" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Active hazard zones</span>
              <span className="adm-metric-value">{activeHazards ?? '—'}</span>
              <span className="adm-metric-note">Shown on the public map</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-blue"><Icon name="users" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">People affected</span>
              <span className="adm-metric-value">{loading ? '—' : peopleAffected}</span>
              <span className="adm-metric-note">Across pending reports</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-green"><Icon name="check" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Validated reports</span>
              <span className="adm-metric-value">{loading ? '—' : counts.Validated}</span>
              <span className="adm-metric-note">{counts.Rejected} rejected</span>
            </div>
          </div>
        </div>

        <ActiveZonesCard onResolved={load} />

        <section className="adm-card adm-card-flush">
          <div className="drm-section-head">
            <div>
              <h2>Incident reports</h2>
              <p>Reports from barangay personnel. Validate or reject each pending report.</p>
            </div>
          </div>

          <nav className="adm-tabs drm-status-tabs" role="tablist" aria-label="Report status">
            {STATUS_TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                className={`adm-tab ${tab === t.key ? 'is-active' : ''}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
                <span className={`adm-tab-count ${t.key === 'Pending' && counts.Pending ? 'drm-count-warn' : ''}`}>{counts[t.key]}</span>
              </button>
            ))}
          </nav>

          <div className="adm-toolbar">
            <div className="adm-search drm-search">
              <Icon name="search" size={16} />
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search description, barangay, reporter, agency…"
                aria-label="Search reports"
              />
            </div>
            <select className="adm-select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Filter by hazard type">
              <option value="">All hazard types</option>
              {typeOptions.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select className="adm-select" value={barangayFilter} onChange={(e) => setBarangayFilter(e.target.value)} aria-label="Filter by barangay">
              <option value="">All barangays</option>
              {barangayOptions.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
            <select className="adm-select" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort reports">
              {Object.entries(SORTS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}
            </select>
          </div>

          <div className="adm-table-meta">
            {loading
              ? 'Loading reports…'
              : `${visible.length} report${visible.length === 1 ? '' : 's'}${filtersOn ? ' match your search' : ''}`}
            {filtersOn && <button type="button" className="adm-link" onClick={clearFilters}>Clear search</button>}
          </div>

          {loading ? (
            <ul className="drm-list">
              {[0, 1, 2].map((i) => (
                <li key={i} className="drm-report drm-report-skeleton">
                  <span className="adm-skeleton" style={{ width: '35%' }} />
                  <span className="adm-skeleton" style={{ width: '80%' }} />
                  <span className="adm-skeleton" style={{ width: '50%' }} />
                </li>
              ))}
            </ul>
          ) : visible.length === 0 ? (
            <div className="adm-empty">
              <Icon name={failed ? 'info' : filtersOn ? 'search' : 'check'} size={28} />
              <p>
                {failed
                  ? 'Reports could not be loaded right now.'
                  : filtersOn
                    ? 'No reports match your search.'
                    : tab === 'Pending'
                      ? 'No reports are waiting for review.'
                      : 'No reports here yet.'}
              </p>
              {failed && <button type="button" className="adm-btn adm-btn-outline adm-btn-sm" onClick={load}>Try again</button>}
            </div>
          ) : (
            <ul className="drm-list">
              {visible.map((r) => (
                <ReportRow key={r.id} report={r} onOpen={setSelected} onReview={openReview} />
              ))}
            </ul>
          )}
        </section>
      </div>

      {selected && !reviewing && (
        <ReportDetail report={selected} onClose={() => setSelected(null)} onReview={openReview} />
      )}
      {reviewing && (
        <ReviewDialog
          report={reviewing.report}
          decision={reviewing.decision}
          onCancel={() => setReviewing(null)}
          onDone={reviewDone}
        />
      )}
      <Toast key={toast?.id} toast={toast} onDone={clearToast} />
    </div>
  );
}