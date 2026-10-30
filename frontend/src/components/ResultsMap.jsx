import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { getArtifactCached } from '../lib/api.js';
import { typeLabel } from '../lib/filters.js';
import { collectResultPoints, groupByLocation, resultsView, splitByRegion } from '../lib/geo.js';
import { parseArtifact } from '../lib/linkedart.js';
import { artifactHref } from '../lib/links.js';
import MapBase, { PARTNER_COLOURS, markerColour } from './MapBase.jsx';

const POPUP_LIMIT = 8;

/** Load and parse the full records behind the summaries; ignores replies for an outdated set. */
function useParsedResults(items, reloadToken) {
  const key = items.map((s) => s.id).join('\n');
  const [state, setState] = useState({ key: null, entries: [], failed: 0 });
  useEffect(() => {
    let active = true;
    Promise.allSettled(items.map((summary) => getArtifactCached(summary.id))).then((outcomes) => {
      if (!active) return;
      const entries = [];
      let failed = 0;
      outcomes.forEach((outcome, i) => {
        if (outcome.status === 'fulfilled') entries.push({ summary: items[i], view: parseArtifact(outcome.value, { partner: items[i].partner }) });
        else failed += 1;
      });
      setState({ key, entries, failed });
    });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, reloadToken]);
  return state.key === key ? state : null;
}

function Popup({ group }) {
  const place = group.items[0].place;
  const records = [];
  const seen = new Set();
  for (const item of group.items) {
    if (seen.has(item.record.id)) continue;
    seen.add(item.record.id);
    records.push(item);
  }
  // The venue's own record (if it is in the results) is the place link; list the rest under it.
  const placeRecord = records.find((r) => r.record.id === place.id);
  const others = records.filter((r) => r !== placeRecord);
  return (
    <div className="map-popup">
      <p className="map-popup__title">
        {placeRecord || place.id
          ? <Link to={artifactHref(place.id || placeRecord.record.id)}>{place.label}</Link>
          : place.label}
      </p>
      {others.length > 0 && (
        <ul className="map-popup__list">
          {others.slice(0, POPUP_LIMIT).map(({ record, role }) => (
            <li key={record.id}>
              <span className="map-popup__dot" style={{ background: PARTNER_COLOURS[record.partner] || '#1f2a44' }} aria-hidden="true" />
              <Link to={artifactHref(record.id)}>{record.label}</Link>
              <span className="map-popup__role"> · {typeLabel(record.type)}{role && role !== 'location' ? `, ${role}` : ''}</span>
            </li>
          ))}
        </ul>
      )}
      {others.length > POPUP_LIMIT && <p className="map-popup__more">+{others.length - POPUP_LIMIT} more</p>}
    </div>
  );
}

/** Map of every result that has coordinates; markers group records sharing a location. */
export default function ResultsMap({ items, total }) {
  const [includeOverseas, setIncludeOverseas] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const parsed = useParsedResults(items, reloadToken);

  const points = useMemo(() => (parsed ? collectResultPoints(parsed.entries) : []), [parsed]);
  const { overseas } = useMemo(() => splitByRegion(points), [points]);
  const groups = useMemo(() => groupByLocation(points).map((group) => {
    const records = new Set(group.items.map((i) => i.record.id));
    return {
      ...group,
      colour: markerColour(group.items.map((i) => i.record.partner)),
      tooltip: `${group.items[0].place.label} · ${records.size} ${records.size === 1 ? 'record' : 'records'}`,
      popup: <Popup group={group} />,
    };
  }), [points]);
  const view = useMemo(() => resultsView(points, { includeOverseas }), [points, includeOverseas]);

  if (!parsed) {
    return <div className="map-frame map-frame--results map-frame--loading" aria-busy="true"><p>Loading locations…</p></div>;
  }

  const mappedRecords = new Set(points.map((p) => p.record.id)).size;
  const unmapped = parsed.entries.length - mappedRecords;
  const overseasRecords = new Set(overseas.map((p) => p.record.id)).size;

  return (
    <div className="results-map">
      <div className="results-map__bar">
        <p className="results-map__summary">
          {mappedRecords
            ? `${mappedRecords} ${mappedRecords === 1 ? 'record' : 'records'} at ${groups.length} ${groups.length === 1 ? 'location' : 'locations'}`
            : 'None of these records has map coordinates'}
          {unmapped > 0 && mappedRecords > 0 && ` · ${unmapped} without coordinates`}
          {total > items.length && ` · showing the first ${items.length} of ${total} matches`}
        </p>
        {overseas.length > 0 && overseas.length < points.length && (
          <label className="results-map__toggle">
            <input type="checkbox" checked={includeOverseas} onChange={(e) => setIncludeOverseas(e.target.checked)} />
            Include places outside Australia ({overseasRecords} {overseasRecords === 1 ? 'record' : 'records'})
          </label>
        )}
      </div>
      {parsed.failed > 0 && (
        <div className="inline-alert" role="alert">
          {parsed.failed} {parsed.failed === 1 ? 'record' : 'records'} could not be loaded, so {parsed.failed === 1 ? 'it is' : 'they are'} missing from the map.
          {' '}<button type="button" className="link-button" onClick={() => setReloadToken((n) => n + 1)}>Retry</button>
        </div>
      )}
      {view ? (
        <MapBase view={view} groups={groups} className="map-frame--results" label="Map of search results" maxRadius={20} />
      ) : (
        <div className="map-empty map-frame--results">
          <p><strong>Nothing to map.</strong></p>
          <p>Try the list view, or search for venues and events, e.g. “Sydney” or “Theatre”.</p>
        </div>
      )}
    </div>
  );
}
