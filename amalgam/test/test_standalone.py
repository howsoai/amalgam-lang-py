import datetime as dt
import logging
import json
from uuid import uuid4
import os
import random

import pytest

import amalgam
from amalgam.api import Amalgam

_logger = logging.getLogger(__name__)

amlg_postfix = os.getenv('AMALGAM_LIBRARY_POSTFIX', '-st')
amlg_path, _ = Amalgam._get_library_path(library_postfix=amlg_postfix)
_logger.debug(f'Amalgam path: ', {amlg_path})
is_amalgam_installed = amlg_path.exists()


@pytest.fixture
def amalgam_lib():
    return Amalgam(library_path=amlg_path, gc_interval=1000,
                   execution_trace_dir='./traces/', trace=True)


@pytest.mark.skipif(not is_amalgam_installed, reason="Amalgam is not installed")
def test_bulk_operations(amalgam_lib):
    amalgam_lib.reset_trace('test_bulk_operations.trace')
    assert bulk_operations(amalgam_lib)


@pytest.mark.skipif(not is_amalgam_installed, reason="Amalgam not installed")
def test_get_version(amalgam_lib):
    amalgam_lib.reset_trace('test_get_version.trace')
    assert amalgam_lib.get_version_string()


@pytest.mark.skipif(not is_amalgam_installed, reason="Amalgam not installed")
def test_get_concurrency_type(amalgam_lib):
    amalgam_lib.reset_trace('test_get_version.trace')
    assert amalgam_lib.get_concurrency_type_string()


@pytest.mark.skipif(not is_amalgam_installed, reason="Amalgam not installed")
def test_is_sbf_datastore_enabled(amalgam_lib):
    assert amalgam_lib.is_sbf_datastore_enabled()


def bulk_operations(amlg):
    """
    Executes the direct interfacing functions a certain number of time over a
    number of rounds to test the number of operations per second and total time
    to execute the number of operations. Main parameter to test with is the
    garbage collection interval (gc_interval).
    """
    label = "hello_howso"
    rounds = 100
    ops_per_round = 1000
    avg_ops = 0
    avg_time = 0
    for n in range(rounds):
        handle = str(uuid4())
        amlg.load_entity(handle, os.path.dirname(
            amalgam.__file__) + "/test/test.amlg", write_log="", print_log="")

        amlg.set_entity_permissions(handle, json.dumps(True))
        ent_permissions = json.loads(amlg.get_entity_permissions(handle))
        for permission_str in [
            "std_out_and_std_err",
            "std_in",
            "load",
            "store",
            "environment",
            "alter_performance",
            "system"
        ]:
            assert permission_str in ent_permissions
            assert ent_permissions[permission_str] is True

        _logger.debug(n)
        start = dt.datetime.now()
        i = 0
        while ops_per_round * 10 > i:
            amlg.set_json_to_label(
                handle, label, json.dumps(["hello", "world"]))
            amlg.get_json_from_label(handle, label)
            i += 10
        interval = dt.datetime.now() - start
        total_time = (interval.seconds + interval.microseconds / 1000000)
        avg_ops += i / total_time
        avg_time += total_time
    _logger.info("completed in " + str(avg_time / rounds) + "s")
    _logger.info(str(avg_ops / rounds) + " operations per second")
    return True
