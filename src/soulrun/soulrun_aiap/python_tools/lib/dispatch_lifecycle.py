"""Read-only local Provider receipts; never infer exit from ticket age or ACKs."""
from __future__ import annotations

from . import runtime_identity

import copy
import hashlib
import json
import re
from pathlib import Path
from .run_store import RunStoreError

PROVIDER_ROOT = Path.home()/'.claude/projects'
MAX_BYTES = 64 * 1024 * 1024


def returned(dispatch):
    return (dispatch or {}).get('lifecycle') == 'RETURNED' and bool(dispatch.get('exit_evidence'))


def replacement_accounting(index):
    match = runtime_identity.revision_match(index.get('engine_version', ''))
    return bool(match and int(match[1]) >= 155)


def unfinished_return(index, dispatch):
    """The caller is serving an unfinished root, not replaying a COMMITTED one."""
    return bool(replacement_accounting(index) and dispatch and dispatch.get('scope_root')
                and dispatch.get('state') == 'ABANDONED' and returned(dispatch))


def continuation_context(store, index):
    """A machine liveness recheck is not a new business answer or an execution permit."""
    if index['run_state'] == 'RUNNING':
        return index
    if index['run_state'] != 'WAITING_USER':
        raise ValueError('Continuation requires a running task.')
    rec = store.read_json(store.gate_path(index['gate']['question_id']))
    current = index['current']
    previous = rec.get('previous_gate') or {}
    if rec.get('dispatch_block') != 'DISPATCH_LIVENESS_UNKNOWN' or rec.get('source') != 'hsaw_doubt' \
            or rec.get('node') != current['name'] or rec.get('visit') != current['visit'] \
            or previous.get('state') != 'CLEAR' or rec.get('answered_at'):
        raise ValueError('An actual human gate or different machine condition still blocks execution.')
    return dict(index, run_state='RUNNING', gate=previous)


def continuation_state(store, index):
    """Current authorized task and accepted prefix, never a new human decision."""
    from . import engine_core as ec
    index = continuation_context(store, index)
    current = index['current']
    if not current or index['nodes'].get(ec._node_key(current['name'], current['visit']), {}).get('status') \
            in {'COMMITTED', 'DEGRADED', 'FAILED', 'COMPLETED', 'SKIPPED'}:
        raise ValueError('Only an unfinished current occurrence may continue.')
    ec._load_routed_program(ec._read_run_input(store))
    accepted = {}
    for key, row in index['nodes'].items():
        if row.get('cache_sha256'):
            name, _, visit = key.partition('@')
            path = ec._cache_path_for(store, index, ec._catalog_entry(index, name), int((visit or '1').removeprefix('v')))
            if hashlib.sha256(store.read_bytes(path)).hexdigest() != row['cache_sha256']:
                raise ValueError('Accepted prefix changed.')
            accepted[key] = row['cache_sha256']
    return dict(current=dict(current), input_sha256=hashlib.sha256(
        store.read_bytes(store.cache_dir / '_run_input.json')).hexdigest(), accepted=accepted,
        accepted_answer=ec._pending_gate_answer(store, index, current['name'], current['visit']))


def continuation_binding(store, index, formal):
    snapshot = formal.get('continuation')
    if not isinstance(snapshot, dict) or snapshot != continuation_state(store, index):
        raise ValueError('Continuation task or accepted prefix changed.')
    digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if f'continuation_state_sha256={digest}' not in formal['bootstrap'].splitlines():
        raise ValueError('Continuation snapshot is not bound to the issued bootstrap.')
    if formal.get('node') != index['current']['name'] or formal.get('visit') != index['current']['visit']:
        raise ValueError('Continuation occurrence changed.')
    return snapshot


def handoff(store, index, dispatch):
    """Read-only authority for replacing only an unstarted same-child continuation."""
    from . import engine_core as ec
    if not replacement_accounting(index) or not dispatch or dispatch.get('state') != 'ISSUED' \
            or dispatch.get('reason') not in {'gate_resume', 'segment_resume'} or dispatch.get('claimed_at') or returned(dispatch):
        return None
    target = dispatch.get('resume_executor') or {}
    history = dispatch.get('history') or []
    previous = history[-1] if history else None
    if not previous or previous.get('ticket') != target.get('previous_ticket') or not returned(previous) \
            or dispatch.get('replacement_count', 0) >= ec.DISPATCH_ATTEMPTS_MAX:
        return None
    try:
        for kind in ('task', 'task_start', 'return'):
            if store.exists_path(store.cache_dir/f'_dispatch_{kind}.{dispatch["ticket"]}.json'):
                return None
        delivery = failed_delivery(store, index, dispatch)
        if store.exists_path(store.cache_dir/f'_dispatch_start.{dispatch["ticket"]}.json') and not delivery:
            return None
        formal = store.read_json(store.dispatch_path(dispatch['ticket']))
        if formal.get('state', 'ISSUED') != 'ISSUED' or formal.get('claimed_at') \
                or formal.get('resume_executor') != target or formal.get('trace_id') != index['trace_id'] \
                or formal.get('scope_root') != dispatch.get('scope_root') \
                or formal.get('reason') != dispatch.get('reason') \
                or formal.get('bootstrap_sha256') != dispatch.get('bootstrap_sha256') \
                or hashlib.sha256(formal['bootstrap'].encode()).hexdigest() != dispatch['bootstrap_sha256']:
            return None
        proof = verify(store, previous)
        identity = resume_executor(store, previous)
        if not identity or identity != target or previous.get('scope_root') != dispatch.get('scope_root') \
                or proof.get('trace_id') != index['trace_id']:
            return None
        authority = dict(previous_ticket=previous['ticket'], unused_ticket=dispatch['ticket'],
            old_executor=target, return_evidence=previous['exit_evidence'],
            question_id=None, authority='returned_segment_unstarted_continuation')
        if dispatch['reason'] == 'segment_resume':
            call, result = proof.get('call') or {}, proof.get('result') or {}
            if proof.get('source') != 'host_agent_tool_return' or proof.get('tool_is_error') \
                    or call.get('source') != 'host_synchronous_agent_event' \
                    or call.get('trace_id') != index['trace_id'] or result.get('status') != 'completed' \
                    or not call.get('tool_call_id') or not call.get('event_id') or not result.get('event_id') \
                    or call.get('tool_call_id') != result.get('tool_call_id') \
                    or call.get('session_id') != result.get('session_id') \
                    or proof.get('bootstrap_sha256') != previous.get('bootstrap_sha256') \
                    or call.get('bootstrap_sha256') != previous.get('bootstrap_sha256') \
                    or (proof.get('public_artifacts') or {}).get('status') != 'SEALED':
                return None
            authority['continuation'] = continuation_binding(store, index, formal)
            if delivery:
                authority['delivery_failure'] = delivery
            return authority
        projection = dict(index)
        if index.get('run_state') == 'WAITING_USER':
            rec = store.read_json(store.gate_path(index['gate']['question_id']))
            if not rec.get('dispatch_block'):
                return None
            projection['gate'] = rec['previous_gate']
        current = index['current']
        answer = ec._pending_gate_answer(store, projection, current['name'], current['visit'])
        if not answer or formal.get('reason') != 'gate_resume':
            return None
        # This is execution-right fencing, not a claim that external processes died.
        authority['question_id'] = answer['question_id']
        if delivery:
            authority['delivery_failure'] = delivery
        return authority
    except (OSError, ValueError, KeyError, TypeError, ec.EngineError, RunStoreError):
        return None


def verify_handoff(store, index, dispatch):
    from . import engine_core as ec
    try:
        proof = dispatch['handoff']
        formal = store.read_json(store.dispatch_path(dispatch['ticket']))
        history = dispatch['history']
        unused, previous = history[-1], history[-2]
        current = index['current']
        segment = unused.get('reason') == 'segment_resume'
        if segment:
            snapshot = continuation_binding(store, index, store.read_json(store.dispatch_path(unused['ticket'])))
            if proof.get('question_id') is not None or proof.get('continuation') != snapshot \
                    or dispatch.get('reason') != 'segment_replacement':
                raise ValueError('Non-gate handoff authority changed.')
        else:
            answer = ec._pending_gate_answer(store, index, current['name'], current['visit'])
            if not answer or answer['question_id'] != proof['question_id'] or proof.get('continuation') \
                    or dispatch.get('reason') != 'gate_replacement':
                raise ValueError('Accepted gate authority changed.')
        if formal.get('handoff') != proof or unused['ticket'] != proof['unused_ticket'] \
                or previous['ticket'] != proof['previous_ticket'] or unused.get('state') != 'ABANDONED' \
                or unused.get('closed_reason') != ('segment_handoff' if segment else 'gate_handoff') or proof['authority'] != 'returned_segment_unstarted_continuation' \
                or previous.get('scope_root') != dispatch['scope_root'] \
                or previous.get('exit_evidence') != proof['return_evidence'] \
                or dispatch.get('replacement_count') != unused.get('replacement_count', 0)+1 \
                or not 1 <= dispatch.get('replacement_count', 0) <= ec.DISPATCH_ATTEMPTS_MAX:
            raise ValueError('handoff binding changed')
        returned_proof = verify(store, previous)
        if returned_proof.get('trace_id') != index['trace_id'] or resume_executor(store, previous) != proof['old_executor']:
            raise ValueError('returned executor changed')
        unused_formal = store.read_json(store.dispatch_path(unused['ticket']))
        if unused_formal.get('state') != 'ABANDONED' or unused_formal.get('claimed_at') \
                or unused_formal.get('reason') != unused.get('reason') \
                or unused_formal.get('trace_id') != index['trace_id'] \
                or unused_formal.get('scope_root') != dispatch.get('scope_root') \
                or unused_formal.get('resume_executor') != proof['old_executor'] \
                or unused_formal.get('bootstrap_sha256') != unused.get('bootstrap_sha256') \
                or hashlib.sha256(unused_formal['bootstrap'].encode()).hexdigest() != unused.get('bootstrap_sha256'):
            raise ValueError('unused ticket changed')
        delivery = failed_delivery(store, index, unused)
        if proof.get('delivery_failure') != delivery or (store.exists_path(
                store.cache_dir/f'_dispatch_start.{unused["ticket"]}.json') and not delivery):
            raise ValueError('delivery attempt changed')
        if any(store.exists_path(store.cache_dir/f'_dispatch_{kind}.{unused["ticket"]}.json')
               for kind in ('task', 'task_start', 'return')):
            raise ValueError('continuation has execution evidence')
    except (OSError, ValueError, KeyError, TypeError, ec.EngineError, RunStoreError) as exc:
        raise ec.EngineError('DISPATCH_HANDOFF_INVALID', 'Replacement evidence changed; no free claim or execution is allowed.') from exc


def failed_delivery(store, index, dispatch):
    """A failed SendMessage is delivery evidence, never physical-exit evidence."""
    try:
        path = store.cache_dir/f'_dispatch_resume_failure.{dispatch["ticket"]}.json'
        if not store.exists_path(path):
            return None
        raw = store.read_bytes(path)
        proof = json.loads(raw)
        start = store.read_json(store.cache_dir/f'_dispatch_start.{dispatch["ticket"]}.json')
        target = dispatch['resume_executor']
        expected = dict(source='host_send_message_failure', ticket=dispatch['ticket'],
            trace_id=index['trace_id'], bootstrap_sha256=dispatch['bootstrap_sha256'],
            session_id=target['session_id'], agent_id=target['agent_id'],
            tool_call_id=start['tool_call_id'], status='failed')
        if any(proof.get(k) != v for k, v in expected.items()) or not proof.get('event_id') \
                or not proof.get('at') or proof.get('start_event_id') != start.get('event_id') \
                or start.get('source') != 'host_synchronous_agent_event' \
                or any(start.get(k) != v for k, v in dict(ticket=dispatch['ticket'], trace_id=index['trace_id'],
                    bootstrap_sha256=dispatch['bootstrap_sha256'], session_id=target['session_id'],
                    resume_agent_id=target['agent_id']).items()):
            return None
        return dict(path=path.name, sha256=hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, KeyError, TypeError, RunStoreError):
        return None


def verify(store, dispatch):
    from . import engine_core as ec
    ref = dispatch.get('exit_evidence') or {}
    if ref.get('path') != f"_dispatch_return.{dispatch['ticket']}.json":
        raise ec.EngineError('DISPATCH_RETURN_EVIDENCE_CHANGED', 'Exit receipt must use its machine-owned cache path.')
    try:
        proof = store.read_json(store.cache_dir/ref['path'])
    except (OSError, ValueError) as exc:
        raise ec.EngineError('DISPATCH_RETURN_EVIDENCE_CHANGED', 'Exit receipt cannot be read.') from exc
    if hashlib.sha256(json.dumps(proof, ensure_ascii=False, sort_keys=True).encode()).hexdigest() != ref.get('sha256') \
            or proof.get('ticket') != dispatch['ticket'] or proof.get('scope_root') != dispatch['scope_root']:
        raise ec.EngineError('DISPATCH_RETURN_EVIDENCE_CHANGED', 'Preserved exit receipt changed; do not reissue.')
    return proof


def resume_executor(store, dispatch):
    """No native identity source is qualified by default in this release.

    Existing receipts remain diagnostic evidence. Neither host-reported fields nor
    rewritten receipt/index pairs can authorize original-child continuation.
    Re-enabling a source requires a separate human-reviewed host qualification.
    """
    return None


def reported_executor(store, dispatch):
    """Read the reported identity for diagnostics, never execution authority."""
    if returned(dispatch):
        proof = verify(store, dispatch)
        agent = proof.get('agent_id')
        parent = (proof.get('result') or {}).get('session_id')
        if proof.get('source') == 'host_agent_tool_return' and not proof.get('tool_is_error') \
                and isinstance(agent, str) and re.fullmatch(r'[A-Za-z0-9_-]{8,80}', agent) and parent:
            return dict(agent_id=agent, session_id=parent, previous_ticket=dispatch['ticket'])
        return None
    index = store.read_index()
    if not pause_continuation(index) or not accepted_pause(store, index, dispatch):
        return None
    return _started_executor(store, index, dispatch)


def failed_return(store, dispatch):
    """docs/05SoulRun 84: the root's child came back through the host's Agent tool with an error (its model supply cut
    off mid-scope, a usage limit say). The return is verified; nothing in it shows the scope finished."""
    from . import engine_core as ec
    if not returned(dispatch):
        return None
    try:
        proof = verify(store, dispatch)
    except ec.EngineError:
        return None
    return proof if proof.get('source') == 'host_agent_tool_return' and proof.get('tool_is_error') is True else None


def _settled(store, index):
    """docs/05SoulRun 87: the run as it stood when an engine dispatch stop opened, so the business answer that the
    stopped continuation resumes stays visible while that stop is active."""
    if index.get('run_state') != 'WAITING_USER':
        return index
    rec = store.read_json(store.gate_path(index['gate']['question_id']))
    return dict(index, gate=rec['previous_gate']) if rec.get('dispatch_block') else index


def failed_pause(store, index, dispatch):
    """docs/05SoulRun 87: the root's child paused at a gate inside its scope (its ticket stays CLAIMED), the gate was
    answered, and then its Agent call came back with an error: the pause is accepted, the child cannot be resumed."""
    try:
        return bool(replacement_accounting(index) and dispatch and dispatch.get('scope_root')
                    and dispatch.get('state') == 'CLAIMED' and dispatch.get('paused_at') and returned(dispatch)
                    and accepted_pause(store, _settled(store, index), dispatch))
    except (OSError, ValueError, KeyError, TypeError, RunStoreError):
        return False


def replacement_basis(store, index, dispatch):
    """What a human may choose instead of a resume that cannot happen: one new child for an unfinished root whose child
    returned with an error and has no trusted identity to resume - also when it had paused at an answered gate first
    (docs/05SoulRun 87) - while a replacement is left. None otherwise - a child that can be resumed keeps being resumed,
    and nothing is ever replaced without the human's choice (human_replacement)."""
    from . import engine_core as ec
    if not (unfinished_return(index, dispatch) or failed_pause(store, index, dispatch)) \
            or resume_executor(store, dispatch) or not failed_return(store, dispatch):
        return None
    # docs/05SoulRun 87: owner ruling 352 §8 item 2 - a replacement takes no dispatch attempt; its own count bounds it.
    if int(dispatch.get('replacement_count') or 0) >= ec.DISPATCH_ATTEMPTS_MAX:
        return None
    return dict(ticket=dispatch['ticket'], attempt=dispatch.get('attempt'), scope_root=copy.deepcopy(dispatch.get('scope_root')),
                exit_evidence=copy.deepcopy(dispatch.get('exit_evidence')))


def _evidence_ref(store, name):
    path = store.cache_dir/name
    return dict(path=name, sha256=hashlib.sha256(store.read_bytes(path)).hexdigest()) if store.exists_path(path) else None


def interrupted_basis(store, index, dispatch):
    """docs/05SoulRun 87 (owner ruling 10-28 on record 86 #5): what a human may choose when a host restart or recovery
    re-entry left the liveness of the ticket's child unknown - one new child, with the risks stated on the stop. Only
    when the re-entry recorded the interruption, no verified return exists, the one bounded return query was already
    offered where the host has one, and a replacement is left. Bound to the ticket, its attempt, the interruption
    record, its start evidence and the query; the engine never treats it as proof that the old child stopped."""
    from . import dispatch_scope, engine_core as ec
    if not replacement_accounting(index) or not dispatch_scope.enabled(index) or not dispatch \
            or not dispatch.get('scope_root') or dispatch.get('state') not in ('ISSUED', 'CLAIMED') or returned(dispatch) \
            or (dispatch.get('interruption_observation') or {}).get('physical_exit') != 'UNVERIFIED' \
            or int(dispatch.get('replacement_count') or 0) >= ec.DISPATCH_ATTEMPTS_MAX:
        return None
    try:
        query = _evidence_ref(store, f"_dispatch_query.{dispatch['ticket']}.json")
        if not query and _started_executor(store, index, dispatch):
            return None  # a same-child resume the host may still answer for: its bounded return query comes first
        start = _evidence_ref(store, f"_dispatch_start.{dispatch['ticket']}.json")
    except (OSError, ValueError, KeyError, TypeError, RunStoreError):
        return None
    return dict(ticket=dispatch['ticket'], attempt=dispatch.get('attempt'), scope_root=copy.deepcopy(dispatch['scope_root']),
                interruption_observation=copy.deepcopy(dispatch['interruption_observation']), start_evidence=start,
                return_query=query)


def offered_basis(store, index, dispatch, block):
    """The replacement an engine dispatch stop of this kind may offer (docs/05SoulRun 84, 87), or None."""
    if block == 'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE':
        return replacement_basis(store, index, dispatch)
    if block == 'DISPATCH_LIVENESS_UNKNOWN':
        return interrupted_basis(store, index, dispatch)
    return None


def last_commit_at(store, index, dispatch):
    """The time of the last commit (a node commit or a gate pause) accepted under this ticket, read from the accepted
    node caches' machine records; None when there is none. Not last_progress_at: that also moves on every next-node
    --agent-ticket re-serve of a claimed child (review of docs/05SoulRun 87, C2). A cache that cannot be read or no
    longer matches its accepted digest is left out, so the bound can only be earlier - more requests listed, never fewer."""
    from . import engine_core as ec
    latest = None
    for key, node in index['nodes'].items():
        if not node.get('cache_sha256'):
            continue
        name, _, visit = key.partition('@')
        try:
            raw = store.read_bytes(ec._cache_path_for(store, index, ec._catalog_entry(index, name),
                                                      int((visit or '1').removeprefix('v'))))
            if hashlib.sha256(raw).hexdigest() != node['cache_sha256']:
                continue
            cache = json.loads(raw)
            for row in [cache, *(cache.get('continuations') or [])]:
                machine = row.get('machine') or {}
                if (machine.get('dispatch') or {}).get('ticket') == dispatch['ticket'] and machine.get('committed_at'):
                    latest = progress_time(machine['committed_at'], latest)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ec.EngineError, RunStoreError):
            continue
    return latest


def requests_since_progress(store, index, dispatch, limit=20):
    """docs/05SoulRun 87: the host-recorded child tool requests of this ticket after its last accepted commit, or its
    claim when it has none - tool, target path and whether a result was recorded; never their contents. A re-serve of
    the claimed child is not a commit and hides nothing (review C2). A request is not proof of a write, and what the
    host did not record cannot be listed."""
    from .engine_core import _parse_ts
    committed = last_commit_at(store, index, dispatch)
    since = progress_time(dispatch.get('claimed_at'), committed) if dispatch.get('claimed_at') or committed else None
    rows = []
    try:
        for path in sorted(store.cache_dir.glob(f"_dispatch_tool.{dispatch['ticket']}.*.json")):
            request = store.read_json(path)
            if request.get('source') != 'host_sdk_child_tool_request' or request.get('ticket') != dispatch['ticket']:
                continue
            if since and request.get('at') and _parse_ts(request['at']) <= _parse_ts(since):
                continue
            raw = request.get('raw_input') if isinstance(request.get('raw_input'), dict) else {}
            target = next((raw[k] for k in ('file_path', 'notebook_path', 'path') if isinstance(raw.get(k), str)), None)
            rows.append(dict(tool=request.get('tool_name'), target=target, at=request.get('at'), ref=path.name,
                             returned=store.exists_path(path.with_name(path.name.replace('_dispatch_tool.', '_dispatch_tool_result.', 1)))))
    except (OSError, ValueError, KeyError, TypeError, RunStoreError):
        return None
    rows.sort(key=lambda r: str(r['at']))
    return dict(count=len(rows), rows=rows[:limit], since=since)


def human_replacement(store, index, dispatch):
    """The human's recorded choice of a new child for exactly this return (docs/05SoulRun 84) or this interrupted
    ticket (docs/05SoulRun 87), recomputed against the evidence now; or None."""
    authority = (dispatch or {}).get('human_replacement')
    if not isinstance(authority, dict) or authority.get('previous_ticket') != dispatch.get('ticket'):
        return None
    try:
        rec = store.read_json(store.gate_path(authority['question_id']))
    except (OSError, ValueError, KeyError, TypeError, RunStoreError):
        return None
    basis = offered_basis(store, index, dispatch, rec.get('dispatch_block'))
    if not basis or authority.get('basis') != basis or rec.get('replacement_basis') != basis \
            or rec.get('chosen_intent') != 'replace_executor' or not rec.get('answered_at') \
            or rec.get('replacement_authorization') != authority:
        return None
    return authority


def lapse_facts(store, index, dispatch):
    """Review of docs/05SoulRun 87, rounds 3-4 (D2, E5): what an engine stop records and says about the human's accepted
    choice to retire this ticket that was not carried out - the choice, the ticket it was to retire, the return recorded
    after it (if any), and what the host recorded after the choice that changed its basis (recorded_after): the old
    agent's return or error return, its start, a new interruption, the return query; 'changed' when none of these."""
    authority = dispatch['human_replacement']
    basis = authority.get('basis') or {}
    after = []
    if returned(dispatch):
        after.append('error_return' if failed_return(store, dispatch) else 'return')
    else:
        if dispatch.get('interruption_observation') != basis.get('interruption_observation'):
            after.append('interruption')
        try:
            if basis.get('start_evidence') is None and _evidence_ref(store, f"_dispatch_start.{dispatch['ticket']}.json"):
                after.append('start')
            if _evidence_ref(store, f"_dispatch_query.{dispatch['ticket']}.json") != basis.get('return_query'):
                after.append('query')
        except (OSError, ValueError, KeyError, TypeError, RunStoreError):
            pass
    return dict(question_id=authority['question_id'], previous_ticket=dispatch['ticket'],
                exit_evidence=copy.deepcopy(dispatch.get('exit_evidence')), recorded_after=after or ['changed'])


_LAPSE_WORDS = {'return': ('旧代理的返回', "the old agent's return"),
                'error_return': ('旧代理带着错误返回', 'that the old agent came back with an error'),
                'start': ('旧代理的启动（选择时没见到它启动过）', "the old agent's start (it had not been seen starting when the choice was made)"),
                'interruption': ('又一次中断（宿主再次重启或恢复重入）', 'another interruption (a further host restart or recovery re-entry)'),
                'query': ('一次返回查询', 'a return query'),
                'changed': ('新的记录', 'new records')}


def lapse_words(facts, *, zh):
    """Round 4 (E5): what the host recorded after the choice, in plain words."""
    words = [_LAPSE_WORDS.get(k, _LAPSE_WORDS['changed'])[0 if zh else 1]
             for k in (facts or {}).get('recorded_after') or ['changed']]
    return ('、' if zh else ' and ').join(words)


def lapsed_replacement(store, index, dispatch):
    """Review of docs/05SoulRun 87, rounds 3-4 (D2, E3, E5): the human's accepted choice to retire this interrupted ticket
    and continue with a new agent that was not carried out - the authority is still on the ticket it was to retire, so no
    replacement was issued - and no longer verifies: after the choice the host recorded the old agent's return (or error
    return), its start or a new interruption; or None. While it stands, every engine stop for this part says so
    (dispatch_budget.pause) and nothing is issued or run inline for the part (engine_core._unlapsed). The human
    acknowledges it by choosing Recheck conditions at a later stop of the same node and visit whose record disclosed it
    (the same choice and ticket): exactly one continuation follows, and no stop asks about that choice again."""
    authority = (dispatch or {}).get('human_replacement')
    if not isinstance(authority, dict) or authority.get('previous_ticket') != dispatch.get('ticket') \
            or 'interruption_observation' not in (authority.get('basis') or {}) \
            or human_replacement(store, index, dispatch):
        return None
    try:
        chosen = store.read_json(store.gate_path(authority['question_id']))
    except (OSError, ValueError, KeyError, TypeError, RunStoreError):
        chosen = {}   # unreadable: no later answer can be bound to it, so none acknowledges it

    def discloses(rec):
        told = rec.get('lapsed_replacement') or {}
        return bool(chosen) and rec.get('source') == 'hsaw_doubt' and (rec.get('node'), rec.get('visit')) == \
            (chosen.get('node'), chosen.get('visit')) and told.get('question_id') == authority['question_id'] \
            and told.get('previous_ticket') == dispatch['ticket']
    after = False
    for row in index['gate']['history']:
        if row.get('question_id') == authority['question_id']:
            after = True
            continue
        if not after or row.get('source') != 'hsaw_doubt' or row.get('resolution_kind') != 'chosen':
            continue
        try:
            rec = store.read_json(store.gate_path(row['question_id']))
        except (OSError, ValueError, KeyError, TypeError, RunStoreError):
            continue   # unreadable: not taken as the human's answer
        if rec.get('chosen_intent') == 'recheck_dispatch' and rec.get('answered_at') and discloses(rec):
            return None
    return authority


def unused_replacement(store, index, rec):
    """Review of docs/05SoulRun 87, round 3 (D2): for an answered engine stop whose replace_executor choice was accepted,
    why that choice replaced nothing; None when its replacement was issued (or the choice was refused, N2). Derived from
    the records, never written back: the ticket it was to retire was never closed by a human replacement, or a later
    accepted choice for the same ticket is the one its replacement carried."""
    authority = rec.get('replacement_authorization')
    if rec.get('chosen_intent') != 'replace_executor' or not isinstance(authority, dict):
        return None
    ticket = authority.get('previous_ticket')
    rows = [row for node in index['nodes'].values() for row in
            [node.get('dispatch') or {}, *((node.get('dispatch') or {}).get('history') or [])] if row.get('ticket') == ticket]
    if any(row.get('closed_reason') == 'human_replacement' for row in rows):
        after = False
        for row in index['gate']['history']:
            if row['question_id'] == rec.get('question_id'):
                after = True
            elif after and row.get('source') == 'hsaw_doubt' and row.get('resolution_kind') == 'chosen':
                later = store.read_json(store.gate_path(row['question_id']))
                if later.get('chosen_intent') == 'replace_executor' \
                        and (later.get('replacement_authorization') or {}).get('previous_ticket') == ticket:
                    break
        else:
            return None   # the last accepted choice for that ticket: its replacement carried it
    return dict(reason='DISPATCH_REPLACEMENT_LAPSED',
                old_return_recorded_after_choice='interruption_observation' in (authority.get('basis') or {})
                and any(returned(row) for row in rows))


def verify_human_replacement(store, index, dispatch):
    """docs/05SoulRun 87: the claim of a human-chosen replacement checks once, against the ticket it retired and the
    answered stop, that the authority is unchanged. It buys no attempt, and no new task quota for a part that already
    holds its charge (owner ruling 352 §8 item 2; dispatch_budget.part_charged); the claim moves the ticket on, so it
    cannot be used twice."""
    from . import engine_core as ec
    try:
        authority, history = dispatch['human_replacement'], dispatch['history']
        previous, basis = history[-1], authority['basis']
        rec = store.read_json(store.gate_path(authority['question_id']))
        formal = store.read_json(store.dispatch_path(dispatch['ticket']))
        if dispatch.get('reason') != 'human_replacement' or formal.get('reason') != 'human_replacement' \
                or formal.get('state', 'ISSUED') != 'ISSUED' or formal.get('claimed_at') \
                or formal.get('bootstrap_sha256') != dispatch.get('bootstrap_sha256') \
                or previous.get('ticket') != authority.get('previous_ticket') or basis.get('ticket') != previous['ticket'] \
                or basis.get('attempt') != previous.get('attempt') or basis.get('scope_root') != previous.get('scope_root') \
                or previous.get('scope_root') != dispatch.get('scope_root') \
                or previous.get('state') != 'ABANDONED' \
                or previous.get('closed_reason') not in (('human_replacement',) if 'interruption_observation' in basis
                                                         else (None, 'human_replacement')) \
                or dispatch.get('replacement_count') != int(previous.get('replacement_count') or 0) + 1 \
                or not 1 <= dispatch['replacement_count'] <= ec.DISPATCH_ATTEMPTS_MAX \
                or rec.get('dispatch_block') not in ('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'DISPATCH_LIVENESS_UNKNOWN') \
                or rec.get('chosen_intent') != 'replace_executor' or not rec.get('answered_at') \
                or rec.get('replacement_authorization') != authority or rec.get('replacement_basis') != basis:
            raise ValueError('replacement authority changed')
        if 'exit_evidence' in basis:
            if previous.get('exit_evidence') != basis['exit_evidence'] or not failed_return(store, previous):
                raise ValueError('failed return changed')
        elif store.read_json(store.dispatch_path(previous['ticket'])).get('interruption_observation') != basis['interruption_observation'] \
                or _evidence_ref(store, f"_dispatch_start.{previous['ticket']}.json") != basis['start_evidence'] \
                or _evidence_ref(store, f"_dispatch_query.{previous['ticket']}.json") != basis['return_query']:
            raise ValueError('interruption evidence changed')
    except (OSError, ValueError, KeyError, TypeError, IndexError, ec.EngineError, RunStoreError) as exc:
        raise ec.EngineError('DISPATCH_REPLACEMENT_INVALID', 'Replacement authority changed; no claim or execution is allowed.') from exc


def _started_executor(store, index, dispatch, seen=frozenset()):
    # A trusted SendMessage start already binds the same child. It is not an exit receipt.
    from . import engine_core as ec
    if dispatch['ticket'] in seen:
        return None
    seen = seen | {dispatch['ticket']}
    try:
        rec = store.read_json(store.dispatch_path(dispatch['ticket']))
        start = store.read_json(store.cache_dir/f"_dispatch_start.{dispatch['ticket']}.json")
        target = rec.get('resume_executor') or {}
        if not target or target != dispatch.get('resume_executor') \
                or rec.get('trace_id') != index['trace_id'] or rec.get('scope_root') != dispatch['scope_root'] \
                or rec.get('bootstrap_sha256') != dispatch.get('bootstrap_sha256') \
                or hashlib.sha256(rec['bootstrap'].encode()).hexdigest() != rec['bootstrap_sha256'] \
                or start.get('source') != 'host_synchronous_agent_event' \
                or any(start.get(k) != v for k, v in dict(ticket=dispatch['ticket'], trace_id=index['trace_id'],
                    bootstrap_sha256=rec['bootstrap_sha256'], session_id=target['session_id'], resume_agent_id=target['agent_id']).items()) \
                or not all(start.get(k) for k in ('tool_call_id','event_id','at')):
            return None
        rows = [r for node in index['nodes'].values() for r in
                ([node.get('dispatch') or {}] + (node.get('dispatch') or {}).get('history', []))
                if r.get('ticket') == target['previous_ticket']]
        previous = rows[0] if len(rows) == 1 else None
        identity = (resume_executor(store, previous) if returned(previous) else
                    _started_executor(store, index, previous, seen)) if previous else None
        if not identity or any(identity[k] != target[k] for k in ('agent_id','session_id')):
            return None
        return dict(agent_id=target['agent_id'], session_id=target['session_id'], previous_ticket=dispatch['ticket'])
    except (OSError, ValueError, KeyError, TypeError, ec.EngineError, RunStoreError):
        return None


def pause_continuation(index):
    match = runtime_identity.revision_match(index.get('engine_version', ''))
    return bool(match and int(match[1]) >= 133)


def return_query_due(store, index, dispatch):
    """The started same-child resume whose one bounded return query has not been offered yet (request_return would offer
    it now), or None. Review of docs/05SoulRun 87 (C1): until it is offered, no other call may open the liveness stop -
    that stop could then never carry the replacement, whose basis needs the query first (interrupted_basis)."""
    match = runtime_identity.revision_match(index.get('engine_version', ''))
    if not match or int(match[1]) < 135 or not dispatch or returned(dispatch) \
            or index['run_state'] != 'RUNNING' or dispatch.get('state') not in {'ISSUED', 'CLAIMED'}:
        return None
    target = _started_executor(store, index, dispatch)
    if not target or store.exists_path(store.cache_dir/f"_dispatch_query.{dispatch['ticket']}.json"):
        return None
    return target


def request_return(store, index, dispatch):
    """Offer one bounded read on abnormal handoff; never manufacture a return."""
    target = return_query_due(store, index, dispatch)
    if not target:
        return None
    path = store.cache_dir/f"_dispatch_query.{dispatch['ticket']}.json"
    start = store.read_json(store.cache_dir/f"_dispatch_start.{dispatch['ticket']}.json")
    query = dict(tool='TaskOutput', input=dict(task_id=target['agent_id'], block=False),
        parent_session_id=target['session_id'], ticket=dispatch['ticket'],
        trace_id=index['trace_id'], bootstrap_sha256=dispatch['bootstrap_sha256'],
        start_tool_call_id=start['tool_call_id'], status='OFFERED_NOT_EXECUTED',
        note='Use this native tool once in the bound parent. If unavailable or nonterminal, stop and ask the human. '
             'Only a host-bound current-segment terminal result permits reissue; it does not prove external side effects completed.')
    store.write_json_once(path, query)
    return dict(schema_version=1, status='DISPATCH_RETURN_QUERY_REQUIRED',
        run=dict(trace_id=index['trace_id'], state='RUNNING'), node=index['current'], steps=[],
        gate=dict(required=False, state='CLEAR'), public_plan=None, public_plan_ref=None,
        return_query=query, replacement_authorized=False)


def accepted_pause(store, index, dispatch):
    from . import engine_core as ec
    if not dispatch or not dispatch.get('paused_at'):
        return False
    try:
        current = index['current']
        answer = ec._pending_gate_answer(store, index, current['name'], current['visit'])
        if not answer:
            return False
        entry = ec._catalog_entry(index, current['name'])
        path = ec._cache_path_for(store, index, entry, current['visit'])
        node = index['nodes'][ec._node_key(current['name'], current['visit'])]
        if hashlib.sha256(store.read_bytes(path)).hexdigest() != node.get('cache_sha256'):
            return False
        cache = store.read_json(path)
        machine = (cache.get('continuations') or [cache])[-1].get('machine') or {}
        return machine.get('paused_gate') == answer['question_id'] \
            and (machine.get('dispatch') or {}).get('ticket') == dispatch['ticket']
    except (OSError, ValueError, KeyError, TypeError, ec.EngineError, RunStoreError):
        return False


def blocked(index):
    from . import dispatch_scope, engine_core as ec
    if not dispatch_scope.enabled(index) or not index.get('current', {}).get('name'):
        return False
    _, d = dispatch_scope.owner(index, ec._catalog_entry(index, index['current']['name']), index['current']['visit'])
    if d and (d.get('interruption_observation') or {}).get('physical_exit') == 'UNVERIFIED' and not returned(d):
        return True
    if pause_continuation(index) and d and d.get('state') == 'CLAIMED' and d.get('paused_at') \
            and index.get('run_state') == 'RUNNING' and index.get('gate', {}).get('answered_at'):
        return False  # _main_agent_dispatch verifies the accepted pause and bound identity before issuing.
    return bool(d and (d.get('state') == 'ABANDONED' or d.get('paused_at')) and not returned(d))


def _read(path, bootstrap_sha, session_id=None):
    root, path = PROVIDER_ROOT.resolve(), Path(path).absolute()
    try:
        path.relative_to(root)
        if any(p.is_symlink() for p in (path, *path.parents) if p == root or root in p.parents):
            return None
        path = path.resolve(strict=True)
        path.relative_to(root)
        if path.suffix != '.jsonl' or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        calls, results = [], []
        # Ignore an incomplete final line during append; never repair the transcript.
        with path.open('r', encoding='utf-8') as stream:
            for number, line in enumerate(stream, 1):
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(row, dict):
                    continue
                message = row.get('message') or {}
                parts = message.get('content') if isinstance(message, dict) else None
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    meta = dict(line=number, event_id=row.get('uuid'), session_id=row.get('sessionId'),
                                observed_at=row.get('timestamp'), sha256=hashlib.sha256(line.encode()).hexdigest())
                    if row.get('type') == 'assistant' and part.get('type') == 'tool_use' and part.get('name') == 'Agent':
                        args = part.get('input') or {}
                        prompt = args.get('prompt') if isinstance(args, dict) else None
                        if isinstance(prompt, str) and hashlib.sha256(prompt.encode()).hexdigest() == bootstrap_sha:
                            calls.append(dict(meta, tool_use_id=part.get('id'), background=args.get('run_in_background', False)))
                    elif row.get('type') == 'user' and part.get('type') == 'tool_result':
                        results.append((dict(meta, tool_use_id=part.get('tool_use_id')), part))
        if len(calls) != 1:
            return None
        call = calls[0]
        if call['background'] is not False or (session_id and call['session_id'] != session_id) \
                or not all(call[k] for k in ('session_id','event_id','tool_use_id','observed_at')):
            return None
        matches = [(meta, part) for meta, part in results if meta['tool_use_id'] == call['tool_use_id']
                   and meta['session_id'] == call['session_id'] and meta['line'] > call['line']]
        if len(matches) != 1:
            return None
        result, part = matches[0]
        if not result['event_id'] or not result['observed_at']:
            return None
        text = json.dumps(part.get('content'), ensure_ascii=False)
        agent = re.search(r'agentId:\s*([A-Za-z0-9_-]+)', text)
        return dict(source='local_provider_transcript', transcript=str(path), call=call, result=result,
                    bootstrap_sha256=bootstrap_sha, tool_is_error=part.get('is_error') is True,
                    agent_id=agent.group(1) if agent else None,
                    verification_scope='synchronous_tool_return_not_external_side_effect_completion')
    except (OSError, ValueError, UnicodeError):
        return None


def receipt(bootstrap_sha, transcript=None, *, session_id=None, workspace=None):
    if not session_id or not workspace or not re.fullmatch(r'[A-Za-z0-9_-]+', session_id):
        return None
    project = PROVIDER_ROOT/re.sub(r'[^A-Za-z0-9]', '-', str(Path(workspace).absolute()))
    path = Path(transcript).absolute() if transcript else project/f'{session_id}.jsonl'
    if path.parent != project.absolute() or path.stem != session_id:
        return None
    return _read(path, bootstrap_sha, session_id)


def progress_time(at, *previous):
    """Causal watermark uses recorded times, never a synthesized wall clock."""
    from .engine_core import _parse_ts
    return max((v for v in (at, *previous) if v), key=_parse_ts)


def progress(store, dispatch, at, *, preserve_equal=False):
    if not dispatch or not dispatch.get('scope_root'):
        return
    path = store.dispatch_path(dispatch['ticket'])
    rec = store.read_json(path)
    latest = progress_time(at, dispatch.get('last_progress_at'), rec.get('last_progress_at'))
    dispatch['last_progress_at'] = latest
    if rec.get('last_progress_at') == latest and (preserve_equal or latest != at):
        return
    rec['last_progress_at'] = latest
    store.write_json(path, rec)
