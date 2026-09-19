import subprocess
from unittest.mock import Mock

import pytest

from scripts.serve import commands, stop_children


@pytest.mark.parametrize("port", [0, -1, 65536, "invalid"])
def test_rejects_invalid_port(port):
    with pytest.raises(ValueError):
        commands(port)


def test_server_uses_one_api_worker_and_one_collector():
    api, collector = commands(10000)
    assert api[-2:] == ["--workers", "1"]
    assert api[api.index("--host") + 1] == "0.0.0.0"
    assert api[api.index("--port") + 1] == "10000"
    assert collector[-2:] == ["-m", "collector"]
    assert "--reload" not in api


def test_shutdown_terminates_running_children_and_reaps_exited_children():
    running = Mock(poll=Mock(return_value=None))
    exited = Mock(poll=Mock(return_value=1))
    stop_children([running, exited])
    running.terminate.assert_called_once()
    exited.terminate.assert_not_called()
    assert running.wait.called and exited.wait.called


def test_shutdown_kills_child_that_does_not_exit():
    child = Mock(
        poll=Mock(return_value=None),
        wait=Mock(side_effect=[subprocess.TimeoutExpired("test", 15), 0]),
    )
    stop_children([child])
    child.kill.assert_called_once()
    assert child.wait.call_count == 2
