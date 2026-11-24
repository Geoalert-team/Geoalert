import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import './forecast.css';

/**
 * Model updates, on the "Predictive models" tab (backend forecast/updates/):
 * each automatic retraining attempt, newest first: when it ran, what it
 * decided and why. Read only.
 */

const RESULT_LABEL = {
  switched: 'Switched',
  kept: 'Kept current',
  not_tried: 'Not tried',
  skipped: 'Skipped',
  failed: 'Failed',
};
const HAZARD_LABEL = { fire: 'Fire', flood: 'Flood' };

const formatDay = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

export default function ModelUpdates() {
  const [updates, setUpdates] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    historyApi.forecastUpdates()
      .then((d) => { if (!cancelled) setUpdates(d?.updates || []); })
      .catch(() => { if (!cancelled) setError('Model updates could not be loaded right now.'); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="fc">
      <h2>Model updates</h2>
      <p className="db-card-sub">
        Each automatic retraining: when it ran, what it decided and why. A new model goes live only when it does at
        least as well as the one in use.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !updates && <p className="db-empty">Loading model updates…</p>}
      {updates && updates.length === 0 && <p className="db-empty">No automatic retraining has run yet.</p>}
      {updates && updates.length > 0 && (
        <div className="fc-table-wrap">
          <table className="fc-table fc-table-whole">
            <thead>
              <tr>
                <th scope="col">Hazard</th><th scope="col">Date</th><th scope="col">Result</th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {updates.map((u, i) => (
                // eslint-disable-next-line react/no-array-index-key
                <tr key={`${i}-${u.hazard}-${u.created_at}`}>
                  <td>{HAZARD_LABEL[u.hazard] || u.hazard}</td>
                  <td>{formatDay(u.created_at)}</td>
                  <td>{`${RESULT_LABEL[u.result] || u.result}${u.is_live ? ' (in use)' : ''}`}</td>
                  <td>{u.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
