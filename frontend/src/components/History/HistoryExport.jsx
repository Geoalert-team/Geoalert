import React, { useEffect, useRef, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { datedFilename, downloadBlob } from '../../utils/csv';

/**
 * Download the history in the BFP fire log's columns A-W, as Excel or CSV,
 * newest first. DRRMO staff, and BFP for fires; the server builds the file (backend
 * apps/history/export.py), leaves sample records out and logs the download.
 *
 *   hazardTypes   [{ id, name }], one checkbox each
 *   initialTypes  names ticked when it opens: the page's tab, or every type
 *   filters       the page's barangay, purok and date params, applied as-is
 *   hasSamples    whether the page shows sample records, which stay out
 *
 * Styled with db- classes from Dashboard.css, like RecordDetail.
 */

const FILES = [
  { id: 'xlsx', label: 'Excel (.xlsx)' },
  { id: 'csv', label: 'CSV (.csv)' },
];

// history-2026-10-29.xlsx for every type, history-fire-flood-2026-10-29.xlsx for some
export function exportFilename(names, all, file, when = new Date()) {
  const words = all ? [] : names.map((n) => n.toLowerCase().replace(/[^a-z0-9]+/g, ''));
  return datedFilename(['history', ...words.filter(Boolean)].join('-'), file, when);
}

export default function HistoryExport({ hazardTypes, initialTypes, filters, hasSamples = false, onClose }) {
  const [picked, setPicked] = useState(() => new Set(initialTypes));
  const [file, setFile] = useState('xlsx');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const firstRef = useRef(null);

  // Escape closes; focus starts on the first hazard type
  useEffect(() => {
    firstRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const names = hazardTypes.map((t) => t.name).filter((n) => picked.has(n));
  // A lone type (BFP's Fire) is still named, in the request and the file name
  const all = hazardTypes.length > 1 && names.length === hazardTypes.length;

  function toggle(name) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }

  async function download() {
    setBusy(true);
    setError('');
    try {
      const blob = await historyApi.export({ ...filters, file, ...(all ? {} : { types: names.join(',') }) });
      downloadBlob(exportFilename(names, all, file), blob);
      onClose();
    } catch (err) {
      setError(err.message || 'Could not prepare the file. Please try again.');
      setBusy(false);
    }
  }

  return (
    <div
      className="db-modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="db-modal db-history-export" role="dialog" aria-modal="true" aria-labelledby="db-export-title">
        <div className="db-modal-head">
          <h2 id="db-export-title">Export history</h2>
          <button type="button" className="db-modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <p className="db-hint">
          One row per record, newest first, in the BFP fire log&apos;s columns A to W. The Barangay, Purok
          and date filters on the page apply.
          {hasSamples && ' Sample records are left out.'}
        </p>

        <fieldset className="db-fieldset">
          <legend>Hazard types</legend>
          <div className="db-export-choices">
            {hazardTypes.map((t, i) => (
              <label key={t.id} className="db-report-check">
                <input
                  ref={i === 0 ? firstRef : undefined}
                  type="checkbox"
                  checked={picked.has(t.name)}
                  onChange={() => toggle(t.name)}
                />
                {t.name}
              </label>
            ))}
          </div>
          {hazardTypes.length > 1 && (
            <p className="db-hint">
              Floods and landslides use the same columns: the hazard and its sub category in G and H,
              injured in N, fatalities in T.
            </p>
          )}
        </fieldset>

        <fieldset className="db-fieldset">
          <legend>File</legend>
          <div className="db-export-choices">
            {FILES.map((f) => (
              <label key={f.id} className="db-report-check">
                <input type="radio" name="history-export-file" checked={file === f.id} onChange={() => setFile(f.id)} />
                {f.label}
              </label>
            ))}
          </div>
        </fieldset>

        {error && <div className="db-error" role="alert">{error}</div>}

        <div className="db-btn-row db-export-actions">
          <button type="button" className="db-btn db-btn-outline" onClick={onClose}>Cancel</button>
          <button type="button" className="db-btn db-btn-primary" onClick={download} disabled={busy || names.length === 0}>
            {busy ? 'Preparing…' : 'Download'}
          </button>
        </div>
      </div>
    </div>
  );
}
