"""Markers local to the brain acceptance suite."""
import pytest


_LIVE_TESTS = {
    "test_yaishka_parity_04_live_vision_critique",
}


def pytest_collection_modifyitems(items):
    """Keep real-provider checks explicit and out of deterministic CI."""
    for item in items:
        if item.name in _LIVE_TESTS:
            item.add_marker(pytest.mark.live)
