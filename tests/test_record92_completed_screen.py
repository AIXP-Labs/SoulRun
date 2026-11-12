"""R100: a completed child is printed before the next main PLAN, without replay."""
from __future__ import annotations

import hashlib
import json

import pytest

from test_record92_return_screen import screen_env as screen_env
import test_round7_line_f as flow


@pytest.mark.parametrize('setup', ['command_line', 'reports_return', 'sdk'])
def test_completed_child_blocks_precede_next_main_plan(tmp_path, monkeypatch, setup, screen_env):
    import soulrun
    from soulrun import _engine, _records, _screen, host

    original = flow._program

    def fixed_program(kind):
        docs = original(kind)
        docs['main.aisop.json'][1]['content']['functions']['Start']['step1'] = 'Return the fixed result three.'
        return docs

    monkeypatch.setattr(flow, '_program', fixed_program)
    run = flow.Run(tmp_path / setup, 'node_hsaw_doubt', screen_env)
    ticket = flow._route(run)['dispatch']['ticket']
    binding = json.loads((run.cache / f'_dispatch.{ticket}.json').read_text(encoding='utf-8'))
    if setup == 'reports_return':
        digest = hashlib.sha256(binding['bootstrap'].encode('utf-8')).hexdigest()
        assert host.observe_agent_start(run.cache, digest, session_id='parent', tool_call_id='call-1',
                                        event_id='start-1', at='2030-01-01T00:00:00Z')['status'] == 'START_BOUND'
    served, _ = run.cmd('next-node', '--agent-ticket', ticket)
    finished = flow._commit(run, 'Start', served, ticket=ticket, output={'value': 3}, user_summary='Computed three.',
                            steps={'done': ['step1'], 'remaining': [], 'not_applicable': []},
                            user_message={'has': False, 'items': [], 'not_applicable': [],
                                          'none_reason': 'A fixed internal arithmetic receipt.'})
    assert finished['dispatch']['closed']
    if setup == 'reports_return':
        assert host.observe_agent_return(run.cache, ticket, session_id='parent', tool_call_id='call-1', event_id='return-1',
                                         at='2030-01-01T00:01:00Z', status='completed',
                                         agent_id='child-agent-1')['status'] == 'RETURN_OBSERVED'
    prior = run.index()
    core = _engine.load('lib.engine_core')
    store = _engine.load('lib.run_store').RunStore(run.cache)
    accepted = core._cache_path_for(store, prior, core._catalog_entry(prior, 'Start'), 1)
    unchanged = accepted.read_bytes(), accepted.stat().st_mtime_ns
    if setup == 'sdk':
        main = soulrun(cmd='next-node', cache_dir=run.cache).json()
        printed = _screen.human_part(run.cache, main)
    else:
        main, printed = run.cmd('next-node')
    expected = finished['dispatch']['public_refs']
    assert main['previous_dispatch_publication']['public_refs'] == expected
    assert _screen.refs_in(main) == [*expected, main['public_plan_ref']]
    body = run.text_of(finished['public_block_ref']).strip('\n')
    fragment = f"----- {finished['public_block_ref']}\n{body}\n----- end of {finished['public_block_ref']}"
    plan_ref = main['public_plan_ref']
    plan = f"----- {plan_ref}\n{run.text_of(plan_ref).strip(chr(10))}\n----- end of {plan_ref}"
    ordered = [*expected, plan_ref]
    waiting = _screen._waiting(_records.read_delivered(run.cache))
    if waiting:
        assert waiting == ordered[-len(waiting):]
    for ref in ordered:
        block = f"----- {ref}\n{run.text_of(ref).strip(chr(10))}\n----- end of {ref}"
        assert printed.count(block) == int(ref not in waiting)
        assert (_screen.SHOWN + ref in _records.read_delivered(run.cache)) == (ref not in waiting)
    if waiting:
        assert _screen.not_printed(waiting, run.cache) in printed
        args = [part for ref in waiting for part in ('--expand', ref)]
        expanded = run.soulrun(*args, '--cache-dir', str(run.cache))
        assert expanded.returncode == 0
        printed += expanded.stdout
        assert all(_screen.SHOWN + ref in _records.read_delivered(run.cache) for ref in waiting)
    assert printed.count(fragment) == 1 and printed.count(plan) == 1
    assert printed.index(fragment) < printed.index(plan)
    assert run.index()['completed'] == prior['completed']
    assert (accepted.read_bytes(), accepted.stat().st_mtime_ns) == unchanged
