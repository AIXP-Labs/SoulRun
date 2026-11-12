"""Readjudication uses verified decisions of this run, never cross-run permission."""
from __future__ import annotations

import copy
import re

from . import hsaw_gate as hg


def _files(item):
    return {str(p).replace('\\', '/').casefold() for p in item.get('affected_files') or []}


def _identity(item):
    return (item.get('category'), item.get('scope'),
            re.sub(r'[\W_]+', '', item.get('title', '').casefold()), frozenset(_files(item)))


def review(items, index, read_gate, read_item):
    """Return prior answers and preserved proposals; callbacks verify accepted disk evidence."""
    if not hg.hard_fail_items(items):
        return []
    problems = hg.verify_register(index)
    if problems:
        raise hg.HsawError('HSAW_REGISTER_INTEGRITY', problems[0])
    register = index.get('hsaw_register') or []
    discovered = {r['id']: r for r in register if r.get('kind') == 'discovered'}
    opened = {r['question_id']: r for r in register if r.get('kind') == 'gate_opened'}
    prior = []
    for answer in register:
        if answer.get('kind') != 'gate_answered' or answer.get('resolution_kind') != 'chosen':
            continue
        qid = answer['question_id']
        event = opened.get(qid)
        gate = read_gate(qid)
        if (not event or gate.get('source') != hg.GATE_SOURCE or gate.get('resolution_kind') != 'chosen'
                or gate.get('node') != event.get('node') or gate.get('visit') != event.get('visit')
                or gate.get('answer_text') != answer.get('answer')
                or not isinstance(gate.get('answer_text_original'), str)
                or gate['answer_text_original'].strip() != gate.get('answer_text')
                or gate.get('chosen_intent') != answer.get('chosen_intent')
                or (gate.get('hsaw') or {}).get('item_ids') != event.get('item_ids')):
            raise hg.HsawError('HSAW_DECISION_EVIDENCE_INVALID', f'{qid}: gate and register differ')
        for item_id in event['item_ids']:
            discovery = discovered.get(item_id)
            if not discovery:
                raise hg.HsawError('HSAW_DECISION_EVIDENCE_INVALID', f'{qid}: discovery missing')
            previous = read_item(discovery['node'], discovery['visit'], item_id)
            if not previous or previous.get('fingerprint') != discovery.get('fingerprint'):
                raise hg.HsawError('HSAW_DECISION_EVIDENCE_INVALID', f'{qid}: accepted finding missing')
            prior.append((previous, qid, answer, gate['answer_text_original']))
    result = []
    for i, proposal in enumerate(items):
        if proposal.get('disposition') != 'HARD_FAIL':
            continue
        matches = []
        for previous, qid, answer, original in prior:
            same = proposal.get('same_as') == previous['id'] or _identity(proposal) == _identity(previous)
            overlap = (proposal.get('scope') == previous.get('scope') and bool(_files(proposal) & _files(previous)))
            if same or overlap:
                matches.append(dict(question_id=qid, item_id=previous['id'], answer_original=original,
                                    chosen_intent=answer.get('chosen_intent'),
                                    relation='EXACT_IDENTITY' if same else 'RELATED_FILES_IDENTITY_UNCERTAIN'))
        if proposal.get('same_as') and not any(p['id'] == proposal['same_as'] for p, _, _, _ in prior):
            raise hg.HsawError('HSAW_DECISION_EVIDENCE_INVALID', 'same_as has no verified answer in this run')
        if matches:
            result.append(dict(item_index=i, proposed=copy.deepcopy(proposal), prior_decisions=matches))
    return result


def gate(items, node, language, records):
    result = hg.compose_gate(items, node, language)
    english = str(language or '').lower().startswith('en')
    heading = ('A prior human decision exists; the new hard-fail proposal requires readjudication.' if english else
               '本运行已有相关人类裁决；新的硬失败提案必须重新交你决定。文件重叠不证明问题语义相同。')
    lines = [heading]
    for record in records:
        for decision in record['prior_decisions']:
            lines.append(f"{decision['question_id']} / {decision['item_id']} / {decision['relation']}: "
                         f"{decision['answer_original']} → {decision['chosen_intent']}")
    result['explanation'] = '\n'.join(lines) + '\n\n' + result['explanation']
    result['options'].insert(-1, dict(kind='terminate', intent='terminate',
                                    label='Terminate and preserve evidence' if english else '终止并保全现场',
                                    note='No further nodes or automatic rollback.' if english else '不再执行后续节点；不自动修复、回退或删除。'))
    for n, option in enumerate(result['options'], 1):
        option['aliases'] = [str(n)]
    return result
