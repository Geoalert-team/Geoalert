import React, { useCallback, useEffect, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import NewsCard from '../components/News/NewsCard';
import AnnouncementForm from '../components/News/AnnouncementForm';
import { useAuth } from '../context/AuthContext';
import { newsApi } from '../api/newsApi';
import './css/News.css';

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
    setPosts((shown) => (editing === 'new'
      ? [post, ...shown]
      : shown.map((p) => (p.kind === post.kind && p.id === post.id ? post : p))));
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
          <div>
            <h1>News</h1>
            <p>Announcements from DRRMO and BFP, and the hazard alerts that went out in Talisay City.</p>
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
          <p className="nw-empty">Loading the news…</p>
        ) : posts.length === 0 ? (
          <p className="nw-empty">No news yet.</p>
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
              <button type="button" className="nw-btn nw-btn-ghost" onClick={() => setConfirming(null)} disabled={deleting}>
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
