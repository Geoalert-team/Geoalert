import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import './forecast.css';

/**
 * How the fire model did on fires it never saw (backend
 * views.ForecastAccuracyView). Fire is the only hazard with a prediction
 * model since 2026-11-22; flood and landslide are being rebuilt. An entry
 * the backend cannot give is shown as unavailable with its reason. It always
 * reads real records, so it takes no filters from the page.
 */
function HazardEntry({ report }) {
  if (report.status === 'unavailable') {
    return (
      <section className="fc-accuracy">
        <h3>{report.hazard}: unavailable</h3>
        {report.reason && <p className="fc-sub">{report.reason}</p>}
      </section>
    );
  }
  return (
    <section className="fc-accuracy">
      <h3>{report.hazard}</h3>
    </section>
  );
}

export default function ForecastAccuracy() {
  const [hazards, setHazards] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    historyApi.forecastAccuracy()
      .then((d) => { if (!cancelled) setHazards(d.hazards); })
      .catch(() => { if (!cancelled) setError('The accuracy check could not be loaded right now.'); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="fc">
      <h2>Model accuracy</h2>
      <p className="db-card-sub">
        How the fire model did on fires it never saw. Counting past fires is only a comparison here, never the
        prediction.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !hazards && <p className="db-empty">Loading the accuracy check…</p>}
      {hazards && !hazards.length && <p className="db-empty">No real records to test a model on yet.</p>}
      {hazards?.map((report) => <HazardEntry key={report.hazard} report={report} />)}
      {hazards && <p className="fc-note">Flood and landslide predictions are being rebuilt.</p>}
    </div>
  );
}
