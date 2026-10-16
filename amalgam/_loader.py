"""Loading of the Amalgam shared library and lookup of its entry points, through ctypes."""
from __future__ import annotations

from ctypes import c_void_p, cast, CDLL
import os


def open_library(path: str | os.PathLike[str]) -> CDLL:
    """
    Load an Amalgam shared library.

    Parameters
    ----------
    path : str or os.PathLike
        Path of the library. Relative paths are resolved against the working directory.

    Returns
    -------
    CDLL
        The loaded library. ctypes never unloads it.

    Raises
    ------
    OSError
        The library cannot be loaded, or it does not export ``DeleteString``.
    """
    full_path = os.path.abspath(os.fspath(path))
    cdll = CDLL(full_path)
    if symbol_address(cdll, "DeleteString") is None:
        raise OSError(f"{full_path!r} is not an Amalgam library: DeleteString not found")
    return cdll


def symbol_address(cdll: CDLL, name: str) -> int | None:
    """Return the address of the entry point ``name``, or None if the library does not export it."""
    try:
        function = getattr(cdll, name)
    except AttributeError:
        return None
    return cast(function, c_void_p).value
