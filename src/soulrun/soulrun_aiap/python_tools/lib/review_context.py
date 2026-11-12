"""Explicit short run facts for blind review, never an upstream report grant."""
import json
from . import blind_review as br


def short(value):
    return isinstance(value, str) and 0 < len(value) <= 64 and all(ord(c) >= 32 for c in value)


def declaration(rows):
    invalid = lambda: br.fail('BLIND_REVIEW_CONTEXT_INVALID',
        'Context requires 1..8 distinct named output scalar selectors with explicit allowed values.')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
        invalid()
    names = []
    for row in rows:
        if not isinstance(row, dict) or not {'name','node','field','path','allowed'} <= set(row) \
                or set(row) - {'name','node','field','path','allowed','choices'}:
            invalid()
        from . import independent_inputs as ii
        ii.declaration(dict(isolation='fresh_agent', input_scope=dict(schema_version=1, constants={},
            values=[{k:row[k] for k in ('name','node','field','path')}])))
        allowed = row['allowed']
        if row['field'] != 'output' or not isinstance(allowed, list) or not 1 <= len(allowed) <= 32 \
                or not all(short(v) for v in allowed) or len(set(allowed)) != len(allowed):
            invalid()
        choices = row.get('choices')
        if choices is not None and (not isinstance(choices, dict) or not 1 <= len(choices) <= 32
                or any(not short(k) or not short(v) or v not in allowed for k,v in choices.items())):
            invalid()
        names.append(row['name'])
    if len(names) != len(set(names)):
        invalid()
    return rows


def capture(store, index, selectors):
    from . import engine_core as ec, independent_inputs as ii
    result = {}
    caches = ec._prev_business_caches(store, index)
    for selector in declaration(selectors):
        cache = next((c for c in reversed(caches) if c['node'] == selector['node']), None)
        if cache is None:
            br.fail('BLIND_REVIEW_CONTEXT_NOT_READY', 'Declared run fact has no accepted source.')
        state = index['nodes'].get(ec._node_key(cache['node'], cache['visit']), {})
        if state.get('status') != 'COMMITTED':
            br.fail('BLIND_REVIEW_CONTEXT_NOT_READY', 'Run fact source is not terminally accepted.')
        source_entry = ec._catalog_entry(index, cache['node'])
        path = ec._cache_path_for(store, index, source_entry, cache['visit'])
        raw, meta = br._bytes(path)
        if meta['sha256'] != ec._input_identity(store, index, cache)['sha256']:
            br.fail('BLIND_REVIEW_CONTEXT_CHANGED', 'Accepted run fact source changed.')
        original = json.loads(raw)
        payload = ec._latest_payload(original)
        value = payload.get('output')
        try:
            for step in ec._JSON_PATH_STEP_RE.findall(selector['path']):
                value = ii._selected_value(store, index, value, payload)
                value = ec._json_path_select(value, [step], 'blind_inputs.context.'+selector['name'])
            value = ii._selected_value(store, index, value, payload)
        except ec.EngineError as exc:
            br.fail('BLIND_REVIEW_CONTEXT_NOT_READY', 'Declared run fact is unavailable; no whole-output fallback.',
                example=exc.code)
        if not short(value) or value not in selector['allowed']:
            br.fail('BLIND_REVIEW_CONTEXT_NOT_READY', 'Run fact is missing, unrecognized or not a declared short scalar.')
        decisions = []
        for event in index['gate']['history'] if selector.get('choices') else []:
            if event.get('node') != cache['node'] or event.get('resolution_kind') not in ('chosen','free_text'):
                continue
            gate_path = store.gate_path(event['question_id'])
            gate_raw, gate_meta = br._bytes(gate_path)
            gate = json.loads(gate_raw)
            if gate.get('visit') != cache['visit']:
                continue
            accepted_answer = next((record.get('gate_answer') for record in [original, *original.get('continuations', [])]
                if (record.get('gate_answer') or {}).get('question_id') == gate.get('question_id')), None)
            if any(gate.get(k) != event.get(k) for k in ('question_id','node','resolution_kind','answered_at')) \
                    or accepted_answer is None or any(accepted_answer.get(k) != gate.get(k)
                        for k in ('node','visit','resolution_kind','chosen_intent')) \
                    or not gate.get('answered_at') or gate.get('consumed_by_commit') is not True \
                    or gate.get('resolution_kind') != 'chosen' \
                    or selector['choices'].get(gate.get('chosen_intent')) != value:
                br.fail('BLIND_REVIEW_CONTEXT_CONFLICT', 'Accepted choice and declared run fact disagree or are not uniquely resolved.')
            decisions.append(dict(question_id=gate['question_id'], chosen_intent=gate['chosen_intent'],
                answered_at=gate['answered_at'], cache=gate_path.relative_to(store.cache_dir).as_posix(),
                sha256=gate_meta['sha256']))
        result[selector['name']] = dict(value=value, source=dict(node=cache['node'], visit=cache['visit'],
            field='output', path=selector['path'], cache=path.relative_to(store.cache_dir).as_posix(),
            sha256=meta['sha256']), decisions=decisions)
    return result


def run_identity(store, index):
    return br.digest([str(store.cache_dir.resolve()), index['trace_id'], index['started_at']])


def verify(store, binding):
    if 'context_inputs' not in binding:
        return
    if binding.get('context_run') != run_identity(store, store.read_index()):
        br.fail('BLIND_REVIEW_CONTEXT_CHANGED', 'Run fact binding belongs to another run.')
    for row in binding['context_inputs'].values():
        for source in (row['source'], *row['decisions']):
            path = store.cache_dir / source['cache']
            if not path.resolve().is_relative_to(store.cache_dir.resolve()):
                br.fail('BLIND_REVIEW_CONTEXT_CHANGED', 'Run fact source escaped this run.')
            try:
                _, meta = br._bytes(path)
            except (OSError, ValueError):
                br.fail('BLIND_REVIEW_CONTEXT_CHANGED', 'Run fact source is unavailable.')
            if meta['sha256'] != source['sha256']:
                br.fail('BLIND_REVIEW_CONTEXT_CHANGED', 'Run fact or accepted choice changed; do not rebind old review.')
