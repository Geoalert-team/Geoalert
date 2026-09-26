import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import logo from '../assets/images/logo1.png';
import photo1 from '../assets/images/p1.jpg';
import photo2 from '../assets/images/p2.jpg';
import photo3 from '../assets/images/p3.jpg';
import './css/PublicHome.css';

/* ---------- Page content (edit these lists to change the text) ---------- */

// Change the alt text to describe what each photo actually shows
const SLIDES = [
  { src: photo1, alt: 'Rescue team loading a stretcher into an ambulance' },
  { src: photo2, alt: 'Residents taking part in a community drill' },
  { src: photo3, alt: 'Talisay City coastline' },
];

const SLIDE_INTERVAL_MS = 6000;

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
  {
    key: 'low',
    name: 'Low risk',
    meaning: 'The area is safe. Standard monitoring is in place.',
    action: 'go about your day and keep your go-bag ready.',
  },
  {
    key: 'medium',
    name: 'Medium risk',
    meaning: 'Conditions could get worse. Stay alert.',
    action: 'watch weather updates and know your evacuation route.',
  },
  {
    key: 'high',
    name: 'High risk',
    meaning: 'Immediate action is required.',
    action: 'prepare to evacuate and follow barangay officials.',
  },
];

const STEPS = [
  { title: 'Open the map', text: 'No sign-up needed. The map opens centered on Talisay City.' },
  { title: 'Find your barangay', text: 'Zoom in to your area and tap a shaded zone to see its risk level.' },
  { title: 'Follow the guidance', text: 'Each hazard shows simple steps for before, during and after an event.' },
];

// TODO: confirm these numbers. The old homepage listed Social Welfare as (032) 407-5926.
// Later this list can come from the Django API instead (see src/api/).
const HOTLINES = [
  { name: 'Talisay DRRMO', number: '(032) 407-5928' },
  { name: 'Fire station', number: '(032) 407-5928' },
  { name: 'Police', number: '(032) 407-5928' },
  { name: 'Social welfare', number: '(032) 407-5928' },
];

/* ---------- Helpers ---------- */

// "(032) 407-5928" -> "tel:+63324075928" (Philippine landline format)
function toTelLink(number) {
  const digits = number.replace(/\D/g, '');
  const withCountry = digits.startsWith('0') ? '63' + digits.slice(1) : digits;
  return `tel:+${withCountry}`;
}

/* ---------- Page ---------- */

export default function PublicHome() {
  // Photo slider
  const [currentSlide, setCurrentSlide] = useState(0);
  const [paused, setPaused] = useState(false);

  // Which hotline was just copied: { name, ok }
  const [copyStatus, setCopyStatus] = useState(null);

  // Move to the next photo every few seconds (restarts when a dot is clicked)
  useEffect(() => {
    if (paused) return undefined;
    const timer = setInterval(() => {
      setCurrentSlide((i) => (i + 1) % SLIDES.length);
    }, SLIDE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [paused, currentSlide]);

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
    <div className="ph">
      <a className="ph-skip" href="#ph-main">Skip to content</a>
      <PublicNavbar />

      <main id="ph-main">
        {/* ============ HERO ============ */}
        <section className="ph-hero">
          <div className="ph-container ph-hero-grid">
            <div>
              <p className="ph-place">Talisay City, Cebu</p>
              <h1 className="ph-hero-title">
                See which parts of Talisay are at risk, and what to do about it.
              </h1>
              <p className="ph-hero-lead">
                GeoAlert is a community hazard map for Talisay City. Check the current risk level
                for floods, landslides, storm surges and fires in your barangay, then follow clear
                safety steps.
              </p>
              <div className="ph-hero-actions">
                <Link className="ph-btn ph-btn-primary" to="/map">Explore the map</Link>
                <Link className="ph-btn ph-btn-outline" to="/what-to-do">See safety steps</Link>
              </div>
              <p className="ph-hero-note">No account needed to view the map.</p>
            </div>

            <div
              className="ph-slider"
              onMouseEnter={() => setPaused(true)}
              onMouseLeave={() => setPaused(false)}
            >
              <div
                className="ph-slider-track"
                style={{ transform: `translateX(-${currentSlide * 100}%)` }}
              >
                {SLIDES.map((slide) => (
                  <div className="ph-slide" key={slide.alt}>
                    <img src={slide.src} alt={slide.alt} />
                  </div>
                ))}
              </div>

              <div className="ph-slider-dots" role="group" aria-label="Choose photo">
                {SLIDES.map((slide, i) => (
                  <button
                    key={slide.alt}
                    type="button"
                    className={`ph-slider-dot ${i === currentSlide ? 'is-active' : ''}`}
                    aria-label={`Photo ${i + 1}`}
                    aria-pressed={i === currentSlide}
                    onClick={() => setCurrentSlide(i)}
                  />
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ============ HAZARDS ============ */}
        <section className="ph-section">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Hazards we monitor</h2>
              <p>Each hazard is rated low, medium or high so you can tell at a glance how worried to be.</p>
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
        <section className="ph-section ph-section-tint">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>What the colors mean</h2>
              <p>The map uses the same three colors everywhere. Here is what each one asks of you.</p>
            </div>

            <ol className="ph-risk-scale">
              {RISK_LEVELS.map((level) => (
                <li key={level.key} className={`ph-risk-step ph-risk-${level.key}`}>
                  <h3>{level.name}</h3>
                  <p className="ph-risk-meaning">{level.meaning}</p>
                  <p className="ph-risk-action"><strong>You:</strong> {level.action}</p>
                </li>
              ))}
            </ol>

            <div className="ph-center">
              <Link className="ph-btn ph-btn-primary" to="/what-to-do">Learn safety protocols</Link>
            </div>
          </div>
        </section>

        {/* ============ HOW IT WORKS ============ */}
        <section className="ph-section">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>How to use GeoAlert</h2>
            </div>

            <ol className="ph-steps">
              {STEPS.map((step, i) => (
                <li key={step.title}>
                  <span className="ph-step-num" aria-hidden="true">{i + 1}</span>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ============ HOTLINES ============ */}
        <section className="ph-section ph-section-tint">
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
      </main>

      {/* ============ FOOTER ============ */}
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