import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from api.databricks import DatabricksConfig
from collector.run import FACILITIES, append_observation
from collector.sync import state_path, synchronize


def observation(count=30):
    return dict(
        facility_id="mccomas",
        facility_name="McComas Hall",
        source_facility_id=FACILITIES["mccomas"][1],
        occupancy=count,
        remaining=100 - count,
        capacity=100,
        occupancy_pct=count,
        observed_at=datetime.now(timezone.utc).isoformat(),
        source_updated_at=None,
        source="vt_recsports",
    )


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "observations.csv"
    row = observation()
    append_observation(source, row)
    repo = Mock(
        config=DatabricksConfig(
            host="https://example.com",
            token="private",
            warehouse_id="warehouse",
            catalog="workspace",
        )
    )
    return source, repo, row


def test_success_checkpoint_and_no_duplicate_upload(setup):
    source, repo, row = setup
    synchronize(source, repo)
    synchronize(source, repo)
    repo.merge.assert_called_once()
    assert repo.merge.call_args.args[0][0]["observed_at"] == row["observed_at"]
    assert repo.merge.call_args.args[0][0]["source_updated_at"] is None
    assert repo.refresh_forecast.call_count == 1
    state = json.loads(state_path(source, repo).read_text())
    assert state["rows"] == 1 and not state["refresh_pending"]


def test_failed_merge_replays_without_losing_csv(setup):
    source, repo, _ = setup
    before = source.read_bytes()
    repo.merge.side_effect = RuntimeError("network")
    with pytest.raises(RuntimeError):
        synchronize(source, repo)
    assert json.loads(state_path(source, repo).read_text())["rows"] == 0
    assert source.read_bytes() == before
    repo.merge.side_effect = None
    synchronize(source, repo)
    assert repo.merge.call_count == 2


def test_failed_gold_refresh_retried_without_reupload(setup):
    source, repo, _ = setup
    repo.refresh_forecast.side_effect = RuntimeError("warehouse")
    with pytest.raises(RuntimeError):
        synchronize(source, repo)
    state = json.loads(state_path(source, repo).read_text())
    assert state["rows"] == 1 and state["refresh_pending"]
    repo.refresh_forecast.side_effect = None
    synchronize(source, repo)
    assert repo.merge.call_count == 1
    assert repo.refresh_forecast.call_count == 2


def test_malformed_row_is_logged_without_hiding_valid_data(setup, caplog):
    source, repo, row = setup
    append_observation(source, row | {"occupancy": "broken"})
    result = synchronize(source, repo)
    assert result == {"processed": 1, "rejected": 1, "checkpoint_rows": 2}
    assert "line 3" in caplog.text


def test_full_backfill_replays_and_bounded_batches(setup):
    source, repo, row = setup
    append_observation(source, row)
    synchronize(source, repo, batch_size=1)
    synchronize(source, repo, full=True, batch_size=1)
    assert repo.merge.call_count == 4  # The real adapter uses an idempotent MERGE.
    assert repo.refresh_forecast.call_count == 2


def test_corrupt_checkpoint_replays_csv(setup):
    source, repo, _ = setup
    state_path(source, repo).write_text("broken")
    assert synchronize(source, repo)["processed"] == 1


def test_overflow_row_does_not_block_valid_observations(setup):
    source, repo, row = setup
    append_observation(source, row | {"occupancy": str(2**64)})
    assert synchronize(source, repo)["rejected"] == 1
    assert len(repo.merge.call_args.args[0]) == 1


def test_extra_csv_columns_do_not_break_checkpoint_hash(setup):
    source, repo, _ = setup
    with source.open("a") as stream:
        stream.write("bad,row,with,too,many,values,in,this,line,for,the,header\n")
    result = synchronize(source, repo)
    assert result["processed"] == result["rejected"] == 1
