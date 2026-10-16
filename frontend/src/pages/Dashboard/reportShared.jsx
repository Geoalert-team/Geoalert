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