import pytest


@pytest.mark.isolation
@pytest.mark.parametrize(
    "scenario",
    [
        "timeout_kills_process_tree",
        "network_denied",
        "filesystem_escape_denied",
        "resource_limits_and_cleanup",
    ],
)
def test_actual_isolation_backend(scenario):
    pytest.skip("No isolation backend is implemented or enabled; execution remains disabled")
