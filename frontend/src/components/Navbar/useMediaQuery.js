import { useEffect, useState } from 'react';

/**
 * Whether a CSS media query matches, kept up to date as the window resizes.
 * False where matchMedia is missing (tests, very old browsers), which means
 * the wide layout.
 */
export default function useMediaQuery(query) {
  const read = () => (typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia(query).matches
    : false);
  const [matches, setMatches] = useState(read);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange(); // the query may have changed since the first render
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}
