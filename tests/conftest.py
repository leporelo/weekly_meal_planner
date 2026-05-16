"""Shared test fixtures and configuration for the vegan meal planner test suite."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_config_path():
    """Return path to the project's config.yaml."""
    return Path(__file__).parent.parent / "config.yaml"


@pytest.fixture
def tmp_history_file(tmp_path):
    """Provide a temporary history file path for tests."""
    return tmp_path / "history.yaml"
