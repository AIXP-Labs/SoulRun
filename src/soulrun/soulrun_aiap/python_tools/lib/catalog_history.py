"""Accepted definitions survive replanning; they never authorize another execution."""
import copy


def definitions(index):
    active=index.get('catalog',[])
    names={e['name'] for e in active}
    return active+[e for n,e in index.get('catalog_history',{}).items() if n not in names]


def remember(index):
    names={key.partition('@')[0] for key,state in index.get('nodes',{}).items() if state.get('cache_sha256')}
    if not names:return
    history=index.setdefault('catalog_history',{})
    for entry in index.get('catalog',[]):
        name=entry['name']
        if name not in names:continue
        prior=history.get(name)
        if prior and any(prior.get(k)!=entry.get(k) for k in ('kind','parent','depth','doc','task','node')):
            from .engine_core import EngineError
            raise EngineError('CATALOG_DEFINITION_CHANGED',f'Accepted definition changed: {name}; preserve evidence and stop.')
        if not prior:history[name]=copy.deepcopy(entry)


def without_previous_subtrees(entries,names):
    out=[];skip_depth=None
    for entry in entries:
        if skip_depth is not None:
            if entry['depth']>skip_depth:continue
            skip_depth=None
        if entry['name'] in names:
            skip_depth=entry['depth'];continue
        out.append(entry)
    return out
