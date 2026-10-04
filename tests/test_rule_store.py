import json
import os

from src.app import RuleStore


def test_reload_on_change_and_keep_last_good(tmp_path):
    path = tmp_path / "config.json"
    store = RuleStore(path)  # creates defaults
    assert len(store()) == 1
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    os.utime(path, ns=(1, 1))
    store.reload_if_changed()
    assert store() == ()
    path.write_text("{", encoding="utf-8")
    os.utime(path, ns=(2, 2))
    store.reload_if_changed()
    assert store() == ()  # broken file keeps the previous (empty) rules


def test_call_does_no_file_io(tmp_path, monkeypatch):
    store = RuleStore(tmp_path / "config.json")
    monkeypatch.setattr(store, "reload_if_changed", lambda: (_ for _ in ()).throw(AssertionError))
    assert len(store()) == 1
