"""Synthetic local-file exclusions keep real source and safe templates visible; no Git is invoked."""
from pathlib import Path
import shutil

import pytest

from conftest import ROOT
from helpers import committed_files


def visible(tmp_path: Path, relative: str) -> bool:
    shutil.copy2(ROOT / '.gitignore', tmp_path / '.gitignore')
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'synthetic-only\n')
    return target in committed_files(tmp_path)


@pytest.mark.parametrize('relative', [
    '.env.local', '.env.production', 'nested/.env.test', '.pypirc', '.netrc', '_netrc',
    'auth.json', 'nested/credentials.json', '.codex/session.json', '.gemini/settings.json',
    '.opencode/session.json', 'keys/private.pem', 'keys/private.key', 'keys/id_ed25519',
    'debug.log', 'trace.private.json', '.coverage.123', 'coverage.xml',
    'release-dist/soulrun.whl', 'release-dist-review/soulrun.tar.gz', '.venv-tools/marker',
])
def test_local_sensitive_or_generated_material_is_not_a_source_input(tmp_path, relative):
    assert not visible(tmp_path, relative)


@pytest.mark.parametrize('relative', [
    '.env.example', 'nested/.env.example', 'README.md', 'README_CN.md', 'src/soulrun/host.py',
    'tests/test_docs.py', '.github/workflows/ci.yml', 'examples/minimal_host.py', 'docs/README.md',
    'examples/settings.json', 'examples/data/neutral.jsonl', 'examples/public.pem.example',
])
def test_templates_source_workflows_and_neutral_data_remain_visible(tmp_path, relative):
    assert visible(tmp_path, relative)
