import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { historyApi } from '../api/historyApi';
import { barangaysApi } from '../api/barangaysApi';
import { hazardsApi } from '../api/hazardsApi';
import './css/Dashboard.css';
import './css/HistoricalData.css';

const SEVERITY = {
  Red:    { label: 'Extreme',  color: 'var(--db-high)' },
  Orange: { label: 'Moderate', color: 'var(--db-medium)' },
  Green:  { label: 'Low',      color: 'var(--db-low)' },
};

// A blank count in the archive means "nobody counted", which is not zero.
// Printing it as 0 would quietly turn an uncounted incident into a
// casualty-free one.
function countText(label, value) {
  if (value === null || value === undefined) return `${label}: not counted`;
  return `${label}: ${Number(value).toLocaleString()}`;
}

// barangay_detail / hazard_type_detail are nested serializers; if either is
// a GeoFeatureModelSerializer the name sits under .properties instead.
function nestedName(detail) {
  return detail?.name || detail?.properties?.name || null;
}

const PAGE_SIZE = 10;

/**
 * The archive of resolved hazards, one record at a time, filterable by
 * hazard type, barangay and date. The trends, seasonal outlook and barangay
 * likelihood that used to sit here are in Reports › Analytics, which reads
 * the same records.
 */
export default function HistoricalData() {
  const [records, setRecords] = useState([]);
  const [barangays, setBarangays] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [hazardId, setHazardId] = useState('');
  const [barangayId, setBarangayId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    barangaysApi.list()
      .then((geo) => setBarangays(
        (geo.features || []).map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }))
      ))
      .catch(() => {});

    // Read hazard types from the API instead of hardcoding 1/2/3 — the
    // seeded IDs won't survive a reseed, and new types are expected.
    hazardsApi.types()
      .then((types) => setHazardTypes(types || []))
      .catch(() => setHazardTypes([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const params = {};
    if (hazardId)   params.hazard_type = hazardId;
    if (barangayId) params.barangay = barangayId;
    if (dateFrom)   params.date_from = dateFrom;
    if (dateTo)     params.date_to = `${dateTo}T23:59:59`;

    setLoading(true);
    setError('');
    setPage(1);
    historyApi.list(params)
      .then((list) => { if (!cancelled) setRecords(Array.isArray(list) ? list : (list?.results || [])); })
      .catch(() => { if (!cancelled) setError('Could not load historical records. Please try again.'); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [hazardId, barangayId, dateFrom, dateTo]);

  const sampleCount = records.filter((r) => r.is_sample).length;
  const pageCount = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const pageRecords = records.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const hazardTabs = [{ id: '', name: 'All types' }, ...hazardTypes.map((t) => ({ id: t.id, name: t.name }))];

  return (
    <div className="db db-history">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Historical records</h1>
          <p>
            Archived hazard events in Talisay City.{' '}
            <Link to="/app/reports?tab=analytics">Trends and the seasonal outlook are in Reports › Analytics</Link>
          </p>
        </div>

        <div className="db-tabs" role="tablist">
          {hazardTabs.map((h) => (
            <button
              key={h.name} type="button" role="tab" aria-selected={String(hazardId) === String(h.id)}
              className={`db-tab ${String(hazardId) === String(h.id) ? 'is-active' : ''}`}
              onClick={() => setHazardId(h.id)}
            >
              {h.name}
            </button>
          ))}
        </div>

        <div className="db-filters">
          <label className="db-field">Barangay
            <select value={barangayId} onChange={(e) => setBarangayId(e.target.value)}>
              <option value="">All barangays</option>
              {barangays.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <label className="db-field">From
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="db-field">To
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
        </div>

        {error && <p className="db-empty">{error}</p>}

        {!error && sampleCount > 0 && (
          <p className="db-note">
            {sampleCount === records.length ? 'All' : `${sampleCount} of ${records.length}`} records shown are
            sample data generated for testing, not real events.
          </p>
        )}

        {!error && (
          <div className="db-card">
            <h2>{loading ? 'Records' : `${records.length} record${records.length === 1 ? '' : 's'}`}</h2>
            {loading ? (
              <p style={{ color: 'var(--db-soft)' }}>Loading...</p>
            ) : records.length === 0 ? (
              <p className="db-empty">No records match these filters.</p>
            ) : (
              <>
              <div className="db-list">
                {pageRecords.map((r) => (
                  <div key={r.id} className="db-item">
                    <div className="db-item-head">
                      <span className="db-item-title">
                        {nestedName(r.hazard_type_detail) || 'Hazard'}
                        {' - '}
                        {nestedName(r.barangay_detail) || 'Unspecified barangay'}
                        {r.is_sample && <span className="db-badge" style={{ marginLeft: 8 }}>Sample</span>}
                      </span>
                      <span
                        className="db-item-meta"
                        style={{ color: SEVERITY[r.severity_level]?.color, fontWeight: 600 }}
                      >
                        {SEVERITY[r.severity_level]?.label || r.severity_level}
                      </span>
                    </div>
                    <div className="db-item-meta">{r.description}</div>
                    <div className="db-item-meta">
                      {new Date(r.occurred_at).toLocaleDateString()}
                      {' · '}{countText('Casualties', r.total_casualties)}
                      {' · '}{countText('Displaced', r.total_displaced)}
                    </div>
                  </div>
                ))}
              </div>

              {pageCount > 1 && (
                <div className="db-pager">
                  <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={() => setPage(page - 1)} disabled={page === 1}>
                    Previous
                  </button>
                  <span>
                    Page {page} of {pageCount}
                    {' · '}{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, records.length)} of {records.length}
                  </span>
                  <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={() => setPage(page + 1)} disabled={page === pageCount}>
                    Next
                  </button>
                </div>
              )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
