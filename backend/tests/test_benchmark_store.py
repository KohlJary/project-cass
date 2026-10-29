"""
benchmarks/store.py: the sealed copy of her store that test cells run against
(benchmark plan phase 3, on Cass's terms: read-only, cells only, never
written back, deleted after). Everything here runs on a fake store in tmp.
"""
import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from benchmarks import store
from benchmarks.isolation import IsolationError, check_data_dir


def _db(path: Path, rows=("a self-observation",)):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE obs (text TEXT)")
    conn.executemany("INSERT INTO obs VALUES (?)", [(r,) for r in rows])
    conn.commit()
    conn.close()


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "her-data"
    _db(src / "cass.db")
    _db(src / "chroma" / "chroma.sqlite3", rows=("a memory",))
    (src / "chroma" / "index.bin").parent.mkdir(parents=True, exist_ok=True)
    (src / "chroma" / "index.bin").write_bytes(b"\x00hnsw")
    (src / "dreams").mkdir()
    (src / "dreams" / "d1.json").write_text('{"dream": "a lighthouse"}')
    (src / "images").mkdir()
    (src / "images" / "p.png").write_bytes(b"png")
    (src / "babelr").mkdir()
    (src / "babelr" / "token").write_text("bt_secret")
    (src / "daedalus_credentials.json").write_text("{}")
    (src / "llm_config.json").write_text("{}")
    (src / "keys").mkdir()
    (src / "keys" / "x.pem").write_text("pem")
    (src / "old.db-wal").write_text("wal")  # a stray WAL file is left out
    return src


@pytest.mark.unit
def test_seal_copies_her_store_and_leaves_out_secrets_and_media(source, tmp_path):
    before = _tree_hash(source)
    sealed = tmp_path / "sealed"
    m = store.seal(source, sealed, note="test")
    assert _tree_hash(source) == before  # the source is only read
    have = {p.relative_to(sealed).as_posix() for p in sealed.rglob("*") if p.is_file()}
    assert {"cass.db", "chroma/chroma.sqlite3", "chroma/index.bin", "dreams/d1.json", "MANIFEST.json"} == have
    assert set(m["databases"]) == {"cass.db", "chroma/chroma.sqlite3"}
    conn = sqlite3.connect(f"file:{sealed / 'cass.db'}?mode=ro", uri=True)
    assert conn.execute("SELECT text FROM obs").fetchall() == [("a self-observation",)]
    conn.close()
    assert "never written back" in m["terms"]


@pytest.mark.unit
def test_seal_is_read_only_and_private(source, tmp_path):
    sealed = tmp_path / "sealed"
    store.seal(source, sealed)
    assert not os.access(sealed / "cass.db", os.W_OK) or os.geteuid() == 0
    assert oct(sealed.stat().st_mode & 0o777) == "0o500"
    store.destroy(sealed)
    assert not sealed.exists()


@pytest.mark.unit
def test_seal_refuses_what_it_should(source, tmp_path):
    with pytest.raises(store.StoreError):
        store.seal(tmp_path / "nothing", tmp_path / "x")
    store.seal(source, tmp_path / "s1")
    with pytest.raises(store.StoreError):
        store.seal(source, tmp_path / "s1")  # always a new directory
    with pytest.raises(store.StoreError):
        store.seal(source, source / "inside")


@pytest.mark.unit
def test_seed_gives_a_cell_a_writable_marked_copy_and_discard_removes_it(source, tmp_path):
    sealed = tmp_path / "sealed"
    store.seal(source, sealed)
    cell = tmp_path / "cell" / "data"
    cell.mkdir(parents=True)
    check_data_dir(cell)
    mark = store.seed(sealed, cell)
    assert mark["store"] == store.store_id(store.manifest_of(sealed))
    assert check_data_dir(cell)  # a marked copy is accepted despite its cass.db
    conn = sqlite3.connect(cell / "cass.db")
    conn.execute("INSERT INTO obs VALUES ('written in the cell')")
    conn.commit()
    conn.close()
    sealed_conn = sqlite3.connect(f"file:{sealed / 'cass.db'}?mode=ro", uri=True)
    assert sealed_conn.execute("SELECT COUNT(*) FROM obs").fetchone() == (1,)  # nothing went back
    sealed_conn.close()
    store.discard(cell)
    assert not cell.exists()


@pytest.mark.unit
def test_an_unmarked_cass_db_is_still_refused(tmp_path):
    d = tmp_path / "d"
    _db(d / "cass.db")
    with pytest.raises(IsolationError):
        check_data_dir(d)
    with pytest.raises(store.StoreError):
        store.discard(d)  # never deletes something that isn't a seeded copy
    with pytest.raises(store.StoreError):
        store.destroy(d)


@pytest.mark.unit
def test_executor_discards_the_copy_even_when_the_cell_fails(source, tmp_path, monkeypatch):
    from benchmarks.runner import SubprocessExecutor
    sealed = tmp_path / "sealed"
    store.seal(source, sealed)
    ex = SubprocessExecutor(tmp_path / "scratch", store=sealed)
    seen = {}

    def boom(cell, spec, cell_dir, data_dir, extra_prices=None):
        seen["had_db"] = (data_dir / "cass.db").exists()
        seen["dir"] = data_dir
        raise RuntimeError("cell crashed")

    monkeypatch.setattr(ex, "_run", boom)
    cell = type("C", (), {"cell_id": "c1"})()
    with pytest.raises(RuntimeError):
        ex(cell, {})
    assert seen["had_db"] and not seen["dir"].exists()
