"""Behavior shared by every native backend, checked against the real engine."""
import _ctypes
from collections.abc import Callable
from ctypes import CDLL
import json
from pathlib import Path
import threading
import time

import pytest

from amalgam._ctypes_library import CtypesLibrary
from amalgam._types import NativeLibrary


def test_version_and_concurrency(native_library: NativeLibrary) -> None:
    """Version and concurrency strings come back as bytes."""
    version = native_library.get_version_string()
    assert isinstance(version, bytes) and version.count(b".") >= 2
    assert native_library.get_concurrency_type_string() in {
        b"SingleThreaded", b"MultiThreaded", b"SingleThreaded+OpenMP", b"MultiThreaded+OpenMP"}


def test_sbf_datastore_flag(native_library: NativeLibrary) -> None:
    """The SBF datastore flag can be read and written."""
    original = native_library.is_sbf_datastore_enabled()
    try:
        native_library.set_sbf_datastore_enabled(not original)
        assert native_library.is_sbf_datastore_enabled() is (not original)
    finally:
        native_library.set_sbf_datastore_enabled(original)


def test_thread_counts(native_library: NativeLibrary) -> None:
    """Thread counts are non-negative ints and setting the maximum is accepted."""
    maximum = native_library.get_max_num_threads()
    assert isinstance(maximum, int) and maximum >= 1
    native_library.set_max_num_threads(maximum)
    assert native_library.get_max_num_threads() == maximum
    assert native_library.get_num_active_threads() >= 0


def test_garbage_collection_params_round_trip(native_library: NativeLibrary) -> None:
    """Garbage-collection parameters round-trip as JSON."""
    original = native_library.get_garbage_collection_params()
    assert original is not None
    params = json.loads(original)
    try:
        native_library.set_garbage_collection_params(
            json.dumps({"min_gc_nodes_threshold": params["min_gc_nodes_threshold"] + 1}))
        updated = json.loads(native_library.get_garbage_collection_params() or b"{}")
        assert updated["min_gc_nodes_threshold"] == params["min_gc_nodes_threshold"] + 1
    finally:
        native_library.set_garbage_collection_params(original)


def test_load_entity_failure_status(native_library: NativeLibrary, tmp_path: Path) -> None:
    """A missing entity file reports loaded=False with a message."""
    loaded, message, version, entity_path = native_library.load_entity(
        "missing", str(tmp_path / "missing.amlg"), "", False, "", "", "", None)
    assert loaded is False
    assert message
    assert version == ""
    assert entity_path == []


def test_labels_round_trip(native_library: NativeLibrary, entity: str) -> None:
    """Label values can be read and written as JSON, including non-ASCII text."""
    assert native_library.get_json_from_label(entity, "hello_howso") == b'"Hello Howso!"'
    native_library.set_json_to_label(entity, "hello_howso", '{"a": "é"}')
    assert json.loads(native_library.get_json_from_label(entity, b"hello_howso") or b"") == {"a": "é"}


def test_entity_permissions(native_library: NativeLibrary, entity: str) -> None:
    """Permissions can be granted and read back."""
    assert native_library.set_entity_permissions(entity, "true") is True
    permissions = json.loads(native_library.get_entity_permissions(entity) or b"{}")
    assert permissions and all(permissions.values())


def test_set_random_seed(native_library: NativeLibrary, entity: str) -> None:
    """Seeding succeeds for a loaded entity and fails for a missing one."""
    assert native_library.set_random_seed(entity, "abc") is True
    assert native_library.set_random_seed("missing", "abc") is False


def test_eval_on_entity(native_library: NativeLibrary, entity: str) -> None:
    """Amalgam code evaluates against an entity."""
    assert native_library.eval_on_entity(entity, "(+ 1 2)") == b"3"


@pytest.mark.parametrize("as_bytes", [False, True])
def test_execute_entity_json(native_library: NativeLibrary, entity: str, as_bytes: bool) -> None:
    """Executing a label accepts str or bytes payloads."""
    body = json.dumps({"payload": {"a": [1, "x"]}})
    result = native_library.execute_entity_json(entity, "echo", body.encode() if as_bytes else body)
    assert result == b'{"a":[1,"x"]}'


def test_execute_entity_json_non_ascii(native_library: NativeLibrary, entity: str) -> None:
    """Non-ASCII str payloads are passed as UTF-8."""
    body = json.dumps({"payload": "café ☕"}, ensure_ascii=False)
    result = native_library.execute_entity_json(entity, "echo", body)
    assert json.loads(result or b"") == "café ☕"


def test_execute_entity_json_missing_handle(native_library: NativeLibrary) -> None:
    """A missing entity produces an empty response."""
    assert native_library.execute_entity_json("missing", "echo", "{}") == b""


def test_execute_entity_json_logged(native_library: NativeLibrary, entity: str) -> None:
    """The logged variant returns both the response and the transaction log."""
    result, log = native_library.execute_entity_json_logged(entity, "echo", json.dumps({"payload": 5}))
    assert result == b"5"
    assert log == b"(seq)"


def test_destroy_entity(native_library: NativeLibrary, test_entity_file: Path) -> None:
    """A destroyed entity answers label reads with an empty response."""
    loaded, _, _, _ = native_library.load_entity("doomed", str(test_entity_file), "", False, "", "", "", None)
    assert loaded
    native_library.destroy_entity("doomed")
    assert native_library.get_json_from_label("doomed", "hello_howso") == b""


@pytest.mark.parametrize("file_type", ["amlg", "caml"])
def test_store_and_load_from_memory(
    native_library: NativeLibrary, entity: str, new_native_handle: Callable[[], str], file_type: str
) -> None:
    """An entity serialized to memory loads back under a new handle."""
    native_library.set_json_to_label(entity, "hello_howso", '"stored"')
    contents = native_library.store_entity_to_memory(entity, file_type, "", None)
    assert contents
    copy = new_native_handle()
    loaded, message, _, _ = native_library.load_entity_from_memory(
        copy, contents, file_type, '{"execute_on_load": true}', "", "", None)
    assert loaded, message
    assert native_library.get_json_from_label(copy, "hello_howso") == b'"stored"'


def test_store_entity_to_memory_missing_handle(native_library: NativeLibrary) -> None:
    """Serializing a missing entity yields empty bytes."""
    assert native_library.store_entity_to_memory("missing", "caml", "", None) == b""


def test_load_into_entity_path(native_library: NativeLibrary, entity: str, test_entity_file: Path) -> None:
    """Entities can be loaded into a contained entity path."""
    loaded, message, _, entity_path = native_library.load_entity(
        entity, str(test_entity_file), "", False, "", "", "", ["child"])
    assert loaded, message
    assert entity_path == ["child"]


def test_store_entity_and_verify(native_library: NativeLibrary, entity: str, tmp_path: Path) -> None:
    """An entity stored to a file verifies; a missing file does not."""
    target = tmp_path / "stored.amlg"
    assert native_library.store_entity(entity, str(target), "", False, "", None)
    assert target.exists()
    assert native_library.verify_entity(str(target))[0] is True
    loaded, message, _, _ = native_library.verify_entity(str(tmp_path / "absent.amlg"))
    assert loaded is False and message


def test_clone_entity(native_library: NativeLibrary, entity: str, new_native_handle: Callable[[], str]) -> None:
    """Cloning copies an entity; cloning a missing entity fails."""
    clone = new_native_handle()
    assert native_library.clone_entity(entity, clone, "", "", False, "", "", "")
    assert native_library.get_json_from_label(clone, "hello_howso") == b'"Hello Howso!"'
    assert not native_library.clone_entity("missing", new_native_handle(), "", "", False, "", "", "")


def test_get_entities(native_library: NativeLibrary, entity: str) -> None:
    """Loaded top-level entities are listed by handle."""
    entities = native_library.get_entities()
    assert entity in entities
    assert all(isinstance(handle, str) for handle in entities)


@pytest.mark.parametrize("bad", [5, None, 1.5])
def test_rejects_non_text_arguments(native_library: NativeLibrary, entity: str, bad: object) -> None:
    """Arguments that are neither str nor bytes raise TypeError."""
    with pytest.raises(TypeError):
        native_library.execute_entity_json(bad, "echo", "{}")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        native_library.execute_entity_json(entity, "echo", bad)  # type: ignore[arg-type]


def test_engine_calls_release_the_gil(native_library: NativeLibrary, entity: str) -> None:
    """Python threads keep running while an engine call is in progress."""
    done = threading.Event()

    def run_busy() -> None:
        native_library.execute_entity_json(entity, "busy", "{}")
        done.set()

    worker = threading.Thread(target=run_busy)
    started = time.perf_counter()
    worker.start()
    ticks = 0
    while not done.is_set():
        ticks += 1
        time.sleep(0.001)
    worker.join()
    assert time.perf_counter() - started > 0.1, "the busy label returned too quickly to measure"
    assert ticks > 20


def test_clone_entity_returns_bool(
    native_library: NativeLibrary, entity: str, new_native_handle: Callable[[], str]
) -> None:
    """clone_entity reports success as a bool."""
    assert native_library.clone_entity(entity, new_native_handle(), "", "", False, "", "", "") is True
    assert native_library.clone_entity("missing", new_native_handle(), "", "", False, "", "", "") is False


def test_ctypes_missing_entry_point_fails_when_called() -> None:
    """A CtypesLibrary over a library without an entry point fails only when that entry point is called."""
    other_library = getattr(_ctypes, "__file__", None)
    if other_library is None:
        pytest.skip("_ctypes is built into this interpreter")
    library = CtypesLibrary(CDLL(other_library))
    with pytest.raises(AttributeError, match="GetVersionString"):
        library.get_version_string()


def test_store_from_entity_path(
    native_library: NativeLibrary, entity: str, test_entity_file: Path, new_native_handle: Callable[[], str],
    tmp_path: Path
) -> None:
    """A contained entity can be stored to memory and to a file by its entity path."""
    loaded, message, _, _ = native_library.load_entity(
        entity, str(test_entity_file), "", False, "", "", "", ["child"])
    assert loaded, message
    target = tmp_path / "child.amlg"
    assert native_library.store_entity(entity, str(target), "", False, "", ["child"]) is True
    loaded, message, _, _ = native_library.verify_entity(str(target))
    assert loaded, message
    # Storing the containing entity would also write its contained entities into this directory.
    assert not (tmp_path / "child").exists()
    stored = new_native_handle()
    loaded, message, _, _ = native_library.load_entity(stored, str(target), "", False, "", "", "", None)
    assert loaded, message
    assert native_library.get_json_from_label(stored, "hello_howso") == b'"Hello Howso!"'
    contents = native_library.store_entity_to_memory(entity, "amlg", "", ["child"])
    assert contents and b"hello_howso" in contents
    loaded, message, _, entity_path = native_library.load_entity_from_memory(
        entity, contents, "amlg", "", "", "", ("second",))
    assert loaded, message
    assert entity_path == ["second"]
