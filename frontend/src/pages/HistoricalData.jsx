import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import RecordDetail from '../components/History/RecordDetail';
import HistoryExport from '../components/History/HistoryExport';
import HistoryImport from '../components/History/HistoryImport';
import { useAuth } from '../context/AuthContext';
import { historyApi } from '../api/historyApi';
import { barangaysApi } from '../api/barangaysApi';
import { hazardsApi } from '../api/hazardsApi';
import './css/Dashboard.css';
import './css/HistoricalData.css';

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

// The list runs newest first, so each row shows its time as well as its date
function when(iso) {
  return new Date(iso).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

const PAGE_SIZE = 10;

/**
 * The archive of resolved hazards, one record at a time, filterable by
 * hazard type, barangay and date. Each record opens in full (RecordDetail):
 * the BFP figures for a fire, and what the barangay reported. The list shows
 * no severity: a record is what happened, not how its alert was graded.
 * The trends, seasonal outlook and barangay likelihood that used to sit here
 * are in Reports › Analytics, which reads the same records.
 * DRRMO staff can export the filtered records in the BFP fire log's columns
 * (HistoryExport), picking the hazard types to include. BFP personnel see
 * and export the fires only; the server holds their export to fires too.
 * DRRMO staff can also import the BFP fire log or the flood and landslide
 * log (HistoryImport).
 */
export default function HistoricalData() {
  const auth = useAuth();
  const canExport = Boolean(auth?.canPublish || auth?.canCloseFires);
  const canImport = Boolean(auth?.canPublish);
  const fireOnly = (auth?.user?.role?.name || auth?.user?.role) === 'BFP_Personnel';
  const [records, setRecords] = useState([]);
  const [barangays, setBarangays] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [hazardId, setHazardId] = useState('');
  const [barangayId, setBarangayId] = useState('');
  // One purok of the barangay: '' for all of them, 'none' for the records
  // that name no purok. Its counts (all time, all types) fill the options.
  const [purokId, setPurokId] = useState('');
  const [purokCounts, setPurokCounts] = useState(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  // The record open in full, and the row to return focus to on close
  const [openId, setOpenId] = useState(null);
  const opener = useRef(null);
  const closeRecord = useCallback(() => {
    setOpenId(null);
    opener.current?.focus();
  }, []);
  // The export window, and the button to return focus to on close
  const [exporting, setExporting] = useState(false);
  const exportButton = useRef(null);
  const closeExport = useCallback(() => {
    setExporting(false);
    exportButton.current?.focus();
  }, []);
  // The import window, likewise; reloaded bumps after records are added
  const [importing, setImporting] = useState(false);
  const [reloaded, setReloaded] = useState(0);
  const importButton = useRef(null);
  const closeImport = useCallback(() => {
    setImporting(false);
    importButton.current?.focus();
  }, []);
  const imported = useCallback((result) => {
    if (result.new > 0) setReloaded((n) => n + 1);
  }, []);

  useEffect(() => {
    barangaysApi.list()
      .then((geo) => setBarangays(
        (geo.features || []).map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }))
      ))
      .catch(() => {});

    // Read hazard types from the API instead of hardcoding 1/2/3 — the
    // seeded IDs won't survive a reseed, and new types are expected.
    hazardsApi.types()
      .then((types) => setHazardTypes((types || []).filter((t) => !fireOnly || t.name.toLowerCase() === 'fire')))
      .catch(() => setHazardTypes([]));
  }, [fireOnly]);

  // The barangay's purok counts (a new barangay starts on all its puroks:
  // the Barangay select resets purokId as it changes)
  useEffect(() => {
    setPurokCounts(null);
    if (!barangayId) return undefined;
    let cancelled = false;
    historyApi.area({ barangay: barangayId, period: 'all', ...(fireOnly ? { types: 'Fire' } : {}) })
      .then((data) => { if (!cancelled) setPurokCounts(data); })
      .catch(() => { /* no counts: the Purok filter stays hidden */ });
    return () => { cancelled = true; };
  }, [barangayId, fireOnly]);

  // The Barangay, Purok and date filters, which the export shares
  const filters = useMemo(() => {
    const params = {};
    if (barangayId) params.barangay = barangayId;
    if (barangayId && purokId) params.purok = purokId;
    if (dateFrom)   params.date_from = dateFrom;
    if (dateTo)     params.date_to = `${dateTo}T23:59:59`;
    return params;
  }, [barangayId, purokId, dateFrom, dateTo]);

  useEffect(() => {
    let cancelled = false;
    const params = fireOnly
      ? { ...filters, hazard_type_name: 'Fire' }
      : hazardId ? { ...filters, hazard_type: hazardId } : filters;

    setLoading(true);
    setError('');
    setPage(1);
    historyApi.list(params)
      .then((list) => { if (!cancelled) setRecords(Array.isArray(list) ? list : (list?.results || [])); })
      .catch(() => { if (!cancelled) setError('Could not load historical records. Please try again.'); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [hazardId, filters, fireOnly, reloaded]);

  const sampleCount = records.filter((r) => r.is_sample).length;
  const pageCount = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const pageRecords = records.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // BFP has the one type, so no tabs
  const hazardTabs = fireOnly ? [] : [{ id: '', name: 'All types' }, ...hazardTypes.map((t) => ({ id: t.id, name: t.name }))];

  return (
    <div className="db db-history">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>{fireOnly ? 'Fire records' : 'Historical records'}</h1>
          {fireOnly ? (
            <p>Archived fires in Talisay City, with the BFP figures each was closed with.</p>
          ) : (
            <p>
              Archived hazard events in Talisay City.{' '}
              <Link to="/app/reports?tab=analytics">Trends and the seasonal outlook are in Reports › Analytics</Link>
            </p>
          )}
        </div>

        {hazardTabs.length > 0 && (
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
        )}

        <div className="db-filters">
          <label className="db-field">Barangay
            <select value={barangayId} onChange={(e) => { setBarangayId(e.target.value); setPurokId(''); }}>
              <option value="">All barangays</option>
              {barangays.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          {barangayId && purokCounts && (
            <label className="db-field">Purok
              <select value={purokId} onChange={(e) => setPurokId(e.target.value)}>
                <option value="">All puroks ({purokCounts.count})</option>
                {purokCounts.puroks.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.count})</option>)}
                {purokCounts.unplaced > 0 && (
                  <option value="none">Purok not recorded ({purokCounts.unplaced})</option>
                )}
              </select>
            </label>
          )}
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
            <div className="db-history-head">
              <h2>{loading ? 'Records' : `${records.length} record${records.length === 1 ? '' : 's'}`}</h2>
              <div className="db-btn-row">
                {canImport && (
                  <button
                    ref={importButton}
                    type="button"
                    className="db-btn db-btn-outline db-btn-sm"
                    onClick={() => setImporting(true)}
                  >
                    Import
                  </button>
                )}
                {canExport && (
                  <button
                    ref={exportButton}
                    type="button"
                    className="db-btn db-btn-outline db-btn-sm"
                    onClick={() => setExporting(true)}
                    disabled={hazardTypes.length === 0}
                  >
                    Export
                  </button>
                )}
              </div>
            </div>
            {loading ? (
              <p style={{ color: 'var(--db-soft)' }}>Loading...</p>
            ) : records.length === 0 ? (
              <p className="db-empty">No records match these filters.</p>
            ) : (
              <>
              <div className="db-list">
                {pageRecords.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className="db-item db-item-clickable db-record-row"
                    onClick={(e) => { opener.current = e.currentTarget; setOpenId(r.id); }}
                  >
                    <span className="db-item-head">
                      <span className="db-item-title">
                        {nestedName(r.hazard_type_detail) || 'Hazard'}
                        {' - '}
                        {nestedName(r.barangay_detail) || 'Unspecified barangay'}
                        {r.is_sample && <span className="db-badge" style={{ marginLeft: 8 }}>Sample</span>}
                      </span>
                      <span className="db-record-open" aria-hidden="true">View details ›</span>
                    </span>
                    <span className="db-item-meta">{r.description}</span>
                    <span className="db-item-meta">
                      {when(r.occurred_at)}
                      {' · '}{countText('Casualties', r.total_casualties)}
                      {' · '}{countText('Displaced', r.total_displaced)}
                    </span>
                  </button>
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

      {openId && <RecordDetail recordId={openId} onClose={closeRecord} />}
      {exporting && (
        <HistoryExport
          hazardTypes={hazardTypes}
          initialTypes={hazardTypes.filter((t) => !hazardId || String(t.id) === String(hazardId)).map((t) => t.name)}
          filters={filters}
          hasSamples={sampleCount > 0}
          onClose={closeExport}
        />
      )}
      {importing && <HistoryImport onImported={imported} onClose={closeImport} />}
    </div>
  );
}
