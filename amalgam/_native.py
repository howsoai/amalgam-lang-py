"""Selection of the backend that calls into the Amalgam shared library."""
from __future__ import annotations

import os

from amalgam._ctypes_library import CtypesLibrary
from amalgam._loader import open_library, symbol_address
from amalgam._types import NativeLibrary

try:
    from amalgam import _api
except ImportError:
    _api = None

BACKEND_ENV_VAR = "AMALGAM_PY_BACKEND"
"""Environment variable naming the backend: ``auto`` (default), ``c``, or ``ctypes``."""

_BACKENDS = ("auto", "c", "ctypes")


def c_extension_available() -> bool:
    """Return whether the ``amalgam._api`` C extension imported."""
    return _api is not None


def selected_backend(backend: str | None = None) -> str:
    """Return the normalized backend name from ``backend`` or the environment, defaulting to ``auto``."""
    raw = backend if backend is not None else os.environ.get(BACKEND_ENV_VAR, "")
    choice = raw.strip().lower() or "auto"
    if choice not in _BACKENDS:
        raise ValueError(f'Unknown {BACKEND_ENV_VAR} value "{choice}"; expected "auto", "c", or "ctypes".')
    return choice


def load_native_library(path: str | os.PathLike[str], backend: str | None = None) -> NativeLibrary:
    """
    Load the Amalgam shared library with the selected backend.

    Parameters
    ----------
    path : str or os.PathLike
        Path of the Amalgam shared library. Relative paths are resolved against the working directory.
    backend : str, optional
        ``"auto"``, ``"c"``, or ``"ctypes"``. Defaults to the ``AMALGAM_PY_BACKEND`` environment variable, and
        to ``"auto"`` when that is unset or empty. ``"auto"`` uses the C extension when it is available.

    Returns
    -------
    NativeLibrary
        The loaded backend.

    Raises
    ------
    ImportError
        ``"c"`` was requested and the C extension is not available.
    ValueError
        The backend name is not recognized.
    OSError
        The library cannot be loaded or is not an Amalgam library.
    """
    choice = selected_backend(backend)
    if choice == "c" and _api is None:
        raise ImportError("The amalgam._api C extension is not available in this installation.")
    cdll = open_library(path)
    if choice == "ctypes" or _api is None:
        return CtypesLibrary(cdll)
    return _api.Library(cdll, tuple(symbol_address(cdll, name) for name in _api.ENTRY_POINTS))
