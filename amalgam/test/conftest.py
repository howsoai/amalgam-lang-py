"""Shared fixtures for tests that run against the real Amalgam library."""
from collections.abc import Callable, Iterator
import os
from pathlib import Path
import tracemalloc
from uuid import uuid4

import pytest

from amalgam._native import BACKEND_ENV_VAR, c_extension_available, load_native_library, selected_backend
from amalgam._types import NativeLibrary
from amalgam.api import Amalgam

TEST_DIR = Path(__file__).parent


def _peak_traced_bytes(function: Callable[[], object]) -> int:
    """Run ``function`` and return its peak Python-heap growth in bytes."""
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        baseline, _ = tracemalloc.get_traced_memory()
        function()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak - baseline


@pytest.fixture
def peak_traced_bytes() -> Callable[[Callable[[], object]], int]:
    """Measure the peak Python-heap growth of a callable."""
    return _peak_traced_bytes


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


def _skip_or_fail_without_c_extension(config: pytest.Config) -> None:
    """Skip the current test when the C extension is missing, or fail it when the extension is required."""
    if not c_extension_available():
        if config.getoption("require_c_extension") or selected_backend() == "c":
            pytest.fail("the amalgam._api C extension is required but cannot be imported")
        pytest.skip("the amalgam._api C extension is not built")


@pytest.fixture(params=["c", "ctypes"])
def backend(request: pytest.FixtureRequest) -> str:
    """Name of the native backend under test; a missing C extension skips its case unless it is required."""
    if request.param == "c":
        _skip_or_fail_without_c_extension(request.config)
    return request.param


@pytest.fixture
def c_extension(request: pytest.FixtureRequest) -> None:
    """Require the C extension: skip without it, or fail when the extension is required."""
    _skip_or_fail_without_c_extension(request.config)


@pytest.fixture
def amlg(amalgam_library_path: Path, backend: str, monkeypatch: pytest.MonkeyPatch) -> Amalgam:
    """An Amalgam instance using the backend under test, with tracing off."""
    monkeypatch.setenv(BACKEND_ENV_VAR, backend)
    return Amalgam(library_path=amalgam_library_path)


@pytest.fixture
def native_library(amalgam_library_path: Path, backend: str) -> NativeLibrary:
    """A native backend loaded from the test engine library."""
    return load_native_library(amalgam_library_path, backend)


@pytest.fixture
def new_native_handle(native_library: NativeLibrary) -> Iterator[Callable[[], str]]:
    """Factory for fresh entity handles; every handle it returns is destroyed at teardown."""
    handles: list[str] = []

    def make_handle() -> str:
        handle = str(uuid4())
        handles.append(handle)
        return handle

    yield make_handle
    for handle in handles:
        native_library.destroy_entity(handle)


@pytest.fixture
def entity(native_library: NativeLibrary, test_entity_file: Path, new_native_handle: Callable[[], str]) -> str:
    """Handle of a freshly loaded copy of the test entity, loaded through the native backend."""
    handle = new_native_handle()
    loaded, message, _, _ = native_library.load_entity(handle, str(test_entity_file), "", False, "", "", "", None)
    assert loaded, message
    return handle


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
