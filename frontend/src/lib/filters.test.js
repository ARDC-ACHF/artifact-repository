import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, buildQuery, getArtifactCached, clearArtifactCache, listArtifacts, searchArtifacts } from './api.js';
import { apiTypesFor, pageCount, readSearchState, toggle, writeSearchState } from './filters.js';

describe('search state in the URL', () => {
  it('round-trips multi-valued filters and drops unknown values', () => {
    const params = new URLSearchParams('q=%20Godot%20&partner=daao&partner=AUSSTAGE&partner=bogus&type=event&type=event&type=widget&page=3');
    const state = readSearchState(params);
    expect(state).toEqual({ q: 'Godot', partners: ['daao', 'ausstage'], types: ['event'], page: 3, view: 'list' });
    expect(writeSearchState(state).toString()).toBe('q=Godot&partner=daao&partner=ausstage&type=event&page=3');
  });

  it('defaults to browse-all page 1 and omits empty values', () => {
    expect(readSearchState(new URLSearchParams('page=-2'))).toEqual({ q: '', partners: [], types: [], page: 1, view: 'list' });
    expect(writeSearchState({ q: '  ', partners: [], types: [], page: 1 }).toString()).toBe('');
  });

  it('keeps the map view in the URL and drops paging there', () => {
    const state = readSearchState(new URLSearchParams('q=Godot&view=map&page=2'));
    expect(state.view).toBe('map');
    expect(writeSearchState(state).toString()).toBe('q=Godot&view=map');
    expect(readSearchState(new URLSearchParams('view=grid')).view).toBe('list');
    expect(writeSearchState({ ...state, view: 'list', page: 2 }).toString()).toBe('q=Godot&page=2');
  });

  it('maps type chips to Linked Art classes', () => {
    expect(apiTypesFor(['event', 'object'])).toEqual(['Activity', 'Event', 'HumanMadeObject', 'VisualItem']);
    expect(apiTypesFor([])).toEqual([]);
  });

  it('toggles and counts pages', () => {
    expect(toggle(['a'], 'b')).toEqual(['a', 'b']);
    expect(toggle(['a', 'b'], 'a')).toEqual(['b']);
    expect(pageCount(0)).toBe(1);
    expect(pageCount(24)).toBe(1);
    expect(pageCount(25)).toBe(2);
  });
});

function jsonResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, text: async () => (body === undefined ? '' : JSON.stringify(body)) };
}

describe('api client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearArtifactCache();
  });

  it('repeats array parameters', () => {
    expect(buildQuery({ q: 'a b', types: ['Activity', 'Event'], partners: [], offset: 0 })).toBe('?q=a+b&types=Activity&types=Event&offset=0');
    expect(buildQuery({})).toBe('');
  });

  it('uses search params for search and list params for browse', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { total: 0, results: [] }));
    await searchArtifacts({ q: 'Godot', types: ['Activity'], partners: ['ausstage'], limit: 24, offset: 24 }, { fetchImpl });
    await listArtifacts({ types: ['Place'], partners: ['ausstage', 'daao'], limit: 24, offset: 0 }, { fetchImpl });
    expect(fetchImpl.mock.calls[0][0]).toBe('/api/v1/search?q=Godot&types=Activity&partners=ausstage&limit=24&offset=24');
    expect(fetchImpl.mock.calls[1][0]).toBe('/api/v1/artifacts?type=Place&partner=ausstage&partner=daao&limit=24&offset=0');
  });

  it('turns HTTP and network failures into ApiError with a readable message', async () => {
    await expect(searchArtifacts({ q: 'x' }, { fetchImpl: async () => jsonResponse(401, { detail: 'Not authenticated' }) }))
      .rejects.toMatchObject({ name: 'ApiError', status: 401, message: expect.stringContaining('DEMO_PUBLIC_READ') });
    await expect(searchArtifacts({ q: 'x' }, { fetchImpl: async () => jsonResponse(422, { detail: [{ msg: 'bad limit' }] }) }))
      .rejects.toMatchObject({ status: 422, message: expect.stringContaining('bad limit') });
    await expect(searchArtifacts({ q: 'x' }, { fetchImpl: async () => { throw new TypeError('Failed to fetch'); } }))
      .rejects.toBeInstanceOf(ApiError);
  });

  it('passes aborts through untouched', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    await expect(searchArtifacts({ q: 'x' }, { fetchImpl: async () => { throw abort; } })).rejects.toBe(abort);
  });

  it('caches record fetches but evicts failures so retries work', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(500, {}))
      .mockResolvedValueOnce(jsonResponse(200, { id: 'x' }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(getArtifactCached('x')).rejects.toMatchObject({ status: 500 });
    await expect(getArtifactCached('x')).resolves.toEqual({ id: 'x' });
    await expect(getArtifactCached('x')).resolves.toEqual({ id: 'x' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
