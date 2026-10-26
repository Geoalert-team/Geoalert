// Reading the susceptibility rasters back in the browser.
//
// The public map no longer shades hazard levels itself: past hazards colour
// whole puroks (purokLevels.js) and active hazards are pins. What is left
// here is the one thing other parts still need, loadClassGrid, which turns a
// susceptibility PNG (public/hazard-index/, built offline) back into class
// numbers. SpotReading uses it for the panel's "This spot" reading and
// utils/zoneCheck.js for the publish panel's checks.

const BASE = `${process.env.PUBLIC_URL || ''}/hazard-index`;

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

// Reads one susceptibility PNG back into class numbers (0 = outside the city, 1..5)
export async function loadClassGrid(index, layer) {
  const img = await loadImage(`${BASE}/${index.layers[layer]}?v=${encodeURIComponent(index.generated || '')}`);
  const canvas = document.createElement('canvas');
  canvas.width = img.width;
  canvas.height = img.height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0);
  const { data } = ctx.getImageData(0, 0, img.width, img.height);

  const lookup = new Map(index.classes.map((c, i) => {
    const [r, g, b] = hexToRgb(c.color);
    return [(r << 16) | (g << 8) | b, i + 1];
  }));
  const cls = new Uint8Array(img.width * img.height);
  for (let i = 0, p = 0; i < cls.length; i += 1, p += 4) {
    if (data[p + 3] > 0) cls[i] = lookup.get((data[p] << 16) | (data[p + 1] << 8) | data[p + 2]) || 0;
  }
  return { width: img.width, height: img.height, cls };
}
