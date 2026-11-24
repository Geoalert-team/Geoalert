import React from 'react';
import FloodReadiness from '../components/Forecast/FloodReadiness';
import ModelUpdates from '../components/Forecast/ModelUpdates';
import ForecastAccuracy from '../components/Forecast/ForecastAccuracy';
import './css/Dashboard.css';

/**
 * The "Predictive models" tab of Reporting and Analytics: what the
 * prediction models are and how they did, kept apart from the analytics of
 * the records (History is not prediction).
 *
 *   Flood data readiness  whether there is enough located flood data to
 *                         improve the flood predictions (counts only)
 *   Model updates         each automatic retraining attempt and what it decided
 *   Model accuracy        how the fire and flood models were built and tested
 *
 * Each card loads on its own, so one failing never hides the other.
 */
export default function PredictiveModelsPanel() {
  return (
    <>
      <div className="db-card">
        <FloodReadiness />
      </div>
      <div className="db-card">
        <ModelUpdates />
      </div>
      <div className="db-card">
        <ForecastAccuracy />
      </div>
    </>
  );
}
