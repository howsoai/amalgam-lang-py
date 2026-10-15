"""Python-heap copies made by Amalgam calls with large payloads."""
from collections.abc import Callable
import json

from amalgam._types import NativeLibrary

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
