# Load sample data

In a terminal, load the bundled sample artifacts

python sample_data/load.py           # POSTs to http://localhost:8000

## Load a work from ACMI

Fetch [Frog Detective 3 from the ACMI Public API](https://api.acmi.net.au/works/125569/?format=jsonld)
and publish its JSON-LD to the running repository:

```bash
python sample_data/load_acmi.py
python sample_data/load_acmi.py https://api.acmi.net.au/works/75517/
python sample_data/load_acmi.py 75517
python sample_data/load_acmi.py --work-id 125569 --base-url http://localhost:8000
python sample_data/load_acmi.py --direct  # use configured storage without a running server
```

Full work URIs and numeric IDs are accepted positionally or via `--work-id` /
`--uri`. The fetch URL is normalised to `https://api.acmi.net.au/works/<id>/?format=jsonld`,
replacing any supplied query string or fragment.

The loader requires internet access to ACMI. It preserves the API payload and
work ID; partner inference assigns `acmi`. Re-running it creates a version only
if the fetched content has changed. Fetch or publish failures exit with status 1.
