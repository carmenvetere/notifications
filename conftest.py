"""Pytest config for the HA integration tests.

The pure-logic tests (tests/test_rule.py etc.) use stdlib unittest and need no
Home Assistant. The tests/test_ha_*.py modules use
pytest-homeassistant-custom-component, which this conftest wires up.
"""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load custom_components/ during tests."""
    yield
