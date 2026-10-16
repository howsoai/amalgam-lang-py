"""Tests for the shared real-library fixtures."""
from collections.abc import Callable
import json

from amalgam.api import Amalgam


def test_entity_file_labels(amlg: Amalgam, loaded_entity: str) -> None:
    """The test entity exposes the labels the suite relies on."""
    assert json.loads(amlg.execute_entity_json(loaded_entity, "hello_howso", "{}")) == "Hello Howso!"
    payload = {"a": [1, "x"]}
    assert json.loads(amlg.execute_entity_json(loaded_entity, "echo", json.dumps({"payload": payload}))) == payload
    assert json.loads(amlg.execute_entity_json(loaded_entity, "busy", json.dumps({"n": 10}))) == 10


def test_new_handle_returns_distinct_handles(amlg: Amalgam, new_handle: Callable[[], str]) -> None:
    """Handles from new_handle are distinct."""
    first, second = new_handle(), new_handle()
    assert first != second
