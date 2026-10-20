import React from 'react';
import Sparkline from '../Charts/Sparkline';
import StatTile from './StatTile';
import { MEASURES, monthLabel } from './measures';

/**
 * How much happened in the period: five counts, the four that belong to the
 * period each with its month-by-month shape. Active zones now is a right-now
 * count, so it has no trend to show.
 */

const num = (n) => (n === null || n === undefined ? null : n.toLocaleString());

const TILES = [
  {
    kpi: 'zones_published', label: 'Zones published', measure: 'zones',
    hint: (k) => (k.zones_retracted ? `${k.zones_retracted} more withdrawn as errors` : null),
  },
  { kpi: 'alerts_issued', label: 'Alerts issued', measure: 'alerts', hint: (k) => `${k.extreme_alerts} Extreme` },
  {
    kpi: 'incidents_submitted', label: 'Incident reports', measure: 'incidents',
    hint: (k) => (k.incidents_pending ? `${k.incidents_pending} still pending` : 'none pending'),
  },
  { kpi: 'recorded_events', label: 'Recorded hazard events', measure: 'events' },
];

export default function ActivityBand({ kpis: k, monthly = [] }) {
  return (
    <section className="an-band" aria-labelledby="an-activity">
      <h2 id="an-activity">Activity</h2>
      <div className="an-tiles">
        <StatTile value={num(k.active_zones_now)} label="Active zones now" hint="On the map today" />
        {TILES.map((t) => {
          const measure = MEASURES.find((m) => m.key === t.measure);
          return (
            <StatTile key={t.kpi} value={num(k[t.kpi])} label={t.label} hint={t.hint?.(k)}>
              <Sparkline
                points={monthly.map((m) => ({ label: monthLabel(m.month), value: m[t.measure] }))}
                label={measure.label}
              />
            </StatTile>
          );
        })}
      </div>
    </section>
  );
}
