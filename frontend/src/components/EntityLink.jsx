import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { resolveInRepository } from '../lib/api.js';
import { linkTargetFor } from '../lib/links.js';

/** Look up which of `ids` are records in this repository: Map<id, 'pending'|'internal'|'missing'|'unknown'>. */
export function useRepositoryStatus(ids) {
  const key = useMemo(() => [...new Set((ids || []).filter(Boolean))].sort().join('\n'), [ids]);
  const [statuses, setStatuses] = useState(() => new Map());

  useEffect(() => {
    const list = key ? key.split('\n') : [];
    let active = true;
    for (const id of list) {
      resolveInRepository(id)
        .then((status) => active && setStatuses((prev) => new Map(prev).set(id, status)))
        .catch(() => active && setStatuses((prev) => new Map(prev).set(id, 'unknown')));
    }
    return () => {
      active = false;
    };
  }, [key]);

  return statuses;
}

/** Renders a reference as an internal link when the record is (or may be) in the repository. */
export default function EntityLink({ entry, status, className = '', children }) {
  const target = linkTargetFor(entry, status);
  const content = children || entry.label;
  if (target.kind === 'internal') {
    return <Link className={`entity-link ${className}`} to={target.href}>{content}</Link>;
  }
  return (
    <span className={`entity-text ${className}`} title={target.title}>
      {content}
      {status === 'missing' && <span className="entity-text__hint"> · not in repository</span>}
    </span>
  );
}
