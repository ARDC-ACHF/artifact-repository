"""Curated AusStage + DAAO demo dataset and its seed script."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.index import FtsIndex
from app.partners import partner_for_iri
from app.service import RepositoryService
from app.storage.fs_store import FilesystemStore
from app.validation.validator import LinkedArtValidator

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "sample_data" / "demo"
WKT_POINT = re.compile(r"^POINT\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)$")
OPEN_LICENCES = ("Public domain", "CC0", "CC BY 2.5", "CC BY 3.0", "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0")

_spec = importlib.util.spec_from_file_location("seed_demo", REPO_ROOT / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_demo)


def _load():
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(DEMO_DIR.glob("*.json"))}


RECORDS = _load()
BY_ID = {rec["id"]: rec for rec in RECORDS.values()}


def _ids(entries):
    return {e["id"] for e in entries or [] if "id" in e}


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _by_prefix(prefix):
    return [rec for name, rec in RECORDS.items() if name.startswith(prefix)]


@pytest.fixture
def seeded(tmp_path):
    results = seed_demo.seed(tmp_path / "demo_data")
    index = FtsIndex(tmp_path / "demo_data" / "index.sqlite3")
    yield results, RepositoryService(FilesystemStore(tmp_path / "demo_data" / "artifacts"), index)
    index.close()


def test_dataset_shape():
    assert len(RECORDS) == len(BY_ID) >= 30
    counts = {prefix: len(_by_prefix(prefix)) for prefix in (
        "ausstage_venue_", "ausstage_event_", "ausstage_person_", "daao_artist_", "daao_work_")}
    assert counts["ausstage_venue_"] >= 6 and counts["ausstage_event_"] >= 8
    assert counts["ausstage_person_"] >= 6 and counts["daao_artist_"] >= 6 and counts["daao_work_"] >= 6


@pytest.mark.parametrize("name", sorted(RECORDS))
def test_every_record_is_valid_linked_art(name):
    result = LinkedArtValidator().validate(RECORDS[name])
    assert result.valid, result.errors


def test_partners_follow_file_prefix():
    for name, rec in RECORDS.items():
        assert partner_for_iri(rec["id"]) == name.split("_", 1)[0]


def test_coordinates_are_wkt_points_in_range():
    places = [node for rec in RECORDS.values() for node in _walk(rec) if "defined_by" in node]
    assert len(places) >= 35
    for node in places:
        match = WKT_POINT.match(node["defined_by"])
        assert match, node
        lon, lat = map(float, match.groups())
        assert -180 <= lon <= 180 and -90 <= lat <= 90
    for venue in _by_prefix("ausstage_venue_"):
        assert venue["type"] == "Place" and WKT_POINT.match(venue["defined_by"])


def test_events_people_and_venues_link_both_ways():
    for event in _by_prefix("ausstage_event_"):
        assert event["timespan"]["begin_of_the_begin"] and event["referred_to_by"]
        for venue in event["took_place_at"]:
            assert BY_ID[venue["id"]]["type"] == "Place"
            assert venue["defined_by"] == BY_ID[venue["id"]]["defined_by"]
        people = _ids(event["carried_out_by"])
        assert people or event["carried_out_by"]
        for iri in people:
            assert event["id"] in _ids(BY_ID[iri]["carried_out"])
    for person in _by_prefix("ausstage_person_"):
        assert person["carried_out"]
        for iri in _ids(person["carried_out"]):
            assert person["id"] in _ids(BY_ID[iri]["carried_out_by"])
    used_venues = {v["id"] for e in _by_prefix("ausstage_event_") for v in e["took_place_at"]}
    assert used_venues == {v["id"] for v in _by_prefix("ausstage_venue_")}


def test_artists_and_artworks_link_both_ways():
    for work in _by_prefix("daao_work_"):
        assert work["type"] == "HumanMadeObject" and work["made_of"]
        (artist_iri,) = _ids(work["produced_by"]["carried_out_by"])
        produced = {p["id"] for act in BY_ID[artist_iri]["carried_out"] for p in act["produced"]}
        assert work["id"] in produced
    for artist in _by_prefix("daao_artist_"):
        assert artist["born"]["took_place_at"] and artist["died"]["took_place_at"]
        for act in artist["carried_out"]:
            for ref in act["produced"]:
                assert artist["id"] in _ids(BY_ID[ref["id"]]["produced_by"]["carried_out_by"])
    assert sum("dimension" in w for w in _by_prefix("daao_work_")) >= 3
    assert sum("current_location" in w for w in _by_prefix("daao_work_")) >= 5


def test_images_are_credited_openly_licensed_commons_files():
    with_images = [rec for rec in RECORDS.values() if rec.get("representation")]
    assert len(with_images) >= 20
    assert len(with_images) < len(RECORDS), "keep some records without images for placeholder states"
    for rec in with_images:
        for visual in rec["representation"]:
            assert visual["type"] == "VisualItem"
            for digital in visual["digitally_shown_by"]:
                (url,) = _ids(digital["access_point"])
                assert url.startswith("https://upload.wikimedia.org/wikipedia/commons/")
                (credit,) = [s["content"] for s in digital["referred_to_by"]]
                assert "https://commons.wikimedia.org/wiki/File:" in credit
                assert any(f". {licence}." in credit for licence in OPEN_LICENCES), credit


def test_every_record_links_to_partner_site():
    for name, rec in RECORDS.items():
        urls = {url for s in rec["subject_of"] for d in s["digitally_carried_by"] for url in _ids(d["access_point"])}
        host = "www.ausstage.edu.au" if name.startswith("ausstage") else "www.daao.org.au"
        assert urls and all(url.startswith(f"https://{host}/") for url in urls)


def test_seed_publishes_everything_idempotently(tmp_path, seeded):
    results, service = seeded
    assert len(results) == len(RECORDS) and all(r.version_created for r in results)
    assert [r.type for r in results][: len(_by_prefix("ausstage_venue_"))] == ["Place"] * 6
    total, items = service.list(limit=100)
    assert total == len(RECORDS) and {i.id for i in items} == set(BY_ID)

    again = seed_demo.seed(tmp_path / "demo_data")
    assert not any(r.version_created for r in again)
    assert all(service.list_versions(iri).total == 1 for iri in BY_ID)


def test_demo_searches_return_expected_partners(seeded):
    _, service = seeded
    total, hits = service.search("Namatjira")
    assert total >= 2 and {h.partner for h in hits} == {"daao"}
    assert "https://www.daao.org.au/bio/albert-namatjira/" in {h.id for h in hits}
    total, hits = service.search("Godot")
    assert total >= 1 and {h.partner for h in hits} == {"ausstage"}
    assert "Activity" in {h.type for h in hits}
    assert service.search("Godot", partners=["daao"])[0] == 0
    _, events = service.search("Belvoir", types=["Activity"])
    assert events and {h.type for h in events} == {"Activity"}
    assert service.list(partner="daao", type="HumanMadeObject")[0] == len(_by_prefix("daao_work_"))


def test_seed_cli_prints_summary(tmp_path, capsys):
    assert seed_demo.main(["--data-dir", str(tmp_path / "d")]) == 0
    out = capsys.readouterr().out
    assert f"Seeded {len(RECORDS)} records" in out and "daao" in out and "ausstage" in out


def test_seed_rejects_invalid_source_without_publishing(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "good.json").write_text(json.dumps(RECORDS["daao_artist_namatjira.json"]))
    (source / "bad.json").write_text(json.dumps({"id": "https://www.daao.org.au/x", "type": "Person"}))
    with pytest.raises(SystemExit, match="bad.json"):
        seed_demo.seed(tmp_path / "d", source)
    assert not (tmp_path / "d").exists()
