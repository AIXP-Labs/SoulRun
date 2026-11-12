"""Read-only actual gate history for opt-in writers, never a semantic grant."""
import copy
import json


def read(cache_dir, *, agent_ticket=None):
    from . import blind_review, engine_core as ec, independent_inputs, render, stop_state
    from .run_store import RunStore, strict_loads

    store = RunStore(cache_dir)
    index = ec._read_input_authority(store, agent_ticket)
    ec.program_guard.assert_run_version(index)
    if stop_state.stop_fence(cache_dir) is not None or index['gate']['state'] != 'CLEAR':
        raise ec.EngineError('WRITE_AUTHORITY_UNAVAILABLE', 'A stopped or waiting run cannot authorize a write.')
    if blind_review.active(store, index) or independent_inputs.active(store, index):
        raise ec.EngineError('WRITE_AUTHORITY_FORBIDDEN', 'Independent review/scoped executors cannot read the parent gate history.')
    run_input = ec._read_run_input(store)
    program = ec._load_routed_program(run_input)
    entry = ec._catalog_entry(index, index['current']['name'])
    view = ec._view_for(program, entry) if program is not None and entry is not None else None
    if entry is None or entry['kind'] not in ('business', 'sub') or (view or {}).get('extra', {}).get('write_scope_reader') is not True:
        raise ec.EngineError('WRITE_AUTHORITY_FORBIDDEN', 'Only a bound program node explicitly declaring write_scope_reader=true may read.')
    raw_input, input_meta = blind_review._bytes(store.cache_dir / ec.RUN_INPUT)
    if strict_loads(raw_input.decode('utf-8')) != run_input:
        raise ec.EngineError('WRITE_AUTHORITY_CHANGED', 'Run input changed or requires a legacy projection; no fallback.')
    entry_path = program.dir / program.entry_file
    raw_program, program_meta = blind_review._bytes(entry_path)
    binding = dict(trace_id=index['trace_id'], program_entry=str(entry_path.resolve()),
                   program_sha256=program_meta['sha256'],
                   request_sha256=ec.sha256_bytes(run_input['user_message'].encode('utf-8')))
    ledger_raw, ledger_meta = blind_review._bytes(store.evidence_path)
    events = strict_loads(ledger_raw.decode('utf-8'))
    if ec.ledger_errors(events):
        raise ec.EngineError('WRITE_AUTHORITY_INVALID', 'The actual evidence ledger cannot be verified.')
    records, sources, originals, seen = [], [], [], set()
    for item in index['gate']['history']:
        if item.get('resolution_kind') not in ('chosen', 'free_text', 'cancel'):
            continue
        qid = item.get('question_id')
        if not isinstance(qid, str) or qid in seen:
            raise ec.EngineError('WRITE_AUTHORITY_INVALID', 'Duplicate or malformed answered gate identity.')
        seen.add(qid)
        path = store.gate_path(qid)
        raw, meta = blind_review._bytes(path)
        record = strict_loads(raw.decode('utf-8'))
        for key in ('question_id', 'node', 'source', 'resolution_kind', 'answered_at'):
            if record.get(key) != item.get(key):
                raise ec.EngineError('WRITE_AUTHORITY_INVALID', 'Gate history and actual record disagree.', field=key)
        if type(record.get('visit')) is not int or not record.get('answered_at'):
            raise ec.EngineError('WRITE_AUTHORITY_INVALID', 'Answered gate lacks its actual occurrence/time.')
        answers = [e for e in events if e.get('kind') == 'gate_answer' and e.get('question_id') == qid
                   and e.get('answered_at') == record['answered_at']]
        fields = ('node', 'visit', 'resolution_kind', 'chosen_intent', 'delivered_at', 'answered_at', 'answered_by')
        if len(answers) != 1 or any(answers[0].get(k) != record.get(k) for k in fields):
            raise ec.EngineError('WRITE_AUTHORITY_INVALID', 'Actual gate answer and hash-chained evidence disagree.')
        # Every accepted menu is checked: removing its scope marker must not erase an earlier limit.
        public = render.menu_block(record, user_language=index.get('user_language')).encode('utf-8')
        name = f'menu.{qid}.{ec.sha256_bytes(public)}.txt'
        menu, _ = blind_review._bytes(store.public_dir / name)
        if menu != public:
            raise ec.EngineError('WRITE_AUTHORITY_INVALID', 'Menu does not match its immutable public version.')
        originals.append((store.public_dir / name, menu))
        records.append(copy.deepcopy(record))
        sources.append(dict(question_id=qid, relative=path.relative_to(store.cache_dir).as_posix(), **meta))
        originals.append((path, raw))
    ledger_answered = {e.get('question_id') for e in events if e.get('kind') == 'gate_answer'
                       and e.get('resolution_kind') in ('chosen', 'free_text', 'cancel')}
    if ledger_answered != seen:
        raise ec.EngineError('WRITE_AUTHORITY_INVALID', 'Complete gate history must include every accepted decision in the evidence chain.')
    result = dict(status='WRITE_AUTHORITY', complete=True, binding=binding,
                  consumer=dict(node=index['current']['name'], visit=index['current']['visit'], agent_ticket=agent_ticket),
                  records=records, sources=sources, semantic_authorization_verified=False,
                  scope='Actual Engine records only. Target/field grants must be explicitly visible in selected gate choices; no inference.')
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(encoded) > blind_review.MAX_BYTES:
        raise ec.EngineError('WRITE_AUTHORITY_TOO_LARGE', 'Complete authority exceeds the bounded reader; never truncate or infer.')
    if store.read_index() != index or blind_review._bytes(store.cache_dir / ec.RUN_INPUT)[1] != input_meta \
            or blind_review._bytes(entry_path)[0] != raw_program \
            or blind_review._bytes(store.evidence_path)[1] != ledger_meta \
            or any(blind_review._bytes(path)[0] != raw for path, raw in originals):
        raise ec.EngineError('WRITE_AUTHORITY_CHANGED', 'Authority changed during read; preserve payload and stop.')
    result['snapshot_sha256'] = ec.sha256_bytes(encoded)
    return result
