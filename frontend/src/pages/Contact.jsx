import React from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';

const HOTLINES = [
  { name: 'DRRMO', number: '(032) 407-5928' },
  { name: 'Fire Station', number: '(032) 407-5928' },
  { name: 'Police', number: '(032) 407-5928' },
  { name: 'Social Welfare', number: '(032) 407-5928' },
];

export default function Contact() {
  return (
    <div className="public-page">
      <PublicNavbar />

      <section className="contact-hero-dark">
        <h1>Emergency Hotlines & Contacts</h1>
        <p>Reach the right people when it matters most. Quick access to emergency services and community support.</p>
      </section>

      <div className="contact-body">
        <h2>Emergency Hotlines</h2>
        <div className="hotline-mini-grid">
          {HOTLINES.map((h) => (
            <div key={h.name} className="hotline-mini-card">
              <div className="hotline-mini-icon">☎</div>
              <div className="hotline-mini-name">{h.name}</div>
              <div className="hotline-mini-number">{h.number}</div>
            </div>
          ))}
        </div>

        <h2>Get In Touch</h2>
        <div className="touch-grid">
          <div className="touch-card email">
            <div className="touch-card-header">
              <div className="touch-card-icon">✉️</div>
              Email
            </div>
            <p className="muted">We respond within 24 hours</p>
            <div className="label">General</div>
            <div className="link">geoalert.talisay@gmail.com</div>
            <div className="label">Support</div>
            <div className="link">support@geoalert.talisay.ph</div>
          </div>
          <div className="touch-card social">
            <div className="touch-card-header">
              <div className="touch-card-icon">🌐</div>
              Follow Us
            </div>
            <p className="muted">Real-time updates & alerts</p>
            <div className="label">Facebook</div>
            <div className="link">facebook.com/GeoAlertTalisay</div>
            <div className="label">Website</div>
            <div className="link">www.geoalert.talisay.ph</div>
          </div>
        </div>

        <h2>Office Location</h2>
        <div className="office-grid">
          <iframe
            className="office-map-frame"
            title="DRRMO Office Location"
            src="https://www.google.com/maps?q=10.2539713,123.8286349&z=17&output=embed"
            width="100%"
            height="220"
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
          />
          <div className="office-info-card">
            <div className="name">DRRMO Office</div>
            <div className="address">Talisay City DRRM Office<br />7R3J+4HR, Cebu South Coastal Rd</div>
            <button
            className="btn primary"
            style={{ width: '100%' }}
            onClick={() => window.open('https://www.google.com/maps/dir/?api=1&destination=10.2539713,123.8286349', '_blank')}
          >📍 Get Directions
          </button>
            
          </div>
        </div>
      </div>

      <footer className="public-footer">
        GeoAlert · Community Geospatial Hazard Guidance & Risk Awareness for Talisay City
      </footer>
    </div>
  );
}