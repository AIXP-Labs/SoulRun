"""Prepare privately; publish a ticket only after its index authority is read back."""
from contextvars import ContextVar
_pending=ContextVar('engine_ticket_publication',default=())

def note(store,ticket):
    pair=(str(store.cache_dir),ticket)
    if pair not in _pending.get():_pending.set(_pending.get()+(pair,))

def path(store,ticket):
    if not __import__('re').fullmatch(r'd[0-9]+-[0-9a-f]+',ticket):
        from .engine_core import EngineError
        raise EngineError('DISPATCH_TICKET_INVALID','Invalid prepared ticket identity.')
    return store.cache_dir/f'_ticket_prepare.{ticket}.json'

def read(store,ticket):
    actual=store.dispatch_path(ticket)
    if not actual.exists():note(store,ticket)
    return store.read_json(actual if actual.exists() else path(store,ticket))

def records(index):
    out={}
    def walk(value,owner):
        if isinstance(value,dict):
            if value.get('ticket'):out[value['ticket']]=dict(value,_owner_key=owner)
            for old in value.get('history') or []:walk(old,owner)
    for key,row in index.get('nodes',{}).items():walk(row.get('dispatch'),key)
    return out

def verify(store,index,ticket,row,authority, *, allow_retirement=False):
    from .engine_core import EngineError
    from .run_store import sha256_bytes
    owner,_,visit=authority['_owner_key'].partition('@')
    node=row.get('node')
    if row.get('ticket')!=ticket or row.get('trace_id')!=index['trace_id'] \
            or sha256_bytes(row.get('bootstrap','').encode())!=row.get('bootstrap_sha256') \
            or authority.get('bootstrap_sha256') and authority['bootstrap_sha256']!=row['bootstrap_sha256'] \
            or row.get('scope_root')!=authority.get('scope_root') \
            or f'node={node}' not in row.get('bootstrap','').splitlines() \
            or f'ticket={ticket}' not in row.get('bootstrap','').splitlines() \
            or node==owner and row.get('visit')!=int((visit or '1').removeprefix('v')) \
            or node!=owner and (not str(node or '').startswith(owner+'/') or not row.get('scope_root')):
        raise EngineError('DISPATCH_TICKET_INVALID','Ticket content does not match accepted index authority.')
    actual=row.get('state','ISSUED');wanted=authority.get('state')
    paused_retirement = actual=='CLAIMED' and authority.get('paused_at') and row.get('paused_at')==authority['paused_at']
    unused_retirement = actual=='ISSUED' and authority.get('closed_reason') in {'gate_handoff','segment_handoff'} and not row.get('claimed_at')
    # docs/05SoulRun 87: the ticket a human-chosen replacement retires, issued or claimed, is retired with it.
    replaced_retirement = actual in ('ISSUED','CLAIMED') and authority.get('closed_reason') in ('human_replacement', 'identity_unverified')
    if actual!=wanted and not (allow_retirement and wanted=='ABANDONED' and (paused_retirement or unused_retirement or replaced_retirement)):
        raise EngineError('DISPATCH_TICKET_INVALID','Ticket state conflicts with accepted index authority.')

def publish(store,index, *, registered=False):
    from .engine_core import EngineError
    pending=[p for p in _pending.get() if p[0]==str(store.cache_dir)]
    if not pending and not registered:return
    authorities=records(index)
    names=list(authorities) if registered else [p[1] for p in pending]
    # A continuation retires its prior right before publishing the new one.
    for ticket,authority in authorities.items():
        if authority.get('state')!='ABANDONED' or not (authority.get('paused_at') or authority.get('closed_reason') in {'gate_handoff','segment_handoff','human_replacement','identity_unverified'}):continue
        actual=store.dispatch_path(ticket)
        if not actual.exists():raise EngineError('DISPATCH_TICKET_INVALID','Prior continuation ticket is missing.')
        row=store.read_json(actual)
        verify(store,index,ticket,row,authority,allow_retirement=True)
        if row.get('state')!='ABANDONED':
            row['state']='ABANDONED'
            store.write_json(actual,row)
    for ticket in names:
        authority=authorities.get(ticket)
        if not authority:continue
        actual=store.dispatch_path(ticket)
        if actual.exists():
            verify(store,index,ticket,store.read_json(actual),authority)
            continue
        prepared=path(store,ticket)
        if not prepared.exists():
            raise EngineError('DISPATCH_TICKET_INVALID','Registered ticket has no private preparation.')
        row=store.read_json(prepared)
        verify(store,index,ticket,row,authority)
        if row.get('claimed_at') or row.get('committed_at'):
            raise EngineError('DISPATCH_TICKET_INVALID','Unpublished ticket already has execution facts.')
        store.write_json_once(actual,row)
    _pending.set(tuple(p for p in _pending.get() if p not in pending))
