import React, { useCallback, useEffect, useState } from 'react';
import { reportsApi } from '../../api/reportApi';

/**
 * What the barangay reported about a zone: the incident reports it was
 * published from, or that joined it later (a fire's later reports). Shown
 * at the top of the resolve form, so DRRMO closes the zone with the
 * barangay's own account in front of them: what was seen, when it started,
 * which puroks, who sent it and the photos.
 *
 * Styled with db- classes from Dashboard.css, like the form around it.
 * A zone published from the office has no report; it says so.
 */

function when(iso) {
  return iso
    ? new Date(iso).toLocaleString('en-PH', {
      month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
    })
    : '';
}

// "Lawaan I, Talisay City, Cebu": the barangay and where it is filed
function area(report) {
  const b = report.barangay_details || {};
  return [b.name, b.municipality, b.province].filter(Boolean).join(', ');
}

function reporter(report) {
  const who = report.submitted_by_name || report.reporter_name || 'Unknown';
  const role = [report.position, report.agency].filter(Boolean).join(', ');
  return role ? `${who} (${role})` : who;
}

export function ReportSummary({ report }) {
  const type = report.hazard_type_details?.name || 'Hazard';
  const puroks = (report.puroks || []).map((p) => p.name).filter(Boolean);
  const photos = report.photos || [];
  return (
    <article className="db-rz-report">
      <p className="db-rz-report-title">
        <strong>{type} · {report.barangay_details?.name || 'Barangay not given'}</strong>
        <span className={`db-rz-status is-${(report.status || '').toLowerCase()}`}>
          {report.status === 'Pending' ? 'Awaiting review' : report.status}
        </span>
      </p>
      <p className="db-rz-meta">Sent {when(report.created_at)} by {reporter(report)}</p>
      <p className="db-rz-desc">{report.description || 'No description given.'}</p>

      {photos.length > 0 && (
        <div className="db-rz-photos">
          {photos.map((photo, i) => (
            <a key={photo.id || photo.url} href={photo.url} target="_blank" rel="noreferrer" title="Open the full-size photo">
              <img
                src={photo.url}
                alt={`Photo sent with the ${type.toLowerCase()} report${photos.length > 1 ? ` (${i + 1} of ${photos.length})` : ''}`}
                loading="lazy"
              />
            </a>
          ))}
        </div>
      )}

      <dl className="db-rz-facts">
        {report.started_at && (<><dt>Started</dt><dd>{when(report.started_at)}</dd></>)}
        {puroks.length > 0 && (<><dt>Purok / Sitio</dt><dd>{puroks.join(', ')}</dd></>)}
        {area(report) && (<><dt>Where</dt><dd>{area(report)}</dd></>)}
        {report.review_note && (<><dt>DRRMO note</dt><dd>{report.review_note}</dd></>)}
      </dl>
    </article>
  );
}

export default function ZoneReports({ zoneId }) {
  const [reports, setReports] = useState(null); // null while loading
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    setReports(null);
    reportsApi.forZone(zoneId)
      .then((data) => setReports(Array.isArray(data) ? data : data?.results || []))
      .catch(() => setFailed(true));
  }, [zoneId]);

  useEffect(() => { if (zoneId) load(); }, [zoneId, load]);

  return (
    <section className="db-rz-reports" aria-label="What the barangay reported">
      <h4>
        What the barangay reported
        {reports?.length > 1 && <span className="db-rz-count">{reports.length} reports</span>}
      </h4>
      {failed ? (
        <div className="db-error" role="alert">
          Couldn&apos;t load the barangay&apos;s report.{' '}
          <button type="button" className="db-btn db-btn-outline db-btn-sm" onClick={load}>Try again</button>
        </div>
      ) : reports === null ? (
        <p className="db-hint">Loading the barangay&apos;s report…</p>
      ) : reports.length === 0 ? (
        <p className="db-hint">No barangay report is linked to this zone. It was published from the office.</p>
      ) : (
        reports.map((r) => <ReportSummary key={r.id} report={r} />)
      )}
    </section>
  );
}
