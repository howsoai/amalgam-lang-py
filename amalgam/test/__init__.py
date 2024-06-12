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
