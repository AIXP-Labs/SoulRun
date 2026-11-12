"""Declared independence, separate claim pools and a non-bypassable human stop."""
from __future__ import annotations

from . import runtime_identity

import copy
import secrets
import re
import json

from . import render, dispatch_lifecycle
from .run_store import RunStoreError, now_iso


def requirements(program):
    from . import engine_core as ec
    raw = program.entry.system.get('dispatch_requirements') if program else None
    if raw is None:
        return [], 16
    def invalid():
        raise ec.EngineError('DISPATCH_REQUIREMENTS_INVALID',
            'dispatch_requirements: {schema_version:1, post_fix_review:boolean, independent_nodes:[{file,node,isolation}]} '
            'requires unique declared agent nodes; isolation is blind_review or fresh_agent.')
    if (not isinstance(raw, dict) or set(raw) - {'schema_version', 'post_fix_review', 'independent_nodes', 'execution_semantics'}
            or not {'schema_version', 'post_fix_review', 'independent_nodes'} <= set(raw)
            or type(raw['schema_version']) is not int or raw['schema_version'] != 1
            or type(raw['post_fix_review']) is not bool or not isinstance(raw['independent_nodes'], list)):
        invalid()
    seen = set()
    for row in raw['independent_nodes']:
        if not isinstance(row, dict) or set(row) - {'file', 'node', 'isolation', 'blind_inputs', 'input_scope'} \
                or not {'file', 'node', 'isolation'} <= set(row) or not all(isinstance(row[k], str) for k in ('file','node','isolation')):
            invalid()
        doc = program.docs.get(row['file'])
        fn = doc.functions.get(row['node']) if doc else None
        key = row['file'], row['node']
        if (key in seen or not isinstance(fn, dict) or fn.get('execute_mode') != 'agent'
                or row['isolation'] not in {'blind_review', 'fresh_agent'}):
            invalid()
        seen.add(key)
        from . import blind_review
        blind_review.declaration(row)
        from . import independent_inputs
        independent_inputs.declaration(row)
    return raw['independent_nodes'], 20 if raw['post_fix_review'] else 16


def pool(program, entry):
    from . import engine_core as ec
    rows, _ = requirements(program)
    file = entry.get('doc') or (program.entry_file if program else None)
    return 'independent' if any(r['file'] == file and r['node'] == ec._bare(entry) for r in rows) else 'ordinary'


def usage(index, which):
    group = index['dispatch']
    independent = group.get('independent_claimed', 0)
    resumes = group.get('ordinary_resumes_claimed', 0) if resume_accounting(index) else 0
    independent_resumes = group.get('independent_resumes_claimed', 0) if independent_resume_accounting(index) else 0
    from . import dispatch_lifecycle
    replacements = group.get(f'{which}_replacements_claimed', 0) if dispatch_lifecycle.replacement_accounting(index) else 0
    from . import dispatch_identity
    identities = dispatch_identity.claimed_stand_ins(index, which)
    return (independent - independent_resumes if which == 'independent' else group['spawns_claimed'] - independent - resumes) - replacements - identities


def replacement(index, dispatch, *, claim=False):
    from . import dispatch_lifecycle
    # docs/05SoulRun 87: a human-chosen replacement is counted like a handoff one (owner ruling 352 §8 item 2).
    # Review of record 87 (S1, owner decision): at its claim it counts as a replacement - no new task quota - only when the
    # part already holds its task charge; a part that was never charged is charged once, by this claim.
    return bool(dispatch_lifecycle.replacement_accounting(index) and dispatch
                and ((dispatch.get('reason') in {'gate_replacement', 'segment_replacement'} and dispatch.get('handoff'))
                     or (dispatch.get('reason') == 'human_replacement' and dispatch.get('human_replacement')
                         and (not claim or part_charged(dispatch)))))


# Tickets that stand in for a predecessor's charge of the same part, never a new task of their own.
_STAND_INS = frozenset({'human_replacement', 'gate_replacement', 'segment_replacement', 'gate_resume', 'segment_resume', 'identity_handoff'})


def part_charged(dispatch):
    """True when the part this ticket runs already holds its task charge: the retired predecessor (history[-1]) was
    claimed, or it was itself a replacement or resume standing in for a predecessor that holds it. A fresh or reissued
    ticket that was never claimed charged nothing."""
    for row in reversed((dispatch or {}).get('history') or []):
        if row.get('claimed_at'):
            return True
        if row.get('reason') not in _STAND_INS:
            return False
    return False


def resume_accounting(index):
    match = runtime_identity.revision_match(index.get('engine_version', ''))
    return bool(match and int(match[1]) >= 146)


def ordinary_resume(index, dispatch):
    # Classification only; the claimant must pass the native start authority check first.
    return bool(resume_accounting(index) and dispatch and dispatch.get('pool', 'ordinary') == 'ordinary'
                and (dispatch.get('reason') == 'gate_resume' or
                     (dispatch_lifecycle.replacement_accounting(index) and dispatch.get('reason') == 'segment_resume'))
                and dispatch.get('resume_executor'))


def independent_resume_accounting(index):
    match = runtime_identity.revision_match(index.get('engine_version', ''))
    return bool(match and int(match[1]) >= 149)


def independent_resume(index, dispatch):
    return bool(independent_resume_accounting(index) and dispatch and dispatch.get('pool') == 'independent'
                and (dispatch.get('reason') == 'gate_resume' or
                     (dispatch_lifecycle.replacement_accounting(index) and dispatch.get('reason') == 'segment_resume'))
                and dispatch.get('resume_executor'))


def limit(index, which):
    from . import engine_core as ec
    return index['dispatch'].get('independent_hard_limit', 16) if which == 'independent' else ec.SPAWN_HARD_LIMIT


def available(index, which, dispatch=None, *, claim=False):
    if dispatch and dispatch.get('identity_handoff') and (not claim or part_charged(dispatch)):
        return True
    return replacement(index, dispatch, claim=claim) or (which=='ordinary' and ordinary_resume(index, dispatch)) or (which=='independent' and independent_resume(index, dispatch)) or usage(index, which) < limit(index, which)


def summary(index):
    rows = index['dispatch'].get('independent_extensions', [])
    added = sum(r['added'] for r in rows)
    cap = limit(index, 'independent')
    return dict(base_limit=cap-added, added=added, effective_limit=cap,
                used=usage(index, 'independent'), extensions=copy.deepcopy(rows))


def remaining_roots(index, program, rows):
    """Declared roots in any document; not a prediction of branch/loop execution."""
    from . import engine_core as ec
    remaining = []
    for row in rows:
        occurrences=[]
        for key,ne in index['nodes'].items():
            item=ec._catalog_entry(index,key.split('@')[0])
            if item and (item.get('doc') or program.entry_file)==row['file'] and ec._bare(item)==row['node']:
                occurrences.append(ne)
        if not any(ne.get('status') in {'COMMITTED', 'DEGRADED', 'FAILED', 'COMPLETED'}
                   or ((ne.get('dispatch') or {}).get('state') == 'CLAIMED'
                       and not ne['dispatch'].get('paused_at')) for ne in occurrences):
            remaining.append(dict(file=row['file'], node=row['node']))
    return remaining


def _agent_capability_block(index, program, entry, rows):
    from . import engine_core as ec
    if program.execution_loading_mode == 'node':
        tools = (index.get('host') or {}).get('host_tools') or {}
        root = ec.dispatch_scope.root_entry(index, entry) if entry else None
        if tools.get('agent') is not True and (rows or (root and ec._declared_mode(program, root) == 'agent')):
            return 'SUBTREE_AGENT_CAPABILITY_UNAVAILABLE'
    return None


def preflight(index, program, entry=None, *, store=None):
    from . import engine_core as ec
    from . import dispatch_lifecycle
    current = index.get('current') or {}
    if store and current.get('name') and (entry is None or entry.get('name') == current['name']):
        current_entry = entry or ec._catalog_entry(index, current['name'])
        if current_entry:
            from . import dispatch_identity
            dispatch = ec._self_dispatch(index, current_entry, current['visit'])[1]
            try:
                if dispatch_identity.authority(store, index, dispatch):
                    # The bound human grant resolves identity uncertainty, not missing tools.
                    rows, _ = requirements(program)
                    return _agent_capability_block(index, program, current_entry, rows)
            except ec.EngineError as exc:
                return exc.code
    if dispatch_lifecycle.blocked(index):
        # A returned predecessor plus a verified unused continuation permits fencing, not death inference.
        current = ec._self_dispatch(index, ec._catalog_entry(index, index['current']['name']),
                                    index['current']['visit'])[1] if store else None
        # docs/05SoulRun 87: or the human's recorded replacement of exactly this interrupted ticket, rechecked now.
        if not current or not (dispatch_lifecycle.handoff(store, index, current)
                               or dispatch_lifecycle.human_replacement(store, index, current)):
            return 'DISPATCH_LIVENESS_UNKNOWN'
    active = record(store, index) if store else None
    if active and active.get('dispatch_block') == 'DISPATCH_LIVENESS_UNKNOWN':
        _, current = ec._self_dispatch(index, ec._catalog_entry(index, index['current']['name']), index['current']['visit'])
        if current and not dispatch_lifecycle.returned(current) and not dispatch_lifecycle.handoff(store, index, current):
            return 'DISPATCH_LIVENESS_UNKNOWN'
    try:
        rows, cap = requirements(program)
    except ec.EngineError as exc:
        return exc.code
    additions = sum(r['added'] for r in index['dispatch'].get('independent_extensions', []))
    index['dispatch']['independent_hard_limit'] = cap + additions
    capability = _agent_capability_block(index, program, entry, rows)
    if capability:
        return capability
    if not rows:
        return None
    for row in rows:
        if row['isolation'] == 'blind_review':
            if not row.get('blind_inputs'):
                return 'BLIND_REVIEW_INPUT_SCOPE_UNDECLARED'
    if ec._no_agent_normal(index) and program.execution_loading_mode == 'normal':
        return None  # authorized whole-run normal; no independence or fresh-context attestation
    if program.execution_loading_mode != 'node' or not ec._host_has_agent_tool(index):
        return 'INDEPENDENT_EXECUTOR_UNAVAILABLE'
    remaining = len(remaining_roots(index, program, rows))
    if usage(index, 'independent') == 0 and remaining > limit(index, 'independent'):
        return 'INDEPENDENT_PREFLIGHT_BUDGET_INSUFFICIENT'
    if entry and pool(program, entry) == 'independent':
        if not ec.dispatch_scope.is_main(index, entry):
            return 'INDEPENDENT_SCOPE_CONFLICT'
        _, d = ec._self_dispatch(index, entry, index['current']['visit'])
        if d and d.get('scope_root') and d['scope_root'] != dict(node=entry['name'], visit=index['current']['visit']):
            return 'INDEPENDENT_SCOPE_CONFLICT'
        if d and d.get('state') == 'CLAIMED' and not d.get('paused_at'):
            return None  # an already claimed executor may finish without buying another claim
        # docs/05SoulRun 87: a child that came back with an error (paused or not) is the human's choice to replace;
        # attempts and quota never decide it (owner ruling 352 §8 item 2).
        if store and dispatch_lifecycle.human_replacement(store, index, d):
            return None
        if store and dispatch_lifecycle.replacement_basis(store, index, d):
            return 'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE'
        if d and d.get('paused_at') and independent_resume_accounting(index) and index.get('gate',{}).get('answered_at'):
            target=dispatch_lifecycle.resume_executor(store,d) if store else None
            if target:return None
        if dispatch_lifecycle.unfinished_return(index, d):
            if d.get('attempt', 0) >= ec.DISPATCH_ATTEMPTS_MAX:
                return 'INDEPENDENT_ATTEMPTS_EXHAUSTED'
            return None if store and dispatch_lifecycle.resume_executor(store,d) else 'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE'
        if not available(index, 'independent', d):
            return 'INDEPENDENT_BUDGET_EXHAUSTED'
        if d and d.get('state') in {'ABANDONED', 'EXHAUSTED'} and d.get('attempt', 0) >= ec.DISPATCH_ATTEMPTS_MAX:
            return 'INDEPENDENT_ATTEMPTS_EXHAUSTED'
    return None


def record(store, index):
    if index['run_state'] == 'WAITING_USER' and index['gate'].get('question_id'):
        row = store.read_json(store.gate_path(index['gate']['question_id']))
        if row.get('dispatch_block'):
            return row
    return None


_ENGINE_STOP_CODES = ('INDEPENDENT_', 'BLIND_REVIEW_', 'ORIGINAL_EXECUTOR_', 'DISPATCH_LIVENESS_UNKNOWN', 'DISPATCH_REPLACEMENT_LAPSED')


def _install(index, rec, now):
    """The run with `rec` as its active engine stop - what pause() writes (round 4: also the projection recheck_outcome
    reads before the stop is written)."""
    qid, node = rec['question_id'], rec['node']
    index['gate'].update(state='WAITING_USER', question_id=qid, node=node, source='hsaw_doubt', kind='choice',
                         presented_at=now, delivered_at=None, answered_at=None)
    index['gate']['history'].append(dict(question_id=qid, node=node, source='hsaw_doubt', prompt_text=None,
        presented_at=now, answered_at=None, resolution_kind=None, answer_ref=f'_gate.{qid}.json'))
    index['tickets'].append(dict(question_id=qid, state='READY', minted_at=now))
    index['run_state'] = 'WAITING_USER'
    from . import engine_core as ec
    index['nodes'][ec._node_key(node, rec['visit'])]['status'] = 'WAITING_USER'
    return index


class _StopView:
    """Round 4: the run cache as the engine reads it at one moment of a recheck on the stop `rec` - `index` for read_index()
    and `rec` at its own gate path (it may not be written yet) - with every write refused, so recheck_outcome stays
    read-only whatever it calls."""

    def __init__(self, store, index, rec):
        self._store, self._index, self._rec = store, index, rec
        self._gate = store.gate_path(rec['question_id'])

    def __getattr__(self, name):
        if name.startswith(('write', 'append', 'ensure')) or name == 'lock':
            raise RunStoreError('DISPATCH_RECHECK_READ_ONLY', name)
        return getattr(self._store, name)

    def read_index(self):
        return copy.deepcopy(self._index)

    def read_json(self, path):
        return copy.deepcopy(self._rec) if path == self._gate else self._store.read_json(path)

    def exists_path(self, path):
        return path == self._gate or self._store.exists_path(path)


def _as_answered(index, rec, intent, now, **fields):
    """Round 5: copies of the run and of the engine stop `rec` as answer() leaves them once `intent` answered it and the
    run goes on: the stop answered with it (plus `fields`), its gate row answered, the gate it paused restored, the
    node's status back, the run going on. Read by recheck_outcome and replace_outcome."""
    from . import engine_core as ec
    label = next((o.get('label') for o in rec.get('options') or [] if o.get('intent') == intent), None)
    answered = dict(copy.deepcopy(rec), answered_at=now, resolution_kind='chosen', chosen_intent=intent, chosen_label=label,
                    **fields)
    running = copy.deepcopy(index)
    for row in running['gate']['history']:
        if row.get('question_id') == rec['question_id']:
            row.update(answered_at=now, resolution_kind='chosen')
    running['gate'] = dict(copy.deepcopy(rec['previous_gate']), history=running['gate']['history'])
    running['run_state'] = 'RUNNING'
    running['nodes'][ec._node_key(rec['node'], rec['visit'])]['status'] = rec['previous_status']
    return running, answered


def recheck_outcome(store, index, rec, *, program=None):
    """Round 4 of the review of docs/05SoulRun 87 (E1, E2, E4, E6): what choosing Recheck conditions on the open engine
    stop `rec` leads to, decided as the engine decides it - answer()'s recheck (preflight on the stop's node), then, with
    the stop answered as answer() leaves it, the main agent's next next-node: its preflight and the step
    engine_core._dispatch_step decides and _main_agent_dispatch carries out. The one source for every text that says what
    a recheck does next (round 5: replace_outcome for the replacement). Read-only: it reads through _StopView (copies of the index, every write refused), and the stop's
    own record is the one passed, so it may be asked before that record is written. `index` is the run with `rec` as its
    active stop. Returns, or None on any doubt:
      dict(next='held', code)                 the recheck does not pass; this stop stays (code: what blocks it)
      dict(next='continues', step)            the old agent is resumed with the recorded return (segment_resume or
                                              gate_resume)
      dict(next='stop', code, replacement)    another engine stop opens on `code`; replacement: it offers record 84's one
                                              new agent
      dict(next='other', step)                the engine takes another step: the human's chosen replacement, a return
                                              query, a wait, a reissue or inline work
    docs/05SoulRun 88 (K1): on a liveness stop that a different condition now blocks, the recheck retires the stop and the
    human is asked at that condition's stop (_recheck_moves_on): 'stop' with that code, or 'other' (return_query)."""
    from . import engine_core as ec
    try:
        program = program or ec._load_routed_program(ec._read_run_input(store))
        entry = ec._catalog_entry(index, rec['node'])
        held = preflight(copy.deepcopy(index), program, entry, store=_StopView(store, index, rec))
        if held:
            moved = _recheck_moves_on(store, index, rec, program, held)
            if not moved:
                return dict(next='held', code=held)
            if moved['step'] == 'query':
                return dict(next='other', step='return_query')
            return dict(next='stop', code=moved['code'], replacement=moved['replacement'])
        # As answer() leaves the run after a passed recheck: this stop answered with it, its gate row answered, the gate
        # it paused restored, the node's status back, the run going on.
        running, answered = _as_answered(index, rec, 'recheck_dispatch', now_iso())
        view = _StopView(store, running, answered)
        root = ec._self_dispatch(running, entry, rec['visit'])[1]
        reason = preflight(copy.deepcopy(running), program, store=view)
        if reason == 'DISPATCH_LIVENESS_UNKNOWN' and dispatch_lifecycle.return_query_due(view, running, root):
            return dict(next='other', step='return_query')
        if reason:
            return dict(next='stop', code=reason, replacement=bool(dispatch_lifecycle.offered_basis(view, running, root, reason)))
        if not (ec.dispatch_scope.enabled(running) and root and root.get('scope_root')):
            return None
        pool = root.get('pool', 'ordinary')
        gate_answer = ec._pending_gate_answer(view, running, rec['node'], rec['visit'])
        try:
            step, _ = ec._dispatch_step(view, running, root, gate_answer, None, pool=pool)
        except ec.EngineError as exc:
            if not exc.code.startswith(_ENGINE_STOP_CODES):
                return None
            return dict(next='stop', code=exc.code, replacement=bool(dispatch_lifecycle.offered_basis(view, running, root, exc.code)))
        code = ec._exhaust_code(running, root, pool) if step == 'exhaust' else None
        if code:
            return dict(next='stop', code=code, replacement=False) if code.startswith(_ENGINE_STOP_CODES) else None
        if step in ('segment_resume', 'gate_resume', 'restored'):
            return dict(next='continues', step='gate_resume' if step == 'restored' else step)
        return dict(next='other', step=step)
    except (ec.EngineError, RunStoreError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


RECHECK_MOVED_ON = 'DISPATCH_RECHECK_MOVED_ON'   # docs/05SoulRun 88 (K1): the supersedes reason of the stop a recheck moved on to
LIVE = 'DISPATCH_LIVENESS_UNKNOWN'
SUBTREE_CAP = 'SUBTREE_AGENT_CAPABILITY_UNAVAILABLE'
# The stops whose recheck may move on to another condition's stop: K1's liveness stop, and (review round 3, O2) the
# missing Agent capability once the host declares it again.
_MOVABLE = (LIVE, SUBTREE_CAP)


def _capability_declared(index):
    """Review round 3 of docs/05SoulRun 88 (O2): the host declares the sub-agent (Agent) capability now - host_tools as the
    host recorded them at its latest (re-)entry (prepare_cache), exactly the test preflight's SUBTREE condition makes."""
    return ((index.get('host') or {}).get('host_tools') or {}).get('agent') is True


def _recheck_moves_on(store, index, rec, program, blocking):
    """docs/05SoulRun 88 (K1, owner ruling: record 87 §10.6 option B): a Recheck conditions answer on the liveness stop `rec`
    whose preflight (`blocking`) now gives another condition - the part is held by something else, e.g. record 84's
    resume-unavailable condition after an error return, or the attempt bound - moves on by the current records: the stop
    is retired with that answer and the human is asked again at that condition's stop, as a stale replacement choice
    retires it (_ask_again_step on the run as answer() leaves it, read-only here). Returns dict(step, code, replacement) -
    step 'query' (the bounded return query comes first) or 'stop' (pause opens `code`; replacement: it offers record 84's
    one new agent) - or None when the stop stays: not a liveness stop, nothing blocks, the liveness condition itself still
    blocks, or the records asked anew would show this stop's own condition again (never a loop of liveness stops).
    Review round 3 (O2, owner decision: the narrow fix): likewise the SUBTREE_AGENT_CAPABILITY_UNAVAILABLE stop once the
    host declares the Agent tool again and another condition now holds the part; while the tool is still lost it stays.
    Review round 3 (R1): never for an answered stop - recovery completes a recorded move itself (_complete_recorded,
    _recorded_move) and never decides it again."""
    from . import engine_core as ec
    block = rec.get('dispatch_block')
    if rec.get('answered_at') or not blocking or blocking == block \
            or not (block == LIVE or (block == SUBTREE_CAP and _capability_declared(index))):
        return None
    running, answered = _as_answered(index, rec, 'recheck_dispatch', now_iso())
    view = _StopView(store, running, answered)
    step, code = _ask_again_step(view, running, answered, None, program)
    if step == 'query':
        return dict(step='query', code=None, replacement=False)
    if code == rec['dispatch_block']:
        return None
    current = ec._self_dispatch(running, ec._catalog_entry(running, running['current']['name']), running['current']['visit'])[1]
    return dict(step='stop', code=code, replacement=bool(dispatch_lifecycle.offered_basis(view, running, current, code)))


def _recorded_move(rec):
    """Review round 2 of docs/05SoulRun 88 (M1): True when the answered liveness stop `rec` records a Recheck conditions
    that moved on (K1) - answer() stamps that recheck's attempt and the answer with one instant, so its last recheck
    attempt carries the answer's own time and names the other condition. A recheck that passed adds no attempt, so its
    last attempt (if any) is older than its answer. Review round 3: likewise a SUBTREE stop's move (O2)."""
    attempts = rec.get('recheck_attempts') or []
    last = attempts[-1] if attempts else {}
    return bool(rec.get('resolution_kind') == 'chosen' and rec.get('chosen_intent') == 'recheck_dispatch'
                and rec.get('last_reply_valid') is True and last.get('at') == rec.get('answered_at')
                and last.get('reason') not in (None, rec.get('dispatch_block')))


def recheck_moved_on(store, index, rec):
    """docs/05SoulRun 88 (K1): for an answered liveness stop that a Recheck conditions answer retired because another
    condition held the part, the stop the human was asked at next - {question_id, code} - from that stop's supersedes link;
    else None. Derived from the records for the reports, never written back. Review round 3: also a SUBTREE stop's move
    (O2); and (R4) a recorded move whose stop that follows was never written (the run stopped after answer()'s index
    write, window 3): the next engine stop of the same node and visit - the one the main agent's next-node opened itself,
    without the link - or, before one opens, no question and the condition the recorded attempt names. Review round 4
    (W2): that later stop only where it is the one next-node opened for the recorded move - no ticket was issued for the
    part between the answer and that stop's presentation (_issued_between); after the run went on (a ticket was issued)
    a later stop is unrelated and the recorded condition is given with no question."""
    if rec.get('source') != 'hsaw_doubt' or rec.get('dispatch_block') not in _MOVABLE \
            or rec.get('chosen_intent') != 'recheck_dispatch' or not rec.get('answered_at'):
        return None
    after, first = False, None
    for row in index['gate']['history']:
        if row.get('question_id') == rec.get('question_id'):
            after = True
            continue
        if not after or row.get('source') != 'hsaw_doubt':
            continue
        try:
            later = store.read_json(store.gate_path(row['question_id']))
        except (OSError, ValueError, KeyError, TypeError, RunStoreError):
            continue
        if later.get('supersedes') == dict(question_id=rec['question_id'], reason=RECHECK_MOVED_ON):
            return dict(question_id=later['question_id'], code=later.get('dispatch_block'))
        if first is None and later.get('dispatch_block') and (later.get('node'), later.get('visit')) == (rec.get('node'), rec.get('visit')):
            first = later
    if not _recorded_move(rec):
        return None
    if first and _issued_between(index, rec, rec.get('answered_at'), first.get('presented_at')):
        first = None          # review round 4 (W2): the run went on before that stop opened; it is not where the move asked
    return dict(question_id=(first or {}).get('question_id'),
                code=(first or {}).get('dispatch_block') or rec['recheck_attempts'][-1].get('reason'))


def _issued_between(index, rec, start, end):
    """Review round 4 of docs/05SoulRun 88 (W2): True when a ticket was issued for the part of the stop `rec` (its dispatch
    or any ticket in that dispatch's history) at or after `start` and at or before `end`, or when that cannot be read -
    a later stop is then never taken for the one next-node opened for the recorded move."""
    from . import engine_core as ec
    try:
        entry = ec._catalog_entry(index, rec['node'])
        dispatch = ec._self_dispatch(index, entry, rec['visit'])[1] if entry else None
        low, high = ec._parse_ts(start), ec._parse_ts(end)
        if low is None or high is None:
            return True
        for row in [dispatch or {}, *((dispatch or {}).get('history') or [])]:
            at = ec._parse_ts(row.get('issued_at'))
            if at is not None and low <= at <= high:
                return True
        return False
    except (ec.EngineError, KeyError, TypeError, ValueError, AttributeError):
        return True


def _replace_choice(store, index, rec, program, blocking):
    """Round 5 of the review of docs/05SoulRun 87 (F1, F2): answer()'s own decision on a replace_executor choice at the
    engine stop `rec` - `blocking` is answer()'s preflight on the stop's node - made without writing anything. answer()
    carries it out; replace_outcome reads it to say what the choice leads to. Returns dict(reason, basis, current,
    outcome, refused):
      reason None                 the choice answers exactly this stop's condition: the one replacement is authorized
                                  on `basis` (record 84's return, or #5's interruption) for the dispatch `current`
      reason set, refused False   this stop stays and nothing is replaced: the records the replacement was offered on
                                  changed (DISPATCH_REPLACEMENT_STALE) or another condition still blocks (that code)
      refused True                a stale choice on a liveness stop retires it, authorizing nothing, and _ask_again asks
                                  anew (review C3, round 2 N1, round 3 D1, round 4 E6); `outcome` is what its recheck led
                                  to (recheck_outcome), read only while preflight did not block"""
    from . import engine_core as ec
    _, current = ec._self_dispatch(index, ec._catalog_entry(index, rec['node']), rec['visit'])
    # docs/05SoulRun 84: the choice holds only for the return it was offered for, unchanged.
    # docs/05SoulRun 87: or for the interrupted ticket it was offered for, recomputed now; stale -> still paused.
    basis = dispatch_lifecycle.offered_basis(store, index, current, rec['dispatch_block'])
    reason = blocking
    if not basis or basis != rec.get('replacement_basis'):
        reason = 'DISPATCH_REPLACEMENT_STALE'
    elif reason == rec['dispatch_block']:
        reason = None                      # the human's choice answers exactly this condition
    stale_liveness = reason == 'DISPATCH_REPLACEMENT_STALE' and rec['dispatch_block'] == 'DISPATCH_LIVENESS_UNKNOWN'
    outcome = recheck_outcome(store, index, rec, program=program) if stale_liveness and blocking is None else None
    refused = stale_liveness and (blocking is not None or bool(outcome and outcome['next'] == 'stop' and outcome.get('replacement')))
    return dict(reason=reason, basis=basis, current=current, outcome=outcome, refused=refused)


def replace_outcome(store, index, rec, *, program=None):
    """Round 5 of the review of docs/05SoulRun 87 (F1, F2): what choosing to retire the old ticket and continue with a new
    agent (replace_executor) on the open engine stop `rec` leads to, decided as the engine decides it - answer()'s
    preflight and _replace_choice, then, where the choice retires the stop, _ask_again_step on the run as answer() leaves
    it and whether the stop it opens offers record 84's one new agent (pause: offered_basis). The one source, with
    recheck_outcome, for every text that says what an option does next. Read-only like recheck_outcome (_StopView, copies
    of the index). None when the stop does not offer the option, or on any doubt; else:
      dict(next='same', code)                 this stop stays and nothing is replaced (code: why the choice is not taken)
      dict(next='carried')                    the one replacement is authorized; the main agent's next-node issues it
      dict(next='stop', code, replacement)    this stop is retired and nothing is replaced; the human is asked again at
                                              the stop `code`; replacement: that stop offers one new agent
      dict(next='query')                      this stop is retired and nothing is replaced; the main agent's next-node
                                              offers the bounded return query first, and the human is asked after it"""
    from . import engine_core as ec
    if rec.get('answered_at') or not any(o.get('intent') == 'replace_executor' for o in rec.get('options') or []):
        return None
    try:
        program = program or ec._load_routed_program(ec._read_run_input(store))
        view, work = _StopView(store, index, rec), copy.deepcopy(index)
        blocking = preflight(work, program, ec._catalog_entry(work, rec['node']), store=view)
        choice = _replace_choice(view, work, rec, program, blocking)
        if not choice['reason']:
            return dict(next='carried')
        if not choice['refused']:
            return dict(next='same', code=choice['reason'])
        # As answer() leaves the run after it retired this stop: answered with the choice refused, the run going on.
        now = now_iso()
        running, answered = _as_answered(work, rec, 'replace_executor', now,
                                         replacement_refused=dict(reason='DISPATCH_REPLACEMENT_STALE', at=now))
        after = _StopView(store, running, answered)
        step, code = _ask_again_step(after, running, answered, choice['outcome'], program)
        if step == 'query':
            return dict(next='query')
        node, visit = running['current']['name'], running['current']['visit']
        current = ec._self_dispatch(running, ec._catalog_entry(running, node), visit)[1]
        return dict(next='stop', code=code, replacement=bool(dispatch_lifecycle.offered_basis(after, running, current, code)))
    except (ec.EngineError, RunStoreError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _since_returned(store, index, rec):
    """The open liveness stop's dispatch once the host has recorded its child's return, or None."""
    from . import engine_core as ec
    if rec.get('dispatch_block') != 'DISPATCH_LIVENESS_UNKNOWN' or rec.get('answered_at'):
        return None
    try:
        entry = ec._catalog_entry(index, rec['node'])
        current = ec._self_dispatch(index, entry, rec['visit'])[1] if entry else None
    except (ec.EngineError, KeyError, TypeError):
        return None
    return current if dispatch_lifecycle.returned(current) else None


# Review round 2 of docs/05SoulRun 88 (L1): the stops a liveness stop's recheck leads to once the part's second attempt
# returned unfinished - next-node's ORIGINAL_EXECUTOR_CONTINUATION_EXHAUSTED and, for the same records at an independent
# root, preflight's INDEPENDENT_ATTEMPTS_EXHAUSTED (the attempt bound). At either only cancel remains (a recheck there
# stays). Review round 3 (R5): that second attempt is the part's one same-agent continuation, or - when that continuation
# never reached the original agent - the one new agent the engine's handoff rule gave the part (_handed_off); the menu
# says which. (O3: INDEPENDENT_ATTEMPTS_EXHAUSTED states the same cause at that bound, _stop_terms.)
_BOUND_STOPS = ('ORIGINAL_EXECUTOR_CONTINUATION_EXHAUSTED', 'INDEPENDENT_ATTEMPTS_EXHAUSTED')


def _handed_off(dispatch):
    """Review round 3 of docs/05SoulRun 88 (R5): True when the part's second attempt went to a new agent because its
    same-agent continuation never reached the original agent - the engine's handoff rule replaced an unclaimed
    segment_resume by a segment_replacement (dispatch_lifecycle.handoff) - and no segment_resume of the part was claimed.
    False where the continuation really reached it (a claimed segment_resume) or no handoff happened."""
    rows = [dispatch or {}, *((dispatch or {}).get('history') or [])]
    return any(r.get('reason') == 'segment_replacement' for r in rows) \
        and not any(r.get('reason') == 'segment_resume' and r.get('claimed_at') for r in rows)


def _bound_story(dispatch):
    """Review round 4 of docs/05SoulRun 88 (W6, W7): how the part's second attempt was used, worded from the dispatch that
    now holds the part - 'used': its one same-agent continuation; 'handed': that continuation never reached the original
    agent and the engine's continuation rule gave the part to one new agent, which holds it now; 'human': after that
    handoff the human chose a new agent in its place (human_replacement), which holds it now; 'other': after the handoff
    another dispatch holds it (said without naming who chose it).
    Review round 5 (problem 86, P1): without a handoff, 'used' only where the agent the continuation reached still holds
    the part - after the last segment_resume that reached it (claimed, or the current one with a recorded return) only
    gate resumes of that same agent follow; 'used_human': after it the human chose exactly one new agent in its place
    (human_replacement), which holds the part now (gate resumes of either agent aside); 'used_other': after it the part
    went to a new agent otherwise (the human replaced agents twice, a gate continuation handed off, ...), said without
    naming who chose the agent holding the part; 'neutral': no continuation is known to have reached the agent (it was
    never claimed and the human replaced it) - said without counting the part's returns."""
    if _handed_off(dispatch):
        reason = (dispatch or {}).get('reason')
        return 'handed' if reason == 'segment_replacement' else 'human' if reason == 'human_replacement' else 'other'
    current = dispatch or {}
    rows = [*(current.get('history') or []), current]          # oldest first; the dispatch that holds the part last
    reached = [i for i, r in enumerate(rows) if r.get('reason') == 'segment_resume'
               and (r.get('claimed_at') or (r is current and dispatch_lifecycle.returned(current)))]
    if not reached:
        return 'neutral'
    since = [r.get('reason') for r in rows[reached[-1] + 1:]]
    if set(since) <= {'gate_resume'}:
        return 'used'
    if since.count('human_replacement') == 1 and set(since) <= {'human_replacement', 'gate_resume'}:
        return 'used_human'
    return 'used_other'


def _bound_words(story, zh):
    """Review round 4 (W6, W7): the history clause of the attempt-bound sentences after a handoff (`story` from
    _bound_story, not 'used'), up to the agent that holds the part now - the caller says that agent returned. Review round
    5 (P1): also 'used_human', 'used_other' and 'neutral' (no 'too'/'also' after it: _bound_also)."""
    if story == 'used_human':
        return ('接回原子代理的那一次已经用过，之后你又选择换了一个新代理，它也' if zh else
                'its one same-agent continuation was used, and you then chose a new agent in its place; that agent')
    if story == 'used_other':
        return ('接回原子代理的那一次已经用过，之后这一段改由新代理去做；现在拿着这一段的代理也' if zh else
                'its one same-agent continuation was used, and the part then went to a new agent; the agent now holding the part')
    if story == 'neutral':
        return '现在拿着这一段的代理' if zh else 'the agent now holding the part'
    if zh:
        return ('接着做的那条消息没送到原来的子代理，' + (
            '引擎按续接规则改派了一个新代理，它也' if story == 'handed' else
            '引擎按续接规则改派了一个新代理；之后你又选择换了一个新代理，它也' if story == 'human' else
            '这一段改由新代理去做；现在拿着这一段的代理也'))
    return ('the continuation message never reached the original sub-agent, ' + (
        "the engine's continuation rule gave the part to one new agent, and it" if story == 'handed' else
        "the engine's continuation rule gave the part to one new agent, and you then chose another new agent in its place; "
        'that agent' if story == 'human' else
        'and the part went to a new agent; the agent now holding the part'))


def _bound_also(story):
    """Review round 5 (P1): whether the English attempt-bound sentence says the agent holding the part returned 'too' /
    'also' - an earlier agent of the part returned unfinished on every history but 'neutral', which counts nothing."""
    return story != 'neutral'


def _at_bound(index, dispatch):
    """Review round 3 of docs/05SoulRun 88 (O3): the part's dispatch returned unfinished at the attempt bound - where
    preflight opens INDEPENDENT_ATTEMPTS_EXHAUSTED for an independent root (and next-node CONTINUATION_EXHAUSTED)."""
    from . import engine_core as ec
    return bool(dispatch_lifecycle.unfinished_return(index, dispatch)
                and int((dispatch or {}).get('attempt') or 0) >= ec.DISPATCH_ATTEMPTS_MAX)


def _returned_hint(rec, outcome, rep, failed, zh, story='used'):
    """Rounds 2-5 of the review of docs/05SoulRun 87 (N1, D3, E2, E6, F1, F2): what a liveness stop says once the host has
    recorded its child's return - that return (an error return said as such) and that nothing was replaced; what Recheck
    conditions leads to, from recheck_outcome - round 5: also where it cannot pass (K1: it does not pass here and the run
    stays on this stop); what choosing the replacement leads to, from replace_outcome, only where the stop offers it
    (round 5), with the earlier recommendation said to no longer apply where it can lead to no new agent; and cancel.
    After a stale replacement choice it opens with the N1 sentence, after a held recheck with that reply's
    acknowledgement - never as a reply that was not given. Review round 3 (R5): at the attempt bound, after the part's
    second attempt went to a new agent (_handed_off), the bound sentence says so; review round 4 (W6): `story`
    (_bound_story) - worded from the dispatch that now holds the part; review round 5 (P1): the round-3 'used' sentence
    only where the agent the continuation reached holds the part."""
    handed = story != 'used'
    nxt, code = outcome.get('next'), outcome.get('code')
    record_84 = nxt == 'stop' and bool(outcome.get('replacement'))
    bound = nxt == 'stop' and code in _BOUND_STOPS               # review round 2 of docs/05SoulRun 88 (L1)
    rnext, rcode = (rep or {}).get('next'), (rep or {}).get('code')
    new_agent = rnext == 'stop' and bool(rep.get('replacement'))
    there = new_agent and record_84 and rcode == code          # Recheck and the replacement lead to that same stop
    moot = rnext in ('same', 'query') or (rnext == 'stop' and not new_agent)
    if zh:
        fact = ('宿主现在记下了旧代理的返回：它带着错误回来了，接不回。' if failed else '宿主现在记下了旧代理的返回。') + '没有换人，继续等待；'
        recheck = ('要按这条返回记录照常接着做，请选「复核条件」' if nxt == 'continues' else
                   '选「复核条件」会转到可以换一个新代理的那道题' if record_84 else
                   (f'这一段的尝试次数已经用完：{_bound_words(story, True)}已经返回，'
                    f'所以选「复核条件」会转到只剩取消的停顿（{code}）' if handed else      # review round 3 (R5), round 4 (W6)
                    f'同一段只能接回原来的子代理一次，这一次已经用过了，所以选「复核条件」会转到只剩取消的停顿（{code}）')
                   if bound else
                   f'选「复核条件」会转到另一道停顿（{code}），那里会写明原因' if nxt == 'stop' else
                   f'选「复核条件」过不去：条件仍未满足（{code}），运行会继续停在这道题上' if nxt == 'held' else
                   '选「复核条件」后，引擎按现在的记录给出下一步')
        replace = ('，选「作废旧票，换一个新代理接着做」会直接在那道题上重新问你' if there else
                   f'。选「作废旧票，换一个新代理接着做」不会在这里换人：这道题会关闭，改在可以换一个新代理的那道题（{rcode}）上重新问你'
                   if new_agent else '')
        cancel = '，也可以取消。' if nxt == 'continues' else '；也可以现在就取消。' if bound else '；也可以取消。'
        # docs/05SoulRun 88 (T4): the write-once advice says choosing the replacement authorizes it; here it leads to the
        # stop with the one new agent, where the human chooses again - the only path to a new agent, so never called moot.
        cancel += '建议里说的授权，要在那道题上再选一次换人才算。' if new_agent else ''
        moot = ('先前推荐的「作废旧票，换一个新代理接着做」已不适用：现在选它不会换人' + (
                    f'，只会关闭这道题，改在另一道停顿（{rcode}）上重新问你，那里不能换新代理。' if rnext == 'stop' else
                    '，只会关闭这道题；主代理下一次取节点时先做一次有界的返回查询，之后再按新的记录问你。' if rnext == 'query' else '。')
                if moot else '')
        stale, held = '这个换人选项依据的记录已经变了：', '复核已执行。'      # record 90 (ledger decision 190): facts only
    else:
        fact = ("the host has now recorded the old agent's return: it came back with an error and cannot be resumed. " if failed else
                "the host has now recorded the old agent's return. ") + 'Nothing was replaced; still paused. '
        recheck = ('To continue normally with that return, choose Recheck conditions' if nxt == 'continues' else
                   'Recheck conditions leads to the stop where one new agent can be chosen' if record_84 else
                   (f"This part's attempts are used up: {_bound_words(story, False)} has returned"
                    f"{' too' if _bound_also(story) else ''}, so Recheck conditions "   # review round 5 (P1)
                    f'leads to a stop where only cancel remains ({code})' if handed else      # review round 3 (R5), round 4 (W6)
                    'One same-agent continuation per part is already used, so Recheck conditions leads to a stop where only '
                    f'cancel remains ({code})') if bound else
                   f'Recheck conditions leads to another stop ({code}), which states its cause' if nxt == 'stop' else
                   f'Recheck conditions does not pass here: a condition is still unmet ({code}), and the run stays paused on '
                   'this stop' if nxt == 'held' else
                   'After Recheck conditions the engine shows the next step on the current records')
        replace = (', and choosing to retire the old ticket asks you there directly' if there else
                   '. Choosing to retire the old ticket replaces nothing here; instead this stop closes and you are asked again '
                   f'at the stop where one new agent can be chosen ({rcode})' if new_agent else '')
        cancel = '; you may also cancel now.' if bound else '; you may also cancel.'
        cancel += (' The authorization in the advice takes effect only when you choose the new agent again at that stop.'
                   if new_agent else '')   # docs/05SoulRun 88 (T4)
        moot = (' The earlier recommendation to retire the old ticket no longer applies: choosing it now replaces nothing' + (
                    f'; it only closes this stop and asks you again at another stop ({rcode}), where no new agent can be chosen.'
                    if rnext == 'stop' else
                    "; it only closes this stop: the main agent's next-node first offers the one bounded return query, and "
                    'then you are asked again on the new records.' if rnext == 'query' else '.')
                if moot else '')
        stale, held = 'The records this replacement was offered on have changed: ', 'Recheck executed. '
    body = fact + recheck + replace + cancel + moot
    attempts = rec.get('recheck_attempts') or []
    last = attempts[-1].get('reason') if rec.get('last_reply_valid') is True and attempts else None
    if last == 'DISPATCH_REPLACEMENT_STALE':
        return stale + body
    body = body if zh else body[0].upper() + body[1:]
    return held + body if nxt == 'held' and last == code else body


def _returned_host_texts(outcome, rep, failed, story='used', ack=''):
    """Rounds 4-5 (E2, E4, F2, F4): answer_hint and errors[0].message for that stop - the same facts as its menu, for the
    host: the recorded return, what Recheck conditions leads to (held included), and what choosing the replacement leads
    to where the stop offers it. Review round 3 (R5), round 4 (W6): `story` as for _returned_hint. Review round 4 (W3):
    `ack` '' - the answer_hint acknowledges no reply (no reply was given at this stop: it was just opened by the answer
    that retired the stop before it). Record 90 (ledger decision 190): otherwise `ack` is the fact sentence on the reply
    given at this stop (_asked_ack) - never 'Valid reply'."""
    handed = story != 'used'
    valid = ack or ''
    nxt, code = outcome.get('next'), outcome.get('code')
    rnext, rcode = (rep or {}).get('next'), (rep or {}).get('code')
    replace = ('; choosing to retire the old ticket now replaces nothing' if rnext == 'same' else
               '; choosing to retire the old ticket replaces nothing here: this stop closes and the human is asked again at '
               f'{rcode}, where one new agent can be chosen' if rnext == 'stop' and rep.get('replacement') else
               '; choosing to retire the old ticket replaces nothing: this stop closes and the human is asked again at '
               f'{rcode}, where no new agent can be chosen' if rnext == 'stop' else
               "; choosing to retire the old ticket replaces nothing: this stop closes, and the main agent's next-node first "
               'offers the one bounded return query' if rnext == 'query' else '')
    wait = 'Present the menu and wait for the human; do not continue, replay work or retry on your own.'
    if nxt == 'continues':   # round 3 wording, with what the replacement leads to (round 5)
        # Review round 4 (W3): no recheck answered at this stop; review round 5 of docs/05SoulRun 88 (problem 86, P2): nor
        # after a held recheck or a stale replacement choice - the reply given then did not continue the run, and nothing
        # goes on until the human answers again; choosing Recheck conditions then continues with that return.
        return (f"{valid}The host has since recorded the old executor's return; the run stays paused until the human answers, "
                f'and Recheck conditions continues with that return{replace}. {wait}',
                "The old executor's return is now recorded; the run stays paused until the human answers, and Recheck "
                f'conditions continues with that return{replace}. No competing executor is allowed.')
    what = ('The host has since recorded that the old executor came back with an error, so it cannot be resumed' if failed else
            "The host has since recorded the old executor's return")
    if nxt == 'held':
        then = f'Recheck conditions does not pass here ({code}), so the run stays paused on this stop'
        return (f'{valid}{what}; {then}{replace}. {wait}',
                f'{what}; {then} until the human answers{replace}. No competing executor is allowed.')
    then = ('Recheck conditions leads to the stop where one new agent can be chosen' if nxt == 'stop' and outcome.get('replacement') else
            (f"this part's attempts are used up ({_BOUND_HOST[story]}), so Recheck conditions leads to a stop where only "
             f'cancel remains ({code})' if handed else      # review round 3 of docs/05SoulRun 88 (R5), round 4 (W6)
             'one same-agent continuation per part is used up, so Recheck conditions leads to a stop where only cancel remains '
             f'({code})') if nxt == 'stop' and code in _BOUND_STOPS else   # review round 2 of docs/05SoulRun 88 (L1)
            f'Recheck conditions leads to another stop ({code})' if nxt == 'stop' else
            'after Recheck conditions the engine takes its next step on the current records')
    return (f'{valid}{what}; {then}{replace}. {wait}',
            f'{what}; the run stays paused until the human answers, and {then}{replace}. No competing executor is allowed.')


# Review round 4 of docs/05SoulRun 88 (W6): the host's history clause at the attempt bound after a handoff, by _bound_story
# (round 5, P1: also 'used_human' and 'neutral').
_BOUND_HOST = {
    'handed': "the continuation never reached the original sub-agent; the one new agent the engine's continuation rule gave "
              'the part has returned too',
    'human': "the continuation never reached the original sub-agent; the engine's continuation rule gave the part to one new "
             'agent, the human then chose another new agent in its place, and that agent has returned too',
    'other': 'the continuation never reached the original sub-agent and the part went to a new agent; the agent now holding '
             'the part has returned too',
    # review round 5 (problem 86, P1): the continuation reached the original agent, then the human replaced it (or the part
    # went to a new agent otherwise); without a continuation known to have reached it ('neutral') nothing is counted
    'used_human': 'its one same-agent continuation was used; the human then chose a new agent in its place, and that agent '
                  'has returned too',
    'used_other': 'its one same-agent continuation was used and the part then went to a new agent; the agent now holding the '
                  'part has returned too',
    'neutral': 'the agent now holding the part has returned',
}


def _since_opened(store, index, rec):
    """docs/05SoulRun 88 (T2, T3): what the host recorded about the open liveness stop's child after the stop opened while
    no return is recorded, and what that changes - the old ticket's start on a stop that offered the replacement as never
    seen starting, after which choosing the replacement no longer carries it (T2: replace_outcome), or an unclaimed
    continuation's failed delivery, after which a recheck passes (T3: recheck_outcome). dict(started, undelivered, rep,
    outcome), or None when no such record changes what an option does, or on any doubt."""
    from . import engine_core as ec
    if rec.get('dispatch_block') != 'DISPATCH_LIVENESS_UNKNOWN' or rec.get('answered_at'):
        return None
    try:
        entry = ec._catalog_entry(index, rec['node'])
        current = ec._self_dispatch(index, entry, rec['visit'])[1] if entry else None
        if not current or dispatch_lifecycle.returned(current):
            return None
        basis = rec.get('replacement_basis') or {}
        started = bool(basis and basis.get('start_evidence') is None and basis.get('ticket') == current.get('ticket')
                       and store.exists_path(store.cache_dir / f"_dispatch_start.{current['ticket']}.json"))
        undelivered = bool(_undelivered(current) and dispatch_lifecycle.failed_delivery(store, index, current))
    except (ec.EngineError, RunStoreError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    rep = replace_outcome(store, index, rec) if started else None
    outcome = recheck_outcome(store, index, rec) if undelivered else None
    started = bool(started and rep and rep['next'] != 'carried')
    undelivered = bool(undelivered and outcome and outcome['next'] != 'held')
    if not (started or undelivered):
        return None
    return dict(started=started, undelivered=undelivered, rep=rep if started else None, outcome=outcome if undelivered else None)


def _opened_texts(rec, live, answer_valid, zh):
    """docs/05SoulRun 88 (T2, T3): the menu hint, answer_hint and errors[0] of a liveness stop about whose unreturned child
    the host recorded something after the stop opened (_since_opened) - the fact, and what choosing the replacement (T2)
    or Recheck conditions (T3) now leads to, from the engine's own decision for that option. Record 90 (ledger decision
    190): after a reply at this stop the line and the answer_hint state what was done (_held_line, _asked_ack), never
    'valid reply'."""
    menu, host = [], []
    if answer_valid:
        menu.append(_held_line(rec, zh) if not live['undelivered'] else
                    '复核已执行；当时条件未满足。' if zh else 'Recheck executed; at that time a condition was unmet. ')
    if live['started']:
        rnext, rcode, new = live['rep']['next'], live['rep'].get('code'), bool(live['rep'].get('replacement'))
        if zh:
            # Review round 2 of docs/05SoulRun 88 (L2): the option note and the menu's Explanation (both written once when
            # the stop opened) say it was never seen starting; both are withdrawn.
            menu.append('宿主在这道题打开以后记下了旧票的启动（选项说明和「说明」里「没有见到它启动过」那两句已不适用）；没有换人，继续等待。' + (
                f'现在选「作废旧票，换一个新代理接着做」不会在这里换人：这道题会关闭，改在可以换一个新代理的那道题（{rcode}）上重新问你；'
                '建议里说的授权，要在那道题上再选一次换人才算。' if rnext == 'stop' and new else
                '先前推荐的「作废旧票，换一个新代理接着做」已不适用：现在选它不会换人' + (
                    f'，只会关闭这道题，改在另一道停顿（{rcode}）上重新问你，那里不能换新代理。' if rnext == 'stop' else
                    '，只会关闭这道题；主代理下一次取节点时先做一次有界的返回查询，之后再按新的记录问你。' if rnext == 'query' else '。')))
        else:
            menu.append("The host recorded the old ticket's start after this stop opened (the option note and the explanation "
                        'saying it was never seen starting no longer apply). Nothing was replaced; still paused. ' + (
                'Choosing to retire the old ticket now replaces nothing here; instead this stop closes and you are asked again at '
                f'the stop where one new agent can be chosen ({rcode}). The authorization in the advice takes effect only when '
                'you choose the new agent again at that stop.' if rnext == 'stop' and new else
                'The earlier recommendation to retire the old ticket no longer applies: choosing it now replaces nothing' + (
                    f'; it only closes this stop and asks you again at another stop ({rcode}), where no new agent can be chosen.'
                    if rnext == 'stop' else
                    "; it only closes this stop: the main agent's next-node first offers the one bounded return query, and then "
                    'you are asked again on the new records.' if rnext == 'query' else '.')))
        host.append("The host has since recorded the old ticket's start, so choosing to retire the old ticket " + (
            f'replaces nothing here: this stop closes and the human is asked again at {rcode}, where one new agent can be chosen'
            if rnext == 'stop' and new else
            f'replaces nothing: this stop closes and the human is asked again at {rcode}, where no new agent can be chosen'
            if rnext == 'stop' else
            "replaces nothing: this stop closes, and the main agent's next-node first offers the one bounded return query"
            if rnext == 'query' else 'now replaces nothing') + '.')
    if live['undelivered']:
        nxt, code, step = live['outcome']['next'], live['outcome'].get('code'), live['outcome'].get('step')
        if zh:
            menu.append('宿主之后记下了接着做的那条消息没送到（这条续接没有送到旧代理）；没有换人，继续等待。现在选「复核条件」' + (
                '会接回原来的子代理' if nxt == 'continues' else
                f'会转到另一道停顿（{code}），那里会写明原因' if nxt == 'stop' else
                '可以通过，引擎按现在的记录给出下一步' + (
                    '：主代理按引擎的说明处理后，引擎会作废这张没送到的续接票，按它自己的续接规则改派一个新代理接着做这一段'
                    if step == 'wait_handoff' else '')) + '；也可以取消。')
        else:
            menu.append('The host has since recorded that the continuation message was never delivered (it did not reach the old '
                        'agent). Nothing was replaced; still paused. ' + (
                'Recheck conditions now resumes the original sub-agent' if nxt == 'continues' else
                f'Recheck conditions now leads to another stop ({code}), which states its cause' if nxt == 'stop' else
                'Recheck conditions now passes: the engine shows the next step on the current records' + (
                    "; once the main agent follows the engine's note, the never-delivered continuation ticket is retired and, by "
                    "the engine's own continuation rule, one new agent continues this part" if step == 'wait_handoff' else '')) +
                '; you may also cancel.')
        host.append('The host has since recorded that the continuation message was never delivered, so ' + (
            'Recheck conditions now resumes the original sub-agent' if nxt == 'continues' else
            f'Recheck conditions now leads to another stop ({code})' if nxt == 'stop' else
            'Recheck conditions now passes and the engine takes its next step on the current records' + (
                "; by the engine's own continuation rule the never-delivered continuation is then replaced by one new agent"
                if step == 'wait_handoff' else '')) + '.')
    told = ' '.join(host)
    base = rec.get('dispatch_error', {}).get('message') or rec.get('cause') or 'Old executor return is unverified'
    error = (told if live['undelivered'] else f"{base.rstrip('.')}. {told}") + ' No competing executor is allowed.'
    # Review round 4 (W3): without `answer_valid` (a stop just opened by the answer that retired the one before it) the
    # answer_hint acknowledges no reply - none was given here; reply() adds what that answer did.
    answer_hint = (((_asked_ack(rec) if live['undelivered'] else
                     _asked_ack(rec) + 'Without a recorded return a recheck still does not pass. ')
                    if answer_valid else '') + told +
                   ' Present the menu and wait for the human; do not continue, replay work or retry on your own.')
    return ''.join(menu) if zh else ' '.join(part.strip() for part in menu), answer_hint, error


def _recorded_gone(index, rec):
    """Review round 4 of docs/05SoulRun 88 (W4): True for an answered stop `rec` whose recorded (carried) replacement names a
    ticket the part no longer runs - the one _complete_recorded never carries out (it retires the stop and asks anew)."""
    from . import engine_core as ec
    replaced = rec.get('replacement_authorization')
    if rec.get('resolution_kind') == 'cancel' or rec.get('replacement_refused') or not replaced:
        return False
    try:
        current = ec._self_dispatch(index, ec._catalog_entry(index, rec['node']), rec['visit'])[1]
    except (ec.EngineError, KeyError, TypeError, AttributeError):
        return False
    return not (current and current.get('ticket') == replaced.get('previous_ticket'))


def _recorded_texts(rec, zh, gone=False):
    """Review round 3 of docs/05SoulRun 88 (R3): the menu line, answer_hint and errors[0] of the active engine stop `rec`
    whose answer is recorded but was cut off before the run went on (a crash between its gate record and the index) - the
    recorded choice, that it is not finished, that the next reply first completes it as recorded whatever it says (a new
    choice is not taken), and that cancel stays available at a stop that follows (a recorded cancel ends the run). Review
    round 4 (W4): worded from what the record says the first attempt decided - a refused replacement choice
    (replacement_refused) and a recorded replacement whose ticket is gone (`gone`, _recorded_gone) replace nothing: the
    next reply closes the stop and the human is asked again."""
    label, intent = rec.get('chosen_label') or rec.get('chosen_intent'), rec.get('chosen_intent')
    cancel = rec.get('resolution_kind') == 'cancel'
    refused = not cancel and bool(rec.get('replacement_refused'))
    if refused or gone:
        if zh:
            menu = ((f'你在这道题上选了「{label}」，但你回答时它依据的记录已经变了，所以不会换人（建议里说的授权不适用于这次答复）；'
                     '运行在关闭这道题、按现在的记录重新问你之前中断了。' if refused else
                     f'你在这道题上的答复「{label}」已经记下，但它授权替换的那张票已经不是这一段现在的票，所以不会换人；运行在处理它的中途中断了。')
                    + '你下一次回复时，引擎先关闭这道题（不换人），再按现在的记录重新问你；新回复不管写什么（包括别的选项、取消或终止），'
                    '都不会改变这一点。重新问你时，你可以在那道题上取消。')
        else:
            menu = ((f'You chose ({label}) at this stop, but the records it was offered on had already changed when you answered, so '
                     'nothing will be replaced (the authorization in the advice does not apply to this answer); the run stopped '
                     'before it closed this stop and asked you again. ' if refused else
                     f"Your answer to this stop ({label}) is recorded, but the ticket it authorized replacing is no longer this "
                     "part's ticket, so nothing will be replaced; the run stopped while carrying it out. ")
                    + 'Your next reply first closes this stop (nothing is replaced) and you are then asked again on the current '
                    'records; whatever the new reply says (another option, cancel or stop included) does not change that. When '
                    'you are asked again, you can cancel there.')
        told = (f"The human's answer at {rec['question_id']} ({intent}) is recorded and was refused as stale when it was given, "
                'so nothing will be replaced; the run stopped before this stop was closed' if refused else
                f"The human's answer at {rec['question_id']} ({intent}) is recorded, but the ticket it authorized replacing is no "
                "longer this part's ticket, so it is not carried out and nothing will be replaced") + (
                '. The next reply closes this stop and the human is asked again on the current records; it is not taken as a '
                'new choice')
        return (menu, f'{told}. Present the menu and wait for the human; do not continue, replay work or retry on your own.',
                f'{told}. No competing executor is allowed.')
    if zh:
        menu = (f'你在这道题上的答复「{label}」已经记下，但运行在处理它的中途中断了，还没处理完。你下一次回复时，引擎会先按这个答复'
                '处理完；新回复不管写什么（包括别的选项、取消或终止），都不会改变它。' +
                ('处理完，本次运行就结束。' if cancel else '处理完以后如果运行又停下来问你，可以在那道题上取消。'))
    else:
        menu = (f'Your answer to this stop ({label}) is recorded, but the run stopped while carrying it out, so it is not finished. '
                'Your next reply first completes that answer; whatever the new reply says (another option, cancel or stop included) '
                'does not change it. ' + ('Completing it ends this run.' if cancel else
                                          'If the run then stops to ask you again, you can cancel there.'))
    told = (f"The human's answer at {rec['question_id']} ({intent}) is recorded but was not carried out before the run stopped; "
            'the next reply completes it as recorded and is not taken as a new choice')
    return (menu, f'{told}. Present the menu and wait for the human; do not continue, replay work or retry on your own.',
            told + ('; completing it ends this run' if cancel else '') + '. No competing executor is allowed.')


def _completed_lead(rec, text, zh, *, retired=False):
    """Review round 3 (R3): the line the reply after a recovery opens with - the recorded answer was completed as recorded,
    and, unless the new reply named the same choice, that the new reply was not taken. (menu text, host text). Review round
    4 (W4): a recorded refusal (replacement_refused) is said to be closed as decided when it was given - nothing was
    replaced; a recorded replacement whose ticket is gone (`retired`, _complete_recorded's fallback) is said not to have
    been carried out - never 'completed as recorded' next to 'nothing was replaced'."""
    from . import engine_core as ec
    label, intent = rec.get('chosen_label') or rec.get('chosen_intent'), rec.get('chosen_intent')
    option = ec._match_option(rec['options'], text.strip())
    said = 'cancel' if ((option and option['kind'] == 'cancel') or text.strip().lower() in (ec.CANCEL_WORDS | ec.TERMINATE_WORDS)) \
        else (option or {}).get('intent')
    same = said == intent
    refused = rec.get('resolution_kind') != 'cancel' and bool(rec.get('replacement_refused'))
    if zh:
        menu = (f'你先前在这道题上选的「{label}」已按你回答时的结果处理完：它依据的记录在你回答时就已经变了，所以没有换人' if refused else
                f'你先前在这道题上的答复「{label}」没能执行：它授权替换的那张票已经不是这一段现在的票，所以没有换人' if retired else
                f'你先前在这道题上的答复「{label}」已经按记下的样子处理完了') + ('。' if same else '；你这次的回复没有采用。')
    else:
        menu = (f'Your earlier choice at this stop ({label}) has now been closed as decided when you answered: the records it was '
                'offered on had already changed, so nothing was replaced' if refused else
                f"Your earlier answer to this stop ({label}) could not be carried out: the ticket it authorized replacing is no "
                "longer this part's ticket, so nothing was replaced" if retired else
                f'Your earlier answer to this stop ({label}) has now been completed as recorded') + (
            '.' if same else '; your new reply was not taken.')
    host = (f"The human's answer recorded earlier at {rec['question_id']} ({intent}) was refused as stale when it was given and "
            'is now closed as decided then: nothing was replaced' if refused else
            f"The human's answer recorded earlier at {rec['question_id']} ({intent}) could not be carried out: the ticket it "
            "authorized replacing is no longer this part's ticket, so nothing was replaced" if retired else
            f"The human's answer recorded earlier at {rec['question_id']} ({intent}) was completed as recorded")
    return menu, host + ('.' if same else '; the new reply was not taken.')


def _capability_back(store, index, rec):
    """Review round 3 of docs/05SoulRun 88 (O2): for the open SUBTREE_AGENT_CAPABILITY_UNAVAILABLE stop `rec` once the host
    declares the Agent tool again, the move its recheck makes (_recheck_moves_on: dict(step, code, replacement)) because
    another condition now holds the part; None while the tool is still lost, or on any doubt. Read-only, as recheck_outcome.
    Review round 4 (W5): dict(step='met') where the recheck simply passes - the tool is declared and preflight no longer
    holds the part (the commonest tool-back case)."""
    from . import engine_core as ec
    if rec.get('dispatch_block') != SUBTREE_CAP or rec.get('answered_at') or not _capability_declared(index):
        return None
    try:
        program = ec._load_routed_program(ec._read_run_input(store))
        held = preflight(copy.deepcopy(index), program, ec._catalog_entry(index, rec['node']), store=_StopView(store, index, rec))
        return _recheck_moves_on(store, index, rec, program, held) if held else dict(step='met')
    except (ec.EngineError, RunStoreError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _met_texts(answer_valid, zh):
    """Review round 4 of docs/05SoulRun 88 (W5, inside the owner's O2 ruling 'the stop says the tool is back'): the menu
    hint, answer_hint and errors[0] of a SUBTREE stop whose capability the host declares now and whose preflight no longer
    holds the part, so Recheck conditions passes and the run goes on by the engine's existing rules - in the ordinary pool
    and at an independent root the main agent's next-node starts the part's agent, in the K1 shape it resumes the original
    sub-agent, and where a condition only next-node sees holds the part (record 84's after an error return in the ordinary
    pool) it opens that stop. After a held recheck it opens with what that reply did (as T3; record 90, ledger decision 190:
    facts only, never 'valid reply'). The question, written when the stop opened, still says the capability is not
    confirmed; the line says so."""
    if zh:
        menu = (('复核已执行；当时条件未满足。' if answer_valid else '') +
                '宿主现在声明了子代理（Agent）能力，这道题等的条件已经满足（上面题目里的「尚未确认」是这道题打开时的情况）。'
                '选「复核条件」会按现在的记录接着往下做：引擎按现有规则可能派出这一段的代理、接回原来的子代理，'
                '也可能在别的条件上再停下来问你；也可以取消。')
    else:
        menu = (('Recheck executed; at that time a condition was unmet. ' if answer_valid else '') +
                'The host now declares the sub-agent (Agent) capability, so the condition this stop waited for is met (the '
                '"not confirmed" in the question above was so when this stop opened). Recheck conditions goes on with the '
                "current records: by the engine's existing rules it may start this part's agent or resume its original "
                'sub-agent, or stop again to ask you on another condition; you may also cancel.')
    told = ('The host now declares the sub-agent (Agent) capability, so the condition this stop waited for is met: Recheck '
            "conditions goes on with the current records (by the engine's existing rules the run may then start this part's "
            'agent, resume its original sub-agent, or stop again on another condition)')
    return (menu,
            ('Recheck executed; at that time a condition was unmet. ' if answer_valid else '') + told +
            '. Present the menu and wait for the human; do not continue, replay work or retry on your own.',
            told + '. No competing executor is allowed.')


def _back_texts(back, answer_valid, zh):
    """Review round 3 (O2): the menu hint, answer_hint and errors[0] of a SUBTREE stop once the host declares the Agent
    tool again and another condition holds the part (_capability_back): the tool is declared again, what holds the part,
    and where Recheck conditions now leads - the stop is then closed and nothing is replaced or started. Review round 4:
    'now declares' (W1: a run whose host never declared it before the stop opened has it declared, not declared 'again');
    the answer_hint acknowledges a reply only with `answer_valid` (W3); where the recheck simply passes, _met_texts (W5)."""
    if back.get('step') == 'met':
        return _met_texts(answer_valid, zh)
    code, query, new = back.get('code'), back.get('step') == 'query', bool(back.get('replacement'))
    host = ("after Recheck conditions the main agent's next-node first offers the one bounded return query, and the human is "
            'asked again on the new records' if query else
            'Recheck conditions leads to the stop where one new agent can be chosen' if new else
            f'Recheck conditions leads to a stop where only cancel remains ({code})' if code in _BOUND_STOPS else
            f'Recheck conditions leads to another stop ({code})')
    held = (f'another condition now holds this part ({code})' if code else 'this part needs the one bounded return query first')
    if zh:
        menu = ('复核已执行；当时条件未满足。' if answer_valid else '') + '宿主现在声明了子代理（Agent）能力，这道题等的条件已经满足，但' + (
            f'现在拦着这一段的是另一个条件（{code}）' if code else '这一段还要先做一次有界的返回查询') + '：' + (
            '选「复核条件」后，主代理下一次取节点时先做一次有界的返回查询，之后再按新的记录问你' if query else
            '选「复核条件」会转到可以换一个新代理的那道题' if new else
            f'选「复核条件」会转到只剩取消的停顿（{code}）' if code in _BOUND_STOPS else
            f'选「复核条件」会转到另一道停顿（{code}）') + '，这道题随之关闭，不会换人，也不会派出代理；也可以取消。'
    else:
        menu = ('Recheck executed; at that time a condition was unmet. ' if answer_valid else '') + (
            'The host now declares the sub-agent (Agent) capability, so the condition this stop waited for is met, but '
            f'{held}: {host[0].upper() + host[1:]}; this stop then closes, and nothing is replaced or started; you may also cancel.')
    return (menu,
            ('Recheck executed; at that time a condition was unmet. ' if answer_valid else '') +
            f'The host now declares the sub-agent (Agent) capability, but {held}: {host}. '
            'Present the menu and wait for the human; do not continue, replay work or retry on your own.',
            f'The host now declares the sub-agent (Agent) capability, but {held}: {host}; this stop then closes and nothing '
            'is replaced or started. No competing executor is allowed.')


# Record 90 (ledger decision 190): a stop asked again after an answer - this stop after a reply given here, or the stop
# _ask_again opened after the answer at the stop before it - states what was done and asks again; it never calls a reply
# valid, since the records cannot tell an answer the engine used from one record 88's recovery completed with the newer
# reply set aside. Wording only: answer_valid and answer_disposition are as before.
def _stale_reply(rec):
    """The last reply at the stop `rec` was a replacement choice refused because its records had changed (answer()'s
    DISPATCH_REPLACEMENT_STALE attempt, the stop kept); otherwise a recheck that did not pass."""
    attempts = rec.get('recheck_attempts') or []
    return bool(attempts) and attempts[-1].get('reason') == 'DISPATCH_REPLACEMENT_STALE'


def _held_line(rec, zh):
    """The menu line of the stop `rec` asked again at once after the reply given here (decision 190)."""
    if _stale_reply(rec):
        return ('这个换人选项依据的记录已经变了，没有换人；请再答一次。' if zh else
                'The records this replacement was offered on have changed, so nothing was replaced. Please answer again.')
    return '复核已执行；当时条件未满足，请再答一次。' if zh else 'Recheck executed; conditions were not met then. Please answer again.'


def _asked_ack(rec):
    """The host sentence on the reply given at the stop `rec`, asked again at once (decision 190)."""
    if _stale_reply(rec):
        return 'The replacement choice was not carried out: the records it was offered on had changed, so nothing was replaced. '
    return 'Recheck executed; conditions were not met then. '


def _again_host(rec):
    """The host sentence opening a reply of the stop `rec` that _ask_again opened (decision 190): what was done with the
    answer at the stop before it, by the supersedes link - true of a first attempt and of record 88's recovered answer."""
    link = rec.get('supersedes') or {}
    if link.get('reason') == RECHECK_MOVED_ON:
        return (f"The recheck answered at the stop before ({link.get('question_id')}) was executed: that stop is closed, "
                'nothing was replaced and no agent was started; this stop asks again. ')
    return (f"The replacement choice answered at the stop before ({link.get('question_id')}) was not carried out: the "
            'records it was offered on had changed, so nothing was replaced; this stop asks again. ')


def reply(store, index, rec, hint=None, *, answer_valid=None, lead=None, asked=False, publish=True, first=None):
    """The served engine stop `rec`. Review round 3 of docs/05SoulRun 88: `lead` - (menu text, host text) a recovered
    answer's reply opens with (R3); an active stop that already carries an answer serves _recorded_texts (R3); a SUBTREE
    stop once the Agent tool is declared again serves _back_texts (O2). Review round 4 (W3): `asked` - `rec` was just
    opened by _ask_again (a stale choice, a retire or a recheck that moved on retired the stop before it) and `hint` says
    why: this stop's own facts follow that explanation instead of replacing it, and acknowledge no reply given here (none
    was) - after a recovery the host text never calls a reply valid next to 'the new reply was not taken'.
    Record 90 round 4 (B1): `publish` False - a serve to a sub-agent (a node-commit with its agent ticket), the reply to the
    gate-answer call that asked again (pause() from _ask_again, round 5) or a render check (orphan_stop): the stop's menu is
    not written, so the stop is not marked served to the main executor (a stop whose menu.<qid>.* file exists has been),
    and the reply names no menu file (public_prompt_ref None; the text is inline).
    Record 90 round 7 (ledger decisions 186 and 187, B1): `first` - the host sentence that opens the first serve of a stop
    asked again, where the records show the answer at the stop before was completed by record 88's recovery and could not
    be carried out (_asked_hint: a recorded replacement retired). Record 90 (ledger decision 190): no reply of a stop asked
    again - this stop after a reply here, or a stop _ask_again opened - says 'valid reply'; where the records cannot tell a
    first attempt from a recovered answer, its line and host text state what was done and ask again (_held_line,
    _asked_ack, _again_host). answer_valid and answer_disposition are unchanged."""
    from . import engine_core as ec
    if answer_valid is None:
        answer_valid = rec.get('last_reply_valid') is True
    ack = answer_valid and not asked
    zh = str(index.get('user_language')).startswith('zh')
    recorded = bool(rec.get('answered_at'))     # review round 3 (R3): a cut-off answer, completed by the next reply
    # Rounds 3-5 of the review of docs/05SoulRun 87 (D3, E2, E4, F1, F2): every serve of a liveness stop whose child has
    # since returned - held included - says what each option it offers now leads to: one decision each (recheck_outcome,
    # replace_outcome) for the menu, answer_hint and errors[], in place of a caller's hint (only answer()'s held recheck
    # passes one here; its reply now says what the next serve says).
    current = _since_returned(store, index, rec)
    outcome = (recheck_outcome(store, index, rec) or dict(next='other')) if current else None
    rep = replace_outcome(store, index, rec) if current else None
    failed = bool(current and dispatch_lifecycle.failed_return(store, current))
    story = _bound_story(current) if current else 'used'          # review round 3 (R5), round 4 (W6), round 5 (P1)
    own = None   # this stop's own facts: (menu text, answer_hint, errors[0])
    if current:
        own = (_returned_hint(rec, outcome, rep, failed, zh, story),
               *_returned_host_texts(outcome, rep, failed, story, ack=_asked_ack(rec) if ack else ''))
    # docs/05SoulRun 88 (T2, T3): likewise while no return is recorded, once the host recorded the old ticket's start or a
    # continuation's failed delivery after the stop opened - in place of the stored acknowledgement of a held recheck.
    live = None if current else _since_opened(store, index, rec)
    if live:
        own = _opened_texts(rec, live, ack, zh)
    back = None if current or live else _capability_back(store, index, rec)      # review round 3 (O2), round 4 (W5)
    if back:
        own = _back_texts(back, ack, zh)
    shown, host_hint, host_error = own or (hint, None, None)
    if asked and own and hint:   # review round 4 (W3): why this stop was opened, then its own facts
        shown = hint + ('' if zh else ' ') + own[0]
    closing = False
    if recorded:   # review round 4 (W4): a recorded answer that replaces nothing only closes this stop
        gone = _recorded_gone(index, rec)
        closing = gone or (rec.get('resolution_kind') != 'cancel' and bool(rec.get('replacement_refused')))
        shown, host_hint, host_error = _recorded_texts(rec, zh, gone=gone)
    if answer_valid and shown is None:
        shown = _held_line(rec, zh)
    if lead:
        shown = lead[0] + (('' if zh else ' ') + shown if shown else '')
    prompt = render.menu_block(rec, hint=shown, user_language=index.get('user_language'),
                               answered='close' if closing else recorded)
    name = f"menu.{rec['question_id']}.txt"
    if publish:
        store.write_public(name, prompt)
    if asked and host_hint and not lead:   # round 4 (W3): the reply to the answer given at the stop before this one
        host_hint = (first or _again_host(rec)) + host_hint
    told = host_hint if recorded else (host_hint or (
        (first or (_again_host(rec) if asked else _asked_ack(rec) + 'This stop asks again. ')) +
        'Present the menu and wait for the human; do not call an earlier reply invalid, replay work or retry without new '
        'evidence.')) if answer_valid else hint
    if lead:   # review round 3 (R3): the recovered answer, then this stop's own facts - never 'valid reply' for the new reply
        told = f"{lead[1]} {host_hint or 'Present the menu and wait for the human; do not continue, replay work or retry on your own.'}"
    return dict(status='WAITING_USER', run_state='WAITING_USER', schema_version=1,
                run=dict(trace_id=index['trace_id'], state='WAITING_USER'), node=None, steps=[],
                public_plan=None, public_plan_ref=None, public_block=None, submission_accepted=False,
                answer_valid=answer_valid, conditions_satisfied=False,
                answer_disposition='VALID_RECHECK_STILL_WAITING' if answer_valid else 'NO_ACCEPTED_RECHECK',
                answer_hint=told,
                gate=dict(question_id=rec['question_id'], state='WAITING_USER', required=True,
                          source='hsaw_doubt', kind='choice', advisory=False, prompt_text=None,
                          public_prompt=prompt, public_prompt_ref=ec._ref(store, name) if publish else None),
                resume=dict(kind='waiting_user', source=rec['question_id']), next=None,
                errors=[dict(code=rec['dispatch_block'], message=host_error or (
                    rec.get('dispatch_error',{}).get('message') or rec.get('cause') or ('Old executor return is unverified; no competing executor is allowed.'
                    if rec['dispatch_block'] == 'DISPATCH_LIVENESS_UNKNOWN' else 'Independent execution is required; inline fallback is forbidden.')))])


def _undelivered(current):
    """Round 5 (F3): True for an unclaimed continuation ticket - the one kind for which a record other than a return lets
    a recheck at its liveness stop pass: the host's record that its SendMessage failed (the engine's own handoff rule,
    record 86 #11: dispatch_lifecycle.handoff)."""
    d = current or {}
    return d.get('state') == 'ISSUED' and not d.get('claimed_at') and d.get('reason') in ('gate_resume', 'segment_resume')


def _stop_terms(store, index, reason, current, zh, *, facts=None, outcome=None):
    """docs/05SoulRun 87 (record 86 #22): the stops the engine opens for its own dispatch state say what actually
    stopped it, what is kept and what each option does. None for the independence and requirement stops, whose
    wording already states their cause. Round 4: the lapsed-choice stop words its recheck from `outcome`
    (recheck_outcome) and what was recorded after the choice from `facts` (dispatch_lifecycle.lapse_facts). Review round 3
    of docs/05SoulRun 88 (O3): INDEPENDENT_ATTEMPTS_EXHAUSTED at the attempt bound of an unfinished return states that
    cause; every other independence stop keeps its wording."""
    from . import engine_core as ec
    kept = '已提交的节点、已答的门和全部证据都保留，不重做。' if zh else ' Accepted nodes, answered gates and all evidence are kept and not redone.'
    cancel = '结束本次运行；保留全部证据和已完成的工作，不重放。' if zh else 'End this run; all evidence and accepted work are kept, nothing is replayed.'
    used = int((current or {}).get('replacement_count') or 0)
    spent = ((f'这一段已经换过 {used} 次新代理，到了上限，不能再换。' if zh else
              f' This part was already replaced {used} times, the limit; no further replacement.')
             if used >= ec.DISPATCH_ATTEMPTS_MAX else '')
    if reason == 'DISPATCH_LIVENESS_UNKNOWN':
        seen = (current or {}).get('interruption_observation') or {}
        sent = _undelivered(current)
        if seen:
            what = (f"运行被打断（{seen.get('reason')}，{seen.get('at')}）时，子代理还拿着这一段的票；引擎无法核实它是否已经停下" if zh else
                    f"The run was interrupted ({seen.get('reason')}, {seen.get('at')}) while a sub-agent held the ticket of this part; "
                    'the engine cannot verify whether it stopped')
            cause = f"the run was interrupted ({seen.get('reason')}) while a sub-agent held the ticket of this part; whether it stopped is unverified"
        else:
            what = ('宿主没有记下这一段子代理的返回；引擎无法核实它是否已经停下' if zh else
                    'The host recorded no return from the sub-agent of this part; the engine cannot verify whether it stopped')
            cause = 'the host recorded no return from the sub-agent holding this part; whether it stopped is unverified'
        return dict(cause=cause, text=what + ('，已暂停；引擎不会自己启动第二个执行者。' if zh else '. Paused; the engine never starts a second executor on its own.'),
            kept=kept + spent,
            # Round 4 (E2): what a recorded return leads to depends on it (recheck_outcome). Round 5 (F2, F3): the menu says
            # what Recheck then leads to in every returned state (reply); without a return - or, for an unclaimed
            # continuation, the host's record that its SendMessage failed (record 86 #11, `sent`) - the recheck is held.
            recheck=('再核对一次有没有它的返回记录。记下了返回，这个菜单会写明这时选「复核条件」会怎样。宿主重启后通常再也记不到；'
                     f"没有返回记录{'、也没有记下接着做的那条消息没送到' if sent else ''}时，复核不会通过，运行继续停在这里。" if zh else
                     'Check again for a recorded return from that sub-agent. Once one is recorded, this menu says what Recheck '
                     'conditions then leads to. After a host restart it usually can no longer be recorded; without it'
                     f"{' and without a record that the continuation message was never delivered' if sent else ''}, a recheck "
                     'does not pass and the run stays paused here.'),
            cancel=cancel + ('取消停不了一个可能还在跑的旧代理。' if zh else ' Cancelling cannot stop an old agent that may still be running.'),
            advice=(('引擎只认宿主记下的返回，或者宿主记下的接着做的那条消息没送到；超时、模型自报或报错文字都代替不了它们。' if sent else
                     '引擎只认宿主记下的返回；超时、模型自报或报错文字都代替不了它。') if zh else
                    ('The engine relies only on a host-recorded return, or a host record that the continuation message was never '
                     'delivered; age, a model claim or error text cannot replace them.' if sent else
                     'The engine relies only on a host-recorded return; age, a model claim or error text cannot replace it.')))
    if reason == 'DISPATCH_REPLACEMENT_LAPSED':   # review of docs/05SoulRun 87, rounds 3-4 (D2, E1)
        qid = (facts or {}).get('question_id') or ((current or {}).get('human_replacement') or {}).get('question_id')
        what = dispatch_lifecycle.lapse_words(facts, zh=zh)
        # E1: this stop opens only where the engine would resume the old agent or go on otherwise (pause), and says which.
        resume = bool(outcome and outcome.get('next') == 'continues')
        return dict(cause=f"the human chose a new agent at {qid}, but the host recorded {dispatch_lifecycle.lapse_words(facts, zh=False)} "
                          f"after that choice; nothing was replaced and {'the old agent is not resumed' if resume else 'nothing goes on for this part'} "
                          'without a new answer',
            text=(f'你在 {qid} 选了「作废旧票，换一个新代理接着做」；新代理派出之前，宿主记下了{what}。这次选择依据的记录已经变了：'
                  f"引擎没有换人，也不会不问你就{'接回旧代理' if resume else '往下做'}，已暂停。" if zh else
                  f"At {qid} you chose to retire the old ticket and continue with a new agent; before the new agent was started, "
                  f"the host recorded {what}. The records that choice was made on have changed: nothing was "
                  f"replaced, and the engine does not {'resume the old agent' if resume else 'go on'} without asking you. Paused."),
            kept=kept,
            recheck=(('按宿主记下的这条返回接着做：接回原来的子代理；不换人。' if zh else
                      'Continue with the recorded return: the original sub-agent is resumed; nothing is replaced.') if resume else
                     (f'按现在的记录往下做，由引擎给出下一步；你在 {qid} 选的换人不会执行。' if zh else
                      f'Go on with the current records; the engine shows the next step. The replacement chosen at {qid} is not '
                      'carried out.')),
            cancel=cancel,
            advice=(('旧代理的返回只说明它的 Agent 调用结束了，不证明它在引擎之外的动作都已完成。要按这条返回接着做，选「复核条件」；'
                     '不想再用它，就取消。' if zh else
                     "The old agent's return shows only that its Agent call ended, not that its actions outside the engine "
                     'completed. To go on with that return, choose Recheck conditions; if you no longer want it, cancel.') if resume else
                    ('你选的换人依据的记录已经变了，引擎不会执行它；要按现在的记录往下做，选「复核条件」；不想往下做，就取消。' if zh else
                     'The records your replacement choice was made on have changed, so it is not carried out. To go on with the '
                     'current records, choose Recheck conditions; otherwise cancel.')))
    if reason == 'INDEPENDENT_ATTEMPTS_EXHAUSTED' and _at_bound(index, current):
        # Review round 3 of docs/05SoulRun 88 (O3, owner decision (b)): at an independent root whose unfinished return reached
        # the attempt bound the cause is the part's used-up continuation (by its history, R5: _handed_off), as next-node's
        # CONTINUATION_EXHAUSTED states it - not that independent execution is unavailable. Options and recommendation unchanged.
        # Review round 4 (W6): after a handoff, worded from the dispatch that now holds the part (_bound_story); review
        # round 5 (P1): the round-3 wording only where the agent the continuation reached holds the part ('used').
        story = _bound_story(current)
        inline = ('已暂停；独立执行的这一段不会改由主代理内联去做，也不会再派新代理。' if zh else
                  'Paused; this independent part is never taken over inline and no new agent is started.')
        if story != 'used':
            return dict(_handed_terms(story, zh, inline, independent=True), kept=kept, cancel=cancel)
        return dict(cause='the sub-agent of this part returned unfinished again; one same-agent continuation per part, and an '
                          'independent part never falls back inline',
            text=('这一段的子代理第二次没做完就返回了；同一段只接回原子代理一次，那一次已经用过，' + inline if zh else
                  'The sub-agent of this part returned unfinished a second time; one same-agent continuation per part is allowed and '
                  'it is used. ' + inline),
            kept=kept, cancel=cancel, recheck=_USED_RECHECK[zh],
            advice=('要继续，先查明它为什么两次都没做完（例如一个节点对一次会话太大）。' if zh else
                    'To go on, first find out why it returned unfinished twice (a node too large for one session, say).'))
    if reason.startswith('ORIGINAL_EXECUTOR_'):
        # Round 5 (F3, record 86 #22): a recheck here keeps this stop where preflight refuses it (an independent root) and
        # opens a new stop of the same kind where the main agent's next-node raises it again (the ordinary pool, a sub node
        # of an independent root) - either way the run stays paused for the human's answer.
        recheck = ('再核对一次能否接回原来的子代理；不会派新代理。接不回的话，运行仍然暂停，等你再选。' if zh else
                   'Check again whether the original sub-agent can be resumed; no new agent is started. If it still cannot, the run '
                   'stays paused for your answer.')
        if reason == 'ORIGINAL_EXECUTOR_CONTINUATION_EXHAUSTED':
            # Review round 4 of docs/05SoulRun 88 (W7): on the handoff path its question, cause, recheck note and advice
            # follow the part's history as R5 and O3 do; after the same-agent continuation the round-3 wording stays -
            # review round 5 (P1): only while the agent it reached holds the part (_bound_story 'used').
            story = _bound_story(current)
            if story != 'used':
                return dict(_handed_terms(story, zh, '已暂停；不会改由主代理内联去做。' if zh else
                                          'Paused; the main agent does not take over inline.', independent=False),
                            kept=kept, cancel=cancel)
            return dict(cause='the sub-agent of this part returned unfinished again; one same-agent continuation per part',
                text=('这一段的子代理第二次没做完就返回了；同一段只接回原子代理一次，已暂停；不会改由主代理内联去做。' if zh else
                      'The sub-agent of this part returned unfinished a second time; one same-agent continuation per part is allowed. '
                      'Paused; the main agent does not take over inline.'),
                kept=kept, cancel=cancel, recheck=_USED_RECHECK[zh],
                advice=('要继续，先查明它为什么两次都没做完（例如一个节点对一次会话太大）。' if zh else
                        'To go on, first find out why it returned unfinished twice (a node too large for one session, say).'))
        if reason == 'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE':
            failed = bool(current and dispatch_lifecycle.failed_return(store, current))
            # docs/05SoulRun 88 (T1): a child that returned without an identity has its return recorded and final (a second
            # one is RETURN_ALREADY_OBSERVED); only a child that has not returned (paused) may still get a record that counts.
            final = not failed and dispatch_lifecycle.returned(current)
            return dict(cause=('the sub-agent of this part came back with an error before finishing it and has no identity to resume'
                               if failed else 'the sub-agent of this part stopped and the engine has no verified identity to resume it'),
                text=(('这一段的子代理没做完就带着错误返回了（例如模型用量上限、断线），没有可接回的身份' if failed else
                       '这一段的子代理停下了，引擎没有可核实的身份去接回原来的子代理') + '，已暂停；引擎不会自己换人。' if zh else
                      ('The sub-agent of this part came back with an error before finishing it (a usage limit or a broken connection, say) '
                       'and has no identity to resume' if failed else
                       'The sub-agent of this part stopped and the engine has no verified identity to resume it') +
                      '. Paused; the engine never replaces it on its own.'),
                kept=kept + spent, recheck=recheck, cancel=cancel,
                advice=(('没有接回或换人的依据时，只剩复核或取消；它是带着错误返回的，复核接不回它，运行仍然暂停。' if failed else
                         '没有接回或换人的依据时，只剩复核或取消；它的返回已经记下，但没有留下可核实的身份，这条返回不会再变，'
                         '复核接不回它，运行仍然暂停。' if final else
                         '没有接回或换人的依据时，只剩复核或取消；除非宿主又记下了关于它的新记录（例如它的返回），复核接不回它，运行仍然暂停。')
                        if zh else
                        'Without grounds to resume or replace it, only recheck or cancel remain; ' +
                        ('it came back with an error, so a recheck does not resume it and the run stays paused.' if failed else
                         'its return is recorded but carries no identity the engine can verify, and that return is final, so a '
                         'recheck does not resume it and the run stays paused.' if final else
                         'unless the host records something new about it (its return, say), a recheck does not resume it and the '
                         'run stays paused.')))
        return dict(cause='the original sub-agent and its parent session cannot be verified for a resume',
                    text=('原子代理及其父会话恢复尚未确认，已暂停；不能暗中换新代理。' if zh else
                          'Original child and parent-session continuation is unverified. Paused; no silent replacement.'),
                    kept=kept, recheck=recheck, cancel=cancel, advice=None)
    if reason.startswith('SUBTREE_'):
        conflict = reason == 'SUBTREE_MAIN_GRAPH_SCOPE_CONFLICT'
        return dict(cause=('the sub-agent scope re-enters an entry-file graph owned by another executor' if conflict else
                           'the host has not declared the sub-agent (Agent) capability this program needs'),
            text=(('子代理范围返回入口文件主图，执行者归属冲突，已暂停；不能越界提交或再派子代理。' if conflict else
                   '子图派发能力尚未确认，已暂停；不能假定存在Agent工具。') if zh else
                  ('The child scope re-enters an entry-file graph. Paused; no cross-owner submission or nested Agent.' if conflict else
                   'Subtree Agent capability is not confirmed. Paused; do not assume a tool exists.')),
            kept='',
            recheck=(('再核对一次执行者归属；不越界提交，条件未满足仍暂停。' if conflict else
                      '再核对一次宿主是否声明了子代理（Agent）能力；不假定它存在，条件未满足仍暂停。') if zh else
                     ('Check the executor ownership again; no cross-owner submission. Remains paused if unresolved.' if conflict else
                      'Check again whether the host declares the sub-agent (Agent) capability; it is never assumed. Remains paused if not.')),
            cancel=cancel, advice=None)
    return None


# Review round 3 (O3), round 4 (W6, W7) of docs/05SoulRun 88: the cause clause of the attempt-bound stops after a handoff.
_BOUND_CAUSE = {
    'handed': "the continuation never reached the original sub-agent, and the one new agent the engine's continuation rule gave "
              'the part returned unfinished too',
    'human': "the continuation never reached the original sub-agent, the engine's continuation rule gave the part to one new "
             'agent, and the new agent the human then chose in its place returned unfinished too',
    'other': 'the continuation never reached the original sub-agent and the part went to a new agent; the agent now holding '
             'the part returned unfinished too',
    # review round 5 (problem 86, P1)
    'used_human': 'its one same-agent continuation was used, and the new agent the human then chose in its place returned '
                  'unfinished too',
    'used_other': 'its one same-agent continuation was used and the part then went to a new agent; the agent now holding the '
                  'part returned unfinished too',
    'neutral': 'the agent now holding the part returned unfinished',
}


# The recheck note of the attempt-bound stops after the part's same-agent continuation was used (round 3 wording; review
# round 5, P1: kept where the part then went to a new agent - 'used_human', 'used_other').
_USED_RECHECK = {
    True: '再核对一次条件。这一段接回原子代理的那一次已经用过，所以复核既不会再接回它，也不会派新代理；运行仍然暂停，等你再选。',
    False: 'Check the conditions again. The one same-agent continuation of this part is already used, so a recheck neither '
           'resumes the original sub-agent nor starts a new agent; the run stays paused for your answer.',
}


def _handed_terms(story, zh, inline, *, independent):
    """Review round 3 (O3), round 4 (W6, W7): cause, question text, recheck note and advice of the attempt-bound stop -
    INDEPENDENT_ATTEMPTS_EXHAUSTED at an independent root's bound (`independent`) or ORIGINAL_EXECUTOR_CONTINUATION_EXHAUSTED
    - after the part's same-agent continuation never reached the original agent (`story` from _bound_story, not 'used'):
    worded from the dispatch that now holds the part. 'Returned unfinished twice' only where that is the whole history
    (the handoff agent itself returned); otherwise the advice does not count. Review round 5 (problem 86, P1): also after
    the continuation reached the agent and the part then went to a new agent ('used_human': the human chose it;
    'used_other': otherwise) - the round-3 recheck note stays, it is true there - and where no continuation is known to
    have reached the agent ('neutral': the attempts are used up and the agent holding the part returned unfinished - no
    'also', no count)."""
    return dict(
        cause="this part's attempts are used up: " + _BOUND_CAUSE[story] + ('; an independent part never falls back inline'
                                                                            if independent else ''),
        text=(f'这一段的尝试次数已经用完：{_bound_words(story, True)}没做完就返回了；' + inline if zh else
              f"This part's attempts are used up: {_bound_words(story, False)} {'also ' if _bound_also(story) else ''}"
              'returned unfinished. ' + inline),
        recheck=_USED_RECHECK[zh] if story in ('used_human', 'used_other') else
                ('再核对一次条件。这一段的尝试次数已经用完，所以复核既不会接回原来的子代理，也不会派新代理；运行仍然暂停，等你再选。' if zh else
                 "Check the conditions again. This part's attempts are used up, so a recheck neither resumes the original "
                 'sub-agent nor starts a new agent; the run stays paused for your answer.'),
        advice=(('要继续，先查明这一段为什么两次都没做完（例如一个节点对一次会话太大）。' if story == 'handed' else
                 '要继续，先查明这一段为什么没能做完（例如一个节点对一次会话太大）。') if zh else
                ('To go on, first find out why this part returned unfinished twice (a node too large for one session, say).'
                 if story == 'handed' else
                 'To go on, first find out why this part did not get finished (a node too large for one session, say).')))


def _interrupted_facts(store, index, current, basis, zh):
    """docs/05SoulRun 87: the facts a human weighs before replacing an interrupted child - the interruption, whether
    its start was ever seen, the return query, and the tool requests recorded since its last commit, or its claim
    when it has none (names and paths only)."""
    seen = basis['interruption_observation']
    lines = [f"中断记录：{seen.get('at')}，{seen.get('reason')}；旧代理是否已经停下：无法核实。" if zh else
             f"Interruption record: {seen.get('at')}, {seen.get('reason')}; whether the old agent stopped: unverified."]
    if basis['start_evidence'] is None:
        lines.append('宿主没有记下这张票的启动：没有见到它启动过。' if zh else 'The host recorded no start for this ticket: it was never seen starting.')
    else:
        lines.append(f"宿主记下过它启动（{basis['start_evidence']['path']}）。" if zh else
                     f"The host recorded its start ({basis['start_evidence']['path']}).")
    if basis['return_query']:
        lines.append('一次性返回查询已经给过，之后宿主没有记下它的返回。' if zh else
                     'The one bounded return query was offered; no return was recorded after it.')
    lines.append(tool_request_facts(store, index, current, zh))
    return '\n'.join(lines)


def tool_request_facts(store, index, current, zh):
    """Bounded diagnostic names and paths, never request contents or authority."""
    lines = []
    requests = dispatch_lifecycle.requests_since_progress(store, index, current)
    if requests is None:
        lines.append('它的工具请求记录读不出来，无法列出。' if zh else 'Its tool request records cannot be read; they cannot be listed.')
    elif not requests['count']:
        lines.append('它上次提交（或领取）之后，宿主没有记下它的工具请求；宿主没记下的动作无法列出。' if zh else
                     'Since its last commit (or claim) the host recorded no tool request from it; actions the host did not record cannot be listed.')
    else:
        lines.append(f"它上次提交（或领取）之后，宿主记下的工具请求 {requests['count']} 条（请求不等于已经写入；宿主没记下的动作无法列出）：" if zh else
                     f"Since its last commit (or claim) the host recorded {requests['count']} tool request(s) from it (a request is not proof "
                     'of a write; actions the host did not record cannot be listed):')
        for row in requests['rows']:
            state = ('有返回记录' if row['returned'] else '没有返回记录') if zh else ('result recorded' if row['returned'] else 'no result recorded')
            lines.append(f"- {row['tool']} {row['target'] or row['ref']} ({state})")
        if requests['count'] > len(requests['rows']):
            more = requests['count'] - len(requests['rows'])
            lines.append(f"另有 {more} 条，记在本次运行缓存的 _dispatch_tool.{current['ticket']}.* 里。" if zh else
                         f"{more} more are recorded in this run's cache as _dispatch_tool.{current['ticket']}.*.")
    return '\n'.join(lines)


def pause(store, index, reason, error=None, *, supersedes=None, why='DISPATCH_REPLACEMENT_STALE', hint=None, lead=None,
          publish=True):
    """Opens the engine stop `reason` at the run's current occurrence (the stop's write-once record, then _land) and
    serves it. Record 90 round 4 (B1): `publish` False when the reply goes to a sub-agent (a node-commit with its agent
    ticket, engine_core.commit) - round 5: or to the gate-answer call that asked again (_ask_again): the stop's menu is
    not written then, so it is not marked served to the main executor."""
    from . import engine_core as ec
    old = record(store, index)
    if old:
        return reply(store, index, old, publish=publish)
    now = now_iso()
    qid = f"q{len(index['gate']['history'])+1:03d}-{secrets.token_hex(4)}"
    node, visit = index['current']['name'], index['current']['visit']
    key = ec._node_key(node, visit)
    zh = str(index.get('user_language')).startswith('zh')
    text = ('独立执行条件不满足，已暂停；不能改为主代理自评。' if zh else
            'Independent execution is unavailable. Paused; self-review is not allowed.')
    entry = ec._catalog_entry(index, node)
    current = ec._self_dispatch(index, entry, visit)[1] if entry else None
    # Round 4 of the review of docs/05SoulRun 87 (E5): the human's accepted choice to retire this part's ticket that was not
    # carried out and is not yet acknowledged - every engine stop for the part says so, and its write-once record carries
    # the facts (dispatch_lifecycle.lapsed_replacement).
    lapse = dispatch_lifecycle.lapsed_replacement(store, index, current) if current else None
    facts = dispatch_lifecycle.lapse_facts(store, index, current) if lapse or (
        reason == 'DISPATCH_REPLACEMENT_LAPSED' and (current or {}).get('human_replacement')) else None
    outcome = None
    if reason == 'DISPATCH_REPLACEMENT_LAPSED':
        # E1: the lapsed-choice stop opens only where its recheck leads on (the old agent's resume, or the engine's other
        # step); where answer()'s recheck could not pass, or another stop would follow, that condition's own stop opens now.
        draft = dict(question_id=qid, node=node, visit=visit, source='hsaw_doubt', dispatch_block=reason,
                     lapsed_replacement=facts, previous_gate=copy.deepcopy(index['gate']),
                     previous_status=index['nodes'][key]['status'], answered_at=None)
        outcome = recheck_outcome(store, _install(copy.deepcopy(index), draft, now), draft)
        if outcome and outcome['next'] in ('held', 'stop') and outcome.get('code') != reason:
            reason, error = outcome['code'], None
    terms = _stop_terms(store, index, reason, current, zh, facts=facts, outcome=outcome)
    if terms:
        text = terms['text'] + terms['kept']
    if facts and reason != 'DISPATCH_REPLACEMENT_LAPSED':
        text = _lapse_lead(facts, zh) + text
    rec = dict(question_id=qid, node=node, visit=visit, source='hsaw_doubt', kind='choice', prompt_text=None,
        question=f'{text}\n{reason}', dispatch_block=reason,
        options=[dict(kind='execute', label='复核条件' if zh else 'Recheck conditions', intent='recheck_dispatch',
                      note=terms['recheck'] if terms else ('不增加额度、不取消独立要求；条件未满足仍暂停。' if zh else 'No budget increase or independence waiver; remains paused if unresolved.')),
                 dict(kind='cancel', label='取消本次运行' if zh else 'Cancel this run', intent='cancel',
                      note=terms['cancel'] if terms else ('保留所有证据，不重放已完成工作。' if zh else 'Preserve evidence; do not replay completed work.'))],
        recommendation='cancel', advice='建议取消后完成程序迁移或能力配置，再开新运行。' if zh else 'Cancel and configure the program/capability before a fresh run.',
        explanation=f"ordinary={usage(index, 'ordinary')}/{limit(index, 'ordinary')}; independent={usage(index, 'independent')}/{limit(index, 'independent')}",
        closing='回复完整编号或选项名。其它具体要求会保留，但不授权续行。' if zh else 'Reply with an exact number or label; other requirements do not authorize execution.',
        presented_at=now, delivered_at=None, answered_at=None, answer_text=None, resolution_kind=None,
        chosen_intent=None, chosen_label=None, consumed_by_commit=True,
        previous_gate=copy.deepcopy(index['gate']), previous_status=index['nodes'][key]['status'])
    if terms:
        rec['cause'] = terms['cause']
    if error is not None:
        diagnostic=error.as_dict()
        rec['dispatch_error']=diagnostic
        rec['explanation']+='\n'+json.dumps(diagnostic,ensure_ascii=False)
        rec['advice']=('先核对上述具体条件与原始证据；原因未明确前，不假定程序需要迁移或扩大权限。' if zh else
            'Inspect the specific condition and evidence first; do not assume a program migration or permission expansion is required.')
    if terms and terms['advice']:
        rec['advice'] = terms['advice']
    if reason == 'DISPATCH_LIVENESS_UNKNOWN':
        rec.update(explanation='Tool return evidence does not prove completion of external side effects.')
    if reason in _BUDGET_STOPS:
        program = ec._load_routed_program(ec._read_run_input(store))
        rec['dispatch_budget_proposal'] = proposal = _proposal(index, program)
        # The active menu is authoritative; cancellation remains the last option.
        rec['options'].insert(1, _extend_option(proposal, zh))
        rec['recommendation'] = 'extend_independent_budget'
        rec['advice'] = ('额度是唯一缺口时，可选择显名追加；其它执行条件不因此豁免。' if zh else
                         'If quota is the only unmet condition, authorize the exact addition; other requirements remain binding.')
    # docs/05SoulRun 84: a child that returned with an error cannot be resumed; the human may choose one new child.
    # docs/05SoulRun 87: also after it paused at an answered gate, and (owner ruling 10-28) when a host restart or a
    # recovery re-entry left its liveness unknown - with the risks stated, never as proof that the old child stopped.
    basis = dispatch_lifecycle.offered_basis(store, index, current, reason)
    if basis and reason == 'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE':
        rec['replacement_basis'] = basis
        rec['options'].insert(1, dict(kind='execute', intent='replace_executor',
            label='换一个新代理接着做' if zh else 'Continue with a new agent',
            note=('新代理从这一段第一个没完成的节点做起，已提交的节点不重做；被打断的那一步会重做一遍，'
                  '如果它已经对外写过东西，可能重复。' if zh else
                  'A new agent starts at the first unfinished node of this part; accepted nodes are not redone. The step '
                  'that was cut off is done again, so anything it already wrote outside may repeat.')))
        rec['recommendation'] = 'replace_executor'
        rec['advice'] = ('原代理是带着错误返回的（例如模型用量上限、断线），没有可接回的身份；引擎不会自己换人。'
                         '选「换一个新代理接着做」就是你授权这一次换人；不回答就什么都不跑。' if zh else
                         'The previous agent returned with an error (a usage limit or a broken connection, say) and has '
                         'no identity to resume; the engine never replaces it on its own. Choosing a new agent authorizes '
                         'this one replacement; without an answer nothing runs.')
    if basis and reason == 'DISPATCH_LIVENESS_UNKNOWN':
        rec['replacement_basis'] = basis
        rec['options'].insert(1, dict(kind='execute', intent='replace_executor',
            label='作废旧票，换一个新代理接着做' if zh else 'Retire the old ticket and continue with a new agent',
            note=('新代理从这一段第一个没完成的节点做起，已提交的节点不重做；被打断的那一步会重做一遍。'
                  '旧代理是否还在跑无法核实（在 Windows 上宿主停了，它也可能作为孤儿进程继续跑）；旧票作废后，它再向引擎提交都会被拒绝'
                  '（DISPATCH_TICKET_STALE），但它在引擎之外写的文件可能重复或冲突。' if zh else
                  'A new agent starts at the first unfinished node of this part; accepted nodes are not redone, and the step that '
                  'was cut off is done again. Whether the old agent is still running cannot be verified (on Windows it may keep '
                  'running as an orphan after its host stopped); once its ticket is retired, every commit from it is rejected '
                  '(DISPATCH_TICKET_STALE), but files it wrote outside the engine may be duplicated or conflict.')
                 + (('宿主从没记下这张票的启动：没有见到它启动过。' if zh else ' The host never recorded this ticket starting: it was never seen starting.')
                    if basis['start_evidence'] is None else '')))
        rec['recommendation'] = 'replace_executor'
        sent = ((('（或者记下接着做的那条消息没送到）' if zh else ' (or that the continuation message was never delivered)')
                 if _undelivered(current) else ''))      # round 5 (F3): the one other record that lets a recheck pass
        rec['advice'] = (f'这是你的风险选择，不是机器证明旧代理已经停下。取消同样停不了一个还在跑的旧代理；复核只有在宿主还能记下它的返回{sent}时才会通过。'
                         '选「作废旧票，换一个新代理接着做」就是你授权这一次换人；不回答就什么都不跑。' if zh else
                         'This is your risk choice, not machine proof that the old agent stopped. Cancelling cannot stop an old agent '
                         f'that is still running either; a recheck passes only if the host can still record its return{sent}. Choosing to '
                         'retire the old ticket authorizes this one replacement; without an answer nothing runs.')
        rec['explanation'] = _interrupted_facts(store, index, current, basis, zh)
    if facts:
        # Rounds 3-4 (D2, E5): bound to the choice that was not carried out and what was recorded after it; a recheck the
        # human answers at this stop acknowledges it (dispatch_lifecycle.lapsed_replacement).
        rec['lapsed_replacement'] = facts
    if reason == 'DISPATCH_REPLACEMENT_LAPSED' and facts:
        rec['recommendation'] = 'recheck_dispatch'
        rec['explanation'] = _lapse_explanation(current['human_replacement'], facts, zh)
    if supersedes:   # review of docs/05SoulRun 87 (C3): asked again because a stale choice retired that stop
        rec['supersedes'] = dict(question_id=supersedes, reason=why)   # docs/05SoulRun 88 (K1): or a recheck moved on (_ask_again)
    store.write_json_once(store.gate_path(qid), rec)
    _land(store, index, rec)
    return reply(store, index, rec, hint, answer_valid=True if supersedes else None, lead=lead, asked=bool(supersedes),
                 publish=publish)


_BUDGET_STOPS = frozenset(('INDEPENDENT_BUDGET_EXHAUSTED', 'INDEPENDENT_PREFLIGHT_BUDGET_INSUFFICIENT'))
_PROPOSAL_BASIS = 'declared_uncommitted_roots_not_future_branches_loops_or_retries'


def _proposal(index, program):
    """pause()'s dispatch_budget_proposal on the run `index` (its independent limit as preflight just refreshed it) and
    `program`: the exact number of independent claims to add for the declared roots not yet run. Record 90 round 4 (B4):
    shared with orphan_stop's check (_proposal_matches)."""
    rows, base = requirements(program)
    pending = remaining_roots(index, program, rows)
    return _proposed(base, limit(index, 'independent'), usage(index, 'independent'), pending)


def _proposed(base, current_cap, used, pending):
    added = max(1, len(pending) - max(0, current_cap-used))
    return dict(added=added, base_limit=base, prior_limit=current_cap, used=used, remaining_declared_roots=pending,
                basis=_PROPOSAL_BASIS)


def _extend_option(proposal, zh):
    """pause()'s budget-extension option for `proposal`: its label and note state the exact number added and the limits."""
    added, current_cap, base = proposal['added'], proposal['prior_limit'], proposal['base_limit']
    return dict(kind='execute', intent='extend_independent_budget',
                label=f'本场追加独立额度 {added} 次' if zh else f'Add {added} independent claims for this run',
                note=(f'只将本场上限{current_cap}提高到{current_cap+added}；不改变默认{base}或独立性要求。分支/循环/重试另计。' if zh else
                      f'This run only: {current_cap} to {current_cap+added}; default {base} and independence unchanged. Branches/loops/retries unknown.'))


def _lapse_lead(facts, zh):
    """The sentence an engine stop other than the lapsed-choice stop opens its question with when its record carries
    `facts` (lapsed_replacement)."""
    return (f"你在 {facts['question_id']} 选的「作废旧票，换一个新代理接着做」没有执行：之后宿主记下了"
            f"{dispatch_lifecycle.lapse_words(facts, zh=True)}，没有换人。" if zh else
            f"Your choice at {facts['question_id']} to retire the old ticket and continue with a new agent was not carried "
            f"out: after it the host recorded {dispatch_lifecycle.lapse_words(facts, zh=False)}; nothing was replaced. ")


def _lapse_explanation(chosen, facts, zh):
    """The lapsed-choice stop's explanation: the choice `chosen` (the part's human_replacement) and what the host recorded
    after it (`facts`; the return it kept is the ticket's exit evidence when the stop opened)."""
    kept_return = (facts.get('exit_evidence') or {}).get('path')
    return ((f"选择：{chosen['question_id']}（{chosen.get('answered_at')}）；之后宿主记下的旧代理返回：{kept_return}。"
             '返回记录不证明它在引擎之外的副作用都已完成。' if zh else
             f"Choice: {chosen['question_id']} ({chosen.get('answered_at')}); the old agent's return the host recorded "
             f'after it: {kept_return}. A return record does not prove its side effects outside the engine completed.')
            if kept_return else
            (f"选择：{chosen['question_id']}（{chosen.get('answered_at')}）；之后宿主记下了"
             f"{dispatch_lifecycle.lapse_words(facts, zh=True)}。" if zh else
             f"Choice: {chosen['question_id']} ({chosen.get('answered_at')}); after it the host recorded "
             f"{dispatch_lifecycle.lapse_words(facts, zh=False)}."))


def _land(store, index, rec):
    """pause()'s writes after the stop's write-once record `rec`: the run with `rec` as its active stop (_install, at the
    instant pause() stamped on the record), its anomalies_summary row and the index. Problem 85 (docs/05SoulRun 90 §2,
    ledger decision 181): reinstall() does exactly these for a record whose index write never landed, on the index as it
    was last written (see reinstall for what that leaves out)."""
    from . import engine_core as ec
    _install(index, rec, rec['presented_at'])
    qid = rec['question_id']
    index['anomalies_summary'].append(dict(node=rec['node'], code=rec['dispatch_block'],
                                           text=f"Paused at {qid}: {rec['cause']}." if 'cause' in rec else
                                           f'Paused at {qid}; independent execution cannot fall back inline.'))
    ec._write_index(store, index)
    return index


# Problem 85 (docs/05SoulRun 90 §2, ledger decision 181): the fields of the record pause() writes - always, sometimes - and
# the fields only an answer (answer()) adds to it later; delivery (mark_delivered) sets delivered_at.
_STOP_FIELDS = frozenset(('question_id', 'node', 'visit', 'source', 'kind', 'prompt_text', 'question', 'dispatch_block',
                          'options', 'recommendation', 'advice', 'explanation', 'closing', 'presented_at', 'delivered_at',
                          'answered_at', 'answer_text', 'resolution_kind', 'chosen_intent', 'chosen_label',
                          'consumed_by_commit', 'previous_gate', 'previous_status'))
_STOP_SOMETIMES = frozenset(('cause', 'dispatch_error', 'dispatch_budget_proposal', 'replacement_basis', 'lapsed_replacement',
                             'supersedes'))
_ANSWER_FIELDS = frozenset(('invalid_answers', 'last_reply_valid', 'recheck_attempts', 'answered_by', 'answer_text_original',
                            'human_wait_ms', 'budget_authorization', 'replacement_authorization', 'replacement_refused'))
_UNANSWERED = ('delivered_at', 'answered_at', 'answer_text', 'resolution_kind', 'chosen_intent', 'chosen_label')
_STOP_ID = re.compile(r'q(\d{3,})-[0-9a-f]{8}')
_STAMP = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z')          # now_iso()


def reinstall(store, index):
    """Problem 85 (docs/05SoulRun 90 §2, ledger decisions 181, 183 and 184): at the start of a next-node (engine_core._serve),
    node-commit (engine_core.commit), interpretation command (engine_core.interpret_human_reply, since the round-6 merge)
    or gate-answer (engine_core.answer_gate), before anything else reads the run, an engine stop whose index write never
    landed - the process died between the stop's write-once record and its index write - is installed as its writer
    would have: dispatch_budget.pause()'s stop (_land) or program_guard.pause()'s program-integrity stop
    (program_guard._land), when it is the one record that writer left there and matches the run exactly (unindexed_stop).
    pause()'s stop is recognised only while the run is RUNNING and the integrity stop also while it waits at a gate; the
    host's prepare calls gate-answer only while the run waits at a gate, so through prepare gate-answer installs only an
    integrity stop cut off over a waiting gate. program_guard.pause() also installs a cut-off integrity stop itself before
    it would open a second one (round 6: a backstop for the one call that reaches it without this install under the same
    lock, engine_core.serve's drift path). The stop then still needs the human's answer: it is not marked served until it
    is served to the main executor (only such a serve writes its menu, record 90 rounds 4-5: next-node and node-commit
    without an agent ticket, the interpretation command, a gate-answer at a stop already shown), so until then no message
    is taken as its answer (engine_core._unshown_stop); its first serve to the main executor is the reply its writer gave
    (served). Nothing is issued, answered or replayed here. Anything else is left as it is, for the orphan
    checks that stop with ENGINE_ORPHAN_WRITE_SET_UNPROVEN. Returns True when it installed a stop (`index` is then the
    run with it).
    Record 90 round 3 (B4): the same as the run that never stopped are the stop, its number, its supersedes link, its record
    (never rewritten), the gate, history, ticket, node status and anomalies row, every answer's outcome and every ticket,
    dispatch and authorisation, and what is served to the main executor. That first serve cannot rebuild a recovery's lead
    (round 4 B2; round 5): where the answer at the stop it retires was completed by record 88's recovery
    (_complete_recorded), pause()'s reply opened with that recovery's lead, built from the human's second reply, which no
    record keeps, and no record marks such a stop; that reply goes to the gate-answer call only (round 5: the stop asked
    again is opened unpublished), so with or without a crash in this window the main executor's first serve is rebuilt
    from the records alone (_asked_hint). Record 90 round 7 (ledger decisions 186 and 187): where a first attempt leaves
    the same records (a refused replacement choice, a recheck that moved on to another condition) its line is the first
    attempt's, which states what was done and calls no reply valid (record 90, ledger decision 190); where the records
    show the recovery (a recorded replacement it could not carry out, a move back to the retired stop's own condition)
    the line says what became of the recorded answer and that the reply received after it was not used, and calls no
    reply valid (_recovered_line). The index is the one last written, so a bookkeeping
    value the cut-off call had changed only in memory before pause() may lag behind that run: a part's preparation count
    (nodes.<n>.prepares), the independent limit preflight refreshed (dispatch.independent_hard_limit, refreshed again by
    every preflight before it is used) and a part's progress time (nodes.<n>.dispatch.last_progress_at; its dispatch file
    holds the newer value)."""
    from . import dispatch_identity
    if dispatch_identity.reinstall(store, index):
        return True
    found = unindexed_stop(store, index)
    if found is None:
        gate = dispatch_identity.record(store, index)
        if gate and not gate.get('answered_at') and not store.exists_path(
                dispatch_identity._authorization_path(store, gate['question_id'])):
            known = {row['question_id'] for row in index['gate']['history']}
            if any(path.stem.removeprefix('_gate.') not in known for path in store.cache_dir.glob('_gate.q*.json')):
                from . import engine_core as ec
                raise ec.EngineError('ENGINE_ORPHAN_WRITE_SET_UNPROVEN',
                                     'An unproven gate record precedes this handover; preserve it and stop.')
        return False
    land, rec = found
    land(store, index, rec)
    return True


def unindexed_stop(store, index):
    """Read-only: (its install, its record) for the engine stop reinstall() would install at the start of a next-node,
    node-commit, interpretation command or gate-answer: an identity fence/menu first, then the record
    dispatch_budget.pause() left, then program_guard.pause()'s integrity stop, or None. Identity observation and
    installation share dispatch_identity.orphan_stop; recognition never installs, shows or answers the question.
    Record 90 round 3 (ledger decision 183): prepare_cache's re-entry reads it as well (engine_core.unindexed_stop) and then
    records no transport wait and no interruption of the open ticket, as for the run that never stopped, waiting at that
    stop; it never installs the stop, so the human's message in that turn never answers a stop the human has not seen.
    The host's lifecycle calls read program_guard.orphan_stop through program_guard.landed_view (round 4 B7, round 5 B6),
    and program_guard.pause() reads it before it would open a second integrity stop (program_guard._cut_off, round 6).
    Record 90 round 4 (B6): recognising never raises on malformed data - any exception a recogniser meets is 'not
    recognised' (None): the record is left to the orphan checks, which stop with ENGINE_ORPHAN_WRITE_SET_UNPROVEN, and
    prepare_cache records the transport wait and the interruption as it did before round 3."""
    from . import dispatch_identity, program_guard
    for recognise, land in ((dispatch_identity.orphan_stop, dispatch_identity._land),
                            (orphan_stop, _land), (program_guard.orphan_stop, program_guard._land)):
        try:
            rec = recognise(store, index)
        except Exception:      # noqa: BLE001 - B6: what cannot be read as the engine's own stop is not installed
            rec = None
        if rec is not None:
            return land, rec
    return None


def unindexed_record(store, index):
    """Problem 85: the one gate record the run index does not know, parsed, when nothing else is unindexed and it carries
    the next number - (its question id, the record) - or None. Shared by the recognisers of the engine's two stops
    (orphan_stop, program_guard.orphan_stop):
      (4) its ordinal is the next one: q{len(history) + 1:03d};
      (5) it is the only gate record the index does not know, and nothing else is unindexed: the current node's cache is
          absent or the accepted one;
    and its bytes are the engine's canonical dump of what they parse to. A file that cannot be read or parsed - deeply
    nested JSON included (RecursionError, record 90 round 3) - gives None and is left to the orphan checks."""
    from . import program_guard
    from .run_store import _regular_path, dumps, strict_loads
    history = index['gate']['history']
    known = {row.get('question_id') for row in history}
    orphans = sorted(p for p in store.cache_dir.glob('_gate.q*.json') if p.stem.removeprefix('_gate.') not in known)
    if not orphans:
        return None
    if len(orphans) != 1 or _unindexed_cache(store, index):                                   # (5)
        return None
    program_guard.assert_run_version(index)
    path, qid = orphans[0], orphans[0].stem.removeprefix('_gate.')
    if qid != f"q{len(history) + 1:03d}-{qid.rpartition('-')[2]}":                           # (4)
        return None
    try:
        if not _regular_path(path):
            return None
        raw = store.read_bytes(path)
        rec = strict_loads(raw.decode('utf-8'))
        if not isinstance(rec, dict) or raw != dumps(rec).encode('utf-8'):
            return None
    except (OSError, ValueError, RecursionError, RunStoreError):
        return None
    return qid, rec


def orphan_stop(store, index):
    """Problem 85: the one unindexed gate record that pause() wrote and nothing touched since, matching the run exactly, or
    None; reinstall() installs it at the start of a next-node, node-commit, interpretation command or gate-answer. pause()
    runs only while the run
    is RUNNING, and its writes are the record, then the index:
      (1) never answered and never delivered - no answer or delivery field set, no menu written for it, no ledger event;
      (2) its node and visit are the run's current ones, an occurrence the index records;
      (3) its previous_gate is the run's current gate, history included;
      (4) its ordinal is the next one, and (5) it is the only unindexed write (unindexed_record).
    Record 90 round 3 (B2): pause() copies or stamps three values the index holds as they are, so they are checked there:
      (6) its previous_status is the node's status in the index;
      (7) its presented_at is no later than now and no earlier than any time the gate before it records (_in_order);
      (8) a supersedes link names the stop _ask_again retired: an answered engine dispatch stop of this node and visit,
          answered with the intent the link's reason names, followed only by answered program-integrity stops (_superseded,
          record 90 round 4 B5), and retired by that answer, never carried out: a replacement choice refused, a recorded
          replacement record 88's recovery could not carry out (the ticket it names is not the part's now), a recheck that
          moved on (_retired, round 6 B3 (1), round 7 B2); and this stop is the one _ask_again opened for that answer - no
          return query offered for the part since, where the retired liveness stop's basis records the query
          (_asked_at_once, round 7 B2).
    Record 90 round 4: (9) the values pause() computes from the run as it computed them, by type as well as value (_same,
    round 5 B1): a budget stop's dispatch_budget_proposal - present exactly when the stop is a budget stop and offers the
    extension - is what pause() computes from the run and the program now (_proposal: the amount added, the limits, the
    claims used and the declared roots not yet run), and the extension option's label and note are pause()'s for it; while
    the program's files differ from the run's binding (PROGRAM_DRIFT_DETECTED) the default and the roots not yet run are
    taken from the record's own figures (_proposal_matches); a lapsed_replacement names the choice and the ticket the part
    still carries, with pause()'s words for it, and that choice has lapsed now (round 5 B3: dispatch_lifecycle
    .lapsed_replacement names the same question and ticket; _lapse_matches); (10) it renders: the stop is served on
    copies, as next-node would serve it once installed, without writing (_renders, B3).
    The record must be pause()'s own: its exact canonical bytes, only pause()'s fields (an answer's or a delivery's being
    left to (1)), pause()'s fixed values, the types it writes, time stamp format and option frame, and its code with the
    facts pause() writes for that code (_pause_record, _code_facts: round 7 B2 - the replacement_basis's keys are those
    of the basis that code offers, the liveness stop's fixed explanation, the lapsed-choice stop's lapsed_replacement, a
    budget code's figures in (9)). The record carries no seal, here or anywhere, and these are not checked: the wording of
    the question, explanation, advice, cause, closing and recommendation, and the labels and notes of the recheck,
    replacement and cancel options (only the extension's are pause()'s); the dispatch_error pause() copied; the
    replacement_basis's values (answer() compares them with the basis the run gives when the replacement is chosen, and a
    mismatch replaces nothing); which code a stop names that carries no fact of its own (no basis, proposal or lapse
    facts, not the liveness stop - preflight's verdict is never recomputed: host records added since can change it);
    whether a linked stop is the one _ask_again opened where the retired stop's basis records no query. A rewrite of
    these is served as written: it can change what the stop says, where a recheck leads or withhold a replacement (a
    choice refused or asked again), never authorise one. Every answer at the stop is decided on the records then (answer()), by the option's intent; what answer()
    takes from the record itself is the budget extension's amount (dispatch_budget_proposal.added, with prior_limit,
    base_limit and used, which it compares with the run; checked here as (9) says), the replacement basis (not checked
    here) and, for a recheck, the lapsed_replacement it acknowledges (checked here as (9) says)."""
    from . import engine_core as ec
    if index.get('run_state') != 'RUNNING':
        return None
    found = unindexed_record(store, index)
    if found is None:
        return None
    qid, rec = found
    if not _pause_record(rec, qid):
        return None
    if not _matches_run(store, index, rec, _ANSWER_FIELDS):                                   # (1)-(3), (7)
        return None
    if rec['previous_status'] != index['nodes'][ec._node_key(rec['node'], rec['visit'])].get('status'):   # (6)
        return None
    if 'supersedes' in rec and not _superseded(store, index, rec):                            # (8)
        return None
    zh = str(index.get('user_language')).startswith('zh')
    if not _proposal_matches(store, index, rec, zh) or not _lapse_matches(store, index, rec, zh):   # (9)
        return None
    return rec if _renders(store, index, rec) else None                                       # (10)


def _matches_run(store, index, rec, answer_fields):
    """Conditions (1), (2), (3) and (7) of orphan_stop, shared with program_guard.orphan_stop: the stop `rec` its writer left
    unindexed was never answered or delivered (`answer_fields`: the fields only an answer adds to that writer's record), is
    the run's current occurrence, was opened on the run's current gate, at an instant in order."""
    from . import engine_core as ec
    if not _untouched(store, rec, answer_fields):                                             # (1)
        return False
    if (rec['node'], rec['visit']) != (index['current'].get('name'), index['current'].get('visit')) \
            or ec._node_key(rec['node'], rec['visit']) not in index['nodes']:                 # (2)
        return False
    if rec['previous_gate'] != index['gate']:                                                 # (3)
        return False
    return _in_order(index, rec)                                                              # (7)


def _in_order(index, rec):
    """Condition (7): the writer stamps presented_at with now_iso() after every time the gate before the stop records - its
    presentation, delivery and answer, and each history row's presentation and answer - and before anything later; never
    after now. A time that cannot be compared fails."""
    from . import engine_core as ec
    gate = index['gate']
    try:
        at = ec._parse_ts(rec['presented_at'])
        earlier = [ec._parse_ts(row[k]) for row in (gate, *gate['history'])
                   for k in ('presented_at', 'delivered_at', 'answered_at') if row.get(k)]
        return at <= ec._parse_ts(now_iso()) and all(t <= at for t in earlier)
    except (TypeError, ValueError, AttributeError, KeyError):
        return False


_LINKED = {'DISPATCH_REPLACEMENT_STALE': 'replace_executor', RECHECK_MOVED_ON: 'recheck_dispatch'}


def _superseded(store, index, rec):
    """Condition (8): pause(supersedes=...) runs only in _ask_again, right after answer() (or its recovery) answered the
    stop it retires and wrote the index - with a stale replacement choice, or a recorded replacement that could not be
    carried out (reason DISPATCH_REPLACEMENT_STALE, chosen replace_executor), or a recheck that moved on (RECHECK_MOVED_ON,
    chosen recheck_dispatch). Record 90 round 4 (B5): so the link's reason is one of these two; it names a history row,
    answered and chosen, whose record is an engine dispatch stop (dispatch_block set) of this stop's node and visit, answered
    and chosen with that intent; it is the last row, or followed only by program-integrity stops opened over it and
    answered before it was (the only gates that open while it waits), each answered. Round 6 (B3 (1)): and that answer
    retired the stop as _carry_out retires one - never one that was carried out: a replacement choice refused as stale
    (replacement_refused) or one whose recorded authorization replaced nothing (dispatch_lifecycle.unused_replacement:
    record 88's retire), a recheck that moved on (_recorded_move). Round 7 (B2): and this stop is the one _ask_again opened
    for that answer, not one a later next-node opened itself - the retire only where record 88's recovery retires (_retired:
    the ticket its authorization names is not the part's ticket), and no return query offered for the part since that
    answer (_asked_at_once)."""
    link, history = rec['supersedes'], index['gate']['history']
    intent = _LINKED.get(link['reason'])
    at = next((i for i, row in enumerate(history) if row.get('question_id') == link['question_id']), None)
    if intent is None or at is None:
        return False
    rows = history[at:]
    try:
        old, *later = [store.read_json(store.gate_path(row['question_id'])) for row in rows]
    except (OSError, ValueError, KeyError, TypeError, RecursionError, RunStoreError):
        return False
    return bool(all(row.get('answered_at') and row.get('resolution_kind') == 'chosen' for row in rows)
                and isinstance(old, dict) and old.get('question_id') == link['question_id']
                and old.get('source') == 'hsaw_doubt' and isinstance(old.get('dispatch_block'), str) and old['dispatch_block']
                and (old.get('node'), old.get('visit')) == (rec['node'], rec['visit'])
                and old.get('answered_at') and old.get('resolution_kind') == 'chosen' and old.get('chosen_intent') == intent
                and _retired(store, index, old, intent) and _asked_at_once(store, index, old)
                and all(isinstance(r, dict) and isinstance(r.get('program_drift'), dict) and r.get('answered_at')
                        for r in later))


def _retired(store, index, old, intent):
    """Round 6 (B3 (1)): the answer recorded at the engine stop `old`, chosen with `intent`, is one _carry_out asks again
    after: for replace_executor a refusal (replacement_refused, C3 / E6 / a late start) or a recorded authorization that
    replaced nothing (record 88's retire: dispatch_lifecycle.unused_replacement names why); for recheck_dispatch a recorded
    move (_recorded_move: K1, O2). A replacement that was carried out, or a recheck that passed, retired nothing. Round 7
    (B2, 'vb 2' defect 2, L1): a recorded authorization is retired only where _complete_recorded retires it - the ticket it
    names (previous_ticket) is not the part's ticket now; an accepted choice that lapsed later (the old agent's return
    recorded after it: unused_replacement's LAPSED) is followed by the lapsed-choice stop next-node opens itself, never by
    one _ask_again opened."""
    from . import engine_core as ec
    if intent == 'replace_executor':
        if old.get('replacement_refused'):
            return True
        authority = old.get('replacement_authorization')
        if not isinstance(authority, dict) or dispatch_lifecycle.unused_replacement(store, index, old) is None:
            return False
        try:
            entry = ec._catalog_entry(index, old['node'])
            current = ec._self_dispatch(index, entry, old['visit'])[1] if entry else None
        except (ec.EngineError, KeyError, TypeError, AttributeError):
            return False
        return not (current and current.get('ticket') == authority.get('previous_ticket'))
    return _recorded_move(old)


def _asked_at_once(store, index, old):
    """Round 7 (B2, 'vb 2' defect 2, L2): False when a return query was offered for the part after the answer recorded at
    the retired stop `old` - _ask_again's query step opens no stop, so a stop opened after that query is next-node's own,
    never the one _ask_again opened. Told where `old` is a liveness stop whose replacement_basis records the part's query
    when it opened (interrupted_basis: return_query) for the ticket the part still runs: the query is offered only while
    the run is RUNNING (dispatch_lifecycle.request_return, next-node), so from that stop's opening to its answer the query
    could not change, and _ask_again, run at that answer, opens its stop before anything else; a query now other than the
    recorded one was offered after the answer. Elsewhere (no such basis) it is not checked: such a link only changes the
    first serve's line, never an authorisation. Anything unreadable fails."""
    from . import engine_core as ec
    basis = old.get('replacement_basis')
    if old.get('dispatch_block') != LIVE or not isinstance(basis, dict) or 'return_query' not in basis:
        return True
    try:
        entry = ec._catalog_entry(index, old['node'])
        current = ec._self_dispatch(index, entry, old['visit'])[1] if entry else None
        if not current or current.get('ticket') != basis.get('ticket'):
            return True
        now = dispatch_lifecycle._evidence_ref(store, f"_dispatch_query.{current['ticket']}.json")
    except (ec.EngineError, OSError, ValueError, KeyError, TypeError, AttributeError, RunStoreError):
        return False
    return _same(now, basis['return_query'])


def _pause_record(rec, qid):
    """The shape of the record pause() writes for the stop `qid` (see orphan_stop). Record 90 round 4 (B3): with the types
    pause() writes - str explanation, advice and closing (and cause), a dict dispatch_error and replacement_basis, a
    supersedes link of two strings - and its option frame (_frame). Record 90 round 7 (B2, 'vb 2' defect 1): and the stop's
    own code (dispatch_block, with the question's last line) as the facts pause() writes for it (_code_facts)."""
    fields = set(rec)
    block, question, link = rec.get('dispatch_block'), rec.get('question'), rec.get('supersedes')
    return bool(_STOP_FIELDS <= fields and fields <= _STOP_FIELDS | _STOP_SOMETIMES | _ANSWER_FIELDS
                and rec['question_id'] == qid and _STOP_ID.fullmatch(qid)
                and rec['source'] == 'hsaw_doubt' and rec['kind'] == 'choice' and rec['prompt_text'] is None
                and rec['consumed_by_commit'] is True
                and isinstance(block, str) and block and isinstance(question, str) and question.endswith('\n' + block)
                and _frame(rec)
                and rec['recommendation'] in [o['intent'] for o in rec['options']]
                and all(isinstance(rec[k], str) for k in ('explanation', 'advice', 'closing'))
                and all(k not in rec or isinstance(rec[k], kind) for k, kind in (('cause', str), ('dispatch_error', dict),
                                                                                 ('replacement_basis', dict)))
                and isinstance(rec['node'], str) and type(rec['visit']) is int
                and isinstance(rec['presented_at'], str) and _STAMP.fullmatch(rec['presented_at'])
                and isinstance(rec['previous_gate'], dict)
                and isinstance(rec['previous_status'], str)
                and ('supersedes' not in rec or (isinstance(link, dict) and set(link) == {'question_id', 'reason'}
                                                 and all(isinstance(v, str) for v in link.values())))
                and _code_facts(rec))


# Record 90 round 7 (B2): what pause() writes only for its liveness stop, and the two replacement bases it offers -
# dispatch_lifecycle.interrupted_basis (the liveness stop) and replacement_basis (record 84's resume-unavailable stop).
_LIVE_EXPLANATION = 'Tool return evidence does not prove completion of external side effects.'
_BASIS_KEYS = {LIVE: frozenset(('ticket', 'attempt', 'scope_root', 'interruption_observation', 'start_evidence', 'return_query')),
               'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE': frozenset(('ticket', 'attempt', 'scope_root', 'exit_evidence'))}


def _code_facts(rec):
    """Record 90 round 7 (B2, 'vb 2' defect 1): the stop's code (dispatch_block) matches the facts pause() writes for that
    code, so a code rewritten with the question's last line is not installed where the record tells: a replacement_basis
    is exactly the one that code offers (the liveness stop's interrupted_basis, the resume-unavailable stop's
    replacement_basis: _BASIS_KEYS); the liveness stop without one - and only it - carries pause()'s fixed explanation
    (_LIVE_EXPLANATION); the lapsed-choice stop carries its lapsed_replacement; a budget stop's figures are those its
    code is given on (_proposal_matches). Not told: which code a stop with no fact of its own names (no basis, proposal or
    lapse facts, not the liveness stop) - preflight's verdict is never recomputed (host records added since can change
    it); such a rewrite changes what the stop says and where a recheck leads, never authorises anything."""
    block, basis = rec['dispatch_block'], rec.get('replacement_basis')
    if basis is not None and set(basis) != _BASIS_KEYS.get(block):
        return False
    if (rec['explanation'] == _LIVE_EXPLANATION) != (block == LIVE and basis is None):
        return False
    return block != 'DISPATCH_REPLACEMENT_LAPSED' or 'lapsed_replacement' in rec


def _frame(rec):
    """Record 90 round 4 (B3, B4): pause()'s options - each a dict of exactly str kind, label and intent and a note that is
    str or None; Recheck conditions first, Cancel this run last, and between them only the one option pause() inserts: the
    budget extension on a budget stop, the one new agent where the record carries its replacement_basis (record 84's
    resume-unavailable stop and the interruption's liveness stop), none otherwise."""
    options, block = rec.get('options'), rec.get('dispatch_block')
    if not (isinstance(options, list) and 2 <= len(options) <= 3 and all(
            isinstance(o, dict) and set(o) == {'kind', 'label', 'intent', 'note'}
            and all(isinstance(o[k], str) for k in ('kind', 'label', 'intent')) and (o['note'] is None or isinstance(o['note'], str))
            for o in options)):
        return False
    between = ('extend_independent_budget' if block in _BUDGET_STOPS else
               'replace_executor' if 'replacement_basis' in rec else None)
    return bool((options[0]['kind'], options[0]['intent']) == ('execute', 'recheck_dispatch')
                and (options[-1]['kind'], options[-1]['intent']) == ('cancel', 'cancel')
                and [(o['kind'], o['intent']) for o in options[1:-1]] == ([('execute', between)] if between else [])
                and ('replacement_basis' not in rec or block in ('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', LIVE)))


def _same(a, b):
    """Record 90 round 5 (B1): equal by type as well as value - the values' canonical JSON, which tells true, 1 and 1.0
    apart (Python's == does not). The recognisers compare what pause() wrote or copied with it, so that a bool or a float
    never passes for an int the writer writes. False for anything that is not JSON."""
    try:
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    except (TypeError, ValueError, RecursionError):
        return False


def _proposal_matches(store, index, rec, zh):
    """Condition (9), record 90 round 4 (B4): a budget stop's dispatch_budget_proposal is the one pause() computes from the
    run and the program now (_proposal, on a copy of the run with the independent limit preflight sets: the program's
    default plus every extension granted) and its extension option is pause()'s for it (_extend_option) - both by type as
    well as value (_same, round 5 B1: the amount added, the limits and the claims used are ints); any other stop carries
    none (_frame: then it offers no extension either). answer() grants the proposal's own amount. While the program's files
    differ from the run's binding (PROGRAM_DRIFT_DETECTED, the program cannot be loaded) the default and the roots not yet
    run are taken from the record's own figures; the rest is checked alike - so there a record whose figures agree with
    each other and with the run's claims and extensions is installed as written. Record 90 round 7 (B2, 'vb 2' defect 1):
    and the stop's code is the one those figures give - preflight names INDEPENDENT_PREFLIGHT_BUDGET_INSUFFICIENT only
    before any independent claim (used 0) with more declared roots left than the limit, INDEPENDENT_BUDGET_EXHAUSTED (it
    and engine_core._exhaust_code) only once the claims used reach the limit."""
    from . import engine_core as ec
    proposal = rec.get('dispatch_budget_proposal')
    if rec['dispatch_block'] not in _BUDGET_STOPS:
        return 'dispatch_budget_proposal' not in rec
    if not isinstance(proposal, dict):
        return False
    try:
        program = ec._load_routed_program(ec._read_run_input(store))
    except ec.EngineError as exc:
        if exc.code != 'PROGRAM_DRIFT_DETECTED':
            return False
        program = None
    additions = sum(r['added'] for r in index['dispatch'].get('independent_extensions', []))
    if program is None:
        base, pending = proposal.get('base_limit'), proposal.get('remaining_declared_roots')
        if base not in (16, 20) or type(base) is not int or not isinstance(pending, list) or not all(
                isinstance(r, dict) and set(r) == {'file', 'node'} and all(isinstance(v, str) for v in r.values())
                for r in pending):
            return False
        want = _proposed(base, base + additions, usage(index, 'independent'), pending)
    else:
        work = copy.deepcopy(index)
        work['dispatch']['independent_hard_limit'] = requirements(program)[1] + additions      # as preflight sets it
        want = _proposal(work, program)
    if not (_same(proposal, want) and _same(rec['options'][1], _extend_option(want, zh))):
        return False
    used, cap = want['used'], want['prior_limit']
    return (used == 0 and len(want['remaining_declared_roots']) > cap) if rec['dispatch_block'] == \
        'INDEPENDENT_PREFLIGHT_BUDGET_INSUFFICIENT' else used >= cap


def _lapse_matches(store, index, rec, zh):
    """Condition (9), record 90 round 4 (B4): a lapsed_replacement the record carries (dispatch_lifecycle.lapse_facts when
    pause() ran) names the human's choice the part's ticket still carries (human_replacement) and that ticket; its exit
    evidence is none or the ticket's own (a return is recorded once and never changed); what the host recorded after the
    choice is a non-empty list of the words lapse_facts uses; and the stop says so in pause()'s words (_lapse_lead opens
    the question, or the lapsed-choice stop's _lapse_explanation). Round 5 (B3): pause() writes one only while that choice
    has lapsed (dispatch_lifecycle.lapsed_replacement) - a lapse never un-lapses, and nothing acknowledges it before the
    stop is installed - so the lapse holds now and names the same question and ticket. What the host recorded after the
    choice may have grown since the crash, so its list is not recomputed. A record without one is not checked: whether
    pause() found one depends on host records that may have changed since."""
    from . import engine_core as ec
    if 'lapsed_replacement' not in rec:
        return True
    facts = rec['lapsed_replacement']
    entry = ec._catalog_entry(index, rec['node'])
    current = ec._self_dispatch(index, entry, rec['visit'])[1] if entry else None
    chosen = (current or {}).get('human_replacement')
    lapsed = dispatch_lifecycle.lapsed_replacement(store, index, current) if current else None
    if not (isinstance(facts, dict) and set(facts) == {'question_id', 'previous_ticket', 'exit_evidence', 'recorded_after'}
            and isinstance(chosen, dict) and facts['question_id'] == chosen.get('question_id')
            and facts['previous_ticket'] == current.get('ticket')
            and isinstance(lapsed, dict) and lapsed.get('question_id') == facts['question_id']
            and lapsed.get('previous_ticket') == facts['previous_ticket']
            and (facts['exit_evidence'] is None or _same(facts['exit_evidence'], current.get('exit_evidence')))
            and isinstance(facts['recorded_after'], list) and facts['recorded_after']
            and all(k in dispatch_lifecycle._LAPSE_WORDS for k in facts['recorded_after'])):
        return False
    if rec['dispatch_block'] == 'DISPATCH_REPLACEMENT_LAPSED':
        return rec['explanation'] == _lapse_explanation(chosen, facts, zh)
    return rec['question'].startswith(_lapse_lead(facts, zh))


def _renders(store, index, rec):
    """Condition (10), record 90 round 4 (B3): the stop as next-node would serve it once installed - its first serve
    (_served) and a plain one (reply, as every later serve and a sub-agent's node-commit) - rendered on copies of the run
    with the stop installed (_install), through a view that refuses every write (_StopView), the menu unwritten: False on
    any exception. A record that cannot be served is not one the engine installs."""
    try:
        work = _install(copy.deepcopy(index), copy.deepcopy(rec), rec['presented_at'])
        view = _StopView(store, work, rec)
        _served(view, work, copy.deepcopy(rec), publish=False)
        reply(view, work, copy.deepcopy(rec), publish=False)
    except Exception:      # noqa: BLE001 - B3: any failure to render fails closed
        return False
    return True


def _untouched(store, rec, answer_fields=_ANSWER_FIELDS):
    """Condition (1) of orphan_stop: the stop `rec` was never answered and never delivered - nor served: its menu is written
    by every serve (served, reply)."""
    from . import engine_core as ec
    qid = rec['question_id']
    return (all(rec[k] is None for k in _UNANSWERED) and not (answer_fields & set(rec))
            and not any(store.public_dir.glob(f'menu.{qid}.*'))
            and not any(not isinstance(e, dict) or e.get('corrupt') or e.get('question_id') == qid
                        for e in ec._read_ledger(store)))


def _unindexed_cache(store, index):
    """Part of condition (5) of orphan_stop: the current node's cache exists but is not the one the index accepted (an
    interrupted commit's write); also True where that cannot be told."""
    from . import engine_core as ec
    from .run_store import sha256_bytes
    name, visit = index['current'].get('name'), index['current'].get('visit')
    try:
        entry = ec._catalog_entry(index, name) if name else None
        if not entry:
            return True
        path = ec._cache_path_for(store, index, entry, visit)
        if not store.exists_path(path):
            return False
        accepted = (index['nodes'].get(ec._node_key(name, visit)) or {}).get('cache_sha256')
        return not accepted or accepted != sha256_bytes(store.read_bytes(path))
    except (OSError, ValueError, KeyError, TypeError, RunStoreError, ec.EngineError):
        return True


def _ask_again(store, index, rec, outcome=None, *, moved=False, lead=None):
    """Review of docs/05SoulRun 87 (C3): a stale replacement choice retired the liveness stop `rec` (answered, nothing
    authorized) while preflight still blocked. The current facts decide what comes next, and nothing runs without a new
    answer: a new stop on what blocks now - the interruption on its recomputed basis, or record 84's resume-unavailable
    condition after a failed return (round 3, D1), each with the replacement only if one is offered - or, when the
    interruption's basis needs the bounded return query first, the main agent's next-node offers the query and the stop
    follows it. Round 4 (E6): record 84's condition also where preflight does not see it (the ordinary pool, a sub node of
    an independent root) - `outcome`, what that stop's recheck led to (recheck_outcome), names it. Round 2 (N1): answer()
    never retires a stop once nothing blocks; should these records not show a block, the stop's own condition is asked
    again - never ANSWERED with the run going on. docs/05SoulRun 88 (K1): `moved` - the human's Recheck conditions retired
    the stop because another condition holds the part (_recheck_moves_on); the same steps ask at that condition's stop,
    linked by supersedes with the reason RECHECK_MOVED_ON. Review round 3 (O2): a SUBTREE stop's move says the Agent tool
    is declared; (R1, R3) `lead` - a recovered answer's reply opens with it (_completed_lead).
    Review round 4 (W1): a recovered move asked on the current records may land on the retired stop's own condition - the
    hint then says that this stop's own condition holds the part again, or that the condition the recorded recheck named no
    longer holds it, never 'another condition'; 'the host declares the Agent capability' is said only where it does now
    (_capability_declared). (W4) After a recovered refusal or a retire the lead says what was decided; no second line.
    Record 90 round 5 (ledger decision 185): _ask_again runs only inside answer(), which only gate-answer reaches
    (engine_core.answer_gate - the host's gate-answer tool and the host's prepare); its reply goes to that host call, not
    to the main executor, so the stop it opens is not served to anyone yet: pause(publish=False) writes no menu, a message
    before the main executor's next-node takes nothing as its answer (engine_core._unshown_stop), and that next-node's
    first serve is pause()'s reply with the line rebuilt from the records (served, _asked_hint; record 90, ledger decision
    190: the line pause()'s reply to a first attempt carries - what was done, no reply called valid - except where the
    records show the answer was completed by record 88's recovery - a retire, a move back to the retired stop's own
    condition - whose line says what became of the recorded answer and that the reply received after it was not used;
    pause()'s reply after a recovery opens with the recovery's `lead`)."""
    from . import engine_core as ec
    zh = str(index.get('user_language')).startswith('zh')
    step, reason, named = _ask_again_where(store, index, rec, outcome, ec._load_routed_program(ec._read_run_input(store)))
    hint = _again_hint(rec, reason, zh, moved=moved, lead=lead, named=named,
                       back=rec.get('dispatch_block') == SUBTREE_CAP and _capability_declared(index))
    # A capability recheck is not consent to hand over the unfinished work.
    if moved and rec.get('dispatch_block') == SUBTREE_CAP and step == 'stop' \
            and reason in {'DISPATCH_LIVENESS_UNKNOWN', 'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE'}:
        from . import dispatch_identity
        entry = ec._catalog_entry(index, rec['node'])
        _, current = ec._self_dispatch(index, entry, rec['visit'])
        if current and current.get('scope_root') and not dispatch_identity.authority(store, index, current):
            return dict(dispatch_identity.open_gate(store, index, publish=False),
                        answer_hint=_joined(zh, lead[0] if lead else '', hint, _again_line(zh)))
    if step == 'query':
        return dict(status='ANSWERED', question_id=rec['question_id'], run_state=index['run_state'],
                    **({} if moved else dict(replacement_authorized=False, answer_disposition='REPLACEMENT_REFUSED_STALE')),
                    answer_hint=_joined(zh, lead[0] if lead else '', hint,
                                        '主代理下一次取节点时先做一次有界的返回查询，之后再按新的记录问你。' if zh else
                                        "The main agent's next-node first offers the one bounded return query; then you are asked again."),
                    independent_budget=summary(index), next=dict(node=rec['node']))
    return pause(store, index, reason, supersedes=rec['question_id'], why=RECHECK_MOVED_ON if moved else 'DISPATCH_REPLACEMENT_STALE',
                 hint=_joined(zh, hint, _again_line(zh)), lead=lead, publish=False)


def _again_line(zh):
    return '下面按现在的记录重新问你。' if zh else 'Here is the question again on the current records.'


def _joined(zh, *parts):
    return ('' if zh else ' ').join(p for p in parts if p)


def _again_hint(rec, reason, zh, *, moved, lead, named, back):
    """_ask_again's line on the stop `rec` it retired, before the stop `reason` it asks at: what became of the answer given
    at `rec` - a recheck that moved on (`moved`; `named`: preflight named `reason`; `back`: the move is a SUBTREE stop's,
    the host declaring the Agent tool), a stale replacement choice, or, after a recovered answer (`lead`), nothing more.
    Record 90 round 3 (B1): shared with _asked_hint, which rebuilds pause()'s reply for the stop's first serve. Record 90
    (ledger decision 190): it states what was done and calls no reply valid, after a first attempt and after record 88's
    recovered answer alike (the records cannot tell them apart)."""
    if moved:
        own = rec.get('dispatch_block')
        if not reason:
            held_by = ''
        elif reason != own:
            held_by = ((('宿主现在声明了子代理（Agent）能力，但' if back else '') + f'这一段现在被另一个条件拦着（{reason}），') if zh else
                       ('the host now declares the sub-agent (Agent) capability, but ' if back else '') +
                       f'another condition now holds this part ({reason}), so ')
        elif named and own == SUBTREE_CAP:     # only on recovery: the host declared the tool at the answer, not now
            held_by = (f'你答复时宿主声明了子代理（Agent）能力，但现在宿主没有声明它，这一段又被这道题自己的条件拦着（{reason}），' if zh else
                       'the host declared the sub-agent (Agent) capability when you answered, but it does not declare it now, so '
                       f"this stop's own condition holds this part again ({reason}); ")
        elif named:
            held_by = (f'这一段现在又被这道题自己的条件拦着（{reason}），' if zh else
                       f"this stop's own condition holds this part again ({reason}); ")
        else:                                  # only on recovery: these records show no block; the stop's own condition is asked again
            was = ((rec.get('recheck_attempts') or [{}])[-1]).get('reason')
            held_by = (f'你答复时拦着这一段的条件（{was}）现在已经不拦着了，' if zh else
                       f'the condition that held this part when you answered ({was}) no longer holds it; ')
        return (f'复核已执行：{held_by}这道题已关闭，没有换人，也没有派出任何代理。' if zh else
                f'Recheck executed: {held_by}this stop is closed; nothing was replaced and no agent was started.')
    if lead:
        return ''           # review round 4 (W4): the lead says what the recorded refusal or the retire decided
    return ('这个换人选项依据的记录已经变了，没有换人。' if zh else
            'The records this replacement was offered on have changed, so nothing was replaced.')


def _recovered_line(old, rec, zh):
    """Record 90 round 7 (B1; ledger decisions 186 and 187): the first serve's line - (menu text, host text) - for the stop
    `rec` asked again where the records show that the answer at the retired stop `old` was completed by record 88's
    recovery (_complete_recorded), which only a newer reply triggers and which set that reply aside: a recorded replacement
    that could not be carried out (retire: `old` carries its authorization and no refusal) or a recorded move asked back
    at the retired stop's own condition (a first attempt moves on only to another condition, _recheck_moves_on). It says
    what became of the recorded answer, that the reply received after it was not used, and asks again; it calls no reply
    valid. Wording only."""
    qid, own = old.get('question_id'), rec['dispatch_block']
    if old.get('chosen_intent') == 'replace_executor':
        label = old.get('chosen_label') or old.get('chosen_intent')
        menu = (f'你先前在上一道题选的「{label}」没能执行：它授权替换的那张票已经不是这一段现在的票，所以没有换人。'
                '之后收到的那条回复没有采用。' if zh else
                f"Your earlier answer at the stop before ({label}) could not be carried out: the ticket it authorized replacing is "
                'no longer this part\'s ticket, so nothing was replaced. The reply received after it was not used.')
        host = (f"The human's answer recorded at the stop before ({qid}, replace_executor) could not be carried out: the ticket "
                "it authorized replacing is no longer this part's ticket, so nothing was replaced; the reply received after it "
                'was not used, and this stop asks again. ')
    else:
        menu = (f'之前记下的答复已处理，复核已执行：按现在的记录，这一段又回到这道题自己的条件（{own}），上一道题已关闭，'
                '没有换人，也没有派出任何代理。之后收到的那条回复没有采用。' if zh else
                f"Your earlier recorded answer was handled; recheck executed: on the current records this part is back at this "
                f"stop's own condition ({own}); the stop before is closed, nothing was replaced and no agent was started. The "
                'reply received after it was not used.')
        host = (f"The human's answer recorded at the stop before ({qid}, recheck_dispatch) was handled: the recheck ran and on "
                f"the current records this part is back at this stop's own condition ({own}); nothing was replaced and no agent "
                'was started. The reply received after it was not used; this stop asks again.')
    return _joined(zh, menu, _again_line(zh)), host


def served(store, index, rec):
    """The open engine stop `rec` as the main executor's next-node and node-commit serve it. Record 90 round 3 (B1): the
    first serve of a stop asked again (supersedes) that was never served, delivered or answered (_untouched: no menu written
    for it yet) carries the line on what became of the answer at the stop it retired (_asked_hint), then the stop asked.
    pause()'s reply when _ask_again opened it did not reach the main executor: round 5 (ledger decision 185) - _ask_again
    runs inside gate-answer and opens the stop unpublished, its reply going to that host call - or it was lost when the
    process died before problem 85's re-install, or after an index write (the re-install's, or pause()'s own) and before
    the reply: the same state on disk. Record 90 round 7 (ledger decisions 186 and 187, B1): no record marks an answer
    completed by record 88's recovery (_complete_recorded writes the records the first attempt writes), so after an answer
    whose records a first attempt also leaves - a refused replacement choice, a recheck that moved on to another condition
    - that line is the first attempt's, which (record 90, ledger decision 190) states what was done and calls no reply
    valid, true either way; where the records show the answer was completed by that recovery -
    a recorded replacement that could not be carried out (a retire), a move back to the retired stop's own condition - the
    line says what became of the recorded answer and that the reply received after it was not used, and calls no reply
    valid (_recovered_line). answer_valid and answer_disposition are round 6's. Every later serve is plain, as for the run
    that never stopped. Round 4 (B1): a node-commit with an agent ticket (the old agent's) is served plain and writes no
    menu (engine_core.commit: reply(..., publish=False)), so this first serve stays for the main executor, whose reply
    reaches the model that talks to the human."""
    return _served(store, index, rec)


def _served(store, index, rec, *, publish=True):
    asked = _asked_hint(store, index, rec)
    if asked is None:
        return reply(store, index, rec, publish=publish)
    hint, first, plain = asked
    if plain:          # round 7 (B1): a move back to the stop's own condition - answer_valid as the plain serve's (False);
        # asked: this stop's own facts acknowledge no reply given here (none was)
        return reply(store, index, rec, answer_valid=False, asked=True, lead=(hint, first), publish=publish)
    return reply(store, index, rec, hint, answer_valid=True, asked=True, publish=publish, first=first)


def _asked_hint(store, index, rec):
    """Record 90 round 3 (B1): the line of the first serve of the stop `rec` that _ask_again opened - rebuilt from its
    supersedes link and the retired stop's record - while `rec` was never served; else None. Returns (menu text, host
    sentence or None, plain). On the first attempt a recheck moves on only to another condition, and a SUBTREE stop's move
    only while the host declares the Agent tool; a replacement choice that asks again was refused (replacement_refused).
    No record marks that the retired stop's answer was completed by record 88's recovery (_complete_recorded writes the
    records the first attempt writes), so a stop asked again after those answers cannot be told from a first attempt
    (record 90 round 4, B2): its line is the first attempt's, which states what was done and calls no reply valid (record
    90, ledger decision 190), host sentence None (reply() opens with _again_host). Only a recovery asks again after a
    recorded replacement it could not carry out (a
    retire: the answer carries its authorization and no refusal) or at the retired stop's own condition after a recorded
    move: _recovered_line - what became of the recorded answer, that the reply received after it was not used; it calls no
    reply valid (ledger decision 186) - with its host sentence (`first`); the own-condition move is served with plain's fields (answer_valid False, as before round 7,
    `plain` True). Since round 5 the stop asked again is opened unpublished (_ask_again), so this is the main executor's
    first serve after every answer that asks again, recovered or not, with or without a crash."""
    link = rec.get('supersedes')
    if not isinstance(link, dict) or not _untouched(store, rec):
        return None
    try:
        old = store.read_json(store.gate_path(link['question_id']))
    except (OSError, ValueError, KeyError, TypeError, RunStoreError):
        return None
    moved, own = link.get('reason') == RECHECK_MOVED_ON, old.get('dispatch_block')
    zh = str(index.get('user_language')).startswith('zh')
    if moved and rec['dispatch_block'] == own:
        return (*_recovered_line(old, rec, zh), True)
    if not moved and isinstance(old.get('replacement_authorization'), dict) and not old.get('replacement_refused'):
        return (*_recovered_line(old, rec, zh), False)
    return (_joined(zh, _again_hint(old, rec['dispatch_block'], zh, moved=moved, lead=None, named=True, back=own == SUBTREE_CAP),
                    _again_line(zh)), None, False)


def _ask_again_where(store, index, rec, outcome, program):
    """Round 5: what _ask_again asks once a stale choice retired the liveness stop `rec`, from the run as answer() left it
    - ('query', None, True): the main agent's next-node offers the bounded return query first; else ('stop', code, named):
    pause() opens the stop `code`. Review round 4 of docs/05SoulRun 88 (W1): `named` - preflight (or the recheck outcome)
    names `code`; False where these records show no block and the stop's own condition is asked again."""
    from . import engine_core as ec
    entry = ec._catalog_entry(index, rec['node'])
    _, current = ec._self_dispatch(index, entry, rec['visit'])
    reason = preflight(index, program, entry, store=store)
    if not reason and outcome and outcome.get('next') == 'stop' and outcome.get('replacement'):
        reason = outcome['code']
    if reason == 'DISPATCH_LIVENESS_UNKNOWN' and dispatch_lifecycle.return_query_due(store, index, current):
        return 'query', None, True
    return 'stop', reason or rec['dispatch_block'], bool(reason)


def _ask_again_step(store, index, rec, outcome, program):
    """Round 5: _ask_again_where's step and code - ('query', None) or ('stop', code). _ask_again carries it out;
    replace_outcome and _recheck_moves_on read it to say where the human is asked again."""
    step, code, _ = _ask_again_where(store, index, rec, outcome, program)
    return step, code


def answer(store, index, rec, question_id, text, by):
    from . import engine_core as ec
    if question_id != rec['question_id']:
        return dict(status='REJECTED', errors=[dict(code='GATE_MISMATCH', message='Answer the active dispatch gate.')])
    if rec.get('answered_at'):
        # Recover a partially persisted answer without changing the human's original authority. Review round 3 of
        # docs/05SoulRun 88 (R1): completed exactly as the first attempt decided it, never decided again on the records now.
        return _complete_recorded(store, index, rec, text)
    option = ec._match_option(rec['options'], text.strip())
    cancel = (option and option['kind'] == 'cancel') or text.strip().lower() in (ec.CANCEL_WORDS | ec.TERMINATE_WORDS)
    if not option and not cancel:
        rec.setdefault('invalid_answers', []).append(dict(at=now_iso(), text_original=text, by=by))
        rec['last_reply_valid'] = False
        ec._write_json(store.gate_path(question_id), rec)
        return reply(store, index, rec)
    extended = replaced = current = moved = stamp = outcome = None
    refused = False
    if not cancel:
        program = ec._load_routed_program(ec._read_run_input(store))
        reason = preflight(index, program, ec._catalog_entry(index, rec['node']), store=store)
        blocking = reason          # round 2 of the review of docs/05SoulRun 87 (N1): the stop's condition, before a choice names it
        if option['intent'] == 'recheck_dispatch' and reason:
            # docs/05SoulRun 88 (K1): a liveness stop held by another condition is retired with this answer; the human is
            # asked at that condition's stop (below, after the answer is written) - nothing runs without that answer.
            # Review round 3 (O2): likewise a SUBTREE stop once the Agent tool is declared again.
            moved = _recheck_moves_on(store, index, rec, program, reason)
        if option['intent'] == 'replace_executor':
            # Round 5: decided by _replace_choice - the decision replace_outcome reads to say what this choice leads to.
            choice = _replace_choice(store, index, rec, program, blocking)
            reason, current, outcome, refused = choice['reason'], choice['current'], choice['outcome'], choice['refused']
            if not reason:
                replaced = dict(question_id=question_id, previous_ticket=choice['basis']['ticket'], basis=choice['basis'],
                                answered_by=by, answered_at=now_iso(), answer_text_original=text)
        if option['intent'] == 'extend_independent_budget':
            proposal = rec.get('dispatch_budget_proposal')
            if (not proposal or reason not in {'INDEPENDENT_BUDGET_EXHAUSTED', 'INDEPENDENT_PREFLIGHT_BUDGET_INSUFFICIENT'}
                    or proposal['prior_limit'] != limit(index, 'independent')
                    or proposal['base_limit'] != requirements(program)[1]
                    or proposal['used'] != usage(index, 'independent')):
                reason = reason or 'DISPATCH_BUDGET_PROPOSAL_STALE'
            else:
                extended = dict(question_id=question_id, added=proposal['added'], prior_limit=proposal['prior_limit'],
                                used_before=proposal['used'], answered_by=by, answered_at=now_iso(),
                                answer_text_original=text)
                projection = copy.deepcopy(index)
                projection['dispatch'].setdefault('independent_extensions', []).append(extended)
                reason = preflight(projection, program, ec._catalog_entry(index, rec['node']), store=store)
                if not reason:
                    problems = store.validate_index(projection)
                    if problems:
                        raise ec.EngineError('INDEX_SCHEMA_INVALID', str(problems[0]))
                    index['dispatch'] = projection['dispatch']
        # Review of docs/05SoulRun 87 (C3): on a liveness stop a recheck cannot pass while the interruption stands, so a
        # stale replacement choice retires this stop - answered, authorizing nothing - and the current facts are asked anew.
        # Round 2 (N1): only while preflight still blocks. Once nothing blocks a recheck can pass, so the stop stays and
        # the human decides; retiring it would let the run go on with no new answer. Round 3 (D1): whatever blocks - a
        # failed return recorded meanwhile gives record 84's condition, which this stop's recheck can never clear.
        # Round 4 (E6): also where a recheck would lead to record 84's stop with its one replacement (recheck_outcome) -
        # in every pool and position the human is asked there directly, never three times. Round 5: `refused` and
        # `outcome` come from _replace_choice above.
        stale_liveness = reason == 'DISPATCH_REPLACEMENT_STALE' and rec['dispatch_block'] == 'DISPATCH_LIVENESS_UNKNOWN'
        stamp = now_iso()
        if reason:
            rec.setdefault('recheck_attempts', []).append(dict(at=stamp, answer_text_original=text, reason=reason))
            rec['last_reply_valid'] = True
        if reason and not refused and not moved:
            ec._write_json(store.gate_path(question_id), rec)
            zh = str(index.get('user_language')).startswith('zh')
            if stale_liveness and blocking is None and dispatch_lifecycle.returned(current):
                # round 2 (N1): the human decides what follows; reply() says what, as every later serve does (rounds 3-4)
                return reply(store, index, rec, answer_valid=True)
            if reason == 'DISPATCH_REPLACEMENT_STALE':   # docs/05SoulRun 87: say why the chosen replacement did not run
                return reply(store, index, rec, answer_valid=True, hint=_held_line(rec, zh))
            # record 90 (ledger decision 190): the stop is asked again - what was done, never 'valid reply'
            return reply(store, index, rec, hint=_held_line(rec, zh), answer_valid=True)
    # M1: a recheck that moves on is answered at the instant of its recorded attempt (_recorded_move reads the pair).
    now = (extended or replaced or {}).get('answered_at') or (stamp if moved else now_iso())
    wait = ec._ms_between(rec.get('delivered_at'), now) if rec.get('delivered_at') else None
    rec.update(answered_at=now, answer_text=text.strip(), answer_text_original=text, answered_by=by,
        resolution_kind='cancel' if cancel else 'chosen', chosen_intent='cancel' if cancel else option['intent'],
        chosen_label=option['label'] if option else text, human_wait_ms=wait)
    if extended:
        rec['budget_authorization'] = extended
    if replaced:
        rec['replacement_authorization'] = replaced
        current['human_replacement'] = copy.deepcopy(replaced)
    if refused:
        rec['replacement_refused'] = dict(reason='DISPATCH_REPLACEMENT_STALE', at=now)
    ec._write_json(store.gate_path(question_id), rec)
    return _carry_out(store, index, rec, extended=extended, replaced=replaced, refused=refused, moved=bool(moved), outcome=outcome)


def _complete_recorded(store, index, rec, text):
    """Review round 3 of docs/05SoulRun 88 (R1; skeptic 1 of round 2): the active engine stop `rec` already carries the
    human's answer - the run stopped after answer() wrote its gate record and before the index (with or without the
    ledger appends between) - and the human has replied again. The recorded answer is completed exactly as the first
    attempt decided it, from the record alone, never decided again on the records now: a carried replacement with its
    recorded authorization (the main agent's next-node then applies the lapse rules to whatever the host recorded since,
    as it does uncrashed - D2/E5), a passing recheck, the budget extension, a refusal (C3/E6/late start) and a K1 or O2
    move (both: the stop retired and the human asked at the stop of what holds the part now, _ask_again), a cancel. No
    attempt is added (R2) and the gate record is not rewritten; the ledger appends are idempotent. A choice that cannot be
    completed - its authorization names a ticket the part no longer runs - is never carried out: the stop is retired as a
    stale choice retires it (C3) and the human is asked anew. Never left open holding later answers; the new reply only
    triggers this, and the reply after it says so (R3, _completed_lead)."""
    from . import engine_core as ec
    zh = str(index.get('user_language')).startswith('zh')
    cancel = rec.get('resolution_kind') == 'cancel'
    refused = not cancel and bool(rec.get('replacement_refused'))
    replaced = None if cancel or refused else rec.get('replacement_authorization')
    extended = None if cancel else rec.get('budget_authorization')
    moved = not cancel and rec.get('chosen_intent') == 'recheck_dispatch' and _recorded_move(rec)
    retire, outcome = False, None
    if not cancel:
        program = ec._load_routed_program(ec._read_run_input(store))
        entry = ec._catalog_entry(index, rec['node'])
        # As the first attempt: preflight refreshes the run's independent limit; its verdict is not asked again, except
        # for where a retired stop asks next (record 84's condition where preflight does not see it, _ask_again_step).
        blocking = preflight(index, program, entry, store=store)
        if replaced:
            current = ec._self_dispatch(index, entry, rec['visit'])[1]
            if current and current.get('ticket') == replaced.get('previous_ticket'):
                current['human_replacement'] = copy.deepcopy(replaced)
            else:
                retire = True
        if extended:
            rows = index['dispatch'].setdefault('independent_extensions', [])
            if not any(r.get('question_id') == extended.get('question_id') for r in rows):
                rows.append(copy.deepcopy(extended))
            index['dispatch']['independent_hard_limit'] = requirements(program)[1] + sum(r['added'] for r in rows)
        if (refused or retire) and blocking is None and rec.get('dispatch_block') == LIVE:
            outcome = recheck_outcome(store, index, rec, program=program)
    return _carry_out(store, index, rec, extended=extended, replaced=replaced, refused=refused, moved=moved, outcome=outcome,
                      retire=retire, lead=_completed_lead(rec, text, zh, retired=retire))


def _carry_out(store, index, rec, *, extended=None, replaced=None, refused=False, moved=False, outcome=None, retire=False,
               lead=None):
    """answer()'s writes after the stop's answered gate record, shared by the first attempt and its recovery (review round
    3 of docs/05SoulRun 88, R1): the node's waiting time, the history row, the stop's ticket, the ledger (gate_answer, the
    budget extension, the replacement authorization - each appended once), the run going on (or ended by a cancel) and its
    index; then a refusal, a retire (R1) or a move (K1, O2) asks again, and anything else answers. `lead` - a recovery's
    reply opens with it (R3)."""
    from . import engine_core as ec
    question_id, now, by = rec['question_id'], rec['answered_at'], rec.get('answered_by')
    cancel = rec.get('resolution_kind') == 'cancel'
    ne = index['nodes'][ec._node_key(rec['node'], rec['visit'])]
    ne['human_wait_ms'] = (ne.get('human_wait_ms') or 0) + (rec.get('human_wait_ms') or 0)
    for row in index['gate']['history']:
        if row['question_id'] == question_id:
            row.update(answered_at=now, resolution_kind=rec['resolution_kind'])
    for ticket in index['tickets']:
        if ticket['question_id'] == question_id or (cancel and ticket['state'] == 'READY'):
            ticket['state'] = 'RETIRED' if cancel else 'CONSUMED'
    ec._ledger_append(store, index, dict(kind='gate_answer', at=now, trace_id=index['trace_id'], engine_version=ec.ENGINE_VERSION,
        question_id=question_id, node=rec['node'], visit=rec['visit'], resolution_kind=rec['resolution_kind'],
        chosen_intent=rec['chosen_intent'], answered_by=by, scope='independent_execution_not_business_authorization',
        **(dict(replacement_refused='DISPATCH_REPLACEMENT_STALE') if refused else {})))
    if extended:
        ec._ledger_append(store, index, dict(kind='independent_budget_extension', at=extended['answered_at'],
            question_id=question_id, trace_id=index['trace_id'], engine_version=ec.ENGINE_VERSION,
            node=rec['node'], visit=rec['visit'], authorization=extended,
            effective_limit=limit(index, 'independent')))
    if replaced:
        ec._ledger_append(store, index, dict(kind='executor_replacement_authorized', at=replaced['answered_at'],
            question_id=question_id, trace_id=index['trace_id'], engine_version=ec.ENGINE_VERSION,
            node=rec['node'], visit=rec['visit'], previous_ticket=replaced['previous_ticket'],
            return_evidence=replaced['basis'].get('exit_evidence'),
            # docs/05SoulRun 87: an interrupted ticket is replaced on the human's risk choice; its exit stays unverified.
            **({k: replaced['basis'][k] for k in ('interruption_observation', 'start_evidence', 'return_query')}
               if 'interruption_observation' in replaced['basis'] else {})))
    if cancel:
        ec.close_dispatch_tickets(store, index, f'human_cancel:{question_id}')
        index['gate']['state'] = 'CLEAR'
        ne['status'] = 'FAILED'
        ec._terminate(index, kind='human_termination', by='human', reason=f'Dispatch conditions cancelled at {question_id}')
    else:
        history = index['gate']['history']
        index['gate'] = dict(rec['previous_gate'], history=history)
        index['run_state'], ne['status'] = 'RUNNING', rec['previous_status']
    ec._write_index(store, index)
    if refused or retire:
        return _ask_again(store, index, rec, outcome, lead=lead)
    if moved:
        return _ask_again(store, index, rec, moved=True, lead=lead)
    return dict(status='TERMINATED' if cancel else 'ANSWERED', question_id=question_id, run_state=index['run_state'],
                independent_budget=summary(index),
                next=None if cancel else dict(node=rec['node']),
                **(dict(answer_hint=lead[0]) if lead else {}),
                **(dict(error_report=ec._error_report(store, index), terminal_delivery_refs=[ec._ref(store, 'ended.txt')]) if cancel else {}))
