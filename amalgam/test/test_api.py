from collections.abc import Callable
from io import BytesIO
import json
from pathlib import Path, WindowsPath
from platform import system
import warnings

from amalgam.api import Amalgam, LoadEntityStatus, ResultWithLog
import pytest
from pytest_mock import MockerFixture


@pytest.mark.parametrize('platform, arch, postfix, expected_path, expected_postfix', [
    ('', '', '', RuntimeError, '-mt'),
    ('linux', '', '', RuntimeError, '-mt'),
    ('darwin', 'aarch64_be', '-st', 'lib/darwin/arm64/amalgam-st.dylib', '-st'),
    ('darwin', 'aarch64', '-mt', 'lib/darwin/arm64/amalgam-mt.dylib', '-mt'),
    ('darwin', 'amd64', '', 'lib/darwin/amd64/amalgam-mt.dylib', '-mt'),
    ('darwin', 'arm64', '', 'lib/darwin/arm64/amalgam-mt.dylib', '-mt'),
    ('darwin', 'arm64', '-st', 'lib/darwin/arm64/amalgam-st.dylib', '-st'),
    ('linux', 'amd64', '-st', 'lib/linux/amd64/amalgam-st.so', '-st'),
    ('linux', 'arm64', '', 'lib/linux/arm64/amalgam-mt.so', '-mt'),
    ('linux', 'arm64', '-st', 'lib/linux/arm64/amalgam-st.so', '-st'),
    ('windows', 'amd64', '-st', 'lib/windows/amd64/amalgam-st.dll', '-st'),
    ('windows', 'arm64', '', RuntimeError, '-mt'),
    ('windows', 'amd64', '-mt', 'lib/windows/amd64/amalgam-mt.dll', '-mt'),
    ('windows', 'x86_64', '-st', 'lib/windows/amd64/amalgam-st.dll', '-st'),
])
def test_amalgam_library_path_defaults(
    mocker: MockerFixture, platform: str, arch: str, postfix: str, expected_path: str | type[Exception],
    expected_postfix: str
) -> None:
    """Test Amalgam._get_library_path is valid."""
    mocker.patch('amalgam.api.platform.system', return_value=platform)
    mocker.patch('amalgam.api.platform.machine', return_value=arch)
    mocker.patch('amalgam.api.Amalgam._get_allowed_postfixes', return_value=["-mt", "-st"])
    mocker.patch('amalgam.api.Path.exists', return_value=True)

    if system() == 'Windows' and expected_path is not RuntimeError:
        expected_path = str(WindowsPath(expected_path))

    try:
        library_path, library_postfix = Amalgam._get_library_path(library_postfix=postfix)
    except Exception as e:
        if not isinstance(expected_path, str):
            assert isinstance(e, expected_path), (
                f'Expected a {type(expected_path)}, but a {type(e)} was raised instead')
        else:
            raise
    else:
        assert isinstance(expected_path, str), (
            f'Expected {expected_path} to be raised.')
        assert str(library_path).endswith(expected_path)
        assert library_postfix == expected_postfix


@pytest.mark.parametrize('platform, arch, expected_postfix, should_raise', [
    ('linux', 'arm64', '-mt', False),
    ('linux', 'arm64_8a', '-st', False),
    ('linux', 'amd64', '-mt', False),
    ('linux', 'i386', '', True),
    ('darwin', 'amd64', '-mt', False),
    ('darwin', 'arm64', '-mt', False),
    ('darwin', 'arm64_8a', '', True),
    ('windows', 'amd64', '-mt', False),
    ('windows', 'i386', '', True),
    ('windows', 'arm64', '', True),
    ('solaris', 'amd64', '', True),
])
def test_get_library_path_arch(
    mocker: MockerFixture, platform: str, arch: str, expected_postfix: str, should_raise: bool
) -> None:
    """Test Amalgam._get_library_path arch is valid."""
    mocker.patch('amalgam.api.Path.exists', return_value=True)
    mocker.patch('amalgam.api.platform.system', return_value=platform)

    if should_raise:
        with pytest.raises(RuntimeError, match="unsupported machine"):
            Amalgam._get_library_path(arch=arch)
    else:
        _, postfix = Amalgam._get_library_path(arch=arch)
        assert postfix == expected_postfix


@pytest.mark.parametrize('postfix, allowed, expected_error', [
    ('', ['-st', '-mt'], None),
    ('-st', ['-st', '-mt'], None),
    ('-mt', ['-st', '-mt'], None),
    ('-omp', ['-mt', '-omp'], None),
    ('mt', ['-st', '-mt'], ValueError),
    ('-abc', ['-st', '-mt'], RuntimeError),
])
def test_get_library_path_postfix(
    mocker: MockerFixture, postfix: str, allowed: list[str], expected_error: type[Exception] | None
) -> None:
    """Test Amalgam._get_library_path postfix is valid."""
    mocker.patch('amalgam.api.Path.exists', return_value=False)
    mocker.patch('amalgam.api.platform.system', return_value="windows")
    mocker.patch('amalgam.api.platform.machine', return_value="amd64")
    mocker.patch('amalgam.api.Amalgam._get_allowed_postfixes', return_value=allowed)

    if expected_error:
        with pytest.raises(expected_error):
            Amalgam._get_library_path(library_postfix=postfix)
    else:
        # Since path.exists is patched to False, we should expect a FileNotFoundError
        with pytest.raises(FileNotFoundError):
            Amalgam._get_library_path(library_postfix=postfix)


@pytest.mark.parametrize('path_in, postfix_in, postfix, raise_warning', [
    ('/lib/windows/amd64/amalgam-mt.dll', '', '-mt', False),
    ('/lib/windows/amd64/amalgam-mt.dll', '-mt', '-mt', False),
    ('/lib/windows/amd64/amalgam-st.dll', '-mt', '-st', True),
])
def test_get_library_path_postfix_warns(
    mocker: MockerFixture, path_in: str, postfix_in: str, postfix: str, raise_warning: bool
) -> None:
    """Test that passing in conflicting paths and postfixes works correctly."""
    mocker.patch('amalgam.api.platform.system', return_value='windows')
    mocker.patch('amalgam.api.platform.machine', return_value='arm64')
    mocker.patch('amalgam.api.Path.exists', return_value=True)

    if raise_warning:
        with pytest.warns(UserWarning, match='and will be ignored.'):
            # Will fail if there are no warnings
            _, library_postfix = Amalgam._get_library_path(library_path=path_in, library_postfix=postfix_in)
    else:
        with warnings.catch_warnings():
            # Will fail if there are any warnings
            warnings.simplefilter('error')
            _, library_postfix = Amalgam._get_library_path(library_path=path_in, library_postfix=postfix_in)

    assert library_postfix == postfix


def test_logging_basic(amlg: Amalgam) -> None:
    """Standard execution lines quote and escape their arguments."""
    amlg.trace = BytesIO()
    amlg._log_execution_std(b"FOO", "bar", """{"baz": "quux"}""")
    assert amlg.trace.getvalue() == b"""FOO "bar" "{\\"baz\\": \\"quux\\"}"\n"""


def test_logging_suffix(amlg: Amalgam) -> None:
    """A suffix is appended unquoted."""
    amlg.trace = BytesIO()
    amlg._log_execution_std(b"FOO", "bar", suffix="""{"baz": "quux"}""")
    assert amlg.trace.getvalue() == b"""FOO "bar" {"baz": "quux"}\n"""


def test_logging_toggle_off_and_on(amlg: Amalgam) -> None:
    """Tracing can be suspended and resumed by assigning to `trace`."""
    first = BytesIO()
    amlg.trace = first
    amlg._log_execution(b"BEFORE")
    amlg.trace = None
    assert amlg.trace is None
    assert not first.closed
    amlg._log_execution(b"WHILE_OFF")
    amlg.trace = first
    amlg._log_execution(b"AFTER")
    assert first.getvalue() == b"BEFORE\nAFTER\n"


def test_logging_logged(amlg: Amalgam, loaded_entity: str) -> None:
    """The logged execution writes the command, timings, result, and log."""
    amlg.trace = BytesIO()
    result = amlg.execute_entity_json_logged(loaded_entity, "echo", b"""{"payload": {"foo": "bar"}}""")
    trace_lines = amlg.trace.getvalue().split(b"\n")
    amlg.trace = None
    assert isinstance(result, ResultWithLog)
    assert result.json == b'{"foo":"bar"}'
    assert result.log == b"(seq)"
    assert trace_lines[0].startswith(b"# TIME EXECUTION START")
    assert trace_lines[1] == (
        b'EXECUTE_ENTITY_JSON_LOGGED "' + loaded_entity.encode() + b'" "echo" {"payload": {"foo": "bar"}}')
    assert trace_lines[2].startswith(b"# TIME EXECUTION STOP")
    assert trace_lines[3] == b'# RESULT >{"foo":"bar"}'
    assert trace_lines[4] == b"# LOG >(seq)"
    assert trace_lines[5:] == [b""]


def test_set_max_num_threads_rejects_negative_untraced(amlg: Amalgam) -> None:
    """A negative thread count raises ValueError before anything is written to the trace."""
    trace = BytesIO()
    amlg.trace = trace
    with pytest.raises(ValueError):
        amlg.set_max_num_threads(-1)
    amlg.trace = None
    assert trace.getvalue() == b""


def test_public_api(
    amlg: Amalgam, loaded_entity: str, new_handle: Callable[[], str], tmp_path: Path
) -> None:
    """The public Amalgam methods return their documented types."""
    assert isinstance(amlg.get_version_string(), bytes)
    assert isinstance(amlg.get_concurrency_type_string(), bytes)
    assert loaded_entity in amlg.get_entities()
    amlg.set_json_to_label(loaded_entity, "hello_howso", json.dumps(["hello", "world"]))
    assert json.loads(amlg.get_json_from_label(loaded_entity, "hello_howso")) == ["hello", "world"]
    assert json.loads(amlg.execute_entity_json(loaded_entity, "echo", json.dumps({"payload": 1}))) == 1
    assert amlg.eval_on_entity(loaded_entity, "(+ 1 2)") == b"3"
    contents = amlg.store_entity_to_memory(loaded_entity, file_type="caml")
    assert isinstance(contents, bytes) and contents
    child = amlg.load_entity_from_memory(loaded_entity, contents, file_type="caml", entity_path=["child"])
    assert isinstance(child, LoadEntityStatus)
    assert child.loaded and child.entity_path == ["child"]
    assert amlg.store_entity(loaded_entity, str(tmp_path / "stored.caml"))
    assert amlg.verify_entity(str(tmp_path / "stored.caml")).loaded
    assert amlg.clone_entity(loaded_entity, new_handle())


def test_load_entity_failure_status(amlg: Amalgam, tmp_path: Path) -> None:
    """A missing entity file reports loaded=False with a message."""
    status = amlg.load_entity("missing", str(tmp_path / "missing.amlg"))
    assert status.loaded is False
    assert status.message
    assert status.entity_path == []
