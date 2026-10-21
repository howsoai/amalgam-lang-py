"""Tests specific to the amalgam._api C extension."""
import gc
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import weakref

import pytest

from amalgam._loader import open_library, symbol_address
from amalgam._native import load_native_library

try:
    from amalgam import _api
except ImportError:
    _api = None


@pytest.fixture
def api_module(c_extension: None) -> object:
    """The extension module; a missing extension skips the test unless it is required."""
    return _api


def test_extension_uses_the_stable_abi(api_module: object) -> None:
    """The built extension is an abi3 module."""
    spec = importlib.util.find_spec("amalgam._api")
    assert spec is not None and spec.origin is not None
    name = Path(spec.origin).name
    assert ".abi3" in name or name.endswith(".pyd")


def test_entry_points_cover_the_engine_api(api_module: object) -> None:
    """ENTRY_POINTS names each wrapped entry point once, including DeleteString."""
    assert "DeleteString" in _api.ENTRY_POINTS
    assert "ExecuteEntityJsonPtr" in _api.ENTRY_POINTS
    assert len(set(_api.ENTRY_POINTS)) == len(_api.ENTRY_POINTS)


def test_library_keeps_its_owner_alive(api_module: object, amalgam_library_path: Path) -> None:
    """A Library holds a reference to the CDLL that owns the loaded library."""
    cdll = open_library(amalgam_library_path)
    owner = weakref.ref(cdll)
    library = _api.Library(cdll, tuple(symbol_address(cdll, name) for name in _api.ENTRY_POINTS))
    del cdll
    gc.collect()
    assert owner() is not None
    assert library.get_version_string()


def test_library_validates_addresses(api_module: object, amalgam_library_path: Path) -> None:
    """A wrong-length address tuple or a missing DeleteString is rejected."""
    cdll = open_library(amalgam_library_path)
    addresses = [symbol_address(cdll, name) for name in _api.ENTRY_POINTS]
    with pytest.raises(ValueError):
        _api.Library(cdll, tuple(addresses[:-1]))
    addresses[_api.ENTRY_POINTS.index("DeleteString")] = None
    with pytest.raises(ValueError, match="DeleteString"):
        _api.Library(cdll, tuple(addresses))


def test_missing_entry_point_raises_attribute_error(api_module: object, amalgam_library_path: Path) -> None:
    """An entry point the library does not export fails when called."""
    cdll = open_library(amalgam_library_path)
    addresses = [symbol_address(cdll, name) for name in _api.ENTRY_POINTS]
    addresses[_api.ENTRY_POINTS.index("GetVersionString")] = None
    library = _api.Library(cdll, tuple(addresses))
    with pytest.raises(AttributeError, match="GetVersionString"):
        library.get_version_string()


def test_libraries_are_independent(api_module: object, amalgam_library_path: Path) -> None:
    """Two Library objects for the same path each work on their own."""
    first = load_native_library(amalgam_library_path, "c")
    second = load_native_library(amalgam_library_path, "c")
    assert first is not second
    del first
    assert second.get_version_string()


def test_import_keeps_the_gil_disabled(api_module: object) -> None:
    """On a free-threaded interpreter, importing the extension does not turn the GIL back on."""
    if not sysconfig.get_config_var("Py_GIL_DISABLED"):
        pytest.skip("not a free-threaded interpreter")
    env = {key: value for key, value in os.environ.items() if key != "PYTHON_GIL"}
    result = subprocess.run(
        [sys.executable, "-c", "import sys, amalgam._api; sys.exit(1 if sys._is_gil_enabled() else 0)"],
        env=env, check=False)
    assert result.returncode == 0
