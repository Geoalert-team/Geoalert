// Where the public map puts a hazard's pins. A fire made from reports comes
// with `pins`: one per purok its reports name, and it is shown by those pins
// alone, with no shading or outline (its zone is only a few small circles,
// used to work out who to alert). A zone an officer drew keeps one pin at its
// middle, and its shading and outline.

export function markerSpots(item) {
  const pins = item.pins || [];
  if (!pins.length) return [{ key: item.id, position: item.position, purok: null }];
  return pins.map((p, i) => ({ key: `${item.id}:${i}`, position: [p.lat, p.lng], purok: p.purok_name ?? null }));
}

export function drawsShading(item) {
  return !(item.pins && item.pins.length);
}
