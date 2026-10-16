"""Tests for loading the Amalgam library and resolving its entry points."""
import _ctypes
from pathlib import Path

import pytest

from amalgam._loader import open_library, symbol_address


def test_missing_library_raises_oserror(tmp_path: Path) -> None:
    """Loading a path that does not exist raises OSError."""
    with pytest.raises(OSError):
        open_library(tmp_path / "amalgam-missing.so")


def test_non_amalgam_library_raises_oserror() -> None:
    """Loading a shared library without the Amalgam entry points raises OSError."""
    other_library = getattr(_ctypes, "__file__", None)
    if other_library is None:
        pytest.skip("_ctypes is built into this interpreter")
    with pytest.raises(OSError, match="DeleteString"):
        open_library(other_library)


def test_relative_path_is_resolved(amalgam_library_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A path relative to the working directory loads."""
    monkeypatch.chdir(amalgam_library_path.parent)
    assert symbol_address(open_library(amalgam_library_path.name), "GetVersionString")


def test_symbol_address(amalgam_library_path: Path) -> None:
    """Exported entry points have integer addresses; unknown names have none."""
    cdll = open_library(amalgam_library_path)
    address = symbol_address(cdll, "ExecuteEntityJsonPtr")
    assert isinstance(address, int) and address != 0
    assert symbol_address(cdll, "NoSuchAmalgamEntryPoint") is None
