from pathlib import Path
import pytest

from amalgam import api
from amalgam.api import Amalgam


def resources_root():
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
    ('windows', 'arm64', '', 'lib/windows/arm64/amalgam-mt.dll', '-mt'),
    ('windows', 'amd64', '-mt', 'lib/windows/amd64/amalgam-mt.dll', '-mt'),
    ('windows', 'x86_64', '-st', 'lib/windows/amd64/amalgam-st.dll', '-st'),


])
def test_get_library_path_defaults(mocker, amalgam_factory, platform, arch,
                                   postfix, expected_path, expected_postfix):
    """Test Amalgam._get_library_path is valid."""
    mocker.patch('amalgam.api.platform.system', return_value=platform)
    mocker.patch('amalgam.api.platform.machine', return_value=arch)

    try:
        amlg = amalgam_factory(library_path=None, library_postfix=postfix)
    except Exception as e:
        assert isinstance(e, expected_path), (
            f'Expected a RuntimeError, but a {type(e)} was raised instead')
    else:
        assert str(amlg.library_path).endswith(expected_path)
        assert amlg.library_postfix == expected_postfix


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
        with pytest.warns(UserWarning, match='and will be ignored.') as record:
            amlg = amalgam_factory(library_path=path_in,
                                   library_postfix=postfix_in)
    else:
        with pytest.warns(None) as record:
            amlg = amalgam_factory(library_path=path_in,
                                   library_postfix=postfix_in)
        assert not len(record)

    assert amlg.library_postfix == postfix
