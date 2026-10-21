"""Types shared by the Amalgam native backends."""
from __future__ import annotations

from collections.abc import Sequence
import typing as t

Text: t.TypeAlias = str | bytes
"""Text passed to the engine: ``str`` is encoded as UTF-8, ``bytes`` is passed through."""

LoadStatusTuple: t.TypeAlias = tuple[bool, str | None, str | None, list[str | None]]
"""Load result: ``(loaded, message, version, entity_path)``."""


class NativeLibrary(t.Protocol):
    """Native backend that calls the Amalgam engine's C entry points."""

    def get_version_string(self) -> bytes | None:
        """Call ``GetVersionString``."""
        ...

    def get_concurrency_type_string(self) -> bytes | None:
        """Call ``GetConcurrencyTypeString``."""
        ...

    def is_sbf_datastore_enabled(self) -> bool:
        """Call ``IsSBFDataStoreEnabled``."""
        ...

    def set_sbf_datastore_enabled(self, enabled: bool, /) -> None:
        """Call ``SetSBFDataStoreEnabled``."""
        ...

    def get_max_num_threads(self) -> int:
        """Call ``GetMaxNumThreads``."""
        ...

    def set_max_num_threads(self, max_num_threads: int, /) -> None:
        """Call ``SetMaxNumThreads``."""
        ...

    def get_num_active_threads(self) -> int:
        """Call ``GetNumActiveThreads``."""
        ...

    def get_garbage_collection_params(self) -> bytes | None:
        """Call ``GetGarbageCollectionParams``."""
        ...

    def set_garbage_collection_params(self, json_params: Text, /) -> None:
        """Call ``SetGarbageCollectionParams``."""
        ...

    def get_json_from_label(self, handle: Text, label: Text, /) -> bytes | None:
        """Call ``GetJSONPtrFromLabel`` and return the JSON value."""
        ...

    def set_json_to_label(self, handle: Text, label: Text, json: Text, /) -> None:
        """Call ``SetJSONToLabel``."""
        ...

    def get_entity_permissions(self, handle: Text, /) -> bytes | None:
        """Call ``GetEntityPermissions``."""
        ...

    def set_entity_permissions(self, handle: Text, json_permissions: Text, /) -> bool:
        """Call ``SetEntityPermissions``."""
        ...

    def load_entity(
        self, handle: Text, file_path: Text, file_type: Text, persist: bool, json_file_params: Text,
        write_log: Text, print_log: Text, entity_path: Sequence[Text] | None, /
    ) -> LoadStatusTuple:
        """Call ``LoadEntity``."""
        ...

    def load_entity_from_memory(
        self, handle: Text, contents: bytes, file_type: Text, json_file_params: Text,
        write_log: Text, print_log: Text, entity_path: Sequence[Text] | None, /
    ) -> LoadStatusTuple:
        """Call ``LoadEntityFromMemory``."""
        ...

    def verify_entity(self, file_path: Text, /) -> LoadStatusTuple:
        """Call ``VerifyEntity``."""
        ...

    def clone_entity(
        self, handle: Text, clone_handle: Text, file_path: Text, file_type: Text, persist: bool,
        json_file_params: Text, write_log: Text, print_log: Text, /
    ) -> bool:
        """Call ``CloneEntity``."""
        ...

    def store_entity(
        self, handle: Text, file_path: Text, file_type: Text, persist: bool, json_file_params: Text,
        entity_path: Sequence[Text] | None, /
    ) -> bool:
        """Call ``StoreEntity``."""
        ...

    def store_entity_to_memory(
        self, handle: Text, file_type: Text, json_file_params: Text, entity_path: Sequence[Text] | None, /
    ) -> bytes | None:
        """Call ``StoreEntityToMemory`` and return the serialized entity."""
        ...

    def destroy_entity(self, handle: Text, /) -> None:
        """Call ``DestroyEntity``."""
        ...

    def set_random_seed(self, handle: Text, rand_seed: Text, /) -> bool:
        """Call ``SetRandomSeed``."""
        ...

    def get_entities(self) -> list[str]:
        """Call ``GetEntities`` and return the handles of the loaded entities."""
        ...

    def execute_entity_json(self, handle: Text, label: Text, json: Text, /) -> bytes | None:
        """Call ``ExecuteEntityJsonPtr`` and return the JSON response."""
        ...

    def execute_entity_json_logged(
        self, handle: Text, label: Text, json: Text, /
    ) -> tuple[bytes | None, bytes | None]:
        """Call ``ExecuteEntityJsonPtrLogged`` and return the JSON response and the transaction log."""
        ...

    def eval_on_entity(self, handle: Text, amlg: Text, /) -> bytes | None:
        """Call ``EvalOnEntity`` and return the result."""
        ...
