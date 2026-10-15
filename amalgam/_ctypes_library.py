"""Amalgam native backend implemented with ctypes."""
from __future__ import annotations

from ctypes import (
    _Pointer, Array, byref, c_bool, c_char, c_char_p, c_size_t, c_uint64, c_void_p,
    cast, CDLL, POINTER, string_at, Structure
)
import typing as t


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
    ("GetEntities", POINTER(c_char_p), (POINTER(c_uint64),)),
    ("ExecuteEntityJsonPtr", _CHAR_P, (c_char_p, c_char_p, c_char_p)),
    ("ExecuteEntityJsonPtrLogged", _ResultWithLog, (c_char_p, c_char_p, c_char_p)),
    ("EvalOnEntity", _CHAR_P, (c_char_p, c_char_p)),
)


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
    ) -> tuple[bool, str | None, str | None, list[str | None]]:
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

    def set_sbf_datastore_enabled(self, enabled: bool) -> None:
        """Call ``SetSBFDataStoreEnabled``."""
        self._function("SetSBFDataStoreEnabled")(enabled)

    def get_max_num_threads(self) -> int:
        """Call ``GetMaxNumThreads``."""
        return self._function("GetMaxNumThreads")()

    def set_max_num_threads(self, max_num_threads: int) -> None:
        """Call ``SetMaxNumThreads``."""
        self._function("SetMaxNumThreads")(max_num_threads)

    def get_num_active_threads(self) -> int:
        """Call ``GetNumActiveThreads``."""
        return self._function("GetNumActiveThreads")()

    def get_garbage_collection_params(self) -> bytes | None:
        """Call ``GetGarbageCollectionParams``."""
        return self.char_p_to_bytes(self._function("GetGarbageCollectionParams")())

    def set_garbage_collection_params(self, json_params: str | bytes) -> None:
        """Call ``SetGarbageCollectionParams``."""
        params_buf = self.str_to_char_p(json_params)
        self._function("SetGarbageCollectionParams")(params_buf)
        del params_buf

    def get_json_from_label(self, handle: str | bytes, label: str | bytes) -> bytes | None:
        """Call ``GetJSONPtrFromLabel``."""
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        result = self.char_p_to_bytes(self._function("GetJSONPtrFromLabel")(handle_buf, label_buf))
        del handle_buf
        del label_buf
        return result

    def set_json_to_label(self, handle: str | bytes, label: str | bytes, json: str | bytes) -> None:
        """Call ``SetJSONToLabel``."""
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        json_buf = self.str_to_char_p(json)
        self._function("SetJSONToLabel")(handle_buf, label_buf, json_buf)
        del handle_buf
        del label_buf
        del json_buf

    def load_entity(
        self, handle: str, file_path: str, file_type: str, persist: bool, json_file_params: str,
        write_log: str, print_log: str, entity_path: list[str] | None
    ) -> tuple[bool, str | None, str | None, list[str | None]]:
        """Call ``LoadEntity``."""
        handle_buf = self.str_to_char_p(handle)
        file_path_buf = self.str_to_char_p(file_path)
        file_type_buf = self.str_to_char_p(file_type)
        json_file_params_buf = self.str_to_char_p(json_file_params)
        write_log_buf = self.str_to_char_p(write_log)
        print_log_buf = self.str_to_char_p(print_log)
        entity_path_p = None
        entity_path_len = 0

        if entity_path is not None and len(entity_path) > 0:
            entity_path_len = len(entity_path)
            entity_path_p = (c_char_p * entity_path_len)()
            for i, entry in enumerate(entity_path):
                entity_path_p[i] = cast(self.str_to_char_p(entry), c_char_p)

        result = self._load_status(self._function("LoadEntity")(
            handle_buf, file_path_buf, file_type_buf, persist,
            json_file_params_buf, write_log_buf, print_log_buf, entity_path_p, entity_path_len))

        del handle_buf
        del file_path_buf
        del file_type_buf
        del json_file_params_buf
        del write_log_buf
        del print_log_buf
        if entity_path_p is not None:
            for i in range(entity_path_len):
                entry_buf = entity_path_p[i]
                del entry_buf
            del entity_path_p
        return result

    def load_entity_from_memory(
        self, handle: str, contents: bytes, file_type: str, json_file_params: str,
        write_log: str, print_log: str, entity_path: list[str] | None
    ) -> tuple[bool, str | None, str | None, list[str | None]]:
        """Call ``LoadEntityFromMemory``."""
        handle_buf = self.str_to_char_p(handle)
        file_type_buf = self.str_to_char_p(file_type)
        json_file_params_buf = self.str_to_char_p(json_file_params)
        write_log_buf = self.str_to_char_p(write_log)
        print_log_buf = self.str_to_char_p(print_log)
        entity_path_p = None
        entity_path_len = 0

        if entity_path is not None and len(entity_path) > 0:
            entity_path_len = len(entity_path)
            entity_path_p = (c_char_p * entity_path_len)()
            for i, entry in enumerate(entity_path):
                entity_path_p[i] = cast(self.str_to_char_p(entry), c_char_p)

        result = self._load_status(self._function("LoadEntityFromMemory")(
            handle_buf, contents, len(contents), file_type_buf, False,
            json_file_params_buf, write_log_buf, print_log_buf, entity_path_p, entity_path_len))

        del handle_buf
        del file_type_buf
        del json_file_params_buf
        del write_log_buf
        del print_log_buf
        if entity_path_p is not None:
            for i in range(entity_path_len):
                entry_buf = entity_path_p[i]
                del entry_buf
            del entity_path_p
        return result

    def verify_entity(self, file_path: str) -> tuple[bool, str | None, str | None, list[str | None]]:
        """Call ``VerifyEntity``."""
        file_path_buf = self.str_to_char_p(file_path)

        result = self._load_status(self._function("VerifyEntity")(file_path_buf))

        del file_path_buf
        return result

    def get_entity_permissions(self, handle: str) -> bytes | None:
        """Call ``GetEntityPermissions``."""
        handle_buf = self.str_to_char_p(handle)

        result = self.char_p_to_bytes(self._function("GetEntityPermissions")(handle_buf))

        del handle_buf
        return result

    def set_entity_permissions(self, handle: str, json_permissions: str | bytes) -> bool:
        """Call ``SetEntityPermissions``."""
        handle_buf = self.str_to_char_p(handle)
        json_permissions_buf = self.str_to_char_p(json_permissions)

        result = self._function("SetEntityPermissions")(handle_buf, json_permissions_buf)

        del handle_buf
        del json_permissions_buf
        return result

    def clone_entity(
        self, handle: str, clone_handle: str, file_path: str, file_type: str, persist: bool,
        json_file_params: str, write_log: str, print_log: str
    ) -> bool:
        """Call ``CloneEntity``."""
        handle_buf = self.str_to_char_p(handle)
        clone_handle_buf = self.str_to_char_p(clone_handle)
        file_path_buf = self.str_to_char_p(file_path)
        file_type_buf = self.str_to_char_p(file_type)
        json_file_params_buf = self.str_to_char_p(json_file_params)
        write_log_buf = self.str_to_char_p(write_log)
        print_log_buf = self.str_to_char_p(print_log)

        result = self._function("CloneEntity")(
            handle_buf, clone_handle_buf, file_path_buf, file_type_buf, persist,
            json_file_params_buf, write_log_buf, print_log_buf)

        del handle_buf
        del clone_handle_buf
        del file_path_buf
        del file_type_buf
        del json_file_params_buf
        del write_log_buf
        del print_log_buf
        return result

    def store_entity(
        self, handle: str, file_path: str, file_type: str, persist: bool, json_file_params: str,
        entity_path: list[str] | None
    ) -> bool:
        """Call ``StoreEntity``."""
        handle_buf = self.str_to_char_p(handle)
        file_path_buf = self.str_to_char_p(file_path)
        file_type_buf = self.str_to_char_p(file_type)
        json_file_params_buf = self.str_to_char_p(json_file_params)
        entity_path_p = None
        entity_path_len = 0

        if entity_path is not None and len(entity_path) > 0:
            entity_path_len = len(entity_path)
            entity_path_p = (c_char_p * entity_path_len)()
            for i, entry in enumerate(entity_path):
                entity_path_p[i] = cast(self.str_to_char_p(entry), c_char_p)

        result = self._function("StoreEntity")(
            handle_buf, file_path_buf, file_type_buf, persist, json_file_params_buf, entity_path_p, entity_path_len)

        del handle_buf
        del file_path_buf
        del file_type_buf
        del json_file_params_buf
        if entity_path_p is not None:
            for i in range(entity_path_len):
                entry_buf = entity_path_p[i]
                del entry_buf
            del entity_path_p
        return result

    def store_entity_to_memory(
        self, handle: str, file_type: str, json_file_params: str, entity_path: list[str] | None
    ) -> bytes | None:
        """Call ``StoreEntityToMemory``."""
        handle_buf = self.str_to_char_p(handle)
        data_p = c_void_p(None)
        data_len = c_size_t(0)
        file_type_buf = self.str_to_char_p(file_type)
        json_file_params_buf = self.str_to_char_p(json_file_params)
        entity_path_p = None
        entity_path_len = 0

        if entity_path is not None and len(entity_path) > 0:
            entity_path_len = len(entity_path)
            entity_path_p = (c_char_p * entity_path_len)()
            for i, entry in enumerate(entity_path):
                entity_path_p[i] = cast(self.str_to_char_p(entry), c_char_p)

        self._function("StoreEntityToMemory")(
            handle_buf, byref(data_p), byref(data_len), file_type_buf, False, json_file_params_buf,
            entity_path_p, entity_path_len)

        result = None
        if data_p.value is not None:
            result = string_at(data_p.value, data_len.value)
            self._function("DeleteString")(cast(data_p, c_char_p))

        del handle_buf
        del file_type_buf
        del json_file_params_buf
        if entity_path_p is not None:
            for i in range(entity_path_len):
                entry_buf = entity_path_p[i]
                del entry_buf
            del entity_path_p
        return result

    def destroy_entity(self, handle: str) -> None:
        """Call ``DestroyEntity``."""
        handle_buf = self.str_to_char_p(handle)

        self._function("DestroyEntity")(handle_buf)

        del handle_buf

    def set_random_seed(self, handle: str, rand_seed: str) -> bool:
        """Call ``SetRandomSeed``."""
        handle_buf = self.str_to_char_p(handle)
        rand_seed_buf = self.str_to_char_p(rand_seed)

        result = self._function("SetRandomSeed")(handle_buf, rand_seed_buf)

        del handle_buf
        del rand_seed_buf
        return result

    def get_entities(self) -> list[str]:
        """Call ``GetEntities``."""
        num_entities = c_uint64()
        entities = self._function("GetEntities")(byref(num_entities))
        result = [entities[i].decode() for i in range(num_entities.value)]

        del entities
        del num_entities
        return result

    def execute_entity_json(self, handle: str, label: str, json: str | bytes) -> bytes | None:
        """Call ``ExecuteEntityJsonPtr``."""
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        json_buf = self.str_to_char_p(json)

        result = self.char_p_to_bytes(self._function("ExecuteEntityJsonPtr")(
            handle_buf, label_buf, json_buf))

        del handle_buf
        del label_buf
        del json_buf
        return result

    def execute_entity_json_logged(
        self, handle: str, label: str, json: str | bytes
    ) -> tuple[bytes | None, bytes | None]:
        """Call ``ExecuteEntityJsonPtrLogged``."""
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        json_buf = self.str_to_char_p(json)

        c_result = self._function("ExecuteEntityJsonPtrLogged")(
            handle_buf, label_buf, json_buf)
        result = self.char_p_to_bytes(c_result.json), self.char_p_to_bytes(c_result.log)

        del handle_buf
        del label_buf
        del json_buf
        return result

    def eval_on_entity(self, handle: str, amlg: str | bytes) -> bytes | None:
        """Call ``EvalOnEntity``."""
        handle_buf = self.str_to_char_p(handle)
        amlg_buf = self.str_to_char_p(amlg)

        result = self.char_p_to_bytes(self._function("EvalOnEntity")(
            handle_buf, amlg_buf))

        del handle_buf
        del amlg_buf
        return result

    def get_version_string(self) -> bytes | None:
        """Call ``GetVersionString``."""
        return self.char_p_to_bytes(self._function("GetVersionString")())

    def get_concurrency_type_string(self) -> bytes | None:
        """Call ``GetConcurrencyTypeString``."""
        return self.char_p_to_bytes(self._function("GetConcurrencyTypeString")())
