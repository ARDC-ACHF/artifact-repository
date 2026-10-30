import { readdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it, vi } from 'vitest';

import {
  collectResultPoints, groupByLocation, isInAustralia, resultsView, splitByRegion, viewFor, SINGLE_POINT_ZOOM,
} from './geo.js';
import { parseArtifact } from './linkedart.js';
import {
  artifactHref, createRepositoryResolver, formatPublishedAt, groupByRole, linkTargetFor, linkedIds,
  parseCredit, parsePublishedAt, referencesIri, selectMentions,
} from './links.js';

const demoDir = resolve(dirname(fileURLToPath(import.meta.url)), '../../../sample_data/demo');
const load = (name) => JSON.parse(readFileSync(resolve(demoDir, name), 'utf8'));

const SYDNEY = { lat: -33.8568, lon: 151.2153 };
const MELBOURNE = { lat: -37.7983, lon: 144.9612 };
const VIENNA = { lat: 48.2082, lon: 16.3738 };

describe('geo helpers', () => {
  it('classifies Australian and overseas points', () => {
    expect(isInAustralia(SYDNEY)).toBe(true);
    expect(isInAustralia({ lat: -42.88, lon: 147.33 })).toBe(true); // Hobart
    expect(isInAustralia(VIENNA)).toBe(false);
    expect(isInAustralia({ lat: -41.29, lon: 174.78 })).toBe(false); // Wellington
    expect(isInAustralia({ lat: null, lon: 1 })).toBe(false);
    const { local, overseas } = splitByRegion([SYDNEY, VIENNA, MELBOURNE, { lat: NaN, lon: 0 }]);
    expect(local).toHaveLength(2);
    expect(overseas).toEqual([VIENNA]);
  });

  it('centres on a single location and fits bounds around several', () => {
    expect(viewFor([])).toBeNull();
    expect(viewFor([SYDNEY, { ...SYDNEY }])).toEqual({ center: [SYDNEY.lat, SYDNEY.lon], zoom: SINGLE_POINT_ZOOM });
    expect(viewFor([SYDNEY, MELBOURNE])).toEqual({ bounds: [[MELBOURNE.lat, MELBOURNE.lon], [SYDNEY.lat, SYDNEY.lon]] });
  });

  it('frames Australia on the results map unless overseas places are requested', () => {
    const points = [SYDNEY, MELBOURNE, VIENNA];
    expect(resultsView(points)).toEqual(viewFor([SYDNEY, MELBOURNE]));
    expect(resultsView(points, { includeOverseas: true })).toEqual(viewFor(points));
    // Only overseas points: still show them rather than an empty map.
    expect(resultsView([VIENNA])).toEqual(viewFor([VIENNA]));
    expect(resultsView([])).toBeNull();
  });

  it('groups co-located points into one marker', () => {
    const groups = groupByLocation([{ ...SYDNEY, n: 1 }, { lat: SYDNEY.lat + 0.00001, lon: SYDNEY.lon, n: 2 }, { ...MELBOURNE, n: 3 }]);
    expect(groups).toHaveLength(2);
    expect(groups[0].items.map((i) => i.n)).toEqual([1, 2]);
  });

  it('turns demo results into map points with record references', () => {
    const files = ['ausstage_event_godot_2013.json', 'ausstage_venue_sydneytheatre.json', 'daao_artist_vonguerard.json'];
    const entries = files.map((f) => {
      const raw = load(f);
      return { summary: { id: raw.id, label: raw._label, type: raw.type, partner: f.split('_')[0] }, view: parseArtifact(raw) };
    });
    const points = collectResultPoints(entries);
    const godot = points.filter((p) => p.record.id.includes('godot'));
    expect(godot).toHaveLength(1);
    expect(godot[0]).toMatchObject({ role: 'venue', place: { label: 'Sydney Theatre, Walsh Bay' }, record: { partner: 'ausstage' } });
    // Event and venue share coordinates -> one marker with both records.
    const groups = groupByLocation(points);
    const walshBay = groups.find((g) => g.items.some((i) => i.record.id.includes('godot')));
    expect(walshBay.items.map((i) => i.record.type).sort()).toEqual(['Activity', 'Place']);
    // Von Guérard's Vienna/London life events are overseas and excluded from the default frame.
    const { overseas } = splitByRegion(points);
    expect(overseas.map((p) => p.role).sort()).toEqual(['born', 'died']);
    expect(collectResultPoints([{ summary: null, view: null }])).toEqual([]);
  });
});

describe('related link resolution', () => {
  it('links to records in the repository and leaves confirmed-missing ones as text', () => {
    const entry = { id: 'https://www.ausstage.edu.au/pages/venue/x', label: 'X' };
    expect(linkTargetFor(entry, 'internal')).toEqual({ kind: 'internal', href: artifactHref(entry.id), pending: false });
    expect(linkTargetFor(entry, undefined)).toMatchObject({ kind: 'internal', pending: true });
    expect(linkTargetFor(entry, 'unknown')).toMatchObject({ kind: 'internal', pending: false });
    expect(linkTargetFor(entry, 'missing')).toMatchObject({ kind: 'text', title: expect.stringContaining('not in this repository') });
    expect(linkTargetFor({ label: 'Sydney Theatre Company' }, 'internal')).toEqual({ kind: 'text' });
    expect(artifactHref('https://a.example/x?y=1&z')).toBe('/artifact?iri=https%3A%2F%2Fa.example%2Fx%3Fy%3D1%26z');
  });

  it('caches hits and 404s but retries after other failures', async () => {
    const fetchRecord = vi.fn(async (iri) => {
      if (iri === 'missing') throw Object.assign(new Error('nf'), { status: 404 });
      if (iri === 'flaky' && fetchRecord.mock.calls.filter(([i]) => i === 'flaky').length === 1) {
        throw Object.assign(new Error('boom'), { status: 500 });
      }
      return { id: iri };
    });
    const resolve = createRepositoryResolver(fetchRecord);
    await expect(resolve('present')).resolves.toBe('internal');
    await expect(resolve('present')).resolves.toBe('internal');
    await expect(resolve('missing')).resolves.toBe('missing');
    await expect(resolve('missing')).resolves.toBe('missing');
    await expect(resolve('flaky')).rejects.toMatchObject({ status: 500 });
    await expect(resolve('flaky')).resolves.toBe('internal');
    await expect(resolve('')).resolves.toBe('missing');
    expect(fetchRecord.mock.calls.map(([i]) => i)).toEqual(['present', 'missing', 'flaky', 'flaky']);
  });

  it('finds reverse links (events at a venue) without duplicating forward links', () => {
    const venue = parseArtifact(load('ausstage_venue_sydneytheatre.json'));
    const event = load('ausstage_event_godot_2013.json');
    const weaving = load('ausstage_person_weaving.json');
    const candidates = [
      { summary: { id: event.id, label: event._label }, raw: event },
      { summary: { id: event.id, label: event._label }, raw: event },
      { summary: { id: weaving.id, label: weaving._label }, raw: weaving },
    ];
    expect(referencesIri(event, venue.id)).toBe(true);
    expect(referencesIri(weaving, venue.id)).toBe(false);
    expect(referencesIri(event, event.id)).toBe(false);
    expect(selectMentions(candidates, venue).map((s) => s.id)).toEqual([event.id]);

    // From Hugo Weaving's page the Godot event is already a forward link, so it is not repeated.
    const person = parseArtifact(weaving);
    expect(linkedIds(person).has(event.id)).toBe(true);
    expect(selectMentions([{ summary: { id: event.id }, raw: event }], person)).toEqual([]);
    expect(selectMentions(candidates, null)).toEqual([]);
  });

  it('groups people and related records by role in first-seen order', () => {
    const view = parseArtifact(load('ausstage_event_godot_2013.json'));
    const groups = groupByRole(view.people);
    expect(groups).toHaveLength(1);
    expect(groups[0].role).toBe('carried out by');
    expect(groups[0].items.map((p) => p.label)).toEqual(['Hugo Weaving', 'Richard Roxburgh', 'Sydney Theatre Company']);
    expect(groups[0].items[2].id).toBeNull();
    const artist = parseArtifact(load('daao_artist_vonguerard.json'));
    expect(groupByRole(artist.related, 'rel')).toEqual([
      { role: 'produced', items: [expect.objectContaining({ label: 'Tower Hill', type: 'HumanMadeObject' })] },
    ]);
  });
});

describe('image attribution', () => {
  it('splits Wikimedia credits into author/licence and a source link', () => {
    const credit = parseCredit('Siebbi. CC BY 3.0. Wikimedia Commons: https://commons.wikimedia.org/wiki/File:Hugo_Weaving_2014.jpg');
    expect(credit).toEqual({
      text: 'Siebbi. CC BY 3.0. Wikimedia Commons',
      licence: 'CC BY 3.0',
      sourceUrl: 'https://commons.wikimedia.org/wiki/File:Hugo_Weaving_2014.jpg',
      sourceLabel: 'View on Wikimedia Commons',
    });
    expect(parseCredit('Public domain, via the artist.').licence).toBe('Public domain');
    expect(parseCredit('CC BY-SA 4.0 Jane').licence).toBe('CC BY-SA 4.0');
  });

  it('falls back to the image URL when the record has no credit', () => {
    const url = 'https://upload.wikimedia.org/wikipedia/commons/a/a1/X.jpg';
    expect(parseCredit(null, url)).toMatchObject({ text: 'Wikimedia Commons', sourceUrl: url, licence: null });
    expect(parseCredit(undefined)).toMatchObject({ text: '', sourceUrl: null });
  });

  it('every demo image carries a credit with a licence and source', () => {
    for (const name of readdirDemo()) {
      for (const image of parseArtifact(load(name)).images) {
        const credit = parseCredit(image.credit, image.url);
        expect(credit.licence, `${name}: ${image.credit}`).toBeTruthy();
        expect(credit.sourceUrl, name).toMatch(/^https:\/\/commons\.wikimedia\.org\//);
      }
    }
  });
});

function readdirDemo() {
  return readdirSync(demoDir).filter((n) => n.endsWith('.json'));
}

describe('version dates', () => {
  it('parses microsecond timestamps and formats them in UTC', () => {
    expect(parsePublishedAt('2026-10-30T01:02:03.123456Z').toISOString()).toBe('2026-10-30T01:02:03.123Z');
    expect(parsePublishedAt('nope')).toBeNull();
    expect(parsePublishedAt(null)).toBeNull();
    expect(formatPublishedAt('2026-10-30T01:02:03.123456Z')).toMatch(/30 Oct 2026/);
    expect(formatPublishedAt('garbage')).toBe('garbage');
    expect(formatPublishedAt(undefined)).toBe('Unknown date');
  });
});
