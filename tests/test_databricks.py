from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from databricks.sdk.service.sql import ResultData, StatementResponse

from api.databricks import DatabricksConfig, DatabricksRepository, WarehouseError

CONFIG = DatabricksConfig(
    host="https://example.databricks.com",
    token="test-secret",
    warehouse_id="warehouse",
    catalog="test_catalog",
)


def response(state="SUCCEEDED", rows=None, next_chunk=None):
    return StatementResponse.from_dict(
        dict(
            statement_id="statement",
            status=dict(state=state),
            manifest=dict(schema=dict(columns=[dict(name="number")])),
            result=dict(data_array=rows or [], next_chunk_index=next_chunk),
        )
    )


def warehouse(api, **kwargs):
    return DatabricksRepository(
        CONFIG, client=SimpleNamespace(statement_execution=api), sleep=lambda _: None, **kwargs
    )


def test_configuration_and_secret_repr():
    assert DatabricksRepository(DatabricksConfig()).status().status == "not_configured"
    assert DatabricksRepository(CONFIG).status().status == "unavailable"
    assert "test-secret" not in repr(CONFIG)
    assert CONFIG.table("raw_occupancy") == "`test_catalog`.`gymbuddy`.`raw_occupancy`"


@pytest.mark.parametrize(
    "identifier", ["", "table;DROP TABLE other", "catalog.with.dot", "bad`name", "42start"]
)
def test_rejects_unsafe_identifiers(identifier):
    with pytest.raises(ValueError, match="identifiers"):
        DatabricksConfig(catalog=identifier).table("raw_occupancy")


def test_pending_running_chunks_and_parameters():
    api = Mock()
    api.execute_statement.return_value = response("PENDING")
    api.get_statement.side_effect = [response("RUNNING"), response(rows=[["1"]], next_chunk=1)]
    api.get_statement_result_chunk_n.return_value = ResultData(data_array=[["2"]])
    repo = warehouse(api)
    assert repo.execute("SELECT :value", {"value": "x'; DROP TABLE nope"}) == [
        {"number": "1"},
        {"number": "2"},
    ]
    assert api.execute_statement.call_args.kwargs["statement"] == "SELECT :value"
    assert api.execute_statement.call_args.kwargs["parameters"][0].value == "x'; DROP TABLE nope"
    assert repo.status().status == "ready"
    api.get_statement_result_chunk_n.assert_called_once_with(
        statement_id="statement", chunk_index=1
    )


@pytest.mark.parametrize("state", ["FAILED", "CANCELED", "CLOSED"])
def test_failed_statement_with_http_success(state):
    api = Mock(execute_statement=Mock(return_value=response(state)))
    with pytest.raises(WarehouseError):
        warehouse(api).execute("SELECT 1")


def test_timeout_does_not_report_success_and_cancels():
    api = Mock(execute_statement=Mock(return_value=response("PENDING")))
    clock = iter([0, 0, 2, 2, 2])
    with pytest.raises(WarehouseError):
        warehouse(api, timeout=1, clock=lambda: next(clock)).execute("SELECT 1")
    api.cancel_execution.assert_called_once_with("statement")


def test_bounded_retry_and_sanitized_errors():
    class Transient(Exception):
        status_code = 503

    api = Mock(execute_statement=Mock(side_effect=Transient("test-secret")))
    with pytest.raises(WarehouseError) as exc:
        warehouse(api).execute("SELECT 1")
    assert "test-secret" not in str(exc.value)
    assert api.execute_statement.call_count == 3


def test_non_retryable_error_is_not_retried():
    api = Mock(execute_statement=Mock(side_effect=ValueError("test-secret")))
    with pytest.raises(WarehouseError):
        warehouse(api).execute("SELECT 1")
    assert api.execute_statement.call_count == 1


def test_truncated_results_are_rejected():
    result = response()
    result.manifest.truncated = True
    with pytest.raises(WarehouseError):
        warehouse(Mock(execute_statement=Mock(return_value=result))).execute("SELECT 1")


def test_initialization_ignores_semicolons_in_comments():
    repo = DatabricksRepository(CONFIG)
    repo.execute = Mock(return_value=[])
    repo.template = Mock(
        side_effect=[
            "-- comment; not SQL\nCREATE SCHEMA IF NOT EXISTS x; CREATE TABLE IF NOT EXISTS t (v INT);",
            "CREATE OR REPLACE VIEW v AS SELECT * FROM t;",
            "CREATE OR REPLACE TABLE gold AS SELECT * FROM v;",
        ]
    )
    repo.initialize()
    assert repo.execute.call_count == 4
    assert all("--" not in call.args[0] for call in repo.execute.call_args_list)


def test_forecast_template_contains_the_exact_configured_table():
    repo = DatabricksRepository(CONFIG)
    assert repo.config.table("occupancy_features") in repo.template("03_gold.sql")


def test_timestamp_read_preserves_microseconds_and_normalizes_offset():
    from api.databricks import timestamp

    assert (
        timestamp("2026-09-19 13:53:32.092818-04:00").isoformat()
        == "2026-09-19T17:53:32.092818+00:00"
    )
    repo = DatabricksRepository(CONFIG)
    repo.execute = Mock(return_value=[])
    repo.get_occupancy()
    repo.get_forecast()
    assert all("SSSSSSXXX" in call.args[0] for call in repo.execute.call_args_list)
