"""Canonical source bytes, current menus and same-version build isolation."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT
from helpers import HOST, QUESTION, commit, gate_payload, take_node


def tooling():
    spec = importlib.util.spec_from_file_location('canonical_sync_test', ROOT/'tools/sync_engine.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


@pytest.fixture
def canonical(tmp_path):
    source = ROOT/'src/soulrun/soulrun_aiap'
    copy = tmp_path/'canonical'
    shutil.copytree(source, copy, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    return copy


def test_canonical_source_is_selected_without_any_text_change(canonical, tmp_path):
    sync = tooling()
    assert sync.canonical_problems(canonical, '1.0.0') == []
    original = files(canonical)
    report = sync.stage_canonical(canonical, tmp_path/'staged', '1.0.0')
    assert report['texts'] == report['resealed'] == []
    assert files(tmp_path/'staged') == original
    assert (tmp_path/'staged/LICENSE').is_file() and (tmp_path/'staged/NOTICE').is_file()
    identity = (tmp_path/'staged/python_tools/lib/runtime_identity.py').read_text('utf-8')
    assert "inherited = '7.0.0-alpha.155'" in identity


@pytest.mark.parametrize('broken', ['LICENSE','NOTICE','python_tools/lib/runtime_identity.py','contracts/core.contract.json'])
def test_incomplete_or_drifted_canonical_source_is_refused(canonical, tmp_path, broken):
    p = canonical/broken
    p.write_bytes(b'changed')
    with pytest.raises(ValueError):
        tooling().stage_canonical(canonical, tmp_path/'staged', '1.0.0')
    assert not (tmp_path/'staged').exists()


def test_canonical_version_is_never_restamped(canonical, tmp_path):
    with pytest.raises(ValueError, match='never restamp'):
        tooling().stage_canonical(canonical, tmp_path/'staged', '1.0.1')


def current_repo(tmp_path):
    repo = tmp_path / 'repo'
    for name in ('src', 'tools'):
        shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for path in ROOT.glob('*.md'):
        shutil.copy2(path, repo / path.name)
    return repo


def upgrade(repo, *args):
    return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(repo/'tools/upgrade_engine.py'), *args],
                          capture_output=True, text=True, encoding='utf-8', timeout=120, cwd=repo)


def test_canonical_upgrade_and_restore_keep_every_original_byte(canonical, tmp_path):
    repo = current_repo(tmp_path)
    before = files(repo/'src/soulrun')
    notice = canonical/'NOTICE'
    notice.write_bytes(notice.read_bytes()+b'\nCanonical roundtrip fixture.\n')
    done = upgrade(repo, '--from', str(canonical), '--engine-version', '1.0.0', '--same-version')
    assert done.returncode == 0, done.stdout+done.stderr
    assert 'no texts changed, no resealing' in done.stdout
    assert files(repo/'src/soulrun/soulrun_aiap') == files(canonical)
    kept = [p for p in (repo/'.engine_backups').iterdir() if p.is_dir()]
    assert len(kept) == 1
    restored = upgrade(repo, '--restore', str(kept[0]))
    assert restored.returncode == 0, restored.stdout+restored.stderr
    assert files(repo/'src/soulrun') == before


def test_canonical_source_cannot_enter_the_legacy_cleaner(canonical, tmp_path):
    sys.path.insert(0, str(ROOT/'tools'))
    import clean_engine
    with pytest.raises(SystemExit, match='never rewrite'):
        clean_engine.build(canonical, tmp_path/'legacy', '1.0.0')
    assert not (tmp_path/'legacy').exists()


def test_interface_failure_is_before_replacement(canonical, tmp_path):
    repo = current_repo(tmp_path)
    core = canonical/'python_tools/lib/engine_core.py'
    text = core.read_text('utf-8')
    import re
    signature = re.search(r'def init_run\([^)]*\)', text, re.S).group(0)
    core.write_text(text.replace(signature, signature.replace('registry_roots', 'roots'), 1), encoding='utf-8')
    before = files(repo/'src/soulrun')
    done = upgrade(repo, '--from', str(canonical), '--engine-version', '1.0.0', '--same-version')
    assert done.returncode == 1 and 'Preflight failed; nothing was changed' in done.stdout
    assert files(repo/'src/soulrun') == before
    assert not (repo/'.engine_backups').exists()


def test_wording_failure_is_before_replacement(canonical, tmp_path):
    repo = current_repo(tmp_path)
    agent_py = tmp_path/'incomplete_agent.py'
    agent_py.write_text('X = 1\n', encoding='utf-8')
    notice = canonical/'NOTICE'
    notice.write_bytes(notice.read_bytes()+b'\nChanged source.\n')
    before = files(repo/'src/soulrun')
    done = upgrade(repo, '--from', str(canonical), '--engine-version', '1.0.0', '--same-version', '--agent-py', str(agent_py))
    assert done.returncode == 1 and 'fixed host wording is stale' in done.stdout
    assert files(repo/'src/soulrun') == before
    assert not (repo/'.engine_backups').exists()


def other_build(agent, ctx):
    """The run's note says another build of the same version began it (what an upgraded SoulRun finds)."""
    note = agent/'.soulrun_cache/.soulrun/runs'/f'{Path(ctx.cache_dir).name}.json'
    data = json.loads(note.read_text('utf-8'))
    data['engine_digest'] = '0'*64
    note.write_text(json.dumps(data), encoding='utf-8')


def test_same_version_different_build_cannot_resume(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id='old-build', **HOST)
    other_build(agent, ctx)
    before = files(Path(ctx.cache_dir))
    asked = soulrun(user_message='continue', session_id='old-build', **HOST)
    assert asked.kind == 'text_only' and asked.cache_dir is None
    assert asked.doubt['code'] == 'ENGINE_BUILD_MISMATCH' and asked.doubt['endable'] is True
    assert asked.doubt['recorded_digest'] == '0'*64
    assert [o['action'] for o in asked.doubt['options']] == ['call', 'ask', 'cancel']
    assert asked.doubt['options'][0]['arguments'] == {'user_message': '取消'}
    assert files(Path(ctx.cache_dir)) == before                         # asking changes nothing


def test_missing_build_record_does_not_authorize_resume(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id='no-build', **HOST)
    (agent/'.soulrun_cache/.soulrun/runs'/f'{Path(ctx.cache_dir).name}.json').unlink()
    before = files(Path(ctx.cache_dir))
    asked = soulrun(user_message='continue', session_id='no-build', **HOST)
    assert asked.doubt['code'] == 'ENGINE_BUILD_MISMATCH' and asked.doubt['recorded_digest'] is None
    assert 'has no record of the engine build' in asked.text
    assert files(Path(ctx.cache_dir)) == before


def test_an_option_number_is_answered_in_the_runs_own_language(soulrun, agent):
    """After an upgrade the first message is often the gate's option number: no language in it, so the run's own."""
    ctx = soulrun(user_message=QUESTION, session_id='old-build-number', **HOST)
    reply = commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ['demo_aiap', 'other_aiap'], 'demo_aiap'))
    assert reply['status'] == 'WAITING_USER'
    other_build(agent, ctx)
    asked = soulrun(user_message='1', session_id='old-build-number', **HOST)
    assert asked.doubt['code'] == 'ENGINE_BUILD_MISMATCH' and asked.text.startswith('这个对话有一场没做完的运行')
    assert '在等你回答' in asked.text and asked.doubt['user_language'] == 'zh'


def test_a_machine_turn_is_still_refused_for_a_run_of_another_build(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id='old-build-machine', **HOST)
    other_build(agent, ctx)
    before = files(Path(ctx.cache_dir))
    for message in ('continue', '取消'):                                # a machine message never ends it either
        with pytest.raises(soulrun.UsageError) as error:
            soulrun(user_message=message, session_id='old-build-machine', human_turn=False, **HOST)
        assert error.value.code == 'ENGINE_BUILD_MISMATCH'
    assert files(Path(ctx.cache_dir)) == before


def test_one_cancel_word_ends_a_run_of_another_build_without_running_it(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id='old-build-end', **HOST)
    other_build(agent, ctx)
    before = json.loads((Path(ctx.cache_dir)/'_index.json').read_text('utf-8'))
    asked = soulrun(user_message='取消，换个问题', session_id='old-build-end', **HOST)   # not one cancel word: asked again
    assert asked.doubt['code'] == 'ENGINE_BUILD_MISMATCH'
    ended = soulrun(user_message='取消', session_id='old-build-end', **HOST)
    assert ended.kind == 'text_only' and ended.doubt['code'] == 'ENGINE_BUILD_RUN_ENDED' and ended.doubt['options'] == []
    assert '已经结束' in ended.text
    after = json.loads((Path(ctx.cache_dir)/'_index.json').read_text('utf-8'))
    assert after['run_state'] == 'ABANDONED' and after['run_termination']['kind'] == 'human_termination'
    assert after['current'] == before['current'] and after['nodes'] == before['nodes']   # no node of it was run
    assert (Path(ctx.cache_dir)/'_public'/'ended.txt').is_file()
    fresh = soulrun(user_message=QUESTION, session_id='old-build-end', **HOST)
    assert fresh.kind == 'program' and fresh.entry_mode == 'fresh' and fresh.cache_dir != ctx.cache_dir


def test_a_run_of_another_engine_version_is_never_ended_here(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id='old-version', **HOST)
    other_build(agent, ctx)
    index = Path(ctx.cache_dir)/'_index.json'
    data = json.loads(index.read_text('utf-8'))
    data['engine_version'] = '7.0.0-alpha.155'
    index.write_text(json.dumps(data), encoding='utf-8')
    before = files(Path(ctx.cache_dir))
    asked = soulrun(user_message='取消', session_id='old-version', **HOST)
    assert asked.doubt['code'] == 'ENGINE_BUILD_MISMATCH' and asked.doubt['endable'] is False
    assert [o['action'] for o in asked.doubt['options']] == ['ask', 'cancel'] and '不能接着跑，也不能结束它' in asked.text
    assert files(Path(ctx.cache_dir)) == before


def test_nonhuman_message_cannot_answer_a_business_gate(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id='human-only', **HOST)
    reply = commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ['demo_aiap','other_aiap'], 'demo_aiap'))
    assert reply['status'] == 'WAITING_USER'
    before = files(Path(ctx.cache_dir))
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message='1', session_id='human-only', human_turn=False, **HOST)
    assert error.value.code == 'HUMAN_REPLY_REQUIRED'
    assert files(Path(ctx.cache_dir)) == before
    assert soulrun(user_message='1', session_id='human-only', **HOST).entry_mode == 'resume'


def test_old_menu_ref_cannot_mark_changed_question_delivered(soulrun, agent):
    from soulrun import host
    from test_full_host import FAR_FUTURE
    ctx = soulrun(user_message=QUESTION, session_id='menu-version', **HOST)
    host.open_restart_question(ctx.cache_dir, instance_started_at=FAR_FUTURE)
    first = host.open_question(ctx.cache_dir)
    store = host.engine('lib.run_store').RunStore(ctx.cache_dir)
    name = f"menu.{first['question_id']}.txt"
    store.write_public(name, first['text']+'\nThe current question has changed.\n')
    current = host.open_question(ctx.cache_dir)
    assert current['reference'] != first['reference']
    legacy = f"⟦engine:{Path(ctx.cache_dir).name}/{name}⟧"
    assert host._menu_in_reply(ctx.cache_dir, first['reference']) is None
    assert host._menu_in_reply(ctx.cache_dir, legacy) is None
    assert not host.open_question(ctx.cache_dir)['delivered']
    assert host._menu_in_reply(ctx.cache_dir, current['reference'])['status'] == 'DELIVERED'
