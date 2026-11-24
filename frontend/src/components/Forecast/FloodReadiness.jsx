import React, { useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { UNDER_REVIEW } from './ForecastAccuracy';
import './forecast.css';

/**
 * Flood data readiness, on the "Predictive models" tab (backend
 * views.FloodReadinessView): located flood days on record against what a
 * flood forecast would need, and new located floods since the flood map was
 * published against the review threshold. It only counts; nothing here
 * changes a prediction. The flood map learns from the 2017 survey, not from
 * these records, and the card says so.
 */

const NOT_ENOUGH = 'Not enough located flood days to try flood forecasting yet.';
const ENOUGH = 'There are enough located flood days to consider building a flood forecast. That needs a rebuild by '
  + 'a developer.';
const NO_MAP = 'No flood map has been published yet.';

function trainingLine(map) {
  const spots = map.survey_spots != null ? ` (${map.survey_spots} flood spots)` : '';
  const built = map.built_at ? ` Built ${map.built_at.slice(0, 10)}.` : '';
  return `The flood map comes from the ${map.trained_on}${spots}, not from these records.${built}`;
}

export default function FloodReadiness() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    historyApi.forecastReadiness()
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError('The readiness check could not be loaded right now.'); });
    return () => { cancelled = true; };
  }, []);

  const need = data?.forecast_days_needed;
  const map = data?.flood_map;
  const since = data?.since_publishing;
  return (
    <div className="fc">
      <h2>Flood data readiness</h2>
      <p className="db-card-sub">
        Whether there is enough located flood data to improve the flood predictions. It only counts: nothing here
        changes a prediction.
      </p>
      {error && <p className="db-error" role="alert">{error}</p>}
      {!error && !data && <p className="db-empty">Loading the readiness check…</p>}
      {data && (
        <>
          <p className="fc-note">
            {`Located flood days on record: ${data.located_flood_days}. Flood forecasting needs about `
              + `${need.min}–${need.max}.`}
          </p>
          <p className="fc-note"><strong>{data.enough_for_forecasting ? ENOUGH : NOT_ENOUGH}</strong></p>
          {map?.available && since ? (
            <>
              <p className="fc-note">
                {`New located floods since the flood map was published: ${since.n}. The map is reviewed after `
                  + `${since.review_after}.`}
              </p>
              {since.under_review && <p className="fc-note"><strong>{UNDER_REVIEW}</strong></p>}
              <p className="fc-note">{trainingLine(map)}</p>
            </>
          ) : (
            <p className="fc-note">{map?.reason || NO_MAP}</p>
          )}
        </>
      )}
    </div>
  );
}
