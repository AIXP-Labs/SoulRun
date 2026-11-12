"""Record92 R100: real command output, not merely expandable files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from test_round7_line_f import HEADER, KINDS, Run, _norm, _pause, _route, assert_joint_presentation


@pytest.fixture
def screen_env(subprocess_env):
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE', 'NUMBER_OF_PROCESSORS',
               'PROCESSOR_ARCHITECTURE', 'PYTHONPATH', 'PYTHONIOENCODING', 'PYTHONUTF8', 'PYTHONDONTWRITEBYTECODE',
               'TEMP', 'TMP', 'TMPDIR', 'HOME', 'USERPROFILE', 'USER', 'USERNAME', 'LOGNAME', 'SOULRUN_TEST_INSTALLED'}
    return {key: value for key, value in subprocess_env.items() if key.upper() in allowed}


def _paused(tmp_path, kind, setup, env):
    from soulrun import host

    run = Run(tmp_path / setup, kind, env)
    issued = _route(run)
    ticket = issued['dispatch']['ticket']
    record = json.loads((run.cache / f'_dispatch.{ticket}.json').read_text(encoding='utf-8'))
    if setup == 'reports_return':
        digest = hashlib.sha256(record['bootstrap'].encode('utf-8')).hexdigest()
        assert host.observe_agent_start(run.cache, digest, session_id='parent', tool_call_id='call-1',
                                        event_id='start-1', at='2030-01-01T00:00:00Z')['status'] == 'START_BOUND'
    paused = _pause(run, ticket)
    if setup == 'reports_return':
        assert host.observe_agent_return(run.cache, ticket, session_id='parent', tool_call_id='call-1',
                                         event_id='return-1', at='2030-01-01T00:01:00Z', status='completed',
                                         agent_id='child-agent-1')['status'] == 'RETURN_OBSERVED'
    elif setup == 'sdk':
        assert host.observe_agent_task_event(run.cache, session_id='parent', agent_id='child-task-1', tool_call_id='call-1',
                                             event_id='task-1', at='2030-01-01T00:01:00Z',
                                             event_type='task_notification', status='completed')['status'] == 'RETURN_UNVERIFIED'
    assert not run.menus(paused['gate']['question_id'])
    return run, paused


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('setup', ['command_line', 'reports_return', 'sdk'])
def test_returned_blocks_reach_main_reply_and_real_cli_in_ledger_order(tmp_path, kind, setup, screen_env):
    from soulrun import _records, _screen

    run, paused = _paused(tmp_path, kind, setup, screen_env)
    given = _records.read_delivered(run.cache)
    before = run.index()
    main, printed = run.cmd('next-node')
    _, expected = assert_joint_presentation(run, paused, before, main)
    assert _screen.refs_in(main) == expected, 'Pause must not jump ahead of returned plans and receipts'
    after = run.index()
    parts = []
    for ref in expected:
        body = run.text_of(ref).strip('\n')
        if _screen.SHOWN + ref not in given and _screen._seen(body) not in given:
            fragment = f'----- {ref}\n{body}\n----- end of {ref}'
            assert printed.count(fragment) == 1, 'Actual stdout must contain the exact block once'
            parts.append(printed.index(fragment))
    assert parts == sorted(parts) and len(parts) >= (4 if kind.startswith('scope') else 2)
    again, second = run.cmd('next-node')
    assert (again.get('dispatch') or {}).get('public_refs') == expected
    assert HEADER not in second and run.index() == after
    assert run.turn('1').returncode == 0
    answer = json.loads((run.cache / f"_gate.{paused['gate']['question_id']}.json").read_text(encoding='utf-8'))
    assert answer['resolution_kind'] == 'chosen'


@pytest.mark.parametrize('kind', KINDS)
def test_three_hosts_receive_identical_returned_public_text(tmp_path, kind, screen_env):
    from soulrun import _screen

    views = []
    for setup in ('command_line', 'reports_return', 'sdk'):
        run, paused = _paused(tmp_path, kind, setup, screen_env)
        before = run.index()
        main, _ = run.cmd('next-node')
        _, expected = assert_joint_presentation(run, paused, before, main)
        assert _screen.refs_in(main) == expected
        views.append([_norm(run.text_of(ref), run) for ref in _screen.refs_in(main)])
    assert views[0] == views[1] == views[2]


def test_returned_refs_keep_cap_waiting_order_and_exact_expand_output(soulrun, agent, tmp_path, screen_env):
    from soulrun import _records, _screen
    from test_screen import cli, start

    _, cache = start(screen_env, agent, tmp_path, 'returned-cap')
    public = Path(cache) / '_public'
    public.mkdir(exist_ok=True)
    refs = [f'⟦engine:{Path(cache).name}/{name}⟧' for name in ('plan.07.child.v1.txt', 'node.07.child.v1.txt')]
    bodies = ['plan body', 'receipt body ' * 3000]
    for ref, body in zip(refs, bodies, strict=True):
        (public / ref.split('/', 1)[1][:-1]).write_text(body, encoding='utf-8')
    reply = {'dispatch': {'public_refs': refs + refs}, 'public_block_ref': refs[-1]}
    assert _screen.refs_in(reply) == refs
    assert _screen.human_part(cache, reply, room=20).startswith(HEADER)
    assert _screen._waiting(_records.read_delivered(cache)) == refs
    first = cli(screen_env, agent, '--expand', refs[0], '--cache-dir', cache)
    assert f'----- {refs[0]}\n{bodies[0]}\n----- end of {refs[0]}' in first.stdout
    page = cli(screen_env, agent, '--expand', refs[1], '--cache-dir', cache)
    marker = '\n[more: run the same command with --offset '
    text, offset = page.stdout.rsplit(marker, 1)
    offset = int(offset.split(']')[0])
    last = cli(screen_env, agent, '--expand', refs[1], '--cache-dir', cache, '--offset', str(offset))
    assert marker not in last.stdout
    assert text + last.stdout == _screen.render([(refs[1], bodies[1])],
        'the text of the blocks asked for; print each on the screen where the program says to present its reference line, '
        'in full and exactly as written')
    assert _screen.human_part(cache, reply) is None


@pytest.mark.parametrize('bad', ['⟦engine:999/plan.07.other.v1.txt⟧', '⟦engine:1/../private.txt⟧',
                                '⟦engine:1/missing.txt⟧'])
@pytest.mark.parametrize('source', ['dispatch', 'previous_dispatch_publication'])
def test_unknown_return_refs_never_read_other_run_or_private_files(soulrun, agent, tmp_path, screen_env, bad, source):
    from soulrun import _screen
    from test_screen import start

    _, cache = start(screen_env, agent, tmp_path, 'bad-ref')
    foreign = Path(cache).parent / '999' / '_public'
    foreign.mkdir(parents=True)
    (foreign / 'plan.07.other.v1.txt').write_text('foreign run sentinel', encoding='utf-8')
    (Path(cache) / 'private.txt').write_text('private sentinel', encoding='utf-8')
    assert _screen.human_part(cache, {source: {'public_refs': [bad]}}) is None
    if bad.startswith('⟦engine:999/'):
        assert 'foreign run sentinel' in _screen.expand([bad], cache), 'Explicit historical expansion stays available'
