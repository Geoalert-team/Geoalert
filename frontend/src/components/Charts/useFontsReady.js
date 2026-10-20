import { useEffect, useState } from 'react';

/**
 * True once the page's web fonts have loaded. Chart.js measures and draws
 * text when it mounts, so a chart drawn before Atkinson Hyperlegible arrives
 * keeps the fallback font until something redraws it; keying on this gives
 * it that redraw. True straight away where the Font Loading API is missing.
 */
export default function useFontsReady() {
  const fonts = typeof document !== 'undefined' ? document.fonts : undefined;
  const [ready, setReady] = useState(() => !fonts || fonts.status === 'loaded');

  useEffect(() => {
    if (ready || !fonts) return undefined;
    let live = true;
    fonts.ready.then(() => { if (live) setReady(true); });
    return () => { live = false; };
  }, [ready, fonts]);

  return ready;
}
