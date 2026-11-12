"""Missing decision prose: one resubmission, then an Engine-owned human gate."""
from .run_store import RunStore,atomic_write_bytes,dumps,sha256_bytes,now_iso
FILE='_gate_delivery.json'

def current(cache_dir,index):
    from .engine_core import EngineError
    path=RunStore(cache_dir).cache_dir/FILE
    if not path.exists():return None
    try:
        rows=__import__('json').loads(path.read_bytes())
        if not isinstance(rows,list):raise ValueError('not a list')
        previous=None
        for row in rows:
            if row['previous_sha256']!=previous or row['sha256']!=sha256_bytes(dumps({k:v for k,v in row.items() if k!='sha256'}).encode()):raise ValueError('invalid chain')
            previous=row['sha256']
        match=[r for r in rows if r['trace_id']==index['trace_id'] and r['node']==index['current']['name'] and r['visit']==index['current']['visit']]
        return match[-1] if match and match[-1]['state']!='RESOLVED' else None
    except (OSError,ValueError,TypeError,KeyError):
        raise EngineError('ENGINE_FAULT_RECORD_INVALID','Gate delivery record cannot be verified; preserve and stop.')

def append(cache_dir,index,**fields):
    store=RunStore(cache_dir);path=store.cache_dir/FILE
    current(cache_dir,index)
    rows=store.read_json(path) if path.exists() else []
    row=dict(owner='execute_engine_gate_delivery',trace_id=index['trace_id'],engine_version=index['engine_version'],
        node=index['current']['name'],visit=index['current']['visit'],at=now_iso(),
        previous_sha256=rows[-1]['sha256'] if rows else None,**fields)
    row['sha256']=sha256_bytes(dumps(row).encode());rows.append(row)
    atomic_write_bytes(path,dumps(rows).encode());return row

def shape(payload):
    gate=payload.get('gate') or {}
    return sha256_bytes(dumps({k:gate.get(k) for k in ('options','recommendation','conditional_reply')}).encode())

def missing(store,node,payload):
    from .engine_core import EngineError
    index=store.read_index();old=current(store.cache_dir,index)
    attempts=(old or {}).get('attempts',0)+1
    allowance=(old or {}).get('allowance',2)
    row=append(store.cache_dir,index,state='NEEDS_TEXT',attempts=attempts,allowance=allowance,
        menu_shape_sha256=(old or {}).get('menu_shape_sha256') or shape(payload))
    exhausted=attempts>=allowance
    raise EngineError('GATE_TEXT_DELIVERY_EXHAUSTED' if exhausted else 'GATE_TEXT_NOT_RECEIVED',
        'The complete decision prose was not received. Resubmit the original gate inline; completed business is not repeated. '
        +('The Engine now asks the human to grant one further delivery attempt or end.' if exhausted else 'One correction attempt remains; no simplified business menu is authorized.'),
        field='gate',expected='original question, explanation, advice and closing inline, or :::gate '+node+' followed by :::',
        example=dict(delivery_attempt=attempts,source_ref=FILE,receipt_sha256=row['sha256']))

def require(cache_dir,index,*,node=None,payload=None):
    from .engine_core import EngineError
    old=current(cache_dir,index)
    if old and (node!=old['node'] or (payload is not None and (not payload.get('gate') or shape(payload)!=old['menu_shape_sha256']))):
        raise EngineError('GATE_TEXT_PENDING','This occurrence is frozen for original gate delivery; no next-node or unrelated commit is authorized.',field=FILE)

def authorize(cache_dir,index,qid,answer):
    old=current(cache_dir,index)
    if not old or old['attempts']<old['allowance']:return False
    append(cache_dir,index,state='NEEDS_TEXT',attempts=old['attempts'],allowance=old['attempts']+1,
        menu_shape_sha256=old['menu_shape_sha256'],human_question_id=qid,human_answer_original=answer)
    return True

def accepted(store,result):
    if result.get('status')!='WAITING_USER':return
    index=store.read_index();old=current(store.cache_dir,index)
    if old:
        append(store.cache_dir,index,state='RESOLVED',attempts=old['attempts'],allowance=old['allowance'],
               menu_shape_sha256=old['menu_shape_sha256'],business_question_id=result['gate']['question_id'])
