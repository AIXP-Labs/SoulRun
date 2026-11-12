"""Canonical dispatch return references, separate from observed parent publication."""
from __future__ import annotations

from collections import Counter
import re

_REF = re.compile(r'\u27e6engine:(\d{1,9})/([A-Za-z0-9][A-Za-z0-9_.-]{0,200}\.txt)\u27e7')
_PREFIXES = ('plan.', 'node.', 'pause.', 'menu.')


def canonical_refs(store, values):
    result = []
    for value in values if isinstance(values, list) else []:
        match = _REF.fullmatch(value) if isinstance(value, str) else None
        if not match or match[1] != store.cache_dir.name or '..' in match[2] or not match[2].startswith(_PREFIXES):
            continue
        path = store.public_dir / match[2]
        try:
            valid = (not path.is_symlink() and path.is_file()
                     and path.resolve().is_relative_to(store.public_dir.resolve()))
        except OSError:
            valid = False
        if not valid:
            continue
        if value not in result:
            result.append(value)
    return result


def previous(store, index, fallback_ref):
    """Read-only retry view; it never claims these references were publicly emitted."""
    from .engine_core import _node_key
    last = index['completed'][-1]
    key = _node_key(last['name'], last['visit'])
    record = (index.get('nodes', {}).get(key) or {}).get('dispatch') or {}
    refs = []
    for segment in [*(record.get('history') or []), record]:
        refs.extend(segment.get('public_refs') or [])
    refs = canonical_refs(store, refs + [fallback_ref])
    return dict(root=dict(node=last['name'], visit=last['visit']), public_refs=refs,
                basis='canonical_dispatch_ledger_not_delivery_ack',
                instruction='Tool results are not public delivery. Present missing public_refs in order once before the next PLAN; do not replay work.')


def observation(store, index, text, history, *, message_eligible=True):
    """Literal presence and standalone layout are facts, neither is DOM delivery proof."""
    expected = []
    for node in index.get('nodes', {}).values():
        record = node.get('dispatch') or {}
        if record.get('mode') != 'agent' or record.get('actor') != 'sub_agent':
            continue
        for segment in [*(record.get('history') or []), record]:
            expected.extend(segment.get('public_refs') or [])
    expected = canonical_refs(store, expected)
    public = text if message_eligible else ''
    literals = [match[0] for match in _REF.finditer(public)]
    observed = canonical_refs(store, literals)
    standalone = canonical_refs(store, [line.strip() for line in public.splitlines()])
    prior = []
    for row in history:
        obs = row.get('dispatch_publication') if isinstance(row, dict) else None
        if isinstance(obs, dict) and obs.get('schema') == 'dispatch_publication.v1' and obs.get('message_eligible') is not False:
            prior.extend(obs.get('observed_refs') or [])
    cumulative = canonical_refs(store, prior + observed)
    counts = Counter(literals)
    return dict(schema='dispatch_publication.v1',
                basis='literal_parent_message_refs_since_observation_schema_not_dom', message_eligible=message_eligible,
                expected_refs=expected, observed_refs=observed, cumulative_observed_refs=cumulative,
                unobserved_refs=[ref for ref in expected if ref not in cumulative],
                standalone_refs=standalone, present_not_standalone_refs=[ref for ref in observed if ref not in standalone],
                duplicate_literal_refs_in_observed_text=[ref for ref in observed if counts[ref] > 1],
                host_delivery_verified=False, dom_verified=False, verdict=None)
