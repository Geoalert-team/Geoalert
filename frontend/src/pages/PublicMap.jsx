import React from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import Map from '../components/Map';

export default function PublicMap() {
  return (
    <div className="public-page" style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <PublicNavbar />
      <div style={{ flex: 1, padding: 16 }}>
        <div className="map-inner" style={{ height: '100%' }}>
          <Map onSelectHazard={() => {}} refreshKey={0} />
        </div>
      </div>
    </div>
  );
}