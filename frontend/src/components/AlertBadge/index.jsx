import React from 'react';
import { useNotifications } from '../../hooks/useNotifications';

export default function AlertBadge({ scope = 'all', email = null }) {
  const { pendingCount } = useNotifications({ scope, email });
  if (!pendingCount) return null;
  return (
    <span
      style={{
        background: 'var(--sev-red)',
        color: '#fff',
        fontSize: 11,
        fontWeight: 700,
        borderRadius: 999,
        padding: '2px 7px',
        marginLeft: 6,
      }}
    >
      {pendingCount}
    </span>
  );
}
