import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import PartnerBadge from '../components/PartnerBadge.jsx';
import TypePlaceholder from '../components/TypePlaceholder.jsx';
import { getArtifactCached } from '../lib/api.js';
import { typeLabel } from '../lib/filters.js';
import { parseArtifact } from '../lib/linkedart.js';

// Minimal record view; the full detail page (facts, maps, versions, raw JSON) builds on this.
export default function ArtifactPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const iri = params.get('iri') || '';
  const [state, setState] = useState({ iri: null, view: null, error: null });

  useEffect(() => {
    if (!iri) return undefined;
    let active = true;
    getArtifactCached(iri)
      .then((raw) => active && setState({ iri, view: parseArtifact(raw), error: null }))
      .catch((error) => active && setState({ iri, view: null, error }));
    return () => {
      active = false;
    };
  }, [iri]);

  const back = (
    <button type="button" className="link-button back-link" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}>
      ← Back to results
    </button>
  );

  if (!iri) {
    return <div className="state-panel"><p>No record was specified.</p><Link className="button" to="/">Search the repository</Link></div>;
  }
  const current = state.iri === iri ? state : { view: null, error: null };
  if (current.error) {
    return <div className="state-panel state-panel--error" role="alert">{back}<p>{current.error.message}</p></div>;
  }
  if (!current.view) {
    return <div className="state-panel" aria-busy="true"><p>Loading record…</p></div>;
  }
  const { view } = current;
  const image = view.images[0];
  return (
    <article className="artifact">
      {back}
      <div className="artifact__hero">
        <div className="artifact__media">
          {image ? <img src={image.url} alt={image.label || view.label} /> : <TypePlaceholder kind={view.kind} label={view.label} />}
        </div>
        <div>
          <PartnerBadge partner={view.partner} /> <span className="artifact__type">{typeLabel(view.type)}</span>
          <h1 className="artifact__title">{view.label}</h1>
          {view.timespan && <p className="artifact__date">{view.timespan.label}</p>}
          {view.descriptions.map((d) => <p key={d.content} className="artifact__description">{d.content}</p>)}
          {image && image.credit && <p className="artifact__credit">Image: {image.credit}</p>}
        </div>
      </div>
    </article>
  );
}
