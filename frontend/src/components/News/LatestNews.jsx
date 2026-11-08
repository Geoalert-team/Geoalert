import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import NewsCard from './NewsCard';
import { newsApi } from '../../api/newsApi';
import '../../pages/css/News.css';

/**
 * The home page's "Latest updates": the three newest newsfeed posts and a link
 * to the News page. Nothing at all while loading, on a failed load or with no
 * posts: the home page reads the same without it. Uses the home page's ph-
 * section classes, and nw- for the cards.
 */
export default function LatestNews() {
  const [posts, setPosts] = useState(null);

  useEffect(() => {
    let cancelled = false;
    newsApi.feed({ limit: 3 })
      .then((page) => { if (!cancelled) setPosts(page.results); })
      .catch(() => { if (!cancelled) setPosts([]); });
    return () => { cancelled = true; };
  }, []);

  if (!posts?.length) return null;

  return (
    <section className="ph-section nw-latest" aria-labelledby="nw-latest-title">
      <div className="ph-container">
        <div className="ph-section-head">
          <h2 id="nw-latest-title">Latest updates</h2>
          <p>What DRRMO and BFP announced, and the hazard alerts that went out.</p>
        </div>
        <div className="nw-list nw-latest-list">
          {posts.map((post) => <NewsCard key={`${post.kind}-${post.id}`} post={post} />)}
        </div>
        <div className="ph-center nw-latest-more">
          <Link className="ph-btn ph-btn-outline" to="/news">See all news</Link>
        </div>
      </div>
    </section>
  );
}
