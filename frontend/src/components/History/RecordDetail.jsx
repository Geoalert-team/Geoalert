import React, { useCallback, useEffect, useRef, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import ZoneReports from '../Resolve/ZoneReports';
import { FATALITIES, INJURED, bfpLabel } from '../Resolve/fireClose';

/**
 * One history record in full, opened from the history page. When and where
 * it happened, the BFP fire log's figures (columns G-W) for a fire, the
 * counts, and what the barangay reported when the hazard was live. No
 * severity: the record is what happened, not how the alert was graded.
 *
 * Styled with db- classes from Dashboard.css (the page already loads it).
 */

function when(iso) {
  return iso
    ? new Date(iso).toLocaleString('en-PH', {
      month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
    })
    : '—';
}

// Blank is "not counted", never 0 (see countText on the history page)
const counted = (v) => (v === null || v === undefined ? 'not counted' : Number(v).toLocaleString());
const cell = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString());

function money(v) {
  if (v === null || v === undefined || v === '') return 'not counted';
  return `₱${Number(v).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function total(record, keys) {
  const known = keys.map((k) => record[k]).filter((v) => v !== null && v !== undefined);
  return known.length ? known.reduce((a, b) => a + Number(b), 0) : null;
}

const COUNT_KEYS = [...INJURED.firefighter, ...INJURED.civilian, ...FATALITIES.firefighter, ...FATALITIES.civilian];

// A fire closed with the BFP figures, or imported from the BFP log
export function hasBfpFigures(record) {
  return Boolean(record.alarm_level || record.property_category)
    || [...COUNT_KEYS, 'damage_cost', 'structures_affected'].some((k) => record[k] !== null && record[k] !== undefined);
}

function CountTable({ caption, groups, record }) {
  return (
    <table className="db-bfp-table">
      <caption>{caption}</caption>
      <thead>
        <tr><th scope="col"><span className="db-sr">Who</span></th><th scope="col">Male</th><th scope="col">Female</th><th scope="col">Total</th></tr>
      </thead>
      <tbody>
        {[['Firefighter', groups.firefighter], ['Civilian', groups.civilian]].map(([label, [male, female]]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td>{cell(record[male])}</td>
            <td>{cell(record[female])}</td>
            <td><strong>{cell(total(record, [male, female]))}</strong></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function RecordDetail({ recordId, onClose }) {
  const [record, setRecord] = useState(null);
  const [failed, setFailed] = useState(false);
  const closeRef = useRef(null);

  const load = useCallback(() => {
    setFailed(false);
    setRecord(null);
    historyApi.detail(recordId).then(setRecord).catch(() => setFailed(true));
  }, [recordId]);
  useEffect(() => { load(); }, [load]);

  // Escape closes; focus starts on the close button
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const type = record?.hazard_type_detail?.name || 'Hazard';
  const b = record?.barangay_detail || {};
  const where = record
    ? record.location_text
      || [...(record.puroks || []), b.name].filter(Boolean).join(', ')
      || 'Not recorded'
    : '';

  return (
    <div
      className="db-modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="db-modal db-record" role="dialog" aria-modal="true" aria-labelledby="db-record-title">
        <div className="db-modal-head">
          <h2 id="db-record-title">
            {record ? `${type} · ${b.name || 'Unspecified barangay'}` : 'Historical record'}
            {record?.is_sample && <span className="db-badge" style={{ marginLeft: 8 }}>Sample</span>}
          </h2>
          <button ref={closeRef} type="button" className="db-modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        {failed ? (
          <div className="db-error" role="alert">
            Couldn&apos;t load this record.{' '}
            <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={load}>Try again</button>
          </div>
        ) : !record ? (
          <p className="db-hint">Loading the record…</p>
        ) : (
          <>
            <section className="db-modal-section">
              <h3>When and where</h3>
              <dl className="db-dl">
                <dt>Happened</dt><dd>{when(record.occurred_at)}</dd>
                <dt>Location</dt><dd>{where}</dd>
                {(b.municipality || b.province) && (
                  <><dt>City / Province</dt><dd>{[b.municipality, b.province].filter(Boolean).join(', ')}</dd></>
                )}
                <dt>Filed</dt><dd>{when(record.archived_at)}</dd>
              </dl>
            </section>

            {record.description && (
              <section className="db-modal-section">
                <h3>Description</h3>
                <p className="db-record-desc">{record.description}</p>
              </section>
            )}

            {hasBfpFigures(record) && (
              <section className="db-modal-section">
                <h3>BFP fire figures</h3>
                <dl className="db-dl">
                  <dt>Property type</dt>
                  <dd>
                    {record.property_category
                      ? `${bfpLabel(record.property_category)} – ${bfpLabel(record.property_subcategory) || '—'}`
                      : 'not recorded'}
                  </dd>
                  <dt>Alarm</dt><dd>{record.alarm_level ? bfpLabel(record.alarm_level) : 'not recorded'}</dd>
                  <dt>Damage</dt><dd>{money(record.damage_cost)}</dd>
                  <dt>Structures</dt><dd>{counted(record.structures_affected)}</dd>
                </dl>
                <div className="db-bfp-tables">
                  <CountTable caption="Injured" groups={INJURED} record={record} />
                  <CountTable caption="Fatalities" groups={FATALITIES} record={record} />
                </div>
              </section>
            )}

            <section className="db-modal-section">
              <h3>Counts</h3>
              <dl className="db-dl">
                <dt>Casualties</dt><dd>{counted(record.total_casualties)}</dd>
                <dt>Displaced</dt><dd>{counted(record.total_displaced)}</dd>
              </dl>
            </section>

            {record.hazard_zone && (
              <section className="db-modal-section">
                <ZoneReports zoneId={record.hazard_zone} />
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
