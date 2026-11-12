"""Release-only archive boundaries; every payload here is synthetic, never extracted."""
from __future__ import annotations

import copy
import io
import stat
import tarfile
import zipfile

import pytest

from test_dist import checker as checker, make_wheel


REQUIRED = (
    'pyproject.toml', 'README.md', 'LICENSE', 'NOTICE', 'src/soulrun/__init__.py',
    'src/soulrun/soulrun_aiap/main.aisop.json', 'tests/conftest.py', 'tools/sync_engine.py',
    'tools/check_docs.py', 'GUIDE.md', 'INSTALL.md', 'docs/README.md', '.github/workflows/ci.yml',
)
PRIVATE = (
    '.env', '.env.local', 'auth.json', 'credentials.json', '.pypirc', '.netrc', '_netrc',
    '.claude/settings.json', '.codex/session.json', '.gemini/settings.json', '.opencode/session.json',
    'keys/private.pem', 'keys/private.key', 'keys/id_ed25519', 'debug.log', 'trace.private.json',
    '.cursor/local.json', '.vscode/settings.json', '.idea/local.xml', '.venv/lib/site.py',
    '.venv-tools/local.py', 'venv-tools/local.py', '.tox/local.py', '.nox/local.py',
    'release-dist/pkg.whl', 'release-dist-review/pkg.tar.gz', 'dist/pkg.whl', 'build/local.py',
    '.coverage.123', 'coverage.xml', 'AUTH.JSON', 'auth.json/nested.txt',
)


def source_archive(folder, extra=(), directories=()):
    path = folder / 'source.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        for name in REQUIRED:
            member = tarfile.TarInfo('soulrun-0/' + name)
            data = b'synthetic-only\n'
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        for name in directories:
            member = tarfile.TarInfo(name)
            member.type = tarfile.DIRTYPE
            archive.addfile(member)
        for member, data in extra:
            archive.addfile(member, io.BytesIO(data) if data is not None else None)
    return path


def regular(name, data=b'synthetic-only\n'):
    member = tarfile.TarInfo(name)
    member.size = len(data)
    return member, data


def rewrite_wheel(path, output, transform):
    with zipfile.ZipFile(path) as archive, zipfile.ZipFile(output, 'w') as target:
        for original in archive.infolist():
            for info, data in transform(copy.copy(original), archive.read(original)):
                target.writestr(info, data)
    return output


@pytest.mark.parametrize('variant', ['identical', 'first_sensitive', 'last_sensitive', 'engine'])
def test_duplicate_zip_members_are_rejected_before_the_name_can_hide_bytes(checker, tmp_path, variant):
    original = make_wheel(tmp_path)
    chosen = 'soulrun/soulrun_aiap/AIAP.md' if variant == 'engine' else 'soulrun/__init__.py'
    marker = ('\n# synthetic-only: ' + 'sk-' + 'A' * 40 + '\n').encode()
    assert checker.privacy_rules.credentials(marker.decode())

    def transform(info, data):
        if info.filename != chosen:
            return [(info, data)]
        first = data + marker if variant in {'first_sensitive', 'engine'} else data
        last = data + marker if variant == 'last_sensitive' else data
        return [(info, first), (copy.copy(info), last)]

    with pytest.warns(UserWarning, match='Duplicate name'):
        path = rewrite_wheel(original, tmp_path / 'duplicate.whl', transform)
    problems = checker.check_wheel(path)
    assert any('duplicate member' in line for line in problems)


@pytest.mark.parametrize('relative', PRIVATE)
@pytest.mark.parametrize('kind', ['wheel', 'source'])
def test_private_material_is_refused_by_path_even_without_a_known_token(checker, tmp_path, relative, kind):
    if kind == 'wheel':
        path = make_wheel(tmp_path, extra={'soulrun/' + relative: 'synthetic-only\n'})
        problems = checker.check_wheel(path)
    else:
        path = source_archive(tmp_path, [regular('soulrun-0/docs/' + relative)])
        problems = checker.check_sdist(path)
    assert any('secrets file' in line or 'private or local-configuration' in line for line in problems)


@pytest.mark.parametrize('relative', ['.env.example', 'settings.json', 'data/neutral.jsonl', 'public.pem.example'])
def test_safe_source_templates_and_neutral_data_still_pass(checker, tmp_path, relative):
    path = source_archive(tmp_path, [regular('soulrun-0/examples/' + relative)])
    assert checker.check_sdist(path) == []


def test_a_template_name_does_not_exempt_a_sensitive_body(checker, tmp_path):
    marker = ('sk-' + 'A' * 40).encode()
    path = source_archive(tmp_path, [regular('soulrun-0/examples/.env.example', marker)])
    assert any('credential' in line for line in checker.check_sdist(path))


@pytest.mark.parametrize('name', [
    'soulrun-0/docs/../../outside.txt', '/absolute.txt', 'soulrun-0/docs/./alias.txt',
    'soulrun-0/docs//alias.txt', 'soulrun-0/docs\\alias.txt', 'soulrun-0/C:' + '/alias.txt',
    'soulrun-0/docs/trailing.txt/',
])
def test_noncanonical_source_member_paths_are_rejected(checker, tmp_path, name):
    problems = checker.check_sdist(source_archive(tmp_path, [regular(name)]))
    assert any('unsafe member path' in line for line in problems)


@pytest.mark.parametrize('name', ['other-root/docs/note.txt', 'README.md'])
def test_source_members_cannot_change_or_omit_the_single_archive_root(checker, tmp_path, name):
    problems = checker.check_sdist(source_archive(tmp_path, [regular(name)]))
    assert any('source root' in line for line in problems)


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE])
def test_source_links_and_special_members_are_not_silently_skipped(checker, tmp_path, kind):
    member = tarfile.TarInfo('soulrun-0/docs/link-or-special')
    member.type, member.linkname = kind, '../../outside.txt'
    problems = checker.check_sdist(source_archive(tmp_path, [(member, None)]))
    assert any('link or special member' in line for line in problems)


def test_duplicate_source_members_are_rejected_even_when_the_bytes_match(checker, tmp_path):
    problems = checker.check_sdist(source_archive(tmp_path, [regular('soulrun-0/README.md')]))
    assert any('duplicate member' in line for line in problems)


def test_file_directory_alias_is_not_a_valid_source_archive(checker, tmp_path):
    problems = checker.check_sdist(source_archive(tmp_path, directories=['soulrun-0/README.md/']))
    assert any('duplicate member' in line for line in problems)


def test_normal_explicit_source_directories_still_pass(checker, tmp_path):
    path = source_archive(tmp_path, directories=['soulrun-0/', 'soulrun-0/docs/', 'soulrun-0/src/'])
    assert checker.check_sdist(path) == []


@pytest.mark.parametrize('directory', ['docs/.env.local/', 'tests/.codex/', 'examples/.venv-tools/'])
def test_empty_private_source_directories_are_also_refused(checker, tmp_path, directory):
    problems = checker.check_sdist(source_archive(tmp_path, directories=['soulrun-0/' + directory]))
    assert any('secrets file' in line or 'private or local-configuration' in line for line in problems)


@pytest.mark.parametrize('mode', [stat.S_IFLNK, stat.S_IFIFO])
def test_zip_type_flags_cannot_turn_a_package_file_into_a_link_or_special(checker, tmp_path, mode):
    original = make_wheel(tmp_path)

    def transform(info, data):
        if info.filename == 'soulrun/__init__.py':
            info.create_system = 3
            info.external_attr = (mode | 0o600) << 16
        return [(info, data)]

    path = rewrite_wheel(original, tmp_path / 'special.whl', transform)
    assert any('link or special member' in line for line in checker.check_wheel(path))


@pytest.mark.parametrize('name', ['soulrun/../escape.txt', '/absolute.txt', 'soulrun\\alias.txt', 'C:' + '/alias.txt'])
def test_noncanonical_zip_paths_are_rejected_as_structure_not_just_an_extra_file(checker, tmp_path, name):
    path = make_wheel(tmp_path)
    member = zipfile.ZipInfo(name)
    # ZipInfo's Windows constructor normalizes backslashes; the fixture must retain the raw name.
    member.filename = member.orig_filename = name
    with zipfile.ZipFile(path, 'a') as archive:
        archive.writestr(member, 'synthetic-only\n')
    problems = checker.check_wheel(path)
    assert any('unsafe member path' in line for line in problems)
