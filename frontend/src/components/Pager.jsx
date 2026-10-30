function pageWindow(page, pages) {
  const set = new Set([1, pages, page - 1, page, page + 1].filter((p) => p >= 1 && p <= pages));
  const sorted = [...set].sort((a, b) => a - b);
  const out = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push(`gap-${p}`);
    out.push(p);
  });
  return out;
}

export default function Pager({ page, pages, onPage }) {
  if (pages <= 1) return null;
  return (
    <nav className="pager" aria-label="Result pages">
      <button type="button" className="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>← Previous</button>
      <ol className="pager__pages">
        {pageWindow(page, pages).map((p) => (typeof p === 'string' ? (
          <li key={p} className="pager__gap" aria-hidden="true">…</li>
        ) : (
          <li key={p}>
            <button type="button" className={`pager__page${p === page ? ' pager__page--on' : ''}`} aria-current={p === page ? 'page' : undefined} onClick={() => onPage(p)}>
              {p}
            </button>
          </li>
        )))}
      </ol>
      <button type="button" className="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next →</button>
    </nav>
  );
}
