"""Declared business replies: validate source and structure, never semantic truth."""
from __future__ import annotations

import copy
import hashlib
import json
import re

SCOPE = 'original_source_and_structure_only'
RULE = ('HUMAN ORIGINAL OVERRIDES the interpretation and compliance declarations. Quotes and coverage prove source/structure only, '
        'not correct understanding or actual compliance. Ambiguity, expanded scope or irreversible changes require HSAW. '
        'Never execute business steps before interpretation acceptance. Never treat aliases or recommendations as authorization.')


class ReplyError(ValueError):
    def __init__(self, code, message, field='conditional_reply'):
        super().__init__(message)
        self.code, self.message, self.field = code, message, field


def fail(code, message, field='conditional_reply'):
    raise ReplyError(code, message, field)


def digest(value):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def exact_keys(value, keys, field):
    if not isinstance(value, dict) or set(value) != set(keys):
        fail('HUMAN_INTERPRETATION_INVALID', f'{field} requires exactly {sorted(keys)}', field)


def strings(value, field, *, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(v, str) or not v.strip() for v in value) \
            or len(set(value)) != len(value):
        fail('HUMAN_INTERPRETATION_INVALID', f'{field} requires distinct nonempty strings', field)
    return value


def declaration(value, view, *, business=False, source=None):
    declared = (view or {}).get('extra', {}).get('conditional_reply')
    if value is None and declared is None:
        return None
    if not business or declared != value:
        fail('CONDITIONAL_REPLY_UNDECLARED', 'Only a program-declared business/HSAW gate accepts conditional replies.')
    required = {'version', 'items', 'quotas', 'nodes'}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - {'gate_sources', 'option_items'}:
        fail('CONDITIONAL_REPLY_INVALID', 'Declare version/items/quotas/nodes and only gate_sources/option_items extensions.')
    sources = value.get('gate_sources')
    if sources is not None:
        strings(sources, 'conditional_reply.gate_sources', nonempty=True)
        if set(sources) - {'user_gate', 'hsaw_doubt', 'sys_io_call', 'advisory_text', 'model_request'}:
            fail('CONDITIONAL_REPLY_INVALID', 'Unknown gate source; engine-owned gates never accept conditional replies.')
    if type(value['version']) is not int or value['version'] != 1:
        fail('CONDITIONAL_REPLY_INVALID', 'Unsupported conditional_reply version.')
    strings(value['nodes'], 'conditional_reply.nodes', nonempty=True)
    if not isinstance(value['items'], list) or not value['items'] or not isinstance(value['quotas'], list):
        fail('CONDITIONAL_REPLY_INVALID', 'Declare nonempty items and explicit quotas.')
    ids, groups = set(), {}
    for item in value['items']:
        exact_keys(item, ('id', 'label', 'group', 'cost', 'rejectable'), 'conditional_reply.items')
        if not all(isinstance(item[k], str) and item[k].strip() for k in ('id', 'label', 'group')) \
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', item['id']) or item['id'] in ids \
                or type(item['cost']) is not int or item['cost'] < 0 or type(item['rejectable']) is not bool:
            fail('CONDITIONAL_REPLY_INVALID', 'Invalid or duplicate item identity/cost/rejectability.')
        ids.add(item['id'])
    for quota in value['quotas']:
        exact_keys(quota, ('group', 'limit'), 'conditional_reply.quotas')
        if not isinstance(quota['group'], str) or not quota['group'] or quota['group'] in groups \
                or type(quota['limit']) is not int or quota['limit'] < 0:
            fail('CONDITIONAL_REPLY_INVALID', 'Invalid or duplicate group quota.')
        groups[quota['group']] = quota['limit']
    if any(i['group'] not in groups for i in value['items']):
        fail('CONDITIONAL_REPLY_INVALID', 'Every item group requires an explicit quota.')
    if not isinstance(value.get('option_items', []), list):
        fail('CONDITIONAL_REPLY_INVALID', 'option_items must be an explicit list.')
    intents = set()
    for preset in value.get('option_items', []):
        exact_keys(preset, ('intent', 'selected', 'rejected'), 'conditional_reply.option_items')
        if not isinstance(preset['intent'], str) or not preset['intent'].strip() or preset['intent'] in intents:
            fail('CONDITIONAL_REPLY_INVALID', 'Preset intents must be unique nonempty strings.')
        intents.add(preset['intent'])
        a, b = strings(preset['selected'], 'preset.selected'), strings(preset['rejected'], 'preset.rejected')
        if (set(a)|set(b)) - ids or set(a)&set(b):
            fail('CONDITIONAL_REPLY_INVALID', 'Preset items must be declared and disjoint.')
    if source is not None and sources is not None and source not in sources:
        return None
    return copy.deepcopy(value)


def latest(record):
    return (record.get('conditional_answers') or [None])[-1]


def pending(record):
    row = latest(record)
    return record.get('resolution_kind') == 'free_text' and row and row['state'] == 'PENDING'


def receive(record, raw, by, now):
    record.setdefault('conditional_answers', []).append(dict(
        text_original=raw, sha256=digest(raw), answered_by=by, answered_at=now, state='PENDING',
        attempts=[], interpretation=None, verification_scope=SCOPE, semantic_correctness='UNVERIFIED'))


def validate(record, candidate, allowed_nodes, completed_nodes):
    exact_keys(candidate, ('question_id', 'answer_sha256', 'choice_intent', 'selected_items', 'rejected_items',
                           'instructions', 'ambiguity'), 'interpretation')
    answer = latest(record)
    if not answer or candidate['question_id'] != record['question_id'] or candidate['answer_sha256'] != answer['sha256'] \
            or digest(answer['text_original']) != answer['sha256']:
        fail('HUMAN_REPLY_BINDING_INVALID', 'Bind to this gate and the full host-recorded original SHA.')
    exact_keys(candidate['ambiguity'], ('status', 'reason'), 'ambiguity')
    if candidate['ambiguity']['status'] not in ('clear', 'needs_human') or not isinstance(candidate['ambiguity']['reason'], str) \
            or not candidate['ambiguity']['reason'].strip():
        fail('HUMAN_INTERPRETATION_INVALID', 'Declare semantic doubt explicitly.')
    if candidate['ambiguity']['status'] == 'needs_human':
        fail('HUMAN_CLARIFICATION_REQUIRED', candidate['ambiguity']['reason'])
    options = [o for o in record['options'] if o['kind'] == 'execute' and o['intent'] == candidate['choice_intent']]
    if len(options) != 1:
        fail('HUMAN_INTERPRETATION_INVALID', 'Name exactly one declared execute intent; do not infer a cancellation.')
    decl = record['conditional_reply']
    catalog = {i['id']: i for i in decl['items']}
    selected = strings(candidate['selected_items'], 'selected_items')
    rejected = strings(candidate['rejected_items'], 'rejected_items')
    if (set(selected) | set(rejected)) - catalog.keys() or set(selected) & set(rejected):
        fail('HUMAN_INTERPRETATION_INVALID', 'Selected/rejected IDs must be disjoint declared items.')
    if any(not catalog[n]['rejectable'] for n in rejected):
        fail('HUMAN_ITEM_NOT_REJECTABLE', 'A rejected item is not declared rejectable.')
    for q in decl['quotas']:
        if sum(catalog[n]['cost'] for n in selected if catalog[n]['group'] == q['group']) > q['limit']:
            fail('HUMAN_ITEM_QUOTA_EXCEEDED', f"Selected cost exceeds {q['group']} limit {q['limit']}.")
    instructions = candidate['instructions']
    if not isinstance(instructions, list) or not instructions:
        fail('HUMAN_INTERPRETATION_INVALID', 'At least one original-backed instruction is required.')
    original = answer['text_original']
    covered, ids = set(), set()
    for instruction in instructions:
        exact_keys(instruction, ('id', 'requirement', 'method', 'evidence', 'nodes'), 'instructions')
        if any(not isinstance(instruction[k], str) or not instruction[k].strip() for k in ('id', 'requirement', 'method')) \
                or instruction['id'] in ids:
            fail('HUMAN_INTERPRETATION_INVALID', 'Instruction IDs are distinct; requirements/methods cannot be empty.')
        ids.add(instruction['id'])
        targets = strings(instruction['nodes'], 'instructions.nodes', nonempty=True)
        if set(targets) - set(decl['nodes']) or set(targets) - set(allowed_nodes) or set(targets) & set(completed_nodes):
            fail('HUMAN_TARGET_INVALID', 'Instructions target only declared, available, uncompleted node identities.')
        refs = instruction['evidence']
        if not isinstance(refs, list) or not refs:
            fail('HUMAN_QUOTE_INVALID', 'Every instruction requires an exact original quote.')
        for ref in refs:
            exact_keys(ref, ('start', 'end', 'quote'), 'evidence')
            start, end = ref['start'], ref['end']
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(original) \
                    or not isinstance(ref['quote'], str) or ref['quote'] != original[start:end]:
                fail('HUMAN_QUOTE_INVALID', 'Quote offsets use Unicode code points and must reproduce the exact original.')
            covered.update(range(start, end))
    if any(not ch.isspace() and pos not in covered for pos, ch in enumerate(original)):
        fail('HUMAN_REPLY_COVERAGE_INCOMPLETE', 'Every non-whitespace original character must map to an instruction quote.')
    quotes = [ref['quote'] for i in instructions for ref in i['evidence']]
    option = options[0]
    ordinal = record['options'].index(option)+1
    tokens = [str(ordinal), option.get('label', ''), option['intent']]
    chosen_in_original = any(token and re.match(r'^\s*'+re.escape(token)+r'(?=$|[\s,，:：;；])', original) for token in tokens)
    presets = [p for p in decl.get('option_items', []) if p['intent'] == option['intent'] and chosen_in_original]
    for kind, items in (('selected', selected), ('rejected', rejected)):
        for item in items:
            explicit = any(re.search(r'(?<![A-Za-z0-9_-])'+re.escape(item)+r'(?![A-Za-z0-9_-])', quote)
                           or re.search(r'(?<![A-Za-z0-9_-])'+re.escape(catalog[item]['label'])+r'(?![A-Za-z0-9_-])', quote) for quote in quotes)
            if not explicit and not any(item in p[kind] for p in presets):
                fail('HUMAN_ITEM_SOURCE_MISSING', f'{kind} item {item} has no exact original quote anchor or program option preset.')
    return copy.deepcopy(candidate), options[0]


def accepted(record):
    row = latest(record)
    if not row or row['state'] != 'ACCEPTED':
        return None
    proof = row.get('proof')
    value = dict(question_id=record['question_id'], node=record['node'], visit=record['visit'],
                 answer_text_original=row['text_original'], answer_sha256=row['sha256'],
                 answered_by=row['answered_by'], answered_at=row['answered_at'], interpretation=row['interpretation'],
                 verification_scope=SCOPE, semantic_correctness='UNVERIFIED', actual_compliance='UNVERIFIED')
    if digest(value) != proof or digest(row['text_original']) != row['sha256']:
        fail('HUMAN_REPLY_PROOF_CHANGED', 'Accepted original/interpretation proof changed; preserve evidence and ask the human.')
    return value


def seal(record):
    row = latest(record)
    value = dict(question_id=record['question_id'], node=record['node'], visit=record['visit'],
                 answer_text_original=row['text_original'], answer_sha256=row['sha256'],
                 answered_by=row['answered_by'], answered_at=row['answered_at'], interpretation=row['interpretation'],
                 verification_scope=SCOPE, semantic_correctness='UNVERIFIED', actual_compliance='UNVERIFIED')
    row['proof'] = digest(value)


def records(store, index):
    result, seen = [], set()
    for event in index['gate']['history']:
        qid = event['question_id']
        if qid in seen or event.get('resolution_kind') != 'free_text':
            continue
        seen.add(qid)
        value = accepted(store.read_json(store.gate_path(qid)))
        if value:
            events = store.read_json(store.evidence_path)
            if not any(e.get('kind') == 'human_interpretation' and e.get('question_id') == qid
                       and e.get('answer_sha256') == value['answer_sha256']
                       and e.get('proof_sha256') == digest(value) for e in events):
                fail('HUMAN_REPLY_PROOF_CHANGED', 'Accepted interpretation must match the append-only run ledger.')
            result.append(value)
    return result


def for_node(records_, node):
    aliases = {node} if isinstance(node, str) else set(node)
    return [dict(question_id=r['question_id'], answer_text_original=r['answer_text_original'],
                 answer_sha256=r['answer_sha256'], selected_items=r['interpretation']['selected_items'],
                 rejected_items=r['interpretation']['rejected_items'], choice_intent=r['interpretation']['choice_intent'],
                 instruction=copy.deepcopy(i), verification_scope=SCOPE,
                 semantic_correctness='UNVERIFIED', actual_compliance='UNVERIFIED')
            for r in records_ for i in r['interpretation']['instructions'] if aliases & set(i['nodes'])]


def compliance(required, given, *, ref_ok):
    if not required and not given:
        return []
    if not isinstance(given, list):
        fail('HUMAN_COMPLIANCE_REQUIRED', 'Submit one human_compliance row per affected instruction.', 'human_compliance')
    wanted = {(r['question_id'], r['instruction']['id']) for r in required}
    seen = set()
    for row in given:
        exact_keys(row, ('question_id', 'instruction_id', 'status', 'rationale', 'evidence_refs'), 'human_compliance')
        key = (row['question_id'], row['instruction_id'])
        if key in seen or key not in wanted or row['status'] not in ('applied', 'not_applicable') \
                or not isinstance(row['rationale'], str) or not row['rationale'].strip():
            fail('HUMAN_COMPLIANCE_INVALID', 'No extra/duplicate/violated declarations; explain applied/not_applicable status.')
        seen.add(key)
        refs = strings(row['evidence_refs'], 'human_compliance.evidence_refs', nonempty=True)
        if any(not ref_ok(ref) for ref in refs):
            fail('HUMAN_COMPLIANCE_INVALID', 'Compliance evidence must exist in this run.')
    if seen != wanted:
        fail('HUMAN_COMPLIANCE_REQUIRED', f'Missing declarations for {sorted(wanted-seen)}.', 'human_compliance')
    return copy.deepcopy(given)


def unreached(records_, reached):
    return [dict(question_id=r['question_id'], instruction_id=i['id'], node=node, status='NOT_REACHED',
                 semantic_correctness='UNVERIFIED', actual_compliance='UNVERIFIED')
            for r in records_ for i in r['interpretation']['instructions'] for node in i['nodes'] if node not in set(reached)]


def table(records_, compliance_rows, language, *, not_reached=()):
    if not records_ and not compliance_rows:
        return ''
    zh = str(language or '').startswith('zh')
    cell = lambda s: str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\r', '&#13;').replace('\n', '<br>')
    rows = [('**人类条件与执行说明（来源/结构校验，非语义证明）**' if zh else
             '**Human conditions and execution declarations (source/structure checks, not semantic proof)**')]
    rows += ['| Gate | Original | Selected / Rejected | Instruction | Targets / Method |', '| --- | --- | --- | --- | --- |']
    for rec in records_:
        plan = rec['interpretation']
        for ins in plan['instructions']:
            rows.append('| ' + ' | '.join(cell(v) for v in (rec['question_id'], rec['answer_text_original'],
                        f"{plan['selected_items']} / {plan['rejected_items']}", f"{ins['id']}: {ins['requirement']}",
                        f"{ins['nodes']} / {ins['method']}")) + ' |')
        raw = json.dumps(plan, ensure_ascii=False, indent=2)
        fence = '`' * max(3, 1+max((len(s) for s in re.findall(r'`+', raw)), default=0))
        rows.append(fence+'json\n'+raw+'\n'+fence)
    if compliance_rows:
        rows += ['| Gate | Node | Instruction | Declared status | Rationale / evidence |', '| --- | --- | --- | --- | --- |']
        for row in compliance_rows:
            rows.append('| ' + ' | '.join(cell(v) for v in (row['question_id'], row.get('node', 'current'), row['instruction_id'], row['status'],
                        f"{row['rationale']} / {row['evidence_refs']}")) + ' |')
    if not_reached:
        rows += ['| Gate | Instruction | Target | Status |', '| --- | --- | --- | --- |']
        rows += ['| '+' | '.join(cell(r[k]) for k in ('question_id','instruction_id','node','status'))+' |' for r in not_reached]
    rows.append('原文最高优先。解读和执行状态均为执行者声明；机器未证明理解正确或实际履行。' if zh else
                'The original has highest authority. Interpretations/statuses are executor declarations, not proof of understanding or actual compliance.')
    return '\n'.join(rows)
