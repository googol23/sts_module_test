import pytest

from module_test import index_builder as index

ROOT = "cbmsoft/emu_test_module_arr/python/module_files/"
MODULE = "M0DL0B0001500B5"
GOOD = ROOT + f"L0DL000150/{MODULE}/pscan_files/module_test_{MODULE}.txt"
E16 = ROOT + "E16_STS/ME16_101_PB2/pscan_files/module_test_ME16_101_PB2.txt"
TEMP = ROOT + "ENC_vs_Temp/M3DR6B0000150A2/B-10_L-20/pscan_files/module_test_M3DR6B0000150A2.txt"


def test_valid_path():
    assert index.valid_path(GOOD, ROOT)
    assert not index.valid_path(E16, ROOT)
    assert not index.valid_path(TEMP, ROOT)
    assert not index.valid_path(GOOD.replace("module_test_", "module_test_wrong_"), ROOT)


@pytest.mark.parametrize("sync", [False, True])
def test_reconcile_index(tmp_path, monkeypatch, sync):
    db = str(tmp_path / "index.db")
    conn = index.init_db(db)
    index.upsert(conn, E16, 1, 10, "old")
    index.upsert(conn, TEMP, 1, 10, "old")
    index.upsert(conn, GOOD.replace(MODULE, "M0DL0B0001500B6"), 1, 10, "stale")
    conn.commit()
    conn.close()
    monkeypatch.setattr(index, "fetch_remote_files_batched", lambda *args: [
        (GOOD, 2, 20, "new"), (E16, 2, 20, "new"), (TEMP, 2, 20, "new")
    ])
    if sync:
        conn = index.init_db(db)
        assert index.sync_and_filter_from_db(conn, "host", ROOT) == [GOOD]
        conn.close()
    else:
        index.build_index("host", ROOT, db)
    conn = index.init_db(db)
    assert index.get_all_files(conn) == [GOOD]
    conn.close()


def test_failed_scan_preserves_index(tmp_path, monkeypatch):
    conn = index.init_db(str(tmp_path / "index.db"))
    index.upsert(conn, GOOD, 1, 10, "old")
    conn.commit()
    def fail(*args):
        raise RuntimeError("SSH failed")
    monkeypatch.setattr(index, "fetch_remote_files_batched", fail)
    with pytest.raises(RuntimeError):
        index.sync_and_filter_from_db(conn, "host", ROOT)
    assert index.get_all_files(conn) == [GOOD]
    conn.close()
