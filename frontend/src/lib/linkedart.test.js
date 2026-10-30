import { readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { asArray, kindForType, mappablePlaces, parseArtifact, parseWktPoint, partnerForIri, snippet } from './linkedart.js';

const DEMO_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../../../sample_data/demo');
const load = (name) => JSON.parse(readFileSync(resolve(DEMO_DIR, name), 'utf-8'));

describe('parseWktPoint', () => {
  it('parses lon/lat order', () => {
    expect(parseWktPoint('POINT(151.2153 -33.8568)')).toEqual({ lon: 151.2153, lat: -33.8568 });
    expect(parseWktPoint('  point ( 144.9612   -37.7983 ) ')).toEqual({ lon: 144.9612, lat: -37.7983 });
    expect(parseWktPoint('POINT Z (1 2 3)')).toEqual({ lon: 1, lat: 2 });
  });

  it('ignores malformed or out-of-range input', () => {
    for (const bad of [undefined, null, 42, '', 'POINT()', 'POINT(1)', 'LINESTRING(1 2, 3 4)', 'POINT(abc def)', 'POINT(200 10)', 'POINT(10 -95)']) {
      expect(parseWktPoint(bad)).toBeNull();
    }
  });
});

describe('helpers', () => {
  it('normalises single values and lists', () => {
    expect(asArray(undefined)).toEqual([]);
    expect(asArray({ a: 1 })).toEqual([{ a: 1 }]);
    expect(asArray([1, 2])).toEqual([1, 2]);
  });

  it('maps partners and kinds like the backend', () => {
    expect(partnerForIri('https://www.daao.org.au/bio/albert-namatjira/')).toBe('daao');
    expect(partnerForIri('https://www.ausstage.edu.au/pages/event/1')).toBe('ausstage');
    expect(partnerForIri('https://ausstage.org.au/person/1')).toBe('ausstage');
    expect(partnerForIri('https://collections.example.museum/x')).toBe('collections');
    expect(partnerForIri('not a url')).toBe('unknown');
    expect(kindForType('Activity')).toBe('event');
    expect(kindForType('HumanMadeObject')).toBe('object');
    expect(kindForType('LinguisticObject')).toBe('text');
    expect(kindForType('Set')).toBe('other');
  });
});

describe('parseArtifact on demo records', () => {
  it('extracts an AusStage event', () => {
    const vm = parseArtifact(load('ausstage_event_godot_2013.json'));
    expect(vm).toMatchObject({ type: 'Activity', kind: 'event', partner: 'ausstage', label: 'Waiting for Godot (2013, Sydney Theatre)' });
    expect(vm.timespan).toEqual({ label: '2013', begin: '2013-01-01T00:00:00Z', end: '2013-12-31T23:59:59Z' });
    expect(vm.places).toEqual([{
      id: 'https://www.ausstage.edu.au/pages/venue/demo-sydney-theatre-walsh-bay',
      label: 'Sydney Theatre, Walsh Bay', role: 'venue', lat: -33.8573, lon: 151.2049,
    }]);
    expect(vm.people.map((p) => p.label)).toEqual(['Hugo Weaving', 'Richard Roxburgh', 'Sydney Theatre Company']);
    expect(vm.people[2].id).toBeNull();
    expect(vm.classifications).toEqual([{ id: 'http://vocab.getty.edu/aat/300069200', label: 'performance' }]);
    expect(vm.images).toHaveLength(1);
    expect(vm.images[0].url).toMatch(/^https:\/\/upload\.wikimedia\.org\//);
    expect(vm.images[0].credit).toContain('CC0');
    expect(vm.descriptions[0].content).toContain('Hugo Weaving as Vladimir');
    expect(vm.externalLinks).toEqual([{ url: 'https://www.ausstage.edu.au/', label: 'Search AusStage (demo identifiers are illustrative)' }]);
  });

  it('extracts a DAAO artwork with materials, dimensions and current location', () => {
    const vm = parseArtifact(load('daao_work_the_pioneer.json'));
    expect(vm.kind).toBe('object');
    expect(vm.partner).toBe('daao');
    expect(vm.timespan.label).toBe('1904');
    expect(vm.people).toEqual([{ id: 'https://www.daao.org.au/bio/frederick-mccubbin/', label: 'Frederick McCubbin', role: 'produced by', type: 'Person' }]);
    expect(vm.materials).toEqual(['oil on canvas (triptych)']);
    expect(vm.dimensions).toEqual(['225.0 × 295.7 cm']);
    expect(vm.places).toEqual([{ id: null, label: 'National Gallery of Victoria, Melbourne', role: 'current location', lat: -37.8226, lon: 144.9689 }]);
    expect(vm.descriptions.map((d) => d.label)).toEqual(['Description']);
    expect(vm.images[0].credit).toContain('Public domain');
  });

  it('extracts a DAAO artist with lifespan, birth/death places and works', () => {
    const vm = parseArtifact(load('daao_artist_namatjira.json'));
    expect(vm.kind).toBe('person');
    expect(vm.timespan).toEqual({ label: '28 July 1902 – 8 August 1959', begin: '1902-07-28T00:00:00Z', end: '1959-08-08T23:59:59Z' });
    expect(vm.places.map((p) => [p.role, p.label])).toEqual([
      ['born', 'Hermannsburg (Ntaria), Northern Territory'],
      ['died', 'Alice Springs, Northern Territory'],
    ]);
    expect(mappablePlaces(vm)).toHaveLength(2);
    expect(vm.related).toEqual([{
      id: 'https://www.daao.org.au/bio/albert-namatjira/works/demo-central-australian-landscape/',
      label: 'Central Australian landscape with ghost gum', type: 'HumanMadeObject', rel: 'produced',
    }]);
  });

  it('extracts an AusStage person and a venue', () => {
    const person = parseArtifact(load('ausstage_person_rush.json'));
    expect(person.related.map((r) => r.rel)).toEqual(['took part in', 'took part in', 'took part in']);
    expect(person.timespan.label).toBe('Born 1951');
    const venue = parseArtifact(load('ausstage_venue_union.json'));
    expect(venue.kind).toBe('place');
    expect(venue.places[0]).toMatchObject({ role: 'location', lat: -37.7983, lon: 144.9612, id: venue.id });
    expect(venue.descriptions.map((d) => d.label)).toEqual(['Description', 'Locality']);
  });

  it('parses every demo record without throwing and keeps all coordinates valid', () => {
    const files = readdirSync(DEMO_DIR).filter((f) => f.endsWith('.json'));
    expect(files.length).toBeGreaterThanOrEqual(30);
    for (const file of files) {
      const vm = parseArtifact(load(file));
      expect(vm.id, file).toBeTruthy();
      expect(['ausstage', 'daao']).toContain(vm.partner);
      for (const place of mappablePlaces(vm)) {
        expect(Math.abs(place.lat)).toBeLessThanOrEqual(90);
        expect(Math.abs(place.lon)).toBeLessThanOrEqual(180);
      }
    }
  });
});

describe('parseArtifact edge cases', () => {
  it('handles empty and non-object input', () => {
    for (const raw of [null, undefined, 'x', {}]) {
      const vm = parseArtifact(raw);
      expect(vm).toMatchObject({ id: null, kind: 'other', images: [], places: [], people: [], timespan: null, label: 'Untitled record' });
    }
  });

  it('accepts single objects where lists are usual and skips bad WKT', () => {
    const vm = parseArtifact({
      id: 'https://nga.gov.au/object/1',
      type: 'HumanMadeObject',
      identified_by: { type: 'Name', content: 'Named via identified_by' },
      classified_as: { type: 'Type', _label: 'print' },
      referred_to_by: { type: 'LinguisticObject', content: 'A single statement.' },
      representation: { type: 'VisualItem', digitally_shown_by: { type: 'DigitalObject', access_point: { id: 'https://example.org/a.jpg' } } },
      current_location: { type: 'Place', _label: 'Somewhere', defined_by: 'POINT(nope)' },
      made_of: { type: 'Material', _label: 'paper' },
      dimension: { type: 'Dimension', value: 10, unit: { _label: 'centimetres' }, classified_as: [{ _label: 'height' }] },
      created_by: { type: 'Creation', carried_out_by: { id: 'https://nga.gov.au/p/1', type: 'Person', _label: 'Maker' } },
      subject_of: { type: 'LinguisticObject', digitally_carried_by: { access_point: 'https://nga.gov.au/page' } },
    }, { partner: 'nga' });
    expect(vm.label).toBe('Named via identified_by');
    expect(vm.classifications).toEqual([{ id: null, label: 'print' }]);
    expect(vm.descriptions).toEqual([{ label: 'Note', content: 'A single statement.' }]);
    expect(vm.images).toEqual([{ url: 'https://example.org/a.jpg', label: null, credit: null }]);
    expect(vm.places).toEqual([{ id: null, label: 'Somewhere', role: 'current location', lat: null, lon: null }]);
    expect(mappablePlaces(vm)).toEqual([]);
    expect(vm.materials).toEqual(['paper']);
    expect(vm.dimensions).toEqual(['Height: 10 cm']);
    expect(vm.people).toEqual([{ id: 'https://nga.gov.au/p/1', label: 'Maker', role: 'created by', type: 'Person' }]);
    expect(vm.externalLinks).toEqual([{ url: 'https://nga.gov.au/page', label: 'https://nga.gov.au/page' }]);
  });

  it('ignores non-http image URLs', () => {
    const vm = parseArtifact({ representation: [{ digitally_shown_by: [{ access_point: [{ id: 'javascript:alert(1)' }] }] }] });
    expect(vm.images).toEqual([]);
  });
});

describe('snippet', () => {
  it('returns short text untouched and truncates long text on a word boundary', () => {
    expect(snippet({ descriptions: [{ content: 'Short.' }] })).toBe('Short.');
    const long = 'word '.repeat(60);
    const result = snippet({ descriptions: [{ content: long }] }, 50);
    expect(result.length).toBeLessThanOrEqual(50);
    expect(result.endsWith('word…')).toBe(true);
    expect(snippet({ descriptions: [] })).toBe('');
  });
});
