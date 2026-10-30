import { typeLabel } from '../lib/filters.js';
import { groupByRole } from '../lib/links.js';
import EntityLink from './EntityLink.jsx';

function capitalise(text) {
  return text ? `${text[0].toUpperCase()}${text.slice(1)}` : text;
}

function formatIsoDate(iso) {
  const match = /^(-?\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  if (!match) return iso;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

function EntityList({ items, statuses }) {
  return (
    <ul className="fact-list__entities">
      {items.map((item) => (
        <li key={`${item.id || item.label}|${item.role || item.rel}`}>
          <EntityLink entry={item} status={item.id ? statuses.get(item.id) : undefined} />
          {item.type === 'Group' && <span className="fact-list__note"> (group)</span>}
        </li>
      ))}
    </ul>
  );
}

/** Key facts as a definition list; rows without data are omitted. */
export default function FactList({ view, statuses }) {
  const rows = [];
  rows.push(['Record type', <span>{typeLabel(view.type)} <span className="fact-list__note">({view.type})</span></span>]);

  if (view.timespan) {
    const { label, begin, end } = view.timespan;
    const machine = [begin, end].filter(Boolean).map(formatIsoDate);
    const showRange = machine.length && !(label || '').match(/\d{4}/);
    rows.push([view.kind === 'person' ? 'Lifespan' : 'Date', (
      <span>
        {label}
        {showRange ? <span className="fact-list__note"> ({machine.join(' – ')})</span> : null}
      </span>
    )]);
  }

  if (view.classifications.length) {
    rows.push(['Classified as', (
      <ul className="chip-list">
        {view.classifications.map((c) => (
          <li key={c.label} className="type-chip" title={c.id || undefined}>{c.label}</li>
        ))}
      </ul>
    )]);
  }

  for (const group of groupByRole(view.people)) {
    rows.push([capitalise(group.role), <EntityList items={group.items} statuses={statuses} />]);
  }

  for (const group of groupByRole(view.places)) {
    rows.push([capitalise(group.role), (
      <ul className="fact-list__entities">
        {group.items.map((place) => (
          <li key={`${place.id || place.label}|${place.role}`}>
            {place.id && place.id !== view.id
              ? <EntityLink entry={place} status={statuses.get(place.id)} />
              : place.label}
            {place.lat !== null && (
              <span className="fact-list__note"> · {place.lat.toFixed(4)}, {place.lon.toFixed(4)}</span>
            )}
          </li>
        ))}
      </ul>
    )]);
  }

  if (view.materials.length) rows.push(['Materials', view.materials.join('; ')]);
  if (view.dimensions.length) rows.push(['Dimensions', view.dimensions.join('; ')]);

  if (view.externalLinks.length) {
    rows.push(['On the partner site', (
      <ul className="fact-list__entities">
        {view.externalLinks.map((link) => (
          <li key={link.url}>
            <a href={link.url} target="_blank" rel="noopener noreferrer" className="external-link">{link.label}</a>
          </li>
        ))}
      </ul>
    )]);
  }

  rows.push(['Identifier', <code className="fact-list__iri">{view.id}</code>]);

  return (
    <dl className="fact-list">
      {rows.map(([term, value], i) => (
        <div key={`${i}|${term}`} className="fact-list__row">
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
