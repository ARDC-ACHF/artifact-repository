// Pure map helpers: grouping co-located markers and choosing a sensible initial view.

// Generous box around mainland Australia and Tasmania (excludes NZ and PNG highlands).
export const AUSTRALIA_BOUNDS = [[-44.5, 112], [-9.5, 154.5]];

export const SINGLE_POINT_ZOOM = 14;
export const MAX_FIT_ZOOM = 14;

function validPoint(p) {
  return p && Number.isFinite(p.lat) && Number.isFinite(p.lon);
}

export function isInAustralia(point) {
  if (!validPoint(point)) return false;
  const [[south, west], [north, east]] = AUSTRALIA_BOUNDS;
  return point.lat >= south && point.lat <= north && point.lon >= west && point.lon <= east;
}

/** Split points into Australian and overseas sets. */
export function splitByRegion(points) {
  const local = [];
  const overseas = [];
  for (const p of points || []) {
    if (!validPoint(p)) continue;
    (isInAustralia(p) ? local : overseas).push(p);
  }
  return { local, overseas };
}

/** Merge points at (practically) the same coordinates so one venue gets one marker. */
export function groupByLocation(points, precision = 4) {
  const groups = new Map();
  for (const p of points || []) {
    if (!validPoint(p)) continue;
    const key = `${p.lat.toFixed(precision)},${p.lon.toFixed(precision)}`;
    if (!groups.has(key)) groups.set(key, { key, lat: p.lat, lon: p.lon, items: [] });
    groups.get(key).items.push(p);
  }
  return [...groups.values()];
}

/**
 * Initial view for a set of points: `{ center, zoom }` for one location,
 * `{ bounds }` (south-west / north-east) for several, or null when there is nothing to show.
 */
export function viewFor(points) {
  const valid = (points || []).filter(validPoint);
  if (!valid.length) return null;
  const lats = valid.map((p) => p.lat);
  const lons = valid.map((p) => p.lon);
  const south = Math.min(...lats);
  const north = Math.max(...lats);
  const west = Math.min(...lons);
  const east = Math.max(...lons);
  if (north - south < 1e-4 && east - west < 1e-4) {
    return { center: [valid[0].lat, valid[0].lon], zoom: SINGLE_POINT_ZOOM };
  }
  return { bounds: [[south, west], [north, east]] };
}

/**
 * Flatten parsed search results `[{ summary, view }]` into map points, one per
 * record × place. A place reached both as the record itself and inline is only counted once.
 */
export function collectResultPoints(entries) {
  const points = [];
  for (const { summary, view } of entries || []) {
    if (!summary || !view) continue;
    const seen = new Set();
    for (const place of view.places || []) {
      if (!Number.isFinite(place.lat) || !Number.isFinite(place.lon)) continue;
      const key = `${place.lat},${place.lon},${place.role}`;
      if (seen.has(key)) continue;
      seen.add(key);
      points.push({
        lat: place.lat,
        lon: place.lon,
        role: place.role,
        place: { id: place.id, label: place.label },
        record: { id: summary.id, label: summary.label || view.label, type: summary.type, partner: summary.partner || view.partner },
      });
    }
  }
  return points;
}

/**
 * View for the search-results map: frame Australian activity by default so a single
 * overseas birthplace doesn't zoom the map out to the whole world.
 */
export function resultsView(points, { includeOverseas = false } = {}) {
  const { local, overseas } = splitByRegion(points);
  if (includeOverseas || !local.length) return viewFor([...local, ...overseas]);
  return viewFor(local);
}
