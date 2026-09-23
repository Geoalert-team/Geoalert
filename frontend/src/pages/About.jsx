import React from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';

export default function About() {
  return (
    <div className="public-page">
      <PublicNavbar />
      <div className="simple-page">
        <h1>About GeoAlert</h1>
        <p>GeoAlert helps residents of Talisay City stay informed about flood, landslide, and fire hazards through real-time geospatial data.</p>
      </div>
    </div>
  );
}