import { useEffect } from 'react';

/**
 * Opens every closed <details> inside `ref` while the page prints, and closes
 * them again after. A printed or PDF copy has nobody to press "Show the
 * numbers", and Chrome will not render a closed <details> body whatever the
 * print stylesheet says, so CSS alone cannot do this.
 */
export default function usePrintOpensDetails(ref) {
  useEffect(() => {
    let opened = [];
    function before() {
      opened = [...(ref.current?.querySelectorAll('details:not([open])') || [])];
      opened.forEach((d) => { d.open = true; });
    }
    function after() {
      opened.forEach((d) => { d.open = false; });
      opened = [];
    }
    window.addEventListener('beforeprint', before);
    window.addEventListener('afterprint', after);
    return () => {
      window.removeEventListener('beforeprint', before);
      window.removeEventListener('afterprint', after);
    };
  }, [ref]);
}
