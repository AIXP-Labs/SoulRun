"""Human-authorized handover when no native identity source is qualified.

Host reports and receipt files are observations, never identity authority in this
release. A new logical execution right requires a bound, presented human choice.
"""
from __future__ import annotations

import copy
import hashlib
import json
import secrets


def _ec():
    from . import engine_core
    return engine_core


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _text(index, zh, en):
    return zh if str(index.get('user_language', '')).lower().startswith('zh') else en


def _ref(store, name):
    return dict(path=name, sha256=hashlib.sha256(store.read_bytes(store.cache_dir / name)).hexdigest())


def _read_ref(store, ref):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        raise ValueError('Missing handover reference')
    path = store.cache_dir / ref['path']
    if path.parent != store.cache_dir or hashlib.sha256(store.read_bytes(path)).hexdigest() != ref['sha256']:
        raise ValueError('Handover reference changed')
    return store.read_json(path)


_AUTHORITY_FIELDS = ('question_id', 'node', 'visit', 'source', 'kind', 'prompt_text', 'question', 'dispatch_block',
                     'options', 'recommendation', 'advice', 'explanation', 'closing', 'presented_at',
                     'consumed_by_commit', 'previous_gate', 'previous_status')
_AUTHORITY_BINDING = ('checkpoint_sha256', 'business_question_id', 'business_record_sha256')
_ANSWER_BASE = frozenset(('delivered_at', 'answered_at', 'answer_text', 'resolution_kind', 'chosen_intent', 'chosen_label'))
_ANSWER_ADDITIONS = frozenset(('answer_text_original', 'answered_by', 'invalid_answers', 'human_wait_ms', 'human_wait_basis'))


def _authority_digest(store, rec):
    required = set(_AUTHORITY_FIELDS) | _ANSWER_BASE | {'identity_handoff'}
    if not required <= set(rec) or not set(rec) <= required | _ANSWER_ADDITIONS:
        raise ValueError('Handover record has missing or unknown fields')
    data = rec['identity_handoff']
    if not isinstance(data, dict) or set(data) != set(_AUTHORITY_BINDING) | {'fence_ref'}:
        raise ValueError('Handover authority binding changed')
    gate = {key: rec[key] for key in _AUTHORITY_FIELDS}
    gate['identity_handoff'] = {key: data[key] for key in _AUTHORITY_BINDING}
    return _digest(dict(input_sha256=hashlib.sha256(store.read_bytes(store.cache_dir / '_run_input.json')).hexdigest(),
                        gate=gate))


def _check_authority(store, rec, fence=None):
    fence = _read_ref(store, rec['identity_handoff']['fence_ref']) if fence is None else fence
    if fence.get('authority_sha256') != _authority_digest(store, rec):
        raise ValueError('Original handover input or immutable question changed; preserve it and stop')
    return fence


def _guard_authority(store, rec):
    try:
        return _check_authority(store, rec)
    except (ValueError, KeyError, OSError) as exc:
        raise _ec().EngineError('DISPATCH_REPLACEMENT_INVALID', str(exc)) from exc


def _owner(index):
    ec = _ec()
    current = index['current']
    entry = ec._catalog_entry(index, current['name'])
    key, dispatch = ec._self_dispatch(index, entry, current['visit'])
    return key, dispatch


def snapshot(store, index):
    ec = _ec()
    accepted, steps = {}, {}
    for key, row in index['nodes'].items():
        if not row.get('cache_sha256'):
            continue
        name, _, visit = key.partition('@')
        entry = ec._catalog_entry(index, name)
        path = ec._cache_path_for(store, index, entry, int((visit or '1').removeprefix('v')))
        raw = store.read_bytes(path)
        if hashlib.sha256(raw).hexdigest() != row['cache_sha256']:
            raise ValueError('Accepted cache changed')
        accepted[key] = row['cache_sha256']
        payload = ec._latest_payload(store.read_json(path))
        steps[key] = payload.get('steps')
    answers = []
    for item in index['gate']['history']:
        if not item.get('answered_at') or item.get('resolution_kind') not in ('chosen', 'free_text', 'cancel'):
            continue
        rec = store.read_json(store.gate_path(item['question_id']))
        if rec.get('program_drift') or rec.get('dispatch_block'):
            continue
        answers.append(dict(question_id=rec['question_id'], answer_sha256=_digest(rec.get('answer_text_original', rec.get('answer_text')))))
    _, dispatch = _owner(index)
    progress = dict(root=dispatch.get('scope_root') if dispatch else None,
                    completed=index['completed'], steps=steps, business_answers=answers)
    return dict(accepted=accepted, progress_key=_digest(progress), external_execution='UNKNOWN')


def record(store, index):
    if index['run_state'] != 'WAITING_USER' or not index['gate'].get('question_id'):
        return None
    rec = store.read_json(store.gate_path(index['gate']['question_id']))
    return rec if rec.get('identity_handoff') else None


def fenced_ticket(index, ticket):
    if not ticket:
        return
    for node in index['nodes'].values():
        current = node.get('dispatch') or {}
        for row in [current, *(current.get('history') or [])]:
            if row.get('ticket') == ticket and row.get('state') == 'ABANDONED' \
                    and row.get('closed_reason') == 'identity_unverified':
                return current


def _publication(store, index, rec, *, publish=True):
    ec = _ec()
    from . import render
    _guard_authority(store, rec)
    name = f"menu.{rec['question_id']}.txt"
    text = render.menu_block(rec, user_language=index.get('user_language'))
    if publish:
        path = store.public_dir / name
        if store.exists_path(path) and store.read_bytes(path) == text.encode('utf-8'):
            from . import menu_history
            menu_history.preserve(store, name, text)
        else:
            store.write_public(name, text)
    source_qid = rec['identity_handoff'].get('business_question_id')
    if publish and source_qid:
        ec._restore_pause_block(store, index, store.read_json(store.gate_path(source_qid)))
    _, dispatch = _owner(index)
    refs = list((dispatch or {}).get('public_refs') or [])
    if source_qid:
        refs = [r for r in refs if f'menu.{source_qid}.' not in r]
    menu_ref = ec._ref(store, name) if publish else None
    if menu_ref and menu_ref not in refs:
        refs.append(menu_ref)
    current = index['current']
    return dict(schema_version=1, status='WAITING_USER',
        run=dict(trace_id=index['trace_id'], state='WAITING_USER'),
        node=dict(name=current['name'], kind=ec._catalog_entry(index, current['name'])['kind']), steps=[],
        gate=dict(state='WAITING_USER', required=True, source='hsaw_doubt', kind='choice',
                  question_id=rec['question_id'], public_prompt=text, public_prompt_ref=menu_ref),
        public_plan=None, public_plan_ref=None,
        public_block_ref=ec._pause_ref(store, source_qid) if source_qid else None,
        dispatch=dict(public_refs=refs, required=False, ticket=(dispatch or {}).get('ticket')),
        resume=dict(kind='waiting_user', source=rec['question_id']))


def _business_options(index, business):
    options = []
    for position, option in enumerate(business['options'], 1):
        if option['kind'] == 'execute':
            options.append(dict(kind='execute', label=option['label'] + _text(index, '，并授权一个新代理继续', ' / authorize one new agent'),
                intent=f'identity_business_{position}',
                note=(option.get('note') or '') + _text(index,
                    ' 同时授权一个新代理仅按本检查点和所选业务范围继续。',
                    ' Apply this business choice and authorize one new agent for the recorded unfinished work.')))
        else:
            note = _text(index,
                ' 取消后续业务，不授权新代理；保留已有结果并按原流程收尾。',
                ' Cancel the remaining business without authorizing an agent; preserve accepted work and follow the original closeout.') \
                if option['kind'] == 'cancel' else _text(index,
                    ' 本选项不授权新代理；保留原停止与保全含义。',
                    ' This choice does not authorize a new agent; preserve its original stop and evidence-preservation intent.')
            options.append(dict(kind=option['kind'], label=option['label'], intent=f'identity_business_{position}',
                                note=(option.get('note') or '') + note))
    return options


def open_gate(store, index, *, business=None, publish=True):
    ec = _ec()
    from . import dispatch_budget
    existing = record(store, index)
    if existing:
        return _publication(store, index, existing, publish=publish)
    pending = dispatch_budget.unindexed_record(store, index)
    if pending and pending[1].get('identity_handoff'):
        raise ec.EngineError('ENGINE_ORPHAN_WRITE_SET_UNPROVEN',
                             'Interrupted handover authority is unproven; preserve it and stop.')
    key, dispatch = _owner(index)
    if not dispatch or not dispatch.get('scope_root'):
        raise ec.EngineError('DISPATCH_REPLACEMENT_INVALID', 'Only the current dispatched root may be handed over.')
    now = ec.now_iso()
    qid = f"q{len(index['gate']['history']) + 1:03d}-{secrets.token_hex(4)}"
    checkpoint = snapshot(store, index)
    exhausted = not business and same_progress_claims(dispatch, checkpoint['progress_key']) > ec.DISPATCH_ATTEMPTS_MAX
    fence = dict(schema_version=1, trace_id=index['trace_id'], ticket=dispatch['ticket'],
        scope_root=copy.deepcopy(dispatch['scope_root']), node=index['current']['name'], visit=index['current']['visit'],
        checkpoint=checkpoint, question_id=qid, at=now, reason='identity_unverified',
        business_question_id=business['question_id'] if business else None)
    fence_name = f'_dispatch_fence.{qid}.json'
    options = []
    if business:
        options = _business_options(index, business)
    elif not exhausted:
        options.append(dict(kind='execute', label=_text(index, '授权一个新代理按已记录工作继续', 'Authorize one new agent to continue'), intent='identity_continue',
            note=_text(index, '只继续本检查点的未完成工作，结果不明的外部操作先核对、不重做。',
                       'Continue only accepted-checkpoint remaining work; do not repeat uncertain external effects.')))
    options.extend([
        dict(kind='execute', label=_text(index, '先暂停，查看交接证据', 'Pause and inspect handover evidence'), intent='identity_inspect',
             note=_text(index, '不消耗业务门，不派新代理，不执行后续业务。', 'Keep the business question unanswered; no new agent or business execution.')),
        dict(kind='cancel', label=_text(index, '结束后续执行并保留已有结果', 'Stop further execution'), intent='identity_stop',
             note=_text(index, '保留已接受工作和证据，不派新代理。', 'Preserve accepted work and evidence; do not dispatch a new agent.')),
    ])
    metadata = dict(fence_ref=None, checkpoint_sha256=_digest(checkpoint),
        business_question_id=business['question_id'] if business else None,
        business_record_sha256=_ref(store, store.gate_path(business['question_id']).name)['sha256'] if business else None)
    rec = dict(question_id=qid, node=index['current']['name'], visit=index['current']['visit'],
        source='hsaw_doubt', kind='choice', dispatch_block='ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE',
        question=((business['question'] + '\n\n') if business else '') + _text(index,
            '同一业务进度的故障重试已耗尽；只能暂停查证或结束。' if exhausted else
            '原子代理身份无法核实。是否授权一个新代理按已记录的未完成工作继续？',
            'The same-progress retry allowance is exhausted. Pause and inspect, or stop.' if exhausted else
            'Native child identity is unverified. Authorize a new agent for the recorded remaining work?'),
        options=options, recommendation='identity_inspect', advice=_text(index, '存疑时先查看绑定的检查点与交接证据。', 'Inspect the bound checkpoint if uncertain.'),
        explanation=((business.get('explanation', '') + '\n') if business else '') + _text(index,
            '旧派工单执行权已关闭，这不证明旧进程或外部工具已退出。结果不明的外部操作先核对、不重做。只有明确的继续选项同时授权新代理。',
            'The old execution right is fenced. This does not prove that the old process or external tools exited. '
            'Unknown external operations must be checked, not repeated. Only a continuing option authorizes a new agent.')
            + '\n' + _text(index, '以下请求记录仅作诊断，不认证身份或退出。',
                           'The following request records are diagnostic only, not identity or exit proof.')
            + '\n' + dispatch_budget.tool_request_facts(store, index, dispatch,
                                                       str(index.get('user_language', '')).lower().startswith('zh')),
        closing=_text(index, '请回复当前选项的完整编号或名称。其它回复不自动授权换人。',
                      'Reply with the exact current option number or label. Other replies do not authorize replacement.'),
        prompt_text=None, presented_at=now, delivered_at=None, answered_at=None, answer_text=None,
        resolution_kind=None, chosen_intent=None, chosen_label=None, consumed_by_commit=True,
        previous_gate=copy.deepcopy(index['gate']),
        previous_status=index['nodes'][ec._node_key(index['current']['name'], index['current']['visit'])]['status'],
        identity_handoff=metadata)
    # Bind the intended immutable question before the existing fence -> gate -> index writes.
    fence['authority_sha256'] = _authority_digest(store, rec)
    store.write_json_once(store.cache_dir / fence_name, fence)
    metadata['fence_ref'] = _ref(store, fence_name)
    store.write_json_once(store.gate_path(qid), rec)
    dispatch.update(state='ABANDONED', closed_reason='identity_unverified', closed_at=now)
    dispatch_budget._install(index, rec, now)
    ec._write_index(store, index)
    return _publication(store, index, rec, publish=publish)


def _validate_fence(store, index, rec):
    data = rec['identity_handoff']
    fence = _check_authority(store, rec)
    _, dispatch = _owner(index)
    if not dispatch or fence['ticket'] != dispatch['ticket'] or fence['trace_id'] != index['trace_id'] \
            or fence['scope_root'] != dispatch.get('scope_root') or fence['question_id'] != rec['question_id'] \
            or _digest(fence['checkpoint']) != data['checkpoint_sha256']:
        raise ValueError('Handover fence no longer binds this root')
    current = snapshot(store, index)
    if current['accepted'] != fence['checkpoint']['accepted']:
        raise ValueError('Accepted checkpoint changed')
    if dispatch['state'] != 'ABANDONED' or not dispatch.get('closed_reason'):
        raise ValueError('Old execution right is not fenced')
    return fence


def _authorization_path(store, qid):
    return store.cache_dir / f'_dispatch_identity_authorization.{qid}.json'


def _consume_question(index, qid):
    ticket = next((t for t in index['tickets'] if t['question_id'] == qid), None)
    if not ticket or ticket['state'] not in ('READY', 'CONSUMED'):
        raise _ec().EngineError('TICKET_NOT_READY', 'The handover question has no consumable human-reply ticket.')
    ticket['state'] = 'CONSUMED'


def _finish_conditional(store, index, rec, source):
    _guard_authority(store, rec)
    """Reconcile a durably accepted original reply; never infer replacement consent."""
    ec = _ec()
    source_id = rec['identity_handoff']['business_question_id']
    if not source.get('conditional_reply') or source.get('resolution_kind') != 'free_text' \
            or source.get('delivered_via_question_id') != rec['question_id'] \
            or source.get('question_id') != source_id or source.get('node') != rec['node'] \
            or source.get('visit') != rec['visit'] or not source.get('answered_at') \
            or not source.get('answer_text_original'):
        raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Conditional reply is not bound to this joint question.')
    ticket = next((t for t in index['tickets'] if t['question_id'] == source_id), None)
    if not ticket or ticket['state'] not in ('READY', 'CONSUMED'):
        raise ec.EngineError('TICKET_NOT_READY', 'The recorded conditional reply cannot be recovered.')
    if ticket['state'] == 'READY':
        history = copy.deepcopy(index['gate']['history'])
        index['gate'] = copy.deepcopy(rec['previous_gate'])
        index['gate']['history'] = history
        program = ec._load_routed_program(ec._read_run_input(store))
        ec._answer_locked(store, index, program, source_id, source['answer_text_original'],
                          source['answered_by'], _recorded=source)
        index.clear()
        index.update(store.read_index())
    rec.update(answered_at=source['answered_at'], answer_text_original=source['answer_text_original'],
               answered_by=source['answered_by'], delivered_at=source.get('delivered_at'),
               resolution_kind='free_text', chosen_intent=None, chosen_label=None)
    ec._write_json(store.gate_path(rec['question_id']), rec)
    row = next(r for r in index['gate']['history'] if r['question_id'] == rec['question_id'])
    row.update(answered_at=source['answered_at'], resolution_kind='free_text')
    _consume_question(index, rec['question_id'])
    ec._write_index(store, index)


def _check_answer(index, rec, auth, *, answered=False):
    ec = _ec()
    data = rec['identity_handoff']
    option = ec._match_option(rec['options'], (auth.get('answer_text_original') or '').strip())
    if auth.get('trace_id') != index['trace_id'] or auth.get('question_id') != rec['question_id'] \
            or auth.get('fence_ref') != data['fence_ref'] \
            or auth.get('checkpoint_sha256') != data['checkpoint_sha256'] \
            or auth.get('business_question_id') != data['business_question_id'] \
            or not auth.get('answered_at') or not auth.get('answered_by') or not option \
            or option['intent'] != auth.get('chosen_intent') or option['intent'] == 'identity_inspect':
        raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Recorded handover answer changed.')
    if (answered or rec.get('answered_at')) and any(rec.get(key) != auth.get(key) for key in
                        ('answered_at', 'answer_text_original', 'answered_by', 'chosen_intent')):
        raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Human answer and handover authorization disagree.')
    if (answered or rec.get('answered_at')) and rec.get('chosen_label') != option['label']:
        raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Recorded choice label differs from the shown option.')
    if option['intent'].startswith('identity_business_') and (
            not isinstance(auth.get('business_choice'), dict)
            or auth['business_choice'].get('kind') != option['kind']):
        raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Business action differs from the shown choice kind.')
    return option


def _delivery(index, rec, answered_at):
    return dict(question_id=rec['question_id'], delivered_at=rec.get('delivered_at') or index['gate'].get('delivered_at'),
                answered_at=answered_at)


def _own_wait(store, index, rec, auth, resolution):
    ec = _ec()
    delivered = auth.get('delivered_at')
    wait = ec._ms_between(delivered, auth['answered_at']) if delivered else None
    rec.update(delivered_at=delivered, human_wait_ms=wait,
               human_wait_basis='DELIVERED_TO_ANSWERED' if delivered else 'UNKNOWN_DELIVERY')
    history = next(r for r in index['gate']['history'] if r['question_id'] == rec['question_id'])
    if not history.get('answered_at'):
        node = index['nodes'][ec._node_key(rec['node'], rec['visit'])]
        node['human_wait_ms'] = (node['human_wait_ms'] or 0) + (wait or 0)
        if delivered is None:
            index['anomalies_summary'].append(dict(node=rec['node'], code='HUMAN_WAIT_UNKNOWN',
                text=f"gate {rec['question_id']}: no delivered timestamp; no wait deducted from active elapsed"))
    if not any(e.get('kind') == 'gate_answer' and e.get('question_id') == rec['question_id']
               and e.get('answered_at') == auth['answered_at'] for e in store.read_json(store.evidence_path)):
        ec._ledger_append(store, index, dict(kind='gate_answer', question_id=rec['question_id'],
            trace_id=index['trace_id'], engine_version=ec.ENGINE_VERSION, node=rec['node'], visit=rec['visit'],
            at=auth['answered_at'], answered_at=auth['answered_at'], delivered_at=delivered,
            answered_by=auth['answered_by'], chosen_intent=auth['chosen_intent'], resolution_kind=resolution,
            human_wait_ms=wait))


def orphan_stop(store, index):
    """Read-only validation of the same interrupted fence/menu that reinstall accepts."""
    ec = _ec()
    from . import dispatch_budget
    if index['run_state'] not in ('RUNNING', 'WAITING_USER'):
        return None
    orphan = dispatch_budget.unindexed_record(store, index)
    if not orphan or not orphan[1].get('identity_handoff'):
        return None
    qid, rec = orphan
    try:
        data = rec['identity_handoff']
        options = rec.get('options')
        if rec.get('question_id') != qid or set(rec) != dispatch_budget._STOP_FIELDS | {'identity_handoff'} \
                or not isinstance(data, dict) or set(data) != {'fence_ref', 'checkpoint_sha256',
                    'business_question_id', 'business_record_sha256'} \
                or (data.get('business_question_id') is not None and not isinstance(data['business_question_id'], str)) \
                or rec.get('source') != 'hsaw_doubt' or rec.get('kind') != 'choice' \
                or rec.get('dispatch_block') != 'ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE' \
                or rec.get('recommendation') != 'identity_inspect' or rec.get('prompt_text') is not None \
                or rec.get('consumed_by_commit') is not True or type(rec.get('visit')) is not int \
                or not all(isinstance(rec.get(k), str) for k in ('node', 'question', 'advice', 'explanation', 'closing')) \
                or not isinstance(options, list) or not all(isinstance(row, dict)
                    and set(row) == {'kind', 'intent', 'label', 'note'}
                    and all(isinstance(row[k], str) for k in ('kind', 'intent', 'label', 'note')) for row in options):
            raise ValueError('Interrupted handover record differs from its writer frame')
        fence = _read_ref(store, data['fence_ref'])
        _, dispatch = _owner(index)
        if not dispatch_budget._matches_run(store, index, rec, dispatch_budget._ANSWER_FIELDS) \
                or rec['previous_status'] != index['nodes'][ec._node_key(rec['node'], rec['visit'])]['status'] \
                or not dispatch or fence['ticket'] != dispatch['ticket'] \
                or fence['scope_root'] != dispatch.get('scope_root') or fence['trace_id'] != index['trace_id'] \
                or fence['question_id'] != qid or fence['checkpoint'] != snapshot(store, index) \
                or _digest(fence['checkpoint']) != rec['identity_handoff']['checkpoint_sha256']:
            raise ValueError('Interrupted handover does not match the unchanged checkpoint')
        source_id = data['business_question_id']
        if source_id != fence.get('business_question_id'):
            raise ValueError('Interrupted handover business binding changed')
        if source_id:
            business = store.read_json(store.gate_path(source_id))
            if _ref(store, store.gate_path(source_id).name)['sha256'] != data['business_record_sha256']:
                raise ValueError('Interrupted handover business record changed')
            intents = [f'identity_business_{i}' for i in range(1, len(business['options']) + 1)]
            kinds = [row['kind'] for row in _business_options(index, business)]
        else:
            if data['business_record_sha256'] is not None:
                raise ValueError('Interrupted handover has an unrelated business digest')
            exhausted = same_progress_claims(dispatch, fence['checkpoint']['progress_key']) > ec.DISPATCH_ATTEMPTS_MAX
            intents = [] if exhausted else ['identity_continue']
            kinds = ['execute'] * len(intents)
        intents += ['identity_inspect', 'identity_stop']
        kinds += ['execute', 'cancel']
        if [row['intent'] for row in options] != intents \
                or [row['kind'] for row in options] != kinds:
            raise ValueError('Interrupted handover option frame changed')
        try:
            _check_authority(store, rec, fence)
        except (ValueError, KeyError, OSError):
            return None
        if not dispatch_budget._renders(store, index, rec):
            raise ValueError('Interrupted handover cannot be rendered read-only')
    except (ValueError, KeyError, OSError) as exc:
        raise ec.EngineError('DISPATCH_REPLACEMENT_INVALID', str(exc)) from exc
    return rec


def _land(store, index, rec):
    ec = _ec()
    from . import dispatch_budget
    fence = _read_ref(store, rec['identity_handoff']['fence_ref'])
    _, dispatch = _owner(index)
    dispatch.update(state='ABANDONED', closed_reason='identity_unverified', closed_at=fence['at'])
    dispatch_budget._install(index, rec, rec['presented_at'])
    ec._write_index(store, index)


def reinstall(store, index):
    """Recover an unchanged, unshown fence/menu write without issuing a right."""
    rec = orphan_stop(store, index)
    if rec is None:
        return False
    _land(store, index, rec)
    return True


def recover_answer(store, index):
    """Finish a recorded answer, including after the business index already landed."""
    if index['run_state'] not in ('RUNNING', 'WAITING_USER'):
        return False
    for row in reversed(index['gate']['history']):
        rec = store.read_json(store.gate_path(row['question_id']))
        if not rec.get('identity_handoff') or row.get('answered_at'):
            continue
        if store.exists_path(_authorization_path(store, rec['question_id'])):
            finish_answer(store, index, rec)
            return True
        source_id = rec['identity_handoff'].get('business_question_id')
        source = store.read_json(store.gate_path(source_id)) if source_id else None
        if source and source.get('resolution_kind') == 'free_text' \
                and source.get('delivered_via_question_id') == rec['question_id']:
            _finish_conditional(store, index, rec, source)
            return True
    return False


def answer(store, index, rec, text, by):
    ec = _ec()
    _guard_authority(store, rec)
    if ec._unshown_stop(store, index, rec):
        return ec._not_shown(rec)
    path = _authorization_path(store, rec['question_id'])
    if store.exists_path(path):
        # The original durable choice wins over new text at every re-entry.
        try:
            checkpoint_index = dict(index, current=dict(name=rec['node'], visit=rec['visit']))
            _validate_fence(store, checkpoint_index, rec)
        except (ValueError, KeyError, OSError) as exc:
            raise ec.EngineError('DISPATCH_REPLACEMENT_INVALID', str(exc)) from exc
        result = finish_answer(store, index, rec)
        option = ec._match_option(rec['options'], (text or '').strip())
        same = option is not None and option['intent'] == rec['chosen_intent']
        label = rec['chosen_label']
        result['answer_hint'] = _text(index,
            f'你先前在这道题上的答复「{label}」已经按记下的样子处理完了' + ('。' if same else '；你这次的回复没有采用。'),
            f'Your earlier answer to this stop ({label}) has now been completed as recorded' +
            ('.' if same else '; your new reply was not taken.'))
        return result
    option = ec._match_option(rec['options'], (text or '').strip())
    if option is None:
        source_id = rec['identity_handoff']['business_question_id']
        source = store.read_json(store.gate_path(source_id)) if source_id else None
        if source and source.get('conditional_reply') and (text or '').strip() and not (text or '').strip().isdigit():
            delivery = _delivery(index, rec, ec.now_iso())
            history = copy.deepcopy(index['gate']['history'])
            index['gate'] = copy.deepcopy(rec['previous_gate'])
            index['gate']['history'] = history
            program = ec._load_routed_program(ec._read_run_input(store))
            result = ec._answer_locked(store, index, program, source_id, text, by,
                                       _delivery=delivery)
            index = store.read_index()
            _finish_conditional(store, index, rec, store.read_json(store.gate_path(source_id)))
            return result
        rec.setdefault('invalid_answers', []).append(dict(at=ec.now_iso(), text=(text or '').strip(),
                                                         text_original=text or '', answered_by=by))
        ec._write_json(store.gate_path(rec['question_id']), rec)
        return dict(status='WAITING_USER', question_id=rec['question_id'], run_state='WAITING_USER', reason='INVALID_ANSWER',
                    answer_valid=False, public_prompt_ref=ec._ref(store, f"menu.{rec['question_id']}.txt"))
    if option['intent'] == 'identity_inspect':
        try:
            fence = _validate_fence(store, index, rec)
        except (ValueError, KeyError, OSError) as exc:
            raise ec.EngineError('DISPATCH_REPLACEMENT_INVALID', str(exc)) from exc
        return dict(status='WAITING_USER', question_id=rec['question_id'], run_state='WAITING_USER',
                    answer_valid=True, conditions_satisfied=False, authorization=False,
                    answer_hint=f"Checkpoint {rec['identity_handoff']['checkpoint_sha256']}; old ticket {fence['ticket']}; "
                                f"accepted caches {len(fence['checkpoint']['accepted'])}; external execution UNKNOWN. "
                                'Paused without answering the business question or authorizing a new agent.',
                    evidence_ref=rec['identity_handoff']['fence_ref'],
                    public_prompt_ref=ec._ref(store, f"menu.{rec['question_id']}.txt"))
    try:
        _validate_fence(store, index, rec)
    except (ValueError, KeyError, OSError) as exc:
        raise ec.EngineError('DISPATCH_REPLACEMENT_INVALID', str(exc)) from exc
    business_id = rec['identity_handoff']['business_question_id']
    business_choice = None
    if business_id and option['intent'] != 'identity_stop':
        business = store.read_json(store.gate_path(business_id))
        if _ref(store, store.gate_path(business_id).name)['sha256'] != rec['identity_handoff']['business_record_sha256']:
            raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'The original business question changed.')
        number = int(option['intent'].removeprefix('identity_business_'))
        business_choice = copy.deepcopy(business['options'][number - 1])
    value = dict(schema_version=1, question_id=rec['question_id'], trace_id=index['trace_id'],
        fence_ref=rec['identity_handoff']['fence_ref'], checkpoint_sha256=rec['identity_handoff']['checkpoint_sha256'],
        answer_text_original=text, answered_by=by, answered_at=ec.now_iso(),
        delivered_at=rec.get('delivered_at') or index['gate'].get('delivered_at'),
        chosen_intent=option['intent'], business_question_id=business_id, business_choice=business_choice)
    path = _authorization_path(store, rec['question_id'])
    if not store.exists_path(path):
        store.write_json_once(path, value)
    else:
        saved = store.read_json(path)
        if saved.get('answer_text_original') != text or saved.get('answered_by') != by:
            raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'A different answer is already recorded.')
    return finish_answer(store, index, rec)


def finish_answer(store, index, rec):
    ec = _ec()
    _guard_authority(store, rec)
    auth = store.read_json(_authorization_path(store, rec['question_id']))
    option = _check_answer(index, rec, auth)
    if option['intent'] == 'identity_stop':
        _own_wait(store, index, rec, auth, 'terminate')
        rec.update(answered_at=auth['answered_at'], answer_text=auth['answer_text_original'],
                   answer_text_original=auth['answer_text_original'], answered_by=auth['answered_by'],
                   resolution_kind='terminate', chosen_intent='identity_stop', chosen_label=option['label'])
        ec._write_json(store.gate_path(rec['question_id']), rec)
        row = next(r for r in index['gate']['history'] if r['question_id'] == rec['question_id'])
        row.update(answered_at=auth['answered_at'], resolution_kind='terminate')
        ec.close_dispatch_tickets(store, index, f"human_terminate:{rec['question_id']}")
        index['gate']['state'] = 'CLEAR'
        for ticket in index['tickets']:
            if ticket['state'] == 'READY':
                ticket['state'] = 'RETIRED'
        ec._terminate(index, kind='human_termination', by='human', reason=f"user terminated at {rec['question_id']}")
        ec._write_index(store, index)
        return dict(status='TERMINATED', run_state=index['run_state'], question_id=rec['question_id'],
                    identity_handover_authorized=False)
    business_id = auth['business_question_id']
    history = copy.deepcopy(index['gate']['history'])
    if business_id:
        business = store.read_json(store.gate_path(business_id))
        if auth['business_choice'] not in business['options']:
            raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Joint authorization does not name an original business choice.')
        consumed = next(t for t in index['tickets'] if t['question_id'] == business_id)['state'] != 'READY'
        if not consumed:
            recorded = business if business.get('answered_at') else None
            if recorded and (recorded.get('chosen_intent') != auth['business_choice']['intent']
                    or recorded.get('answer_text_original') != auth['answer_text_original']
                    or recorded.get('answered_by') != auth['answered_by']):
                raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Recorded business answer conflicts with the joint choice.')
            index['gate'] = copy.deepcopy(rec['previous_gate'])
            index['gate']['history'] = history
            program = ec._load_routed_program(ec._read_run_input(store))
            result = ec._answer_locked(store, index, program, business_id, auth['answer_text_original'],
                                       auth['answered_by'], _choice=auth['business_choice'], _recorded=recorded,
                                       _delivery=dict(question_id=rec['question_id'], delivered_at=auth.get('delivered_at'),
                                                      answered_at=auth['answered_at']))
            index.clear()
            index.update(store.read_index())
        else:
            if business.get('chosen_intent') != auth['business_choice']['intent'] or any(
                    business.get(key) != auth.get(key) for key in ('answer_text_original', 'answered_by', 'answered_at')):
                raise ec.EngineError('HUMAN_REPLY_BINDING_INVALID', 'Business answer conflicts with the joint choice.')
            result = dict(status='ANSWERED', run_state=index['run_state'])
    else:
        _own_wait(store, index, rec, auth, 'chosen')
        index['gate'] = copy.deepcopy(rec['previous_gate'])
        index['gate']['history'] = history
        index['gate']['state'] = 'CLEAR'
        index['nodes'][ec._node_key(rec['node'], rec['visit'])]['status'] = rec['previous_status']
        index['run_state'] = 'RUNNING'
        result = dict(status='ANSWERED', run_state='RUNNING')
    _, dispatch = _owner(index)
    fence = _read_ref(store, auth['fence_ref'])
    if dispatch and dispatch['ticket'] == fence['ticket']:
        dispatch.update(state='ABANDONED', closed_reason='identity_unverified')
    rec.update(answered_at=auth['answered_at'], answer_text=auth['answer_text_original'],
        delivered_at=auth.get('delivered_at'),
        answer_text_original=auth['answer_text_original'], answered_by=auth['answered_by'],
        resolution_kind='chosen', chosen_intent=auth['chosen_intent'], chosen_label=option['label'])
    ec._write_json(store.gate_path(rec['question_id']), rec)
    row = next((r for r in index['gate']['history'] if r['question_id'] == rec['question_id']), None)
    if row:
        row.update(answered_at=auth['answered_at'], resolution_kind='chosen')
    _consume_question(index, rec['question_id'])
    ec._write_index(store, index)
    result.update(question_id=rec['question_id'], identity_handover_authorized=option['kind'] == 'execute')
    return result


def authority(store, index, dispatch):
    if not dispatch or dispatch.get('closed_reason') != 'identity_unverified':
        return None
    for row in reversed(index['gate']['history']):
        rec = store.read_json(store.gate_path(row['question_id']))
        data = rec.get('identity_handoff')
        if not data:
            continue
        try:
            fence = _read_ref(store, data['fence_ref'])
            if fence['ticket'] != dispatch['ticket']:
                continue
            if not store.exists_path(_authorization_path(store, rec['question_id'])):
                return None
            auth = store.read_json(_authorization_path(store, rec['question_id']))
            option = _check_answer(index, rec, auth, answered=True)
            if option['kind'] != 'execute':
                return None
            _validate_fence(store, index, rec)
            business_id = auth['business_question_id']
            if business_id:
                business = store.read_json(store.gate_path(business_id))
                if auth['business_choice'] not in business['options'] or business.get('chosen_intent') != auth['business_choice']['intent'] \
                        or any(business.get(key) != auth.get(key) for key in ('answer_text_original', 'answered_by', 'answered_at')):
                    raise _ec().EngineError('HUMAN_REPLY_BINDING_INVALID', 'Business and joint answers disagree.')
            if not rec.get('answered_at') or auth['answered_at'] != rec['answered_at'] \
                    or auth['chosen_intent'] != rec['chosen_intent'] \
                    or auth['chosen_intent'] in ('identity_inspect', 'identity_stop') \
                    or auth['question_id'] != rec['question_id'] or auth['trace_id'] != index['trace_id'] \
                    or auth['checkpoint_sha256'] != data['checkpoint_sha256']:
                return None
            progress = snapshot(store, index)['progress_key']
            if same_progress_claims(dispatch, progress) > _ec().DISPATCH_ATTEMPTS_MAX:
                raise _ec().EngineError('ORIGINAL_EXECUTOR_CONTINUATION_EXHAUSTED', 'Same-progress handover failure bound reached.')
            return dict(fence_ref=data['fence_ref'], authorization_ref=_ref(store, _authorization_path(store, rec['question_id']).name),
                        progress_key=progress, previous_ticket=dispatch['ticket'], question_id=rec['question_id'])
        except (ValueError, KeyError, OSError) as exc:
            raise _ec().EngineError('DISPATCH_REPLACEMENT_INVALID', str(exc)) from exc
    return None


def same_progress_claims(dispatch, progress):
    return sum(1 for row in [dispatch, *(dispatch.get('history') or [])]
               if row.get('identity_handoff', {}).get('progress_key') == progress and row.get('claimed_at'))


def verify_ticket(store, index, dispatch):
    ec = _ec()
    from . import dispatch_prepare
    try:
        proof = dispatch['identity_handoff']
        auth = _read_ref(store, proof['authorization_ref'])
        fence = _read_ref(store, proof['fence_ref'])
        formal = store.read_json(store.dispatch_path(dispatch['ticket']))
        owner_key, owner = _owner(index)
        if not owner or owner.get('ticket') != dispatch['ticket']:
            raise ValueError('Identity handover does not own the current root')
        dispatch_prepare.verify(store, index, dispatch['ticket'], formal,
                               dict(dispatch, _owner_key=owner_key))
        if formal.get('reason') != dispatch.get('reason'):
            raise ValueError('Identity handover ticket reason changed')
        # Bind the first claim to the approved cursor and accepted bytes, not later legitimate progress.
        if dispatch.get('state') == 'ISSUED':
            current = index['current']
            if formal.get('node') != current['name'] or formal.get('visit') != current['visit'] \
                    or snapshot(store, index)['accepted'] != fence['checkpoint']['accepted']:
                raise ValueError('Identity handover checkpoint changed before claim')
        if formal.get('identity_handoff') != proof or auth['question_id'] != proof['question_id'] \
                or auth['trace_id'] != index['trace_id'] or fence['trace_id'] != index['trace_id'] \
                or auth['fence_ref'] != proof['fence_ref'] or fence['ticket'] != proof['previous_ticket'] \
                or fence['scope_root'] != dispatch['scope_root'] or dispatch.get('resume_executor') \
                or formal.get('resume_executor') \
                or auth['chosen_intent'] in ('identity_stop', 'identity_inspect'):
            raise ValueError('Identity handover authority changed')
        gate = store.read_json(store.gate_path(auth['question_id']))
        _check_authority(store, gate, fence)
        option = _check_answer(index, gate, auth, answered=True)
        if option['kind'] != 'execute':
            raise ValueError('A cancellation does not authorize an identity handover ticket'
                             if option['kind'] == 'cancel' else 'A non-executing choice does not authorize an identity handover ticket')
    except (ValueError, KeyError, OSError) as exc:
        raise ec.EngineError('DISPATCH_REPLACEMENT_INVALID', str(exc)) from exc


def claimed_stand_ins(index, pool):
    total = 0
    for node in index['nodes'].values():
        dispatch = node.get('dispatch') or {}
        charged = False
        for row in [*(dispatch.get('history') or []), dispatch]:
            if row.get('pool', 'ordinary') != pool or not row.get('claimed_at'):
                continue
            if row.get('identity_handoff') and charged:
                total += 1
            charged = True
    return total
