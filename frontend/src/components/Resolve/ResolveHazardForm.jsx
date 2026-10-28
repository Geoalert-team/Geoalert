import React from 'react';
import CloseFireForm from './CloseFireForm';
import CloseEventForm from './CloseEventForm';

/**
 * The form DRRMO fills in when a hazard is over. Used in two places —
 * inside the map's hazard panel and inside the DRRMO dashboard — so it
 * styles itself entirely with db- classes from Dashboard.css and brings
 * no stylesheet of its own. Outside a .db page, wrap it in .db-scope so
 * the tokens resolve.
 *
 * Each hazard is filed as one row of its log, with what the barangay
 * reported about the zone (ZoneReports) in view: a fire gets CloseFireForm,
 * the BFP fire log's columns G to W; a flood, landslide or any other type
 * gets CloseEventForm, the flood and landslide log's columns G to N.
 *
 * Props:
 *   zoneId            hazard zone UUID
 *   title             what's being resolved, e.g. "Flood · Tabunok"
 *   hazardType        the zone's hazard type name; 'Fire' opens the fire form
 *   onCancel()        close without doing anything
 *   onResolved(zone)  called with the updated zone after it is resolved
 */
export default function ResolveHazardForm({ hazardType, ...props }) {
  return (hazardType || '').toLowerCase() === 'fire'
    ? <CloseFireForm {...props} />
    : <CloseEventForm hazardType={hazardType} {...props} />;
}
