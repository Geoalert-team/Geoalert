import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import ReportsPanel from './Reports';
import AnalyticsPanel from './Analytics';
import './css/Dashboard.css';
import './css/ReportingAnalytics.css';

/**
 * F7 "Reporting and Analytics" is one module, and was two nav items. They
 * answer different questions of the same records, for the same people:
 *
 *   Reports    what happened - filtered, printable, written to the audit
 *              log, meant to be handed over as an official figure
 *   Analytics  how we are handling it - read rates, how long an alert sits
 *              unread, how long a zone stays active
 *
 * Tabs rather than one long page: flattened together, the Print button
 * stops being clear about what it prints, and an officer after one
 * official figure would scroll past response-time charts to reach it.
 *
 * Both panels are the original pages with their own navbar and heading
 * removed; everything else about them, the audit logging included, is
 * untouched.
 */

const TABS = [
  {
    key: 'reports',
    label: 'Reports',
    blurb: 'Summaries of hazard activity and response for planning and decision-making.',
  },
  {
    key: 'analytics',
    label: 'Analytics',
    blurb: 'How hazards have been handled, month by month.',
  },
];

export default function ReportingAnalytics() {
  // The tab lives in the URL so a link can point at one, the back button
  // steps between them, and a refresh stays put. ?tab=analytics is also
  // where /app/analytics now lands, so older links still work.
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab');
  const active = TABS.some((t) => t.key === requested) ? requested : 'reports';
  const current = TABS.find((t) => t.key === active);

  // A tab is mounted the first time it is opened and stays mounted after
  // that. Reports keeps its filters and the generated report in component
  // state, so unmounting it would wipe a report an officer had just set up
  // because they glanced at Analytics. Waiting until a tab is first opened
  // keeps Analytics' aggregate query off the page load for officers who
  // only ever want a report.
  const [opened, setOpened] = useState(() => [active]);
  useEffect(() => {
    setOpened((prev) => (prev.includes(active) ? prev : [...prev, active]));
  }, [active]);

  function pick(key) {
    if (key === active) return;
    // Built from the current params rather than replacing them, so anything
    // else in the query string survives the tab change.
    const next = new URLSearchParams(params);
    next.set('tab', key);
    setParams(next, { replace: false });
  }

  return (
    <div className="db ra-page">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Reporting and Analytics</h1>
          <p>{current.blurb}</p>
        </div>

        <div className="ra-tabs db-no-print" role="tablist" aria-label="Reporting and analytics">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              id={`ra-tab-${t.key}`}
              aria-selected={active === t.key}
              aria-controls={`ra-panel-${t.key}`}
              className={`ra-tab ${active === t.key ? 'is-active' : ''}`}
              onClick={() => pick(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {TABS.filter((t) => opened.includes(t.key)).map((t) => (
          <div
            key={t.key}
            role="tabpanel"
            id={`ra-panel-${t.key}`}
            aria-labelledby={`ra-tab-${t.key}`}
            className="ra-panel"
            // hidden, not unmounted: the panel keeps its state, and screen
            // readers and printing both skip it while it is closed.
            hidden={active !== t.key}
          >
            {t.key === 'analytics' ? <AnalyticsPanel /> : <ReportsPanel />}
          </div>
        ))}
      </div>
    </div>
  );
}
