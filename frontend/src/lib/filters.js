// Search state <-> URL. Mirrors the API's filter semantics: values within one facet are
// OR-ed (repeated `types`/`partners`, or repeated `type`/`partner` on the list endpoint),
// and the facets are AND-ed together.

export const PAGE_SIZE = 24;

export const PARTNERS = [
  { slug: 'ausstage', label: 'AusStage', blurb: 'Australian live performance' },
  { slug: 'daao', label: 'DAAO', blurb: 'Design & Art Australia Online' },
  { slug: 'austlit', label: 'AustLit', blurb: 'Australian literature' },
  { slug: 'nga', label: 'NGA', blurb: 'National Gallery of Australia' },
];

// UI type chips map onto one or more Linked Art top-level classes.
export const TYPE_FILTERS = [
  { slug: 'event', label: 'Event', types: ['Activity', 'Event'] },
  { slug: 'person', label: 'Person', types: ['Person', 'Group'] },
  { slug: 'place', label: 'Place', types: ['Place'] },
  { slug: 'object', label: 'Object', types: ['HumanMadeObject', 'VisualItem'] },
  { slug: 'text', label: 'Text', types: ['LinguisticObject', 'Text'] },
];

const PARTNER_SLUGS = new Set(PARTNERS.map((p) => p.slug));
const TYPE_SLUGS = new Map(TYPE_FILTERS.map((t) => [t.slug, t]));

export function partnerLabel(slug) {
  const known = PARTNERS.find((p) => p.slug === slug);
  return known ? known.label : slug || 'Unknown';
}

/** Friendly label for a Linked Art class ("Activity" -> "Event"). */
export function typeLabel(type) {
  const match = TYPE_FILTERS.find((t) => t.types.includes(type));
  return match ? match.label : type || 'Record';
}

export function isKnownPartner(slug) {
  return PARTNER_SLUGS.has(slug);
}

function uniqueInOrder(values, allowed) {
  const seen = new Set();
  return values
    .map((v) => (v || '').trim().toLowerCase())
    .filter((v) => v && allowed(v) && !seen.has(v) && seen.add(v));
}

/** Read search state from URLSearchParams; unknown filter values are dropped. */
export function readSearchState(params) {
  const q = (params.get('q') || '').trim();
  const partners = uniqueInOrder(params.getAll('partner'), (v) => PARTNER_SLUGS.has(v));
  const types = uniqueInOrder(params.getAll('type'), (v) => TYPE_SLUGS.has(v));
  const page = Number.parseInt(params.get('page') || '1', 10);
  return { q, partners, types, page: Number.isFinite(page) && page > 0 ? page : 1 };
}

/** Serialise search state; empty values are omitted so URLs stay short and shareable. */
export function writeSearchState({ q = '', partners = [], types = [], page = 1 }) {
  const params = new URLSearchParams();
  if (q.trim()) params.set('q', q.trim());
  for (const p of partners) params.append('partner', p);
  for (const t of types) params.append('type', t);
  if (page > 1) params.set('page', String(page));
  return params;
}

/** Linked Art class names to send to the API for the selected type chips. */
export function apiTypesFor(typeSlugs) {
  return typeSlugs.flatMap((slug) => (TYPE_SLUGS.get(slug) || { types: [] }).types);
}

export function toggle(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function pageCount(total, pageSize = PAGE_SIZE) {
  return Math.max(1, Math.ceil((total || 0) / pageSize));
}
