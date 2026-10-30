import { useState } from 'react';

import { buildQuery } from '../lib/api.js';

/** Collapsible pretty-printed JSON-LD; only rendered once opened. */
export default function RawJson({ raw, iri }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(null);
  const text = open ? JSON.stringify(raw, null, 2) : '';

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(raw, null, 2));
      setCopied('Copied');
    } catch {
      setCopied('Copy failed');
    }
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <details className="raw-json" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <span className="raw-json__title">Linked Art JSON-LD</span>
        <span className="raw-json__hint">{open ? 'Hide' : 'Show the record exactly as stored'}</span>
      </summary>
      {open && (
        <>
          <div className="raw-json__tools">
            <button type="button" className="button" onClick={copy}>{copied || 'Copy JSON'}</button>
            <a className="button" href={`/api/v1/artifacts/item${buildQuery({ iri })}`} target="_blank" rel="noopener noreferrer">Open in API</a>
          </div>
          <pre className="raw-json__code"><code>{text}</code></pre>
        </>
      )}
    </details>
  );
}
