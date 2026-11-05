# Load sample data

In a terminal, load the bundled sample artifacts

python sample_data/load.py           # POSTs to http://localhost:8000

## Load a work from ACMI

Run these commands from the repository root. HTTP mode uses the same
`API_AUTH_USERNAME` and `API_AUTH_PASSWORD` environment variables as the server;
set both to the server's credentials before importing.

Fetch [Frog Detective 3 from the ACMI Public API](https://api.acmi.net.au/works/125569/?format=jsonld)
and publish its JSON-LD to the running repository:

```bash
python sample_data/load_acmi.py
python sample_data/load_acmi.py https://api.acmi.net.au/works/75517/
python sample_data/load_acmi.py 75517
python sample_data/load_acmi.py --work-id 125569 --base-url http://localhost:8000
.venv/bin/python sample_data/load_acmi.py --work-id 97661 --base-url http://localhost:8081
```

Full work URIs and numeric IDs are accepted positionally or via `--work-id` /
`--uri`. The fetch URL is normalised to `https://api.acmi.net.au/works/<id>/?format=jsonld`,
replacing any supplied query string or fragment.

The loader fetches ACMI's public JSON-LD without credentials, then authenticates
only the repository publication request. Missing credentials are reported before
fetching; a 401 means the server rejected the supplied credentials.

For filesystem loading without HTTP, stop the server first and run:

```bash
python sample_data/load_acmi.py --work-id 97661 --direct --data-dir ./data
```

Direct mode needs no API credentials. `--data-dir` selects the directory containing
`artifacts/` and `index.sqlite3` (default: `./data`).

The loader requires internet access to ACMI. It preserves the API payload and
work ID; partner inference assigns `acmi`. Re-running it creates a version only
if the fetched content has changed. Fetch or publish failures exit with status 1.

## Test the ACMI loader

From the repository root:

```bash
.venv/bin/python -m pytest sample_data/test_load_acmi.py
```

These tests use temporary storage and simulated HTTP requests; no running server
or ACMI API access is required. They are also discovered by `python -m pytest`.
