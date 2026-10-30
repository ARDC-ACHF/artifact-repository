import { useEffect, useRef, useState } from 'react';

export default function SearchBar({ value, onSearch, suggestions = [] }) {
  const [draft, setDraft] = useState(value);
  const inputRef = useRef(null);

  // Keep the box in sync when the URL changes (back button, suggestion links).
  useEffect(() => {
    setDraft(value);
  }, [value]);

  function submit(event) {
    event.preventDefault();
    onSearch(draft.trim());
  }

  function clear() {
    setDraft('');
    onSearch('');
    inputRef.current?.focus();
  }

  return (
    <div className="search-bar">
      <form className="search-bar__form" role="search" onSubmit={submit}>
        <label htmlFor="search-input" className="visually-hidden">Search the repository</label>
        <svg className="search-bar__icon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="m15.5 15.5 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          id="search-input"
          ref={inputRef}
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search people, performances, venues and artworks…"
          autoComplete="off"
          spellCheck="false"
        />
        {draft && (
          <button type="button" className="search-bar__clear" onClick={clear} aria-label="Clear search">×</button>
        )}
        <button type="submit" className="button button--primary">Search</button>
      </form>
      {suggestions.length > 0 && (
        <p className="search-bar__suggestions">
          <span>Try:</span>
          {suggestions.map((s) => (
            <button key={s} type="button" className="link-button" onClick={() => onSearch(s)}>{s}</button>
          ))}
        </p>
      )}
    </div>
  );
}
