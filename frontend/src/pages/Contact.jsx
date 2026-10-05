import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import logo from '../assets/images/logo1.png';
import './css/PublicHome.css'; // shared ph- styles: sections, buttons, hotline cards, footer
import './css/Contact.css';    // styles only used on this page (ct-)

/* ---------- Page content (edit these lists to change the text) ---------- */

// TODO: confirm these numbers with the DRRMO
const HOTLINES = [
  { name: 'Talisay DRRMO', number: '(032) 407-5928' },
  { name: 'Fire station', number: '(032) 407-5928' },
  { name: 'Police', number: '(032) 407-5928' },
  { name: 'Social welfare', number: '(032) 407-5928' },
];

const EMAILS = [
  { label: 'General questions', address: 'geoalert.talisay@gmail.com' },
  { label: 'Technical support', address: 'support@geoalert.talisay.ph' },
];

const SOCIALS = [
  { label: 'Facebook', text: 'facebook.com/GeoAlertTalisay', url: 'https://facebook.com/GeoAlertTalisay' },
  { label: 'Website', text: 'www.geoalert.talisay.ph', url: 'https://www.geoalert.talisay.ph' },
];

const OFFICE = {
  name: 'Talisay City DRRM Office',
  address: '7R3J+4HR, Cebu South Coastal Road, Talisay City, Cebu',
  mapEmbed: 'https://www.google.com/maps?q=10.2539713,123.8286349&z=17&output=embed',
  directions: 'https://www.google.com/maps/dir/?api=1&destination=10.2539713,123.8286349',
};

/* ---------- Helpers ---------- */

// "(032) 407-5928" -> "tel:+63324075928" (Philippine landline format)
function toTelLink(number) {
  const digits = number.replace(/\D/g, '');
  const withCountry = digits.startsWith('0') ? '63' + digits.slice(1) : digits;
  return `tel:+${withCountry}`;
}

/* ---------- Page ---------- */

export default function Contact() {
  // Which hotline was just copied: { name, ok }
  const [copyStatus, setCopyStatus] = useState(null);

  async function copyNumber(hotline) {
    try {
      await navigator.clipboard.writeText(hotline.number);
      setCopyStatus({ name: hotline.name, ok: true });
    } catch {
      setCopyStatus({ name: hotline.name, ok: false });
    }
    setTimeout(() => setCopyStatus(null), 2000);
  }

  function copyLabel(hotline) {
    if (!copyStatus || copyStatus.name !== hotline.name) return 'Copy number';
    return copyStatus.ok ? 'Copied' : 'Select and copy the number';
  }

  const drrmo = HOTLINES[0];

  return (
    <div className="ph">
      <a className="ph-skip" href="#ph-main">Skip to content</a>
      <PublicNavbar />

      <main id="ph-main">
        {/* ============ HERO + EMERGENCY CALLOUT ============ */}
        <section className="ct-hero">
          <div className="ph-container ct-hero-grid">
            <div>
              <p className="ct-hero-place">Talisay City DRRMO</p>
              <h1 className="ct-hero-title">Contact and emergency hotlines</h1>
              <p className="ct-hero-lead">
                Reach the right people when it matters most. Save these numbers before you need them.
              </p>
            </div>

            <div className="ct-urgent">
              <p className="ct-urgent-title">Life-threatening emergency?</p>
              <p className="ct-urgent-text">Call right away. Don't wait to send a message or email.</p>
              <div className="ct-urgent-actions">
                <a className="ph-btn ct-btn-white" href="tel:911">Call 911</a>
                <a className="ph-btn ct-btn-ghost" href={toTelLink(drrmo.number)}>
                  <span>Call DRRMO</span>
                  <span className="ct-nowrap">{drrmo.number}</span>
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* ============ HOTLINES ============ */}
        <section className="ph-section">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Emergency hotlines</h2>
              <p>Tap a number to call it on your phone, or copy it to save for later.</p>
            </div>

            <ul className="ph-hotline-grid">
              {HOTLINES.map((hotline) => {
                const copied = copyStatus?.name === hotline.name && copyStatus.ok;
                return (
                  <li key={hotline.name} className="ph-hotline-card">
                    <h3>{hotline.name}</h3>
                    <a className="ph-hotline-number" href={toTelLink(hotline.number)}>
                      {hotline.number}
                    </a>
                    <button
                      type="button"
                      className={`ph-btn-copy ${copied ? 'is-copied' : ''}`}
                      onClick={() => copyNumber(hotline)}
                    >
                      {copyLabel(hotline)}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        {/* ============ GET IN TOUCH ============ */}
        <section className="ph-section ph-section-tint">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Get in touch</h2>
              <p>For questions, feedback or help using GeoAlert. Not for emergencies.</p>
            </div>

            <div className="ct-contact-grid">
              <article className="ct-contact-card">
                <div className="ct-contact-icon ct-icon-email" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" /></svg>
                </div>
                <h3>Email</h3>
                <p className="ct-contact-note">We reply within 24 hours.</p>
                <dl className="ct-contact-list">
                  {EMAILS.map((email) => (
                    <div key={email.address}>
                      <dt>{email.label}</dt>
                      <dd><a href={`mailto:${email.address}`}>{email.address}</a></dd>
                    </div>
                  ))}
                </dl>
              </article>

              <article className="ct-contact-card">
                <div className="ct-contact-icon ct-icon-social" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></svg>
                </div>
                <h3>Follow us</h3>
                <p className="ct-contact-note">Real-time updates and alerts.</p>
                <dl className="ct-contact-list">
                  {SOCIALS.map((social) => (
                    <div key={social.label}>
                      <dt>{social.label}</dt>
                      <dd>
                        <a href={social.url} target="_blank" rel="noopener noreferrer">{social.text}</a>
                      </dd>
                    </div>
                  ))}
                </dl>
              </article>
            </div>
          </div>
        </section>

        {/* ============ OFFICE LOCATION ============ */}
        <section className="ph-section">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Office location</h2>
            </div>

            <div className="ct-office">
              <iframe
                className="ct-office-map"
                title="Map showing the Talisay City DRRM Office"
                src={OFFICE.mapEmbed}
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
              <div className="ct-office-info">
                <h3>{OFFICE.name}</h3>
                <p className="ct-office-address">{OFFICE.address}</p>
                <div className="ct-office-actions">
                  <a className="ph-btn ph-btn-primary" href={OFFICE.directions} target="_blank" rel="noopener noreferrer">
                    Get directions
                  </a>
                  <a className="ph-btn ph-btn-outline" href={toTelLink(drrmo.number)}>Call the office</a>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* ============ FOOTER (same as homepage) ============ */}
      <footer className="ph-footer">
        <div className="ph-container ph-footer-inner">
          <div className="ph-footer-brand">
            <span className="ph-footer-logo">
              <img src={logo} alt="" />
            </span>
            <div>
              <p className="ph-footer-name">GeoAlert</p>
              <p className="ph-footer-tagline">
                Community geospatial hazard guidance and risk awareness for Talisay City.
              </p>
            </div>
          </div>
          <ul className="ph-footer-links">
            <li><Link to="/map">Map</Link></li>
            <li><Link to="/about">About</Link></li>
            <li><Link to="/contact">Contact</Link></li>
            <li><Link to="/what-to-do">What to do</Link></li>
          </ul>
        </div>
        <p className="ph-container ph-footer-copy">&copy; {new Date().getFullYear()} GeoAlert</p>
      </footer>
    </div>
  );
}