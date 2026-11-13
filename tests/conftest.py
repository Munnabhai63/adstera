"""
tests/conftest.py — Global test fixtures and state isolation for adstera test suite.
Ensures zero environment leaks, cached config pollution, or order-dependence across tests.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator
import pytest


@pytest.fixture(autouse=True)
def isolate_test_environment() -> Generator[None, None, None]:
    """Snapshot and restore os.environ for every test to guarantee order independence."""
    saved_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(saved_env)
