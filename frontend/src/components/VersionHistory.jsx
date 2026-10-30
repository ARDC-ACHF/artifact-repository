import { useEffect, useState } from 'react';

import { getVersions, isAbortError } from '../lib/api.js';
import { formatPublishedAt } from '../lib/links.js';

/** Published versions of a record, newest first, each linking to its immutable JSON-LD snapshot. */
export default function VersionHistory({ iri }) {
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState({ iri: null, status: 'loading', data: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    setState({ iri, status: 'loading', data: null, error: null });
    getVersions(iri, { signal: controller.signal })
      .then((data) => setState({ iri, status: 'ready', data, error: null }))
      .catch((error) => {
        if (controller.signal.aborted || isAbortError(error)) return;
        setState({ iri, status: 'error', data: null, error });
      });
    return () => controller.abort();
  }, [iri, reloadToken]);

  const current = state.iri === iri ? state : { status: 'loading' };

  if (current.status === 'loading') return <p className="muted" aria-busy="true">Loading version history…</p>;
  if (current.status === 'error') {
    if (current.error.status === 404) return <p className="muted">No published versions were found for this record.</p>;
    return (
      <div className="inline-alert" role="alert">
        Version history is unavailable: {current.error.message}{' '}
        <button type="button" className="link-button" onClick={() => setReloadToken((n) => n + 1)}>Retry</button>
      </div>
    );
  }

  const versions = [...(current.data.versions || [])].sort((a, b) => (a.published_at < b.published_at ? 1 : -1));
  if (!versions.length) return <p className="muted">No published versions were found for this record.</p>;

  return (
    <>
      <p className="muted">
        {versions.length === 1 ? 'Published once.' : `${versions.length} published versions.`} Each version is kept as an immutable snapshot.
      </p>
      <ol className="version-list">
        {versions.map((version, i) => (
          <li key={version.published_at} className={`version-list__item${version.is_current ? ' version-list__item--current' : ''}`}>
            <span className="version-list__number">v{versions.length - i}</span>
            <time dateTime={version.published_at}>{formatPublishedAt(version.published_at)}</time>
            {version.is_current && <span className="version-list__badge">Current</span>}
            <a className="version-list__link" href={version.locator} target="_blank" rel="noopener noreferrer">JSON-LD</a>
          </li>
        ))}
      </ol>
    </>
  );
}
