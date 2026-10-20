/**
 * Charts do not resize for print on their own: the print stylesheet changes
 * card widths, but Chart.js only hears about it after the browser has taken
 * its print snapshot, so a printed or PDF copy can show a line drawn for the
 * screen layout. The Chart.js docs' fix ("Printing Resizable Charts"):
 * resize every chart in beforeprint, and again in afterprint for the screen.
 *
 * Takes the Chart class (for Chart.instances) rather than importing it, so
 * the behaviour can be tested without loading Chart.js. Returns a remover.
 */
export function installPrintResize(Chart) {
  const resizeAll = () => Object.values(Chart.instances).forEach((chart) => chart.resize());
  window.addEventListener('beforeprint', resizeAll);
  window.addEventListener('afterprint', resizeAll);
  return () => {
    window.removeEventListener('beforeprint', resizeAll);
    window.removeEventListener('afterprint', resizeAll);
  };
}
