import React from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';

export default function Contact() {
  return (
    <div className="public-page">
      <PublicNavbar />
      <div className="simple-page">
        <h1>Contact Us</h1>
        <p>Reach the Talisay City DRRMO office for questions, reports, or feedback about GeoAlert.</p>
      </div>
    </div>
  );
}