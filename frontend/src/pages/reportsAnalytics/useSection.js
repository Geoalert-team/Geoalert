import { useEffect, useRef, useState } from 'react';

const NO_PERMISSION = 'You do not have permission to view these figures.';
const FAILED = 'These figures could not be loaded right now. Please try again later.';

/** The sentence to show for a failed load: the server's own for a refused filter. */
export function loadError(err) {
  if (err?.status === 403) return NO_PERMISSION;
  if (err?.status === 400 && err?.data?.error) return err.data.error;
  return FAILED;
}

/**
 * Loads `load(params)` while `active`, once per distinct params: switching
 * back to a section, or re-applying the same filters, asks for nothing new
 * (and writes no new audit row). params null means "do not load" (a filter
 * the page has already refused). A slower, older answer never replaces a
 * newer one, and a load cut short by leaving the section is retried on
 * return.
 * -> { status: 'idle' | 'loading' | 'ready' | 'error', data, error }
 */
export default function useSection(load, params, active = true) {
  const key = params === null ? null : JSON.stringify(params);
  const loaded = useRef(null);
  const [state, setState] = useState({ status: 'idle', data: null, error: '' });

  useEffect(() => {
    if (!active || key === null || loaded.current === key) return undefined;
    loaded.current = key;
    let live = true;
    let done = false;
    setState((s) => ({ ...s, status: 'loading', error: '' }));
    load(params)
      .then((data) => { done = true; if (live) setState({ status: 'ready', data, error: '' }); })
      .catch((err) => {
        done = true;
        if (!live) return;
        loaded.current = null; // try again next time
        setState({ status: 'error', data: null, error: loadError(err) });
      });
    return () => {
      live = false;
      if (!done) loaded.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, key]);

  return state;
}
