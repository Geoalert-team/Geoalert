import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { hazardIconPath } from '../components/Map/hazardInfo';
import { GUIDES, PHASES, UNIVERSAL_TIPS, VIDEOS } from '../data/safetyGuides';
import { hazardsApi } from '../api/hazardsApi';
import { guidanceApi } from '../api/guidanceApi';
import { useAuth } from '../context/AuthContext';
import GuidanceEditor from '../components/Guidance/GuidanceEditor';
import { guidanceError, stepsFrom } from '../utils/guidance';
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

// Every word of the search must appear (any order, any case)
const wordsOf = (q) => q.toLowerCase().split(/\s+/).filter(Boolean);
const matchesAll = (text, words) => {
  const t = (text || '').toLowerCase();
  return words.every((w) => t.includes(w));
};

// Search the built-in general safety steps, one hit per matching step
function searchStaticGuides(q) {
  const words = wordsOf(q);
  if (!words.length) return [];
  const hits = [];
  HAZARDS.forEach((name) => {
    PHASES.forEach((p) => {
      (GUIDES[name].phases[p.key] || []).forEach((step) => {
        if (matchesAll(`${name} ${p.title} ${step}`, words)) hits.push({ hazard: name, phase: p, step });
      });
    });
  });
  return hits;
}

export default function WhatToDo() {
  // The hazard and phase live in the URL, not in state. That's what makes
  // "open in a new tab" keep the reader's place, and what lets the map's
  // "Full safety guide" button land on the right hazard.
  const [searchParams, setSearchParams] = useSearchParams();

  const hazardParam = searchParams.get('hazard') || '';
  const phaseParam = searchParams.get('phase') || '';
  const hazard = HAZARDS.find((h) => h.toLowerCase() === hazardParam.toLowerCase()) || DEFAULT_HAZARD;
  const phase = PHASES.some((p) => p.key === phaseParam) ? phaseParam : DEFAULT_PHASE;
  // Keyword search (?q=): kept in the URL like the other filters
  const qParam = (searchParams.get('q') || '').trim();
  const [query, setQuery] = useState(qParam);
  const filtersActive = searchParams.has('hazard') || searchParams.has('phase') || Boolean(qParam);

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
    setQuery('');
    setSearchParams({}, { replace: true });
  }

  // Typing updates the URL after a short pause, so each keystroke is not a request
  useEffect(() => {
    const t = setTimeout(() => {
      const next = query.trim();
      if (next === qParam) return;
      const params = new URLSearchParams(searchParams);
      if (next) params.set('q', next); else params.delete('q');
      setSearchParams(params, { replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [query]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the box in step when the URL changes (back button, Clear filters)
  useEffect(() => { setQuery(qParam); }, [qParam]);

  // Published articles matching the search, across every hazard and phase
  const [searchHits, setSearchHits] = useState(null);
  const [searching, setSearching] = useState(false);
  useEffect(() => {
    if (!qParam) { setSearchHits(null); return undefined; }
    let cancelled = false;
    setSearching(true);
    guidanceApi.list({ search: qParam })
      .then((data) => { if (!cancelled) setSearchHits(Array.isArray(data) ? data : data?.results || []); })
      .catch(() => { if (!cancelled) setSearchHits([]); })
      .finally(() => { if (!cancelled) setSearching(false); });
    return () => { cancelled = true; };
  }, [qParam]);
  const staticHits = useMemo(() => searchStaticGuides(qParam), [qParam]);

  // Open a result: drop the search and go to that hazard and phase
  function openResult(hazardName, phaseKey, hash = '') {
    setQuery('');
    setSearchParams({ hazard: hazardName, phase: phaseKey }, { replace: false });
    if (hash) setTimeout(() => document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth' }), 400);
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

  // DRRMO Officers and Admins edit the published guidance right here: an
  // article id being edited, 'new' for the Add form, or null
  const { canPublish } = useAuth();
  const [editingId, setEditingId] = useState(null);
  const [actionError, setActionError] = useState('');

  // A form left open belongs to the hazard and phase it was opened for
  useEffect(() => {
    setEditingId(null);
    setActionError('');
  }, [hazard, phase]);

  function startEditing(id) {
    setActionError('');
    setEditingId(id);
  }

  function afterSave() {
    setEditingId(null);
    retry();
  }

  // Delete unpublishes: residents stop seeing it, the row stays in the database
  async function removeArticle(article) {
    if (!window.confirm('Remove this guidance? Residents will no longer see it.')) return;
    setActionError('');
    try {
      await guidanceApi.remove(article.id);
      setEditingId(null);
      retry();
    } catch (err) {
      setActionError(guidanceError(err));
    }
  }

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
  // Editing needs the live list (not the fallback shown when it failed to
  // load) and the hazard's id; First aid is fixed reference content
  const canEdit = canPublish && !isFirstAid && !loadingArticles && !loadError && Boolean(hazardTypeMap[hazard]);

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

              <label className="wt-search">
                <span className="wt-sr">Search the safety guides</span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M21 21l-5-5" /></svg>
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search guides, e.g. sandbag, LPG, evacuation"
                />
              </label>

              {filtersActive && (
                <button type="button" className="wt-reset" onClick={clearFilters}>
                  Clear filters
                </button>
              )}
            </div>

            {qParam ? (
              <div className="wt-results" aria-live="polite">
                <h2>Results for &ldquo;{qParam}&rdquo;</h2>
                {searching && <p className="wt-muted">Searching…</p>}

                {!searching && searchHits && searchHits.length > 0 && (
                  <>
                    <h3>Published by the Talisay City DRRMO</h3>
                    <ul className="wt-result-list">
                      {searchHits.map((a) => {
                        const name = a.hazard_type_detail?.name || '';
                        const phaseKey = (a.timeline_phase || '').toLowerCase();
                        return (
                          <li key={a.id}>
                            <button type="button" onClick={() => openResult(HAZARDS.find((h) => h === name) || DEFAULT_HAZARD, phaseKey, `article-${a.id}`)}>
                              <strong>{a.title}</strong>
                              <small>{name} · {a.timeline_phase}</small>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                )}

                {staticHits.length > 0 && (
                  <>
                    <h3>General safety steps</h3>
                    <ul className="wt-result-list">
                      {staticHits.map((h) => (
                        <li key={`${h.hazard}-${h.phase.key}-${h.step}`}>
                          <button type="button" onClick={() => openResult(h.hazard, h.phase.key)}>
                            <strong>{h.step}</strong>
                            <small>{h.hazard} · {h.phase.title}</small>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                )}

                {!searching && searchHits && searchHits.length === 0 && staticHits.length === 0 && (
                  <p className="wt-notice">
                    No guidance matches &ldquo;{qParam}&rdquo;. Try a different word, or clear the search to
                    browse by hazard.
                  </p>
                )}
                <p className="wt-source-note">
                  Searches the DRRMO&apos;s published guidance and the general safety steps on this page.
                </p>
              </div>
            ) : (
            <>
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
                <div className="wt-steps-head">
                  <h3>
                    {isFirstAid
                      ? `First aid for ${hazard.toLowerCase()} injuries`
                      : `${currentPhase.title} a ${hazard.toLowerCase()}`}
                  </h3>
                  {/* One form at a time, so switching never throws away unsaved edits */}
                  {canEdit && editingId === null && (
                    <button type="button" className="wt-edit-btn" onClick={() => startEditing('new')}>
                      Add guidance
                    </button>
                  )}
                </div>

                {actionError && <p className="wt-action-error" role="alert">{actionError}</p>}

                {canEdit && editingId === 'new' && (
                  <GuidanceEditor
                    hazardTypeId={hazardTypeMap[hazard]}
                    phase={PHASE_TO_API[phase]}
                    onSaved={afterSave}
                    onCancel={() => setEditingId(null)}
                  />
                )}

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
                        {canEdit && editingId === article.id ? (
                          <GuidanceEditor article={article} onSaved={afterSave} onCancel={() => setEditingId(null)} />
                        ) : (
                          <>
                            <div className="wt-article-head">
                              <div>
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
                              {canEdit && editingId === null && (
                                <div className="wt-article-tools">
                                  <button
                                    type="button"
                                    className="wt-edit-btn"
                                    aria-label={`Edit "${article.title}"`}
                                    onClick={() => startEditing(article.id)}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    type="button"
                                    className="wt-edit-btn wt-edit-btn-danger"
                                    aria-label={`Delete "${article.title}"`}
                                    onClick={() => removeArticle(article)}
                                  >
                                    Delete
                                  </button>
                                </div>
                              )}
                            </div>
                            <ol className="wt-steps">
                              {stepsFrom(article.body).map((step, i) => (
                                <li key={`${i}-${step}`}>{step}</li>
                              ))}
                            </ol>
                          </>
                        )}
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
            </>
            )}
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
      </main>

      {/* ============ FOOTER ============ */}
      <footer className="ph-footer">
        <div className="ph-container ph-footer-inner">
          <div className="ph-footer-brand">
            <span className="ph-footer-logo">
              <img src={logo} alt="" />
            </span>
            <div>
              <p className="ph-footer-name">GeoAlert Talisay</p>
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
        <p className="ph-container ph-footer-copy">&copy; {new Date().getFullYear()} GeoAlert Talisay</p>
      </footer>
    </div>
  );
}