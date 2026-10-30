import { useEffect } from 'react';
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet';

import { MAX_FIT_ZOOM } from '../lib/geo.js';

export const PARTNER_COLOURS = {
  ausstage: '#b4232f',
  daao: '#0d7a6f',
  austlit: '#4f46c8',
  nga: '#b45f06',
};
const MIXED_COLOUR = '#1f2a44';

export function markerColour(partners) {
  const unique = [...new Set(partners)];
  return unique.length === 1 ? PARTNER_COLOURS[unique[0]] || MIXED_COLOUR : MIXED_COLOUR;
}

function viewKey(view) {
  return view ? JSON.stringify(view) : '';
}

/** Re-frame the map whenever the requested view changes (filters, overseas toggle, new record). */
function FitView({ view }) {
  const map = useMap();
  const key = viewKey(view);
  useEffect(() => {
    if (!view) return;
    map.invalidateSize();
    if (view.bounds) map.fitBounds(view.bounds, { padding: [48, 48], maxZoom: MAX_FIT_ZOOM });
    else map.setView(view.center, view.zoom);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);
  return null;
}

/**
 * Shared Leaflet map. `groups` come from groupByLocation(); each needs `colour`, `tooltip`
 * and `popup` (React content). Scroll-wheel zoom is off so the page scrolls normally on a demo.
 */
export default function MapBase({ view, groups, className = '', label, maxRadius = 16 }) {
  if (!view) return null;
  const initial = view.bounds
    ? { bounds: view.bounds, boundsOptions: { padding: [48, 48], maxZoom: MAX_FIT_ZOOM } }
    : { center: view.center, zoom: view.zoom };
  return (
    <div className={`map-frame ${className}`} role="region" aria-label={label}>
      <MapContainer {...initial} scrollWheelZoom={false} worldCopyJump className="map-canvas">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />
        <FitView view={view} />
        {groups.map((group) => (
          <CircleMarker
            key={group.key}
            center={[group.lat, group.lon]}
            radius={Math.min(maxRadius, 8 + Math.sqrt(group.items.length) * 3)}
            pathOptions={{ color: '#fff', weight: 2, fillColor: group.colour, fillOpacity: 0.9 }}
          >
            {group.tooltip && <Tooltip direction="top" offset={[0, -8]}>{group.tooltip}</Tooltip>}
            {group.popup && <Popup minWidth={220} maxWidth={320}>{group.popup}</Popup>}
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
