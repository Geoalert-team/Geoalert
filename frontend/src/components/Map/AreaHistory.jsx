import React, { useCallback, useEffect, useState } from 'react';
import { historyApi } from '../../api/historyApi';
import { severityInfo } from './hazardInfo';
import { areaTitle } from './purokLevels';

const PAGE = 5; // events shown per "Show more"

function formatDate(iso) {
  if (!iso) return 'Not recorded';
  return new Date(iso).toLocaleDateString('en-PH', { year: 'numeric', month: 'long', day: 'numeric' });
}

function Swatch({ level }) {
  return <span className="pm-area-swatch" style={{ background: level ? severityInfo(level).color : '#c3cad6' }} />;
}

/**
 * The past hazards section of the barangay panel (GET /api/history/area/).
 *
 * barangay     { id, name }
 * purokId      null for the whole barangay, a purok id for one purok, or
 *              'none' for the barangay's records that name no purok
 * types        the hazard types ticked in Layers; nothing is fetched for none
 * onPickPurok  (id | 'none' | null) when a row or the way back is chosen
 */
export default function AreaHistory({ barangay, purokId, types, onPickPurok }) {
  const [area, setArea] = useState(null);
  const [failed, setFailed] = useState(false);
  const [shown, setShown] = useState(PAGE);
  const [attempt, setAttempt] = useState(0);
  const typeList = types.join(',');

  useEffect(() => {
    setArea(null);
    setFailed(false);
    if (!barangay?.id || !typeList) return undefined;
    let live = true;
    const params = { barangay: barangay.id, ...(purokId != null ? { purok: purokId } : {}), types: typeList };
    historyApi.area(params)
      .then((data) => { if (live) { setArea(data); setShown(PAGE); } })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [barangay?.id, purokId, typeList, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  if (!typeList) return <p className="pm-muted">Tick a hazard type in Layers to see its history.</p>;
  if (failed) {
    return (
      <p className="pm-muted">
        Past records couldn't be loaded. Try again.{' '}
        <button type="button" className="pm-history-more" onClick={retry}>Try again</button>
      </p>
    );
  }
  if (!area) return <p className="pm-muted">Loading past records…</p>;

  const years = area.thresholds?.years;
  const left = area.events.length - shown;

  return (
    <div className="pm-area-history">
      {purokId != null && (
        <>
          <button type="button" className="pm-area-back" onClick={() => onPickPurok(null)}>
            ‹ {barangay.name}
          </button>
          <p className="pm-area-title">
            <Swatch level={area.level} />
            <strong>{area.purok?.name}</strong>
            {area.purok?.parent && <small>{area.purok.parent}</small>}
          </p>
        </>
      )}

      <p className="pm-history-summary">{areaTitle(area.count, types, years)}</p>

      {purokId == null && (area.puroks.length > 0 || area.unplaced > 0) && (
        <ul className="pm-area-puroks">
          {area.puroks.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onPickPurok(p.id)}>
                <Swatch level={p.level} />
                <span>
                  <strong>{p.name}</strong>
                  {p.parent && <small>{p.parent}</small>}
                </span>
                <span className="pm-area-count">{p.count}</span>
              </button>
            </li>
          ))}
          {area.unplaced > 0 && (
            <li>
              <button type="button" onClick={() => onPickPurok('none')}>
                <Swatch level={null} />
                <span><strong>Purok not recorded</strong></span>
                <span className="pm-area-count">{area.unplaced}</span>
              </button>
            </li>
          )}
        </ul>
      )}

      {area.events.length > 0 && (
        <ul className="pm-timeline pm-history-list">
          {area.events.slice(0, shown).map((e) => (
            <li key={e.id}>
              <span className="pm-timeline-dot" />
              <div>
                <strong>{formatDate(e.date)}</strong>
                <span>{[e.type, e.alarm_level, e.property_subcategory || e.property_category].filter(Boolean).join(' · ')}</span>
                {purokId == null && e.puroks.length > 0 && (
                  <span className="pm-history-counts">{e.puroks.join(', ')}</span>
                )}
                {e.location_text && <span className="pm-history-counts">{e.location_text}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}

      {left > 0 && (
        <button type="button" className="pm-history-more" onClick={() => setShown((n) => n + PAGE)}>
          Show more
        </button>
      )}
    </div>
  );
}
