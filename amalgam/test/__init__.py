import os
from pathlib import Path
import platform


def get_test_options():
    """
    Simply parses the ENV variable 'TEST_OPTIONS' into a list, if possible
    and returns it. This will be used with `pytest.skipif` to conditionally
    test some additional tests.

    Returns
    -------
    list[str]
    """
    try:
        options = os.getenv('TEST_OPTIONS').split(',')
    except (AttributeError, ValueError):
        options = []
    return options


if platform.system() == 'Windows':
    amalgam_binary = 'amalgam.dll'
elif platform.system() == 'Darwin':
    amalgam_binary = 'amalgam.dylib'
else:
    amalgam_binary = 'amalgam.so'

amalgam_path = Path(Path.home(), '.howso', 'lib', 'dev', 'amlg', 'lib', amalgam_binary)
