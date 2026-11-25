"""Partner inference must distinguish institutions from service subdomains."""

import pytest

from app.partners import HOST_TO_PARTNER, partner_for_iri


@pytest.mark.parametrize(
    ("iri", "expected"),
    [
        ("https://api.acmi.net.au/works/125569/", "acmi"),
        ("https://acmi.net.au/works/125569/", "acmi"),
        ("https://www.acmi.net.au/", "acmi"),
        ("https://v2.api.acmi.net.au/", "acmi"),
        ("https://user:password@API.ACMI.NET.AU.:8443/", "acmi"),
        ("https://collections.example.museum/thing/1", "example"),
        ("https://api.example.co.uk/", "example"),
        ("https://api.example.com/", "example"),
        ("https://ausstage.org.au/event/1", "ausstage"),
        ("https://www.austlit.edu.au/", "austlit"),
        ("https://nga.gov.au/", "nga"),
        ("https://collections.example.invalid/", "collections"),
        ("http://localhost:8000/", "localhost"),
        ("/works/125569/", "unknown"),
        ("", "unknown"),
    ],
)
def test_partner_for_iri(iri, expected):
    assert partner_for_iri(iri) == expected


def test_explicit_host_mapping_takes_precedence(monkeypatch):
    monkeypatch.setitem(HOST_TO_PARTNER, "api.example.com", "curated-name")
    assert partner_for_iri("https://api.example.com/works/1") == "curated-name"
