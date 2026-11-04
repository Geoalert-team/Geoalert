import React from 'react';
import { Link } from 'react-router-dom';
import { hazardColor, hazardIconPath, severityInfo } from '../Map/hazardInfo';

/**
 * One post of the newsfeed: an announcement DRRMO or BFP wrote, or a hazard
 * alert that went out (backend apps/news/feed.py). Text is rendered as text,
 * never HTML; line breaks are kept by CSS (white-space: pre-line).
 *
 *   post               a feed item ({ kind: 'announcement' | 'alert', ... })
 *   onEdit, onDelete   shown, as buttons, only when post.can_edit
 *
 * Styled with nw- classes from pages/css/News.css.
 */

export function postDate(iso) {
  return new Date(iso).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

// "Fire alert (Moderate) for Mohon · Purok Santol"
export function alertTitle(post) {
  const level = severityInfo(post.severity).label.replace(/ risk$/, '');
  const where = post.barangay || 'Talisay City';
  const puroks = post.puroks?.length ? ` · ${post.puroks.join(', ')}` : '';
  return `${post.hazard_type || 'Hazard'} alert (${level}) for ${where}${puroks}`;
}

function AlertCard({ post }) {
  const active = post.status === 'active';
  return (
    <article className="nw-card nw-card-alert" style={{ '--nw-hazard': hazardColor(post.hazard_type || '') }}>
      <header className="nw-card-head">
        <span className="nw-hazard-icon" aria-hidden="true">
          {/* hazard_type is null when its type was deleted */}
          <svg viewBox="0 0 24 24"><path d={hazardIconPath(post.hazard_type || '')} /></svg>
        </span>
        <span className={`nw-status ${active ? 'is-active' : 'is-resolved'}`}>{active ? 'Active' : 'Resolved'}</span>
        <time dateTime={post.published_at}>{postDate(post.published_at)}</time>
      </header>
      <h3>{alertTitle(post)}</h3>
      {post.map_link && <Link className="nw-map-link" to={post.map_link}>View on map</Link>}
    </article>
  );
}

function AnnouncementCard({ post, onEdit, onDelete }) {
  return (
    <article className="nw-card nw-card-announcement">
      <header className="nw-card-head">
        <span className={`nw-source is-${post.source.toLowerCase()}`}>{post.source}</span>
        <time dateTime={post.published_at}>
          {postDate(post.published_at)}{post.edited_at ? ' · edited' : ''}
        </time>
      </header>
      <h3>{post.title}</h3>
      {post.photo_url && <img className="nw-photo" src={post.photo_url} alt={post.title} loading="lazy" />}
      <p className="nw-body">{post.body}</p>
      {post.can_edit && onEdit && onDelete && (
        <div className="nw-actions">
          <button type="button" className="nw-btn nw-btn-ghost" onClick={() => onEdit(post)}>Edit</button>
          <button type="button" className="nw-btn nw-btn-ghost nw-btn-danger" onClick={() => onDelete(post)}>Delete</button>
        </div>
      )}
    </article>
  );
}

export default function NewsCard({ post, onEdit, onDelete }) {
  return post.kind === 'alert'
    ? <AlertCard post={post} />
    : <AnnouncementCard post={post} onEdit={onEdit} onDelete={onDelete} />;
}
