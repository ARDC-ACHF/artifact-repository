import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import FilterChips from '../components/FilterChips.jsx';
import Pager from '../components/Pager.jsx';
import ResultCard from '../components/ResultCard.jsx';
import SearchBar from '../components/SearchBar.jsx';
import { isAbortError, listArtifacts, searchArtifacts } from '../lib/api.js';
import {
  PAGE_SIZE, PARTNERS, TYPE_FILTERS, apiTypesFor, pageCount, partnerLabel, readSearchState, writeSearchState,
} from '../lib/filters.js';

const SUGGESTIONS = ['Godot', 'Namatjira', 'Belvoir', 'Streeton', 'Opera House'];

function describeResults({ q, partners, types }, total) {
  const noun = total === 1 ? 'record' : 'records';
  const scope = [
    partners.length ? partners.map(partnerLabel).join(' or ') : null,
    types.length ? TYPE_FILTERS.filter((t) => types.includes(t.slug)).map((t) => t.label.toLowerCase()).join(' or ') : null,
  ].filter(Boolean).join(', ');
  const suffix = scope ? ` · ${scope}` : '';
  return q ? `${total} ${noun} matching “${q}”${suffix}` : `Browsing ${scope ? '' : 'all '}${total} ${noun}${suffix}`;
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const paramsKey = params.toString();
  const state = useMemo(() => readSearchState(new URLSearchParams(paramsKey)), [paramsKey]);
  const requestKey = writeSearchState(state).toString();
  const [reloadToken, setReloadToken] = useState(0);
  const [result, setResult] = useState({ key: null, status: 'loading', total: 0, items: [], error: null });

  useEffect(() => {
    const controller = new AbortController();
    const { q, partners, types, page } = state;
    const query = { types: apiTypesFor(types), partners, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE };
    setResult((prev) => ({ ...prev, status: 'loading', error: null }));
    const call = q
      ? searchArtifacts({ ...query, q }, { signal: controller.signal })
      : listArtifacts(query, { signal: controller.signal });
    call
      .then((data) => {
        if (controller.signal.aborted) return;
        setResult({ key: requestKey, status: 'ready', total: data.total || 0, items: data.results || [], error: null });
      })
      .catch((error) => {
        if (controller.signal.aborted || isAbortError(error)) return;
        setResult({ key: requestKey, status: 'error', total: 0, items: [], error });
      });
    // Aborting on change guarantees a slow, older request can never overwrite newer results.
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey, reloadToken]);

  const update = useCallback((patch) => {
    // Any change other than paging returns to page 1, matching a fresh query.
    const next = { ...state, page: 1, ...patch };
    setParams(writeSearchState(next));
  }, [state, setParams]);

  const goToPage = useCallback((page) => {
    update({ page });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [update]);

  const pages = pageCount(result.total);
  const stale = result.key !== requestKey;
  const loading = result.status === 'loading';
  const hasFilters = state.partners.length > 0 || state.types.length > 0;

  return (
    <div className="search-page">
      <section className="hero">
        <h1 className="hero__title">Explore Australia’s performing and visual arts, linked.</h1>
        <p className="hero__lede">
          One search across partner collections published as Linked Art: performances and venues from AusStage,
          artists and artworks from DAAO.
        </p>
        <SearchBar value={state.q} onSearch={(q) => update({ q })} suggestions={state.q ? [] : SUGGESTIONS} />
        <FilterChips
          partners={state.partners}
          types={state.types}
          partnerOptions={PARTNERS}
          typeOptions={TYPE_FILTERS}
          onPartnersChange={(partners) => update({ partners })}
          onTypesChange={(types) => update({ types })}
        />
      </section>

      <section className="results" aria-busy={loading} aria-live="polite">
        <div className="results__header">
          <h2 className="results__summary">
            {result.status === 'error' ? 'Something went wrong'
              : loading && (stale || result.items.length === 0) ? 'Searching…'
                : describeResults(state, result.total)}
          </h2>
          {pages > 1 && result.status === 'ready' && !stale && (
            <span className="results__page">Page {state.page} of {pages}</span>
          )}
        </div>

        {result.status === 'error' && !loading && (
          <div className="state-panel state-panel--error" role="alert">
            <p>{result.error.message}</p>
            <button type="button" className="button button--primary" onClick={() => setReloadToken((n) => n + 1)}>Try again</button>
          </div>
        )}

        {result.status === 'ready' && !stale && result.total === 0 && (
          <div className="state-panel">
            <p>No records match{state.q ? ` “${state.q}”` : ''}{hasFilters ? ' with these filters' : ''}.</p>
            {hasFilters && (
              <button type="button" className="button" onClick={() => update({ partners: [], types: [] })}>Clear filters</button>
            )}
          </div>
        )}

        {result.status === 'ready' && !stale && result.total > 0 && result.items.length === 0 && (
          <div className="state-panel">
            <p>Page {state.page} is past the end of these results.</p>
            <button type="button" className="button" onClick={() => goToPage(1)}>Go to page 1</button>
          </div>
        )}

        {result.items.length > 0 && (
          <ul className={`result-grid${loading ? ' result-grid--loading' : ''}`}>
            {result.items.map((summary) => <ResultCard key={summary.id} summary={summary} />)}
          </ul>
        )}

        {loading && result.items.length === 0 && result.status !== 'error' && (
          <ul className="result-grid" aria-hidden="true">
            {Array.from({ length: 8 }, (_, i) => <li key={i} className="result-card result-card--skeleton" />)}
          </ul>
        )}

        {!stale && result.status === 'ready' && <Pager page={state.page} pages={pages} onPage={goToPage} />}
      </section>
    </div>
  );
}
