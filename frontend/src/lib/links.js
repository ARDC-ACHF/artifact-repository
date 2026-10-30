// Pure helpers for the detail page: resolving related IRIs, image attribution and version dates.

export function artifactHref(iri) {
  return `/artifact?iri=${encodeURIComponent(iri)}`;
}

/**
 * Cache of "is this IRI a record in the repository?" checks.
 * `fetchRecord(iri)` resolves with the record or rejects with an error carrying `status`.
 * Resolves to 'internal' or 'missing' (404); other failures reject and are not cached,
 * so a later lookup can retry.
 */
export function createRepositoryResolver(fetchRecord) {
  const cache = new Map();
  return function resolve(iri) {
    if (!iri) return Promise.resolve('missing');
    if (cache.has(iri)) return cache.get(iri);
    const promise = Promise.resolve()
      .then(() => fetchRecord(iri))
      .then(
        () => 'internal',
        (error) => {
          if (error && error.status === 404) return 'missing';
          cache.delete(iri);
          throw error;
        },
      );
    cache.set(iri, promise);
    return promise;
  };
}

/**
 * Decide how to render a reference to another entity.
 * status: 'internal' | 'missing' | 'pending' | 'unknown' (lookup failed) | undefined.
 *  - in the repository (or not yet known)  -> internal detail-page link
 *  - confirmed missing                     -> plain text with the IRI as a hint
 *  - no IRI at all (e.g. an unnamed Group) -> plain text
 */
export function linkTargetFor(entry, status) {
  const id = entry && entry.id;
  if (!id) return { kind: 'text' };
  if (status === 'missing') return { kind: 'text', title: `${id} (not in this repository)` };
  return { kind: 'internal', href: artifactHref(id), pending: status === 'pending' || status === undefined };
}

const URL_PATTERN = /https?:\/\/[^\s<>"')]+/i;
const LICENCE_PATTERN = /\b(CC0(?: 1\.0)?|CC[ -]BY(?:[ -](?:SA|ND|NC|NC-SA|NC-ND))?(?: \d\.\d)?|Public domain)\b/i;

/**
 * Split an attribution statement such as
 * "Siebbi. CC BY 3.0. Wikimedia Commons: https://commons.wikimedia.org/wiki/File:X.jpg"
 * into display text, licence and a source link.
 */
export function parseCredit(credit, imageUrl = null) {
  const raw = typeof credit === 'string' ? credit.trim() : '';
  const urlMatch = URL_PATTERN.exec(raw);
  const sourceUrl = urlMatch ? urlMatch[0].replace(/[.,;]+$/, '') : imageUrl;
  const text = (urlMatch ? raw.replace(urlMatch[0], '') : raw).replace(/[\s:–-]+$/, '').trim();
  const licenceMatch = LICENCE_PATTERN.exec(raw);
  const isCommons = /wikimedia/i.test(raw) || /wikimedia\.org/i.test(sourceUrl || '');
  return {
    text: text || (isCommons ? 'Wikimedia Commons' : ''),
    licence: licenceMatch ? licenceMatch[1] : null,
    sourceUrl: sourceUrl || null,
    sourceLabel: isCommons ? 'View on Wikimedia Commons' : 'Image source',
  };
}

/** "2026-10-30T01:02:03.123456Z" -> Date (microseconds trimmed so every browser parses it). */
export function parsePublishedAt(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.replace(/(\.\d{3})\d+Z$/, '$1Z');
  const date = new Date(trimmed);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatPublishedAt(value, locale = 'en-AU') {
  const date = parsePublishedAt(value);
  if (!date) return value || 'Unknown date';
  return date.toLocaleString(locale, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short',
  });
}

/** Group entries by role, keeping first-seen order: [{ role, items }]. */
export function groupByRole(entries, key = 'role') {
  const groups = [];
  const index = new Map();
  for (const entry of entries || []) {
    const role = entry[key] || 'related';
    if (!index.has(role)) {
      index.set(role, groups.length);
      groups.push({ role, items: [] });
    }
    groups[index.get(role)].items.push(entry);
  }
  return groups;
}

/** True if the raw record references `iri` anywhere (as an `id` value). */
export function referencesIri(raw, iri) {
  if (!raw || !iri) return false;
  const stack = [raw];
  while (stack.length) {
    const node = stack.pop();
    if (Array.isArray(node)) stack.push(...node);
    else if (node && typeof node === 'object') {
      if (node.id === iri && node !== raw) return true;
      for (const value of Object.values(node)) if (value && typeof value === 'object') stack.push(value);
    }
  }
  return false;
}

/**
 * Reverse links: from search candidates `[{ summary, raw }]`, keep the records that
 * reference `view.id` and aren't already linked from the page itself.
 */
export function selectMentions(candidates, view) {
  if (!view || !view.id) return [];
  const already = linkedIds(view);
  const seen = new Set();
  const out = [];
  for (const { summary, raw } of candidates || []) {
    if (!summary || !summary.id || already.has(summary.id) || seen.has(summary.id)) continue;
    if (!referencesIri(raw, view.id)) continue;
    seen.add(summary.id);
    out.push(summary);
  }
  return out;
}

/** Ids already shown on the page, so reverse links don't duplicate them. */
export function linkedIds(view) {
  const ids = new Set();
  if (!view) return ids;
  for (const list of [view.people, view.places, view.related]) {
    for (const entry of list || []) if (entry.id) ids.add(entry.id);
  }
  if (view.id) ids.add(view.id);
  return ids;
}
