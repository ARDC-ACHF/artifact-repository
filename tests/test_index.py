import sqlite3

import pytest

from app.index import FtsIndex


@pytest.fixture
def index(tmp_path):
    index = FtsIndex(tmp_path / "index.sqlite")
    yield index
    index.close()


def put(index, iri, partner="nga", type="HumanMadeObject", text="blue painting"):
    index.upsert(iri, partner=partner, type=type, label=None, body_text=text)


def test_filters_paging_and_bound_parameters(index):
    put(index, "a")
    put(index, "b")
    put(index, "c", partner="ausstage", type="Activity")
    assert index.search("paint", types=["HumanMadeObject"], partners=["nga"])[0] == 2
    total, rows = index.list(limit=1, offset=1)
    assert total == 3 and [r.iri for r in rows] == ["b"]
    total, rows = index.search("blue", limit=1, offset=1)
    assert total == 3 and len(rows) == 1
    assert index.list(offset=99) == (3, [])
    injection = "x') OR 1=1 --"
    assert index.list(types=[injection])[0] == 0
    assert index.search("blue", partners=[injection])[0] == 0
    put(index, injection, partner=injection, type=injection)
    assert index.list(types=[injection], partners=[injection])[0] == 1
    index.delete(injection)
    assert index.count() == 3
    assert index.health()["ok"] is True
    index.clear()
    assert index.count() == 0


@pytest.mark.parametrize("query", ["", "\"", "!!!", "blue:painting", "blue OR painting", "-blue", "blue*", "'; DROP TABLE artifacts; --"])
def test_punctuation(index, query):
    put(index, "a")
    total, rows = index.search(query)
    assert 0 <= total <= 1
    assert index.count() == 1


def test_upsert_real_transaction_rollback(index):
    put(index, "a", text="original")
    # SQLite rejects this binding after DELETE has already executed.
    with pytest.raises(sqlite3.ProgrammingError):
        put(index, "a", text=object())
    assert not index._conn.in_transaction
    assert index.search("original")[0] == 1
    assert index.count() == 1
    put(index, "a", text="replacement")
    assert index.search("original")[0] == 0
    assert index.search("replacement")[0] == 1


def test_close(index):
    index.close()
    assert index.health()["ok"] is False