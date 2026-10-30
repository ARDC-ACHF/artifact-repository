import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import EntityLink, { useRepositoryStatus } from '../components/EntityLink.jsx';
import FactList from '../components/FactList.jsx';
import ImageGallery from '../components/ImageGallery.jsx';
import PartnerBadge from '../components/PartnerBadge.jsx';
import PlaceMap from '../components/PlaceMap.jsx';
import RawJson from '../components/RawJson.jsx';
import VersionHistory from '../components/VersionHistory.jsx';
import { getArtifactCached, isAbortError, searchArtifacts } from '../lib/api.js';
import { typeLabel } from '../lib/filters.js';
import { parseArtifact } from '../lib/linkedart.js';
import { artifactHref, groupByRole, selectMentions } from '../lib/links.js';

const MENTION_TITLES = {
  place: 'Events and people at this place',
  person: 'Also appears in',
  event: 'Also linked from',
  object: 'Also linked from',
};

/** Records that point at this one but aren't linked from it (e.g. events held at a venue). */
function useMentions(view) {
  const [state, setState] = useState({ id: null, items: [] });
  useEffect(() => {
    if (!view || !view.id || !view.label) return undefined;
    const controller = new AbortController();
    searchArtifacts({ q: view.label, limit: 50 }, { signal: controller.signal })
      .then(async (data) => {
        const summaries = (data.results || []).filter((s) => s.id !== view.id);
        const outcomes = await Promise.allSettled(summaries.map((s) => getArtifactCached(s.id)));
        const candidates = outcomes
          .map((o, i) => (o.status === 'fulfilled' ? { summary: summaries[i], raw: o.value } : null))
          .filter(Boolean);
        if (!controller.signal.aborted) setState({ id: view.id, items: selectMentions(candidates, view) });
      })
      .catch((error) => {
        // Reverse links are a nice-to-have; a failed lookup just hides the section.
        if (!controller.signal.aborted && !isAbortError(error)) setState({ id: view.id, items: [] });
      });
    return () => controller.abort();
  }, [view]);
  return state.id === (view && view.id) ? state.items : [];
}

function RelatedSection({ view, statuses, mentions }) {
  const groups = groupByRole(view.related, 'rel');
  if (!groups.length && !mentions.length) return null;
  return (
    <section className="detail-card">
      <h2 className="detail-card__title">Related records</h2>
      {groups.map((group) => (
        <div key={group.role} className="related-group">
          <h3 className="related-group__title">{group.role}</h3>
          <ul className="related-list">
            {group.items.map((item) => (
              <li key={item.id}>
                <EntityLink entry={item} status={statuses.get(item.id)} className="related-list__link" />
                {item.type && <span className="related-list__type">{typeLabel(item.type)}</span>}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {mentions.length > 0 && (
        <div className="related-group">
          <h3 className="related-group__title">{MENTION_TITLES[view.kind] || 'Also linked from'}</h3>
          <ul className="related-list">
            {mentions.map((summary) => (
              <li key={summary.id} className={`partner-${summary.partner}`}>
                <Link to={artifactHref(summary.id)} className="entity-link related-list__link">{summary.label || summary.id}</Link>
                <span className="related-list__type">{typeLabel(summary.type)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function useArtifact(iri, reloadToken) {
  const [state, setState] = useState({ iri: null, raw: null, view: null, error: null });
  useEffect(() => {
    if (!iri) return undefined;
    let active = true;
    getArtifactCached(iri)
      .then((raw) => active && setState({ iri, raw, view: parseArtifact(raw), error: null }))
      .catch((error) => active && setState({ iri, raw: null, view: null, error }));
    return () => {
      active = false;
    };
  }, [iri, reloadToken]);
  return state.iri === iri ? state : { iri, raw: null, view: null, error: null };
}

export default function ArtifactPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const iri = (params.get('iri') || '').trim();
  const [reloadToken, setReloadToken] = useState(0);
  const { raw, view, error } = useArtifact(iri, reloadToken);

  const linkIds = useMemo(() => (view ? [...view.people, ...view.places, ...view.related].map((e) => e.id).filter((id) => id && id !== view.id) : []), [view]);
  const statuses = useRepositoryStatus(linkIds);
  const mentions = useMentions(view);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [iri]);

  useEffect(() => {
    document.title = view ? `${view.label} · Linked Art Repository` : 'Linked Art Repository';
  }, [view]);

  // location.key is 'default' on a fresh page load, i.e. there is no in-app page to go back to.
  const back = (
    <button type="button" className="link-button back-link" onClick={() => (location.key !== 'default' ? navigate(-1) : navigate('/'))}>
      ← Back
    </button>
  );

  if (!iri) {
    return <div className="state-panel"><p>No record was specified.</p><Link className="button" to="/">Search the repository</Link></div>;
  }
  if (error) {
    const missing = error.status === 404;
    return (
      <div className="state-panel state-panel--error" role="alert">
        <p><strong>{missing ? 'This record isn’t in the repository.' : 'The record could not be loaded.'}</strong></p>
        <p>{missing ? <code className="fact-list__iri">{iri}</code> : error.message}</p>
        <div className="state-panel__actions">
          {!missing && <button type="button" className="button button--primary" onClick={() => setReloadToken((n) => n + 1)}>Try again</button>}
          <Link className="button" to="/">Back to search</Link>
        </div>
      </div>
    );
  }
  if (!view) {
    return (
      <div className="artifact artifact--loading" aria-busy="true">
        <div className="artifact__hero">
          <div className="gallery__stage result-card__shimmer-block" />
          <div><p className="muted">Loading record…</p></div>
        </div>
      </div>
    );
  }

  const [lead, ...moreDescriptions] = view.descriptions;
  const venue = view.places.find((p) => p.role === 'venue');

  return (
    <article className={`artifact partner-${view.partner}`}>
      {back}
      <header className="artifact__hero">
        <ImageGallery key={view.id} images={view.images} kind={view.kind} label={view.label} />
        <div className="artifact__intro">
          <div className="artifact__eyebrow">
            <PartnerBadge partner={view.partner} />
            <span className="artifact__type">{typeLabel(view.type)}</span>
          </div>
          <h1 className="artifact__title">{view.label}</h1>
          {(view.timespan || venue) && (
            <p className="artifact__date">
              {view.timespan && view.timespan.label}
              {view.timespan && venue && ' · '}
              {venue && <EntityLink entry={venue} status={venue.id ? statuses.get(venue.id) : undefined} />}
            </p>
          )}
          {view.classifications.length > 0 && (
            <ul className="chip-list">
              {view.classifications.map((c) => <li key={c.label} className="type-chip">{c.label}</li>)}
            </ul>
          )}
          {lead && <p className="artifact__description">{lead.content}</p>}
          {view.externalLinks.length > 0 && (
            <div className="artifact__actions">
              {view.externalLinks.map((link) => (
                <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer" className="button button--accent">
                  {link.label} ↗
                </a>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="artifact__body">
        <div className="artifact__main">
          <section className="detail-card">
            <h2 className="detail-card__title">Details</h2>
            <FactList view={view} statuses={statuses} />
          </section>
          {moreDescriptions.length > 0 && (
            <section className="detail-card">
              <h2 className="detail-card__title">Notes</h2>
              {moreDescriptions.map((d) => (
                <div key={d.content} className="note">
                  <h3 className="note__label">{d.label}</h3>
                  <p>{d.content}</p>
                </div>
              ))}
            </section>
          )}
          <RelatedSection view={view} statuses={statuses} mentions={mentions} />
        </div>
        <aside className="artifact__aside">
          <section className="detail-card">
            <h2 className="detail-card__title">Where</h2>
            <PlaceMap view={view} statuses={statuses} />
          </section>
          <section className="detail-card">
            <h2 className="detail-card__title">Version history</h2>
            <VersionHistory iri={view.id || iri} />
          </section>
        </aside>
      </div>

      <RawJson raw={raw} iri={iri} />
    </article>
  );
}
