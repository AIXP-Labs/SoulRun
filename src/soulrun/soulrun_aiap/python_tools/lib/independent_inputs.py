"""Opt-in fresh-agent field snapshots, not a filesystem or Provider memory sandbox."""
import copy
import json
import re
from pathlib import Path

from . import blind_review


def fail(code,text,**kw):
    from .engine_core import EngineError
    raise EngineError(code,text,**kw)


def declaration(row):
    if 'input_scope' not in row:return None
    spec=row['input_scope']
    invalid=lambda:fail('INDEPENDENT_INPUT_SCOPE_INVALID','input_scope requires fresh_agent, schema_version=1, constants and explicit output/vars subfields.')
    if row.get('isolation')!='fresh_agent' or not isinstance(spec,dict) or set(spec)!={'schema_version','constants','values'} \
            or type(spec['schema_version']) is not int or spec['schema_version']!=1 \
            or not isinstance(spec['constants'],dict) or not isinstance(spec['values'],list):invalid()
    names=list(spec['constants'])
    for item in spec['values']:
        if not isinstance(item,dict) or set(item)!={'name','node','field','path'} \
                or item['field'] not in ('output','vars') or not isinstance(item['node'],str) or not item['node'] \
                or not isinstance(item['path'],str) or len(item['path'])>2048 or not re.fullmatch(
                    r'(?:[^.\[\]]+|\[[0-9]+\])(?:\.[^.\[\]]+|\[[0-9]+\])*',item['path']):invalid()
        names.append(item['name'])
    if not 1<=len(names)<=32 or any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',n) for n in names):invalid()
    if len(set(names))!=len(names):invalid()
    try:json.dumps(spec,allow_nan=False)
    except (ValueError,TypeError):invalid()
    return spec


def _selected_value(store,index,value,payload,trail=()):
    from . import engine_core as ec
    if isinstance(value,dict) and ec.ADDRESS_REF_KEY in value:
        identity=blind_review.digest(value)
        if identity in trail or len(trail)>=16:
            fail('INDEPENDENT_INPUT_FIELD_MISSING','Selected address chain is cyclic or exceeds 16 hops; no fallback.')
        owner=payload
        resolved=value.get(ec.ADDRESS_REF_RESOLVED) or {}
        if resolved.get('kind')=='input':
            try:
                entry=ec._catalog_entry(index,resolved['node'])
                key=ec._node_key(resolved['node'],resolved['visit'])
                path=ec._cache_path_for(store,index,entry,resolved['visit'])
                raw=store.read_bytes(path)
                if ec.sha256_bytes(raw)!=index['nodes'][key]['cache_sha256']:
                    fail('INDEPENDENT_INPUT_FIELD_MISSING','Nested input cache changed; no fallback.')
                owner=ec._payload_at_revision(json.loads(raw),resolved['revision'])
            except (KeyError,TypeError,ValueError,IndexError,OSError):
                fail('INDEPENDENT_INPUT_FIELD_MISSING','Nested input source is unavailable; no fallback.')
        selected=ec._deref_address_refs(store,{'selected':value},payload)['selected']
        if selected==value:
            fail('INDEPENDENT_INPUT_FIELD_MISSING','Selected address is unresolved; no fallback.')
        return _selected_value(store,index,selected,owner,trail+(identity,))
    if isinstance(value,dict):
        return {k:_selected_value(store,index,v,payload,trail) for k,v in value.items()}
    if isinstance(value,list):
        return [_selected_value(store,index,v,payload,trail) for v in value]
    return value


def bind(store,index,program,entry,visit):
    from . import dispatch_budget,engine_core as ec
    rows,_=dispatch_budget.requirements(program)
    row=next((r for r in rows if r['file']==(entry.get('doc') or program.entry_file) and r['node']==ec._bare(entry)),None)
    spec=declaration(row) if row else None
    if spec is None:return None
    values={k:dict(value=copy.deepcopy(v),source=None) for k,v in spec['constants'].items()}
    caches=ec._prev_business_caches(store,index)
    for selector in spec['values']:
        cache=next((c for c in reversed(caches) if c['node']==selector['node']),None)
        if cache is None:
            fail('INDEPENDENT_INPUT_SOURCE_MISSING','Declared source has not been committed.',field='input_scope.'+selector['name'])
        identity=ec._input_identity(store,index,cache)
        source_entry=ec._catalog_entry(index,cache['node'])
        source_path=ec._cache_path_for(store,index,source_entry,cache['visit'])
        raw=store.read_bytes(source_path)
        if ec.sha256_bytes(raw)!=identity['sha256']:
            fail('INDEPENDENT_INPUT_SOURCE_CHANGED','Declared source cache changed before binding.')
        payload=ec._latest_payload(cache)
        value=payload.get(selector['field'])
        try:
            for step in ec._JSON_PATH_STEP_RE.findall(selector['path']):
                if selector['field']=='output' and isinstance(value,dict) and ec.ADDRESS_REF_KEY in value:
                    value=_selected_value(store,index,value,payload)
                value=ec._json_path_select(value,[step],'input_scope.'+selector['name'])
            if selector['field']=='output':
                value=_selected_value(store,index,value,payload)
            unresolved=[]
            ec._address_markers(value,'input_scope',unresolved)
            if unresolved:
                fail('INDEPENDENT_INPUT_FIELD_MISSING','Selected value still contains an unresolved address; no source-cache fallback.')
        except ec.EngineError as exc:
            fail('INDEPENDENT_INPUT_FIELD_MISSING','Declared field is unavailable; do not read the whole source as fallback.',
                 field='input_scope.'+selector['name'],expected=selector['path'],example=exc.as_dict())
        values[selector['name']]=dict(value=copy.deepcopy(value),source=dict(node=cache['node'],visit=cache['visit'],
            sha256=identity['sha256'],cache=source_path.relative_to(store.cache_dir).as_posix(),field=selector['field'],path=selector['path']))
    root=dict(node=entry['name'],visit=visit)
    binding=dict(schema_version=1,root=root,run=ec.sha256_bytes((str(store.cache_dir.resolve())+index['trace_id']+index['started_at']).encode()),
        declaration_sha256=blind_review.digest(spec),values=values,isolation='engine_api_field_projection_not_memory_or_filesystem_sandbox')
    if len(json.dumps(binding,ensure_ascii=False).encode())>blind_review.MAX_BYTES:
        fail('INDEPENDENT_INPUT_SCOPE_INVALID','Declared values exceed the existing bounded input size.')
    name='_inputs.'+blind_review.digest(root)[:24]+'.json'
    path=store.cache_dir/name
    if path.exists():
        saved=store.read_json(path)
        if saved!=binding:fail('INDEPENDENT_INPUT_BINDING_CHANGED','Existing input snapshot cannot be rebound or overwritten.')
    else:store.write_json_once(path,binding)
    return dict(path=name,sha256=blind_review.digest(binding))


def load(store,ref):
    from . import engine_core as ec
    try:
        if not isinstance(ref,dict) or not re.fullmatch(r'_inputs\.[a-f0-9]{24}\.json',ref.get('path','')):
            raise ValueError('path')
        raw,_=blind_review._bytes(store.cache_dir/ref['path'])
        binding=json.loads(raw)
        if blind_review.digest(binding)!=ref.get('sha256') or not isinstance(binding.get('values'),dict):
            raise ValueError('digest')
        sources={(r['source']['cache'],r['source']['sha256']) for r in binding['values'].values() if r['source']}
        for relative,sha in sources:
            path=store.cache_dir/relative
            if not path.resolve().is_relative_to(store.cache_dir.resolve()):raise ValueError('source path')
            data,_=blind_review._bytes(path)
            if ec.sha256_bytes(data)!=sha:
                fail('INDEPENDENT_INPUT_SOURCE_CHANGED','Input source changed; do not silently rebind a resumed executor.')
        return binding
    except ec.EngineError as exc:
        if exc.code=='INDEPENDENT_INPUT_SOURCE_CHANGED':raise
        fail('INDEPENDENT_INPUT_BINDING_CHANGED','Bound input snapshot is linked, unavailable or changed.')
    except (ValueError,KeyError,TypeError,OSError):
        fail('INDEPENDENT_INPUT_BINDING_CHANGED','Bound input snapshot is unavailable or changed.')


def active(store,index):
    from . import engine_core as ec
    current=index.get('current') or {}
    entry=ec._catalog_entry(index,current.get('name'))
    _,owner=ec._self_dispatch(index,entry,current['visit']) if entry else (None,None)
    ref=(owner or {}).get('input_binding')
    return load(store,ref) if ref else None


def refs(binding):
    sha=blind_review.digest(binding)
    return [dict(kind='scoped_value',name=name,ref=f'scoped:{sha}:{name}',sha256=blind_review.digest(row['value']))
        for name,row in binding['values'].items()]


def read(binding,ref,field,offset,limit,path=None):
    if field!='output':fail('INPUT_REF_INVALID','Scoped values expose their selected output only, not the source cache.')
    names={r['ref']:r['name'] for r in refs(binding)}
    if ref not in names:fail('INPUT_REF_INVALID','Scoped input is outside this root binding.')
    value=copy.deepcopy(binding['values'][names[ref]]['value'])
    from . import engine_core as ec
    if path is not None:value=ec._json_path_select(value,path,'input_path')
    encoded=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,separators=(',',':'))
    if offset>len(encoded):fail('INPUT_REF_INVALID','Offset is beyond the selected value.')
    end=min(len(encoded),offset+limit);complete=offset==0 and end==len(encoded)
    return dict(status='INPUT',kind='scoped_value',field='output',encoding='text',offset=offset,total_chars=len(encoded),
        complete=complete,next_offset=end if end<len(encoded) else None,value=value if complete else None,
        text=None if complete else encoded[offset:end],sha256=blind_review.digest(binding['values'][names[ref]]['value']))


def allows(binding,cache,field=None,path=None):
    if blind_review.owns(cache,binding):return True
    return any(row['source'] and row['source']['node']==cache['node'] and row['source']['visit']==cache['visit']
        and row['source']['field']==field and row['source']['path']==path for row in binding['values'].values())


def filter_reply(store,index,reply):
    binding=active(store,index)
    if not binding or reply.get('input_authority') is None:return reply
    from . import engine_core as ec
    ia=reply['input_authority']
    own=[c for c in ec._prev_business_caches(store,index) if blind_review.owns(c,binding)]
    catalog=refs(binding)
    projected={}
    for item in catalog:
        value=binding['values'][item['name']]['value']
        text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,separators=(',',':'))
        projected[item['name']]=copy.deepcopy(value) if len(text)<=768 else dict(value_complete=False,total_chars=len(text),read_input_ref=item['ref'])
    ia.update(user_message=None,prev_node_summary=None,context=projected,
        input_refs=refs(binding)+ec._input_refs(store,index,own))
    prefix=ia.get('parent_prefix')
    if prefix and not (prefix.get('node')==binding['root']['node'] and prefix.get('visit')==binding['root']['visit']):ia.pop('parent_prefix',None)
    ia['input_catalog'].update(total=len(ia['input_refs']),has_more=False)
    required=ia.get('required_fields',{})
    ia['required_fields']=ec._required_fields_status(required.get('present',[])+required.get('missing',[]),own,ia['context'])
    ia['scoped_inputs']=dict(root=binding['root'],isolation=binding['isolation'],binding_sha256=blind_review.digest(binding),
        rule='Use only declared values and this root\'s own accepted records. value_complete=false is a directory, not the value: read its scoped ref, optionally select a path inside it; join required pages until complete. Missing inputs stop; never substitute the whole upstream result. HSAW and applicable human instructions remain authoritative.')
    for key in ('human_conditions','human_compliance_records'):ia.pop(key,None)
    if reply.get('frame'):reply['frame'].update(parent_steps=[],siblings=[])
    if reply.get('module'):reply['module']={k:v for k,v in reply['module'].items() if k in ('note','status')}
    reply['source_support_candidates']=[]
    return reply
