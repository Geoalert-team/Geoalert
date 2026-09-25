import React from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';

export default function About() {
  return (
    <div className="public-page">
      <PublicNavbar />

      <section className="about-hero">
        <div className="about-eyebrow">• Talisay City Disaster Risk Reduction</div>
        <h1>About GeoAlert</h1>
        <p>Empowering communities through real-time hazard mapping, actionable guidance, and coordinated disaster preparedness.</p>
      </section>

      <section className="about-resilience">
        <div className="about-resilience-text">
          <h2>Strengthening Community Resilience</h2>
          <p>Developed in collaboration with the Talisay City Disaster Risk Reduction and Management Office (DRRMO), GeoAlert consolidates critical hazard information into a single, accessible platform.</p>
          <p>By delivering real-time, unified, and actionable hazard guidance across all devices, we bridge the information gap. GeoAlert empowers residents to make informed decisions and supports emergency responders in coordinating faster, safer operations.</p>
        </div>

        <div className="about-feature-grid">
          <div className="about-feature-card">
            <div className="icon-badge pink">📍</div>
            Real-Time Data
          </div>
          <div className="about-feature-card">
            <div className="icon-badge blue">🛡️</div>
            Safety Guidance
          </div>
          <div className="about-feature-card">
            <div className="icon-badge green">📊</div>
            Historical Data
          </div>
          <div className="about-feature-card">
            <div className="icon-badge orange">🔒</div>
            Secure Access
          </div>
        </div>
      </section>

      <section className="hazards-section">
        <h2 className="section-title">Hazards We Monitor</h2>
        <p className="section-subtitle">
          GeoAlert actively monitors Talisay City for specific threats. Our interactive map uses a simple
          color-coded pin system so you can instantly spot the danger level in your community.
        </p>
        <div className="about-hazard-grid">
          <div className="about-hazard-item">
            <div className="icon">💧</div>
            <div className="name">Flood</div>
            <ul className="risk-list">
              <li><span className="dot green" /> Low Risk</li>
              <li><span className="dot orange" /> Medium Risk</li>
              <li><span className="dot red" /> High Risk</li>
            </ul>
          </div>
          <div className="about-hazard-item">
            <div className="icon">⛰️</div>
            <div className="name">Landslide</div>
            <ul className="risk-list">
              <li><span className="dot green" /> Low Risk</li>
              <li><span className="dot orange" /> Medium Risk</li>
              <li><span className="dot red" /> High Risk</li>
            </ul>
          </div>
          <div className="about-hazard-item">
            <div className="icon">🔥</div>
            <div className="name">Fire</div>
            <ul className="risk-list">
              <li><span className="dot green" /> Low Risk</li>
              <li><span className="dot orange" /> Medium Risk</li>
              <li><span className="dot red" /> High Risk</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="risk-legend-section">
        <h3 className="section-title small">Understanding The Risk Level</h3>
        <div className="risk-explain-row">
          <div className="risk-explain-item">
            <span className="dot green" />
            <strong>Low Risk</strong>
            <p>Area is currently safe. Standard monitoring.</p>
          </div>
          <div className="risk-explain-item">
            <span className="dot orange" />
            <strong>Medium Risk</strong>
            <p>Be prepared and monitor updates.</p>
          </div>
          <div className="risk-explain-item">
            <span className="dot red" />
            <strong>High Risk</strong>
            <p>Immediate danger. Take action or evacuate.</p>
          </div>
        </div>
      </section>

      <div className="team-card">
        <div className="team-avatar">👤</div>
        <div>
          <div className="name">DRRMO Head</div>
          <div className="role">Talisay City Disaster Risk Reduction — Oversight of the team →</div>
        </div>
      </div>

      <footer className="public-footer">
        GeoAlert · Community Geospatial Hazard Guidance & Risk Awareness for Talisay City
      </footer>
    </div>
  );
}