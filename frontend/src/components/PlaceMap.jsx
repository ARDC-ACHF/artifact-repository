import { groupByLocation, splitByRegion, viewFor } from '../lib/geo.js';
import { mappablePlaces } from '../lib/linkedart.js';
import EntityLink from './EntityLink.jsx';
import MapBase, { markerColour } from './MapBase.jsx';

function roleText(items) {
  return [...new Set(items.map((p) => p.role))].join(', ');
}

/** Mini map of a single record's places (venue, birthplace, current location, …). */
export default function PlaceMap({ view, statuses }) {
  const places = mappablePlaces(view);
  const unmapped = view.places.filter((p) => p.lat === null || p.lon === null);

  if (!places.length) {
    return (
      <div className="map-empty">
        <p><strong>No mapped locations.</strong></p>
        <p>
          {unmapped.length
            ? `${unmapped.map((p) => p.label).join(', ')} ${unmapped.length === 1 ? 'has' : 'have'} no coordinates in this record.`
            : 'This record doesn’t name any places.'}
        </p>
      </div>
    );
  }

  const groups = groupByLocation(places).map((group) => ({
    ...group,
    colour: markerColour([view.partner]),
    tooltip: `${group.items[0].label} · ${roleText(group.items)}`,
    popup: (
      <div className="map-popup">
        {group.items.map((place) => (
          <p key={`${place.id || place.label}|${place.role}`} className="map-popup__row">
            <span className="map-popup__role">{place.role}</span>
            {place.id && place.id !== view.id
              ? <EntityLink entry={place} status={statuses.get(place.id)} />
              : <strong>{place.label}</strong>}
          </p>
        ))}
      </div>
    ),
  }));
  const { overseas } = splitByRegion(places);

  return (
    <div>
      <MapBase view={viewFor(places)} groups={groups} className="map-frame--mini" label={`Map of places for ${view.label}`} />
      <ul className="map-legend">
        {places.map((place) => (
          <li key={`${place.id || place.label}|${place.role}`}>
            <span className="map-legend__dot" style={{ background: markerColour([view.partner]) }} aria-hidden="true" />
            <span className="map-legend__role">{place.role}</span> {place.label}
          </li>
        ))}
        {unmapped.map((place) => (
          <li key={`${place.id || place.label}|${place.role}|unmapped`} className="map-legend__unmapped">
            <span className="map-legend__role">{place.role}</span> {place.label} (no coordinates)
          </li>
        ))}
      </ul>
      {overseas.length > 0 && overseas.length < places.length && (
        <p className="map-note">The map is zoomed out to include places outside Australia.</p>
      )}
    </div>
  );
}
