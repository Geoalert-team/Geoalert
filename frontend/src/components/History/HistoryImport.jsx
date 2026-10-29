import React, { useEffect, useRef, useState } from 'react';
import { historyApi } from '../../api/historyApi';

/**
 * Bring the BFP fire log or the flood and landslide log into the history,
 * from the History page. DRRMO staff only; the server reads the file (backend
 * apps/history/importing.py, the same code as the manage.py importers), tells
 * the two logs apart by their sheets and adds only rows not already in the
 * history, so a log with new rows at the bottom can be brought in again.
 *
 * Choosing a file checks it and shows what would happen; nothing is saved
 * until Import, which sends the same file again.
 *
 *   onImported(result)  after records were added, so the page reloads its list
 *   onClose()
 *
 * Styled with db- classes from Dashboard.css, like HistoryExport.
 */

function plural(n, one, many = `${one}s`) {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

function Details({ title, children }) {
  return (
    <details className="db-import-details">
      <summary>{title}</summary>
      {children}
    </details>
  );
}

export default function HistoryImport({ onImported, onClose }) {
  const [file, setFile] = useState(null);
  const [warnings, setWarnings] = useState(false);
  const [check, setCheck] = useState(null); // the server's answer for the file
  const [busy, setBusy] = useState(''); // 'checking' or 'importing'
  const [error, setError] = useState('');
  const [done, setDone] = useState(null); // the answer once imported
  const inputRef = useRef(null);

  // Escape closes (not while saving); focus starts on the file picker
  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape' && busy !== 'importing') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  async function run(chosen, { save = false, includeWarnings = warnings } = {}) {
    setBusy(save ? 'importing' : 'checking');
    setError('');
    try {
      const result = await historyApi.importFile(chosen, { save, includeWarnings });
      if (save) {
        setDone(result);
        onImported?.(result);
      } else {
        setCheck(result);
      }
    } catch (err) {
      setError(err.data?.file || err.message || 'The file could not be read. Please try again.');
      if (!save) setCheck(null);
    } finally {
      setBusy('');
    }
  }

  function pick(e) {
    const chosen = e.target.files?.[0] || null;
    setFile(chosen);
    setCheck(null);
    setWarnings(false);
    if (chosen) run(chosen, { includeWarnings: false });
  }

  function toggleWarnings() {
    const next = !warnings;
    setWarnings(next);
    run(file, { includeWarnings: next });
  }

  const floods = check?.kind === 'flood_landslide';

  return (
    <div
      className="db-modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget && busy !== 'importing') onClose(); }}
    >
      <div className="db-modal db-history-import" role="dialog" aria-modal="true" aria-labelledby="db-import-title">
        <div className="db-modal-head">
          <h2 id="db-import-title">Import history</h2>
          <button type="button" className="db-modal-close" onClick={onClose} aria-label="Close" disabled={busy === 'importing'}>×</button>
        </div>

        {done ? (
          <>
            <div className="db-success" role="status">
              {done.new > 0
                ? `Imported ${plural(done.new, 'record')} from the ${done.kind_label.toLowerCase()}.`
                : 'Nothing new was imported: every row is already in the history.'}
              {done.already > 0 && ` ${plural(done.already, 'row was', 'rows were')} already in it.`}
            </div>
            <div className="db-btn-row db-export-actions">
              <button type="button" className="db-btn db-btn-primary" onClick={onClose}>Done</button>
            </div>
          </>
        ) : (
          <>
            <p className="db-hint">
              The BFP fire log or the flood and landslide log, as an Excel workbook (.xlsx). Only rows not already
              in the history are added, so a log can be imported again after new rows are typed in. Nothing is
              saved until you press Import.
            </p>

            <label className="db-field">
              File
              <input ref={inputRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={pick} disabled={Boolean(busy)} />
            </label>

            {busy === 'checking' && <p className="db-hint">Checking the file…</p>}
            {error && <div className="db-error" role="alert">{error}</div>}

            {check && busy !== 'checking' && (
              <section className="db-import-check" aria-label="What the import would do">
                <p className="db-import-kind">{check.kind_label} · {plural(check.read, 'row')} read</p>
                <p className="db-import-new">
                  {check.new > 0 ? `${plural(check.new, 'new record')} to add` : 'Nothing new to add'}
                </p>
                <ul className="db-import-facts">
                  <li>Already in the history: <strong>{check.already.toLocaleString()}</strong></li>
                  {check.new > 0 && (
                    <>
                      <li>Placed in a purok: <strong>{check.linked.toLocaleString()}</strong></li>
                      <li>Filed under the barangay only: <strong>{check.barangay_only.toLocaleString()}</strong></li>
                    </>
                  )}
                </ul>

                {floods && (
                  <label className="db-report-check">
                    <input type="checkbox" checked={warnings} onChange={toggleWarnings} />
                    Also import warnings that were not events (pre-emptive evacuations, risk advisories, a rising river)
                  </label>
                )}

                {check.problems.map((p) => (
                  <Details key={p.label} title={`${p.label} (${p.rows.length}), left out`}>
                    <p className="db-import-rows">{p.rows.join(', ')}</p>
                  </Details>
                ))}

                {check.unlinked.length > 0 && (
                  <Details title={`${plural(check.unlinked.length, 'place')} matched no purok, filed under the barangay`}>
                    <ul className="db-import-list">
                      {check.unlinked.map((u) => (
                        <li key={`${u.barangay}|${u.place}`}>
                          {u.barangay}: {u.place}
                          {u.count ? ` (${plural(u.count, 'fire')})` : ''}
                          {u.close.length > 0 && <span className="db-import-close"> · close: {u.close.join(', ')}</span>}
                        </li>
                      ))}
                    </ul>
                  </Details>
                )}

                {check.to_check.length > 0 && (
                  <Details title={`${plural(check.to_check.length, 'row')} marked CHECK in the log`}>
                    <ul className="db-import-list">
                      {check.to_check.map((line) => <li key={line}>{line}</li>)}
                    </ul>
                  </Details>
                )}
              </section>
            )}

            <div className="db-btn-row db-export-actions">
              <button type="button" className="db-btn db-btn-outline" onClick={onClose} disabled={busy === 'importing'}>
                Cancel
              </button>
              <button
                type="button"
                className="db-btn db-btn-primary"
                onClick={() => run(file, { save: true })}
                disabled={Boolean(busy) || !check || check.new === 0}
              >
                {busy === 'importing' ? 'Importing…' : check?.new > 0 ? `Import ${plural(check.new, 'record')}` : 'Import'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
