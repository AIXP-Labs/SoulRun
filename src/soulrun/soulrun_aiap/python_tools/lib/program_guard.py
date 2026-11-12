"""A machine-detected identity fence using the existing human gate transport.

Called under the run lock. Never parses changed rules, invents a node commit,
rebases an identity or authorizes replay of a completed side effect.
"""
from __future__ import annotations

from . import runtime_identity

import copy
from pathlib import Path
import re
import secrets

from . import program_binding, render
from .run_store import RunStoreError, now_iso, sha256_bytes


def assert_run_version(index):
    from . import engine_core as ec
    version = str(index.get('engine_version', ''))
    match = runtime_identity.revision_match(version)
    protected = bool(match and int(match[1]) >= 119) or version.startswith('1.')
    if protected and version != ec.ENGINE_VERSION and index.get('run_state') not in ec.TERMINAL_STATES:
        raise ec.EngineError('RUN_ENGINE_VERSION_MISMATCH',
                             f'Run requires {version}; loaded engine is {ec.ENGINE_VERSION}. '
                             'Preserve this run; use its original engine or start a fresh run. No migration authorized.')


def check_write_target(target, executor, *, purpose='artifact', cache_dir=None, field=None):
    from . import engine_core as ec
    raw = str(target) if isinstance(target, (str, Path)) else ''
    if (purpose not in {'artifact', 'program'} or not raw.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in raw) or not Path(raw).is_absolute()):
        raise ec.EngineError('INVALID_WRITE_PATH', f'Expected an absolute, unescaped path and a valid purpose; got {raw!r}. '
                             'Use forward slashes; do not repair or resolve corrupted input.', field=field or 'path')
    path = Path(target).resolve()
    root = Path(executor).resolve()
    engine = ec._engine_dir().resolve()
    def code_owned(relative):
        parts = {p.casefold() for p in relative.parts}
        return bool(parts & {'tools', 'tool_dirs', 'python_tools', 'contracts', 'schemas', '.version_history'}
                    or relative.suffix.casefold() in {'.py', '.pyw', '.js', '.ts', '.sh', '.ps1', '.bat', '.cmd'}
                    or any(p.casefold() in str(relative).casefold() for p in ec.GOVERNANCE_PATTERNS))
    cache = Path(cache_dir).resolve() if cache_dir is not None else None
    original = Path(target).absolute()
    work_root = next((cache/name for name in ('_work', '_proc')
                      if cache and original.is_relative_to(cache/name)), None)
    machine_owned = False
    if work_root and path.is_relative_to(work_root):
        rel = path.relative_to(work_root)
        lexical = original.relative_to(work_root)
        # docs/05SoulRun 87: the acceptance receipts moved from replies/ to _receipts/ and stay machine evidence
        machine_owned = any((work_root.name == '_work' and bool(r.parts) and r.parts[0].casefold() in ('replies', '_receipts')) or (
            work_root.name == '_proc' and r.name.casefold().startswith('sha256-')) for r in (rel, lexical))
    if purpose == 'program' and not machine_owned:
        work = work_root and path.is_relative_to(work_root) and work_root.resolve() == work_root
        data = path != root and path.is_relative_to(root) and not path.is_relative_to(engine) and not code_owned(path.relative_to(root))
        if work or data:
            raise ec.EngineError('EXECUTOR_TARGET_OVERLAP',
                'This is current-run work or business data, not a program-write target. '
                'No program-write preflight is needed; register the existing file as an artifact. '
                'This does not authorize writing program code or machine-owned files.', field=field or 'target_aiap_dir')
    if purpose == 'artifact' and cache_dir is not None:
        for name in ('_work', '_proc'):
            work = cache / name
            if original.is_relative_to(work):
                if not path.is_relative_to(work) or work.resolve() != work:
                    raise ec.EngineError('INVALID_WORK_ARTIFACT', 'Work artifacts must be files within their own run work directory.',
                                         field=field or 'path')
                if machine_owned:
                    raise ec.EngineError('ENGINE_OWNED_ARTIFACT',
                        'Engine replies and hash captures are machine evidence, not model-written artifacts. Use their evidence channel.', field=field or 'path')
                if not path.exists():
                    raise ec.EngineError('WORK_ARTIFACT_MISSING', 'The current-run work file does not exist; register it after creation.', field=field or 'path')
                if not path.is_file():
                    raise ec.EngineError('INVALID_WORK_ARTIFACT', 'Work artifacts must be regular files, not directories.', field=field or 'path')
                return dict(status='PASS', path=str(path), purpose=purpose, read_only=True,
                            scope='current_run_work_artifact_not_a_filesystem_sandbox')
    for protected in (root, engine):
        if (protected.is_relative_to(path) or (path.is_relative_to(protected)
                and (purpose == 'program' or protected == engine))):
            raise ec.EngineError('EXECUTOR_TARGET_OVERLAP', f'Write target {path} overlaps executing program {protected}. '
                                 'Use an independent staging and publication target; do not write first.', field=field or 'target_aiap_dir')
    if path.is_relative_to(root):
        if code_owned(path.relative_to(root)):
            raise ec.EngineError('SELF_MODIFY_FORBIDDEN', f'{path} belongs to the executing program, not business data.', field=field or 'path')
    return dict(status='PASS', path=str(path), purpose=purpose, read_only=True,
                scope='declared_write_target_not_a_filesystem_sandbox')


def record(store, index):
    qid = index['gate'].get('question_id')
    if index['run_state'] == 'WAITING_USER' and qid:
        rec = store.read_json(store.gate_path(qid))
        if rec.get('program_drift'):
            return rec
    return None


def restored_payloads(store, index, node, visit):
    """The payloads the answered program-integrity stops of the occurrence (`node`, `visit`) kept (pending_payload_refs) and
    a recheck released: named to the occurrence's next serve (engine_core._serve), never accepted. Record 90 round 6 (B2,
    problem 94): not those of an integrity stop opened while the run waited at an engine dispatch stop (_opened_over_gate)
    - there every payload in its record came from a node-commit made while it was open (pause() keeps none there:
    no serve or commit reaches pause() at a waiting dispatch stop), which the run whose files never changed keeps under
    _dispatch_pending and names to no later serve; so after the recheck that stop's payloads stay kept and are named to no
    one, and a replacement agent the human then chooses is not handed the work of the executor it replaces. Record 90
    round 7 (B4, 'vb 2' defect 4): likewise over a waiting business gate - not those of any integrity stop opened while the
    run waited at a gate (_opened_over_gate)."""
    refs = []
    for row in index['gate']['history']:
        if row.get('node') != node or not row.get('answered_at'):
            continue
        rec = store.read_json(store.gate_path(row['question_id']))
        if rec.get('program_drift') and rec.get('visit') == visit and rec.get('chosen_intent') == 'recheck_program' \
                and not _opened_over_gate(rec):
            for ref in rec.get('pending_payload_refs', []):
                if ref not in refs:
                    refs.append(ref)
    return refs


def _opened_over_gate(rec):
    """Record 90 round 7 (B4; round 6 B2 for a dispatch stop): True when the program-integrity stop `rec` was opened while
    the run waited at a gate - a business gate or an engine dispatch stop (previous_run_state WAITING_USER). Every payload
    such a stop keeps came from a call the run waiting at that gate refuses (a node-commit: RUN_STATE_FORBIDS_COMMIT, or at
    a dispatch stop kept under _dispatch_pending; the interpretation command: no interpretation is pending while the run
    waits); pause() from a serve or a gate-answer keeps none. So after the recheck those payloads are named to no one
    (restored_payloads, answer()'s reply), as on the run whose files never changed."""
    return rec.get('previous_run_state') == 'WAITING_USER'


def pending_payload(store, payload, rec=None, *, directory='_program_drift'):
    if payload is not None:
        raw = payload.encode('utf-8')
        digest = sha256_bytes(raw)
        path = store.cache_dir / directory / f'payload-{digest}.txt'
        if path.exists():
            if store.read_bytes(path) != raw:
                raise RunStoreError('READ_BACK_MISMATCH', f'pending payload changed: {path}')
        else:
            store.write_text_once(path, payload)
        ref = dict(path=str(path), sha256=digest, bytes=len(raw), accepted=False)
        if rec is not None and ref not in rec.setdefault('pending_payload_refs', []):
            from . import engine_core as ec
            rec['pending_payload_refs'].append(ref)
            ec._write_json(store.gate_path(rec['question_id']), rec)
        return ref
    return None


def reply(store, index, rec, *, hint=None, publish=True):
    """The served program-integrity stop `rec`. Record 90 round 4 (B1, B3): `publish` False - a serve that does not reach
    the main executor (a sub-agent's call; the reply of a gate-answer that opened the stop, pause(publish=False), or that
    installed it or met it not yet shown, engine_core._show_integrity_stop - round 5) or orphan_stop's render check: the
    menu is not written (a stop whose menu.<qid>.* file exists has been served to the main executor) and the reply names
    no menu file (public_prompt_ref None). A gate-answer at the stop once it has been shown (answer(): an option not
    matched, a recheck that does not pass) publishes, as every serve did before round 4; that stop is shown already."""
    from . import engine_core as ec
    view = dict(rec)
    recorded = bool(rec.get('answered_at'))
    latest = (rec.get('recheck_attempts') or [{}])[-1]
    details = [f"{row.get('kind')}: {row.get('file', row.get('detail', 'binding'))}" for row in latest.get('changes', rec['program_drift']['changes'])]
    if latest and hint is None and not recorded:
        hint = '原文件尚未恢复，保持暂停。' if str(index.get('user_language')).startswith('zh') else 'Original files are not restored; still paused.'
    view['question'] += '\n\n' + str(rec['program_drift']['target'].get('dir')) + '\n' + '\n'.join(details)
    view['explanation'] += (' 覆盖AISOP与AIAP.md；不覆盖工具脚本或业务数据。' if str(index.get('user_language')).startswith('zh') else
                            ' Coverage: AISOP and AIAP.md, not tool scripts or business data.')
    if recorded:
        label = rec.get('chosen_label') or rec.get('chosen_intent')
        notice = (f'你先前在这道题上的答复「{label}」已经记下，但处理尚未完成；这里不是新的选择。\n\n原问题和选项（只读，不重新开放）：\n'
                  if str(index.get('user_language')).startswith('zh') else
                  f'Your earlier answer to this stop ({label}) is recorded but is not yet complete. This is not a new choice.\n\n'
                  'Original question and options (read-only, not offered again):\n')
        view['question'] = notice + view['question']
    prompt = render.menu_block(view, hint=hint, user_language=index.get('user_language'), answered=recorded,
                               heading='▣ GATE — 已记录的答复 / recorded answer' if recorded else None)
    name = f"menu.{rec['question_id']}.txt"
    if publish:
        store.write_public(name, prompt)
    return dict(status='WAITING_USER', run_state='WAITING_USER', schema_version=1,
                run=dict(trace_id=index['trace_id'], state='WAITING_USER'), node=None,
                steps=[], public_plan=None, public_plan_ref=None, public_block=None,
                gate=dict(question_id=rec['question_id'], state='WAITING_USER', required=True,
                          source='hsaw_doubt', kind='choice', advisory=False, prompt_text=None,
                          public_prompt=prompt, public_prompt_ref=ec._ref(store, name) if publish else None),
                resume=dict(kind='waiting_user', source=rec['question_id']),
                errors=[dict(code=rec['program_drift']['code'], message=(
                    'Earlier human answer is recorded but incomplete; a new reply cannot change that choice.' if recorded else
                    'Program identity changed; human decision required.'))],
                next=None, submission_accepted=False, pending_payload_refs=rec.get('pending_payload_refs', []),
                program_binding=dict(status='DRIFT', changes=rec['program_drift']['changes']))


def _stop_text(zh):
    """The fixed parts of the program-integrity stop pause() writes, in the run's language - shared with orphan_stop, which
    recognises them (record 90 round 3)."""
    return dict(
        question='运行程序或权限文件已变化，执行已暂停。请恢复原文件后复核，或取消。' if zh else
                 'Program or permission files changed. Execution is paused. Restore original files and recheck, or cancel.',
        options=[
            dict(kind='execute', label='恢复原文件后复核' if zh else 'Recheck restored files', intent='recheck_program',
                 note='只复核原字节，不接受新权限，不自动重放。' if zh else 'Original bytes only; no new permissions or automatic replay.'),
            dict(kind='cancel', label='取消本次运行' if zh else 'Cancel this run', intent='cancel',
                 note='保留现有证据和工件，不再执行。' if zh else 'Preserve evidence and artifacts; stop execution.')],
        closing='回复完整编号或选项名；其它具体要求原样保留但不授权续行，请另设人裁问题。' if zh else
                'Reply with an exact number or label. Other requirements are retained but do not authorize continuation; ask a separate gate.',
        recommendation='recheck_program',
        advice='建议先恢复原文件；需要新版本时取消后新开运行。' if zh else
               'Restore the original files; use a new run for a changed program.',
        explanation='已完成工作不回滚；待提交载荷保留但未接受，不能把暂停当作重做副作用的授权。' if zh else
                    'Completed work is preserved. Pending payloads are retained, not accepted; no replay is authorized.')


def pause(store, index, error, payload=None, *, publish=True):
    """Opens the program-integrity stop at the run's current occurrence (the payload it keeps, the ticket it abandons, its
    write-once record, then _land) and serves it - or serves the one already open. Record 90 round 6 (B3 (4)): the one
    already open includes the stop an earlier pause() at this occurrence wrote and was cut off before its index write
    (orphan_stop, problem 85): it is installed first (_cut_off), as reinstall() installs it, and served as the open one -
    so a call that reaches pause() before any install under its lock never opens a second stop with the same number
    beside it. Every caller but one installs such a stop at its start (dispatch_budget.reinstall: next-node, node-commit,
    the interpretation command since the round-6 merge, gate-answer); the one left is engine_core.serve's drift path,
    which takes the run lock again after _serve released it, so _cut_off is a backstop for a stop cut off between
    those two locks (record 90 round 7, B5). Record 90 round 5 (ledger decision 185): `publish` False when that serve
    does not reach the main executor (a sub-agent's call, or a gate-answer inside the host's prepare): the menu is not
    written, so the stop is not marked served (reply). Problem 94 (round 5): while the run waits at an engine dispatch stop (_over_dispatch_stop) that
    stop's ticket is left as it is. This stop refuses every serve and commit with any ticket until it is answered (a
    node-commit's payload is kept in its record, not accepted), so no agent can be served or commit for the ticket; the
    host may still record the ticket's start or return, as on the run waiting at the dispatch stop, and an old agent may
    still be running (at a liveness stop that is why the stop exists). Once the files are restored and rechecked, the
    dispatch stop is answered as on the run whose files never changed (a payload kept meanwhile is named to no later serve:
    restored_payloads, round 6; nor in the recheck's reply, round 7). Over a running part (or a business gate) the open
    ticket is abandoned (paused_dispatch) and resumed after the recheck; over a waiting business gate a node-commit's
    payload is kept likewise and named to no later serve (round 7, B4: the run whose files never changed refuses that
    commit)."""
    from . import engine_core as ec
    existing = record(store, index) or _cut_off(store, index)
    if existing:
        pending_payload(store, payload, existing)
        return reply(store, index, existing, publish=publish)
    payload_ref = pending_payload(store, payload)
    now = now_iso()
    qid = f"q{len(index['gate']['history']) + 1:03d}-{secrets.token_hex(4)}"
    node, visit = index['current']['name'], index['current']['visit']
    key = ec._node_key(node, visit)
    zh = str(index.get('user_language', '')).startswith('zh')
    drift = dict(code='PROGRAM_DRIFT_DETECTED', changes=getattr(error, 'changes', []),
                 target=getattr(error, 'binding_target', None), observed_at=now)
    rec = dict(question_id=qid, node=node, visit=visit, source='hsaw_doubt', kind='choice', prompt_text=None, **_stop_text(zh),
               presented_at=now, delivered_at=None, answered_at=None, answer_text=None, resolution_kind=None,
               chosen_intent=None, chosen_label=None, consumed_by_commit=True,
               program_drift=drift, previous_gate=copy.deepcopy(index['gate']), previous_run_state=index['run_state'],
               previous_node_status=index['nodes'][key]['status'], pending_payload_refs=[payload_ref] if payload_ref else [])
    dispatch = index['nodes'][key].get('dispatch')
    if dispatch and dispatch.get('state') in ('ISSUED', 'CLAIMED') and not _over_dispatch_stop(store, index):
        rec['paused_dispatch'] = copy.deepcopy(dispatch)
        ec._record_ticket_state(store, dispatch, 'ABANDONED', paused_at=now)
    store.write_json_once(store.gate_path(qid), rec)
    _land(store, index, rec)
    return reply(store, index, rec, publish=publish)


def _cut_off(store, index):
    """Record 90 round 6 (B3 (4)): the program-integrity stop an earlier pause() at this occurrence wrote and was cut off
    before its index write (orphan_stop: recognised exactly as reinstall() recognises it; never raises), installed with
    _land - the index then holds it as that pause() would have left it - or None."""
    try:
        rec = orphan_stop(store, index)
    except Exception:      # noqa: BLE001 - not recognised (as dispatch_budget.unindexed_stop)
        return None
    if rec is None:
        return None
    _land(store, index, rec)
    return rec


def _over_dispatch_stop(store, index):
    """Record 90 round 5 (problem 94, ledger decision 185): True while the run `index` waits at an engine dispatch stop
    (dispatch_budget.record: its active gate's record carries dispatch_block) - pause() then leaves the part's ticket as it
    is; orphan_stop and landed_view read the same on the run the stop's record was opened on."""
    from . import dispatch_budget as db
    return index.get('run_state') == 'WAITING_USER' and db.record(store, index) is not None


def _land(store, index, rec):
    """pause()'s writes after the integrity stop's write-once record `rec`: the run with `rec` as its active stop, at the
    instant pause() stamped on the record - the ticket pause() abandoned (paused_dispatch; its dispatch file was written
    before the record), the gate and its history row, the stop's ticket, the run and the node waiting - its
    anomalies_summary row and the index. Record 90 round 3 (ledger decision 183, problem 85's method):
    dispatch_budget.reinstall() - at the start of next-node, node-commit, the interpretation command and gate-answer - and,
    since round 6, pause() itself (_cut_off) do exactly these for a record whose index write never landed (orphan_stop),
    so the two cannot drift apart. Record 90 round 4: _landed is the same without the
    write (the render check and landed_view)."""
    from . import engine_core as ec
    _landed(index, rec)
    ec._write_index(store, index)
    return index


def _landed(index, rec):
    """_land's changes to the run `index` in memory, for the stop `rec`."""
    from . import engine_core as ec
    qid, node, now = rec['question_id'], rec['node'], rec['presented_at']
    key = ec._node_key(node, rec['visit'])
    if 'paused_dispatch' in rec:
        index['nodes'][key]['dispatch'].update(state='ABANDONED', paused_at=now)
    index['gate'].update(state='WAITING_USER', question_id=qid, node=node, source='hsaw_doubt', kind='choice',
                         presented_at=now, delivered_at=None, answered_at=None)
    index['gate']['history'].append(dict(question_id=qid, node=node, source='hsaw_doubt', prompt_text=None,
                                       presented_at=now, answered_at=None, resolution_kind=None,
                                       answer_ref=f'_gate.{qid}.json'))
    index['tickets'].append(dict(question_id=qid, state='READY', minted_at=now))
    index['run_state'] = 'WAITING_USER'
    index['nodes'][key]['status'] = 'WAITING_USER'
    index['anomalies_summary'].append(dict(node=node, code=rec['program_drift']['code'],
                                           text=f"Frozen before further execution; evidence _gate.{qid}.json"))
    return index


def landed_view(store, index):
    """Read-only (record 90 round 4, B7): the run `index` as the host's lifecycle calls must read it - a copy with the
    program-integrity stop installed (_landed) when the run holds one cut off before its index write (orphan_stop: the
    stop the next next-node, node-commit, interpretation command or gate-answer installs, or pause() before it would open
    another), else `index`
    itself. engine_core.observe_dispatch_start, record_dispatch_resume_failure and the start half of
    record_dispatch_task_event answer on it (round 5, B6), so each answers as on the run that never stopped: where pause()
    abandoned the part's open ticket (paused_dispatch: over a running part or a business gate) that ticket is ABANDONED in
    the view - an Agent-tool start (observe_dispatch_start) is UNBOUND and a failed delivery DELIVERY_FAILURE_UNBOUND, with
    nothing written for it, while an SDK task start of that ticket (record_dispatch_task_event) is bound as on that run
    (that binding needs only a ticket not closed); where it left the ticket as it is (problem 94: over a waiting
    dispatch stop) the view holds it as before and they answer as on the run whose files never changed (a late start
    binds). record_dispatch_return reads the index as written and records the return, as the run that never stopped
    does; the recogniser accepts what it adds (_paused_dispatch). Recognising never raises (as
    dispatch_budget.unindexed_stop)."""
    try:
        rec = orphan_stop(store, index)
    except Exception:      # noqa: BLE001 - not recognised
        rec = None
    return _landed(copy.deepcopy(index), rec) if rec is not None else index


# Record 90 round 3 (ledger decision 183): the fields of the record pause() writes - always, sometimes - and the fields only
# an answer (answer(), or the gate-answer that opened the stop, after its index write) adds later; delivery sets delivered_at.
_STOP_FIELDS = frozenset(('question_id', 'node', 'visit', 'source', 'kind', 'prompt_text', 'question', 'options', 'closing',
                          'recommendation', 'advice', 'explanation', 'presented_at', 'delivered_at', 'answered_at',
                          'answer_text', 'resolution_kind', 'chosen_intent', 'chosen_label', 'consumed_by_commit',
                          'program_drift', 'previous_gate', 'previous_run_state', 'previous_node_status',
                          'pending_payload_refs'))
_ANSWER_FIELDS = frozenset(('invalid_answers', 'recheck_attempts', 'answer_text_original', 'answered_by', 'human_wait_ms',
                            'deducted_human_wait_ms', 'human_wait_basis', 'deferred_business_answer'))


def orphan_stop(store, index):
    """Record 90 round 3 (ledger decision 183, decision 181's method): the one unindexed gate record that pause() above wrote
    - the program-integrity stop - and nothing touched since, matching the run exactly, or None; reinstall() then installs
    it with _land - at the start of a next-node, node-commit or interpretation command (the latter since the round-6
    merge), and of a gate-answer (engine_core.answer_gate; through the host's prepare that runs only while the run waits at
    a gate, so there it installs this stop cut off over a waiting gate) - and so does pause() itself before it would open
    a second one (round 6, B3 (4): _cut_off, a backstop for engine_core.serve's drift path, which takes the run lock again
    after _serve released it). pause() runs while the run is RUNNING or WAITING_USER at a business
    gate or an engine dispatch stop - never over an integrity stop the run already waits at: it serves that one and writes
    no record (round 6, B3 (3): so while record() names one, nothing is recognised). Its writes are the payload it keeps
    and the ticket it abandons, the record, then the index. As for dispatch_budget.pause()'s stop
    (dispatch_budget.orphan_stop): the record's exact canonical bytes, the next number and the only unindexed write
    (unindexed_record); never answered or delivered, the current occurrence, the current gate, an instant in order
    (_matches_run); pause()'s fields and its fixed values in the run's language (_drift_record). And the values the index
    and files hold that pause() copied, compared by type as well as value (dispatch_budget._same, round 5 B1):
    previous_run_state is the run state, previous_node_status the node's status, the ticket it abandoned or left
    (_paused_dispatch: abandoned exactly where pause() abandons it - not over a waiting engine dispatch stop, problem 94,
    round 5 - with the host's return of that ticket recorded since, round 4 B7), the payload it kept (_kept_payloads), and
    the program it bound (round 5 B2, round 6 B3 (2): the binding target is the one pause() takes at the record's node -
    the run's routed program, or at Router.match the registry snapshot entry the kept payload's route names -
    _bound_target). Round 4 (B3): with the types pause() writes - the binding target a dict of exactly str dir and
    entry_file, each change row one of program_binding.differences' rows (_drift_record) - and it
    renders: served on a copy of the run with it installed, without writing (_renders). The record carries no seal: a
    rewrite that keeps all of this (the list of changed files, say) cannot be told; it authorizes nothing - answer()
    rechecks the bytes of the program the record's target names."""
    from . import dispatch_budget as db, engine_core as ec
    state = index.get('run_state')
    if state not in ('RUNNING', 'WAITING_USER') or record(store, index) is not None:
        return None
    found = db.unindexed_record(store, index)
    if found is None:
        return None
    qid, rec = found
    if not _drift_record(rec, qid, str(index.get('user_language', '')).startswith('zh')):
        return None
    if not db._matches_run(store, index, rec, _ANSWER_FIELDS) or not _bound_target(store, rec):
        return None
    node = index['nodes'][ec._node_key(rec['node'], rec['visit'])]
    if rec['previous_run_state'] != state or rec['previous_node_status'] != node.get('status'):
        return None
    if not _paused_dispatch(store, node, rec, over=_over_dispatch_stop(store, index)) or not _kept_payloads(store, rec):
        return None
    return rec if _renders(store, index, rec) else None


def _bound_target(store, rec):
    """Record 90 round 5 (B2): pause() takes the binding target from the error engine_core._load_bound_program raised, which
    names the program it loaded. Round 6 (B3 (2)): exactly the one it loads at the record's node - the run's routed program
    (_load_routed_program, wherever the run has one), or at Router.match, before the run has one, the registry snapshot
    entry the payload being committed names (engine_core._prevalidate_advance: route.package of the payload pause() kept,
    parsed as node-commit parses it) - by (dir, entry_file); never another snapshot entry. Anything unreadable fails."""
    from . import engine_core as ec
    run_input = ec._read_run_input(store)
    target = rec['program_drift']['target']
    bound = [run_input.get('routed')] if run_input.get('routed') else []
    if rec['node'] == ec.NODE_MATCH:
        try:
            ref = rec['pending_payload_refs'][0]
            text = store.read_bytes(store.cache_dir / '_program_drift' / f"payload-{ref['sha256']}.txt").decode('utf-8')
            route = ec._parse_payload(text, [], [], raw_gate_intents=[], na_reasons=[]).get('route')
            package = route['package'] if route else None
            bound.append(next((s for s in run_input['snapshot'] if s['package'] == package), None))
        except Exception:      # noqa: BLE001 - what cannot be read as the payload pause() kept names no program
            return False
    return any(isinstance(t, dict) and (t.get('dir'), t.get('entry_file')) == (target['dir'], target['entry_file'])
               for t in bound)


def _renders(store, index, rec):
    """Record 90 round 4 (B3): the stop as next-node serves it once installed (reply), on a copy of the run with it
    installed (_landed), through a view that refuses every write (dispatch_budget._StopView), the menu unwritten: False on
    any exception."""
    from . import dispatch_budget as db
    try:
        work = _landed(copy.deepcopy(index), copy.deepcopy(rec))
        reply(db._StopView(store, work, rec), work, copy.deepcopy(rec), publish=False)
    except Exception:      # noqa: BLE001 - B3: any failure to render fails closed
        return False
    return True


def _drift_record(rec, qid, zh):
    """The shape of the record pause() writes for the stop `qid` (see orphan_stop)."""
    from .dispatch_budget import _STAMP, _STOP_ID
    fields, drift, refs = set(rec), rec.get('program_drift'), rec.get('pending_payload_refs')
    return bool(_STOP_FIELDS <= fields and fields <= _STOP_FIELDS | {'paused_dispatch'} | _ANSWER_FIELDS
                and rec['question_id'] == qid and _STOP_ID.fullmatch(qid)
                and rec['source'] == 'hsaw_doubt' and rec['kind'] == 'choice' and rec['prompt_text'] is None
                and rec['consumed_by_commit'] is True
                and all(rec[k] == v for k, v in _stop_text(zh).items())
                and isinstance(rec['node'], str) and type(rec['visit']) is int
                and isinstance(rec['presented_at'], str) and _STAMP.fullmatch(rec['presented_at'])
                and isinstance(drift, dict) and set(drift) == {'code', 'changes', 'target', 'observed_at'}
                and drift['code'] == 'PROGRAM_DRIFT_DETECTED' and drift['observed_at'] == rec['presented_at']
                and isinstance(drift['changes'], list) and all(_change_row(row) for row in drift['changes'])
                and isinstance(drift['target'], dict) and set(drift['target']) == {'dir', 'entry_file'}
                and all(isinstance(v, str) and v for v in drift['target'].values())
                and isinstance(rec['previous_gate'], dict) and isinstance(rec['previous_run_state'], str)
                and isinstance(rec['previous_node_status'], str)
                and isinstance(refs, list) and len(refs) <= 1)


_SIZE = dict(bytes=int, sha256=str)


def _change_row(row):
    """Record 90 round 4 (B3): one row program_binding.differences writes, with its keys and types."""
    if not isinstance(row, dict) or not isinstance(row.get('kind'), str):
        return False
    kind, keys = row['kind'], set(row)

    def size(v):
        return isinstance(v, dict) and set(v) == set(_SIZE) and all(type(v[k]) is t for k, t in _SIZE.items())
    if kind == 'BASELINE_INVALID':
        return keys == {'kind'}
    if kind == 'IDENTITY_CHANGED':
        return keys == {'kind', 'file', 'expected', 'actual'} and row['file'] in ('directory', 'entry_file') \
            and all(v is None or isinstance(v, str) for v in (row['expected'], row['actual']))
    if kind in ('ADDED', 'REMOVED', 'CHANGED'):
        before, after = row.get('expected'), row.get('actual')
        return keys == {'kind', 'file', 'expected', 'actual'} and isinstance(row['file'], str) \
            and (before is None) == (kind == 'ADDED') and (after is None) == (kind == 'REMOVED') \
            and (before is None or size(before)) and (after is None or size(after))
    if kind == 'UNREADABLE':
        return keys == {'kind', 'file', 'reason'} and isinstance(row['file'], str) and isinstance(row['reason'], str)
    if kind == 'BASELINE_UNREADABLE':
        return keys == {'kind', 'files'} and isinstance(row['files'], dict)
    return False


def _paused_dispatch(store, node, rec, *, over=False):
    """pause() abandons the occurrence's open ticket before its record: paused_dispatch is that ticket exactly as the index
    holds it (by type as well as value, round 5 B1), and its dispatch file (where it has one) was abandoned at the stop's
    instant; with no open ticket there is none. Record 90 round 5 (problem 94): `over` - the run waits at an engine
    dispatch stop (_over_dispatch_stop): pause() leaves the ticket as it is and writes no paused_dispatch, whatever the
    ticket's state. Record 90 round 4 (B7): or the host has recorded that ticket's return since
    (engine_core.record_dispatch_return, which the run waiting at the stop takes as well): the index then holds it with
    exactly what that call adds (_with_return), and its dispatch file carries the same return."""
    from .dispatch_budget import _same
    dispatch = node.get('dispatch')
    paused = rec.get('paused_dispatch')
    if 'paused_dispatch' not in rec:
        return over or not (dispatch and dispatch.get('state') in ('ISSUED', 'CLAIMED'))
    if over or not (isinstance(paused, dict) and paused.get('state') in ('ISSUED', 'CLAIMED') and isinstance(dispatch, dict)):
        return False
    try:
        returned = not _same(dispatch, paused)
        if returned and not _same(dispatch, _with_return(store, paused, dispatch.get('exit_evidence'))):
            return False
        path = store.dispatch_path(dispatch['ticket'])
        if not store.exists_path(path):
            return not returned
        written = store.read_json(path)
    except (OSError, ValueError, KeyError, TypeError, RecursionError, RunStoreError):
        return False
    return isinstance(written, dict) and written.get('state') == 'ABANDONED' and written.get('paused_at') == rec['presented_at'] \
        and (not returned or (written.get('lifecycle') == 'RETURNED' and _same(written.get('exit_evidence'), dispatch['exit_evidence'])))


def _with_return(store, dispatch, ref):
    """Record 90 round 4 (B7): the open ticket `dispatch` (the index's, not paused) as engine_core.observe_dispatch_return
    leaves it once the host's return was recorded for it under the evidence reference `ref` - abandoned (it was neither
    paused nor committed), RETURNED with that exit evidence (and its resumed session observed, for a resume) - when `ref`
    names that ticket's return receipt by its digest; else None."""
    import json
    if dispatch.get('exit_evidence') or not isinstance(ref, dict):
        return None
    name = f"_dispatch_return.{dispatch['ticket']}.json"
    proof = store.read_json(store.cache_dir / name)
    if ref != dict(path=name, sha256=sha256_bytes(json.dumps(proof, ensure_ascii=False, sort_keys=True).encode())):
        return None
    out = dict(dispatch, state='ABANDONED', lifecycle='RETURNED', exit_evidence=ref)
    if dispatch.get('resume_executor'):
        out['context_resume'] = 'ORIGINAL_SESSION_RESUME_OBSERVED'
    return out


def _kept_payloads(store, rec):
    """pause() keeps the payload it was given before its record (pending_payload): no reference, or one to the file in
    _program_drift named by the digest of exactly the bytes it holds (its size an int, accepted False: by type as well as
    value, round 5 B1)."""
    from .dispatch_budget import _same
    for ref in rec['pending_payload_refs']:
        try:
            path = store.cache_dir / '_program_drift' / f"payload-{ref['sha256']}.txt"
            raw = store.read_bytes(path)
            if not _same(ref, dict(path=ref['path'], sha256=sha256_bytes(raw), bytes=len(raw), accepted=False)) \
                    or Path(ref['path']).resolve() != path.resolve():
                return False
        except (OSError, ValueError, KeyError, TypeError, RunStoreError):
            return False
    return True


def answer(store, index, rec, question_id, text, by):
    """The human's answer `text` at the open program-integrity stop `rec`: an option not matched or a recheck of files not
    restored keeps the stop (the record notes it); a cancel ends the run; a recheck of restored files returns the run to
    where the stop paused it. The answer is written into the stop's write-once record, then carried out (_apply_answer).
    Record 90 round 7 (B3, 'vb 1' defect 6): a record that already carries an answer - the process died after this
    function wrote it and before the index - is completed exactly as recorded (_complete_answer), never decided again."""
    from . import engine_core as ec
    if question_id != rec['question_id']:
        return dict(status='REJECTED', errors=[dict(code='GATE_MISMATCH', message='Answer the active program integrity gate first.')])
    if rec.get('answered_at'):
        return _complete_answer(store, index, rec, text)
    option = ec._match_option(rec['options'], (text or '').strip())
    cancel = (option and option['kind'] == 'cancel') or (text or '').strip().lower() in (ec.CANCEL_WORDS | ec.TERMINATE_WORDS)
    if not option and not cancel:
        rec.setdefault('invalid_answers', []).append(dict(at=now_iso(), text_original=text, by=by))
        ec._write_json(store.gate_path(question_id), rec)
        return reply(store, index, rec, hint='请选择1或2。' if str(index.get('user_language')).startswith('zh') else 'Choose 1 or 2.')
    if not cancel:
        run_input = ec._read_run_input(store)
        target = rec['program_drift']['target']
        try:
            ec._load_bound_program(run_input, target)
        except ec.EngineError as exc:
            rec.setdefault('recheck_attempts', []).append(dict(at=now_iso(), answer_text_original=text,
                                                              answered_by=by, changes=getattr(exc, 'changes', []), code=exc.code))
            ec._write_json(store.gate_path(question_id), rec)
            return reply(store, index, rec, hint='原文件尚未恢复，保持暂停。' if str(index.get('user_language')).startswith('zh') else 'Original files are not restored; still paused.')
    now = now_iso()
    wait = ec._ms_between(rec.get('delivered_at'), now) if rec.get('delivered_at') else None
    # An underlying business gate accounts for its entire wait when answered.
    deducted = (wait or 0) if rec['previous_run_state'] != 'WAITING_USER' else 0
    rec.update(answered_at=now, answer_text=text.strip(), answer_text_original=text, answered_by=by,
               resolution_kind='cancel' if cancel else 'chosen', chosen_intent='cancel' if cancel else 'recheck_program',
               chosen_label=option['label'] if option else text, human_wait_ms=wait, deducted_human_wait_ms=deducted,
               human_wait_basis='DELIVERED_TO_ANSWERED' if wait is not None else 'UNKNOWN_DELIVERY')
    ec._write_json(store.gate_path(question_id), rec)
    return _apply_answer(store, index, rec)


def _apply_answer(store, index, rec, lead=None):
    """answer()'s writes after the stop's answered write-once record `rec`, from that record alone - shared by the first
    attempt and its recovery (record 90 round 7, B3; as dispatch_budget._carry_out for the engine's dispatch stops): the
    node's waiting time, the ledger's gate_answer (appended once), the history row, the tickets, then the run ended by a
    cancel or returned by a recheck to where the stop paused it, and its index. `lead` - the line a recovery's reply
    carries as its answer_hint (_complete_answer), in the run's language as record 88's recovered replies give it. Round
    7 (B4, 'vb 1' defect 5): a recheck's reply names the payloads the stop kept only where a later serve is handed them
    (restored_payloads): none from a stop opened while the run waited at a gate (_opened_over_gate)."""
    from . import engine_core as ec
    question_id, now, cancel = rec['question_id'], rec['answered_at'], rec.get('resolution_kind') == 'cancel'
    node_entry = index['nodes'][ec._node_key(rec['node'], rec['visit'])]
    node_entry['human_wait_ms'] = (node_entry.get('human_wait_ms') or 0) + (rec.get('deducted_human_wait_ms') or 0)
    ec._ledger_append(store, index, dict(kind='gate_answer', at=now, trace_id=index['trace_id'], engine_version=ec.ENGINE_VERSION,
                      question_id=question_id, node=rec['node'], visit=rec['visit'], resolution_kind=rec['resolution_kind'],
                      chosen_intent=rec['chosen_intent'], delivered_at=rec.get('delivered_at'), answered_at=now,
                      human_wait_ms=rec.get('human_wait_ms'), answered_by=rec.get('answered_by'),
                      scope='program_integrity_not_business_authorization'))
    for row in index['gate']['history']:
        if row['question_id'] == question_id:
            row.update(answered_at=now, resolution_kind=rec['resolution_kind'])
    for ticket in index['tickets']:
        if ticket['question_id'] == question_id or (cancel and ticket['state'] == 'READY'):
            ticket['state'] = 'RETIRED' if cancel else 'CONSUMED'
    told = dict(answer_hint=lead) if lead else {}
    if cancel:
        ec.close_dispatch_tickets(store, index, f'program_drift_cancel:{question_id}')
        index['gate']['state'] = 'CLEAR'
        index['nodes'][ec._node_key(rec['node'], rec['visit'])]['status'] = 'FAILED'
        ec._terminate(index, kind='human_termination', by='human', reason=f'Program drift cancelled at {question_id}')
        ec._write_index(store, index)
        return dict(status='TERMINATED', run_state=index['run_state'], question_id=question_id, **told,
                    error_report=ec._error_report(store, index), terminal_delivery_refs=[ec._ref(store, 'ended.txt')])
    history = index['gate']['history']
    index['gate'] = dict(rec['previous_gate'], history=history)
    index['nodes'][ec._node_key(rec['node'], rec['visit'])]['status'] = rec['previous_node_status']
    index['run_state'] = rec['previous_run_state']
    ec._write_index(store, index)
    return dict(status='ANSWERED', question_id=question_id, run_state=index['run_state'],
                chosen=dict(intent='recheck_program', label=rec['chosen_label']),
                next=dict(node=rec['node']), program_binding=dict(status='MATCH'),
                pending_payload_refs=[] if _opened_over_gate(rec) else rec.get('pending_payload_refs', []), **told,
                note='Continue from preserved evidence. Do not replay completed side effects; any prior business gate still requires its own answer.')


def _complete_answer(store, index, rec, text):
    """Record 90 round 7 (B3, 'vb 1' defect 6; record 88's rule, as dispatch_budget._complete_recorded for the engine's
    dispatch stops): the open program-integrity stop `rec` already carries the human's answer - the process died after
    answer() wrote its gate record and before the index (with or without the ledger's gate_answer between) - and a reply
    has come again. The recorded answer is completed exactly as the first attempt decided it, from the record alone: a
    recorded cancel ends the run, a recorded recheck returns it to where the stop paused it (the bytes were rechecked when
    that answer was given; any later change is met by the next serve or commit, which opens a new stop). The new reply is
    never matched afresh and the gate record is never rewritten; the ledger's gate_answer is appended once. The reply
    says the recorded answer was completed as recorded and, unless the new reply named the same choice, that the new
    reply was not taken (ledger decision 186) - it calls no reply valid."""
    from . import engine_core as ec
    zh = str(index.get('user_language')).startswith('zh')
    text = (text or '').strip()
    option = ec._match_option(rec['options'], text)
    said = 'cancel' if ((option and option['kind'] == 'cancel') or text.lower() in (ec.CANCEL_WORDS | ec.TERMINATE_WORDS)) \
        else (option or {}).get('intent')
    same = said == rec.get('chosen_intent')
    label = rec.get('chosen_label') or rec.get('chosen_intent')
    cancel = rec.get('resolution_kind') == 'cancel'
    if zh:
        menu = (f'你先前在这道题上的答复「{label}」已经按记下的样子处理完了：' +
                ('本次运行已结束' if cancel else '复核在你回答时已经通过，运行回到这道题暂停之前的地方') +
                ('。' if same else '；你这次的回复没有采用。'))
    else:
        menu = (f'Your earlier answer to this stop ({label}) has now been completed as recorded: ' +
                ('this run has ended' if cancel else 'the recheck passed when you answered, and the run is back where this stop '
                                                     'paused it') + ('.' if same else '; your new reply was not taken.'))
    return _apply_answer(store, index, rec, lead=menu)


def dispatch_resume_gate(store, index, dispatch):
    if dispatch.get('state') != 'ABANDONED' or not dispatch.get('paused_at'):
        return None
    for row in reversed(index['gate']['history']):
        rec = store.read_json(store.gate_path(row['question_id']))
        if (rec.get('paused_dispatch') or {}).get('ticket') == dispatch['ticket']:
            return rec['question_id'] if rec.get('answered_at') and rec.get('chosen_intent') == 'recheck_program' else None
    return None
