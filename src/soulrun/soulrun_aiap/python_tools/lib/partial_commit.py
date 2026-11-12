"""Forward a proven original transition under the recovery policy; never replay business."""
import copy
import re
from pathlib import Path
from . import write_observation as wo
from .run_store import RunStore, RunStoreError, dumps, sha256_bytes, _regular_path, strict_loads, atomic_write_bytes, now_iso

INTENTS = '_commit_intents'
RECOVERIES = '_orphan_recoveries'
ORPHAN_CODE = 'ENGINE_ORPHAN_COMMIT_INTERRUPTED'


def persist_intent(cache_dir, observed, previous_raw=None):
    """Keep only this CLI's bound intent; no business replay or directory scan."""
    from . import fault_reentry, engine_core as ec
    from .run_store import _write_guard
    store = RunStore(cache_dir)
    operation = observed.get('operation_id') or ''
    if not re.fullmatch(r'[0-9a-f]{16}', operation):
        raise RunStoreError('COMMIT_INTENT_INVALID', 'Original operation identity is missing')
    directory = store.cache_dir / INTENTS
    path, pointer = directory / (operation + '.json'), directory / 'current.json'
    if not _regular_path(path) or not _regular_path(pointer) or _write_guard(path) is None:
        raise RunStoreError('COMMIT_INTENT_INVALID', 'Intent must remain under the original run lock')
    identity = (observed.get('forward_commit') or {}).get('identity') or {}
    mark = identity.get('progress_mark') or {}
    if identity.get('engine_version') != ec.ENGINE_VERSION or observed.get('trace_id') != identity.get('trace_id') \
            or observed.get('original_current') != dict(name=mark.get('node'),visit=mark.get('visit')):
        raise RunStoreError('COMMIT_INTENT_INVALID', 'Intent does not belong to the original transition')
    with wo.maintenance():
        if not (observed.get('request') or {}).get('payload_ref'):
            fault_reentry.preserve_request(store, observed)
        record = dict(schema_version=1, owner='execute_engine_commit_intent', operation_id=operation,
                      engine_version=identity['engine_version'], trace_id=identity['trace_id'], session_id=identity['session_id'],
                      progress_mark=copy.deepcopy(mark),
                      write_observation=observed)
        if previous_raw is not None and not path.exists():
            raise RunStoreError('COMMIT_INTENT_INVALID', 'Original intent disappeared during the owned operation')
        if path.exists():
            raw = store.read_bytes(path)
            old = strict_loads(raw.decode('utf-8')) if previous_raw is None else None
            if (previous_raw is not None and raw != previous_raw) or (old is not None and (
                    any(old.get(k) != record[k] for k in ('owner', 'operation_id', 'engine_version', 'trace_id', 'session_id', 'progress_mark'))
                    or old.get('sha256') != sha256_bytes(dumps({k:v for k,v in old.items() if k != 'sha256'}).encode()))):
                raise RunStoreError('COMMIT_INTENT_INVALID', 'Existing original intent changed')
        record['sha256'] = sha256_bytes(dumps(record).encode())
        raw = dumps(record).encode()
        atomic_write_bytes(path, raw)
        head = dict(schema_version=1, operation_id=operation)
        head_raw = dumps(head).encode()
        if not pointer.exists() or store.read_bytes(pointer) != head_raw:
            if not _regular_path(pointer):
                raise RunStoreError('COMMIT_INTENT_INVALID', 'Intent pointer is not regular')
            atomic_write_bytes(pointer, head_raw)
        return raw


def original_intent(store, index):
    """The pointer discovers evidence; its presence never grants recovery."""
    from . import tool_faults, engine_core as ec
    pointer = store.cache_dir / INTENTS / 'current.json'
    try:
        if not pointer.exists():
            return None
        if not _regular_path(pointer):
            raise ValueError('intent pointer is not regular')
        head = store.read_json(pointer)
        operation = head.get('operation_id') or ''
        if head.get('schema_version') != 1 or not re.fullmatch(r'[0-9a-f]{16}', operation):
            raise ValueError('invalid intent pointer')
        path = pointer.parent / (operation + '.json')
        if not _regular_path(path):
            raise ValueError('intent path is not regular')
        saved = store.read_json(path)
        record = {k:v for k,v in saved.items() if k != 'sha256'}
        if saved.get('sha256') != sha256_bytes(dumps(record).encode()) or record.get('schema_version') != 1 \
                or record.get('owner') != 'execute_engine_commit_intent' or record.get('operation_id') != operation \
                or any(record.get(k) != index.get(k) for k in ('engine_version', 'trace_id', 'session_id')):
            raise ValueError('original intent identity or digest changed')
        if record.get('progress_mark') != tool_faults.mark(index):
            return None
        row = dict(owner='execute_engine_cli', tool='node_commit', at=now_iso(),
                   engine_version=index['engine_version'], trace_id=index['trace_id'], progress_mark=tool_faults.mark(index),
                   error=dict(code=ORPHAN_CODE, message='Original CLI ended before index acceptance; verify its persisted Engine transition.'),
                   write_observation=record['write_observation'])
        row['sha256'] = tool_faults.seal(row)
        return row
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RunStoreError) as exc:
        raise ec.EngineError('ENGINE_ORPHAN_WRITE_SET_UNPROVEN', 'Original intent cannot be verified; preserve it and stop.') from exc


def _operation_id(row):
    operation = (row.get('write_observation') or {}).get('operation_id') or ''
    if not re.fullmatch(r'[0-9a-f]{16}', operation):
        raise ValueError('original operation identity is missing')
    return operation


def _recovery_path(store, row, authorization):
    identity = dict(kind=authorization['kind'], question_id=authorization.get('question_id'))
    attempt = sha256_bytes(dumps(identity).encode())[:16]
    return store.cache_dir / RECOVERIES / (_operation_id(row) + '.' + attempt + '.json'), attempt


def record_recovery(store, index, row, verified, authorization):
    """Persist an attempt before forwarding; outcome is later read from acceptance."""
    path, attempt = _recovery_path(store, row, authorization)
    if not _regular_path(path):
        raise ValueError('recovery receipt path is not regular')
    record = dict(schema_version=1, owner='execute_engine_orphan_recovery', at=now_iso(),
                  operation_id=row['write_observation']['operation_id'], engine_version=index['engine_version'],
                  attempt_id=attempt,
                  trace_id=index['trace_id'], session_id=index['session_id'], node=verified['entry']['name'], visit=verified['visit'],
                  cache_ref=verified['path'].relative_to(store.cache_dir).as_posix(),
                  cache_sha256=sha256_bytes(store.read_bytes(verified['path'])),
                  cache_revision=len(verified['cache'].get('continuations') or []),
                  intent_sha256=sha256_bytes(dumps(row['write_observation']).encode()),
                  authorization=authorization, business_replayed=False)
    with wo.maintenance():
        if path.exists():
            old = store.read_json(path)
            if old.get('receipt_sha256') != sha256_bytes(dumps({k:v for k,v in old.items() if k != 'receipt_sha256'}).encode()) \
                    or any(old.get(k) != record[k] for k in ('owner','operation_id','attempt_id','engine_version','trace_id','session_id','node','visit','cache_ref','cache_sha256','cache_revision','intent_sha256','authorization','business_replayed')):
                raise ValueError('recovery receipt changed')
            return old
        record['receipt_sha256'] = sha256_bytes(dumps(record).encode())
        store.write_json_once(path, record)
    return record


def recover_unrecorded(store, index):
    from . import engine_core as ec, tool_faults
    import prepare_cache
    row = original_intent(store, index)
    verified = proof(store.cache_dir, index, row or {})
    if not row or not verified:
        raise ec.EngineError('ENGINE_ORPHAN_WRITE_SET_UNPROVEN', 'No complete original transition proof; preserve it and stop.')
    policy = prepare_cache.resume_interrupted_policy()
    directory = store.cache_dir / RECOVERIES
    if not _regular_path(directory):
        raise ec.EngineError('ENGINE_ORPHAN_WRITE_SET_UNPROVEN', 'Recovery diagnostic path changed; preserve and stop.')
    previous_attempt = any(directory.glob(_operation_id(row) + '.*.json'))
    if not policy['enabled'] or previous_attempt:
        error = ec.EngineError(ORPHAN_CODE, row['error']['message'],
                               example=dict(resume_policy=policy, automatic_attempt_already_recorded=previous_attempt))
        with wo.maintenance():
            tool_faults.record(store.cache_dir, 'node_commit', error, observation=row['write_observation'])
        raise error
    record_recovery(store, index, row, verified, dict(kind='switch', policy=policy))
    _apply_verified(verified, index)
    return True


def guard_submission(store, index, entry, visit):
    """A fresh payload must not append over an unaccepted original transition."""
    from . import engine_core as ec, dispatch_lifecycle, tool_faults
    if not dispatch_lifecycle.replacement_accounting(index):
        return
    path = ec._cache_path_for(store, index, entry, visit)
    accepted_sha = (index['nodes'].get(ec._node_key(entry['name'], visit)) or {}).get('cache_sha256')
    known_gates = {h['question_id'] for h in index['gate']['history']}
    unindexed_gate = any(p.stem.removeprefix('_gate.') not in known_gates for p in store.cache_dir.glob('_gate.q*.json'))
    if not unindexed_gate and (not store.exists_path(path) or
            accepted_sha == sha256_bytes(store.read_bytes(path))):
        return
    try:
        row = original_intent(store, index)
        verified = proof(store.cache_dir, index, row or {})
    except ec.EngineError:
        if accepted_sha and not unindexed_gate:
            return  # The existing continuation validator owns accepted-cache drift.
        raise
    if not verified:
        if accepted_sha and not unindexed_gate:
            return
        raise ec.EngineError('ENGINE_ORPHAN_WRITE_SET_UNPROVEN', 'Unaccepted original cache is not proven; preserve it, never append a new submission.')
    error = ec.EngineError(ORPHAN_CODE, 'Original transition is pending; use its preserved submission, never append a new payload or repeat business.')
    with wo.maintenance():
        tool_faults.record(store.cache_dir, 'node_commit', error, observation=row['write_observation'])
    raise error


def _delivery_state(store, index):
    path = store.cache_dir / RECOVERIES / 'delivery.json'
    if not _regular_path(path):
        raise ValueError('notification store is not regular')
    if not path.exists():
        return dict(schema_version=1, owner='execute_engine_orphan_notice', deliveries={},
                    **{k:index[k] for k in ('trace_id','session_id','engine_version')})
    saved = store.read_json(path)
    if saved.get('owner') != 'execute_engine_orphan_notice' or saved.get('schema_version') != 1 \
            or not isinstance(saved.get('deliveries'), dict) \
            or any(saved.get(k) != index.get(k) for k in ('trace_id','session_id','engine_version')) \
            or saved.get('sha256') != sha256_bytes(dumps({k:v for k,v in saved.items() if k != 'sha256'}).encode()):
        raise ValueError('notification identity or checksum changed')
    saved.pop('sha256')
    return saved


def recovery_observations(cache_dir, index=None):
    """Receipts describe attempts; accepted state proves whether they completed."""
    from . import engine_core as ec, tool_faults
    store = RunStore(cache_dir)
    directory = store.cache_dir / RECOVERIES
    if not directory.exists():
        return []
    if not _regular_path(directory):
        raise ValueError('recovery diagnostic directory is not regular')
    index = index if index is not None else store.read_index()
    deliveries = _delivery_state(store, index)['deliveries']
    out, accepted = [], None
    for path in sorted(directory.glob('*.json')):
        if path.name == 'delivery.json':
            continue
        if not _regular_path(path):
            raise ValueError('recovery receipt is not regular')
        raw = store.read_bytes(path)
        row = strict_loads(raw.decode('utf-8'))
        if row.get('receipt_sha256') != sha256_bytes(dumps({k:v for k,v in row.items() if k != 'receipt_sha256'}).encode()) \
                or row.get('owner') != 'execute_engine_orphan_recovery' or row.get('schema_version') != 1 \
                or not re.fullmatch(r'[0-9a-f]{16}', str(row.get('operation_id',''))) \
                or not re.fullmatch(r'[0-9a-f]{16}', str(row.get('attempt_id',''))) \
                or path.name != row['operation_id'] + '.' + row['attempt_id'] + '.json' \
                or any(row.get(k) != index.get(k) for k in ('trace_id','session_id','engine_version')):
            raise ValueError('recovery receipt identity or checksum changed')
        recovered = False
        key = ec._node_key(row['node'], row['visit'])
        state = index.get('nodes', {}).get(key) or {}
        entry = ec._catalog_entry(index, row['node'])
        if entry and state.get('cache_sha256'):
            cache_path = ec._cache_path_for(store, index, entry, row['visit'])
            cache_raw = store.read_bytes(cache_path)
            history = strict_loads(cache_raw.decode('utf-8'))
            revision = row['cache_revision']
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
                raise ValueError('invalid recovery revision')
            if revision <= len(history.get('continuations') or []) and sha256_bytes(cache_raw) == state['cache_sha256']:
                history['continuations'] = (history.get('continuations') or [])[:revision]
                recovered = sha256_bytes(dumps(history).encode()) == row['cache_sha256']
                if recovered:
                    if accepted is None:
                        accepted = tool_faults.accepted_state_proof(cache_dir, index)
                    ledger = ec._read_ledger(store)
                    recovered = bool(accepted and any(e.get('kind') in ('commit','pause') and e.get('node') == row['node']
                        and e.get('visit') == row['visit'] and e.get('revision') == revision
                        and e.get('cache_sha256') == row['cache_sha256'] for e in ledger))
        out.append(dict(source_ref=path.relative_to(store.cache_dir).as_posix(), source_sha256=sha256_bytes(raw),
                        code='ORPHAN_COMMIT_RECOVERED' if recovered else 'ORPHAN_RECOVERY_ATTEMPT_PENDING',
                        record=row, recovery_authorized=False,
                        acceptance_basis='current_original_operation_acceptance_not_individual_attempt_outcome',
                        notice=dict(deliveries.get(row['operation_id']) or {'state':'NOT_QUEUED'})))
    return out


def notification(cache_dir, events, invocation_id, agent_name):
    """Host-event observation, not an ACK from constructing callback Content."""
    from . import engine_core as ec, render
    store = RunStore(cache_dir)
    path = store.cache_dir / RECOVERIES / 'delivery.json'
    if not (store.cache_dir / RECOVERIES).exists():
        return None
    with wo.maintenance(), store.lock():
        index = store.read_index()
        rows = recovery_observations(cache_dir, index)
        saved = _delivery_state(store, index)
        pieces, queued, changed = [], [], False
        for item in rows:
            if item['code'] != 'ORPHAN_COMMIT_RECOVERED':
                continue
            row = item['record']
            operation = row['operation_id']
            if operation in queued:
                continue
            zh = index.get('user_language') == 'zh'
            body = (
                f"Engine 恢复通知：{row['node']}（第 {row['visit']} 次）的原提交记账已补完并核验。\n"
                "仅补 Engine 状态；未重新计算、联网或重复写业务记录，原业务门仍由你裁决。\n"
                f"恢复依据：{item['source_ref']}。这条说明由宿主生成，不是 ACP 原文。" if zh else
                f"Engine recovery notice: original bookkeeping for {row['node']} (visit {row['visit']}) was forwarded and verified.\n"
                "Only Engine state was completed; no business computation, fetch or record write was repeated. Business gates still require your answer.\n"
                f"Receipt: {item['source_ref']}. This is a host-generated notice, not ACP output.")
            authorization = row.get('authorization') or {}
            if authorization.get('kind') == 'human':
                raw_reply = authorization['answer_text_original']
                displayed = raw_reply.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|',r'\|').replace('\r','').replace('\n','<br>')
                details = (f"\n\n| 人类裁决 | 内容 |\n| --- | --- |\n| 回复原文 | {displayed} |\n"
                           f"| 恢复门 | {authorization['question_id']} |\n| 授权范围 | 仅补原 Engine 记账，不重执业务 |" if zh else
                           f"\n\n| Human decision | Value |\n| --- | --- |\n| Original reply | {displayed} |\n"
                           f"| Recovery gate | {authorization['question_id']} |\n| Scope | Original Engine bookkeeping only; no business replay |")
                body += details
            text = render.robot_frame(body, index.get('user_language'))
            note = saved['deliveries'].get(operation) or {}
            if note.get('state') == 'OBSERVED':
                continue
            if note.get('text_sha256') == sha256_bytes(text.encode()) and note.get('invocation_id'):
                observed = next((e for e in events if e.get('id') and e.get('author') == agent_name
                    and e.get('invocation_id') == note['invocation_id']
                    and sha256_bytes(e.get('text','').encode()) == note.get('message_sha256')), None)
                if observed:
                    note.update(state='OBSERVED', event_id=observed['id'], observed_at=now_iso(), basis='committed_host_callback_event')
                    saved['deliveries'][operation] = note
                    changed = True
                    continue
            if note.get('invocation_id') == invocation_id or not invocation_id:
                continue
            saved['deliveries'][operation] = dict(state='QUEUED_UNCONFIRMED', invocation_id=invocation_id,
                text_sha256=sha256_bytes(text.encode()), receipt_sha256=row['receipt_sha256'], queued_at=now_iso())
            pieces.append(text)
            queued.append(operation)
            changed = True
        message = '\n'.join(pieces)
        for operation in queued:
            saved['deliveries'][operation]['message_sha256'] = sha256_bytes(message.encode())
        if changed:
            saved['sha256'] = sha256_bytes(dumps(saved).encode())
            atomic_write_bytes(path, dumps(saved).encode())
        return message if pieces else None


def _dispatch_values(before, machine, entry, visit, previous=None):
    from . import dispatch_lifecycle
    progress = dict(before, last_progress_at=dispatch_lifecycle.progress_time(
        machine['committed_at'], before.get('last_progress_at'), previous))
    complete = dict(progress)
    if machine.get('paused_gate'):
        complete['paused_at'] = machine['committed_at']
    elif before['scope_root'] == dict(node=entry['name'], visit=visit) and not machine.get('module_prefix'):
        complete.update(state='COMMITTED', committed_at=machine['committed_at'], actor='sub_agent')
    return before, progress, complete


def _dispatch_intent(store, index, entry, visit, last):
    from . import engine_core as ec
    machine = last['machine'].get('dispatch')
    if not machine or not machine.get('ticket'):
        return None
    _, owner = ec._self_dispatch(index, entry, visit)
    if not owner or owner['state'] != 'CLAIMED' or owner.get('paused_at') \
            or machine.get('actor') != 'sub_agent' or machine.get('fallback') \
            or owner.get('scope_root') != machine.get('scope_root'):
        raise ValueError('Only an original claimed subtree can be forwarded')
    path = store.dispatch_path(machine['ticket'])
    if not _regular_path(path):
        raise ValueError('Dispatch path changed')
    before = store.read_json(path)
    if before.get('ticket') != owner['ticket'] or before.get('state') != 'CLAIMED' \
            or before.get('claimed_at') != owner.get('claimed_at') or before.get('paused_at') \
            or before.get('trace_id') != index['trace_id'] or before.get('scope_root') != owner.get('scope_root') \
            or before.get('bootstrap_sha256') != owner.get('bootstrap_sha256') \
            or sha256_bytes(before['bootstrap'].encode()) != owner.get('bootstrap_sha256'):
        raise ValueError('Original dispatch authority changed')
    return dict(path=path.name, before=before, before_sha256=sha256_bytes(store.read_bytes(path)))


def prepare(store, index, entry, visit, last, *, pause_record=None, hsaw_events=(), shared_events=()):
    from . import dispatch_lifecycle, engine_core as ec
    if not dispatch_lifecycle.replacement_accounting(index):
        return
    if entry['name'] == ec.NODE_MATCH:
        return
    try:
        dispatch = _dispatch_intent(store, index, entry, visit, last)
    except (OSError, ValueError, TypeError, KeyError, RunStoreError):
        return
    if last['machine'].get('paused_gate') and not pause_record:
        return
    shared = None
    if last['machine'].get('hsaw'):
        if not hsaw_events or not shared_events:
            return
        from . import hsaw_gate
        target = hsaw_gate.ledger_path(store.cache_dir.parent, ec._hsaw_package(index))
        try:
            if not _regular_path(target):
                return
            raw = store.read_bytes(target) if store.exists_path(target) else b''
            expected, _ = hsaw_gate.project_ledger(raw, ec._hsaw_package(index),
                f"{store.cache_dir.name}:{index['trace_id']}", shared_events)
            shared = dict(path=str(target), before_sha256=sha256_bytes(raw) if target.exists() else 'ABSENT',
                          expected_sha256=sha256_bytes(expected), events=copy.deepcopy(shared_events))
        except (OSError, ValueError, RunStoreError):
            return
    ledger = ec._read_ledger(store)
    gate = last.get('gate_answer')
    manifests = {}
    try:
        for frame in index.get('call_stack') or []:
            manifest = store.manifest_path(frame['parent'])
            if not _regular_path(manifest):
                return
            manifests[manifest.relative_to(store.cache_dir).as_posix()] = sha256_bytes(store.read_bytes(manifest))
    except (OSError, ValueError, KeyError, RunStoreError):
        return
    path = ec._cache_path_for(store, index, entry, visit)
    final_paths = [store.cache_dir/'final_answer.json', store.final_answer_path,
                   store.public_dir/'final_answer.txt', store.public_dir/'evidence.txt'] if entry['name'] in ec.FINAL_NODES else []
    if any(store.exists_path(p) for p in final_paths):
        return
    wo.bind_forward_commit(dict(schema_version=1, node=entry['name'], visit=visit,
        identity=dict(engine_version=index['engine_version'],trace_id=index['trace_id'],session_id=index['session_id'],
                      progress_mark=dict(completed=len(index['completed']),node=entry['name'],visit=visit)),
        cache_ref=path.relative_to(store.cache_dir).as_posix(),
        last_sha256=sha256_bytes(dumps(last).encode()),
        before_cache_sha256=sha256_bytes(store.read_bytes(path)) if store.exists_path(path) else 'ABSENT',
        ledger_count=len(ledger), ledger_prefix_sha256=sha256_bytes(dumps(ledger).encode()), manifests=manifests,
        gate_sha256=sha256_bytes(store.read_bytes(store.gate_path(gate['question_id']))) if gate else None,
        pause_record=copy.deepcopy(pause_record),
        final_paths=[p.relative_to(store.cache_dir).as_posix() for p in final_paths],
        hsaw_events=copy.deepcopy(hsaw_events), shared_ledger=shared, dispatch=dispatch))


def proof(cache_dir, index, row):
    from . import engine_core as ec, dispatch_lifecycle, fault_reentry, tool_faults
    try:
        store = RunStore(cache_dir)
        observed = row['write_observation']
        intent = observed['forward_commit']
        baseline = observed['baseline']
        request = fault_reentry.original_request(store, row)
        if not dispatch_lifecycle.replacement_accounting(index) or row['tool'] != 'node_commit' \
                or observed['effect_phase'] == 'ACCEPTED' or not request \
                or request.get('interpretation') or intent.get('schema_version') != 1 \
                or request.get('node') != intent['node'] or index['run_state'] != 'RUNNING' \
                or index['current'] != dict(name=intent['node'], visit=intent['visit']) \
                or not wo.state_matches(index, baseline) \
                or sha256_bytes(store.read_bytes(store.cache_dir/'_run_input.json')) != baseline['input_sha256']:
            return None
        program = ec._load_routed_program(ec._read_run_input(store))
        entry = ec._catalog_entry(index, intent['node'])
        path = ec._cache_path_for(store, index, entry, intent['visit'])
        if path.relative_to(store.cache_dir).as_posix() != intent['cache_ref'] or not _regular_path(path):
            return None
        cache = store.read_json(path)
        last = (cache.get('continuations') or [cache])[-1]
        pause = intent.get('pause_record')
        if bool(pause) != bool(last['machine'].get('paused_gate')):
            return None
        if pause:
            pause_path = store.gate_path(pause['question_id'])
            if pause['question_id'] != last['machine']['paused_gate'] or pause['node'] != intent['node'] \
                    or pause['visit'] != intent['visit'] or not _regular_path(pause_path) \
                    or store.read_json(pause_path) != pause or pause.get('answered_at') \
                    or pause.get('answer_text') or pause.get('delivered_at') or pause.get('consumed_by_commit'):
                return None
        normalized = dict(payload=last['payload'], machine=last['machine'], gate_answer=last.get('gate_answer'))
        if sha256_bytes(dumps(normalized).encode()) != intent['last_sha256'] \
                or last['machine'].get('trace_id') != index['trace_id'] \
                or last['machine'].get('engine_version') != index['engine_version']:
            return None
        dispatch = intent.get('dispatch')
        machine_dispatch = last['machine'].get('dispatch') or {}
        formal_path = None
        if bool(dispatch) != bool(machine_dispatch.get('ticket')):
            return None
        if dispatch:
            _, owner = ec._self_dispatch(index, entry, intent['visit'])
            before = dispatch['before']
            formal_path = store.dispatch_path(machine_dispatch['ticket'])
            if not owner or owner.get('state') != 'CLAIMED' or owner.get('paused_at') \
                    or request.get('agent_ticket') != owner['ticket'] or owner['ticket'] != before['ticket'] \
                    or dispatch['path'] != formal_path.name or not _regular_path(formal_path) \
                    or sha256_bytes(dumps(before).encode()) != dispatch['before_sha256'] \
                    or before.get('bootstrap_sha256') != owner.get('bootstrap_sha256') \
                    or before.get('trace_id') != index['trace_id'] or before.get('scope_root') != owner.get('scope_root') \
                    or sha256_bytes(before['bootstrap'].encode()) != owner.get('bootstrap_sha256') \
                    or ec._check_dispatch_for_commit(index, program, entry, intent['visit'], last['payload'], request['agent_ticket'], store=store) != machine_dispatch:
                return None
            values = _dispatch_values(before, last['machine'], entry, intent['visit'], owner.get('last_progress_at'))
            formal_raw = store.read_bytes(formal_path)
            if formal_raw not in {dumps(v).encode() for v in values}:
                return None
            written = next((w for w in observed['writes'] if Path(w['path']) == formal_path), None)
            if written and written.get('before_sha256') != dispatch['before_sha256'] \
                    or not written and formal_raw != dumps(before).encode():
                return None
        elif request.get('agent_ticket'):
            return None
        for artifact in last['machine'].get('artifacts') or []:
            artifact_path = Path(artifact['path'])
            if not _regular_path(artifact_path) or sha256_bytes(store.read_bytes(artifact_path)) != artifact.get('sha256'):
                return None
        if intent['before_cache_sha256'] != 'ABSENT':
            previous = copy.deepcopy(cache)
            if not previous.get('continuations'):
                return None
            previous['continuations'].pop()
            if sha256_bytes(dumps(previous).encode()) != intent['before_cache_sha256']:
                return None
        elif cache.get('continuations'):
            return None
        ledger = ec._read_ledger(store)
        count = intent['ledger_count']
        final = entry['name'] in ec.FINAL_NODES
        if ec.ledger_errors(ledger) or len(ledger) not in ({count, count+1, count+2} if final else {count, count+1}) \
                or sha256_bytes(dumps(ledger[:count]).encode()) != intent['ledger_prefix_sha256']:
            return None
        if len(ledger) > count and any(ledger[count].get(k) != v for k, v in dict(kind='pause' if pause else 'commit',
                node=intent['node'], visit=intent['visit'], trace_id=index['trace_id'],
                revision=len(cache.get('continuations') or []), cache_sha256=sha256_bytes(store.read_bytes(path))).items()):
            return None
        key = ec._node_key(intent['node'], intent['visit'])
        projection = copy.deepcopy(index)
        projection['nodes'][key]['cache_sha256'] = sha256_bytes(store.read_bytes(path))
        if not tool_faults.accepted_state_proof(cache_dir, projection):
            return None
        pending = last.get('gate_answer')
        gate_path = store.gate_path(pending['question_id']) if pending else None
        block_name = f"node.{entry['ordinal']+1:02d}.{ec._safe_name(entry['name'])}.v{intent['visit']}.txt"
        allowed = {path, store.index_path, store.evidence_path, store.public_dir/block_name}
        if formal_path:
            allowed.add(formal_path)
        shared = intent.get('shared_ledger')
        hsaw_events = intent.get('hsaw_events') or []
        shared_sha = None
        if bool(shared) != bool(last['machine'].get('hsaw')):
            return None
        if shared:
            from . import hsaw_gate
            shared_path = hsaw_gate.ledger_path(store.cache_dir.parent, ec._hsaw_package(index))
            discoveries = [e for e in hsaw_events if e.get('kind') == 'discovered']
            items = last['machine']['hsaw']['items']
            if shared['path'] != str(shared_path) or not _regular_path(shared_path) \
                    or shared['events'] != discoveries or len(discoveries) != len(items):
                return None
            for event, item in zip(discoveries, items):
                if any(event.get(k) != item.get(k) for k in ('id','fingerprint','category','severity','disposition','title')):
                    return None
            shared_sha = sha256_bytes(store.read_bytes(shared_path)) if shared_path.exists() else 'ABSENT'
            if shared_sha not in {shared['before_sha256'], shared['expected_sha256']}:
                return None
            hsaw_gate.project_ledger(store.read_bytes(shared_path) if shared_path.exists() else b'',
                ec._hsaw_package(index), f"{store.cache_dir.name}:{index['trace_id']}", shared['events'])
            allowed.add(shared_path)
        preserved_evidence = None
        if final:
            from . import final_answer, render
            final_paths = [store.cache_dir/'final_answer.json', store.final_answer_path,
                           store.public_dir/'final_answer.txt', store.public_dir/'evidence.txt']
            if intent.get('final_paths') != [p.relative_to(store.cache_dir).as_posix() for p in final_paths]:
                return None
            text = ec._compose_answer(last['payload'], last['machine'].get('report_parts'))
            artifact = final_answer.assemble(text, index.get('user_language') or 'zh',
                last['machine']['final_answer_basis'], (last['payload'].get('semantics') or {}).get('answer_details'))
            expected_final = {final_paths[0]: dumps(artifact).encode(), final_paths[1]: text.encode(),
                              final_paths[2]: render.final_block(text, index.get('user_language')).encode()}
            for target in final_paths:
                allowed.add(target)
                written = next((w for w in observed['writes'] if Path(w['path']) == target), None)
                if not _regular_path(target) or (store.exists_path(target) and not written):
                    return None
                if target in expected_final and store.exists_path(target) and store.read_bytes(target) != expected_final[target]:
                    return None
            if len(ledger) == count+2 and any(ledger[-1].get(k) != v for k, v in dict(kind='final',
                    at=last['machine']['committed_at'], trace_id=index['trace_id'], engine_version=index['engine_version'],
                    final_answer_sha256=sha256_bytes(text.encode()), run_state='COMPLETED').items()):
                return None
            if store.exists_path(final_paths[3]):
                preserved_evidence = sha256_bytes(store.read_bytes(final_paths[3]))
        if pause:
            position = ec._track_position(index, entry, intent['visit'])
            allowed.update({pause_path, store.public_dir/f"menu.{pause['question_id']}.txt",
                store.public_dir/f"pause.{position['ordinal']:02d}.{ec._safe_name(entry['name'])}.{pause['question_id']}.v{intent['visit']}.txt"})
        frame_closed_at = None
        manifests = intent.get('manifests') or {}
        frame_paths = {store.manifest_path(frame['parent']).relative_to(store.cache_dir).as_posix(): frame
                       for frame in index.get('call_stack') or []}
        if set(manifests) != set(frame_paths):
            return None
        for relative, before_sha in manifests.items():
            manifest_path = store.cache_dir / relative
            if not _regular_path(manifest_path):
                return None
            written = next((w for w in observed['writes'] if Path(w['path']) == manifest_path), None)
            expected = written.get('expected_sha256') if written else before_sha
            actual = sha256_bytes(store.read_bytes(manifest_path))
            if (written and written.get('before_sha256') != before_sha) or actual not in {before_sha, expected}:
                return None
            manifest = store.read_json(manifest_path)
            frame = frame_paths[relative]
            if any(manifest.get(k) != v for k, v in dict(trace_id=index['trace_id'], engine_version=index['engine_version'],
                    parent=frame['parent'], parent_visit=frame['parent_visit'], dir=frame['dir']).items()):
                return None
            if frame is ec._frame_of(index, entry) and manifest.get('state') == 'CLOSED' and actual == expected:
                frame_closed_at = manifest.get('closed_at')
                if not ec._parse_ts(frame_closed_at):
                    return None
            allowed.add(manifest_path)
        report = last['machine'].get('execution_report')
        if report:
            from . import execution_report
            execution_report.verify(report, last['payload']['user_summary'], store.cache_dir.name,
                                    intent['node'], intent['visit'])
            report_path = store.cache_dir / report['file']
            if report_path.parent != store.cache_dir / '_reports' or not _regular_path(report_path):
                return None
            report_bytes = store.read_bytes(report_path)
            if len(report_bytes) != report['full_bytes'] or sha256_bytes(report_bytes) != report['full_sha256']:
                return None
            allowed.add(report_path)
        if gate_path:
            allowed.add(gate_path)
            gate = store.read_json(gate_path)
            gate['consumed_by_commit'] = False
            if sha256_bytes(dumps(gate).encode()) != intent['gate_sha256']:
                return None
        for written in observed['writes']:
            target = Path(written['path'])
            if target not in allowed or not _regular_path(target):
                return None
            if target == store.index_path:
                continue  # The versioned baseline above, not an append-only prefix.
            actual = sha256_bytes(store.read_bytes(target)) if store.exists_path(target) else 'ABSENT'
            expected = written.get('expected_sha256') or written.get('sha256')
            if actual not in {expected, written.get('before_sha256')}:
                return None
            if target == path and actual != expected:
                return None  # No complete original cache to re-apply.
            if target == gate_path:
                gate = store.read_json(gate_path)
                if gate.get('answer_text') != pending.get('answer_text'):
                    return None
                gate['consumed_by_commit'] = False
                if sha256_bytes(dumps(gate).encode()) != written.get('before_sha256'):
                    return None
        pre = None if pause else ec._prevalidate_advance(store, index, ec._read_run_input(store), program, entry, last['payload'])
        return dict(store=store, program=program, entry=entry, visit=intent['visit'], cache=cache,
                    path=path, last=last, pre=pre, frame_closed_at=frame_closed_at, pause_record=pause,
                    preserved_evidence_sha256=preserved_evidence, hsaw_events=hsaw_events,
                    shared_ledger=shared, shared_ledger_sha256=shared_sha)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RunStoreError, ec.EngineError):
        return None


def _apply_verified(verified, index):
    """Both automatic and human recovery use the original Engine transition."""
    from . import engine_core as ec
    store, last = verified['store'], verified['last']
    if verified['shared_ledger']:
        from . import hsaw_gate
        hsaw_gate.ledger_append(store.cache_dir.parent, ec._hsaw_package(index),
            f"{store.cache_dir.name}:{index['trace_id']}", verified['shared_ledger']['events'],
            verified_append=True, expected_sha256=verified['shared_ledger_sha256'])
    if last.get('gate_answer'):
        ec._mark_gate_consumed(store, last['gate_answer']['question_id'])
    if verified['pause_record']:
        return ec._finish_pause(store, index, verified['entry'], verified['visit'], last['payload'],
                                verified['path'], last['machine'], verified['pause_record'],
                                hsaw_events=verified['hsaw_events'])
    if verified['hsaw_events']:
        from . import hsaw_gate
        hsaw_gate.append_events(index, verified['hsaw_events'])
    return ec._apply_commit_to_index(store, index, ec._read_run_input(store), verified['program'],
        verified['entry'], verified['visit'], last['payload'], verified['cache'], verified['path'], verified['pre'],
        recovered=True, frame_closed_at=verified['frame_closed_at'],
        preserved_evidence_sha256=verified['preserved_evidence_sha256'])


def recover(cache_dir):
    from . import engine_core as ec, tool_faults
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        row = tool_faults.current(cache_dir, index)
        permit = tool_faults.retry_permit(cache_dir)
        verified = proof(cache_dir, index, row or {})
        if not verified or permit.get('state') != 'CONSUMED' or permit.get('strategy') != 'FORWARD_ORPHAN_COMMIT' \
                or permit.get('fault_sha256') != row.get('sha256'):
            raise ec.EngineError('ENGINE_FAULT_REENTRY_INVALID', 'Exact orphan write set or human permit changed; do not replay business.')
        if row['error']['code'] == ORPHAN_CODE:
            record_recovery(store, index, row, verified, dict(kind='human', question_id=permit['question_id'],
                answer_text_original=permit['answer_text_original'], answer_source_ref='_host_lifecycle.json',
                answer_sha256=sha256_bytes(permit['answer_text_original'].encode())))
        result = _apply_verified(verified, index)
        if not verified['pause_record']:
            ec._write_index(store, index)
            result.update(status='COMMITTED', node=verified['entry']['name'], run_state=index['run_state'],
                          cache_sha256=index['nodes'][ec._node_key(verified['entry']['name'], verified['visit'])]['cache_sha256'])
    ticket = (verified['last']['machine'].get('dispatch') or {}).get('ticket')
    return ec._with_next_plan(cache_dir, result, ticket)
