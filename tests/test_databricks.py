import pytest

from api.databricks import DatabricksConfig, DatabricksRepository


def test_configuration_is_explicitly_not_implemented_until_connected():
    assert DatabricksRepository(DatabricksConfig()).status().model_dump() == {
        "configured": False,
        "status": "not_configured",
    }
    config = DatabricksConfig(
        host="https://example.databricks.com",
        token="test-secret",
        warehouse_id="warehouse",
        catalog="test_catalog",
    )
    assert DatabricksRepository(config).status().model_dump() == {
        "configured": True,
        "status": "not_implemented",
    }
    assert "test-secret" not in repr(config)
    assert config.table("raw_occupancy") == "`test_catalog`.`gymbuddy`.`raw_occupancy`"


@pytest.mark.parametrize(
    "identifier", ["", "table;DROP TABLE other", "catalog.with.dot", "bad`name", "42start"]
)
def test_rejects_unsafe_identifiers(identifier):
    with pytest.raises(ValueError, match="identifiers"):
        DatabricksConfig(catalog=identifier).table("raw_occupancy")


def test_backfill_boundary_does_not_mutate_unconnected_data(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("test observation\n")
    with pytest.raises(NotImplementedError):
        DatabricksRepository(DatabricksConfig()).backfill_observations(source)
    assert source.read_text() == "test observation\n"
