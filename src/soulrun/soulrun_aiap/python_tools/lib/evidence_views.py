"""Read-only evidence projections; counts are not semantic event classification."""
from __future__ import annotations

import hashlib
import copy
import html
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

# Review round 4 of docs/05SoulRun 88 (W1): the two engine stops whose recheck may move on (dispatch_budget._MOVABLE) - a
# stop a recheck moved on to with one of these codes may have the retired stop's own condition again (a recovered move).
MOVABLE_STOPS = ('DISPATCH_LIVENESS_UNKNOWN', 'SUBTREE_AGENT_CAPABILITY_UNAVAILABLE')


def protocol_attempts(cache_dir):
    """Existing CLI receipts only; do not classify help examples or Provider events."""
    rows, unreadable, receipts = [], [], {}
    root = Path(cache_dir)
    archive = root / '_work' / 'replies'
    try:
        for parent in (root, *root.parents, root / '_work', archive):
            if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('linked receipt directory is not read')
        paths = sorted(archive.glob('*.commit.*.json'))
    except (OSError, ValueError) as exc:
        paths = []
        unreadable.append(dict(file='_work/replies', reason=str(exc)))
    for path in paths:
        try:
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('linked receipt is not read')
            raw = path.read_bytes()
            receipt = json.loads(raw)
            if not isinstance(receipt, dict):
                raise ValueError('reply is not an object')
            if receipt.get('status') in ('REJECTED', 'ERROR'):
                errors = receipt.get('errors', [])
                if not isinstance(errors, list) or any(not isinstance(e, dict) or not isinstance(e.get('code'), str) for e in errors):
                    raise ValueError('reply errors must be an array of coded objects')
        except (OSError, ValueError) as exc:
            unreadable.append(dict(file=path.name, reason=str(exc)))
            continue
        if receipt.get('status') in ('REJECTED', 'ERROR'):
            receipts[path.relative_to(root).as_posix()] = receipt
            rows.append(dict(node=receipt.get('node'), status=receipt['status'],
                             codes=list(dict.fromkeys(e['code'] for e in errors)),
                             error_count=len(errors),
                             file=path.relative_to(cache_dir).as_posix(), sha256=hashlib.sha256(raw).hexdigest()))
    aliases, unknown = [], []
    for row in rows:
        receipt = receipts[row['file']]
        if 'reply_file' not in receipt:
            continue
        target = receipt['reply_file']
        path = PurePosixPath(target) if isinstance(target, str) else None
        formal = receipts.get(target) if isinstance(target, str) else None
        valid_path = path and len(path.parts) == 3 and path.parts[:2] == ('_work', 'replies') and '\\' not in target
        # Printed stdout adds reply_file; the archived formal receipt is a leaf, never an alias chain.
        if (valid_path and formal and 'reply_file' not in formal and target != row['file']
                and all(k in receipt and k in formal and receipt[k] == formal[k]
                        for k in ('status', 'node', 'errors', 'payload_file'))):
            aliases.append(dict(file=row['file'], canonical_file=target, sha256=row['sha256'],
                                basis='explicit_reply_file_and_matching_commit_identity'))
        else:
            unknown.append(dict(file=row['file'], reply_file=target, reason='alias_identity_unverified'))
    alias_files = {r['file'] for r in aliases}
    canonical = [row for row in rows if row['file'] not in alias_files]
    return dict(rejected_or_error_count=len(rows), archived_record_count=len(rows), records=rows, unreadable=unreadable,
                canonical_attempt_count=None if unreadable or unknown else len(canonical),
                canonical_files=[r['file'] for r in canonical], aliases=aliases,
                **(dict(unknown_aliases=unknown) if unknown else {}),
                count_basis='conservative_archive_records' if unreadable or unknown else 'same_run_receipt_identity',
                scope='archived_commit_replies_only_not_all_provider_calls',
                recovery='later_success_does_not_erase_failed_attempts')


def _absolute_path(value):
    if not isinstance(value, (str, Path)):
        return None
    text = str(value)
    cls = PureWindowsPath if PureWindowsPath(text).drive or '\\' in text else PurePosixPath
    path = cls(text)
    return path if path.is_absolute() and '..' not in path.parts else None


def _root_path(value):
    """Only tool-owned native roots resolve relative to cwd, never artifact declarations."""
    if isinstance(value, Path):
        return _absolute_path(value.resolve())
    absolute = _absolute_path(value)
    if absolute or not isinstance(value, str) or not value.strip() or PureWindowsPath(value).drive:
        return absolute
    return _absolute_path(Path(value).resolve())


def protocol_summary(attempts):
    known = attempts.get('canonical_attempt_count') is not None
    files = set(attempts['canonical_files']) if known else None
    records = [r for r in attempts['records'] if r['file'] in files] if known else attempts['records']
    by_code = Counter(code for row in records for code in set(row['codes']))
    by_node = Counter(row.get('node') or '<unrecorded>' for row in records)
    return dict(rejected_count=sum(r['status'] == 'REJECTED' for r in records),
        error_count=sum(r['status'] == 'ERROR' for r in records),
        attempts_by_code=dict(sorted(by_code.items())), attempts_by_node=dict(sorted(by_node.items())),
        unreadable_count=len(attempts['unreadable']),
        completeness='INCOMPLETE' if attempts['unreadable'] or attempts.get('unknown_aliases') else 'ARCHIVED_RECEIPTS_ONLY',
        **(dict(archived_record_count=len(attempts['records']), canonical_attempt_count=attempts.get('canonical_attempt_count'))
           if attempts['records'] or attempts['unreadable'] else {}),
        **(dict(alias_count=len(attempts.get('aliases', [])), unknown_alias_count=len(attempts.get('unknown_aliases', [])))
           if attempts.get('aliases') or attempts.get('unknown_aliases') else {}),
        count_basis=attempts.get('count_basis', 'legacy_archive_records'),
        evidence_files=[r['file'] for r in attempts['records']], scope='archived_commit_replies_not_business_retries_or_provider_failures')


def human_decision_summary(records):
    if records is None:
        return dict(count=None, records=[], scope='UNOBSERVED')
    unique = {r['question_id']: r for r in records if r.get('question_id')}
    fields = ('question_id', 'node', 'visit', 'resolution_kind', 'chosen_intent', 'answered_at', 'replacement_refused',
              'replacement_not_used', 'recheck_moved_on')   # docs/05SoulRun 88 (K1): a recheck that moved on to another stop
    # Review of docs/05SoulRun 87, round 2 (N2): a stale replacement choice is a resolved reply that replaced nothing;
    # round 3 (D2): so is an accepted one whose replacement never ran (the host recorded the old agent's return first).
    refused = sum(bool(r.get('replacement_refused')) for r in unique.values())
    unused = sum(bool(r.get('replacement_not_used')) for r in unique.values())
    return dict(count=len(unique), records=[{k: r[k] for k in fields if k in r} for r in unique.values()],
                scope='whole_run_resolved_choices_and_free_text_not_invalid_replies_or_off_channel_authorization',
                **({'refused_replacement_choices': refused} if refused else {}),
                **({'unused_replacement_choices': unused} if unused else {}))


def execution_facts(context, cache_dir, program_dir, *, snapshot=None, nodes=None):
    """Project accepted observations, without rereading artifacts or certifying prose."""
    roots = [('cache', _root_path(cache_dir)), ('program', _root_path(program_dir))]
    artifacts, unique = [], {key: set() for key in ('cache', 'program', 'other', 'unknown')}
    for item in artifact_rows(context['artifact_observations']):
        path = _absolute_path(item.get('path'))
        scope = next((label for label, root in roots if path and root and path.is_relative_to(root)),
                     'other' if path else 'unknown')
        unique[scope].add(path if path else item.get('path'))
        artifacts.append(dict(item, scope=scope))
    return dict(
        scope='whole_run_including_prior_resumes', snapshot=snapshot, **({'nodes': nodes} if nodes else {}),
        protocol=protocol_summary(context['protocol_attempts']),
        human_decisions=human_decision_summary(context.get('human_decisions')),
        receipt_effects=copy.deepcopy(context.get('receipt_effects') or []),
        anomalies=anomaly_view(context['run_observations']) if 'run_observations' in context else
                  dict(record_count=None, distinct_text_groups=None, event_count=None, basis='UNOBSERVED'),
        artifacts=dict(record_count=len(artifacts), unique_paths_by_scope={k: len(v) for k, v in unique.items()}, records=artifacts,
            declared_operation_records=dict(Counter(a['declared_operation'] or 'unspecified' for a in artifacts)),
            scope='registered_files_including_children_not_all_side_effects',
            operation_authority='model_declared_not_proved_by_file_hash'),
        rule='Report and Explain interpret whole-run facts, including earlier resumes and Router choices. Tables carry counts and observations; do not transcribe them. '
             'Label narrower windows; never replace whole-run totals. Zero anomalies is not zero rejected commits; no deletion is not no modification. '
             'Counts cover archived observations only, not all events. Include child artifacts through their parent; file hashes do not prove declared operations. Do not recount from prose. '
             'nodes.states counts main, sub and engine occurrences separately - never add them into one business-node figure; the Report states the same '
             'whole-run status as semantics.functional_status, never milder than nodes.functional_status_floor. Write no rejected/error numbers in prose or '
             'output: a rejected commit changes them and the machine table carries them.'
             + (' receipt_effects: scoped claims, not operation proof; never sum overlaps or infer zero.'
                if context.get('receipt_effects') else ''))


def artifact_rows(groups):
    """The same declared/observed join for served facts and the committed report."""
    artifacts = []
    for group in groups:
        observed = {_absolute_path(a.get('path')): a for a in group['observed'] if _absolute_path(a.get('path'))}
        declared = group['declared']
        keys = {_absolute_path(a.get('path')) for a in declared}
        # An observed-only file is evidence too; absence of an operation is not a write claim.
        items = declared + [a for a in group['observed'] if _absolute_path(a.get('path')) not in keys]
        for item in items:
            path = _absolute_path(item.get('path'))
            observation = observed.get(path, {}) if path else {}
            artifacts.append(dict(node=group['node'], visit=group['visit'], revision=group['revision'],
                path=observation.get('path') or item.get('path'), kind=item.get('kind'),
                declared_operation=item.get('operation'), note=item.get('note'),
                observed_sha256=observation.get('sha256')))
    return artifacts


def source_support_rows(records):
    """Latest accepted proof per occurrence; forwarded ledgers are never summed."""
    rows = []
    for cache in records:
        revisions = [cache, *(cache.get('continuations') or [])]
        proof = revisions[-1]['machine'].get('source_support')
        if not proof:
            continue
        rows.append(dict(node=cache['node'], visit=cache['visit'], revision=len(revisions) - 1,
                         claim_ids=copy.deepcopy(proof.get('claim_ids')),
                         **{k: copy.deepcopy(proof.get(k)) for k in ('labelled', 'source_verified', 'derived', 'unverified',
                             'demoted', 'reclassified_derived', 'verification_scope', 'retrieval_provenance',
                             'claim_classifications', 'dependency_observations', 'dependency_scope')}))
        if proof.get('unique_claims') or proof.get('unidentified_observations'):
            rows[-1].update({k: copy.deepcopy(proof[k]) for k in
                ('effective_counts', 'unique_claims', 'unidentified_observations', 'count_basis')})
    return rows


def source_support_preview(row, ref):
    """A discovery summary, never the authority used to validate inherited claims."""
    fields = ('node', 'visit', 'revision', 'labelled', 'source_verified', 'derived', 'unverified',
              'verification_scope', 'retrieval_provenance', 'dependency_scope', 'effective_counts',
              'unique_claims', 'unidentified_observations', 'count_basis')
    preview = {k: copy.deepcopy(row.get(k)) for k in fields}
    preview['count_basis'] = row.get('count_basis') or 'legacy_id_label_observations_not_effective'
    for key, name in (('demoted', 'demotions'), ('reclassified_derived', 'reclassifications')):
        records = row.get(key)
        preview[name] = dict(count=len(records), reasons=dict(Counter(r.get('reason', 'UNSPECIFIED') for r in records))) if records is not None else None
    dependencies = row.get('dependency_observations')
    preview['dependency_risks'] = None if dependencies is None else dict(
        observation_count=len(dependencies), unverified_input_observations=sum(len(r.get('unverified_inputs', [])) for r in dependencies),
        unresolved_input_observations=sum(len(r.get('unresolved_inputs', [])) for r in dependencies),
        unresolved_reasons=dict(Counter(reason for r in dependencies for reasons in r.get('unresolved_reasons', {}).values() for reason in reasons)),
        count_basis='dependency_observations_not_unique_claims')
    preview.update(source_support_complete=False, source_support_read=dict(ref=ref, field='source_support'),
        use='Read the complete bound proof for claim identities, propagation or any ambiguity/demotion/dependency risk; counts do not certify a conclusion.')
    # A tiny existing proof is cheaper to keep; folding must not grow routine replies.
    return preview if len(json.dumps(preview, ensure_ascii=False, indent=2).encode()) < len(json.dumps(row, ensure_ascii=False, indent=2).encode()) else copy.deepcopy(row)


def receipt_effect_rows(records):
    """Small accepted @value receipts only; no file scan, address expansion or prose inference."""
    result = []
    count_key = re.compile(r'(?:(?:records|files|items|rows|episodes)_(deleted|purged|removed)|(deleted|purged|removed)_count)$')

    def walk(value, path, origin=None):
        if isinstance(value, dict):
            if (any(value.get(k) is True for k in ('dry_run', 'simulated', 'preview'))
                    or any(str(value.get(k, '')).strip().casefold() in
                           {'dry_run', 'dry-run', 'planned', 'preview', 'simulated', 'not_executed'} for k in ('status', 'mode'))):
                return
            if '@ref' in value:
                meta = value.get('@resolved') or {}
                if isinstance(meta, dict) and meta.get('kind') in ('proc', 'work', 'artifact', 'input') and '@value' in value:
                    digest = meta.get('sha256')
                    full = meta.get('by') == 'engine' and re.fullmatch(r'[0-9a-f]{64}', str(digest or ''))
                    # Tiny resolutions deliberately omit source hashes; the accepted cache owns their embedded value.
                    tiny = set(meta) == {'kind'} and str(value['@ref']).startswith(meta['kind'] + ':')
                    if full or tiny:
                        yield from walk(value['@value'], path, dict(reference=value['@ref'], sha256=digest if full else None,
                            identity_scope='resolved_source' if full else 'accepted_cache_embedded_value'))
                return
            for key, child in value.items():
                field = path + '.' + key
                match = count_key.fullmatch(key)
                if origin and match and type(child) is int and child >= 0:
                    yield dict(field=field, count=child, operation=match[1] or match[2], **origin)
                if not key.startswith('@'):
                    yield from walk(child, field, origin)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                yield from walk(child, f'{path}[{i}]', origin)

    for cache in records:
        for revision, row in enumerate([cache, *(cache.get('continuations') or [])]):
            for effect in walk(row['payload'].get('output'), 'output'):
                result.append(dict(node=cache['node'], visit=cache['visit'], revision=revision, **effect,
                    basis='accepted_resolved_receipt_not_independent_operation_audit'))
    return result


def anomaly_view(rows):
    groups = {}
    for row in rows:
        key = (row.get('code'), row.get('text'))
        group = groups.setdefault(key, dict(code=key[0], text=key[1], record_count=0, reported_by=[]))
        group['record_count'] += 1
        if row.get('node') not in group['reported_by']:
            group['reported_by'].append(row.get('node'))
    return dict(record_count=len(rows), distinct_text_groups=len(groups), event_count=None,
                basis='exact_code_and_text_not_event_identity', groups=list(groups.values()))


def revision_anomaly_rows(records):
    """The all-node-revisions scope: payload.anomalies (MODEL_ANOMALY) and machine.engine_anomalies of every revision of
    the given node caches - gate-paused and module pre-work revisions included. Each record counts, equal text or not."""
    rows = []
    for cache in records:
        for revision, row in enumerate([cache, *(cache.get('continuations') or [])]):
            for a in (row.get('payload') or {}).get('anomalies') or []:
                rows.append(dict(node=cache.get('node'), revision=revision, code='MODEL_ANOMALY', text=a))
            for a in (row.get('machine') or {}).get('engine_anomalies') or []:
                rows.append(dict(node=cache.get('node'), revision=revision, **a))
    return rows


def code_counts(rows):
    """docs/05SoulRun 87: records per code, most first (equal counts by code); a count, never a severity."""
    counts = Counter(row.get('code') for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], str(item[0]))))


def record_kind(cache, index=None):
    from . import dispatch_scope
    kind = cache.get('kind')
    if kind in ('business', 'sub') and index and index.get('program', {}).get('entry_file'):
        entry = next((e for e in index.get('catalog', []) if e['name'] == cache.get('node')), None) or index.get('catalog_history',{}).get(cache.get('node'))
        return 'main' if dispatch_scope.is_main(index, entry) else 'sub'
    return {'business': 'main'}.get(kind, kind)


def node_state_counts(records, index=None):
    """Latest accepted status of every occurrence by kind; main, sub and engine occurrences are never one business-node figure."""
    states = {kind: Counter() for kind in ('main', 'sub', 'engine', 'final')}
    for cache in records:
        kind = 'final' if cache.get('node') in ('Engine.final-answer', 'final') else record_kind(cache, index)
        if kind in states:
            states[kind][(cache.get('continuations') or [cache])[-1]['payload']['status']] += 1
    return {k: dict(v) for k, v in states.items()}


def report_snapshot(cache_dir, index, at, *, records=(), hsaw=None, cancelled=None):
    from . import dispatch_accounting, blind_review
    from .run_store import RunStore
    counts = protocol_summary(protocol_attempts(cache_dir))
    records = list(records)
    anomalies = revision_anomaly_rows(records)
    store = RunStore(cache_dir)
    accounting = dispatch_accounting.snapshot(store, index)
    reviews = blind_review.latest_results(store, records)
    return dict(at=at, scope='whole_run_before_this_commit',
                **(dict(dispatch_accounting=accounting) if accounting is not None else {}),
                **(dict(review_candidate_bindings=reviews) if reviews else {}),
                rejected_count=counts['rejected_count'],
                error_count=counts['error_count'], unreadable_count=counts['unreadable_count'],
                **(dict(receipt_identity={k: counts.get(k, 0) for k in ('archived_record_count', 'canonical_attempt_count',
                    'alias_count', 'unknown_alias_count', 'count_basis', 'completeness')})
                    if counts.get('archived_record_count') or counts['unreadable_count'] else {}),
                anomaly_records=len(index.get('anomalies_summary') or []),
                anomaly_basis='index_summary_only_not_revision_or_event_count',
                revision_anomalies=anomaly_view(anomalies), node_states=node_state_counts(records, index),
                main_nodes=len({c.get('node') for c in records if record_kind(c, index) == 'main'}),
                receipt_basis=counts['scope'], hsaw=hsaw,   # alpha.87: the sovereignty doubt gate facts
                cancelled=cancelled,   # alpha.88 (doc 196 F4'): where the human cancelled and what was not run
                user_messages=user_message_rows(records),
                source_support=source_support_rows(records),
                receipt_effects=receipt_effect_rows(records),
                artifacts=artifact_rows(dict(node=c['node'], visit=c['visit'], revision=n,
                    declared=r['payload'].get('evidence', {}).get('artifacts') or [], observed=r['machine'].get('artifacts') or [])
                    for c in records for n,r in enumerate([c, *(c.get('continuations') or [])])))


def user_message_rows(records):
    """alpha.93: the checked user_message declaration of every business / sub node (latest revision), for the execution report."""
    rows = []
    for cache in records:
        if cache.get('kind') not in ('business', 'sub'):
            continue
        last = (cache.get('continuations') or [cache])[-1]
        um = (last.get('machine') or {}).get('user_message')
        if um is None:
            continue
        rows.append(dict(node=cache.get('node'), visit=cache.get('visit'), has=um.get('has'), messages=um.get('messages'),
                         literals=um.get('literals_verbatim'), none_reason=um.get('none_reason'), prose_output_chars=um.get('prose_output_chars'),
                         not_applicable=[f"{x.get('step') or str(x.get('text') or '')[:40]}: {x.get('reason')}" for x in um.get('not_applicable') or []]))
    return rows


def _literal(text):
    # A single escaped line also protects legacy section/guard parsers outside Markdown.
    escaped = html.escape(text, quote=False).replace('\r', '&#13;').replace('\n', '&#10;').replace('·', '&#183;')
    return '<pre><code>' + escaped + '</code></pre>'


def _table_cell(text):
    # One physical line: neither Markdown nor the outer node parser can interpret user markup.
    escaped = html.escape(str(text), quote=True)
    for char in '\r\n|\\`*[]·_~:@':   # alpha.79: _ ~ emphasis and : @ autolinks are Markdown too (Web replay, doc 163)
        escaped = escaped.replace(char, f'&#{ord(char)};')
    escaped = re.sub(r'(?i)(www)\.', r'\1&#46;', escaped)   # GFM autolinks a bare www. host
    return '<span style="white-space:pre-wrap;overflow-wrap:anywhere">' + escaped + '</span>'


def _label(text):
    # A narrow screen leaves ~150 px for the table: a label that may wrap is squeezed to one character per line.
    return f'<span style="white-space:nowrap">{text}</span>'


def _reply_table(record, zh):
    basis = 'host_argument_original' if isinstance(record.get('answer_text_original'), str) else 'legacy_normalized_record'
    answer = record.get('answer_text_original') if basis == 'host_argument_original' else record.get('answer_text')
    unknown = '未记录' if zh else 'Not recorded'
    effect = ('已消费本次授权；不证明业务动作成功' if zh else 'Authorization consumed; does not certify business success') if record.get('consumed_by_commit') else (
        '本节点接收裁决；结果见本节点报告' if zh else 'Decision received; outcome is in this node report')
    if record.get('replacement_refused'):   # review of docs/05SoulRun 87, round 2 (N2): the stop was retired, nothing authorized
        effect = ('未采纳：这个换人选项依据的记录已经变了，没有换人' if zh else
                  'Refused: the records this replacement was offered on had changed; nothing was replaced')
    unused = record.get('replacement_not_used')
    if unused:   # round 3 (D2): accepted, but its replacement never ran
        effect = (('未使用：选择之后宿主记下了旧代理的返回，这次选择没有换人' if zh else
                   "Not used: the host recorded the old agent's return after this choice; this choice replaced nothing")
                  if unused.get('old_return_recorded_after_choice') else
                  ('未使用：这次选择依据的记录在选择之后变了，这次选择没有换人' if zh else
                   'Not used: the records this choice was made on changed after it; this choice replaced nothing'))
    moved = record.get('recheck_moved_on')
    if moved:   # docs/05SoulRun 88 (K1): the human's recheck retired this stop
        # Review round 3 (R4): before the stop that follows opens (the run stopped after answer()'s index write) it has no
        # question. Review round 4 (W1, W2): with no question the code is the condition the recorded recheck named (never this
        # stop's own); a linked stop's code may be this stop's own condition again (a recovered move), so where it is one of
        # the two a retired stop can have, the line says only where and on what records the human was asked.
        asked, code = moved.get('question_id'), moved.get('code')
        if not asked:
            effect = (f'复核已执行：你复核时拦着这一段的是另一个条件（{code}），这道题因此关闭；这次复核没有授权任何执行' if zh else
                      f'Recheck executed: when you rechecked, another condition held this part ({code}), so this stop was closed; '
                      'this recheck authorized nothing')
        elif code in MOVABLE_STOPS:
            effect = (f'复核已执行：这道题因此关闭，改在 {asked}（{code}）按当时的记录重新问你；这次复核没有授权任何执行' if zh else
                      f'Recheck executed: this stop was closed and you were asked again at {asked} ({code}) on the records at that '
                      'time; this recheck authorized nothing')
        else:
            effect = (f'复核已执行：这道题因此关闭，改在 {asked} 重新问你，那时拦着这一段的是另一个条件（{code}）；这次复核没有授权任何执行'
                      if zh else
                      f'Recheck executed: this stop was closed and you were asked again at {asked}, where another condition then '
                      f'held this part ({code}); this recheck authorized nothing')
    if record.get('resolution_kind') == 'cancel':   # alpha.79 (doc 161 §6.1): a refusal is a human decision, never an authorization
        effect = '用户拒绝该请求：未授权执行，后续按程序的错误路由处理' if zh else 'Declined by the user: nothing was authorized; the program error route continued'
        if record.get('cancel_outcome') == 'report':   # alpha.88 (doc 196 F4'): no error route - the business work closed, the report and the answer followed
            effect = ('用户拒绝该请求：未授权执行；业务到此收束，仅生成执行报告与终答' if zh else
                      'Declined by the user: nothing was authorized; the business work closed here and only the execution report and the answer followed')
    labels = ('节点', '问题', '回复', '选项', '处置') if zh else ('Node', 'Question', 'Reply', 'Option', 'Outcome')
    question = re.sub(r'\*\*|__|`', '', record.get('question') or '')   # emphasis marks of the engine's own question mean nothing in a literal cell
    values = [f"{record.get('node', unknown)} (visit {record.get('visit', 1)})", question or unknown,
              answer if answer is not None else unknown, record.get('chosen_label') or unknown, effect]
    rows = ['| 项目 | 内容 |' if zh else '| Item | Content |', '| --- | --- |']
    rows.extend(f'| {_label(label)} | {_table_cell(value)} |' for label, value in zip(labels, values))
    if basis != 'host_argument_original':
        rows.append(f'| {_label("依据" if zh else "Basis")} | legacy_normalized_record |')
    invalid = [r for r in record.get('invalid_answers') or [] if isinstance(r, dict)]
    for n, row in enumerate(invalid, 1):   # alpha.79 (doc 161 §6.1): listed apart, never shown as accepted
        rows.append(f"| {'未采纳' if zh else 'Not accepted'} {n} | {_table_cell(row.get('text_original', row.get('text', unknown)))} |")
    if any('text_original' not in r for r in invalid):
        rows.append(f'| {"未采纳依据" if zh else "Basis, not accepted"} | stripped_record |')
    meta = {k: record[k] for k in ('question_id', 'node', 'visit', 'resolution_kind', 'chosen_intent') if k in record}
    meta.update(basis=basis, answer_sha256=hashlib.sha256(answer.encode('utf-8')).hexdigest() if answer is not None else None)
    if record.get('replacement_refused'):
        meta['replacement_refused'] = True
    if unused:
        meta['replacement_not_used'] = True
    if moved:
        meta['recheck_moved_on'] = True
    if invalid:
        meta['invalid_replies'] = len(invalid)
    return '\n'.join(rows), meta


def project_report(payload, language, *, gate_answer=None, snapshot=None, decisions=()):
    """Append machine-owned evidence before hashing/rendering; never edit model prose."""
    if not gate_answer and snapshot is None and not decisions:
        return payload, None
    original = payload['user_summary']
    parts = [original]
    meta = dict(model_report_sha256=hashlib.sha256(original.encode('utf-8')).hexdigest())
    if payload.get('node') == 'Engine.execute-report' and (payload.get('semantics') or {}).get('per_node'):
        zh = str(language).startswith('zh')
        rows = ['**主节点执行说明（模型提交）**' if zh else '**Main-node execution descriptions (model-authored)**',
                '| 节点 | 实际行动 | 结果 |' if zh else '| Node | Material action | Result |', '| --- | --- | --- |']
        rows += [f"| {_table_cell(r['node'])} | {_table_cell(r['material_action'])} | {_table_cell(r['result'])} |"
                 for r in payload['semantics']['per_node']]
        parts.append('\n'.join(rows))
    zh = (language or '').startswith('zh')
    records = list({r['question_id']: r for r in decisions}.values())
    if gate_answer and all(r['question_id'] != gate_answer['question_id'] for r in records):
        records.append(gate_answer)   # alpha.79: the reply this commit consumes is always shown, also when the whole-run list lacks it
    if records:
        parts.append('**业务门人类回复（机器记录）**' if zh else '**Business-gate human replies (machine records)**')
        parts.append('此处仅统计引擎业务门中已接受的人类回复；宿主故障恢复等其它授权不在此统计中，应以其独立记录为准。' if zh else
                     'These statistics cover only accepted human replies to engine business gates. Host fault-recovery and other authorizations are outside these statistics; consult their separate records.')
        meta['human_replies'] = []
        for record in records:
            table, info = _reply_table(record, zh)
            parts.append(table)
            meta['human_replies'].append(info)
        if gate_answer:
            meta['human_reply'] = next(r for r in meta['human_replies'] if r['question_id'] == gate_answer['question_id'])
    elif snapshot is not None:
        parts += [('**业务门人类回复（机器记录）**' if zh else '**Business-gate human replies (machine records)**'),
                  ('本报告所统计的业务门中，没有已接受的人类回复记录。宿主故障恢复等其它授权不在此统计中，应以其独立记录为准。' if zh else
                   'No accepted human reply is recorded for the business gates covered by this report. Host fault-recovery and other authorizations are outside these statistics; consult their separate records.')]
        meta['human_replies'] = []
    cancelled = snapshot.get('cancelled') if isinstance(snapshot, dict) else None
    if cancelled:   # alpha.88 (doc 196 F4'): the machine states where the human cancelled and what was not run, whatever the prose says
        dropped = list(cancelled.get('dropped_nodes') or [])
        label = cancelled.get('chosen_label') or cancelled.get('answer_text') or ('取消' if zh else 'cancel')
        parts.append('**取消记录（机器记录）**' if zh else '**Cancellation (machine record)**')
        parts.append((f"人类在 {cancelled['node']} 的门 {cancelled['question_id']} 取消（{label}）；业务到此收束，其后 {len(dropped)} 个计划节点未执行："
                      f"{'、'.join(dropped) if dropped else '无'}。执行报告与终答照常生成。") if zh else
                     (f"The human cancelled at gate {cancelled['question_id']} on {cancelled['node']} ({label}); the business work closed there and "
                      f"{len(dropped)} planned node(s) were not run: {', '.join(dropped) if dropped else 'none'}. The execution report and the answer still follow."))
        meta['cancelled'] = cancelled
    if snapshot is not None:
        parts += [('**提交前账目快照（机器记录）**' if zh else '**Pre-commit accounting (machine record)**'),
                  f"scope={snapshot['scope']} · at={snapshot['at']}\n"
                  f"REJECTED={snapshot['rejected_count']} · ERROR={snapshot['error_count']} · "
                  f"anomaly_records={snapshot['anomaly_records']} · unreadable_receipts={snapshot['unreadable_count']}",
                  ('含本轮此前恢复及本节点已归档拒收；不含本次提交和后续 final，最终计数见 EVIDENCE。' if zh else
                   'Includes prior resumes and archived rejections; current commit and later final are excluded. EVIDENCE holds final counts.')]
        if snapshot.get('receipt_identity'):
            parts.append(('回执身份口径（机器记录）：' if zh else 'Receipt identity basis (machine record): ')
                         + _table_cell(json.dumps(snapshot['receipt_identity'], ensure_ascii=False)))
        parts.append('**节点状态（提交前）**' if zh else '**Node states (pre-commit)**')
        parts.append(('| 类别 | 状态与数量 |' if zh else '| Kind | Status and count |') + '\n| --- | --- |\n' + '\n'.join(
            f'| {_label(_TRACK_ZH.get(kind, kind) if zh else kind)} | {_table_cell(json.dumps(counts, ensure_ascii=False))} |'
            for kind, counts in snapshot.get('node_states', {}).items()))
        revision_count = (snapshot.get('revision_anomalies') or {}).get('record_count')
        parts.append((f'异常口径：索引记录 {snapshot["anomaly_records"]}；节点全部修订记录 {revision_count}。两者可能重叠，不相加，不代表独立事件数。' if zh else
                      f'Anomaly scope: index records {snapshot["anomaly_records"]}; all node revisions {revision_count}. Overlapping counts, not summed or treated as distinct events.'))
        parts.extend(_report_evidence_tables(snapshot, zh))
        if snapshot.get('dispatch_accounting'):
            facts = snapshot['dispatch_accounting']
            labels = [('roots','派发根'),('tickets','票据'),('execution_segments','执行段'),
                      ('host_confirmed_returns','宿主确认返回'),
                      ('new_executor_claims','执行段领取（含续跑）' if 'incomplete_root_continuations' in facts else '新执行者领取'),
                      ('main_agent_takeovers','主代理接手'),('human_gate_continuations','人类门续段'),
                      ('ordinary_claims','普通新派发领取' if 'ordinary_resume_claims' in facts else '普通领取'),
                      ('independent_claims','独立领取')]
            labels.extend((key,label) for key,label in [('ordinary_resume_claims','普通同代理续跑领取'),('total_claims','全部领取')] if key in facts)
            labels.extend((key,label) for key,label in [('independent_resume_claims','独立同代理续跑领取'),('independent_raw_claims','独立原始领取')] if key in facts)
            # docs/05SoulRun 87: replacement claims are counted on their own, not as new tasks
            labels.extend((key,label) for key,label in [('replacement_claims','换新代理领取'),('human_chosen_replacements','人选换新代理')] if key in facts)
            if 'incomplete_root_continuations' in facts:
                labels.append(('incomplete_root_continuations','非门同代理续段'))
            labels.extend((key, label) for key, label in (
                ('identity_source_qualification', '原生身份资格（报告非证明）'),
                ('reported_agent_ids_count', '已报告child标识数（未认证）'),
                ('identity_handover_claims', '身份换人领取（含重试）'),
                ('identity_progress_handovers', '不同业务进度的身份交接'),
                ('identity_same_progress_retry_claims', '同进度故障重试领取')) if key in facts)
            rows = ['| 派发账目 | 机器值 |' if zh else '| Dispatch accounting | Machine value |', '| --- | --- |']
            unknown = '未记录（v1 不接宿主返回事件）' if zh else 'Not recorded (v1 has no host-return event bridge)'
            rows.extend(f'| {label if zh else key} | {unknown if facts[key] is None else facts[key]} |' for key,label in labels)
            resumed = facts.get('original_session_resumes') or dict(count=0, verification='UNVERIFIED')
            resume_value = f"{resumed['count']} {resumed['verification']} / UNKNOWN"
            rows.append(f'| 原会话恢复 / Provider物理总量 | {resume_value} |' if zh else
                        f'| Original-session resumes / physical Provider total | {resume_value} |')
            parts.append('\n'.join(rows))
            if 'incomplete_root_continuations' in facts and 'identity_handover_claims' not in facts:
                parts.append('执行段领取包含同代理续跑，不是新child或Provider物理总量；非门续段不计人类答复。' if zh else
                    'The legacy new_executor_claims field includes same-child segment claims, not new child or physical Provider totals. Non-gate continuations are not human answers.')
            if 'identity_handover_claims' in facts:
                parts.append('身份换人以绑定的人答授权；旧式segment_resume不构成人类答复。报告与逻辑领取不认证原生身份，也不证明物理退出。' if zh else
                    'Identity handovers require the bound human choice; legacy segment_resume is not a human answer. '
                    'Reports and logical claims do not authenticate native identity or attest physical exit.')
        if snapshot.get('review_candidate_bindings'):
            parts.append('**评审绑定（机器记录）**' if zh else '**Review bindings (machine record)**')
            rows = ['| 评审根 | 候选摘要 | 状态 |' if zh else '| Review root | Candidate digest | Status |', '| --- | --- | --- |']
            for r in snapshot['review_candidate_bindings']:
                root = r.get('root') or {}
                rows.append(f"| {_table_cell(str(root.get('node'))+'@'+str(root.get('visit')))} | {_table_cell(str(r.get('candidate_digest'))[:12])} | {r['status']} |")
            parts.append('\n'.join(rows))
            parts.append('评审分数只证明快照那一版；CHANGED_AFTER_REVIEW 表示当前内容未经该次评审；EVIDENCE_CHANGED 表示证据无法复核。是否需要复评由程序流程决定。' if zh else
                         'Scores certify only the snapshotted candidate. CHANGED_AFTER_REVIEW means current content was not reviewed by that root; EVIDENCE_CHANGED means evidence cannot be reverified. The program decides whether to review again.')
        hsaw = snapshot.get('hsaw')
        if hsaw is not None:   # alpha.87 (doc 193 R-a): the sovereignty doubt gate record, graded critical / medium / low
            parts.append('**主权疑惑门记录（机器记录）**' if zh else '**Sovereignty doubt gate record (machine record)**')
            rows = hsaw.get('rows') or []
            if rows:
                parts.append(('| 编号 | 类别 | 级别 | 节点 | 标题 | 处置 | 门 | 人的回答 |' if zh else '| Id | Category | Severity | Node | Title | Disposition | Gate | Human answer |')
                             + '\n| --- | --- | --- | --- | --- | --- | --- | --- |\n' + '\n'.join(
                    f"| {_table_cell(r['id'])} | {_table_cell(r['category'])} | {_table_cell(r['severity'])} | {_table_cell(r['node'])} | {_table_cell(r['title'])} | "
                    f"{_table_cell(r['disposition'])} | {_table_cell(r['question_id'] or '—')} | {_table_cell(r['answer'] or '—')} |" for r in rows))
            else:
                parts.append('本场没有条目。' if zh else 'No items this run.')
            parts.append((f"critical {hsaw['critical']} · medium {hsaw['medium']} · low {hsaw['low']} · 门 {hsaw['gates']}；该包累计已发现且未关闭的条目 {hsaw['open']} 条（按指纹去重）。" if zh else
                          f"critical {hsaw['critical']} · medium {hsaw['medium']} · low {hsaw['low']} · gates {hsaw['gates']}; open items of this package across runs: {hsaw['open']} (by fingerprint)."))
            problems = [*(hsaw.get('register_problems') or []), *(hsaw.get('ledger_problems') or [])]
            if problems:
                parts.append(('台账链问题：' if zh else 'Ledger problems: ') + '; '.join(problems)[:400])
        um_rows = snapshot.get('user_messages') or []
        if um_rows:   # alpha.93 (doc 218): what each business / sub node declared it gives the user, as the engine checked it
            parts.append('**User Message 记录（机器记录）**' if zh else '**User Message record (machine record)**')
            head = ('| 节点 | 声明 | 条数 | 逐字原文 | 不适用 / 无的理由 |' if zh else '| Node | Declared | Items | Verbatim texts | Not applicable / none reason |')
            yes, no = ('有', '无') if zh else ('yes', 'no')
            lines = []
            for r in um_rows:
                why = '; '.join(r['not_applicable']) if r['has'] else (r['none_reason'] or '')
                if r.get('prose_output_chars'):
                    why += (f'（输出里另有 {r["prose_output_chars"]} 字符自然语言）' if zh else f' (output carries {r["prose_output_chars"]} characters of prose)')
                lines.append(f"| {_table_cell(r['node'])} | {yes if r['has'] else no} | {r['messages']} | {r['literals']} | {_table_cell(why or '—')} |")
            parts.append(head + '\n| --- | --- | --- | --- | --- |\n' + '\n'.join(lines))
        meta['snapshot'] = snapshot
    return dict(payload, user_summary='\n\n'.join(parts)), meta


def _report_evidence_tables(snapshot, zh):
    parts = []
    if 'source_support' in snapshot:
        parts.append('**来源支持性核验（机器记录）**' if zh else '**Source support (machine record)**')
        sources = snapshot['source_support']
        if sources:
            head = ('| 节点 / visit / 修订 | 模型标注 SV | 机器 SV / D / U | 降级或重分类 | 核验范围 / 检索权威 |' if zh else
                    '| Node / visit / revision | Model-labelled SV | Machine SV / D / U | Demotions or reclassifications | Verification / retrieval scope |')
            lines = [head, '| --- | --- | --- | --- | --- |']
            for r in sources:
                changes = [f"{d.get('claim_id')}: {d.get('reason')}" for key in ('demoted','reclassified_derived') for d in r.get(key) or []]
                effective = r.get('effective_counts')
                if effective is not None:
                    values = '/'.join(str(effective[k]) for k in ('source_verified', 'derived', 'unverified', 'ambiguous'))
                    changes.append(f"effective SV/D/U/A={values}; unique={r['unique_claims']}; unidentified={r['unidentified_observations']}; SV/D/U column=legacy ID-label observations")
                cells = [f"{r['node']} / {r['visit']} / {r['revision']}", r.get('labelled'),
                         ' / '.join(str(r.get(k)) if r.get(k) is not None else 'UNKNOWN' for k in ('source_verified','derived','unverified')),
                         '; '.join(changes) or '-', f"{r.get('verification_scope') or 'UNKNOWN'} / {r.get('retrieval_provenance') or 'UNKNOWN'}"]
                lines.append('| ' + ' | '.join(_table_cell('UNKNOWN' if c is None else c) for c in cells) + ' |')
            parts.append('\n'.join(lines))
        else:
            parts.append('未记录来源支持性核验；不等于核验通过。' if zh else 'No source-support record; this is not a verification pass.')
        parts.append(('SV/D/U = source_verified/derived/unverified。每行是该 occurrence 最新修订，转交同一台账不相加。模型标注不是机器接受；捕获内容支持不是外部真相或检索认证。' if zh else
                      'SV/D/U = source_verified/derived/unverified. Latest revision per occurrence; forwarded ledgers are not summed. Model labels are not accepted counts; captured support is not external truth or retrieval attestation.'))
    if 'artifacts' in snapshot:
        parts.append('**工件观察（机器记录）**' if zh else '**Artifact observations (machine record)**')
        artifacts = snapshot['artifacts']
        if artifacts:
            head = ('| 节点 / visit / 修订 | 路径 | 类型 / 说明 | 声明操作 | 观测 SHA-256 |' if zh else
                    '| Node / visit / revision | Path | Kind / note | Declared operation | Observed SHA-256 |')
            lines = [head, '| --- | --- | --- | --- | --- |']
            for r in artifacts:
                cells = [f"{r['node']} / {r['visit']} / {r['revision']}", r.get('path'),
                         f"{r.get('kind') or '-'} / {r.get('note') or '-'}", r.get('declared_operation') or 'unspecified',
                         r.get('observed_sha256') or 'UNOBSERVED']
                lines.append('| ' + ' | '.join(_table_cell('UNKNOWN' if c is None else c) for c in cells) + ' |')
            parts.append('\n'.join(lines))
        else:
            parts.append('没有登记工件；不证明没有副作用。' if zh else 'No registered artifacts; this does not prove no side effects.')
        parts.append(('包含已接受修订的登记，不代表全部副作用；操作为声明值，文件哈希不证明操作、业务成功或可安全删除。' if zh else
                      'Accepted revision registrations, not all side effects; operations are declared, and file hashes do not prove operations, business success or safe deletion.'))
    return parts


REPORT_COUNT_KEYS = (('protocol_rejected_count', 'rejected_count'), ('protocol_error_count', 'error_count'))
_TRACK_ZH = dict(main='主节点 main', sub='子节点 sub', engine='引擎节点 engine', final='终答 final')   # alpha.84: the three tracks by name
_CLAUSE = r'(?:^[\s>#\-]*(?:\d+[.)]\s+)?|[，,、：:（(|]\s*)'   # a statement may open a sentence / list item, follow a comma or colon, or sit in a table cell
_STATUS_PASS = re.compile(_CLAUSE + r'(?:整轮|本轮|总体)?(?:功能状态|functional(?:_status| status))[\s:：=|]*(?:为|是|is)?\s*PASS\b(?!\s*[/、])', re.I)   # `PASS / DEGRADED / ...` enumerates, it states nothing
_ALL_PASS = re.compile(_CLAUSE + r'(?:(?:全部|所有)\s*)?(\d+)\s*个业务节点\s*(?:全部|全都|均|都)\s*(?:为|是)?\s*(?:PASS|通过)'
                       r'|' + _CLAUSE + r'all\s+(\d+)\s+business\s+nodes\s+(?:are\s+|were\s+)?(?:PASS|passed)\b', re.I)
# alpha.84 (doc 176 A2; isolated run doc 175 §4.3: "九个主节点全部以 PASS 完成" / "9/9 主节点提交成功" - six main nodes, three engine nodes):
# Chinese numerals, the main-node noun (main nodes ONLY - 业务节点 above stays main + sub) and the n/n form.
_ZH_NUM = r'[二三四五六七八九]?十[一二三四五六七八九]?|[一二两三四五六七八九]|\d+'
_MAIN_ALL_PASS = re.compile(_CLAUSE + r'(?:(?:全部|所有)\s*)?(' + _ZH_NUM + r')\s*个\s*主(?:业务)?节点\s*(?:全部|全都|均|都)\s*(?:以|为|是)?\s*(?:PASS|通过)'
                            r'|' + _CLAUSE + r'(\d+)\s*/\s*(\d+)\s*(?:个\s*)?主(?:业务)?节点', re.I)
_ZH_DIGIT = dict(zip('一二两三四五六七八九', (1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))


def _number(text):
    """一 .. 九十九 (and 两), or Arabic digits."""
    if text.isdigit():
        return int(text)
    if '十' in text:
        tens, _, ones = text.partition('十')
        return (_ZH_DIGIT[tens] if tens else 1) * 10 + (_ZH_DIGIT[ones] if ones else 0)
    return _ZH_DIGIT[text]
_HEDGE_BEFORE = re.compile(r'若|如果|假如|假设|除非|不能|不得|不可|不应|并非|不是|未能|尚未|先前|此前|之前|早先|旧快照|旧时点|旧值|\b(?:if|unless|not|never|cannot|earlier|previous|older)\b', re.I)
_HEDGE_AFTER = re.compile(r'^[^，,。；;]{0,12}(?:不成立|不正确|不准确|有误|错误|才|wrong|incorrect)', re.I)


def _asserted(sentence, match):
    """Quoted, conditional, negated, historical and corrected statements remain model prose."""
    before, after = sentence[:match.start()], sentence[match.end():]
    quoted = any(before.count(a) > before.count(b) for a, b in (('「', '」'), ('“', '”'), ('《', '》'))) or before.count('"') % 2
    return not (quoted or _HEDGE_BEFORE.search(before) or _HEDGE_AFTER.search(after))


def report_consistency_errors(payload, snapshot, *, status=None):
    """Unqualified whole-run assertions of the Report against the accepted node records; not an NLP truth gate. Emphasis and code marks never
    change a fact, and a statement may sit behind a comma or in a table cell (production cache/32, doc 162 §3.1). `status` overrides
    semantics.functional_status when the caller already knows the status the run allows. Machine-owned output counts: align_report_counts."""
    issues = []
    text = re.sub(r'[*`]', '', payload.get('user_summary') or '')
    status = status or (payload.get('semantics') or {}).get('functional_status')
    states = snapshot.get('node_states') or {}
    business = [states.get('main') or {}, states.get('sub') or {}]
    total = sum(sum(c.values()) for c in business)
    all_pass = not any(n for c in business for s, n in c.items() if s != 'PASS')
    for sentence in re.split(r'[。\n;；]', text):
        for match in _STATUS_PASS.finditer(sentence):
            if status != 'PASS' and _asserted(sentence, match):
                issues.append(dict(field='user_summary', found=sentence.strip()[:120], expected=f'whole-run functional status {status}'))
        for match in _ALL_PASS.finditer(sentence):
            if (int(match[1] or match[2]) != total or not all_pass) and _asserted(sentence, match):
                issues.append(dict(field='user_summary', found=sentence.strip()[:120],
                                   expected=dict(main=states.get('main'), sub=states.get('sub'), note='main and sub occurrences are counted separately')))
        main = states.get('main') or {}
        for match in _MAIN_ALL_PASS.finditer(sentence):   # alpha.84: the main track only; engine nodes (Router.*, final) are never main nodes
            stated = _number(match[1]) if match[1] else int(match[3])
            held = {sum(main.values()), snapshot.get('main_nodes')} - {None}   # occurrences, or distinct nodes when a node was revisited
            wrong = stated not in held or (match[1] and any(n for s, n in main.items() if s != 'PASS'))
            if wrong and _asserted(sentence, match):
                issues.append(dict(field='user_summary', found=sentence.strip()[:120],
                                   expected=dict(main=main, sub=states.get('sub'), engine=states.get('engine'),
                                                 note='main nodes are the program nodes of the main graph; engine nodes (Router.*, final) and sub nodes are counted apart')))
    return issues


def align_report_counts(payload, snapshot):
    """Machine-owned duplicates in Engine.execute-report output follow the snapshot, like output.human_decisions (alpha.58): a rejection would
    change the very count it checks (the rejection is one more archived receipt). Recorded with the model value, never silent."""
    output, notes = payload.get('output'), []
    if isinstance(output, dict):
        fixed = dict(output)
        for key, fact in REPORT_COUNT_KEYS:
            if key in fixed and fixed[key] != snapshot[fact]:
                notes.append(dict(code='REPORT_COUNT_ALIGNED', text=f'output.{key}: model value {fixed[key]!r} -> {snapshot[fact]} '
                                  f'(machine-owned count, scope={snapshot["scope"]}; prose is never edited)'))
                fixed[key] = snapshot[fact]
        if notes:
            payload = dict(payload, output=fixed)
    return payload, notes


_ZERO_ANOMALIES = re.compile(r'无异常(?!波动)|零异常|\bno\s+anomalies\b|无\s+anomalies|异常[：:=]\s*(?:0(?!\d)|无(?![\u4e00-\u9fff]))', re.I)
_ANOMALY_SCOPE = re.compile(r'(?P<local>本节点|当前节点|\bthis node\b)|'
                            r'(?P<run>本轮|整轮|全轮|本次运行|前序节点|其他节点|全部\s*\d+\s*个节点|\b(?:whole run|entire run|upstream nodes)\b)', re.I)


def _zero_anomaly_conflicts(text, payload, index, local_anomalies):
    records = index.get('anomalies_summary') or []
    local_count = sum(1 for row in records if row.get('node') == payload.get('node'))
    local_count += len(payload.get('anomalies') or []) + len(local_anomalies)
    scopes = set()
    for sentence in re.split(r'[。！!\n；;]|[，,]\s*(?:但是|但|不过|然而|but\b|however\b)', text, flags=re.I):
        for match in _ZERO_ANOMALIES.finditer(sentence):
            if (not _ANOMALY_SCOPE.search(sentence[:match.start()]) and
                    re.match(r'\s*(?:不等于|不代表|不意味着|does not mean\b|is not equivalent to\b)', sentence[match.end():], re.I)):
                continue
            scope_marks = list(_ANOMALY_SCOPE.finditer(sentence[:match.start()]))
            local = bool(scope_marks and scope_marks[-1].lastgroup == 'local')
            if (local_count if local else len(records)) and _asserted(sentence, match):
                scopes.add('node_before_report' if local else 'whole_run_before_report')
    if records and re.search(r'异常为零[^。\n]{0,80}本轮[^。\n]{0,12}两者都是零', text):
        scopes.add('whole_run_before_report')
    return sorted(scopes)


def report_fact_findings(payload, index, *, snapshot=None, local_anomalies=()):
    """Record an explicit zero claim conflicting with prior records; never rewrite prose."""
    text = '\n'.join([payload.get('user_summary') or '', payload.get('explain') or ''])
    findings = []
    for scope in _zero_anomaly_conflicts(re.sub(r'[*`]', '', text), payload, index, local_anomalies):
        findings.append(dict(code='REPORT_FACT_CONFLICT', text=f'Report claims no anomalies despite recorded anomalies; scope={scope}; original text retained.'))
    hsaw_count = sum(1 for e in index.get('hsaw_register') or [] if isinstance(e, dict) and e.get('kind') == 'discovered')   # alpha.87
    if hsaw_count and re.search(r'(?:无|没有|零|不存在)\s*(?:HSAW|主权疑惑门?|疑惑门)\s*(?:条目|记录|事项)?|(?:HSAW|疑惑门)\s*(?:条目|记录)?\s*[：:=]\s*(?:0|无|没有|零)(?=[，,。.！!\s]|$)|\bno\s+hsaw\s+(?:items|entries|records)\b|\bhsaw(?:\s+items)?\s*[:=]\s*0\b', text, re.I):
        findings.append(dict(code='REPORT_FACT_CONFLICT', text=f'Report claims no HSAW items but {hsaw_count} were recorded in this run; original text retained (alpha.87).'))
    if snapshot:
        effects = [r for r in snapshot.get('receipt_effects') or [] if r['count'] > 0]
        # Narrow whole-run denials only, not quoted old errors, hypothetical policy or comparisons.
        denial = r'(?:本轮|本次运行)?(?:无删除操作发生|没有删除任何文件|未执行清理)|\bNo deletion occurred\b'
        sentences = re.split(r'[\n。；;]', re.sub(r'[*`]', '', text))
        if effects and any(_asserted(s, m) and not re.search(r'声称|原文|旧报告|下次|下一轮|如果|假设|本节点|不证明|不等于|不代表', s[:m.start()])
                           for s in sentences for m in re.finditer(denial, s, re.I)):
            findings.append(dict(code='REPORT_SIDE_EFFECT_CONFLICT', text=(
                'Whole-run no-deletion/cleanup statement conflicts with positive bound receipt counts: '
                + ', '.join(f"{r['node']}@{r['visit']} r{r['revision']} {r['field']}={r['count']}" for r in effects)
                + '. Receipt assertions, not an independent filesystem audit; original prose retained.')))
        for key, code in [('rejected_count', 'REJECTED'), ('error_count', 'ERROR')]:
            values = re.findall(rf'\b{code}\s*[:=]?\s*(\d+)\b|(\d+)\s*次\s*{code}\b', text)
            wrong = sorted({int(a or b) for a, b in values} - {snapshot[key]})
            if wrong:
                findings.append(dict(code='REPORT_COUNT_CONFLICT', text=f'{code} prose counts {wrong} differ from {snapshot[key]}; scope={snapshot["scope"]}; diagnostic only, an explicitly older snapshot may be legitimate.'))
    return findings


def node_anomalies(payload, machine, previous=()):
    text = [f'[revision {n}] {item}' for n, row in enumerate(previous)
            for item in node_anomalies(row['payload'], row['machine'])]
    text.extend(payload.get('anomalies') or [])
    for item in machine.get('engine_anomalies') or []:
        text.append(f"[engine:{item['code']}] {item['text']}")
    return list(dict.fromkeys(text))


def evidence_anomalies(payload):
    rows = []
    for call in payload['evidence']['tool_calls']:
        if call.get('verified_by') == 'engine' and call.get('exit_code') not in (None, 0):
            # docs/05SoulRun 87: the call's own declared purpose rides along, so a conventional exit 1 (diff: the files differ, grep:
            # nothing found) reads as what it is; the judgement and the fields are unchanged
            purpose = ' '.join(str(call.get('purpose') or '').split())
            purpose = f" (purpose: {purpose[:160]}{'…' if len(purpose) > 160 else ''})" if purpose else ''
            rows.append(dict(code='PROCESS_EXIT_NONZERO', text=(
                f"{call['stdout_path']}: exit_code={call['exit_code']}{purpose}; a later success does not erase this attempt")))
    for artifact in payload['evidence']['artifacts']:
        if artifact['kind'] == 'directory':
            rows.append(dict(code='DIRECTORY_MEMBERS_UNOBSERVED', text=(
                f"{artifact['path']}: directory existence only; individual file changes are not verified by this entry")))
    return rows
