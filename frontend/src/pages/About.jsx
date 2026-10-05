import React from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import logo from '../assets/images/logo1.png';
import './css/PublicHome.css'; // shared ph- styles: sections, buttons, hazard cards, risk scale, footer
import './css/About.css';      // styles only used on this page (ab-)

/* ---------- Page content (edit these lists to change the text) ---------- */

const FEATURES = [
  {
    key: 'realtime',
    title: 'Real-time data',
    text: 'Risk levels on the map are updated by the DRRMO as conditions change.',
    icon: (
      <>
        <path d="M12 21s-6-5.3-6-10a6 6 0 0 1 12 0c0 4.7-6 10-6 10z" />
        <circle cx="12" cy="11" r="2" />
      </>
    ),
  },
  {
    key: 'guidance',
    title: 'Safety guidance',
    text: 'Clear steps for what to do before, during and after each hazard.',
    icon: <path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z" />,
  },
  {
    key: 'history',
    title: 'Historical data',
    text: 'Past hazard records help spot the areas that are affected again and again.',
    icon: <path d="M4 20V10 M10 20V4 M16 20v-7 M22 20H2" />,
  },
  {
    key: 'secure',
    title: 'Secure access',
    text: 'Staff accounts are protected with two-factor authentication.',
    icon: (
      <>
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </>
    ),
  },
];

const HAZARDS = [
  {
    key: 'flood',
    name: 'Floods',
    text: 'Rising water from heavy rain, overflowing rivers and blocked drainage.',
    icon: <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" />,
  },
  {
    key: 'landslide',
    name: 'Landslides',
    text: 'Soil and rock movement on slopes, most likely after days of steady rain.',
    icon: <path d="M3 20l6-12 4 7 3-4 5 9z" />,
  },
  {
    key: 'fire',
    name: 'Fires',
    text: 'Fire risk in closely built neighborhoods, especially during the dry months.',
    icon: <path d="M12 3c1 4 5 5.5 5 10.5A5 5 0 0 1 7 13.5C7 11 8.5 9.5 9.5 8.5c0 2 1 3 2 3 0-3-.5-5.5.5-8.5z" />,
  },
];

const RISK_LEVELS = [
  { key: 'low', name: 'Low risk', meaning: 'The area is currently safe. Standard monitoring is in place.' },
  { key: 'medium', name: 'Medium risk', meaning: 'Be prepared and keep watching for updates.' },
  { key: 'high', name: 'High risk', meaning: 'Immediate danger. Take action or evacuate.' },
];

/* ---------- Page ---------- */

export default function About() {
  return (
    <div className="ph">
      <a className="ph-skip" href="#ph-main">Skip to content</a>
      <PublicNavbar />

      <main id="ph-main">
        {/* ============ HERO ============ */}
        <section className="ab-hero">
          <div className="ph-container">
            <p className="ab-hero-place">Talisay City DRRMO</p>
            <h1 className="ab-hero-title">About GeoAlert</h1>
            <p className="ab-hero-lead">
              Real-time hazard mapping, clear safety guidance and coordinated disaster
              preparedness for every barangay in Talisay City.
            </p>
          </div>
        </section>

        {/* ============ MISSION + FEATURES ============ */}
        <section className="ph-section">
          <div className="ph-container ab-mission">
            <div className="ab-mission-text">
              <h2>Strengthening community resilience</h2>
              <p>
                GeoAlert was developed with the Talisay City Disaster Risk Reduction and Management
                Office (DRRMO) to bring critical hazard information together in one place that
                anyone can open on their phone.
              </p>
              <p>
                Residents can check the risk in their own barangay and decide what to do next,
                while emergency responders get a shared picture that helps them coordinate faster
                and more safely.
              </p>
              <div className="ab-mission-actions">
                <Link className="ph-btn ph-btn-primary" to="/map">Explore the map</Link>
                <Link className="ph-btn ph-btn-outline" to="/contact">Contact the DRRMO</Link>
              </div>
            </div>

            <ul className="ab-feature-grid">
              {FEATURES.map((feature) => (
                <li key={feature.key} className={`ab-feature ab-feature-${feature.key}`}>
                  <div className="ab-feature-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">{feature.icon}</svg>
                  </div>
                  <h3>{feature.title}</h3>
                  <p>{feature.text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ============ HAZARDS ============ */}
        <section className="ph-section ph-section-tint">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Hazards we monitor</h2>
              <p>
                The map shows each hazard with a simple color code, so you can spot the danger
                level in your community at a glance.
              </p>
            </div>

            <div className="ph-hazard-grid">
              {HAZARDS.map((hazard) => (
                <article key={hazard.key} className={`ph-hazard-card ph-hazard-${hazard.key}`}>
                  <div className="ph-hazard-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">{hazard.icon}</svg>
                  </div>
                  <h3>{hazard.name}</h3>
                  <p>{hazard.text}</p>
                  <ul className="ph-level-list">
                    <li><span className="ph-dot ph-dot-low" />Low risk</li>
                    <li><span className="ph-dot ph-dot-medium" />Medium risk</li>
                    <li><span className="ph-dot ph-dot-high" />High risk</li>
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ============ RISK LEVELS ============ */}
        <section className="ph-section">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Understanding the risk levels</h2>
            </div>

            <ol className="ph-risk-scale ab-risk-scale">
              {RISK_LEVELS.map((level) => (
                <li key={level.key} className={`ph-risk-step ph-risk-${level.key}`}>
                  <h3>{level.name}</h3>
                  <p className="ph-risk-meaning">{level.meaning}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ============ TEAM ============ */}
        <section className="ph-section ph-section-tint">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Who runs GeoAlert</h2>
            </div>

            <div className="ab-team-card">
              {/* Photo placeholder: replace the span with <img src={...} alt="Name of the DRRMO Head"> */}
              <span className="ab-team-photo" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
                </svg>
              </span>
              <div>
                <h3>DRRMO Head</h3>
                <p className="ab-team-org">Talisay City Disaster Risk Reduction and Management Office</p>
                <p className="ab-team-role">Oversees the GeoAlert team.</p>
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