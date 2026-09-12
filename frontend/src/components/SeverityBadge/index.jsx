import React from 'react';
import { severityColor, severityLabel } from '../../utils/severityColor';

export default function SeverityBadge({ severity }) {
  const color = severityColor(severity);
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 11.5,
        fontWeight: 600,
        padding: '3px 8px',
        border: `1px solid ${color}`,
        color,
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color }} />
      {severityLabel(severity)}
    </span>
  );
}
