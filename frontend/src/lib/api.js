// Thin fetch wrapper around the repository API (/api/v1). All calls are read-only GETs.

const API_BASE = '/api/v1';

export class ApiError extends Error {
  constructor(message, { status = 0, url = '' } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.url = url;
  }
}

export function isAbortError(error) {
  return Boolean(error) && (error.name === 'AbortError' || error.code === 20);
}

/** Build a query string; arrays become repeated keys (`types=a&types=b`). */
export function buildQuery(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === '') continue;
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined && item !== null && item !== '') query.append(key, String(item));
    }
  }
  const text = query.toString();
  return text ? `?${text}` : '';
}

function describeFailure(status, detail) {
  if (status === 401 || status === 403) return 'The repository requires a login for reads. Start the server with DEMO_PUBLIC_READ=1.';
  if (status === 503) return 'The repository is not configured for access (no credentials and public read is off).';
  if (status === 404) return 'Not found in the repository.';
  if (status === 422) return `The request was rejected${detail ? `: ${detail}` : '.'}`;
  return `The repository returned an error (HTTP ${status})${detail ? `: ${detail}` : '.'}`;
}

function detailFrom(body) {
  if (!body) return '';
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg || '').filter(Boolean).join('; ');
  return '';
}

async function request(path, { signal, fetchImpl = globalThis.fetch } = {}) {
  const url = `${API_BASE}${path}`;
  let response;
  try {
    response = await fetchImpl(url, { signal, headers: { Accept: 'application/json, application/ld+json' } });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError('Could not reach the repository API. Is the server running?', { url });
  }
  let body = null;
  const raw = await response.text();
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      if (response.ok) throw new ApiError('The repository returned a response that is not JSON.', { status: response.status, url });
    }
  }
  if (!response.ok) {
    throw new ApiError(describeFailure(response.status, detailFrom(body)), { status: response.status, url });
  }
  return body;
}

/** Full-text search. `types`/`partners` are OR-ed within themselves, AND-ed together. */
export function searchArtifacts({ q, types = [], partners = [], limit = 24, offset = 0 }, options) {
  return request(`/search${buildQuery({ q, types, partners, limit, offset })}`, options);
}

/** Browse without a query; the list endpoint takes repeated `type`/`partner`. */
export function listArtifacts({ types = [], partners = [], limit = 24, offset = 0 }, options) {
  return request(`/artifacts${buildQuery({ type: types, partner: partners, limit, offset })}`, options);
}

export function getArtifact(iri, options) {
  return request(`/artifacts/item${buildQuery({ iri })}`, options);
}

export function getVersions(iri, options) {
  return request(`/artifacts/versions${buildQuery({ iri })}`, options);
}

export function getVersion(iri, publishedAt, options) {
  return request(`/artifacts/version${buildQuery({ iri, published_at: publishedAt })}`, options);
}

// Shared cache of in-flight/completed record fetches so cards and pages don't refetch.
// Failed fetches are evicted so a retry can succeed.
const artifactCache = new Map();
const CACHE_LIMIT = 300;

export function getArtifactCached(iri) {
  if (artifactCache.has(iri)) return artifactCache.get(iri);
  const promise = getArtifact(iri).catch((error) => {
    artifactCache.delete(iri);
    throw error;
  });
  artifactCache.set(iri, promise);
  if (artifactCache.size > CACHE_LIMIT) artifactCache.delete(artifactCache.keys().next().value);
  return promise;
}

export function clearArtifactCache() {
  artifactCache.clear();
}
