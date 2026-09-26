import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { hazardIconPath, DRRMO_HOTLINE } from '../components/Map/hazardInfo';
import { GUIDES, PHASES, UNIVERSAL_TIPS, VIDEOS } from '../data/safetyGuides';
import logo from '../assets/images/logo1.png';
import './css/PublicHome.css'; // shared ph- styles: sections, buttons, footer
import './css/WhatToDo.css';   // styles only used on this page (wt-)

const HAZARDS = Object.keys(GUIDES); // ['Flood', 'Landslide', 'Fire']

// Simple line icons for the universal tips
const TIP_ICONS = {
  connected: 'M5 3h14v18H5z M9 18h6',
  routes: 'M4 19c4 0 4-7 8-7s4 7 8 7 M12 5v3 M9 8h6',
  family: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M2 20c0-3 3-5 6-5s6 2 6 5 M14 15c3 0 8 1 8 5',
  kit: 'M4 8h16v12H4z M9 8V5h6v3 M12 11v6 M9 14h6',
};

export default function WhatToDo() {
  const [hazard, setHazard] = useState('Flood');
  const [phase, setPhase] = useState('before');
  const [packed, setPacked] = useState({}); // { "Flood:Whistle": true }
  const [videoId, setVideoId] = useState(VIDEOS[0]?.id);

  const guide = GUIDES[hazard];
  const currentPhase = PHASES.find((p) => p.key === phase);

  // Videos for the chosen hazard come first in the list
  const sortedVideos = [...VIDEOS].sort(
    (a, b) => Number(b.hazard === hazard) - Number(a.hazard === hazard),
  );
  const activeVideo = VIDEOS.find((v) => v.id === videoId) || VIDEOS[0];

  const packedCount = guide.supplies.filter((item) => packed[`${hazard}:${item}`]).length;

  function chooseHazard(name) {
    setHazard(name);
    setPhase('before');
    const firstVideo = VIDEOS.find((v) => v.hazard === name);
    if (firstVideo) setVideoId(firstVideo.id);
  }

  function toggleSupply(item) {
    const key = `${hazard}:${item}`;
    setPacked((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="ph">
      <a className="ph-skip" href="#ph-main">Skip to content</a>
      <PublicNavbar />

      <main id="ph-main">
        {/* ============ HERO ============ */}
        <section className="wt-hero">
          <div className="ph-container">
            <p className="wt-hero-place">Safety guides</p>
            <h1 className="wt-hero-title">What to do</h1>
            <p className="wt-hero-lead">
              Step-by-step guides for floods, landslides and fires. Know your hazard, know your
              response, stay safe.
            </p>
          </div>
        </section>

        {/* ============ HAZARD GUIDE ============ */}
        <section className="ph-section">
          <div className="ph-container">
            {/* Hazard switcher */}
            <div className="wt-hazard-tabs" role="tablist" aria-label="Choose a hazard">
              {HAZARDS.map((name) => (
                <button
                  key={name}
                  type="button"
                  role="tab"
                  aria-selected={hazard === name}
                  className={`wt-hazard-tab wt-hazard-${name.toLowerCase()} ${hazard === name ? 'is-active' : ''}`}
                  onClick={() => chooseHazard(name)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d={hazardIconPath(name)} /></svg>
                  {name}
                </button>
              ))}
            </div>

            <div className="wt-guide-head">
              <h2>{guide.title}</h2>
              <p>{guide.intro}</p>
            </div>

            {/* Before / During / After / First aid */}
            <div className="wt-phases" role="tablist" aria-label={`${hazard} response steps`}>
              {PHASES.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  role="tab"
                  aria-selected={phase === p.key}
                  className={`wt-phase ${phase === p.key ? 'is-active' : ''}`}
                  onClick={() => setPhase(p.key)}
                >
                  <span className="wt-phase-num" aria-hidden="true">{p.number ?? '+'}</span>
                  <span className="wt-phase-text">
                    <strong>{p.title}</strong>
                    <small>{p.subtitle}</small>
                  </span>
                </button>
              ))}
            </div>

            <div className="wt-guide-body">
              {/* Steps for the chosen phase */}
              <div className="wt-steps-card" role="tabpanel">
                <h3>
                  {currentPhase.key === 'firstaid'
                    ? `First aid for ${hazard.toLowerCase()} injuries`
                    : `${currentPhase.title} a ${hazard.toLowerCase()}`}
                </h3>
                <ol className="wt-steps">
                  {guide.phases[phase].map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </div>

              {/* Go-bag checklist */}
              <aside className="wt-supplies-card">
                <div className="wt-supplies-head">
                  <h3>Go-bag checklist</h3>
                  <span className="wt-supplies-count">{packedCount} of {guide.supplies.length} packed</span>
                </div>
                <p className="wt-supplies-note">
                  Pack these before {hazard.toLowerCase()} season and keep the bag somewhere easy to grab.
                </p>
                <ul className="wt-supplies">
                  {guide.supplies.map((item) => {
                    const id = `supply-${hazard}-${item}`.replace(/\W+/g, '-');
                    const isPacked = !!packed[`${hazard}:${item}`];
                    return (
                      <li key={item}>
                        <input
                          id={id}
                          type="checkbox"
                          checked={isPacked}
                          onChange={() => toggleSupply(item)}
                        />
                        <label htmlFor={id}>{item}</label>
                      </li>
                    );
                  })}
                </ul>
              </aside>
            </div>
          </div>
        </section>

        {/* ============ UNIVERSAL TIPS ============ */}
        <section className="ph-section ph-section-tint">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Tips for every hazard</h2>
              <p>Small things you can do today that help in any emergency.</p>
            </div>

            <ul className="wt-tips">
              {UNIVERSAL_TIPS.map((tip) => (
                <li key={tip.key} className="wt-tip">
                  <span className="wt-tip-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path d={TIP_ICONS[tip.key]} /></svg>
                  </span>
                  <h3>{tip.title}</h3>
                  <p>{tip.text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ============ VIDEOS ============ */}
        <section className="ph-section">
          <div className="ph-container">
            <div className="ph-section-head">
              <h2>Tutorial videos</h2>
              <p>Watch and share these with your family.</p>
            </div>

            {activeVideo && (
              <div className="wt-videos">
                <div className="wt-player">
                  <div className="wt-player-frame">
                    <iframe
                      key={activeVideo.id}
                      src={`https://www.youtube-nocookie.com/embed/${activeVideo.id}`}
                      title={activeVideo.title}
                      allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                      loading="lazy"
                    />
                  </div>
                  <div className="wt-player-info">
                    <div>
                      <span className="wt-video-tag">{activeVideo.hazard}</span>
                      <h3>{activeVideo.title}</h3>
                    </div>
                    <a
                      className="wt-youtube-link"
                      href={`https://www.youtube.com/watch?v=${activeVideo.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Watch on YouTube
                    </a>
                  </div>
                </div>

                <ul className="wt-playlist" aria-label="More videos">
                  {sortedVideos.map((video) => (
                    <li key={video.id}>
                      <button
                        type="button"
                        className={`wt-playlist-item ${video.id === activeVideo.id ? 'is-active' : ''}`}
                        aria-current={video.id === activeVideo.id}
                        onClick={() => setVideoId(video.id)}
                      >
                        <img
                          src={`https://i.ytimg.com/vi/${video.id}/mqdefault.jpg`}
                          alt=""
                          loading="lazy"
                        />
                        <span>
                          <strong>{video.title}</strong>
                          <small>{video.hazard}</small>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>

        {/* ============ EMERGENCY STRIP ============ */}
        <section className="wt-emergency">
          <div className="ph-container wt-emergency-inner">
            <p>
              <strong>In an emergency, don't read. Call.</strong>
              <span>911 or the Talisay DRRMO at {DRRMO_HOTLINE.label}</span>
            </p>
            <div className="wt-emergency-actions">
              <a className="ph-btn wt-btn-white" href="tel:911">Call 911</a>
              <a className="ph-btn wt-btn-ghost" href={DRRMO_HOTLINE.tel}>Call DRRMO</a>
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