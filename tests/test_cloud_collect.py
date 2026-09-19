import csv
from unittest.mock import Mock

from collector.run import append_observation
from scripts.cloud_collect import run
from tests.test_sync import observation


def test_cloud_outbox_only_clears_after_confirmed_upload(tmp_path, monkeypatch):
    path = tmp_path / "raw.csv"
    append_observation(path, observation())
    monkeypatch.setattr("scripts.cloud_collect.collect_once", lambda *_a, **_k: (0, 0))
    sync = Mock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr("scripts.cloud_collect.synchronize", sync)
    assert run(path, warehouse=Mock()) == 1
    assert len(list(csv.DictReader(path.open()))) == 1
    sync.side_effect = None
    sync.return_value = {"rejected": 0}
    assert run(path, warehouse=Mock()) == 0
    assert list(csv.DictReader(path.open())) == []


def test_rejected_cloud_rows_are_preserved(tmp_path, monkeypatch):
    path = tmp_path / "raw.csv"
    append_observation(path, observation())
    monkeypatch.setattr("scripts.cloud_collect.collect_once", lambda *_a, **_k: (0, 0))
    monkeypatch.setattr("scripts.cloud_collect.synchronize", lambda *_: {"rejected": 1})
    assert run(path, warehouse=Mock()) == 1
    assert len(list(csv.DictReader(path.open()))) == 1
