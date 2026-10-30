import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { getArtifactCached } from '../lib/api.js';
import { typeLabel } from '../lib/filters.js';
import { kindForType, parseArtifact, snippet } from '../lib/linkedart.js';
import { artifactHref } from '../lib/links.js';
import PartnerBadge from './PartnerBadge.jsx';
import TypePlaceholder from './TypePlaceholder.jsx';

/** Fetch and parse the full record behind a search summary (cached, ignores stale replies). */
export function useArtifactPreview(summary) {
  const [state, setState] = useState({ id: null, view: null, error: null });
  useEffect(() => {
    let active = true;
    getArtifactCached(summary.id)
      .then((raw) => active && setState({ id: summary.id, view: parseArtifact(raw, { partner: summary.partner }), error: null }))
      .catch((error) => active && setState({ id: summary.id, view: null, error }));
    return () => {
      active = false;
    };
  }, [summary.id, summary.partner]);
  // Never show a preview that belongs to a previous summary.
  return state.id === summary.id ? state : { id: summary.id, view: null, error: null };
}

export { artifactHref };

export default function ResultCard({ summary }) {
  const { view, error } = useArtifactPreview(summary);
  const [failedImages, setFailedImages] = useState(() => new Set());
  const loading = !view && !error;
  const kind = view ? view.kind : kindForType(summary.type);
  const label = summary.label || (view && view.label) || summary.id;
  const image = view && view.images.find((img) => !failedImages.has(img.url));
  const text = view ? snippet(view, 150) : '';
  const facts = view
    ? [view.timespan && view.timespan.label, view.classifications[0] && view.classifications[0].label].filter(Boolean)
    : [];

  return (
    <li className={`result-card partner-${summary.partner}`}>
      <Link to={artifactHref(summary.id)} className="result-card__link">
        <div className="result-card__media">
          {loading ? (
            <div className="result-card__shimmer" aria-hidden="true" />
          ) : image ? (
            <img src={image.url} alt={image.label || label} loading="lazy" decoding="async" onError={() => setFailedImages((prev) => new Set(prev).add(image.url))} />
          ) : (
            <TypePlaceholder kind={kind} label={label} />
          )}
          <span className="result-card__type">{typeLabel(summary.type)}</span>
        </div>
        <div className="result-card__body">
          <PartnerBadge partner={summary.partner} />
          <h3 className="result-card__title">{label}</h3>
          {facts.length > 0 && <p className="result-card__facts">{facts.join(' · ')}</p>}
          {text && <p className="result-card__snippet">{text}</p>}
          {loading && <p className="result-card__snippet result-card__snippet--muted">Loading preview…</p>}
          {error && <p className="result-card__snippet result-card__snippet--muted">Preview unavailable</p>}
        </div>
      </Link>
    </li>
  );
}
