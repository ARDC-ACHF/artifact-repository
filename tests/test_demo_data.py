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
REVISIONS = {path.name: json.loads(path.read_text(encoding="utf-8"))
             for path in sorted((DEMO_DIR / "revisions").glob("*.json"))}
NAMATJIRA = "https://www.daao.org.au/bio/albert-namatjira/"
GODOT = "https://www.ausstage.edu.au/pages/event/demo-waiting-for-godot-2013"
RAMS = "https://www.daao.org.au/bio/tom-roberts/works/demo-shearing-the-rams/"
EXPECTED_VERSIONS = {NAMATJIRA: 2, GODOT: 2, RAMS: 3}


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
    assert again.revisions == [] and again.warnings == []
    assert {iri: service.list_versions(iri).total for iri in BY_ID} == {
        iri: EXPECTED_VERSIONS.get(iri, 1) for iri in BY_ID}


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


def test_list_endpoint_accepts_repeated_filters_like_search(seeded):
    from fastapi.testclient import TestClient

    from app.main import create_app

    _, service = seeded
    with TestClient(create_app(service=service, public_read=True, frontend_dir=None)) as client:
        both = client.get("/api/v1/artifacts", params=[("type", "Activity"), ("type", "Place"), ("limit", 100)])
        assert both.status_code == 200
        assert {r["type"] for r in both.json()["results"]} == {"Activity", "Place"}
        assert both.json()["total"] == len(_by_prefix("ausstage_event_")) + len(_by_prefix("ausstage_venue_"))
        single = client.get("/api/v1/artifacts", params={"partner": "daao", "type": "Person"}).json()
        assert single["total"] == len(_by_prefix("daao_artist_"))
        partners = client.get("/api/v1/artifacts", params=[("partner", "daao"), ("partner", "ausstage")]).json()
        assert partners["total"] == len(RECORDS)


@pytest.mark.parametrize("params", [
    [("partner", "")], [("type", "")], [("partner", ""), ("type", "")], [("partner", "  ")],
    [("type", ""), ("type", " ")], "partner=&type=",
])
def test_list_endpoint_blank_filters_mean_unfiltered(seeded, params):
    from fastapi.testclient import TestClient

    from app.main import create_app

    _, service = seeded
    with TestClient(create_app(service=service, public_read=True, frontend_dir=None)) as client:
        url = "/api/v1/artifacts" + (f"?{params}" if isinstance(params, str) else "")
        response = client.get(url, params=None if isinstance(params, str) else params)
    assert response.status_code == 200
    assert response.json()["total"] == len(RECORDS)


def test_list_endpoint_blank_values_mixed_with_real_filters_are_ignored(seeded):
    from fastapi.testclient import TestClient

    from app.main import create_app

    _, service = seeded
    with TestClient(create_app(service=service, public_read=True, frontend_dir=None)) as client:
        mixed = client.get("/api/v1/artifacts", params=[("partner", ""), ("partner", "daao"), ("type", " ")]).json()
        assert mixed["total"] == len(_by_prefix("daao_"))
        types = client.get("/api/v1/artifacts", params=[("type", "Place"), ("type", ""), ("partner", "")]).json()
        assert types["total"] == len(_by_prefix("ausstage_venue_"))
        assert client.get("/api/v1/artifacts", params={"partner": "nobody"}).json()["total"] == 0
    assert service.list(partner="", type=[""])[0] == len(RECORDS)
    assert service.list(partner=["", "daao"])[0] == len(_by_prefix("daao_"))


def test_seed_cli_prints_summary(tmp_path, capsys):
    assert seed_demo.main(["--data-dir", str(tmp_path / "d")]) == 0
    out = capsys.readouterr().out
    assert f"Seeded {len(RECORDS)} records" in out and "daao" in out and "ausstage" in out
    assert f"Applied {len(REVISIONS)} revisions to 3 records" in out


def test_revision_files_are_valid_and_share_base_ids():
    assert sorted(REVISIONS) == [
        "ausstage_event_godot_2013.v2.json", "daao_artist_namatjira.v2.json",
        "daao_work_shearing_the_rams.v2.json", "daao_work_shearing_the_rams.v3.json"]
    validator = LinkedArtValidator()
    for name, rec in REVISIONS.items():
        assert validator.validate(rec).valid, name
        assert rec["id"] == RECORDS[name.split(".v")[0] + ".json"]["id"]


def test_revisions_are_the_planned_curatorial_edits():
    def statements(rec):
        return {s["_label"]: s["content"] for s in rec["referred_to_by"]}

    nam1, nam2 = RECORDS["daao_artist_namatjira.json"], REVISIONS["daao_artist_namatjira.v2.json"]
    assert "Biography" not in statements(nam1) and "Battarbee" in statements(nam2)["Biography"]
    assert nam2["died"]["took_place_at"] != nam1["died"]["took_place_at"]
    assert "Hospital" in nam2["died"]["took_place_at"][0]["_label"]

    god1, god2 = RECORDS["ausstage_event_godot_2013.json"], REVISIONS["ausstage_event_godot_2013.v2.json"]
    assert len(_ids(god2["carried_out_by"]) - _ids(god1["carried_out_by"])) == 2
    assert _ids(god1["carried_out_by"]) < _ids(god2["carried_out_by"])
    assert "Photo credit" in statements(god2) and "Photo credit" not in statements(god1)

    rams1 = RECORDS["daao_work_shearing_the_rams.json"]
    rams2, rams3 = REVISIONS["daao_work_shearing_the_rams.v2.json"], REVISIONS["daao_work_shearing_the_rams.v3.json"]
    widths = [[d["value"] for d in r["dimension"] if d["classified_as"][0]["_label"] == "width"]
              for r in (rams1, rams2, rams3)]
    assert widths == [[138.3], [183.3], [183.3]]
    assert statements(rams2)["Dimensions"] == "122.4 × 183.3 cm" and "Felton Bequest" in statements(rams2)["Provenance"]
    assert rams1["_label"] == rams2["_label"] == "Sheering the Rams (Tom Roberts)"
    assert rams3["_label"] == "Shearing the Rams (Tom Roberts)"
    assert rams3["identified_by"][0]["content"] == "Shearing the Rams"
    assert {k: v for k, v in rams3.items() if k not in ("_label", "identified_by")} == {
        k: v for k, v in rams2.items() if k not in ("_label", "identified_by")}


def test_seeded_history_has_backdated_versions_and_latest_is_current(seeded):
    results, service = seeded
    assert len(results.revisions) == len(REVISIONS) and all(r.version_created for r in results.revisions)
    assert results.warnings == []
    expected_dates = {
        NAMATJIRA: ["2024-03-14", "2024-08-21"],
        GODOT: ["2024-03-14", "2024-08-21"],
        RAMS: ["2024-03-14", "2024-08-21", "2025-02-10"],
    }
    all_stamps = []
    for iri, dates in expected_dates.items():
        history = service.list_versions(iri)
        oldest_first = list(reversed(history.versions))
        assert [v.published_at[:10] for v in oldest_first] == dates
        assert [v.is_current for v in oldest_first] == [False] * (len(dates) - 1) + [True]
        all_stamps += [v.published_at for v in oldest_first]
    for iri in set(BY_ID) - set(expected_dates):
        all_stamps += [v.published_at for v in service.list_versions(iri).versions]
    assert len(set(all_stamps)) == len(all_stamps), "demo dates are unique per record and version"
    assert all(s.startswith(("2024-", "2025-")) for s in all_stamps)

    current = {iri: json.loads(service.get_raw(iri)) for iri in expected_dates}
    assert current[NAMATJIRA] == REVISIONS["daao_artist_namatjira.v2.json"]
    assert current[GODOT] == REVISIONS["ausstage_event_godot_2013.v2.json"]
    assert current[RAMS] == REVISIONS["daao_work_shearing_the_rams.v3.json"]
    oldest = service.list_versions(RAMS).versions[-1]
    assert json.loads(service.get_version_raw(RAMS, oldest.published_at)) == RECORDS["daao_work_shearing_the_rams.json"]


def test_search_indexes_revised_content(seeded):
    _, service = seeded
    assert GODOT in {h.id for h in service.search("Quast")[1]}
    assert NAMATJIRA in {h.id for h in service.search("Battarbee")[1]}
    assert RAMS in {h.id for h in service.search("Felton")[1]}
    assert {h.label for h in service.search("Rams")[1] if h.id == RAMS} == {"Shearing the Rams (Tom Roberts)"}
    assert service.search("Sheering")[0] == 0


def test_reset_reseed_gives_same_history(tmp_path):
    data_dir = tmp_path / "demo_data"
    first = seed_demo.seed(data_dir)
    (data_dir / "keep.txt").write_text("not repository data")
    again = seed_demo.seed(data_dir, reset=True)
    assert all(r.version_created for r in again) and len(again.revisions) == len(REVISIONS)
    assert [r.published_at for r in again] == [r.published_at for r in first]
    assert [r.published_at for r in again.revisions] == [r.published_at for r in first.revisions]
    assert (data_dir / "keep.txt").exists()
    index = FtsIndex(data_dir / "index.sqlite3")
    try:
        service = RepositoryService(FilesystemStore(data_dir / "artifacts"), index)
        assert {iri: service.list_versions(iri).total for iri in BY_ID} == {
            iri: EXPECTED_VERSIONS.get(iri, 1) for iri in BY_ID}
    finally:
        index.close()


def test_stale_data_without_reset_warns(tmp_path):
    data_dir = tmp_path / "demo_data"
    seed_demo.seed(data_dir)
    index = FtsIndex(data_dir / "index.sqlite3")
    try:
        service = RepositoryService(FilesystemStore(data_dir / "artifacts"), index)
        stale = dict(REVISIONS["daao_work_shearing_the_rams.v3.json"], _label="Edited live today")
        assert service.publish(stale).published_at > "2025-12"
    finally:
        index.close()
    result = seed_demo.seed(data_dir)
    assert any("daao_work_shearing_the_rams" in w and "--reset" in w for w in result.warnings)
    assert not seed_demo.seed(data_dir, reset=True).warnings


def test_invalid_revision_blocks_reset(tmp_path):
    source = tmp_path / "src"
    (source / "revisions").mkdir(parents=True)
    (source / "daao_artist_namatjira.json").write_text(json.dumps(RECORDS["daao_artist_namatjira.json"]))
    wrong = dict(REVISIONS["daao_artist_namatjira.v2.json"], id="https://www.daao.org.au/bio/someone-else/")
    (source / "revisions" / "daao_artist_namatjira.v2.json").write_text(json.dumps(wrong))
    data_dir = tmp_path / "d"
    seed_demo.seed(data_dir, DEMO_DIR)
    with pytest.raises(SystemExit, match="does not match base id"):
        seed_demo.seed(data_dir, source, reset=True)
    assert (data_dir / "artifacts").exists() and (data_dir / "index.sqlite3").exists()


def test_seed_clock_patch_does_not_leak(tmp_path):
    from datetime import datetime, timezone

    import app.service as service_module

    original = service_module._now_published_at
    seed_demo.seed(tmp_path / "demo_data")
    assert service_module._now_published_at is original
    index = FtsIndex(tmp_path / "live" / "index.sqlite3")
    try:
        service = RepositoryService(FilesystemStore(tmp_path / "live" / "artifacts"), index)
        stamp = service.publish(RECORDS["daao_artist_namatjira.json"]).published_at
    finally:
        index.close()
    assert stamp.startswith(str(datetime.now(timezone.utc).year))


def test_seed_rejects_invalid_source_without_publishing(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "good.json").write_text(json.dumps(RECORDS["daao_artist_namatjira.json"]))
    (source / "bad.json").write_text(json.dumps({"id": "https://www.daao.org.au/x", "type": "Person"}))
    with pytest.raises(SystemExit, match="bad.json"):
        seed_demo.seed(tmp_path / "d", source)
    assert not (tmp_path / "d").exists()
