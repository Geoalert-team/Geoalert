import React, { useEffect, useRef, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import ExportMenu from '../components/Analytics/ExportMenu';
import usePrintOpensDetails from '../components/Analytics/usePrintOpensDetails';
import { barangaysApi } from '../api/barangaysApi';
import { hazardsApi } from '../api/hazardsApi';
import { reportsApi } from '../api/reportApi';
import { csvFilename, downloadCsv } from '../utils/csv';
import FilterBar from './reportsAnalytics/FilterBar';
import useReportFilters from './reportsAnalytics/useReportFilters';
import useSection from './reportsAnalytics/useSection';
import { answerWords, rangeError, requestParams } from './reportsAnalytics/filters';
import { AtAGlance, Band, BusiestMonths, WhereItHappens, YearByYear } from './trendAnalysis/sections';
import { trendCsv } from './trendAnalysis/trendCsv';
import './css/Dashboard.css';
import './css/ReportsAnalytics.css';
import './css/TrendAnalysis.css';

/**
 * F7 Trend Analysis: how hazards in Talisay City have changed over the years,
 * from the archive of past events, in plain words. Separate from Reports &
 * Analytics (what the system holds and how operations went).
 *
 *   At a glance       per hazard: going up, going down, no steady change, or
 *                     not enough years yet; months that stood out
 *   Year by year      events each year (or month), by hazard
 *   Busiest months    which months usually have the most events
 *   Where it happens  the barangay map and how often each has events
 *
 * Three answers feed it, each loading and failing on its own: trends/,
 * trends/patterns/ and trends/places/. The filters apply as they change (a
 * typed date when the field is left); each answer is written to the audit log.
 */
export default function TrendAnalysis() {
  const [filters, setFilters, resetFilters] = useReportFilters('trends');
  const [today] = useState(() => new Date());
  const [hazardTypes, setHazardTypes] = useState([]);
  const [features, setFeatures] = useState([]);
  const [step, setStep] = useState('year');
  const bodyRef = useRef(null);
  usePrintOpensDetails(bodyRef);

  useEffect(() => {
    hazardsApi.types()
      .then((list) => setHazardTypes(Array.isArray(list) ? list : list?.results || []))
      .catch(() => setHazardTypes([]));
    barangaysApi.list().then((geo) => setFeatures(geo?.features || [])).catch(() => setFeatures([]));
  }, []);

  const barangays = features.map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }));
  const invalid = !!rangeError(filters, today);
  const base = invalid ? null : requestParams(filters, today);
  const trends = useSection(reportsApi.trends, base && { ...base, granularity: step });
  const patterns = useSection(reportsApi.trendPatterns, base);
  const places = useSection(reportsApi.trendPlaces, base);

  const loading = [trends, patterns, places].some((s) => s.status === 'loading');
  const loaded = trends.data || patterns.data || places.data;

  async function exportAs(via) {
    // The words come from a loaded answer, so the file describes the figures it holds
    const { words, criteria } = answerWords(loaded);
    try {
      await reportsApi.printed('analytics', criteria, via);
    } catch {
      // export anyway
    }
    if (via === 'csv') {
      downloadCsv(csvFilename('trend-analysis'),
        trendCsv({ trends: trends.data, patterns: patterns.data, places: places.data }, words));
    } else {
      window.print();
    }
  }

  return (
    <div className="db ra-page ta-page">
      <PublicNavbar />
      <div className="db-wrap">
        <header className="ra-head">
          <div>
            <h1>Trend Analysis</h1>
            <p>How hazards in Talisay City have changed over the years, in plain words.</p>
          </div>
          <div className="db-no-print">
            <ExportMenu onExport={exportAs} disabled={loading || !loaded} />
          </div>
        </header>

        <FilterBar filters={filters} onChange={setFilters} onReset={resetFilters} hazardTypes={hazardTypes}
          barangays={barangays} today={today} kind="trends" mode="live" />
        <p className="ra-print-only">Trend Analysis · {answerWords(loaded).words}</p>

        <div className="ta-body" ref={bodyRef}>
          <Band id="at-a-glance" title="At a glance" state={patterns} invalid={invalid}
            sub="Is each hazard happening more often, less often, or about the same?">
            {patterns.data && <AtAGlance data={patterns.data} />}
          </Band>
          <Band id="year-by-year" title="Year by year" state={trends} invalid={invalid}>
            {trends.data && <YearByYear data={trends.data} step={step} onStep={setStep} />}
          </Band>
          <Band id="busiest-months" title="Busiest months" state={trends} invalid={invalid}
            sub="On average, how many events happen in each month of the year.">
            {trends.data && <BusiestMonths data={trends.data} />}
          </Band>
          <Band id="where" title="Where it happens" state={places} invalid={invalid}
            sub="Which barangays have the most events, and how often they have them.">
            {places.data && <WhereItHappens places={places.data} trends={trends.data} features={features} />}
          </Band>
        </div>
      </div>
    </div>
  );
}
