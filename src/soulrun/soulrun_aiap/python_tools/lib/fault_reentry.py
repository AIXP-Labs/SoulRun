"""One read-only recovery evaluation shared by menus, answers and CLI entry."""
import hashlib
import json
from pathlib import Path


def content_hash(text):
    from .engine_core import _decode_payload_json
    value = _decode_payload_json(text)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def preserve_request(store, observed):
    from . import write_observation
    request = dict(observed.get('request') or {})
    text = request.pop('payload_text', None)
    if text is not None:
        try:
            digest = content_hash(text)
        except (ValueError, TypeError):
            request['payload_unverifiable'] = True
        else:
            raw = text.encode('utf-8')
            relative = '_fault_payload/sha256-' + hashlib.sha256(raw).hexdigest() + '.json'
            from .run_store import read_bytes, _regular_path
            path = store.cache_dir / relative
            with write_observation.maintenance():
                path.parent.mkdir(exist_ok=True)
                if path.parent.is_symlink() or path.parent.resolve() != store.cache_dir / '_fault_payload':
                    raise ValueError('payload evidence directory escapes the run')
                if not _regular_path(path):
                    raise ValueError('payload evidence path is not regular')
                try:
                    with path.open('xb') as stream:
                        stream.write(raw)
                        stream.flush()
                        __import__('os').fsync(stream.fileno())
                except FileExistsError:
                    pass
                if read_bytes(path) != raw:
                    raise ValueError('payload evidence changed')
            request.update(payload_ref=relative, payload_sha256=hashlib.sha256(raw).hexdigest(),
                           payload_content_sha256=digest)
    observed['request'] = request or None


def original_request(store, row):
    from .run_store import read_bytes, _regular_path
    request = (row.get('write_observation') or {}).get('request') or {}
    relative = request.get('payload_ref')
    if relative:
        path = store.cache_dir / relative
        if path.parent.is_symlink() or path.parent.resolve() != store.cache_dir / '_fault_payload' or not _regular_path(path):
            return None
        raw = read_bytes(path)
        if hashlib.sha256(raw).hexdigest() != request.get('payload_sha256') \
                or content_hash(raw.decode('utf-8')) != request.get('payload_content_sha256'):
            return None
    elif row.get('tool') == 'node_commit' and row['error']['code'] != 'GATE_TEXT_DELIVERY_EXHAUSTED':
        return None
    return request


def request_matches(store, row, actual):
    original = original_request(store, row)
    if original is None or actual is None:
        return False
    keys = ('node', 'agent_ticket', 'interpretation') if row['tool'] == 'node_commit' else ('agent_ticket', 'abandon', 'reason')
    if any(original.get(key) != actual.get(key) for key in keys):
        return False
    if original.get('payload_content_sha256'):
        try:
            return content_hash(actual.get('payload_text', '')) == original['payload_content_sha256']
        except (ValueError, TypeError):
            return False
    return True


def project_commit_reentry(cache_dir, index, *, agent_ticket=None):
    """Discover a bound submission without serving a node or consuming its permit."""
    from . import stop_flow, tool_faults
    from .run_store import RunStore
    life = stop_flow.read_lifecycle(cache_dir)
    permit = life.get('fault_reentry') or {}
    if life.get('stop') or permit.get('state') != 'AUTHORIZED_ONE_ROUND' or permit.get('entry_tool') != 'node_commit':
        return None
    row = tool_faults.current(cache_dir, index)
    if not row or row.get('tool') != 'node_commit' or permit.get('fault_sha256') != row.get('sha256') \
            or permit.get('trace_id') != index.get('trace_id') or permit.get('progress_mark') != tool_faults.mark(index) \
            or life.get('trace_id') != index.get('trace_id') or life.get('session_id') != index.get('session_id'):
        return None
    stopped = next((s for s in reversed(life.get('stops') or [])
                    if (s.get('gate') or {}).get('question_id') == permit.get('question_id')), {})
    gate, resolution = stopped.get('gate') or {}, stopped.get('resolution') or {}
    answer = gate.get('answer') or {}
    if gate.get('state') != 'ANSWERED' or answer.get('intent') != 'continue_run' \
            or answer.get('text') != permit.get('answer_text_original') or not answer.get('at') \
            or resolution.get('by') != 'human' or resolution.get('kind') != 'continue':
        return None
    assessment = evaluate(cache_dir, index, row)
    if assessment.get('strategy') not in {'REENTER_ORIGINAL','ACCEPTED_REPLY','FORWARD_ORPHAN_COMMIT'} or permit.get('strategy') != assessment['strategy']:
        return None
    store = RunStore(cache_dir)
    request = original_request(store, row)
    if not request or not request.get('payload_ref') or (agent_ticket and agent_ticket != request.get('agent_ticket')):
        return None
    import sys
    command = [sys.executable, '-B', str(Path(__file__).parent.parent / 'node_commit.py'),
               '--cache-dir', str(store.cache_dir), '--node', request['node'],
               '--payload-file', str(store.cache_dir / request['payload_ref'])]
    if request.get('agent_ticket'):
        command += ['--agent-ticket', request['agent_ticket']]
    if request.get('interpretation'):
        command += ['--interpret-human-reply']
    reply_only = assessment['strategy'] == 'ACCEPTED_REPLY'
    historical = assessment.get('reply_mode') == 'HISTORICAL_PROJECTION'
    return dict(status='ENGINE_REPLY_RECOVERY' if reply_only else 'ENGINE_SUBMISSION_RECOVERY', node_served=False, permit_consumed=False,
        recovery=dict(tool='node_commit', request=request, command_argv=command,
                      question_id=permit['question_id'], fault_sha256=row['sha256'],
                      executor='main_reply_reader' if historical else 'original_ticket_holder' if request.get('agent_ticket') else 'main_inline',
                      rule=('Main may read this sealed receipt with the exact command. The old ticket argument binds request identity only, never execution rights; '
                            'emit no old plan, serve or commit. Continue only through fresh current authority.' if historical else
                            'Read the bound complete accepted reply only; this command must not serve or commit again.' if reply_only else
                            'Only the original executor may submit this preserved payload. No business recomputation, '
                            'payload edits, new child or authority. The actual submission rechecks and consumes the permit.')))


def publication_proof(cache_dir, index, row):
    from . import tool_faults, write_observation, dispatch_prepare, engine_core as ec
    from .run_store import RunStore, _regular_path
    try:
        observed = row['write_observation']
        store = RunStore(cache_dir)
        if row['tool'] not in ('next_node', 'next_node_after_commit') \
                or not write_observation.state_matches(index, observed, accepted=True):
            return False
        if ec.sha256_bytes((store.cache_dir / '_run_input.json').read_bytes()) != observed['baseline']['input_sha256']:
            return False
        if not tool_faults.accepted_state_proof(cache_dir, index, allow_publication=True):
            return False
        ec._load_routed_program(ec._read_run_input(store))
        registered = dispatch_prepare.records(index)
        pending = False
        for ticket, authority in registered.items():
            actual = store.dispatch_path(ticket)
            if not actual.exists():
                prepared = dispatch_prepare.path(store, ticket)
                if not prepared.exists() or authority.get('state') != 'ISSUED':
                    return False
                dispatch_prepare.verify(store, index, ticket, store.read_json(prepared), authority)
                if any((store.cache_dir / f'_dispatch_{kind}.{ticket}.json').exists() for kind in ('start', 'return')):
                    return False
                pending = True
            else:
                dispatch_prepare.verify(store, index, ticket, store.read_json(actual), authority, allow_retirement=True)
                pending |= store.read_json(actual).get('state', 'ISSUED') != authority.get('state')
        for written in observed.get('writes') or []:
            path = Path(written['path'])
            path.resolve().relative_to(store.cache_dir)
            if path == store.index_path:
                continue
            if not _regular_path(path) or written.get('phase') != 'VERIFIED' \
                    or ec.sha256_bytes(path.read_bytes()) != written.get('sha256'):
                return False
            if path.name.startswith('_ticket_prepare.'):
                if store.read_json(path)['ticket'] not in registered:
                    return False
            elif path.parent == store.cache_dir and path.name.startswith('_dispatch.d'):
                formal=store.read_json(path)
                ticket=formal.get('ticket')
                if ticket not in registered or path != store.dispatch_path(ticket):
                    return False
                dispatch_prepare.verify(store,index,ticket,formal,registered[ticket])
            elif path.parent != store.cache_dir / '_public' or not path.name.startswith('plan.'):
                return False
        return pending or any(a.get('state')=='ISSUED' for a in registered.values())
    except Exception:
        return False


def evaluate(cache_dir, index, row):
    from . import tool_faults
    from .run_store import RunStore
    observed = row.get('write_observation') or {}
    strategy, reason = None, 'No verified safe continuation for this effect set.'
    reply_evidence = None
    reply_mode = None
    recovery_rule = None
    if tool_faults.resolved(index, row):
        strategy, reason = 'RECHECK_CONDITION', 'The declared condition has cleared; cause remains undetermined.'
    elif row['error']['code'] == 'GATE_TEXT_DELIVERY_EXHAUSTED':
        strategy, reason = 'DELIVER_ORIGINAL_MENU', 'One human-authorized delivery only; no business answer.'
    elif row['error']['code'] == 'ENGINE_ORPHAN_COMMIT_INTERRUPTED':
        from . import partial_commit
        if partial_commit.proof(cache_dir, index, row):
            strategy, reason = 'FORWARD_ORPHAN_COMMIT', 'Persisted original transition verified; forward Engine bookkeeping only.'
    elif row['error']['code'] == 'ENGINE_UNEXPECTED_EXCEPTION':
        if observed.get('effect_phase') == 'ACCEPTED':
            from . import engine_core as ec, write_observation, accepted_replies
            receipt = observed.get('acceptance') or observed.get('baseline') or {}
            store = RunStore(cache_dir)
            saved = accepted_replies.recoverable(cache_dir, index, observed)
            if saved:
                reply_mode = saved['reply_mode']
                recovery_rule = saved.get('recovery_rule')
                strategy, reason = 'ACCEPTED_REPLY', ('Verified original host-return transition; emit a read-only notice, never the old plan/ticket.'
                    if reply_mode == 'HISTORICAL_PROJECTION' else 'Bound complete reply verified; read it only, never serve or commit again.')
            elif row['tool'] != 'node_commit' and not accepted_replies.enabled(index) and tool_faults.accepted_state_proof(cache_dir, index) \
                    and ec.sha256_bytes((store.cache_dir / '_run_input.json').read_bytes()) == receipt.get('input_sha256') \
                    and write_observation.core_hash(index) == receipt.get('index_core_sha256'):
                strategy, reason = 'ACCEPTED_REPLY', 'Accepted state verified; no business replay.'
            elif row['tool'] == 'node_commit':
                reply_evidence = accepted_replies.inspect(cache_dir, index, observed)
                if reply_evidence['status'] == 'VERIFIED_HISTORICAL_READ_ONLY':
                    reason = ('Bound complete reply exists and verifies, but current state changed; '
                              'historical read-only evidence does not authorize old plans, tickets or business re-entry.')
                else:
                    reason = ('Commit accepted; reply evidence rejected: '+reply_evidence['status']+
                              '. Preserve the original submission; never resubmit business.')
        elif tool_faults.safe_state_proof(cache_dir, index, row):
            if row['tool'] != 'node_commit' or original_request(RunStore(cache_dir), row) is not None:
                strategy, reason = 'REENTER_ORIGINAL', 'Original stage unchanged; only this Engine entry may run once.'
        elif publication_proof(cache_dir, index, row):
            strategy, reason = 'PUBLISH_ACCEPTED_TICKET', 'Complete registered publication only; no new ticket or child.'
        else:
            from . import partial_commit
            if partial_commit.proof(cache_dir, index, row):
                strategy, reason = 'FORWARD_ORPHAN_COMMIT', 'Exact orphan cache and write set verified; complete only its original Engine transition.'
    result = dict(strategy=strategy, safe=bool(strategy), reason=reason)
    if reply_evidence is not None:
        result['reply_evidence'] = reply_evidence
    if reply_mode:
        result['reply_mode'] = reply_mode
    if recovery_rule:
        result['recovery_rule'] = str(recovery_rule)
    return result
