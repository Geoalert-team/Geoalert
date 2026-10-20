/**
 * '#1c2e4a', 0.14 -> 'rgba(28,46,74,0.14)'. Three-digit hex works too.
 * For canvas fills, which cannot read CSS custom properties or 8-digit hex
 * reliably across browsers.
 */
export function withAlpha(hex, alpha) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return `rgba(${r},${g},${b},${alpha})`;
}
