import React, { useState } from 'react';

// The one list of hotlines, shown on the homepage and the Contact page.
// TODO: confirm these numbers. The old homepage listed Social Welfare as (032) 407-5926.
// Later this list can come from the Django API instead (see src/api/).
export const HOTLINES = [
  { name: 'Talisay DRRMO', number: '(032) 407-5928', icon: 'M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z' },
  { name: 'Fire station', number: '(032) 407-5928', icon: 'M12 3c1 4 5 5.5 5 10.5A5 5 0 0 1 7 13.5C7 11 8.5 9.5 9.5 8.5c0 2 1 3 2 3 0-3-.5-5.5.5-8.5z' },
  { name: 'Police', number: '(032) 407-5928', icon: 'M12 3l2.6 5.6 6.1.7-4.5 4.1 1.2 6-5.4-3-5.4 3 1.2-6-4.5-4.1 6.1-.7L12 3z' },
  { name: 'Social welfare', number: '(032) 407-5928', icon: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z' },
];

const PHONE_ICON = 'M6.6 3.5l2.6.6 1.2 3.6-1.7 1.4a12 12 0 0 0 6.2 6.2l1.4-1.7 3.6 1.2.6 2.6c0 1.2-1 2.1-2.2 2C10.5 19.7 4.3 13.5 4.6 5.7c0-1.2.8-2.2 2-2.2z';

// "(032) 407-5928" -> "tel:+63324075928" (Philippine landline format)
export function toTelLink(number) {
  const digits = number.replace(/\D/g, '');
  const withCountry = digits.startsWith('0') ? '63' + digits.slice(1) : digits;
  return `tel:+${withCountry}`;
}

export default function HotlineGrid() {
  // Which hotline was just copied: { name, ok }
  const [copyStatus, setCopyStatus] = useState(null);

  async function copyNumber(hotline) {
    try {
      await navigator.clipboard.writeText(hotline.number);
      setCopyStatus({ name: hotline.name, ok: true });
    } catch {
      // Clipboard can fail on non-HTTPS pages
      setCopyStatus({ name: hotline.name, ok: false });
    }
    setTimeout(() => setCopyStatus(null), 2000);
  }

  function copyLabel(hotline) {
    if (!copyStatus || copyStatus.name !== hotline.name) return 'Copy number';
    return copyStatus.ok ? 'Copied' : 'Select and copy the number';
  }

  return (
    <ul className="ph-hotline-grid">
      {HOTLINES.map((hotline, i) => {
        const copied = copyStatus?.name === hotline.name && copyStatus.ok;
        return (
          // The DRRMO comes first and stands out: the number to try first
          <li key={hotline.name} className={`ph-hotline-card ${i === 0 ? 'is-primary' : ''}`}>
            <span className="ph-hotline-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d={hotline.icon} /></svg>
            </span>
            <h3>{hotline.name}</h3>
            <a className="ph-hotline-number" href={toTelLink(hotline.number)}>
              {hotline.number}
            </a>
            <div className="ph-hotline-actions">
              <a className="ph-call" href={toTelLink(hotline.number)} aria-label={`Call ${hotline.name}`}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d={PHONE_ICON} /></svg>
                Call
              </a>
              <button
                type="button"
                className={`ph-btn-copy ${copied ? 'is-copied' : ''}`}
                onClick={() => copyNumber(hotline)}
              >
                {copyLabel(hotline)}
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
