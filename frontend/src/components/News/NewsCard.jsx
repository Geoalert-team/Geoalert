import React, { useState } from 'react';
import seal from '../../assets/images/logo1.png';
import { hazardIconPath } from '../Map/hazardInfo';
import { timeAgo } from '../../utils/timeAgo';

/**
 * One post of the newsfeed, laid out like an official page's post: the
 * office's logo and name, an Official mark, when, then the post: an
 * announcement DRRMO or BFP wrote (backend apps/news/feed.py). Text is
 * rendered as text, never HTML; line breaks are kept by CSS
 * (white-space: pre-line).
 *
 *   post               a feed item ({ kind: 'announcement', ... })
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

// Text longer than this folds behind "See more"
const FOLD_LINES = 5;
const FOLD_CHARS = 320;

export function postDate(iso) {
  return new Date(iso).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

function Icon({ path }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={path} /></svg>;
}

// The office's round logo
function Avatar({ office }) {
  if (!office.logo) {
    return <span className="nw-avatar is-bfp" aria-hidden="true"><Icon path={hazardIconPath('Fire')} /></span>;
  }
  return (
    <span className="nw-avatar">
      <img src={office.logo} alt="" />
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

export default function NewsCard({ post, onEdit, onDelete }) {
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
