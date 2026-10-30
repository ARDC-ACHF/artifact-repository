import { Link, Route, Routes } from 'react-router-dom';

import ArtifactPage from './pages/ArtifactPage.jsx';
import SearchPage from './pages/SearchPage.jsx';

function NotFound() {
  return (
    <div className="state-panel">
      <h1>Page not found</h1>
      <p>That address doesn’t match anything in the demo.</p>
      <Link className="button" to="/">Back to search</Link>
    </div>
  );
}

export default function App() {
  return (
    <div className="app">
      <header className="site-header">
        <div className="site-header__inner">
          <Link to="/" className="brand" aria-label="ACHF Explorer home">
            <span className="brand__mark" aria-hidden="true">AE</span>
            <span className="brand__text">
              <strong>ACHF Explorer</strong>
              <span>Australian cultural records, linked</span>
            </span>
          </Link>
          <nav className="site-nav" aria-label="Partners in this demo">
            <span className="partner-dot partner-ausstage">AusStage</span>
            <span className="partner-dot partner-daao">DAAO</span>
          </nav>
        </div>
      </header>

      <main className="site-main">
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/artifact" element={<ArtifactPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      <footer className="site-footer">
        <p>
          <strong>Demo data.</strong> Records are hand-curated to resemble AusStage and DAAO entries; some
          identifiers and details are illustrative. Images from Wikimedia Commons under their stated licences.
          Map tiles © OpenStreetMap contributors.
        </p>
      </footer>
    </div>
  );
}
