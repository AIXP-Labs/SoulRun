"""Keep pre-work, subgraph work and post-work in one node occurrence."""
import copy
from pathlib import Path
import re
import time
from . import aisop_parse, program_loader
from .run_store import dumps, sha256_bytes, _regular_path, now_iso


def boundary(program, entry, view):
    module = (view or {}).get('module')
    if not module:
        return None
    for pos, step in enumerate(view['steps']):
        work = (step.get('assert') or {}).get('work') or step['text']
        target = step.get('sub_task')
        call = None
        if isinstance(work, str) and not target:
            call = aisop_parse.DELEGATE_STEP_RE.search(work)
            target = aisop_parse.module_target_of_step(work) if call else None
            if not target:
                bare = re.match(r'(?:Delegate\s+to|委托|进入)\s+([A-Za-z0-9_][\w.-]*)', work.strip(), re.I)
                target = bare.group(1) if bare else None
        if not target:
            continue
        resolved = program_loader.resolve_module(program, entry.get('doc') or program.entry_file, target)
        if resolved and all(resolved.get(k) == module.get(k) for k in ('doc','task','entry_node')):
            within = bool(call and work[:call.start()].strip(' .;|'))
            return dict(pre_steps=[s['key'] for s in view['steps'][:pos]], call_step=step['key'],
                within_step=within, pre_text=work[:call.start()] if within else '',
                post_text=work[call.start():] if within else '', needs_prefix=bool(pos or within))
    # Legacy label-only wrappers have no explicit pre/call boundary to reorder.
    return None


def pending(index, entry, visit, plan):
    from . import engine_core as ec
    state = index['nodes'].get(ec._node_key(entry['name'], visit)) or {}
    return bool(plan and plan['needs_prefix'] and not state.get('module') and not state.get('module_prefix'))


def validate(store, index, program, entry, visit, view, payload):
    from . import engine_core as ec
    control = payload.get('module_control')
    plan = boundary(program, entry, view)
    is_pending = pending(index, entry, visit, plan)
    if not control:
        if is_pending and not payload.get('gate') and payload['status'] != 'FAIL':
            raise ec.EngineError('MODULE_PREFIX_REQUIRED', 'Pre-work must be accepted before opening this subgraph.', field='module_control')
        return None
    if payload.get('gate') or not is_pending:
        raise ec.EngineError('MODULE_PREFIX_INVALID', 'Module control only applies before this occurrence opens its subgraph.', field='module_control')
    if control['action'] == 'skip':
        verify_cache(store, index, program, entry, visit, view, control, payload)
        if payload['steps']['remaining'] or plan['call_step'] not in payload['steps']['not_applicable']:
            raise ec.EngineError('MODULE_SKIP_INVALID', 'A verified cache skip still completes own work and marks the call not applicable.')
        return dict(state='SKIPPED', **{k:plan[k] for k in ('pre_steps','call_step','within_step')})
    if not plan['call_step']:
        raise ec.EngineError('MODULE_BOUNDARY_AMBIGUOUS', 'The label has no explicit call step; declare the order or use a real doubt gate.')
    if any(s['key'] in plan['pre_steps'] and (s.get('sub_task') or s.get('delegate_file')) for s in view['steps']):
        raise ec.EngineError('MODULE_BOUNDARY_AMBIGUOUS', 'Multiple module calls need distinct graph nodes; do not claim an untracked earlier subgraph.')
    if payload['status'] != 'PARTIAL' or set(payload['steps']['done']) != set(plan['pre_steps']) \
            or payload['steps']['not_applicable'] or payload.get('next_hint'):
        raise ec.EngineError('MODULE_PREFIX_INVALID', 'Enter uses PARTIAL, exactly the pre-steps done, and call/post steps remaining.')
    return dict(state='ACCEPTED', **{k:plan[k] for k in ('pre_steps','call_step','within_step')})


def cache_path(program, policy):
    value = (policy or {}).get('path')
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else program.dir/path


def capture_cache(store, index, program, entry, visit, view):
    from . import engine_core as ec
    from . import dispatch_budget
    if dispatch_budget.pool(program,entry) == 'independent':
        return False
    state = index['nodes'][ec._node_key(entry['name'], visit)]
    if state.get('module_cache_observation'):
        return False
    policy = view['extra'].get('module_cache')
    path = cache_path(program, policy)
    if path is None:
        return False
    if not path.resolve().is_relative_to(program.dir.resolve()) or not _regular_path(path):
        raise ec.EngineError('MODULE_SKIP_INVALID', 'Declared cache must remain a regular path in the program directory.')
    raw = store.read_bytes(path) if path.exists() else None
    state['module_cache_observation'] = dict(path=str(path.resolve()),
        sha256=sha256_bytes(raw) if raw is not None else 'ABSENT',
        mtime_ns=path.stat().st_mtime_ns if raw is not None else None,
        binding=cache_bindings(store,index,view))
    return True


def verify_cache(store, index, program, entry, visit, view, control, payload):
    from . import engine_core as ec
    policy = view['extra'].get('module_cache')
    from . import dispatch_budget
    if dispatch_budget.pool(program, entry) == 'independent':
        raise ec.EngineError('MODULE_SKIP_INVALID', 'An independent review cannot be replaced by a cached result.')
    if not isinstance(policy, dict) or type(policy.get('ttl_seconds')) is not int or policy['ttl_seconds'] <= 0:
        raise ec.EngineError('MODULE_SKIP_UNDECLARED', 'The program must explicitly declare a deterministic module_cache policy.')
    path = cache_path(program, policy)
    observed = index['nodes'][ec._node_key(entry['name'], visit)].get('module_cache_observation') or {}
    requested = Path(control.get('cache_ref') or '')
    if not requested.is_absolute():
        requested = program.dir/requested
    raw = store.read_bytes(path) if path and path.exists() else None
    if path is None or path.resolve() != requested.resolve() or not _regular_path(path) \
            or observed.get('path') != str(path.resolve()) or observed.get('sha256') in (None,'ABSENT') \
            or raw is None or sha256_bytes(raw) != observed['sha256'] \
            or path.stat().st_mtime_ns != observed['mtime_ns']:
        raise ec.EngineError('MODULE_SKIP_INVALID', 'Only the declared, pre-existing cache observed before pre-work may skip a subgraph; changed/new cache rejected.')
    from .run_store import strict_loads
    cached = strict_loads(raw.decode('utf-8'))
    age = time.time()-path.stat().st_mtime
    module = view['module']
    module_path = program.dir/module['doc']
    bindings = cache_bindings(store,index,view)
    if cached.get('schema_version') != 1 or not 0 <= age < policy['ttl_seconds'] \
            or cached.get('input_sha256') != sha256_bytes((store.cache_dir/'_run_input.json').read_bytes()) \
            or cached.get('module_sha256') != sha256_bytes(module_path.read_bytes()) \
            or cached.get('call_sha256') != bindings['call_sha256'] \
            or cached.get('upstream_sha256') != bindings['upstream_sha256'] \
            or cached.get('output') != payload['output']:
        raise ec.EngineError('MODULE_SKIP_INVALID', 'Cache age, original input, module bytes or output binding failed.')


def cache_bindings(store, index, view):
    from . import engine_core as ec
    inputs = []
    for done in index['completed']:
        entry = ec._catalog_entry(index, done['name'])
        if entry['kind'] not in ('business','sub'):
            continue
        path = ec._cache_path_for(store,index,entry,done['visit'])
        raw = store.read_bytes(path)
        if sha256_bytes(raw) != index['nodes'][ec._node_key(done['name'],done['visit'])]['cache_sha256']:
            raise ec.EngineError('CONTINUATION_EVIDENCE_CHANGED', 'An upstream cache used in the skip binding changed.')
        value = ec._latest_payload(store.read_json(path))
        inputs.append(dict(node=done['name'], output=value['output'], vars=value.get('vars')))
    decisions = [{k:r.get(k) for k in ('node','chosen_intent','answer_text_original','answer_text','chosen_label')}
                 for r in ec._human_decisions(store,index,ec.NODE_REPORT,0)]
    return dict(call_sha256=sha256_bytes(dumps(dict(module=view['module'],steps=view['steps'])).encode()),
        upstream_sha256=sha256_bytes(dumps(dict(inputs=inputs,context=index['context'],human_decisions=decisions)).encode()))


def prefix_record(store, index, entry, visit):
    from . import engine_core as ec
    state = index['nodes'].get(ec._node_key(entry['name'], visit)) or {}
    if not state.get('module_prefix'):
        return None
    path = ec._cache_path_for(store, index, entry, visit)
    raw = store.read_bytes(path)
    if sha256_bytes(raw) != state['cache_sha256']:
        raise ec.EngineError('CONTINUATION_EVIDENCE_CHANGED', 'Accepted module pre-work changed.')
    cache = store.read_json(path)
    records = [r for r in [cache, *(cache.get('continuations') or [])] if r['machine'].get('module_prefix')]
    if len(records) != 1:
        raise ec.EngineError('MODULE_PREFIX_INVALID', 'Expected one accepted module prefix in this occurrence.')
    return cache, records[0]


def attach(store, index, program, entry, visit, reply):
    from . import engine_core as ec
    from . import contracts as _contracts
    view = ec._view_for(program, entry)
    plan = boundary(program, entry, view)
    if not plan:
        return
    saved = prefix_record(store, index, entry, visit)
    if pending(index, entry, visit, plan):
        reply['module_execution'] = dict(phase='PRE_WORK', **plan,
            all_step_keys=[s['key'] for s in view['steps']],
            rule='Execute only pre-steps and work before the call inside call_step. Do not open/re-run the subgraph or do post-work. '
                 'Commit PARTIAL with module_control.action=enter, pre-steps done and call/post remaining. '
                 'A human doubt still uses HSAW; a cache skip needs a program-declared module_cache policy and bound file.')
        reply['payload_skeleton'].update(status='PARTIAL', module_control=dict(action='enter'),
            steps=dict(done=plan['pre_steps'], remaining=[s['key'] for s in view['steps'] if s['key'] not in plan['pre_steps']], not_applicable=[]))
        executable = []
        for step in reply['steps']:
            if step['key'] in plan['pre_steps']:
                executable.append(step)
            elif step['key'] == plan['call_step'] and plan['within_step']:
                executable.append(dict(step, text=plan['pre_text'], partial_step=True))
        reply['steps'] = executable
        reply['deferred_step_keys'] = reply['payload_skeleton']['steps']['remaining']
        reply['payload_rules'].insert(0, reply['module_execution']['rule'])
        reply['payload_rules'][0] = _contracts.text('module-order.prefix')
        reply['node_facts']['accepted_keys'].append('module_control')
        for pos, rule in enumerate(reply['payload_rules']):
            if getattr(rule,'key',None)=='core.top_level_keys':
                reply['payload_rules'][pos]=_contracts.text(rule.key,_facts=ec._FACT_POINTERS[rule.key],
                    accepted=', '.join(reply['node_facts']['accepted_keys']))
        prefix_view = pre_view(view,program,entry)
        reply['delivery_obligations'] = ec.delivery_obligations.obligations(prefix_view)
        reply['gate'].update(ec._gate_summary(prefix_view['gate_sources']))
        skeleton = reply['payload_skeleton']
        unanswered = reply['gate']['required'] and not reply['input_authority'].get('gate_answer')
        reply['module_execution']['submission_kind'] = 'PAUSE_GATE' if unanswered else 'ENTER_MODULE'
        if unanswered:
            skeleton.pop('module_control', None)
            keys = [s['key'] for s in view['steps']]
            positions = [keys.index(g['step']) if g.get('step') in keys else 0
                         for g in prefix_view['gate_sources'] if g.get('required')]
            stop = min(positions, default=0)
            done = [key for key in plan['pre_steps'] if keys.index(key) < stop]
            skeleton['steps'] = dict(done=done, remaining=[key for key in keys if key not in done], not_applicable=[])
            reply['deferred_step_keys'] = skeleton['steps']['remaining']
        else:
            skeleton.pop('gate', None)
        if not reply['gate']['required'] and not reply['gate']['advisory']:
            reply['payload_rules'] = [r for r in reply['payload_rules']
                                     if getattr(r, 'key', None) not in ('gate.declared', 'gate.stream')]
        observed = index['nodes'][ec._node_key(entry['name'],visit)].get('module_cache_observation')
        if observed:
            reply['module_execution']['cache_binding'] = observed['binding']
    elif saved:
        cache, prefix = saved
        reply['module_execution'] = dict(phase='POST_WORK', **plan, accepted_pre_steps=prefix['payload']['steps']['done'],
            pre_output=ec._clip_output(prefix['payload']['output'])[0], pre_output_is_preview=True,
            input_ref=ec._input_refs(store, index, [cache])[0]['ref'],
            rule='Accepted pre-work and the closed subgraph must not repeat. Finish only post-work; close all original step keys cumulatively.')
        reply['payload_rules'].insert(0,_contracts.text('module-order.post'))
        observed = index['nodes'][ec._node_key(entry['name'],visit)].get('module_cache_observation')
        if observed:
            reply['module_execution']['cache_binding'] = observed['binding']
        suffix_view = post_view(store,index,program,entry,visit,view)
        reply['gate'].update(ec._gate_summary(suffix_view['gate_sources']))
        reply['delivery_obligations'] = ec.delivery_obligations.obligations(suffix_view)
        if prefix.get('gate_answer'):
            reply['module_execution']['pre_gate_answer'] = prefix['gate_answer']
        for step in reply['steps']:
            if step['key'] in prefix['payload']['steps']['done']:
                step['accepted_before_module'] = True


def input_allowed(index, node, visit):
    from . import engine_core as ec
    if not isinstance(node,str) or type(visit) is not int or visit < 1:
        return False
    current = index.get('current') or {}
    state = index['nodes'].get(ec._node_key(node, visit)) or {}
    if not state.get('module_prefix'):
        return False
    return (current == dict(name=node, visit=visit) or any(f['parent'] == node and f['parent_visit'] == visit
                                                        for f in index.get('call_stack', [])))


def pre_view(view, program, entry):
    described = copy.deepcopy(view)
    plan = boundary(program, entry, view)
    steps = []
    for step in described['steps']:
        if step['key'] in plan['pre_steps']:
            steps.append(step)
        elif step['key'] == plan['call_step'] and plan['within_step']:
            steps.append(aisop_parse.describe_step(step['key'], plan['pre_text']))
    described['steps'] = steps
    described['gate_sources'] = aisop_parse.scan_gate_sources(described)
    return described


def post_view(store, index, program, entry, visit, view):
    saved = prefix_record(store,index,entry,visit)
    if not saved:
        return view
    _, record = saved
    plan = boundary(program,entry,view)
    described = copy.deepcopy(view)
    described['steps'] = [aisop_parse.describe_step(s['key'],plan['post_text'])
        if s['key'] == plan['call_step'] and plan['within_step'] else s
        for s in described['steps'] if s['key'] not in plan['pre_steps']]
    if record.get('gate_answer'):
        described['reserved'].pop('user_gate',None)
    described['gate_sources'] = aisop_parse.scan_gate_sources(described)
    return described


def attach_parent(store, index, program, frame, reply):
    from . import engine_core as ec
    entry = ec._catalog_entry(index, frame['parent'])
    saved = prefix_record(store, index, entry, frame['parent_visit'])
    if saved:
        cache, record = saved
        reply['input_authority']['parent_prefix'] = dict(node=entry['name'], visit=frame['parent_visit'],
            output=ec._clip_output(record['payload']['output'])[0], output_is_preview=True,
            input_ref=ec._input_refs(store, index, [cache])[0]['ref'],
            rule='Accepted same-occurrence pre-work, not a completed parent result. Read needed full input with this bound ref; never repeat it.')
        reply['frame']['note'] = 'Accepted parent pre-work precedes this subgraph; remaining parent work follows its end. Read only the bound parent_prefix and authorized input refs.'


def apply_prefix(store, index, entry, visit, payload, cache, cache_path, machine):
    from . import engine_core as ec, dispatch_lifecycle, dispatch_scope
    key = ec._node_key(entry['name'], visit)
    state = index['nodes'][key]
    state.update(status='ACTIVE', cache_sha256=sha256_bytes(store.read_bytes(cache_path)),
        module_prefix=copy.deepcopy(machine['module_prefix']),
        logical_tool_calls=ec._node_evidence(cache)['counts']['declared_entries'],
        artifacts=machine.get('artifacts', []), sources_count=len(payload['evidence']['sources']))
    _, dispatch = ec._self_dispatch(index, entry, visit)
    result_dispatch = None
    if dispatch and dispatch.get('ticket'):
        dispatch_lifecycle.progress(store, dispatch, machine['committed_at'], preserve_equal=True)
        result_dispatch = dict(ticket=dispatch['ticket'], actor='sub_agent', closed=False, reason='module_prefix',
                               **dispatch_scope.view(dispatch, include_refs=False))
    ec._ledger_append(store, index, ec._ledger_commit_event(index, entry, visit, len(cache.get('continuations') or []),
                                                          payload, machine, kind='commit'))
    block, reference = None, None
    if payload['user_messages']:
        block = ec.render.robot_frame('\n\n'.join(payload['user_messages']), index.get('user_language'))
        name = f"prefix.{entry['ordinal']+1:02d}.{ec._safe_name(entry['name'])}.v{visit}.txt"
        store.write_public(name, block)
        reference = ec._ref(store, name)
        if dispatch and dispatch.get('scope_root'):
            dispatch_scope.append_ref(dispatch, reference)
    return dict(public_block=block, public_block_ref=reference, gate=None, errors=[],
        next=dict(node=entry['name'], kind=entry['kind']), dispatch=result_dispatch,
        module_execution=dict(phase='PRE_WORK_ACCEPTED', node_complete=False,
            rule='Same occurrence, original executor; open the declared subgraph next. Do not repeat accepted pre-work.'))
