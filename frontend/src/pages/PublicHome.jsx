import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import hero1 from '../assets/images/drrmo1.jpg';
import hero2 from '../assets/images/drrmo2.jpg';
import hero3 from '../assets/images/drrmo3.jpg';

const HERO_IMAGES = [hero1, hero2, hero3];

const HOTLINES = [
  { name: 'Talisay DRRMO', number: '(032) 407-5928' },
  { name: 'Fire Station', number: '(032) 407-5928' },
  { name: 'Police', number: '(032) 407-5928' },
  { name: 'Social Welfare', number: '(032) 407-5926' },
];

export default function PublicHome() {
  const navigate = useNavigate();
  const [activeSlide, setActiveSlide] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveSlide((prev) => (prev + 1) % HERO_IMAGES.length);
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="public-page">
      <PublicNavbar />

      <section className="hero">
        <div className="hero-image">
          {HERO_IMAGES.map((img, i) => (
            <img
              key={i}
              src={img}
              alt={`GeoAlert community outreach ${i + 1}`}
              className={i === activeSlide ? 'active' : ''}
            />
          ))}
          <div className="hero-dots">
            {HERO_IMAGES.map((_, i) => (
              <button
                key={i}
                className={`hero-dot ${i === activeSlide ? 'active' : ''}`}
                onClick={() => setActiveSlide(i)}
                aria-label={`Show slide ${i + 1}`}
              />
            ))}
          </div>
        </div>

        <div className="hero-text">
          <h1>Welcome to <span className="hero-accent">GeoAlert</span></h1>
          <p>
            GeoAlert is a community-centered hazard awareness system that helps residents in
            Talisay City identify disaster-prone areas through an interactive map. Get real-time
            risk levels and actionable safety guidance for floods, landslides, storm surges, and fires.
          </p>
          <button className="btn primary hero-cta" onClick={() => navigate('/map')}>
            Explore the Map
          </button>
        </div>
      </section>

   

      <section className="hazards-section">
        <h2 className="section-title">Hazards We Monitor</h2>
        <p className="section-subtitle">
          GeoAlert tracks real-time hazard data using color-coded indicators so you can instantly
          identify risk levels in your community.
        </p>
      <div className="hazard-cards">
      <div className="hazard-card flood">
        <div className="hazard-card-icon">💧</div>
        <div className="hazard-card-title">Floods</div>
        <ul className="risk-list">
          <li><span className="dot green" /> Low Risk</li>
          <li><span className="dot orange" /> Medium Risk</li>
          <li><span className="dot red" /> High Risk</li>
        </ul>
      </div>
      <div className="hazard-card landslide">
        <div className="hazard-card-icon">⛰️</div>
        <div className="hazard-card-title">Landslides</div>
        <ul className="risk-list">
          <li><span className="dot green" /> Low Risk</li>
          <li><span className="dot orange" /> Medium Risk</li>
          <li><span className="dot red" /> High Risk</li>
        </ul>
      </div>
      <div className="hazard-card fire">
        <div className="hazard-card-icon">🔥</div>
        <div className="hazard-card-title">Fires</div>
        <ul className="risk-list">
          <li><span className="dot green" /> Low Risk</li>
          <li><span className="dot orange" /> Medium Risk</li>
          <li><span className="dot red" /> High Risk</li>
        </ul>
      </div>
    </div>
      </section>

      <section className="risk-legend-section">
        <h3 className="section-title small">Understanding Risk Levels</h3>
        <div className="risk-legend-row">
          <div className="risk-legend-item">
            <div><span className="dot green" /> <strong>Low Risk</strong></div>
            <p>Area is safe with standard monitoring in place.</p>
          </div>
          <div className="risk-legend-item">
            <div><span className="dot orange" /> <strong>Medium Risk</strong></div>
            <p>Be prepared and actively monitor weather alerts.</p>
          </div>
          <div className="risk-legend-item">
            <div><span className="dot red" /> <strong>High Risk</strong></div>
            <p>Immediate action required. Prepare to evacuate.</p>
          </div>
        </div>
        <div className="risk-legend-cta">
          <button className="btn primary" onClick={() => navigate('/what-to-do')}>
            Learn Safety Protocols
          </button>
        </div>
      </section>

      <section className="hotlines-section">
        <h2 className="section-title">Emergency Hotlines</h2>
        <p className="section-subtitle">Quick access to emergency response teams and disaster support services.</p>
        <div className="hotline-cards">
          {HOTLINES.map((h) => (
            <div key={h.name} className="hotline-card">
              <div className="hotline-icon">☎</div>
              <div className="hotline-name">{h.name}</div>
              <div className="hotline-number">{h.number}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="public-footer">
        GeoAlert · Community Geospatial Hazard Guidance & Risk Awareness for Talisay City
      </footer>
    </div>
  );
}