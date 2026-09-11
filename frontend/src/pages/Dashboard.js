import React, { useState } from 'react';
import { useAuth } from '../api/AuthContext';
import HazardMap from '../components/HazardMap';
import PublishHazardModal from '../components/PublishHazardModal';
import AlertsPanel from '../components/AlertsPanel';
import IncidentReports from './IncidentReports';
import Guidance from './Guidance';
import Analytics from './Analytics';
import AdminPanel from './AdminPanel';

const roleName = (user) => user?.role?.name || user?.role || '';

export default function Dashboard() {
  const { user, logout, canPublish } = useAuth();
  const role = roleName(user);
  const [tab, setTab] = useState('map');
  const [showPublish, setShowPublish] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const isDRRMO = ['DRRMO_Officer', 'System_Admin'].includes(role);
  const isAdmin = role === 'System_Admin';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderBottom: '1px solid var(--line)', background: 'var(--panel)' }}>
        <h1 style={{ fontSize: 19, margin: 0 }}>GeoAlert â€” Talisay City</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: 13 }}>{user?.email} <span className="muted">({role})</span></span>
          <button className="btn" onClick={logout}>Log out</button>
        </div>
      </header>

      <nav className="nav-tabs">
        <button className={tab === 'map' ? 'active' : ''} onClick={() => setTab('map')}>Hazard Map</button>
        <button className={tab === 'incidents' ? 'active' : ''} onClick={() => setTab('incidents')}>Incident Reports</button>
        {isDRRMO && <button className={tab === 'guidance' ? 'active' : ''} onClick={() => setTab('guidance')}>Safety Guidance</button>}
        {isDRRMO && <button className={tab === 'analytics' ? 'active' : ''} onClick={() => setTab('analytics')}>Analytics & Reports</button>}
        {isAdmin && <button className={tab === 'admin' ? 'active' : ''} onClick={() => setTab('admin')}>System Admin</button>}
      </nav>

      {tab === 'map' && (
        <>
          <AlertsPanel />
          <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
            {canPublish && <button className="btn primary floating-action" onClick={() => setShowPublish(true)}>Publish hazard</button>}
            <HazardMap refreshKey={refreshKey} />
          </div>
        </>
      )}

      {tab === 'incidents' && <div className="scroll-page"><IncidentReports /></div>}
      {tab === 'guidance' && isDRRMO && <div className="scroll-page"><Guidance /></div>}
      {tab === 'analytics' && isDRRMO && <div className="scroll-page"><Analytics /></div>}
      {tab === 'admin' && isAdmin && <div className="scroll-page"><AdminPanel /></div>}

      {showPublish && (
        <PublishHazardModal
          hazardTypes={[]}
          barangays={[]}
          onClose={() => setShowPublish(false)}
          onCreated={() => { setShowPublish(false); setRefreshKey(k => k + 1); }}
        />
      )}
    </div>
  );
}
