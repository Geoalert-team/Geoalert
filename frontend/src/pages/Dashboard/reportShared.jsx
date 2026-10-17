import React from 'react';
import { hazardColor, hazardIconPath } from '../../components/Map/hazardInfo';

// Small pieces for showing incident reports. Styles live in css/DRRMODashboard.css.

export function HazardIcon({ type, size = 'md' }) {
  const color = hazardColor(type) || '#43516a';
  return (
    <span className={`drm-hazard-icon drm-hazard-${size}`} style={{ color, background: `${color}1a` }} aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round">
        <path d={hazardIconPath(type)} />
      </svg>
    </span>
  );
}

export function StatusTag({ status }) {
  const tone = { Pending: 'warn', Validated: 'good', Rejected: 'bad' }[status] || 'neutral';
  const label = status === 'Pending' ? 'Awaiting review' : status;
  return <span className={`adm-action adm-action-${tone}`}>{label}</span>;
}

// ImpactChips (dead / injured / missing / displaced) used to live here. The
// report form stopped collecting casualty counts, so every chip read zero on
// every report — a row of zeroes next to a real flood report says something
// false, not something unknown.

/**
 * The photo attached to a report, if there is one.
 *
 * Opens full size in a new tab rather than a lightbox: an officer deciding
 * whether to validate wants to zoom into the water line, and the browser's
 * own image viewer does that better than anything worth building here.
 *
 * The src is the absolute URL the API returns. If the API and the file are
 * on different machines — each developer runs their own server against the
 * shared database — the image will not load, which onError says plainly
 * instead of leaving a broken icon.
 */
export function ReportPhoto({ report, alt, linked = true }) {
  const [failed, setFailed] = React.useState(false);
  if (!report?.photo) return null;

  if (failed) {
    return (
      <p className="drm-photo-missing">
        A photo was attached but could not be loaded from this server.
      </p>
    );
  }

  const image = (
    <img
      src={report.photo}
      alt={alt || 'Photo attached to this report'}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );

  // linked={false} for rows that are themselves a button: an anchor inside a
  // button is invalid HTML, and a click would both follow the link and open
  // the row. Those rows open a dialog that carries the full-size version.
  if (!linked) return <span className="drm-report-photo is-plain">{image}</span>;

  return (
    <a
      className="drm-report-photo"
      href={report.photo}
      target="_blank"
      rel="noreferrer"
      title="Open the full-size photo"
    >
      {image}
    </a>
  );
}