"""Run-scoped Engine quantities, distinct from unknown Provider physical totals."""
from __future__ import annotations

from . import dispatch_budget, dispatch_lifecycle


def snapshot(store, index):
    if not all(key in index for key in ('nodes', 'dispatch', 'trace_id')):
        return None  # A partial diagnostic index cannot establish run-wide quantities.
    group = index['dispatch']
    v2 = any((ne.get('dispatch') or {}).get('scope_root') for ne in index['nodes'].values())
    if not group.get('tickets_issued', 0):
        return None
    known = {}
    for ne in index['nodes'].values():
        d = ne.get('dispatch') or {}
        for row in [d, *(d.get('history') or [])]:
            if row.get('ticket'):
                known[row['ticket']] = row
    issued, starts, returned, continued, physical_ids, resumed, incomplete = [], set(), set(), set(), set(), set(), set()
    reported_ids = set()
    for ticket, row in known.items():
        rec = store.read_json(store.dispatch_path(ticket))
        if rec.get('trace_id') != index['trace_id'] or rec.get('ticket') != ticket:
            continue
        issued.append(rec)
        if rec.get('reason') == 'gate_resume':
            continued.add(ticket)
        if rec.get('reason') == 'segment_resume':
            incomplete.add(ticket)
        start_path = store.cache_dir/f'_dispatch_start.{ticket}.json'
        if start_path.exists():
            start = store.read_json(start_path)
            if start.get('trace_id') == index['trace_id'] and start.get('bootstrap_sha256') == rec.get('bootstrap_sha256'):
                starts.add((start['session_id'], start['tool_call_id']))
        if row.get('exit_evidence'):
            dispatch_lifecycle.verify(store, dict(row, scope_root=row.get('scope_root') or rec.get('scope_root')))
            proof = store.read_json(store.cache_dir/row['exit_evidence']['path'])
            if proof.get('source') == 'host_agent_tool_return':
                returned.add((proof['result']['session_id'], proof['result']['tool_call_id']))
                if proof.get('agent_id'):
                    reported_ids.add(proof['agent_id'])
                    if dispatch_lifecycle.resume_executor(store, row):
                        physical_ids.add(proof['agent_id'])
                target = rec.get('resume_executor')
                if target and dispatch_lifecycle.resume_executor(store, row) and proof.get('agent_id') == target['agent_id'] \
                        and proof['call'].get('resume_agent_id') == target['agent_id'] \
                        and proof['result'].get('session_id') == target['session_id']:
                    resumed.add(ticket)
    roots = {(r.get('scope_root', {}).get('node') or r['node'], r.get('scope_root', {}).get('visit') or r['visit']) for r in issued}
    handovers = [r for r in issued if r.get('reason') == 'identity_handoff' and r.get('claimed_at')]
    progress = {r['identity_handoff']['progress_key'] for r in handovers}
    return dict(scope='this_engine_run_bound_tickets_and_host_events', roots=len(roots), tickets=len(issued),
        execution_segments=sum(bool(r.get('claimed_at')) for r in issued),
        host_agent_calls_started=len(starts) if v2 else None, host_confirmed_returns=len(returned) if v2 else None,
        host_event_status='RECORDED_V2' if v2 else 'NOT_RECORDED_V1',
        identity_source_qualification='UNVERIFIED', reported_agent_ids_count=len(reported_ids),
        identity_handover_claims=len(handovers), identity_progress_handovers=len(progress),
        identity_same_progress_retry_claims=len(handovers) - len(progress),
        new_executor_claims=group['spawns_claimed'],
        new_executor_claims_basis='legacy_raw_execution_segment_claims_including_resumes_not_native_child_count',
        new_child_agents_observed_lower_bound=len(physical_ids),
        original_session_resumes=dict(count=len(resumed), verification='HOST_EVENT_OBSERVED' if resumed else 'UNVERIFIED'),
        main_agent_takeovers=group['fallbacks'], human_gate_continuations=len(continued),
        incomplete_root_continuations=len(incomplete),
        ordinary_claims=dispatch_budget.usage(index, 'ordinary'), independent_claims=dispatch_budget.usage(index, 'independent'),
        **(dict(total_claims=group['spawns_claimed'], ordinary_resume_claims=group.get('ordinary_resumes_claimed',0))
           if dispatch_budget.resume_accounting(index) else {}),
        **(dict(independent_resume_claims=group.get('independent_resumes_claimed',0),
                independent_raw_claims=group.get('independent_claimed',0))
           if dispatch_budget.independent_resume_accounting(index) else {}),
        # docs/05SoulRun 87: replacements are counted on their own, not as new tasks (owner ruling 352 §8 item 2).
        **(dict(replacement_claims=group.get('ordinary_replacements_claimed',0) + group.get('independent_replacements_claimed',0),
                human_chosen_replacements=sum(r.get('reason') == 'human_replacement' for r in issued))
           if dispatch_lifecycle.replacement_accounting(index) else {}),
        physical_provider_spawns=dict(total=None, status='UNKNOWN', observed_identity_lower_bound=len(physical_ids)),
        rule='Logical claims/segments and reported IDs are not physical Agent creations or qualified native identity. '
             'Host start/return quantities count bound reports only. Physical totals stay unknown; no qualified identities '
             'means an observed lower bound of zero, not proof that zero agents exist. Identity handovers and same-progress retries are separate.')
