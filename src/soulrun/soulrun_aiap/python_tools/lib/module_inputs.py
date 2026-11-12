"""Bounded program-owned call configuration, separate from business history."""
import copy
import json
import math
import re
from .run_store import sha256_bytes


def values(view):
    extra = (view or {}).get('extra') or {}
    if 'module_inputs' not in extra:
        return None
    supplied = extra['module_inputs']
    valid = isinstance(supplied, dict) and 0 < len(supplied) <= 16
    if valid:
        for key,value in supplied.items():
            scalar = value is None or type(value) is bool or type(value) is int or (
                type(value) is float and math.isfinite(value)) or (
                isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',value))
            valid = valid and isinstance(key,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',key) and scalar
    if not valid or ('module' in view and not view['module']):
        from .engine_core import EngineError
        raise EngineError('MODULE_INPUTS_INVALID',
            'A module call may declare 1..16 literal scalar configuration values; no paths, expressions or history. '
            'Correct the program declaration, never default an invalid call to a whole run.',field='module_inputs')
    return copy.deepcopy(supplied)


def attach(program,index,frame,reply):
    from . import engine_core as ec
    parent = ec._catalog_entry(index,frame['parent'])
    view = ec._view_for(program,parent) if parent else None
    supplied = values(view)
    if supplied is None:
        return
    target = view['module']
    if any(target[key] != frame[key] for key in ('doc','task','ns')):
        raise ec.EngineError('MODULE_INPUTS_INVALID','Call configuration does not bind this module frame.')
    reply['input_authority']['module_inputs'] = supplied
    reply['frame']['module_input_source'] = dict(node=frame['parent'],visit=frame['parent_visit'],
        file=view['file'],task=view['task'],target=dict(doc=target['doc'],task=target['task']),
        sha256=sha256_bytes(json.dumps(supplied,sort_keys=True,separators=(',',':'),allow_nan=False).encode()),
        rule='Program-owned literal execution configuration for this call. Consume unchanged; not Writer data, old scores or permission to read parent history.')
