"""Read-only counts by evidence source; no inferred cross-source deduplication."""
from .run_store import RunStore, RunStoreError


def project(cache_dir, index=None, diagnostics=None):
    from . import engine_core as ec, tool_faults, dispatch_budget
    store = RunStore(cache_dir)
    index = index if index is not None else store.read_index()
    rows = diagnostics if diagnostics is not None else tool_faults.report_diagnostics(cache_dir)
    faults = [r for r in rows if r['source_ref'] == tool_faults.FILE
              and r['code'] != 'RECOVERY_DIAGNOSTIC_UNVERIFIABLE']
    operations, unknown_operations, recovered, rejected = set(), 0, set(), set()
    for row in faults:
        record = row['record']
        operation = (record.get('write_observation') or {}).get('operation_id')
        origin = (record.get('recovery') or {}).get('origin_fault_sha256')
        if origin:
            original = next((r['record'] for r in faults if r['record'].get('sha256') == origin), None)
            operation = ((original or {}).get('write_observation') or {}).get('operation_id')
        if operation:
            operations.add(operation)
            if record.get('disposition') == 'REPLY_RECOVERED':
                recovered.add(operation)
            elif record.get('disposition') == tool_faults.REJECTED_REPLY:
                rejected.add(operation)   # a rejection changed nothing: not an unresolved operation
        else:
            unknown_operations += 1
    node_rows, unreadable = 0, []
    for key, state in index.get('nodes', {}).items():
        if not state.get('cache_sha256'):
            continue
        try:
            name, _, visit = key.partition('@v')
            entry = ec._catalog_entry(index, name)
            path = ec._cache_path_for(store, index, entry, int(visit or 1))
            cache = store.read_json(path)
            if ec.sha256_bytes(store.read_bytes(path)) != state['cache_sha256']:
                raise ValueError('accepted node cache changed')
            node_rows += sum(len(r['payload'].get('anomalies') or []) +
                             len(r['machine'].get('engine_anomalies') or []) for r in ec._evidence_records(cache))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RunStoreError, ec.EngineError):
            unreadable.append(key)
    rechecks, recheck_passed, lifecycle_verified = 0, 0, True
    gate_sources_unverifiable = []
    qids = {r['question_id'] for r in (index.get('gate') or {}).get('history') or [] if r.get('question_id')}
    if (index.get('gate') or {}).get('question_id'):
        qids.add(index['gate']['question_id'])
    for qid in sorted(qids):
        try:
            gate = store.read_json(store.gate_path(qid))
            for attempt in gate.get('recheck_attempts') or []:
                rechecks += 1
                recheck_passed += attempt.get('condition_result') == 'PASSED'
        except (OSError, ValueError, TypeError, KeyError, RunStoreError):
            gate_sources_unverifiable.append(qid)
    life_path = store.cache_dir/'_host_lifecycle.json'
    if store.exists_path(life_path):
        try:
            life = store.read_json(life_path)
            if any(life.get(k) != index.get(k) for k in ('session_id', 'trace_id')):
                raise ValueError('lifecycle identity differs')
            stops = list(life.get('stops') or [])
            if life.get('stop'):
                stops.append(life['stop'])
            for stop in stops:
                for attempt in (stop.get('gate') or {}).get('recheck_attempts') or []:
                    rechecks += 1
                    recheck_passed += attempt.get('condition_result') == 'PASSED'
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RunStoreError):
            lifecycle_verified = False
    dispatch = index.get('dispatch') or {}
    orphan_rows = [r for r in rows if r['code'] in ('ORPHAN_COMMIT_RECOVERED','ORPHAN_RECOVERY_ATTEMPT_PENDING')]
    orphan_operations = {r['record']['operation_id'] for r in orphan_rows}
    accepted_orphans = {r['record']['operation_id'] for r in orphan_rows if r['code']=='ORPHAN_COMMIT_RECOVERED'}
    return dict(schema_version=1, scope='this_cache_recorded_evidence_only',
        identity={k:index.get(k) for k in ('trace_id','session_id','engine_version')},
        index_anomaly_rows=len(index.get('anomalies_summary') or []), node_anomaly_rows=node_rows,
        node_sources_unverifiable=unreadable, machine_fault_rows=len(faults),
        bound_operation_events=len(operations), fault_rows_without_operation_binding=unknown_operations,
        recovered_reply_operations=len(recovered), unresolved_recorded_operations=len(operations-recovered-rejected),
        rejected_replies_not_delivered=len(rejected),
        orphan_recovery_attempts=len(orphan_rows),
        orphan_bound_operations=len(orphan_operations),
        orphan_recoveries=len(accepted_orphans),
        orphan_recoveries_pending=len(orphan_operations-accepted_orphans),
        automatic_reply_attempts=sum(r['record'].get('disposition') == 'REPLY_RECOVERY_ATTEMPTED' for r in faults),
        automatic_reply_recoveries=sum(r['record'].get('disposition') == 'REPLY_RECOVERED' and
            (r['record'].get('recovery') or {}).get('by') != 'human' for r in faults),
        manual_reply_recoveries=sum(r['record'].get('disposition') == 'REPLY_RECOVERED' and
            (r['record'].get('recovery') or {}).get('by') == 'human' for r in faults),
        human_rechecks=rechecks, human_rechecks_passed=recheck_passed,
        lifecycle_source_verified=lifecycle_verified, gate_sources_unverifiable=gate_sources_unverifiable,
        diagnostic_sources_unverifiable=[dict(source_ref=r['source_ref'], source_sha256=r['source_sha256'])
            for r in rows if r['code'] in ('RECOVERY_DIAGNOSTIC_UNVERIFIABLE','RECOVERY_DIAGNOSTIC_TRUNCATED_TAIL')],
        dispatch_counts=dict(raw_spawns_claimed=dispatch.get('spawns_claimed', 0),
            ordinary_logical_claims=dispatch_budget.usage(index, 'ordinary') if 'spawns_claimed' in dispatch else 0,
            independent_logical_claims=dispatch_budget.usage(index, 'independent') if 'spawns_claimed' in dispatch else 0,
            ordinary_replacements_claimed=dispatch.get('ordinary_replacements_claimed', 0),
            independent_replacements_claimed=dispatch.get('independent_replacements_claimed', 0),
            provider_actual_spawns='UNVERIFIED'),
        cross_source_deduplication='not_inferred', recovery_authorized=False)
