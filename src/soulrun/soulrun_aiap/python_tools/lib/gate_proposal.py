"""Pure proposal projection. Not run admission, evidence validation or human authority."""
import copy
import hashlib
import json

from . import hsaw_gate


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def project(payload, *, node, language):
    from .engine_core import _normalize_gate_shape
    if not isinstance(payload, dict) or not isinstance(node, str) or not node.strip():
        raise ValueError('GATE_PROPOSAL_INVALID')
    source = copy.deepcopy(payload)
    if not isinstance(source.get('gate'), dict) or not isinstance(source.get('hsaw_items', []), list):
        raise ValueError('GATE_PROPOSAL_INVALID')
    options = source['gate'].get('options')
    if not isinstance(options, list) or not options or any(not isinstance(o, dict)
        or any(not isinstance(o.get(k), str) or not o[k].strip() for k in ('kind','intent','label'))
        or not isinstance(o.get('aliases', []), list) for o in options):
        raise ValueError('GATE_PROPOSAL_OPTIONS_INVALID')
    if any(not isinstance(item, dict) for item in source.get('hsaw_items', [])):
        raise ValueError('GATE_PROPOSAL_ITEMS_INVALID')
    notes = []
    hsaw_gate.normalize_shape(source, notes)
    hsaw_gate.align_items(source.get('hsaw_items', []), notes, language)
    if hsaw_gate.hard_fail_items(source.get('hsaw_items', [])):
        raise ValueError('HSAW_HARD_FAIL_NO_PROPOSAL')
    _normalize_gate_shape(source['gate'], notes)
    original = copy.deepcopy(source['gate']['options'])
    gate = source['gate']
    if hsaw_gate.freeze_items(source.get('hsaw_items', [])):
        gate = hsaw_gate.completed_gate(gate, source['hsaw_items'], node, language, notes)
    intents = [o['intent'] for o in gate['options']]
    if len(set(intents)) != len(intents):
        raise ValueError('GATE_PROPOSAL_DUPLICATE_INTENT')
    return dict(status='GATE_PROPOSAL', proposal_sha256=digest(payload), gate=gate,
        original_options=original, added_intents=[i for i in intents if i not in {o['intent'] for o in original}],
        notes=notes, authorization=False, semantic_authorization_verified=False,
        scope='Draft only. Actual commit revalidates current run, findings and gate; human answer is still required.')
