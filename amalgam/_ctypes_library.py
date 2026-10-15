"""Amalgam native backend implemented with ctypes."""
from __future__ import annotations

from collections.abc import Sequence
from ctypes import (
    _Pointer, Array, byref, c_bool, c_char, c_char_p, c_size_t, c_uint64, c_void_p,
    cast, CDLL, POINTER, string_at, Structure
)
import typing as t

from amalgam._types import LoadStatusTuple, Text


class _LoadEntityStatus(Structure):
    """
    A private status returned from Amalgam binary LoadEntity C API.

    This is implemented with ctypes for accessing binary Amalgam builds.
    """

    _fields_ = [
        ("loaded", c_bool),
        ("message", POINTER(c_char)),
        ("version", POINTER(c_char)),
        ("entity_path", POINTER(POINTER(c_char))),
        ("entity_path_len", c_size_t)
    ]


class _ResultWithLog(Structure):
    """The C-native version of :class:`ResultWithLog`."""
    _fields_ = [
        ("json", POINTER(c_char)),
        ("log", POINTER(c_char))
    ]


_CHAR_P = POINTER(c_char)

# (entry point, restype, argtypes) for every engine function this backend calls.
_SIGNATURES: tuple[tuple[str, t.Any, tuple[t.Any, ...]], ...] = (
    ("DeleteString", None, (c_char_p,)),
    ("GetVersionString", _CHAR_P, ()),
    ("GetConcurrencyTypeString", _CHAR_P, ()),
    ("IsSBFDataStoreEnabled", c_bool, ()),
    ("SetSBFDataStoreEnabled", None, (c_bool,)),
    ("GetMaxNumThreads", c_size_t, ()),
    ("SetMaxNumThreads", None, (c_size_t,)),
    ("GetNumActiveThreads", c_size_t, ()),
    ("GetGarbageCollectionParams", _CHAR_P, ()),
    ("SetGarbageCollectionParams", None, (c_char_p,)),
    ("GetJSONPtrFromLabel", _CHAR_P, (c_char_p, c_char_p)),
    ("SetJSONToLabel", None, (c_char_p, c_char_p, c_char_p)),
    ("GetEntityPermissions", _CHAR_P, (c_char_p,)),
    ("SetEntityPermissions", c_bool, (c_char_p, c_char_p)),
    ("LoadEntity", _LoadEntityStatus,
     (c_char_p, c_char_p, c_char_p, c_bool, c_char_p, c_char_p, c_char_p, POINTER(c_char_p), c_size_t)),
    ("LoadEntityFromMemory", _LoadEntityStatus,
     (c_char_p, c_void_p, c_size_t, c_char_p, c_bool, c_char_p, c_char_p, c_char_p, POINTER(c_char_p), c_size_t)),
    ("VerifyEntity", _LoadEntityStatus, (c_char_p,)),
    ("CloneEntity", c_bool, (c_char_p, c_char_p, c_char_p, c_char_p, c_bool, c_char_p, c_char_p, c_char_p)),
    ("StoreEntity", c_bool, (c_char_p, c_char_p, c_char_p, c_bool, c_char_p, POINTER(c_char_p), c_size_t)),
    ("StoreEntityToMemory", c_bool,
     (c_char_p, POINTER(c_void_p), POINTER(c_size_t), c_char_p, c_bool, c_char_p, POINTER(c_char_p), c_size_t)),
    ("DestroyEntity", None, (c_char_p,)),
    ("SetRandomSeed", c_bool, (c_char_p, c_char_p)),
    ("GetEntities", POINTER(_CHAR_P), (POINTER(c_uint64),)),
    ("ExecuteEntityJsonPtr", _CHAR_P, (c_char_p, c_char_p, c_char_p)),
    ("ExecuteEntityJsonPtrLogged", _ResultWithLog, (c_char_p, c_char_p, c_char_p)),
    ("EvalOnEntity", _CHAR_P, (c_char_p, c_char_p)),
)


def _encode(value: Text) -> bytes:
    """Return ``value`` as UTF-8 bytes; ``bytes`` input is returned as-is, without copying."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(f"expected str or bytes, not {type(value).__name__}")


def _entity_path_array(entity_path: Sequence[Text] | None) -> tuple[Array[c_char_p] | None, int]:
    """Build a ``const char **`` array for an entity path; ``None`` or empty gives a null pointer."""
    if not entity_path:
        return None, 0
    encoded = [_encode(entry) for entry in entity_path]
    # The array keeps references to the bytes objects it points into.
    return (c_char_p * len(encoded))(*encoded), len(encoded)


class CtypesLibrary:
    """
    Amalgam native backend that calls the engine through ctypes.

    Parameters
    ----------
    cdll : CDLL
        The loaded Amalgam library, from :func:`amalgam._loader.open_library`.
    """

    def __init__(self, cdll: CDLL) -> None:
        self._cdll = cdll
        self._functions: dict[str, t.Any] = {}
        for name, restype, argtypes in _SIGNATURES:
            function = getattr(cdll, name, None)
            if function is not None:
                function.restype = restype
                function.argtypes = list(argtypes)
            self._functions[name] = function

    def _function(self, name: str) -> t.Any:
        """Return the configured engine function ``name``."""
        function = self._functions[name]
        if function is None:
            raise AttributeError(f"function '{name}' not found in the Amalgam library")
        return function

    def str_to_char_p(
        self,
        value: str | bytes,
        size: t.Optional[int] = None
    ) -> Array[c_char]:
        """
        Convert a string to an Array of C char.

        User must call `del` on returned buffer

        Parameters
        ----------
        value : str or bytes
            The value of the string.
        size : int, optional
            The size of the string. If not provided, the length of
            the string is used.

        Returns
        -------
        Array of c_char
            An Array of C char datatypes which form the given string
        """
        if isinstance(value, str):
            value = value.encode('utf-8')
        buftype = c_char * (size if size is not None else (len(value) + 1))
        buf = buftype()
        buf.value = value
        return buf

    def char_p_to_bytes(self, p: _Pointer[c_char] | c_char_p) -> bytes | None:
        """
        Copy native C char pointer to bytes, cleaning up memory correctly.

        Parameters
        ----------
        p : c_char_p
            The char pointer to convert

        Returns
        -------
        bytes or None
            The byte-encoded char
        """
        bytes_str = cast(p, c_char_p).value

        self._function("DeleteString")(p)

        return bytes_str

    def char_p_to_str(self, p: _Pointer[c_char] | c_char_p) -> str | None:
        """
        Copy native C char pointer to UTF-8-encoded string, cleaning up memory correctly.

        Parameters
        ----------
        p : c_char_p
            The char pointer to convert

        Returns
        -------
        str or None
            The resulting string
        """
        b = self.char_p_to_bytes(p)
        s: str | None = None
        if b is not None:
            try:
                s = b.decode("UTF-8")
            except UnicodeDecodeError:
                s = None
        return s

    def _load_status(
        self, c_status: _LoadEntityStatus
    ) -> LoadStatusTuple:
        """Convert and free an engine ``LoadEntityStatus``."""
        loaded = bool(c_status.loaded)
        message = self.char_p_to_str(c_status.message)
        version = self.char_p_to_str(c_status.version)
        entity_path = [self.char_p_to_str(c_status.entity_path[i]) for i in range(c_status.entity_path_len)]
        self._function("DeleteString")(cast(c_status.entity_path, c_char_p))
        return loaded, message, version, entity_path

    def is_sbf_datastore_enabled(self) -> bool:
        """Call ``IsSBFDataStoreEnabled``."""
        return self._function("IsSBFDataStoreEnabled")()

    def set_sbf_datastore_enabled(self, enabled: bool, /) -> None:
        """Call ``SetSBFDataStoreEnabled``."""
        self._function("SetSBFDataStoreEnabled")(enabled)

    def get_max_num_threads(self) -> int:
        """Call ``GetMaxNumThreads``."""
        return self._function("GetMaxNumThreads")()

    def set_max_num_threads(self, max_num_threads: int, /) -> None:
        """Call ``SetMaxNumThreads``."""
        self._function("SetMaxNumThreads")(max_num_threads)

    def get_num_active_threads(self) -> int:
        """Call ``GetNumActiveThreads``."""
        return self._function("GetNumActiveThreads")()

    def get_garbage_collection_params(self) -> bytes | None:
        """Call ``GetGarbageCollectionParams``."""
        return self.char_p_to_bytes(self._function("GetGarbageCollectionParams")())

    def set_garbage_collection_params(self, json_params: Text, /) -> None:
        """Call ``SetGarbageCollectionParams``."""
        self._function("SetGarbageCollectionParams")(_encode(json_params))

    def get_json_from_label(self, handle: Text, label: Text, /) -> bytes | None:
        """Call ``GetJSONPtrFromLabel``."""
        return self.char_p_to_bytes(self._function("GetJSONPtrFromLabel")(_encode(handle), _encode(label)))

    def set_json_to_label(self, handle: Text, label: Text, json: Text, /) -> None:
        """Call ``SetJSONToLabel``."""
        self._function("SetJSONToLabel")(_encode(handle), _encode(label), _encode(json))

    def load_entity(
        self, handle: Text, file_path: Text, file_type: Text, persist: bool, json_file_params: Text,
        write_log: Text, print_log: Text, entity_path: Sequence[Text] | None, /
    ) -> LoadStatusTuple:
        """Call ``LoadEntity``."""
        path_array, path_len = _entity_path_array(entity_path)
        return self._load_status(self._function("LoadEntity")(
            _encode(handle), _encode(file_path), _encode(file_type), persist, _encode(json_file_params),
            _encode(write_log), _encode(print_log), path_array, path_len))

    def load_entity_from_memory(
        self, handle: Text, contents: bytes, file_type: Text, json_file_params: Text,
        write_log: Text, print_log: Text, entity_path: Sequence[Text] | None, /
    ) -> LoadStatusTuple:
        """Call ``LoadEntityFromMemory``; ``contents`` must be ``bytes``."""
        if not isinstance(contents, bytes):
            raise TypeError(f"contents must be bytes, not {type(contents).__name__}")
        path_array, path_len = _entity_path_array(entity_path)
        return self._load_status(self._function("LoadEntityFromMemory")(
            _encode(handle), contents, len(contents), _encode(file_type), False, _encode(json_file_params),
            _encode(write_log), _encode(print_log), path_array, path_len))

    def verify_entity(self, file_path: Text, /) -> LoadStatusTuple:
        """Call ``VerifyEntity``."""
        return self._load_status(self._function("VerifyEntity")(_encode(file_path)))

    def get_entity_permissions(self, handle: Text, /) -> bytes | None:
        """Call ``GetEntityPermissions``."""
        return self.char_p_to_bytes(self._function("GetEntityPermissions")(_encode(handle)))

    def set_entity_permissions(self, handle: Text, json_permissions: Text, /) -> bool:
        """Call ``SetEntityPermissions``."""
        return self._function("SetEntityPermissions")(_encode(handle), _encode(json_permissions))

    def clone_entity(
        self, handle: Text, clone_handle: Text, file_path: Text, file_type: Text, persist: bool,
        json_file_params: Text, write_log: Text, print_log: Text, /
    ) -> bool:
        """Call ``CloneEntity``."""
        return self._function("CloneEntity")(
            _encode(handle), _encode(clone_handle), _encode(file_path), _encode(file_type), persist,
            _encode(json_file_params), _encode(write_log), _encode(print_log))

    def store_entity(
        self, handle: Text, file_path: Text, file_type: Text, persist: bool, json_file_params: Text,
        entity_path: Sequence[Text] | None, /
    ) -> bool:
        """Call ``StoreEntity``."""
        path_array, path_len = _entity_path_array(entity_path)
        return self._function("StoreEntity")(
            _encode(handle), _encode(file_path), _encode(file_type), persist, _encode(json_file_params),
            path_array, path_len)

    def store_entity_to_memory(
        self, handle: Text, file_type: Text, json_file_params: Text, entity_path: Sequence[Text] | None, /
    ) -> bytes | None:
        """Call ``StoreEntityToMemory``."""
        data_p = c_void_p(None)
        data_len = c_size_t(0)
        path_array, path_len = _entity_path_array(entity_path)

        self._function("StoreEntityToMemory")(
            _encode(handle), byref(data_p), byref(data_len), _encode(file_type), False,
            _encode(json_file_params), path_array, path_len)

        result = None
        if data_p.value is not None:
            result = string_at(data_p.value, data_len.value)
            self._function("DeleteString")(cast(data_p, c_char_p))
        return result

    def destroy_entity(self, handle: Text, /) -> None:
        """Call ``DestroyEntity``."""
        self._function("DestroyEntity")(_encode(handle))

    def set_random_seed(self, handle: Text, rand_seed: Text, /) -> bool:
        """Call ``SetRandomSeed``."""
        return self._function("SetRandomSeed")(_encode(handle), _encode(rand_seed))

    def get_entities(self) -> list[str]:
        """Call ``GetEntities``; every returned string and the array itself are freed."""
        num_entities = c_uint64()
        entities = self._function("GetEntities")(byref(num_entities))
        try:
            raw = [self.char_p_to_bytes(entities[i]) or b"" for i in range(num_entities.value)]
        finally:
            if entities:
                self._function("DeleteString")(cast(entities, c_char_p))
        return [handle.decode() for handle in raw]

    def execute_entity_json(self, handle: Text, label: Text, json: Text, /) -> bytes | None:
        """Call ``ExecuteEntityJsonPtr``."""
        return self.char_p_to_bytes(
            self._function("ExecuteEntityJsonPtr")(_encode(handle), _encode(label), _encode(json)))

    def execute_entity_json_logged(
        self, handle: Text, label: Text, json: Text, /
    ) -> tuple[bytes | None, bytes | None]:
        """Call ``ExecuteEntityJsonPtrLogged``."""
        c_result = self._function("ExecuteEntityJsonPtrLogged")(_encode(handle), _encode(label), _encode(json))
        return self.char_p_to_bytes(c_result.json), self.char_p_to_bytes(c_result.log)

    def eval_on_entity(self, handle: Text, amlg: Text, /) -> bytes | None:
        """Call ``EvalOnEntity``."""
        return self.char_p_to_bytes(self._function("EvalOnEntity")(_encode(handle), _encode(amlg)))

    def get_version_string(self) -> bytes | None:
        """Call ``GetVersionString``."""
        return self.char_p_to_bytes(self._function("GetVersionString")())

    def get_concurrency_type_string(self) -> bytes | None:
        """Call ``GetConcurrencyTypeString``."""
        return self.char_p_to_bytes(self._function("GetConcurrencyTypeString")())
