import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import seal from '../../assets/images/logo1.png';
import { hazardColor, hazardIconPath, severityInfo } from '../Map/hazardInfo';
import { timeAgo } from '../../utils/timeAgo';

/**
 * One post of the newsfeed, laid out like an official page's post: the
 * office's logo and name, an Official mark, when, then the post. Either an
 * announcement DRRMO or BFP wrote, or a hazard alert that went out (backend
 * apps/news/feed.py). Text is rendered as text, never HTML; line breaks are
 * kept by CSS (white-space: pre-line).
 *
 *   post               a feed item ({ kind: 'announcement' | 'alert', ... })
 *   onEdit, onDelete   shown, as buttons, only when post.can_edit
 *
 * Styled with nw- classes from pages/css/News.css.
 */

// Who a post is from, as residents know them
const OFFICES = {
  DRRMO: { name: 'Talisay City DRRMO', logo: seal },
  // The project has no BFP logo yet, so a flame emblem stands in (logo: null).
  // To use the official one: import its file above and set it here.
  BFP: { name: 'BFP Talisay City', logo: null },
};
const SYSTEM = { name: 'GeoAlert Talisay', logo: seal };

// Text longer than this folds behind "See more"
const FOLD_LINES = 5;
const FOLD_CHARS = 320;

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

function Icon({ path }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={path} /></svg>;
}

// The office's round logo; an alert's carries its hazard's badge in the corner
function Avatar({ office, hazard }) {
  if (!office.logo) {
    return <span className="nw-avatar is-bfp" aria-hidden="true"><Icon path={hazardIconPath('Fire')} /></span>;
  }
  return (
    <span className="nw-avatar">
      <img src={office.logo} alt="" />
      {hazard !== undefined && (
        <span className="nw-avatar-badge" style={{ background: hazardColor(hazard || '') }} aria-hidden="true">
          <Icon path={hazardIconPath(hazard || '')} />
        </span>
      )}
    </span>
  );
}

function Byline({ office, post, kind, edited }) {
  return (
    <div className="nw-byline">
      <span className="nw-office-line">
        <span className="nw-office">{office.name}</span>
        <span className="nw-official" title="An official GeoAlert Talisay account">
          <Icon path="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z" />
          Official
        </span>
      </span>
      <span className="nw-meta">
        <time dateTime={post.published_at} title={postDate(post.published_at)}>{timeAgo(post.published_at)}</time>
        {` · ${kind}`}{edited ? ' · Edited' : ''}
      </span>
    </div>
  );
}

function AlertCard({ post }) {
  const active = post.status === 'active';
  return (
    <article className="nw-card nw-card-alert" style={{ '--nw-hazard': hazardColor(post.hazard_type || '') }}>
      <header className="nw-card-head">
        <Avatar office={SYSTEM} hazard={post.hazard_type} />
        <Byline office={SYSTEM} post={post} kind={`${post.hazard_type || 'Hazard'} alert`} />
        <span className={`nw-status ${active ? 'is-active' : 'is-resolved'}`}>{active ? 'Active' : 'Resolved'}</span>
      </header>
      <h3>{alertTitle(post)}</h3>
      {post.map_link && (
        <Link className="nw-map-link" to={post.map_link}>View on map <span aria-hidden="true">→</span></Link>
      )}
    </article>
  );
}

function AnnouncementCard({ post, onEdit, onDelete }) {
  const office = OFFICES[post.source] || OFFICES.DRRMO;
  const long = post.body.split('\n').length > FOLD_LINES || post.body.length > FOLD_CHARS;
  const [open, setOpen] = useState(false);
  return (
    <article className="nw-card nw-card-announcement">
      <header className="nw-card-head">
        <Avatar office={office} />
        <Byline office={office} post={post} kind="Announcement" edited={Boolean(post.edited_at)} />
        {post.can_edit && onEdit && onDelete && (
          <div className="nw-actions">
            <button type="button" className="nw-btn nw-btn-small" onClick={() => onEdit(post)}>Edit</button>
            <button type="button" className="nw-btn nw-btn-small nw-btn-danger" onClick={() => onDelete(post)}>Delete</button>
          </div>
        )}
      </header>
      <h3>{post.title}</h3>
      <p className={`nw-body${long && !open ? ' is-folded' : ''}`}>{post.body}</p>
      {long && (
        <button type="button" className="nw-see-more" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? 'See less' : 'See more'}
        </button>
      )}
      {post.photo_url && <img className="nw-photo" src={post.photo_url} alt={post.title} loading="lazy" />}
    </article>
  );
}

export default function NewsCard({ post, onEdit, onDelete }) {
  return post.kind === 'alert'
    ? <AlertCard post={post} />
    : <AnnouncementCard post={post} onEdit={onEdit} onDelete={onDelete} />;
}
