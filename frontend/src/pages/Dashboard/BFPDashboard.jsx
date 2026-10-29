import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { hazardsApi } from '../../api/hazardsApi';
import { historyApi } from '../../api/historyApi';
import { reportsApi } from '../../api/reportApi';
import ActiveZonesCard from '../../components/Resolve/ActiveZonesCard';
import RecordDetail from '../../components/History/RecordDetail';
import { Icon, formatDateTime, timeAgo } from './admin/adminShared';
import { HazardIcon, ReportPhotos, StatusTag } from './reportShared';
import { placeLabel } from './fireReport';
import '../css/Dashboard.css';
import '../css/AdminDashboard.css';
import '../css/DRRMODashboard.css';

const RECENT = 5;
const REPORTS_PAGE = 5;
const REPORT_TABS = [
  { key: 'Pending', label: 'Waiting for DRRMO' },
  { key: 'All', label: 'All fire reports' },
];

function isFire(feature) {
  const p = feature.properties || {};
  const type = p.hazard_type_name || p.hazard_type_details?.name || p.hazard_type_detail?.name || '';
  return type.toLowerCase() === 'fire';
}

/**
 * One barangay fire report, read-only: DRRMO validates, rejects and pushes.
 * Photos open full size, as in DRRMO's queue.
 */
function FireReportRow({ report }) {
  const barangay = report.barangay_details?.name;
  return (
    <li className="drm-report">
      <div className="drm-report-static">
        <HazardIcon type="Fire" />
        <div className="drm-report-body">
          <div className="drm-report-head">
            <span className="drm-report-title">
              Fire<span className="drm-report-place">{barangay ? ` · ${barangay}` : ' · Barangay not set'}</span>
            </span>
            <StatusTag status={report.status} />
          </div>
          <p className="drm-report-desc">{report.description || 'No description given.'}</p>
          <ReportPhotos report={report} alt="Photo sent with the fire report" />
          <p className="drm-report-meta">
            <span>{report.reporter_name || report.submitted_by_name || 'Unknown reporter'}</span>
            {report.position && <span>{report.position}</span>}
            {report.started_at && <span>Started {formatDateTime(report.started_at)}</span>}
            {placeLabel(report) && <span>{placeLabel(report)}</span>}
            <span title={formatDateTime(report.created_at)}>Sent {timeAgo(report.created_at).toLowerCase()}</span>
          </p>
          {report.status === 'Rejected' && report.review_note && (
            <p className="drm-report-meta"><span>DRRMO: {report.review_note}</span></p>
          )}
        </div>
      </div>
      {report.hazard_zone && (
        <div className="drm-report-actions">
          <Link className="adm-btn adm-btn-ghost adm-btn-sm" to={`/map?zone=${report.hazard_zone}`}>View map</Link>
        </div>
      )}
    </li>
  );
}

/**
 * BFP personnel's dashboard: barangays' fire reports as soon as they are
 * sent (read-only; DRRMO decides them), the fires live on the map, closed
 * here (or from the map's panel) with the BFP figures, and the fires already
 * filed. A BFP account does nothing else; publishing, withdrawing and the
 * other hazards stay with DRRMO, and the server holds BFP to fires on every
 * call. Built from the DRRMO dashboard's pieces and look.
 */
export default function BFPDashboard() {
  const [fires, setFires] = useState(null); // active fire features
  const [reports, setReports] = useState(null); // fire reports, newest first
  const [reportTab, setReportTab] = useState('Pending');
  const [reportPage, setReportPage] = useState(1);
  const [recent, setRecent] = useState(null); // { count, results } of fire records
  const [thisYear, setThisYear] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(null);
  // The record open in full, and the row to return focus to on close
  const [openId, setOpenId] = useState(null);
  const opener = useRef(null);
  const closeRecord = useCallback(() => {
    setOpenId(null);
    opener.current?.focus();
  }, []);

  const load = useCallback(() => {
    setRefreshing(true);
    const year = new Date().getFullYear();
    return Promise.all([
      hazardsApi.list()
        .then((geo) => setFires((geo.features || []).filter(isFire)))
        .catch(() => setFires([])),
      // The server sends BFP the fire reports only
      reportsApi.list()
        .then((data) => setReports((Array.isArray(data) ? data : data.results || [])
          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))))
        .catch(() => setReports([])),
      historyApi.page({ hazard_type_name: 'Fire', limit: RECENT })
        .then(setRecent)
        .catch(() => setRecent({ count: 0, results: [] })),
      historyApi.page({ hazard_type_name: 'Fire', date_from: `${year}-01-01`, limit: 1 })
        .then((data) => setThisYear(data.count))
        .catch(() => setThisYear(null)),
    ]).finally(() => {
      setRefreshing(false);
      setUpdatedAt(new Date());
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  const latest = recent?.results?.[0];
  const waiting = reports ? reports.filter((r) => r.status === 'Pending') : [];
  const shownReports = reportTab === 'Pending' ? waiting : reports || [];
  const reportPages = Math.max(1, Math.ceil(shownReports.length / REPORTS_PAGE));
  const currentReportPage = Math.min(reportPage, reportPages);
  const pageReports = shownReports.slice((currentReportPage - 1) * REPORTS_PAGE, currentReportPage * REPORTS_PAGE);

  return (
    <div className="db adm drm">
      <PublicNavbar />
      <div className="adm-wrap">
        <header className="adm-header">
          <div>
            <p className="adm-eyebrow">Bureau of Fire Protection</p>
            <h1>BFP dashboard</h1>
            <p className="adm-lede">
              Fire reports from barangays as they come in, and the fires on the hazard map right now. When one
              is out, close it with the BFP figures and it is filed in the fire history.
            </p>
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
            <span className="adm-metric-icon adm-metric-amber"><Icon name="flame" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Active fires</span>
              <span className="adm-metric-value">{fires ? fires.length : '—'}</span>
              <span className="adm-metric-note">Shown on the public map</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-navy"><Icon name="alert" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Waiting for DRRMO</span>
              <span className="adm-metric-value">{reports ? waiting.length : '—'}</span>
              <span className="adm-metric-note">Fire reports not on the map yet</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-green"><Icon name="check" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Filed this year</span>
              <span className="adm-metric-value">{thisYear ?? '—'}</span>
              <span className="adm-metric-note">Fires in the history since January</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-blue"><Icon name="clock" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Last fire</span>
              <span className="adm-metric-value">{latest ? timeAgo(latest.occurred_at) : '—'}</span>
              <span className="adm-metric-note">{latest ? formatDateTime(latest.occurred_at) : 'None on record'}</span>
            </div>
          </div>
        </div>

        <section className="adm-card adm-card-flush">
          <div className="drm-section-head">
            <div>
              <h2>Fire reports</h2>
              <p>
                What barangays report, as soon as they send it. DRRMO validates each one and puts it on the map,
                which sends the fire alert.
              </p>
            </div>
          </div>

          <nav className="adm-tabs drm-status-tabs" role="tablist" aria-label="Fire reports">
            {REPORT_TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={reportTab === t.key}
                className={`adm-tab ${reportTab === t.key ? 'is-active' : ''}`}
                onClick={() => { setReportTab(t.key); setReportPage(1); }}
              >
                {t.label}
                <span className={`adm-tab-count ${t.key === 'Pending' && waiting.length ? 'drm-count-warn' : ''}`}>
                  {t.key === 'Pending' ? waiting.length : (reports || []).length}
                </span>
              </button>
            ))}
          </nav>

          {reports === null ? (
            <div className="adm-empty"><p>Loading fire reports…</p></div>
          ) : shownReports.length === 0 ? (
            <div className="adm-empty">
              <Icon name="check" size={28} />
              <p>{reportTab === 'Pending' ? 'No fire report is waiting for DRRMO.' : 'No fire reports yet.'}</p>
            </div>
          ) : (
            <>
              <ul className="drm-list">
                {pageReports.map((r) => <FireReportRow key={r.id} report={r} />)}
              </ul>
              {reportPages > 1 && (
                <div className="adm-pager">
                  <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" disabled={currentReportPage <= 1}
                    onClick={() => setReportPage(currentReportPage - 1)}>
                    <Icon name="chevronLeft" size={16} /> Previous
                  </button>
                  <span>Page {currentReportPage} of {reportPages}</span>
                  <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" disabled={currentReportPage >= reportPages}
                    onClick={() => setReportPage(currentReportPage + 1)}>
                    Next <Icon name="chevronRight" size={16} />
                  </button>
                </div>
              )}
            </>
          )}
        </section>

        <ActiveZonesCard fireOnly onResolved={load} />

        <section className="adm-card adm-card-flush">
          <div className="drm-section-head">
            <div>
              <h2>Recent fires</h2>
              <p>
                The latest fires in the history, with the figures they were closed with.{' '}
                <Link to="/app/history">See every fire record</Link>
              </p>
            </div>
          </div>
          <div style={{ padding: '0 20px 20px' }}>
            {recent === null ? (
              <p className="db-hint">Loading…</p>
            ) : recent.results.length === 0 ? (
              <p className="db-empty">No fires are on record yet.</p>
            ) : (
              <div className="db-list">
                {recent.results.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className="db-item db-item-clickable db-record-row"
                    onClick={(e) => { opener.current = e.currentTarget; setOpenId(r.id); }}
                  >
                    <span className="db-item-head">
                      <span className="db-item-title">
                        Fire - {r.barangay_detail?.name || r.barangay_detail?.properties?.name || 'Unspecified barangay'}
                        {r.is_sample && <span className="db-badge" style={{ marginLeft: 8 }}>Sample</span>}
                      </span>
                      <span className="db-record-open" aria-hidden="true">View details ›</span>
                    </span>
                    {r.description && <span className="db-item-meta">{r.description}</span>}
                    <span className="db-item-meta">{formatDateTime(r.occurred_at)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {openId && <RecordDetail recordId={openId} onClose={closeRecord} />}
    </div>
  );
}
