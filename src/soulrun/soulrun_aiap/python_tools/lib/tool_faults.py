"""Fail-closed CLI diagnostics; they authorize a stop, never a business action."""
import hashlib,json
from pathlib import Path
from .run_store import RunStore,RunStoreError,atomic_write_bytes,dumps,now_iso,_regular_path
from . import write_observation
FILE='_engine_faults.json'

def cli_args(argv):
    import argparse
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--cache-dir');parser.add_argument('--payload-file')
    return parser.parse_known_args(argv)[0]

def policy():
    from . import contracts as _contracts
    return json.loads(_contracts.text('engine-faults.policy'))

def mark(index):
    return dict(completed=len(index.get('completed',[])),node=index['current']['name'],visit=index['current']['visit'])

def seal(row):
    return hashlib.sha256(dumps(row).encode()).hexdigest()

def record(cache_dir,tool,error, *, disposition=None, recovery=None, observation=None):
    from . import engine_core as ec
    if error.code not in policy()['non_retryable']:return None
    store=RunStore(cache_dir)
    try:index=store.read_index()
    except Exception:return None
    if index.get('engine_version')!=ec.ENGINE_VERSION or (index.get('run_state') in ec.TERMINAL_STATES and not disposition):return None
    if observation is not None:
        import copy
        observed=copy.deepcopy(observation)
    else:
        observed=write_observation.facts()
    from . import fault_reentry
    fault_reentry.preserve_request(store,observed)
    if any(w.get('path')==str(store.index_path) and w.get('phase')=='VERIFIED'
           and w.get('sha256')==ec.sha256_bytes(store.index_path.read_bytes()) for w in observed.get('writes') or []):
        observed['accepted_index_core_sha256']=write_observation.core_hash(index)
        observed['accepted_recovery_projection_version']=1
        observed['accepted_recovery_state_sha256']=write_observation.recovery_hash(index)
    row=dict(owner='execute_engine_cli',tool=tool,at=now_iso(),engine_version=ec.ENGINE_VERSION,
        trace_id=index['trace_id'],progress_mark=mark(index),error=error.as_dict(),
        write_observation=observed)
    if disposition:row.update(disposition=disposition, recovery=recovery)
    path=store.cache_dir/FILE
    rows=json.loads(path.read_bytes()) if path.exists() else []
    permit=retry_permit(cache_dir)
    if rows and rows[-1].get('disposition')==disposition and rows[-1].get('error')==row['error'] and rows[-1].get('progress_mark')==row['progress_mark'] \
            and permit.get('fault_sha256')!=rows[-1].get('sha256'):return rows[-1]
    rows.append(dict(row,sha256=seal(row)))
    with write_observation.maintenance():
        atomic_write_bytes(path,dumps(rows).encode())
    return rows[-1]

def capture(cache_dir,tool,error):
    """A broken diagnostic store must not replace the originating CLI failure."""
    try:
        row=record(cache_dir,tool,error)
        if not row:return {}
        out=dict(receipt=FILE)
        request=(row.get('write_observation') or {}).get('request') or {}
        if request.get('payload_ref'):
            out['original_payload']=dict(path=str(Path(cache_dir)/request['payload_ref']),
                sha256=request['payload_sha256'],rule='Resubmit this original content; changed content does not consume the permit.')
        try:
            with write_observation.maintenance():
                question=pending_question(cache_dir,RunStore(cache_dir).read_index())
            if question:out.update(fault_question_id=question['question_id'],public_block_ref=question['public_block_ref'])
        except Exception as exc:
            out['diagnostic_menu_error']=type(exc).__name__
        return out
    except Exception as exc:
        return dict(diagnostic_write_error=type(exc).__name__)

REJECTED_REPLY='REJECTED_REPLY_NOT_DELIVERED'
HANDLED_DISPOSITIONS=('REPLY_RECOVERED',REJECTED_REPLY)


def rejected_reply_proof(cache_dir,observed):
    """A node-commit the Engine rejected whose printed reply then failed. Proven from this call's own write facts: it wrote
    only the echo of that REJECTED reply (and, for a sub-agent, the rejected payload kept under _dispatch_pending/), and the
    run's index, input and tickets are exactly as they were when the call began. Such a fault changes nothing and authorizes
    nothing, so it needs no human decision; the executor reads the echo or submits again. Anything else returns None and
    keeps the fail-closed path: an accepted commit, any other write, an echo that is not a rejection, a changed run."""
    from . import engine_core as ec
    try:
        before=observed.get('baseline') or {}
        if observed.get('tool')!='node_commit' or observed.get('effect_phase')!='WRITES_VERIFIED' or not before:return None
        store=RunStore(cache_dir);root=store.cache_dir.resolve();index=store.read_index()
        if not write_observation.state_matches(index,before) \
                or ec.sha256_bytes((store.cache_dir/'_run_input.json').read_bytes())!=before.get('input_sha256') \
                or sorted(p.name for p in store.cache_dir.glob('_dispatch.d*.json'))!=before.get('ticket_files'):return None
        replies,kept=[],[]
        for written in observed.get('writes') or []:
            path=Path(written['path']).resolve();rel=path.relative_to(root)
            if written.get('phase')!='VERIFIED' or not _regular_path(path) or not path.is_file():return None
            if rel.parent.as_posix()=='_work/replies' and '.commit.' in rel.name and rel.suffix=='.json':replies.append(rel)
            elif rel.parent.as_posix()=='_dispatch_pending':kept.append(rel)
            else:return None
        if len(replies)!=1:return None
        raw=(root/replies[0]).read_bytes();reply=json.loads(raw)
        if not isinstance(reply,dict) or reply.get('status')!='REJECTED':return None
        return dict(reply_ref=replies[0].as_posix(),reply_sha256=ec.sha256_bytes(raw),
            kept_payload_refs=[k.as_posix() for k in kept],run_unchanged=True,accepted=False,business_replayed=False)
    except Exception:return None


WINDOWS_MAX_PATH=260


def _long_paths_enabled():
    """Windows' LongPathsEnabled setting, read only; False when it cannot be read."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
            return winreg.QueryValueEx(key,'LongPathsEnabled')[0]==1
    except (ImportError,OSError):
        return False


def describe(error):
    """The message of an unexpected exception. docs/05SoulRun 90 (problem 24): Windows without long-path support refuses a
    path of 260 characters or more and reports it as 'No such file or directory' (or 'path not found'); that case is said
    plainly - how long, the limit - with the system's own words after it. Anything else: str(error), as before."""
    import errno
    import os
    if os.name!='nt' or not isinstance(error,OSError) or (error.errno!=errno.ENOENT and getattr(error,'winerror',None) not in (3,206)):
        return str(error)
    paths=[os.path.abspath(os.fsdecode(p)) for p in (error.filename,error.filename2) if isinstance(p,(str,bytes,os.PathLike))]
    paths=[p for p in paths if not p.startswith('\\\\?\\') and len(p)>=WINDOWS_MAX_PATH]
    if not paths or _long_paths_enabled():
        return str(error)
    path=max(paths,key=len)
    return (f'Path too long: {len(path)} characters; without long-path support (not enabled on this machine) Windows refuses a path of '
            f'{WINDOWS_MAX_PATH} characters or more, and reports it as not found. Use a shorter run folder or enable long paths. '
            f'Path: {path} (system message: {error})')


def unexpected(cache_dir,tool,error):
    from . import engine_core as ec
    from . import partial_commit
    try:
        store=RunStore(cache_dir)
        index=store.read_index()
        original=partial_commit.original_intent(store,index)
        directory=store.cache_dir/partial_commit.RECOVERIES
        attempted=bool(original and _regular_path(directory) and
            any(directory.glob(original['write_observation']['operation_id']+'.*.json')))
        if attempted and partial_commit.proof(cache_dir,index,original):
            fault=ec.EngineError(partial_commit.ORPHAN_CODE,
                'A recovery attempt failed before acceptance; recheck the original transition and obtain a new human decision.',
                example=dict(original_error_type=type(error).__name__,original_error=str(error)))
            with write_observation.maintenance():
                record(cache_dir,'node_commit',fault,observation=original['write_observation'])
            return dict(status='ERROR',errors=[fault.as_dict()],**capture(cache_dir,'node_commit',fault))
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RunStoreError,ec.EngineError):
        pass  # Unproven effects keep the original fail-closed unexpected-fault path.
    import traceback
    frames=traceback.extract_tb(error.__traceback__)
    where=frames[-1] if frames else None
    proof=rejected_reply_proof(cache_dir,write_observation.facts()) if cache_dir and tool=='node_commit' else None
    if proof:
        fault=ec.EngineError('ENGINE_UNEXPECTED_EXCEPTION',describe(error),field=tool,
            example=dict(exception_type=type(error).__name__,point='rejected_reply'))
        try:
            row=record(cache_dir,tool,fault,disposition=REJECTED_REPLY,recovery=proof)
        except Exception:
            row=None
        if row:
            return dict(status='ERROR',errors=[fault.as_dict()],receipt=FILE,
                rejected_reply=dict(disposition=REJECTED_REPLY,reply_file=proof['reply_ref'],
                    rule='The Engine rejected this submission and changed nothing; only its printed reply was lost. '
                         'Read the reply file, or fix the payload and submit again. No human decision is needed.'))
    fault=ec.EngineError('ENGINE_UNEXPECTED_EXCEPTION',describe(error),field=tool,
        example=dict(exception_type=type(error).__name__,file=where.filename if where else None,line=where.lineno if where else None))
    return dict(status='ERROR',errors=[fault.as_dict()],**capture(cache_dir,tool,fault))

def current(cache_dir,index):
    from . import engine_core as ec
    path=Path(cache_dir)/FILE
    if not path.exists():return None
    try:
        rows=json.loads(path.read_bytes())
        if not isinstance(rows,list):raise ValueError('fault store is not a list')
        for saved in rows:
            row={k:v for k,v in saved.items() if k!='sha256'}
            if saved.get('sha256')!=seal(row) or row.get('owner')!='execute_engine_cli':raise ValueError('fault receipt changed')
        for saved in reversed(rows):
            row={k:v for k,v in saved.items() if k!='sha256'}
            if row.get('engine_version')==ec.ENGINE_VERSION and row.get('trace_id')==index.get('trace_id') and row.get('progress_mark')==mark(index):return saved
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        raise ec.EngineError('ENGINE_FAULT_RECORD_INVALID','Machine fault diagnostic cannot be verified; preserve it and stop.')
    return None

def resolved(index,row):
    code=row['error']['code'];active={e['name']:e for e in index.get('catalog',[])};history=index.get('catalog_history',{})
    accepted={k.partition('@')[0] for k,s in index.get('nodes',{}).items() if s.get('cache_sha256')}
    if code=='CATALOG_HISTORY_MISSING':return accepted<=active.keys()|history.keys()
    if code=='CURRENT_PLAN_ENTRY_MISSING':return index['current']['name'] in active
    if code=='CATALOG_DEFINITION_CHANGED':
        fields=('kind','parent','depth','doc','task','node')
        return not any(n in history and any(history[n].get(k)!=e.get(k) for k in fields) for n,e in active.items() if n in accepted)
    return False

def retry_permit(cache_dir):
    from . import stop_flow
    return stop_flow.read_lifecycle(cache_dir).get('fault_reentry') or {}

def human_reentry_receipt(cache_dir,index):
    """Disclose an already recorded machine answer; never grant or consume authority."""
    from . import stop_flow
    life=stop_flow.read_lifecycle(cache_dir);permit=life.get('fault_reentry') or {}
    if life.get('trace_id')!=index.get('trace_id') or life.get('session_id')!=index.get('session_id') \
            or permit.get('trace_id')!=index.get('trace_id') or permit.get('state')!='CONSUMED':return None
    row=current(cache_dir,index)
    if not row or row.get('sha256')!=permit.get('fault_sha256'):return None
    for stopped in reversed(life.get('stops') or []):
        gate=stopped.get('gate') or {};answer=gate.get('answer') or {};resolution=stopped.get('resolution') or {}
        if gate.get('question_id')!=permit.get('question_id'):continue
        if gate.get('state')!='ANSWERED' or resolution.get('by')!='human' or resolution.get('kind')!='continue' \
                or answer.get('intent')!='continue_run' or answer.get('text')!=permit.get('answer_text_original') \
                or not answer.get('at'):return None
        return dict(question_id=gate['question_id'],answer_text_original=answer['text'],answered_at=answer['at'],
            chosen_intent=answer['intent'],fault_sha256=row['sha256'],reentry_state=permit['state'],
            source_ref='_host_lifecycle.json',scope='one_verified_engine_reentry_not_a_business_gate_answer',
            rule='The human already answered this machine recovery gate. gate_answer is for business gates and may be null. '
                 'Do not reopen this answered gate or replay committed business; a new fault still requires its own decision.')
    return None

def authorize_retry(cache_dir,index,row,question_id,answer, *, life=None):
    """Only a verified exact receipt can authorize one fresh CLI entry."""
    from . import stop_flow
    verified=current(cache_dir,index)
    if not verified or verified.get('sha256')!=row.get('sha256'):return False
    observed=row.get('write_observation') or {}
    delivery=row['error']['code']=='GATE_TEXT_DELIVERY_EXHAUSTED'
    if (row['error']['code'] not in ('ENGINE_UNEXPECTED_EXCEPTION','ENGINE_ORPHAN_COMMIT_INTERRUPTED') and not delivery) or observed.get('trace_id')!=index['trace_id']:
        return False
    from . import fault_reentry
    assessment=fault_reentry.evaluate(cache_dir,index,row)
    phase=observed.get('effect_phase')
    if delivery:
        from . import gate_delivery
        if not gate_delivery.authorize(cache_dir,index,question_id,answer):return False
    elif not assessment['safe']:return False
    # Accepted requires the current index/ledger to prove a complete, non-orphan commit.
    if phase=='ACCEPTED':
        if not accepted_state_proof(cache_dir,index):return False
        receipt=observed.get('acceptance') or observed.get('baseline') or {}
        if not receipt.get('input_sha256') or hashlib.sha256((RunStore(cache_dir).cache_dir/'_run_input.json').read_bytes()).hexdigest()!=receipt['input_sha256']:return False
        if assessment['strategy']!='ACCEPTED_REPLY' and receipt.get('index_core_sha256') and write_observation.core_hash(index)!=receipt['index_core_sha256']:return False
    persist=life is None
    life=stop_flow.read_lifecycle(cache_dir) if persist else life
    previous=life.get('fault_reentry') or {}
    if previous.get('fault_sha256')==row['sha256']:
        return previous.get('state')=='AUTHORIZED_ONE_ROUND' and previous.get('question_id')==question_id
    life['fault_reentry']=dict(state='AUTHORIZED_ONE_ROUND', fault_sha256=row['sha256'],
        question_id=question_id, answer_text_original=answer, trace_id=index['trace_id'],
        entry_tool='next_node' if row['tool']=='next_node_after_commit' else row['tool'],
        progress_mark=mark(index),tool=row['tool'],strategy=assessment['strategy'],at=now_iso())
    if assessment.get('reply_mode') == 'HISTORICAL_PROJECTION':
        life['fault_reentry'].update(reply_mode=assessment['reply_mode'],
            current_recovery_sha256=write_observation.recovery_hash(index))
    if persist:stop_flow.write_lifecycle(cache_dir,fault_reentry=life['fault_reentry'])
    return True

def consume_retry(cache_dir):
    if retry_permit(cache_dir).get('state')!='AUTHORIZED_ONE_ROUND':return
    from . import engine_core as ec
    if RunStore(cache_dir).read_index().get('engine_version')!=ec.ENGINE_VERSION:return
    entry=write_observation.facts().get('tool')
    request=write_observation.request()
    with write_observation.maintenance():
        with RunStore(cache_dir).lock():
            return _consume_retry_locked(cache_dir,entry=entry,request=request)

def require_clear(cache_dir,index):
    """A failed menu write must not turn a recorded fault into permission to execute."""
    report_observations(cache_dir)
    if not (RunStore(cache_dir).cache_dir/FILE).exists():return
    row=current(cache_dir,index)
    if not row or resolved(index,row):return
    if row.get('disposition') in HANDLED_DISPOSITIONS:return
    permit=retry_permit(cache_dir)
    if permit.get('fault_sha256')==row.get('sha256') and permit.get('trace_id')==index['trace_id'] \
            and permit.get('state')=='CONSUMED':return
    from .engine_core import EngineError
    raise EngineError('ENGINE_FAULT_PAUSED','A verified machine fault remains paused; obtain the actual human decision before re-entry. Preserve its receipt.',field=FILE)

def _consume_retry_locked(cache_dir, *, entry=None, request=None):
    from . import stop_flow
    life=stop_flow.read_lifecycle(cache_dir)
    permit=life.get('fault_reentry') or {}
    if permit.get('state')=='AUTHORIZED_ONE_ROUND':
        index=RunStore(cache_dir).read_index()
        row=current(cache_dir,index)
        if not row or permit.get('trace_id')!=index['trace_id'] or permit.get('fault_sha256')!=row.get('sha256') \
                or permit.get('progress_mark')!=mark(index):
            from .engine_core import EngineError
            raise EngineError('ENGINE_FAULT_REENTRY_INVALID','Fault re-entry identity changed; preserve and stop.')
        actual=entry or write_observation.facts().get('tool')
        if actual and permit.get('entry_tool') and actual!=permit['entry_tool']:
            from .engine_core import EngineError
            raise EngineError('ENGINE_FAULT_REENTRY_INVALID','Permit is bound to a different Engine entry; never resubmit completed business.')
        stopped=next((s for s in reversed(life.get('stops') or []) if (s.get('gate') or {}).get('question_id')==permit.get('question_id')),None)
        gate=(stopped or {}).get('gate') or {}
        if life.get('stop') or gate.get('state')!='ANSWERED' or (gate.get('answer') or {}).get('intent')!='continue_run' \
                or (stopped.get('resolution') or {}).get('by')!='human':
            from .engine_core import EngineError
            raise EngineError('ENGINE_FAULT_PAUSED','Human answer and gate resolution are not fully persisted; permit remains unused.')
        from . import fault_reentry
        bound=(row.get('write_observation') or {}).get('request')
        if (actual=='node_commit' or bound) and row['error']['code']!='GATE_TEXT_DELIVERY_EXHAUSTED' \
                and not fault_reentry.request_matches(RunStore(cache_dir),row,request):
            from .engine_core import EngineError
            request=(row.get('write_observation') or {}).get('request') or {}
            raise EngineError('ENGINE_FAULT_REENTRY_PAYLOAD_MISMATCH',
                'Resubmit the preserved original payload with its original node/ticket. Permit not consumed.',
                expected=request.get('payload_ref'))
        strategy=permit.get('strategy')
        if permit.get('current_recovery_sha256') and write_observation.recovery_hash(index) != permit['current_recovery_sha256']:
            from .engine_core import EngineError
            raise EngineError('ENGINE_FAULT_REENTRY_INVALID', 'Current authority changed after the human decision; permission unused.')
        assessment=fault_reentry.evaluate(cache_dir,index,row)
        if not assessment['safe'] or strategy and strategy!=assessment['strategy']:
            from .engine_core import EngineError
            raise EngineError('ENGINE_FAULT_REENTRY_INVALID','Recovery proof changed; preserve and stop.')
        if assessment['strategy']=='PUBLISH_ACCEPTED_TICKET':
            from . import dispatch_prepare
            dispatch_prepare.publish(RunStore(cache_dir),index,registered=True)
        permit.update(state='CONSUMED',consumed_at=now_iso())
        with write_observation.maintenance():
            stop_flow.write_lifecycle(cache_dir,fault_reentry=permit)
        return assessment['strategy']

def pending_question(cache_dir,index,invocation_id=''):
    from . import supply_flow as sf,stop_flow
    from .engine_core import EngineError
    try:row=current(cache_dir,index)
    except EngineError as exc:
        row=dict(owner='execute_engine_recovery_verification',at=now_iso(),progress_mark=mark(index),error=exc.as_dict())
    if not row or resolved(index,row) or row.get('disposition') in HANDLED_DISPOSITIONS:return None
    permit=retry_permit(cache_dir)
    if permit.get('fault_sha256')==row.get('sha256') and permit.get('trace_id')==index['trace_id'] \
            and permit.get('state') in {'AUTHORIZED_ONE_ROUND','CONSUMED'}:return None
    life=stop_flow.read_lifecycle(cache_dir);stop=life.get('stop') or {}
    if stop.get('state')=='GATED':
        from . import menu_history
        return dict(question_id=stop['gate']['question_id'],public_block_ref=menu_history.ref(cache_dir,f"menu.{stop['gate']['question_id']}.txt"))
    return sf.open_supply_question(cache_dir,index,error_code=row['error']['code'],error_details=dict(supply_kind='engine_fault',engine_fault=row),
        invocation_id=invocation_id,attempts=0,progress_mark=mark(index),since=row['at'])


def accepted_state_proof(cache_dir,index, *, allow_publication=False):
    from . import engine_core as ec
    try:
        store = RunStore(cache_dir)
        ec.program_guard.assert_run_version(index)
        ec._read_run_input(store)
        if ec.ledger_errors(ec._read_ledger(store)):return False
        for key, row in index['nodes'].items():
            if row.get('cache_sha256'):
                entry = ec._catalog_entry(index,key.partition('@')[0])
                visit = int((key.partition('@')[2] or '1').removeprefix('v'))
                if ec.sha256_bytes(ec._cache_path_for(store,index,entry,visit).read_bytes()) != row['cache_sha256']:return False
        tickets = list(store.cache_dir.glob('_dispatch.d*.json'))
        if not allow_publication and len(tickets) != (index.get('dispatch') or {}).get('tickets_issued', 0):return False
        from . import dispatch_prepare
        registered=dispatch_prepare.records(index)
        expected={f'_dispatch.{t}.json' for t in registered}
        if len(registered)!=(index.get('dispatch') or {}).get('tickets_issued',0):return False
        if not {p.name for p in tickets}<=expected or not allow_publication and {p.name for p in tickets}!=expected:return False
        for path in tickets:
            ticket=json.loads(path.read_bytes())
            authority=registered.get(ticket.get('ticket'))
            if not authority or path.name!=f"_dispatch.{ticket['ticket']}.json" or ticket.get('trace_id') != index['trace_id'] \
                    or ec.sha256_bytes(ticket['bootstrap'].encode()) != ticket['bootstrap_sha256'] \
                    or (authority.get('bootstrap_sha256') and authority['bootstrap_sha256']!=ticket['bootstrap_sha256']):return False
            if ticket.get('scope_root')!=authority.get('scope_root'):return False
            owner,_,visit=authority['_owner_key'].partition('@')
            if f"node={ticket.get('node')}" not in ticket['bootstrap'].splitlines() or f"ticket={ticket['ticket']}" not in ticket['bootstrap'].splitlines():return False
            if ticket.get('node')==owner:
                if ticket.get('visit')!=int((visit or '1').removeprefix('v')):return False
            elif not str(ticket.get('node','')).startswith(owner+'/') or ticket.get('scope_root')!=authority.get('scope_root') or not ticket.get('scope_root'):return False
        return True
    except Exception:return False


def safe_state_proof(cache_dir,index,row):
    """Only the failed next-node stage; a private unregistered preparation cannot execute."""
    from . import engine_core as ec,dispatch_prepare
    from .run_store import _regular_path
    try:
        observed=row['write_observation'];before=observed['baseline'];store=RunStore(cache_dir)
        if row['tool'] not in ('next_node','next_node_after_commit','node_commit') or not before or index['run_state']!='RUNNING':return False
        if row['tool']=='node_commit' and observed.get('writes'):return False
        if not write_observation.state_matches(index,before) \
                or ec.sha256_bytes((store.cache_dir/'_run_input.json').read_bytes())!=before['input_sha256'] \
                or sorted(p.name for p in store.cache_dir.glob('_dispatch.d*.json'))!=before['ticket_files']:return False
        if not accepted_state_proof(cache_dir,index):return False
        ec._load_routed_program(ec._read_run_input(store))
        for written in observed['writes']:
            path=Path(written['path'])
            path.resolve().relative_to(store.cache_dir)
            if not _regular_path(path):return False
            if path==store.index_path:continue
            actual=ec.sha256_bytes(path.read_bytes()) if path.exists() else 'ABSENT'
            if actual==written.get('before_sha256'):continue
            if path.name.startswith('_ticket_prepare.') and written.get('before_sha256')=='ABSENT' \
                    and written.get('phase')=='VERIFIED' and written.get('sha256')==actual:
                ticket=store.read_json(path);identity=ticket['ticket']
                if path!=dispatch_prepare.path(store,identity) or ec._ticket_known(index,identity) \
                        or ticket.get('trace_id')!=index['trace_id'] or ticket.get('claimed_at') or ticket.get('committed_at') \
                        or store.dispatch_path(identity).exists() \
                        or any((store.cache_dir/f'_dispatch_{kind}.{identity}.json').exists() for kind in ('start','return')) \
                        or ec.sha256_bytes(ticket['bootstrap'].encode())!=ticket.get('bootstrap_sha256'):return False
                continue
            return False
        return True
    except Exception:return False


def verify_accepted(cache_dir, candidate):
    from . import engine_core as ec, stop_state
    try:
        store=RunStore(cache_dir)
        if stop_state.stop_fence(cache_dir) is not None:return False
        if ec.sha256_bytes(store.index_path.read_bytes()) != candidate['index_sha256']:return False
        if ec.sha256_bytes((store.cache_dir/'_run_input.json').read_bytes()) != candidate['input_sha256']:return False
        report_observations(cache_dir)
        return accepted_state_proof(cache_dir,store.read_index())
    except Exception:return False


def recover_reply(cache_dir, tool, error):
    from . import reply_io
    if isinstance(error, reply_io.ReplyEmissionError):
        return False  # The receiver may already have a prefix; one blind resend is not safe.
    try:return _recover_reply(cache_dir, tool, error)
    except Exception:return False


def replay_reply(cache_dir):
    """After one bound human permit, print the saved reply without business re-entry."""
    from . import accepted_replies, engine_core as ec
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        row = current(cache_dir, index)
        permit = retry_permit(cache_dir)
        saved = accepted_replies.recoverable(cache_dir, index, (row or {}).get('write_observation') or {})
        if not saved or permit.get('state') != 'CONSUMED' or permit.get('strategy') != 'ACCEPTED_REPLY' \
                or permit.get('fault_sha256') != row.get('sha256'):
            raise ec.EngineError('ENGINE_FAULT_REENTRY_INVALID', 'Accepted reply evidence or human permit changed; no replay.')
        if saved['reply_mode'] == 'HISTORICAL_PROJECTION':
            if permit.get('reply_mode') != saved['reply_mode'] or permit.get('current_recovery_sha256') != write_observation.recovery_hash(index):
                raise ec.EngineError('ENGINE_FAULT_REENTRY_INVALID', 'Historical read permission no longer binds current state.')
            result = dict(status='ACCEPTED_REPLY_READ_ONLY', historical=True, old_plan_and_ticket_executable=False,
                node=saved['receipt']['node'], reply_file=saved['receipt']['reply_ref'],
                wire_sha256=saved['receipt']['wire_sha256'],
                rule='Original reply preserved; no business or old plan/ticket replay. Use next_node without the old ticket for current authority.')
            wire = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            result, wire = saved['result'], saved['wire']
        write_observation.accepted(result, kind=saved['receipt']['kind'], node=saved['receipt']['node'])
        write_observation.bind_accepted_reply(saved['reference'])
    from . import reply_io
    reply_io.emit(wire)
    record(cache_dir, row['tool'], ec.EngineError(
        row['error']['code'], row['error'].get('message',''), field=row['error'].get('field'),
        expected=row['error'].get('expected'), example=row['error'].get('example')),
        disposition='REPLY_RECOVERED', recovery=dict(by='human', question_id=permit['question_id'],
            origin_fault_sha256=row['sha256'], business_replayed=False))
    return True


def _recover_reply(cache_dir, tool, error):
    """One verified reply retry, never another serve/commit or business action."""
    from . import engine_core as ec, model_view, reply_io
    candidate = write_observation.reply_candidate()
    if candidate is None or write_observation.facts()['effect_phase'] != 'ACCEPTED':return False
    store = RunStore(cache_dir)
    with write_observation.maintenance(), store.lock():
        index=store.read_index()
        rows=json.loads((store.cache_dir/FILE).read_bytes()) if (store.cache_dir/FILE).exists() else []
        if any(row.get('tool')==tool and row.get('trace_id')==index['trace_id'] and row.get('progress_mark')==mark(index)
               and row.get('disposition') in ('REPLY_RECOVERY_ATTEMPTED','REPLY_RECOVERED') for row in rows):return False
        if not verify_accepted(cache_dir,candidate):return False
    fault=ec.EngineError('ENGINE_UNEXPECTED_EXCEPTION',describe(error),field=tool,
        example=dict(exception_type=type(error).__name__, point='accepted_reply'))
    row=record(cache_dir,tool,fault,disposition='REPLY_RECOVERY_ATTEMPTED',recovery=dict(
        index_sha256=candidate['index_sha256'], input_sha256=candidate['input_sha256']))
    if row is None:return False
    try:
        result=model_view.lean(candidate['result'])
        result['tool_reply_recovery']=dict(code='ACCEPTED_REPLY_RECOVERED_ONCE',receipt=FILE,
            business_replayed=False, original_error=str(error))
        reply_io.emit(reply_io.render(result, cache_dir,candidate['kind'],candidate['node']))
    except Exception:
        return False
    record(cache_dir,tool,fault,disposition='REPLY_RECOVERED',recovery=dict(attempt_sha256=row['sha256'],business_replayed=False))
    return True


def recheck_facts(index, row, *, authorized=False):
    passed=resolved(index,row)
    return dict(condition_result='PASSED' if passed else 'UNRESOLVED',
        recovery_result='BOUNDED_REENTRY_AUTHORIZED' if authorized else 'CONDITION_CLEARED' if passed else 'NOT_AUTHORIZED',
        root_cause='UNDETERMINED', error_code=row['error']['code'],
        checked_at=now_iso(), source_ref=FILE, fault_sha256=row.get('sha256'),
        progress_mark=mark(index), business_replayed=False)


def fault_description(row, language, *, assessment=None):
    zh=language=='zh'
    observed=row.get('write_observation') or {}
    phase=observed.get('effect_phase','UNKNOWN')
    labels={'NOT_STARTED':('本次尚未开始写入','No write started'),
        'ACCEPTED':('内核已接受；工具回复失败','Kernel accepted; tool reply failed'),
        'WRITES_VERIFIED':('已写文件读回通过；整体提交尚未确认','Written files verified; whole operation not accepted'),
        'STARTED_UNCONFIRMED':('写入已尝试；落盘结果未确认','Write attempted; effects not confirmed'),
        'PERSISTED_UNCONFIRMED':('文件已替换；读回尚未确认','File replaced; readback not confirmed')}
    stage=labels.get(phase,('写入阶段未知','Write phase unknown'))[0 if zh else 1]
    safe=bool((assessment or {}).get('safe'))
    text=(f"工具：{row.get('tool')}；阶段：{stage}。\n错误：{row['error']['code']} — {row['error'].get('message','')}\n"
        f"原始诊断：{FILE}；条件复核不等于根因已修复，已完成业务不重放。" if zh else
        f"Tool: {row.get('tool')}; stage: {stage}.\nError: {row['error']['code']} — {row['error'].get('message','')}\n"
        f"Original diagnostic: {FILE}. Recheck is not proof of root-cause repair; completed business is never replayed.")
    evidence = (assessment or {}).get('reply_evidence')
    if (assessment or {}).get('reply_mode') == 'HISTORICAL_PROJECTION':
        text += '\n'+('原段可信宿主返回已核验；本次只补只读说明和原回复引用，不输出旧PLAN/票据，不重做业务。' if zh else
                       'Original segment host return verified; recover only a read-only notice and original reply reference, never old plans/tickets or business.')
    if evidence:
        failed = ', '.join(k for k,v in evidence['checks'].items() if v is False)
        text += '\n'+(('原回复核验：' if zh else 'Saved reply evidence: ')+evidence['status']+
                      ('；未通过项：' if zh else '; failed checks: ')+(failed or 'none'))
        if evidence['status'] == 'VERIFIED_HISTORICAL_READ_ONLY':
            text += '\n'+('原完整回复存在且已核验；当前状态变化，旧PLAN/票据不能执行。只读位置：' if zh else
                           'The complete original reply exists and verifies; current state changed, old plans/tickets cannot execute. Read-only location: ')+evidence['reply_ref']
    if row['error']['code'] in ('ENGINE_UNEXPECTED_EXCEPTION','ENGINE_ORPHAN_COMMIT_INTERRUPTED') and not safe:
        text+='\n'+('本次缺少安全续写证据，不能继续；复核不会重试整条工具或覆盖旧临时文件。' if zh else
                     'This operation cannot continue safely: effects are unconfirmed. Recheck does not replay the tool or install an old temporary file.')
    elif safe:
        text+='\n'+('只有身份、缓存、票据和证据链复核通过后，一次人类授权才允许有限重入。' if zh else
                     'One human-authorized re-entry requires identity, cache, ticket and ledger verification.')
    request=observed.get('request') or {}
    if request.get('payload_ref'):
        text+='\n'+('原提交保全位置：' if zh else 'Preserved original payload: ')+request['payload_ref']
    known = {
        'RESUME_EXECUTOR_LIVENESS_UNKNOWN': ('旧执行者状态未核验；不得由不可达推断死亡。', 'Previous executor state is unverified; unreachable does not prove death.'),
        'ENGINE_UNEXPECTED_EXCEPTION': ('这是工具异常，不是业务结果判定；只有原写集核验通过才可有限补记。', 'This is a tool exception, not a business verdict; only verified original effects permit bounded recovery.'),
        'ENGINE_ORPHAN_COMMIT_INTERRUPTED': ('原工具在索引接受前退出；继续仅补已核验的原提交记账，不重做业务、不代答原业务门。', 'The original CLI ended before index acceptance; continue forwards verified Engine bookkeeping only, never business or a gate answer.'),
        'PROGRAM_VERSION_CHANGED': ('执行中的程序版本变化；先恢复原文件或结束本场，不授权新版本续跑。', 'The running program changed; restore its original files or end this run, not authorize a new version.')}
    explanation = known.get(row['error']['code'])
    text += '\n'+(explanation[0 if zh else 1] if explanation else
        ('原因尚未确定；保留原诊断，可选择结束本场。' if zh else 'Cause is undetermined; preserve diagnostics or end this run.'))
    return text, safe


def report_observations(cache_dir):
    try:return _report_observations(cache_dir)
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        from .engine_core import EngineError
        raise EngineError('ENGINE_FAULT_RECORD_INVALID','Recovery diagnostic cannot be parsed or verified; preserve it. Read-only diagnostic report remains available.') from exc


def _report_observations(cache_dir):
    """Verified machine recovery records, separately sourced from node anomalies."""
    out=[]
    from . import recovery_diagnostics
    from .run_store import read_bytes,_regular_path
    names=[FILE,'_atomic_replace_recoveries.jsonl']
    extra=Path(cache_dir)/'_atomic_replace_recoveries'
    if extra.exists():
        if extra.is_symlink() or not extra.is_dir():raise ValueError('diagnostic directory is not regular')
        names.extend(p.relative_to(cache_dir).as_posix() for p in sorted(extra.glob('*.json')))
    for name in names:
        path=Path(cache_dir)/name
        if not path.exists():continue
        if not _regular_path(path):raise ValueError('diagnostic path is not regular')
        raw=read_bytes(path)
        tail=None
        if name==FILE:rows=json.loads(raw)
        elif name.endswith('.jsonl'):rows,tail=recovery_diagnostics.rows(raw)
        else:rows=[json.loads(raw)]
        if not isinstance(rows,list):raise ValueError('invalid diagnostic store shape')
        for row in rows:
            key='sha256' if name==FILE else 'receipt_sha256'
            if row.get(key)!=seal({k:v for k,v in row.items() if k!=key}):
                from .engine_core import EngineError
                raise EngineError('ENGINE_FAULT_RECORD_INVALID','Recovery diagnostic checksum changed; preserve and stop.')
            out.append(dict(source_ref=name,source_sha256=hashlib.sha256(raw).hexdigest(),
                code='ATOMIC_REPLACE_RECOVERED' if name!=FILE else row.get('disposition') or row['error']['code'], record=row))
        if tail:
            out.append(dict(source_ref=name,source_sha256=hashlib.sha256(raw).hexdigest(),
                code='RECOVERY_DIAGNOSTIC_TRUNCATED_TAIL',record=tail))
    from . import partial_commit
    out.extend(partial_commit.recovery_observations(cache_dir))
    return out


def report_diagnostics(cache_dir):
    """Read-only disclosure never acts as a recovery authorization."""
    try:return report_observations(cache_dir)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        error=type(exc).__name__
    except Exception as exc:
        error=getattr(exc,'code',type(exc).__name__)
    out=[]
    names=[FILE,'_atomic_replace_recoveries.jsonl']
    directory=Path(cache_dir)/'_orphan_recoveries'
    if directory.exists() and _regular_path(directory):
        names.extend(p.relative_to(cache_dir).as_posix() for p in sorted(directory.glob('*.json')))
    for name in names:
        path=Path(cache_dir)/name
        if path.exists():
            raw=path.read_bytes()
            out.append(dict(source_ref=name,source_sha256=hashlib.sha256(raw).hexdigest(),
                code='RECOVERY_DIAGNOSTIC_UNVERIFIABLE',record=dict(verification='UNVERIFIABLE',bytes=len(raw),reason=error,
                recovery_authorized=False,business_result_not_replayed=True)))
    return out
