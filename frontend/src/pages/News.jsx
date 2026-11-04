import React, { useCallback, useEffect, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import NewsCard from '../components/News/NewsCard';
import AnnouncementForm from '../components/News/AnnouncementForm';
import { useAuth } from '../context/AuthContext';
import { newsApi } from '../api/newsApi';
import seal from '../assets/images/logo1.png';
import './css/News.css';

// Grey stand-ins for the first page while it loads
function Skeletons() {
  return (
    <div className="nw-list" aria-busy="true" aria-label="Loading the news">
      {[0, 1, 2].map((i) => (
        <div key={i} className="nw-card nw-skeleton" aria-hidden="true">
          <div className="nw-card-head">
            <span className="nw-skel nw-skel-avatar" />
            <span className="nw-skel-lines"><span className="nw-skel" /><span className="nw-skel nw-skel-short" /></span>
          </div>
          <span className="nw-skel nw-skel-title" />
          <span className="nw-skel" />
          <span className="nw-skel nw-skel-short" />
        </div>
      ))}
    </div>
  );
}

/**
 * The public newsfeed: what DRRMO and BFP announced and the hazard alerts
 * that went out, newest first, ten at a time (backend apps/news). Anyone can
 * read it; DRRMO, admins and BFP post here, and edit or delete the posts the
 * server marks can_edit.
 */
export default function News() {
  const { canPostNews } = useAuth() || {};
  const [posts, setPosts] = useState(null); // null while the first page loads
  const [nextBefore, setNextBefore] = useState(null);
  const [failed, setFailed] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [editing, setEditing] = useState(null); // 'new', a post, or null
  const [confirming, setConfirming] = useState(null); // the post to delete
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    setPosts(null);
    newsApi.feed({})
      .then((page) => { setPosts(page.results); setNextBefore(page.next_before); })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Escape closes the delete dialog, unless the delete is under way
  useEffect(() => {
    if (!confirming) return undefined;
    const onKey = (e) => { if (e.key === 'Escape' && !deleting) setConfirming(null); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [confirming, deleting]);

  async function loadMore() {
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const page = await newsApi.feed({ before: nextBefore });
      setPosts((shown) => [...shown, ...page.results]);
      setNextBefore(page.next_before);
    } catch {
      setMoreFailed(true);
    } finally {
      setLoadingMore(false);
    }
  }

  function saved(post) {
    // The first page may have failed or still be loading: the new post shows anyway
    setPosts((shown) => (editing === 'new'
      ? [post, ...(shown || [])]
      : (shown || []).map((p) => (p.kind === post.kind && p.id === post.id ? post : p))));
    setFailed(false);
    setEditing(null);
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await newsApi.remove(confirming.id);
      setPosts((shown) => shown.filter((p) => !(p.kind === 'announcement' && p.id === confirming.id)));
      setConfirming(null);
    } catch {
      // The post stays; the dialog stays open to try again
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="nw-page">
      <PublicNavbar />
      <main className="nw-wrap">
        <header className="nw-header">
          <img className="nw-header-seal" src={seal} alt="" />
          <div className="nw-header-text">
            <p className="nw-eyebrow">Talisay City, Cebu</p>
            <h1>News &amp; Advisories</h1>
            <p>Official updates from Talisay City DRRMO and BFP, and every hazard alert GeoAlert sent.</p>
          </div>
          {canPostNews && (
            <button type="button" className="nw-btn nw-btn-primary" onClick={() => setEditing('new')}>
              New announcement
            </button>
          )}
        </header>

        {failed ? (
          <div className="nw-empty" role="alert">
            <p>Couldn&apos;t load the news.</p>
            <button type="button" className="nw-btn nw-btn-ghost" onClick={load}>Try again</button>
          </div>
        ) : posts === null ? (
          <Skeletons />
        ) : posts.length === 0 ? (
          <div className="nw-empty">
            <p className="nw-empty-title">No news yet</p>
            <p>Announcements and hazard alerts will appear here as they are posted.</p>
          </div>
        ) : (
          <div className="nw-list">
            {posts.map((post) => (
              <NewsCard key={`${post.kind}-${post.id}`} post={post} onEdit={setEditing} onDelete={setConfirming} />
            ))}
          </div>
        )}

        {posts && nextBefore && (
          <div className="nw-more">
            {moreFailed && <p className="nw-error" role="alert">Couldn&apos;t load more. Try again.</p>}
            <button type="button" className="nw-btn nw-btn-ghost" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
          </div>
        )}
      </main>

      {editing && (
        <AnnouncementForm post={editing === 'new' ? null : editing} onSaved={saved} onClose={() => setEditing(null)} />
      )}
      {confirming && (
        <div className="nw-backdrop">
          <div className="nw-dialog" role="alertdialog" aria-modal="true" aria-labelledby="nw-delete-title">
            <h2 id="nw-delete-title">Delete this announcement?</h2>
            <p>&ldquo;{confirming.title}&rdquo; is removed from the news for everyone. This can&apos;t be undone.</p>
            <div className="nw-dialog-actions">
              <button type="button" className="nw-btn nw-btn-ghost" onClick={() => setConfirming(null)} disabled={deleting} autoFocus>
                Cancel
              </button>
              <button type="button" className="nw-btn nw-btn-danger-solid" onClick={confirmDelete} disabled={deleting}>
                {deleting ? 'Deleting…' : 'Delete post'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
