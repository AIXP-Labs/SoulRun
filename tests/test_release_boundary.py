"""Read-only release admission: source form is verified, never a cleaning waiver."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT
from legacy_snapshot import unpack


def tooling():
    spec = importlib.util.spec_from_file_location('release_sync_test', ROOT / 'tools/sync_engine.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root = tmp_path / 'package'
    engine = root / 'soulrun_aiap'
    shutil.copytree(ROOT / 'src/soulrun/soulrun_aiap', engine,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    manifest = root / 'engine_manifest.json'
    shutil.copy2(ROOT / 'src/soulrun/engine_manifest.json', manifest)
    sync = tooling()
    monkeypatch.setattr(sync, 'ENGINE', engine)
    monkeypatch.setattr(sync, 'MANIFEST', manifest)
    return sync, root


def re_record(sync, **overrides):
    record = sync.build_manifest(sync.ENGINE, 'test-only source')
    record.update(overrides)
    sync.MANIFEST.write_text(json.dumps(record), encoding='utf-8')


def test_canonical_release_accepts_original_bytes_without_cleaning(bundle):
    sync, root = bundle
    before = snapshot(root)
    assert sync.check_release() == []
    assert sync.main(['--check-release']) == 0
    assert snapshot(root) == before


def test_actual_cli_release_entry_is_read_only():
    before = snapshot(ROOT / 'src/soulrun')
    done = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/sync_engine.py'), '--check-release'],
                          capture_output=True, text=True, encoding='utf-8')
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'canonical' in done.stdout and 'OK' in done.stdout
    assert snapshot(ROOT / 'src/soulrun') == before


@pytest.mark.parametrize('form', [None, '', 'unknown', [], 1, False])
def test_missing_or_unknown_source_form_is_not_a_legacy_fallback(bundle, form):
    sync, root = bundle
    record = json.loads(sync.MANIFEST.read_text('utf-8'))
    if form is None:
        record.pop('source_form')
    else:
        record['source_form'] = form
    sync.MANIFEST.write_text(json.dumps(record), encoding='utf-8')
    before = snapshot(root)
    assert sync.check_release()
    assert sync.main(['--check-release']) == 1
    assert snapshot(root) == before


@pytest.mark.parametrize('damage', ['missing', 'json', 'list', 'duplicate', 'empty-files'])
def test_unverifiable_manifest_fails_closed(bundle, damage):
    sync, root = bundle
    if damage == 'missing':
        sync.MANIFEST.unlink()
    elif damage == 'json':
        sync.MANIFEST.write_text('{', encoding='utf-8')
    elif damage == 'list':
        sync.MANIFEST.write_text('[]', encoding='utf-8')
    elif damage == 'duplicate':
        sync.MANIFEST.write_text('{"source_form":"legacy-clean","source_form":"canonical"}', encoding='utf-8')
    else:
        re_record(sync, files={})
    before = snapshot(root)
    assert sync.check_release()
    assert snapshot(root) == before


@pytest.mark.parametrize('field,value', [
    ('file_count', 1), ('installed_file_count', 1), ('file_count', True),
    ('digest', '0' * 64), ('installed_digest', '0' * 64), ('engine_version', '9.0.0'),
])
def test_manifest_metadata_must_match_its_body(bundle, field, value):
    sync, _ = bundle
    re_record(sync, **{field: value})
    assert sync.check_release()


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'contracts/../escape', 'a\\b', 'a:b', './AIAP.md'])
def test_recorded_paths_cannot_escape_or_alias(bundle, path):
    sync, _ = bundle
    record = json.loads(sync.MANIFEST.read_text('utf-8'))
    record['files'][path] = '0' * 64
    sync.MANIFEST.write_text(json.dumps(record), encoding='utf-8')
    assert sync.check_release()


@pytest.mark.parametrize('name', ['AIAP.md', 'NOTICE', 'python_tools/lib/engine_core.py', 'contracts/core.contract.json'])
def test_drift_or_missing_files_fail_before_source_selection(bundle, name):
    sync, _ = bundle
    (sync.ENGINE / name).unlink()
    assert sync.check_release()


@pytest.mark.parametrize('case', ['identity', 'license', 'contract-digest', 'contract-empty', 'contract-path'])
def test_re_recording_outer_manifest_does_not_bypass_canonical_requirements(bundle, case):
    sync, _ = bundle
    if case == 'identity':
        path = sync.ENGINE / 'agent_card.json'
        record = json.loads(path.read_text('utf-8'))
        record['name'] = 'wrong'
        path.write_text(json.dumps(record), encoding='utf-8')
    elif case == 'license':
        (sync.ENGINE / 'LICENSE').write_text('not the declared license', encoding='utf-8')
    else:
        path = sync.ENGINE / 'contracts/manifest.json'
        record = json.loads(path.read_text('utf-8'))
        if case == 'contract-empty':
            record['files'] = {}
        elif case == 'contract-path':
            record['files']['../LICENSE'] = '0' * 64
        else:
            record['files']['core.contract.json'] = '0' * 64
        path.write_text(json.dumps(record), encoding='utf-8')
    re_record(sync, source_form='canonical')
    assert sync.check_release()


@pytest.mark.parametrize('name', ['.env', '.execution_cache/1/data.json', 'tests/private.py'])
def test_unshipped_or_secret_files_are_not_hidden_by_manifest_filters(bundle, name):
    sync, _ = bundle
    path = sync.ENGINE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('private', encoding='utf-8')
    assert sync.check_release()


def test_re_recorded_credential_is_still_refused(bundle):
    sync, _ = bundle
    path = sync.ENGINE / 'NOTICE'
    path.write_bytes(path.read_bytes() + ('\n' + 'ghp_' + 'A' * 36).encode())
    re_record(sync)
    assert any('credential' in item for item in sync.check_release())


def test_link_like_source_is_refused_before_reading(bundle, monkeypatch):
    sync, _ = bundle
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p.name == 'NOTICE' or original(p))
    assert any('link' in item for item in sync.check_release())


def test_canonical_label_cannot_be_downgraded_to_legacy(bundle):
    sync, _ = bundle
    re_record(sync, source_form='legacy-clean')
    assert any('canonical' in item for item in sync.check_release())


@pytest.mark.parametrize('dirty', [False, True])
def test_explicit_legacy_path_keeps_original_strict_checker(tmp_path, monkeypatch, dirty):
    engine = tmp_path / 'legacy'
    unpack(engine, 'src/soulrun/soulrun_aiap/')
    sync = tooling()
    monkeypatch.setattr(sync, 'ENGINE', engine)
    monkeypatch.setattr(sync, 'MANIFEST', tmp_path / 'engine_manifest.json')
    if dirty:
        path = engine / 'python_tools/lib/engine_core.py'
        path.write_bytes(path.read_bytes() + b'\n# new ' + b'alpha.' + b'123 marker\n')
    re_record(sync, source_form='legacy-clean')
    before = snapshot(tmp_path)
    assert bool(sync.check_release()) is dirty
    assert snapshot(tmp_path) == before


def test_canonical_rejection_never_invokes_legacy_fallback(bundle, monkeypatch):
    sync, _ = bundle
    monkeypatch.setattr(sync, 'canonical_problems', lambda *args: ['canonical identity refused'])
    sys.path.insert(0, str(ROOT / 'tools'))
    import clean_engine
    monkeypatch.setattr(clean_engine, 'check', lambda *args: pytest.fail('must not fall back to legacy'))
    assert 'canonical identity refused' in sync.check_release()


def test_linked_manifest_is_refused_before_its_content_is_read(bundle, monkeypatch):
    sync, _ = bundle
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == sync.MANIFEST or original(p))
    read_text = Path.read_text
    def checked_read(path, *args, **kwargs):
        assert path != sync.MANIFEST, 'must not read a linked manifest'
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', checked_read)
    assert sync.check_release()


def test_source_selection_flag_cannot_override_an_unknown_record(bundle):
    sync, _ = bundle
    re_record(sync, source_form='unknown')
    assert sync.main(['--check-release', '--canonical']) == 1


def test_changed_source_without_re_recording_is_rejected(bundle):
    sync, _ = bundle
    path = sync.ENGINE / 'python_tools/lib/engine_core.py'
    path.write_bytes(path.read_bytes() + b'\n# changed\n')
    assert any('changed:' in line for line in sync.check_release())
