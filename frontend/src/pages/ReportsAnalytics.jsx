import React, { useEffect, useRef, useState } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { barangaysApi } from '../api/barangaysApi';
import { hazardsApi } from '../api/hazardsApi';
import FilterBar from './reportsAnalytics/FilterBar';
import ModelsSection from './reportsAnalytics/ModelsSection';
import OperationsSection from './reportsAnalytics/OperationsSection';
import SummarySection from './reportsAnalytics/SummarySection';
import useReportFilters from './reportsAnalytics/useReportFilters';
import { filtersFromParams, filtersToParams, rangeError, requestParams } from './reportsAnalytics/filters';
import { MODELS_PATH, TRENDS_PATH } from './paths';
import './css/Dashboard.css';
import './css/ReportsAnalytics.css';

/**
 * F7 Reports & Analytics: what GeoAlert holds, how operations went, and the
 * figures the office can hand over. (How hazards have behaved over the years
 * is the separate Trend Analysis module, /app/trends.)
 *
 *   Summary        the Hazard Summary report: holdings, events and impact,
 *                  breakdowns by hazard, barangay and purok, completeness
 *   Operations     the Response Status report: zones, alerts, incident
 *                  reports and how fast they were handled
 *   Prediction models  which models are in use, how they are trained,
 *                  and how GeoAlert switches to its own (an explanation)
 *
 * The filters apply on Apply, so each section is generated, and written to
 * the audit log, once per set of filters. Only the open section loads.
 */
export const SECTIONS = [
  { key: 'summary', label: 'Summary' },
  { key: 'operations', label: 'Operations' },
  { key: 'models', label: 'Prediction models' },
];

/** Where an old address of this page now lives, or null. */
export function legacyTarget(params) {
  if (params.get('view') === 'trends' || params.get('tab') === 'analytics') {
    const carried = filtersToParams(filtersFromParams(params, 'trends'), new URLSearchParams(), 'trends').toString();
    return carried ? `${TRENDS_PATH}?${carried}` : TRENDS_PATH;
  }
  if (params.get('tab') === 'models') return MODELS_PATH;
  return null;
}

export default function ReportsAnalytics() {
  const [params, setParams] = useSearchParams();
  const [filters, setFilters, resetFilters] = useReportFilters('reports');
  const [today] = useState(() => new Date());
  const [hazardTypes, setHazardTypes] = useState([]);
  const [barangays, setBarangays] = useState([]);
  const tabRefs = useRef({});
  const section = SECTIONS.some((s) => s.key === params.get('section')) ? params.get('section') : 'summary';
  const [opened, setOpened] = useState(() => [section]);
  useEffect(() => { setOpened((prev) => (prev.includes(section) ? prev : [...prev, section])); }, [section]);

  useEffect(() => {
    hazardsApi.types()
      .then((list) => setHazardTypes(Array.isArray(list) ? list : list?.results || []))
      .catch(() => setHazardTypes([]));
    barangaysApi.list()
      .then((geo) => setBarangays((geo?.features || []).map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }))))
      .catch(() => setBarangays([]));
  }, []);

  const moved = legacyTarget(params);
  if (moved) return <Navigate to={moved} replace />;

  function pick(key) {
    if (key === section) return;
    const next = new URLSearchParams(params);
    if (key === 'summary') next.delete('section');
    else next.set('section', key);
    setParams(next);
  }

  function onTabKey(e) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const i = SECTIONS.findIndex((s) => s.key === section);
    const next = SECTIONS[(i + (e.key === 'ArrowRight' ? 1 : SECTIONS.length - 1)) % SECTIONS.length];
    pick(next.key);
    tabRefs.current[next.key]?.focus();
  }

  // A refused range (a hand-edited address) asks for nothing; the bar says why
  const sectionParams = rangeError(filters, today) ? null : requestParams(filters, today);
  const BODIES = {
    summary: (active) => <SummarySection params={sectionParams} active={active} />,
    operations: (active) => <OperationsSection params={sectionParams} active={active} />,
    models: () => <ModelsSection />,
  };

  return (
    <div className="db ra-page">
      <PublicNavbar />
      <div className="db-wrap">
        <header className="ra-head">
          <div>
            <h1>Reports & Analytics</h1>
            <p>What GeoAlert holds, how operations went, and the figures to hand over.</p>
          </div>
          <div className="ra-switch db-no-print" role="tablist" aria-label="Reports & Analytics sections">
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                ref={(node) => { tabRefs.current[s.key] = node; }}
                type="button"
                role="tab"
                id={`ra-tab-${s.key}`}
                aria-selected={section === s.key}
                aria-controls={`ra-panel-${s.key}`}
                tabIndex={section === s.key ? 0 : -1}
                className={`ra-switch-btn ${section === s.key ? 'is-active' : ''}`}
                onClick={() => pick(s.key)}
                onKeyDown={onTabKey}
              >
                {s.label}
              </button>
            ))}
          </div>
        </header>

        <FilterBar filters={filters} onChange={setFilters} onReset={resetFilters} hazardTypes={hazardTypes}
          barangays={barangays} today={today} kind="reports" mode="apply" />

        {SECTIONS.filter((s) => opened.includes(s.key)).map((s) => (
          <div key={s.key} role="tabpanel" id={`ra-panel-${s.key}`} aria-labelledby={`ra-tab-${s.key}`}
            className="ra-panel db-card" hidden={section !== s.key}>
            {BODIES[s.key](section === s.key)}
          </div>
        ))}
      </div>
    </div>
  );
}
