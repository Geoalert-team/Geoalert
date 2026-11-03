import React from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import HotlineGrid, { HOTLINES, toTelLink } from '../components/Hotlines/HotlineGrid';
import logo from '../assets/images/logo1.png';
import './css/PublicHome.css'; // shared ph- styles: sections, buttons, hotline cards, footer
import './css/Contact.css';    // styles only used on this page (ct-)

/* ---------- Page content (edit these lists to change the text) ---------- */

const OFFICE = {
  name: 'Talisay City DRRM Office',
  address: '7R3J+4HR, Cebu South Coastal Road, Talisay City, Cebu',
  mapEmbed: 'https://www.google.com/maps?q=10.2539713,123.8286349&z=17&output=embed',
  directions: 'https://www.google.com/maps/dir/?api=1&destination=10.2539713,123.8286349',
};

const PIN_ICON = 'M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21zM12 11.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z';

/* ---------- Page ---------- */

export default function Contact() {
  const drrmo = HOTLINES[0];

  return (
    <div className="ph">
      <a className="ph-skip" href="#ph-main">Skip to content</a>
      <PublicNavbar />

      <main id="ph-main">
        {/* ============ HERO ============ */}
        <section className="ct-hero">
          <div className="ph-container ct-hero-grid">
            <div>
              <p className="ct-hero-place">Talisay City DRRMO</p>
              <h1 className="ct-hero-title">Contact and emergency hotlines</h1>
              <p className="ct-hero-lead">
                Reach the right people when it matters most. Save these numbers before you need them.
              </p>
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

            <HotlineGrid />
          </div>
        </section>

        {/* ============ OFFICE LOCATION ============ */}
        <section className="ph-section ph-section-tint">
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
                <span className="ph-hotline-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d={PIN_ICON} /></svg>
                </span>
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
              <p className="ph-footer-name">GeoAlert Talisay</p>
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
        <p className="ph-container ph-footer-copy">&copy; {new Date().getFullYear()} GeoAlert Talisay</p>
      </footer>
    </div>
  );
}