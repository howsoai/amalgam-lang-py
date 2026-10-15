"""
Remove the ``[[tool.setuptools.ext-modules]]`` table from a pyproject.toml.

The release workflow runs this in its own checkout before building the ``py3-none-any`` wheel, which uses the
ctypes backend.
"""
from pathlib import Path
import re
import sys
import tomllib

_EXT_MODULES_TABLE = re.compile(r"(?ms)^\[\[tool\.setuptools\.ext-modules\]\]\n.*?(?=^\[|\Z)")


def remove_extension_modules(text: str) -> str:
    """Return ``text`` without its ext-modules table, verifying the result parses without one."""
    result = _EXT_MODULES_TABLE.sub("", text)
    if "ext-modules" in tomllib.loads(result).get("tool", {}).get("setuptools", {}):
        raise ValueError("pyproject.toml still declares ext-modules")
    return result


def main(argv: list[str]) -> None:
    """Rewrite the pyproject.toml named on the command line in place."""
    path = Path(argv[1])
    path.write_text(remove_extension_modules(path.read_text()))


if __name__ == "__main__":
    main(sys.argv)
