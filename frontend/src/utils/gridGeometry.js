/**
 * Geometry on the hazard-index raster grid (Web Mercator, north up): where a
 * [lat, lng] falls among the raster's cells, and back.
 */

const mercY = (lat) => {
  const s = Math.sin((lat * Math.PI) / 180);
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
};

const latFromMercY = (y) => {
  const t = (0.5 - y) * 4 * Math.PI;
  return (Math.asin(Math.tanh(t / 2)) * 180) / Math.PI;
};

/**
 * Maps between [lat, lng] and fractional cell coordinates for a raster
 * covering `bounds` ([[south, west], [north, east]]) at width x height.
 */
export function makeGrid(bounds, width, height) {
  const [[south, west], [north, east]] = bounds;
  const y0 = mercY(north);
  const y1 = mercY(south);
  return {
    width,
    height,
    toCell: (lat, lng) => [((lng - west) / (east - west)) * width, ((mercY(lat) - y0) / (y1 - y0)) * height],
    toLatLng: (x, y) => [latFromMercY(y0 + (y / height) * (y1 - y0)), west + (x / width) * (east - west)],
  };
}
