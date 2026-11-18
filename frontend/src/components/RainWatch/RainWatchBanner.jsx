import React from 'react';
import { dayLabel, rainLevel } from './rainWatchLevels';
import './rainWatch.css';

// A slim line over the map whenever Orange or Red is coming in the next 3 days
export default function RainWatchBanner({ info, data, onView }) {
  if (!info) return null;
  const index = (data?.days || []).findIndex((d) => d.key === info.key);
  const label = dayLabel(data?.days?.[index], index);
  const when = index <= 1 ? label.toLowerCase() : label;
  return (
    <button
      type="button"
      className="rw-banner"
      style={{ '--rw-color': rainLevel(info.level).color }}
      onClick={() => onView(info.key)}
    >
      {`Rain watch: ${info.level} expected ${when} → view`}
    </button>
  );
}
