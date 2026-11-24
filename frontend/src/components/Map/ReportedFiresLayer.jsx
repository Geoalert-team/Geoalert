import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { reportsApi } from '../../api/reportApi';
import { timeAgo } from '../../utils/timeAgo';
import { hazardColor, hazardIconPath } from './hazardInfo';
import { REPORTED_WINDOW_HOURS, awaitingDrrmo, reportSpots } from './reportedFires';

/**
 * Staff only (BFP, DRRMO, Admin; the page decides): the fire reports from
 * the last day that DRRMO has not decided yet, as dashed pins, so the fire
 * service can see where they are while DRRMO reviews them.
 * Residents never get this layer, and the server would refuse them the list
 * anyway: only a fire DRRMO approves goes on the public map.
 *
 * Props:
 *   focusId     a report id from /map?report=<id>: zoom to it and open it
 *   onFocused   called once with whether that report was found
 *   onCount     called with how many reports are waiting
 *   refreshMs   how often to check again while the map is open
 */

const REPORTED_ICON = L.divIcon({
  className: 'pm-drop-wrap',
  html: `<span class="pm-report-drop">
           <svg viewBox="0 0 44 56" aria-hidden="true">
             <path class="pm-report-body" d="M22 54s-17-19.6-17-32a17 17 0 0 1 34 0c0 12.4-17 32-17 32z"/>
             <path d="${hazardIconPath('Fire')}" transform="translate(13 13) scale(0.75)" fill="${hazardColor('Fire')}"/>
           </svg>
         </span>`,
  iconSize: [44, 56],
  iconAnchor: [22, 54],
  popupAnchor: [0, -48],
});

const started = (iso) => new Date(iso).toLocaleString('en-PH', {
  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
});

export default function ReportedFiresLayer({ focusId = null, onFocused, onCount, refreshMs = 30000 }) {
  const map = useMap();
  const [reports, setReports] = useState(null); // null until the first answer
  const markers = useRef({});

  const load = useCallback(() => {
    reportsApi.pendingFires(REPORTED_WINDOW_HOURS)
      .then((list) => setReports((Array.isArray(list) ? list : list?.results || []).filter(awaitingDrrmo)))
      // Keep what is shown; the BFP dashboard still lists every report
      .catch(() => setReports((prev) => prev || []));
  }, []);

  useEffect(() => {
    load();
    const refresh = () => { if (document.visibilityState === 'visible') load(); };
    const id = setInterval(refresh, refreshMs);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [load, refreshMs]);

  const pins = useMemo(
    () => (reports || []).flatMap((report) => reportSpots(report).map((spot) => ({ report, spot }))),
    [reports],
  );

  // How many reports have a pin here (the map's pill counts what it shows)
  useEffect(() => {
    if (reports && onCount) onCount(new Set(pins.map((p) => p.report.id)).size);
  }, [reports, pins, onCount]);

  // Opened from the BFP dashboard's Show on map: zoom in and open its first pin
  useEffect(() => {
    if (!focusId || reports === null) return;
    const pin = pins.find((p) => String(p.report.id) === String(focusId));
    if (pin) {
      map.setView(pin.spot.position, Math.max(map.getZoom(), 17));
      setTimeout(() => markers.current[pin.spot.key]?.openPopup(), 0);
    }
    if (onFocused) onFocused(Boolean(pin));
  }, [focusId, reports, pins, map, onFocused]);

  return pins.map(({ report, spot }) => {
    const barangay = report.barangay_details?.name || 'Barangay not set';
    return (
      <Marker
        key={spot.key}
        position={spot.position}
        icon={REPORTED_ICON}
        title={`Reported fire, not confirmed: ${spot.place ? `${spot.place}, ` : ''}${barangay}`}
        ref={(m) => { if (m) markers.current[spot.key] = m; else delete markers.current[spot.key]; }}
      >
        <Popup>
          <div className="pm-report-pop">
            <span className="pm-report-pop-tag">Reported fire · not confirmed</span>
            <strong>{spot.place ? `${spot.place}, ` : ''}{barangay}</strong>
            <span className="pm-report-pop-meta">
              Sent {timeAgo(report.created_at).toLowerCase()}
              {report.started_at && <> · started {started(report.started_at)}</>}
            </span>
            {report.description && <p>{report.description}</p>}
            <p className="pm-report-pop-note">
              DRRMO hasn&apos;t reviewed this yet, so residents haven&apos;t been alerted and can&apos;t see it.
            </p>
            <span className="pm-report-pop-links">
              <Link to="/app/dashboard">Open dashboard</Link>
            </span>
          </div>
        </Popup>
      </Marker>
    );
  });
}
