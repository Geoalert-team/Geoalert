import React from 'react';
import Meter from '../Charts/Meter';
import StatTile from './StatTile';
import { duration } from './measures';

/**
 * How well the office responded: two shares as meters (alerts opened,
 * reports reviewed) and three median times. Medians, so one slow case does
 * not drag the figure.
 */

const num = (n) => (n ?? 0).toLocaleString();

export default function ResponseBand({ kpis: k }) {
  return (
    <section className="an-band" aria-labelledby="an-response">
      <h2 id="an-response">Response</h2>
      <p className="db-card-sub">
        How quickly alerts were read and reports were reviewed. Medians, so one slow case does not skew them.
      </p>
      <div className="an-meters">
        <Meter
          value={k.read_rate}
          label="Alert notices opened"
          caption={`${num(k.notices_read)} of ${num(k.notices_sent)} sent`}
          emptyCaption="None sent in this period"
        />
        <Meter
          value={k.review_rate}
          label="Incident reports reviewed"
          caption={`${num(k.incidents_validated)} validated, ${num(k.incidents_rejected)} rejected`}
          emptyCaption="None submitted in this period"
        />
      </div>
      <div className="an-medians">
        <StatTile value={duration(k.median_minutes_to_read)} label="to open an alert" hint="from when it was sent" />
        <StatTile value={duration(k.median_minutes_to_review)} label="to review a report" hint="from submission to decision" />
        <StatTile value={duration(k.median_minutes_zone_active)} label="a zone stayed active" hint="from publishing to resolved" />
      </div>
    </section>
  );
}
