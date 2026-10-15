"""Shared fixtures for tests that run against the real Amalgam library."""
from collections.abc import Callable, Iterator
import os
from pathlib import Path
from uuid import uuid4

import pytest

from amalgam.api import Amalgam

TEST_DIR = Path(__file__).parent


@pytest.fixture(scope="session")
def amalgam_library_path() -> Path:
    """Path of the engine library under ``amalgam/lib``, honoring ``AMALGAM_LIBRARY_POSTFIX``."""
    postfix = os.getenv("AMALGAM_LIBRARY_POSTFIX", "-st")
    try:
        path, _ = Amalgam._get_library_path(library_postfix=postfix)
    except (FileNotFoundError, RuntimeError) as err:
        pytest.skip(f"Amalgam library is not installed: {err}")
    return path


@pytest.fixture(scope="session")
def test_entity_file() -> Path:
    """Path of the Amalgam entity used by the tests."""
    return TEST_DIR / "test.amlg"


@pytest.fixture
def amlg(amalgam_library_path: Path) -> Amalgam:
    """An Amalgam instance on the test engine library, with tracing off."""
    return Amalgam(library_path=amalgam_library_path)


@pytest.fixture
def new_handle(amlg: Amalgam) -> Iterator[Callable[[], str]]:
    """Factory for fresh entity handles; every handle it returns is destroyed at teardown."""
    handles: list[str] = []

    def make_handle() -> str:
        handle = str(uuid4())
        handles.append(handle)
        return handle

    yield make_handle
    for handle in handles:
        amlg.destroy_entity(handle)


@pytest.fixture
def loaded_entity(amlg: Amalgam, test_entity_file: Path, new_handle: Callable[[], str]) -> str:
    """Handle of a freshly loaded copy of the test entity."""
    handle = new_handle()
    status = amlg.load_entity(handle, str(test_entity_file))
    assert status.loaded, status.message
    return handle
