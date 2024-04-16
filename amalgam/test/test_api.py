from pathlib import Path, WindowsPath
from platform import system
import warnings

from amalgam import api
from amalgam.api import Amalgam
import pytest


def resources_root():
    """Get resources root path."""
    return Path(Path(api.__file__).parent, "resources")


@pytest.fixture
def amalgam_factory(mocker):
    """Amalgam instance factory."""

    def _factory(*args, **kwargs):
        # Mock LoadLibrary so we do not attempt to load the actual amalgam
        # binaries. Path exists must also be mocked so the check that the
        # binaries exist is bypassed.
        mocker.patch('amalgam.api.cdll.LoadLibrary')
        mocker.patch('amalgam.api.Path.exists', return_value=True)
        return Amalgam(*args, **kwargs)

    return _factory


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
    mocker, amalgam_factory, platform, arch, postfix, expected_path,
    expected_postfix
):
    """Test Amalgam._get_library_path is valid."""
    mocker.patch('amalgam.api.platform.system', return_value=platform)
    mocker.patch('amalgam.api.platform.machine', return_value=arch)
    mocker.patch('amalgam.api.Amalgam._get_allowed_postfixes', return_value=["-mt", "-st"])

    if system() == 'Windows' and expected_path is not RuntimeError:
        expected_path = str(WindowsPath(expected_path))

    try:
        amlg = amalgam_factory(library_path=None, library_postfix=postfix)
    except Exception as e:
        if not isinstance(expected_path, str):
            assert isinstance(e, expected_path), (
                f'Expected a {type(expected_path)}, but a {type(e)} was raised instead')
        else:
            raise
    else:
        assert isinstance(expected_path, str), (
            f'Expected {expected_path} to be raised.')
        assert str(amlg.library_path).endswith(expected_path)
        assert amlg.library_postfix == expected_postfix


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
def test_get_library_path_arch(mocker, platform, arch, expected_postfix, should_raise):
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
def test_get_library_path_postfix(mocker, postfix, allowed, expected_error):
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
def test_get_library_path_postfix_warns(mocker, amalgam_factory, path_in,
                                        postfix_in, postfix, raise_warning):
    """Test that passing in conflicting paths and postfixes works correctly."""
    mocker.patch('amalgam.api.platform.system', return_value='windows')
    mocker.patch('amalgam.api.platform.machine', return_value='arm64')

    if raise_warning:
        with pytest.warns(UserWarning, match='and will be ignored.'):
            # Will fail if there are no warnings
            amlg = amalgam_factory(library_path=path_in,
                                   library_postfix=postfix_in)
    else:
        with warnings.catch_warnings():
            # Will fail if there are any warnings
            warnings.simplefilter('error')
            amlg = amalgam_factory(library_path=path_in,
                                   library_postfix=postfix_in)

    assert amlg.library_postfix == postfix
