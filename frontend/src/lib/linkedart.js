// Pure helpers that turn raw Linked Art JSON-LD into a flat view model for the UI.
// Every Linked Art field may hold a single value or a list, and any of them may be missing.

export function asArray(value) {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value : [value];
}

const WKT_POINT = /^\s*POINT\s*Z?\s*\(\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?:\s+-?\d+(?:\.\d+)?)?\s*\)\s*$/i;

/** Parse a WKT `POINT(lon lat)` string; returns null for anything malformed or out of range. */
export function parseWktPoint(wkt) {
  if (typeof wkt !== 'string') return null;
  const match = WKT_POINT.exec(wkt);
  if (!match) return null;
  const lon = Number(match[1]);
  const lat = Number(match[2]);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return null;
  return { lon, lat };
}

const HOST_TO_PARTNER = {
  'ausstage.org.au': 'ausstage',
  'ausstage.edu.au': 'ausstage',
  'austlit.edu.au': 'austlit',
  'nga.gov.au': 'nga',
  'daao.org.au': 'daao',
};

/** Mirror of app/partners.py so records fetched without a summary still get a partner. */
export function partnerForIri(iri) {
  let host;
  try {
    host = new URL(iri).hostname.toLowerCase();
  } catch {
    return 'unknown';
  }
  if (host.startsWith('www.')) host = host.slice(4);
  if (HOST_TO_PARTNER[host]) return HOST_TO_PARTNER[host];
  const first = host.split('.').find(Boolean);
  return (first || 'unknown').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'unknown';
}

export function kindForType(type) {
  switch (type) {
    case 'Activity':
    case 'Event':
      return 'event';
    case 'Person':
    case 'Group':
      return 'person';
    case 'Place':
      return 'place';
    case 'HumanMadeObject':
    case 'VisualItem':
      return 'object';
    case 'LinguisticObject':
    case 'Text':
      return 'text';
    default:
      return 'other';
  }
}

function text(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/** Display label: `_label`, else the first Name in `identified_by`. */
export function labelOf(node) {
  if (!node || typeof node !== 'object') return null;
  const direct = text(node._label);
  if (direct) return direct;
  for (const ident of asArray(node.identified_by)) {
    if (ident && ident.type === 'Name' && text(ident.content)) return text(ident.content);
  }
  return null;
}

function classificationLabels(node) {
  return asArray(node && node.classified_as)
    .map((c) => (c && typeof c === 'object' ? (text(c._label) || '').toLowerCase() : ''))
    .filter(Boolean);
}

function idOf(node) {
  return node && typeof node === 'object' && text(node.id) ? node.id : null;
}

function parseTimespan(ts) {
  if (!ts || typeof ts !== 'object') return null;
  const begin = text(ts.begin_of_the_begin) || text(ts.end_of_the_begin);
  const end = text(ts.end_of_the_end) || text(ts.begin_of_the_end);
  const label = labelOf(ts) || formatRange(begin, end);
  if (!label && !begin && !end) return null;
  return { label, begin, end };
}

function year(iso) {
  const match = /^(-?\d{1,4})/.exec(iso || '');
  return match ? match[1] : null;
}

function formatRange(begin, end) {
  const a = year(begin);
  const b = year(end);
  if (a && b) return a === b ? a : `${a}–${b}`;
  return a || b || null;
}

const STATEMENT_KIND = {
  description: 'description',
  'materials statement': 'materials',
  medium: 'materials',
  'dimensions statement': 'dimensions',
  dimensions: 'dimensions',
  'attribution statement': 'credit',
  'image credit': 'credit',
};

function statementKind(statement) {
  for (const cls of classificationLabels(statement)) {
    if (STATEMENT_KIND[cls]) return STATEMENT_KIND[cls];
  }
  const label = (text(statement._label) || '').toLowerCase();
  return STATEMENT_KIND[label] || 'note';
}

const UNIT_ABBREVIATIONS = {
  centimetres: 'cm', centimeters: 'cm', millimetres: 'mm', millimeters: 'mm',
  metres: 'm', meters: 'm', inches: 'in', kilograms: 'kg', grams: 'g',
};

function formatDimension(dim) {
  if (!dim || typeof dim !== 'object' || dim.value === undefined || dim.value === null) return null;
  const unitLabel = labelOf(dim.unit) || '';
  const unit = UNIT_ABBREVIATIONS[unitLabel.toLowerCase()] || unitLabel;
  const [what] = classificationLabels(dim);
  const amount = `${dim.value}${unit ? ` ${unit}` : ''}`;
  return what ? `${what[0].toUpperCase()}${what.slice(1)}: ${amount}` : amount;
}

function placeEntry(node, role) {
  if (!node || typeof node !== 'object') return null;
  const point = parseWktPoint(node.defined_by);
  const label = labelOf(node);
  if (!label && !point && !idOf(node)) return null;
  return {
    id: idOf(node),
    label: label || 'Unnamed place',
    role,
    lat: point ? point.lat : null,
    lon: point ? point.lon : null,
  };
}

function personEntry(node, role) {
  if (!node || typeof node !== 'object') return null;
  const label = labelOf(node);
  if (!label && !idOf(node)) return null;
  return { id: idOf(node), label: label || 'Unnamed', role, type: node.type || null };
}

function relatedEntry(node, rel) {
  const id = idOf(node);
  if (!id) return null;
  return { id, label: labelOf(node) || id, type: node.type || null, rel };
}

function uniqueBy(items, keyFn) {
  const seen = new Set();
  return items.filter((item) => {
    if (!item) return false;
    const key = keyFn(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function parseImages(raw) {
  const images = [];
  for (const visual of asArray(raw.representation)) {
    if (!visual || typeof visual !== 'object') continue;
    for (const digital of asArray(visual.digitally_shown_by)) {
      if (!digital || typeof digital !== 'object') continue;
      const credit = asArray(digital.referred_to_by)
        .filter((s) => s && statementKind(s) === 'credit')
        .map((s) => text(s.content))
        .find(Boolean) || null;
      for (const ap of asArray(digital.access_point)) {
        const url = typeof ap === 'string' ? ap : idOf(ap);
        if (url && /^https?:\/\//i.test(url)) {
          images.push({ url, label: labelOf(digital) || labelOf(visual), credit });
        }
      }
    }
  }
  return uniqueBy(images, (i) => i.url);
}

function parseExternalLinks(raw) {
  const links = [];
  for (const subject of asArray(raw.subject_of)) {
    if (!subject || typeof subject !== 'object') continue;
    for (const carrier of asArray(subject.digitally_carried_by)) {
      for (const ap of asArray(carrier && carrier.access_point)) {
        const url = typeof ap === 'string' ? ap : idOf(ap);
        if (url && /^https?:\/\//i.test(url)) links.push({ url, label: labelOf(subject) || url });
      }
    }
  }
  return uniqueBy(links, (l) => l.url);
}

/** Turn a raw Linked Art record into the view model used by pages and components. */
export function parseArtifact(raw, { partner } = {}) {
  const record = raw && typeof raw === 'object' ? raw : {};
  const id = text(record.id);
  const type = text(record.type) || 'Unknown';
  const kind = kindForType(type);

  const classifications = uniqueBy(
    asArray(record.classified_as)
      .filter((c) => c && typeof c === 'object')
      .map((c) => ({ id: idOf(c), label: labelOf(c) }))
      .filter((c) => c.label),
    (c) => c.label.toLowerCase(),
  );

  const descriptions = [];
  const materials = [];
  const dimensions = [];
  for (const statement of asArray(record.referred_to_by)) {
    if (!statement || typeof statement !== 'object') continue;
    const content = text(statement.content);
    if (!content) continue;
    const statementType = statementKind(statement);
    if (statementType === 'materials') materials.push(content);
    else if (statementType === 'dimensions') dimensions.push(content);
    else if (statementType !== 'credit') {
      descriptions.push({ label: text(statement._label) || 'Note', content, primary: statementType === 'description' });
    }
  }
  descriptions.sort((a, b) => Number(b.primary) - Number(a.primary));

  // A curated medium statement ("oil on canvas") reads better than the bare material list.
  if (!materials.length) {
    for (const material of asArray(record.made_of)) {
      const label = labelOf(material);
      if (label) materials.push(label);
    }
  }
  if (!dimensions.length) {
    for (const dim of asArray(record.dimension)) {
      const formatted = formatDimension(dim);
      if (formatted) dimensions.push(formatted);
    }
  }

  const production = asArray(record.produced_by)[0] || asArray(record.created_by)[0] || null;

  let timespan = parseTimespan(asArray(record.timespan)[0]) || parseTimespan(production && asArray(production.timespan)[0]);
  const born = asArray(record.born)[0];
  const died = asArray(record.died)[0];
  if (!timespan && (born || died)) {
    const b = parseTimespan(born && asArray(born.timespan)[0]);
    const d = parseTimespan(died && asArray(died.timespan)[0]);
    if (b || d) {
      const label = b && d ? `${b.label} – ${d.label}` : b ? `Born ${b.label}` : `Died ${d.label}`;
      timespan = { label, begin: b ? b.begin : null, end: d ? d.end : null };
    }
  }

  const places = [];
  if (kind === 'place') places.push(placeEntry({ ...record, id }, 'location'));
  for (const node of asArray(record.took_place_at)) places.push(placeEntry(node, kind === 'event' ? 'venue' : 'took place at'));
  if (production) {
    for (const node of asArray(production.took_place_at)) places.push(placeEntry(node, 'made at'));
  }
  for (const node of asArray(born && born.took_place_at)) places.push(placeEntry(node, 'born'));
  for (const node of asArray(died && died.took_place_at)) places.push(placeEntry(node, 'died'));
  for (const node of asArray(record.current_location)) places.push(placeEntry(node, 'current location'));

  const productionRole = record.created_by ? 'created by' : 'produced by';
  const people = uniqueBy([
    ...asArray(record.carried_out_by).map((p) => personEntry(p, 'carried out by')),
    ...asArray(production && production.carried_out_by).map((p) => personEntry(p, productionRole)),
  ], (p) => `${p.id || p.label}|${p.role}`);

  const related = [];
  for (const act of asArray(record.carried_out)) {
    if (!act || typeof act !== 'object') continue;
    related.push(relatedEntry(act, kind === 'person' ? 'took part in' : 'carried out'));
    for (const made of asArray(act.produced)) related.push(relatedEntry(made, 'produced'));
    for (const made of asArray(act.created)) related.push(relatedEntry(made, 'created'));
  }
  for (const [field, rel] of [['part_of', 'part of'], ['about', 'about'], ['represents', 'depicts'], ['member_of', 'member of'], ['used_specific_object', 'used']]) {
    for (const node of asArray(record[field])) related.push(relatedEntry(node, rel));
  }

  return {
    id,
    type,
    partner: partner || (id ? partnerForIri(id) : 'unknown'),
    label: labelOf(record) || id || 'Untitled record',
    kind,
    classifications,
    descriptions: descriptions.map(({ label, content }) => ({ label, content })),
    images: parseImages(record),
    timespan,
    places: places.filter(Boolean),
    people: people.filter(Boolean),
    related: uniqueBy(related.filter(Boolean), (r) => `${r.id}|${r.rel}`),
    materials: uniqueBy(materials, (m) => m.toLowerCase()),
    dimensions,
    externalLinks: parseExternalLinks(record),
  };
}

/** Short plain-text snippet for result cards. */
export function snippet(viewModel, maxLength = 160) {
  const source = viewModel && viewModel.descriptions && viewModel.descriptions[0];
  if (!source) return '';
  const content = source.content.replace(/\s+/g, ' ').trim();
  if (content.length <= maxLength) return content;
  const cut = content.slice(0, maxLength - 1);
  const lastSpace = cut.lastIndexOf(' ');
  return `${(lastSpace > maxLength * 0.6 ? cut.slice(0, lastSpace) : cut).replace(/[\s,;:.]+$/, '')}…`;
}

/** Places that can be drawn on a map. */
export function mappablePlaces(viewModel) {
  return ((viewModel && viewModel.places) || []).filter((p) => p.lat !== null && p.lon !== null);
}
