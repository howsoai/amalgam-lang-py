"""Repository-wide pytest options."""
import os

# Importing amalgam binds the installed package before pytest's importlib mode imports test modules from the
# checkout, so tests run against the installed package and its compiled extension.
import amalgam  # noqa: F401  # imported only for its side effect on sys.modules
import pytest


def _env_flag(name: str) -> bool:
    """Return whether environment variable ``name`` holds a truthy value."""
    return os.environ.get(name, "").strip().lower() not in ("", "0", "false", "no", "off")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--require-c-extension``, on by default when the ``CI`` environment variable is truthy."""
    parser.addoption(
        "--require-c-extension",
        action="store_true",
        default=_env_flag("CI"),
        help="Fail, rather than skip, C-backend tests when the amalgam._api extension cannot be imported.",
    )
