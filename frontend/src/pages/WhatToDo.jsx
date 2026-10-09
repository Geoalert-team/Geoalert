import React, { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { hazardIconPath, DRRMO_HOTLINE } from '../components/Map/hazardInfo';
import { GUIDES, PHASES, UNIVERSAL_TIPS, VIDEOS } from '../data/safetyGuides';
import { hazardsApi } from '../api/hazardsApi';
import { guidanceApi } from '../api/guidanceApi';
import logo from '../assets/images/logo1.png';
import './css/PublicHome.css';
import './css/WhatToDo.css';

const HAZARDS = Object.keys(GUIDES); // ['Flood', 'Landslide', 'Fire']

const TIP_ICONS = {
  connected: 'M5 3h14v18H5z M9 18h6',
  routes: 'M4 19c4 0 4-7 8-7s4 7 8 7 M12 5v3 M9 8h6',
  family: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M2 20c0-3 3-5 6-5s6 2 6 5 M14 15c3 0 8 1 8 5',
  kit: 'M4 8h16v12H4z M9 8V5h6v3 M12 11v6 M9 14h6',
};

// timeline_phase values expected by the backend (Before/During/After only).
// First aid is not a backend phase, so it stays static.
const PHASE_TO_API = { before: 'Before', during: 'During', after: 'After' };

const DEFAULT_HAZARD = HAZARDS[0];
const DEFAULT_PHASE = 'before';

// One line of an article body = one numbered step
const stepsFrom = (body = '') => body.split('\n').map((s) => s.trim()).filter(Boolean);

export default function WhatToDo() {
  // The hazard and phase live in the URL, not in state. That's what makes
  // "open in a new tab" keep the reader's place, and what lets the map's
  // "Full safety guide" button land on the right hazard.
  const [searchParams, setSearchParams] = useSearchParams();

  const hazardParam = searchParams.get('hazard') || '';
  const phaseParam = searchParams.get('phase') || '';
  const hazard = HAZARDS.find((h) => h.toLowerCase() === hazardParam.toLowerCase()) || DEFAULT_HAZARD;
  const phase = PHASES.some((p) => p.key === phaseParam) ? phaseParam : DEFAULT_PHASE;
  const filtersActive = searchParams.has('hazard') || searchParams.has('phase');

  const [packed, setPacked] = useState({});
  const [videoId, setVideoId] = useState(VIDEOS[0]?.id);

  const [hazardTypeMap, setHazardTypeMap] = useState({}); // { Flood: 1, ... }
  const [liveArticles, setLiveArticles] = useState([]);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  const guide = GUIDES[hazard];
  const currentPhase = PHASES.find((p) => p.key === phase) || PHASES[0];

  function applyFilters(next) {
    const params = new URLSearchParams(searchParams);
    if (next.hazard) params.set('hazard', next.hazard);
    if (next.phase) params.set('phase', next.phase);
    setSearchParams(params);
  }

  function clearFilters() {
    setSearchParams({}, { replace: true });
  }

  // Load real hazard type IDs once, so guidance can be filtered by hazard_type
  useEffect(() => {
    hazardsApi
      .types()
      .then((types) => {
        const list = Array.isArray(types) ? types : types?.results || [];
        const map = {};
        list.forEach((t) => { map[t.name] = t.id; });
        setHazardTypeMap(map);
      })
      .catch(() => setHazardTypeMap({}));
  }, []);

  // Fetch published guidance whenever the hazard or phase changes
  useEffect(() => {
    if (phase === 'firstaid') {
      setLiveArticles([]);
      setLoadError('');
      return undefined;
    }
    const hazardTypeId = hazardTypeMap[hazard];
    if (!hazardTypeId) return undefined;

    let cancelled = false;
    setLoadingArticles(true);
    setLoadError('');

    guidanceApi
      .list({ hazard_type: hazardTypeId, phase: PHASE_TO_API[phase] })
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : data?.results || [];
        setLiveArticles([...list].sort((a, b) => new Date(a.created_at) - new Date(b.created_at)));
      })
      .catch(() => {
        if (cancelled) return;
        setLiveArticles([]);
        setLoadError('Guidance could not be loaded right now.');
      })
      .finally(() => { if (!cancelled) setLoadingArticles(false); });

    return () => { cancelled = true; };
  }, [hazard, phase, hazardTypeMap, reloadKey]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  const sortedVideos = [...VIDEOS].sort(
    (a, b) => Number(b.hazard === hazard) - Number(a.hazard === hazard),
  );
  const activeVideo = VIDEOS.find((v) => v.id === videoId) || VIDEOS[0];

  const packedCount = guide.supplies.filter((item) => packed[`${hazard}:${item}`]).length;

  function chooseHazard(name) {
    applyFilters({ hazard: name, phase: DEFAULT_PHASE });
    const firstVideo = VIDEOS.find((v) => v.hazard === name);
    if (firstVideo) setVideoId(firstVideo.id);
  }

  function toggleSupply(item) {
    const key = `${hazard}:${item}`;
    setPacked((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  // A link to this exact article, so right-click → open in a new tab keeps
  // the hazard and phase the reader was looking at.
  const articleHref = (article) =>
    `/what-to-do?hazard=${encodeURIComponent(hazard)}&phase=${phase}#article-${article.id}`;

  const hasPublished = liveArticles.length > 0;
  const isFirstAid = currentPhase.key === 'firstaid';

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
            <div className="wt-filter-bar">
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
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d={hazardIconPath(name)} />
                    </svg>
                    {name}
                  </button>
                ))}
              </div>

              {filtersActive && (
                <button type="button" className="wt-reset" onClick={clearFilters}>
                  Clear filters
                </button>
              )}
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
                  onClick={() => applyFilters({ hazard, phase: p.key })}
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
              <div className="wt-steps-card" role="tabpanel">
                <h3>
                  {isFirstAid
                    ? `First aid for ${hazard.toLowerCase()} injuries`
                    : `${currentPhase.title} a ${hazard.toLowerCase()}`}
                </h3>

                {isFirstAid ? (
                  /* First aid is always the static reference content */
                  <ol className="wt-steps">
                    {guide.phases.firstaid.map((step) => <li key={step}>{step}</li>)}
                  </ol>
                ) : loadingArticles ? (
                  <p className="wt-muted">Loading guidance…</p>
                ) : loadError ? (
                  <>
                    <div className="wt-error" role="alert">
                      <p>{loadError}</p>
                      <button type="button" className="wt-retry" onClick={retry}>Try again</button>
                    </div>
                    <p className="wt-source-note">
                      Showing general safety steps in the meantime. These are standard advice, not
                      the Talisay City DRRMO's published guidance.
                    </p>
                    <ol className="wt-steps">
                      {guide.phases[phase].map((step) => <li key={step}>{step}</li>)}
                    </ol>
                  </>
                ) : hasPublished ? (
                  /* Published guidance, one card per article so its title shows */
                  <div className="wt-articles">
                    {liveArticles.map((article) => (
                      <article key={article.id} id={`article-${article.id}`} className="wt-article">
                        <div className="wt-article-head">
                          <h4>
                            <a href={articleHref(article)}>{article.title}</a>
                          </h4>
                          <p className="wt-article-meta">
                            {article.hazard_type_detail?.name || hazard} · {article.timeline_phase}
                            {article.updated_at && (
                              <> · updated {new Date(article.updated_at).toLocaleDateString('en-PH', {
                                year: 'numeric', month: 'long', day: 'numeric',
                              })}</>
                            )}
                          </p>
                        </div>
                        <ol className="wt-steps">
                          {stepsFrom(article.body).map((step, i) => (
                            <li key={`${i}-${step}`}>{step}</li>
                          ))}
                        </ol>
                      </article>
                    ))}
                  </div>
                ) : (
                  <>
                    <p className="wt-notice">
                      No guidance content available for selected criteria. Please try different
                      filters.
                    </p>
                    <p className="wt-source-note">
                      General safety steps for a {hazard.toLowerCase()}, shown until the DRRMO
                      publishes guidance for this phase.
                    </p>
                    <ol className="wt-steps">
                      {guide.phases[phase].map((step) => <li key={step}>{step}</li>)}
                    </ol>
                  </>
                )}
              </div>

              {/* Go-bag checklist (static) */}
              <aside className="wt-supplies-card">
                <div className="wt-supplies-head">
                  <h3>Go-bag checklist</h3>
                  <span className="wt-supplies-count">
                    {packedCount} of {guide.supplies.length} packed
                  </span>
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
                    <svg viewBox="0 0 24 24">
                      <path d={TIP_ICONS[tip.key]} />
                    </svg>
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
                    <a className="wt-youtube-link" href={`https://www.youtube.com/watch?v=${activeVideo.id}`} target="_blank" rel="noopener noreferrer">
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