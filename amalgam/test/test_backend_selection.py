"""Tests for choosing between the C and ctypes backends."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from amalgam._ctypes_library import CtypesLibrary
from amalgam._native import BACKEND_ENV_VAR, c_extension_available, load_native_library, selected_backend


def test_ctypes_backend_by_name(amalgam_library_path: Path) -> None:
    """Asking for ctypes always returns the ctypes backend."""
    assert isinstance(load_native_library(amalgam_library_path, "ctypes"), CtypesLibrary)


def test_environment_variable_selects_backend(
    amalgam_library_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backend environment variable is honored when no backend is passed."""
    monkeypatch.setenv(BACKEND_ENV_VAR, "ctypes")
    assert isinstance(load_native_library(amalgam_library_path), CtypesLibrary)


@pytest.mark.parametrize("value", ["", "auto", " AUTO "])
def test_auto_prefers_the_extension(
    amalgam_library_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Auto mode uses the C extension when it is importable and ctypes otherwise."""
    monkeypatch.setenv(BACKEND_ENV_VAR, value)
    library = load_native_library(amalgam_library_path)
    assert isinstance(library, CtypesLibrary) is (not c_extension_available())


def test_c_backend_requires_the_extension(amalgam_library_path: Path) -> None:
    """Asking for the C backend without the extension raises ImportError."""
    if c_extension_available():
        assert not isinstance(load_native_library(amalgam_library_path, "c"), CtypesLibrary)
    else:
        with pytest.raises(ImportError):
            load_native_library(amalgam_library_path, "c")


def test_unknown_backend_raises(tmp_path: Path) -> None:
    """An unrecognized backend name raises ValueError before anything is loaded."""
    with pytest.raises(ValueError, match=BACKEND_ENV_VAR):
        load_native_library(tmp_path / "not-loaded.so", "rust")


def test_selected_backend_normalizes() -> None:
    """Backend names are case- and whitespace-insensitive."""
    assert selected_backend(" C ") == "c"
    assert selected_backend("") == "auto"


def test_backend_fixture_probe(backend: str) -> None:
    """Uses the backend fixture; also run in a subprocess by the next test."""
    assert backend in ("c", "ctypes")


@pytest.mark.parametrize("extra_args, extra_env, expected", [
    ([], {"CI": ""}, "1 passed, 1 skipped"),
    (["--require-c-extension"], {"CI": ""}, "1 passed, 1 error"),
    ([], {"CI": "true"}, "1 passed, 1 error"),
    ([], {"CI": "", BACKEND_ENV_VAR: "c"}, "1 passed, 1 error"),
])
def test_required_c_extension_fails_instead_of_skipping(
    extra_args: list[str], extra_env: dict[str, str], expected: str, tmp_path: Path
) -> None:
    """The c backend case skips without the extension unless the C extension is required, which errors it."""
    # A plugin loaded with -p runs before any conftest or test module imports amalgam._native, so the
    # extension import fails in the subprocess whether or not the extension is built.
    (tmp_path / "block_api.py").write_text('import sys\n\nsys.modules["amalgam._api"] = None\n')
    env = {key: value for key, value in os.environ.items() if key != BACKEND_ENV_VAR}
    env["PYTHONPATH"] = os.pathsep.join(path for path in (str(tmp_path), env.get("PYTHONPATH")) if path)
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "block_api", *extra_args,
         f"{__file__}::test_backend_fixture_probe"],
        env=env, capture_output=True, text=True, check=False)
    assert expected in result.stdout, result.stdout
    if "error" in expected:
        assert "the amalgam._api C extension is required but cannot be imported" in result.stdout, result.stdout
