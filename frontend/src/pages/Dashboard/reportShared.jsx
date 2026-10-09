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

export function ImpactChips({ report }) {
  const items = [
    { label: 'dead', value: report.casualties_dead, tone: 'bad' },
    { label: 'injured', value: report.casualties_injured, tone: 'warn' },
    { label: 'missing', value: report.casualties_missing, tone: 'warn' },
    { label: 'displaced', value: report.displaced, tone: 'info' },
  ];
  return (
    <div className="drm-chips">
      {items.map((i) => (
        <span key={i.label} className={`drm-chip ${i.value > 0 ? `is-${i.tone}` : ''}`}>
          <strong>{i.value ?? 0}</strong> {i.label}
        </span>
      ))}
    </div>
  );
}