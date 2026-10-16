"""Python-heap copies made by Amalgam calls with large payloads."""
from collections.abc import Callable
from io import BytesIO
import json
import os
from pathlib import Path

import pytest

from amalgam._native import BACKEND_ENV_VAR
from amalgam._types import NativeLibrary
from amalgam.api import Amalgam, LoadEntityStatus

PAYLOAD_SIZE = 10_000_000


def test_execute_entity_json_input_copies(
    native_library: NativeLibrary, entity: str, backend: str,
    peak_traced_bytes: Callable[[Callable[[], object]], int]
) -> None:
    """The C backend passes an ASCII str payload without copying; ctypes copies it once."""
    body = json.dumps({"pad": "x" * PAYLOAD_SIZE})
    peak = peak_traced_bytes(lambda: native_library.execute_entity_json(entity, "hello_howso", body))
    assert peak < (PAYLOAD_SIZE // 100 if backend == "c" else PAYLOAD_SIZE * 1.1)


def test_execute_entity_json_bytes_input_is_not_copied(
    native_library: NativeLibrary, entity: str, peak_traced_bytes: Callable[[Callable[[], object]], int]
) -> None:
    """A bytes payload is passed without copying on every backend."""
    body = json.dumps({"pad": "x" * PAYLOAD_SIZE}).encode()
    peak = peak_traced_bytes(lambda: native_library.execute_entity_json(entity, "hello_howso", body))
    assert peak < PAYLOAD_SIZE // 100


def test_set_json_to_label_input_copies(
    native_library: NativeLibrary, entity: str, backend: str,
    peak_traced_bytes: Callable[[Callable[[], object]], int]
) -> None:
    """Setting a large label value does not copy an ASCII str payload in the C backend."""
    body = json.dumps("x" * PAYLOAD_SIZE)
    peak = peak_traced_bytes(lambda: native_library.set_json_to_label(entity, "hello_howso", body))
    assert peak < (PAYLOAD_SIZE // 100 if backend == "c" else PAYLOAD_SIZE * 1.1)


LOAD_PARAMS = '{"execute_on_load": true}'


@pytest.fixture
def large_entity(
    amlg: Amalgam, test_entity_file: Path, new_handle: Callable[[], str]
) -> tuple[str, bytes]:
    """A loaded entity holding a large label value, and its plain-text serialization."""
    handle = new_handle()
    assert amlg.load_entity(handle, str(test_entity_file)).loaded
    amlg.set_json_to_label(handle, "hello_howso", json.dumps(os.urandom(PAYLOAD_SIZE // 2).hex()))
    contents = amlg.store_entity_to_memory(handle, file_type="amlg")
    assert contents is not None and len(contents) > PAYLOAD_SIZE
    return handle, contents


def test_load_entity_from_memory_untraced_makes_no_copies(
    amlg: Amalgam, large_entity: tuple[str, bytes], new_handle: Callable[[], str],
    peak_traced_bytes: Callable[[Callable[[], object]], int]
) -> None:
    """With tracing off, loading from memory does not copy the contents on the Python heap."""
    _, contents = large_entity
    handle = new_handle()
    statuses: list[LoadEntityStatus] = []
    peak = peak_traced_bytes(lambda: statuses.append(
        amlg.load_entity_from_memory(handle, contents, file_type="amlg", json_file_params=LOAD_PARAMS)))
    assert statuses[0].loaded, statuses[0].message
    assert peak < len(contents) // 10
    assert amlg.load_command_log_entry is None


def test_store_entity_to_memory_untraced_makes_one_copy(
    amlg: Amalgam, large_entity: tuple[str, bytes], peak_traced_bytes: Callable[[Callable[[], object]], int]
) -> None:
    """With tracing off, storing to memory allocates only the returned bytes."""
    handle, contents = large_entity
    peak = peak_traced_bytes(lambda: amlg.store_entity_to_memory(handle, file_type="amlg"))
    assert peak < len(contents) * 1.1


def test_load_entity_from_memory_traced_logs_contents(
    amlg: Amalgam, large_entity: tuple[str, bytes], new_handle: Callable[[], str]
) -> None:
    """With tracing on, the load command is traced and kept for trace resets."""
    _, contents = large_entity
    amlg.trace = BytesIO()
    assert amlg.load_entity_from_memory(
        new_handle(), contents, file_type="amlg", json_file_params=LOAD_PARAMS).loaded
    traced = amlg.trace.getvalue()
    amlg.trace = None
    assert amlg.load_command_log_entry is not None
    assert amlg.load_command_log_entry.startswith(b"LOAD_ENTITY_FROM_MEMORY ")
    assert traced.startswith(amlg.load_command_log_entry)


def test_reset_trace_after_untraced_memory_load(
    amalgam_library_path: Path, backend: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    large_entity: tuple[str, bytes], new_handle: Callable[[], str]
) -> None:
    """Enabling tracing after an untraced in-memory load replays no stale load command."""
    monkeypatch.setenv(BACKEND_ENV_VAR, backend)
    traced = Amalgam(library_path=amalgam_library_path, trace=True, execution_trace_dir=str(tmp_path))
    _, contents = large_entity
    saved = traced.trace
    traced.trace = None
    assert traced.load_entity_from_memory(
        new_handle(), contents, file_type="amlg", json_file_params=LOAD_PARAMS).loaded
    traced.trace = saved
    traced.reset_trace("after.trace")
    assert b"LOAD_ENTITY_FROM_MEMORY" not in (tmp_path / "after.trace").read_bytes()
