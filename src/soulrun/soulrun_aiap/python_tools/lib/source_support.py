"""Validate declared claim support against captured content, not external truth."""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
from decimal import Decimal, InvalidOperation

from . import contracts as _contracts   # alpha.97 (doc 233)


RULE = _contracts.text("evidence.source_support")
REPAIR_RULE = _contracts.text("evidence.source_repair")   # alpha.107 (doc 269 T3): after a refusal only, in _HELP
SCOPE = 'captured_content_support_not_external_truth'
_NUMBER = re.compile(r'(?<![\d.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\d.])')


def input_template():
    """Unfilled canonical shape, not an automatic claim or retrieval attestation."""
    return dict(
        source=dict(source_id='<source-id>', url='<actual source URL; replace with path for a local source>',
                    content_kind='original', content_ref='<saved original address>', retrieved_at=None),
        claim=dict(claim_id='<unique-id>', verification='source_verified', value=None, source_ids=['<source-id>'],
            support_check=dict(performed=None, method=None, located_in='<source-id>', evidence_span=None, result=None)),
        rule='Fill only from work actually done. Original support: performed=true, result=supported, method=exact_span|numeric_equality|restatement. '
             'Use one directly supported value per claim and copy its exact passage; a whole array/table needs atomic claims, not a scalar summary. '
             'Numeric units/scales must match: 2.5 billion cannot directly verify 2500 million; record that conversion as derived. '
             'restatement is a semantic paraphrase, never a numeric-conversion bypass. Keep public claim IDs identical after splitting. '
             'Reuse validated inherited claims by input reference, not retyped incomplete support objects. '
             'Save each fetched original once and bind content_ref, e.g. work:original.txt; reuse it. '
             'For derived inputs Node@visit/claim_id, include an explicit input reference to that committed output; '
             'the written ID alone is not authority. '
             'A source needs exactly one actual url or path, not neither/both. Without captured support use unverified, not performed=true. '
             'For a plain search source omit BOTH content_kind/content_ref; '
             'never fabricate a capture, timestamp or URL. Templates/placeholders are not evidence; no extra fetch or preflight required. '
             + LOCATOR_HELP + ' Public checked counts use machine effective_counts; legacy source_verified/derived/unverified count ID-label observations. Ambiguous identities are not verified. Read the complete proof by source_support_read when needed.',
        locator=dict(anchor='<a phrase of the saved original, at least 8 characters, occurring once>',
                     until='<optional phrase that ends the passage, or omit>'))


class SupportError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


class SupportErrors(SupportError):
    def __init__(self, issues):
        super().__init__(issues[0]['field'], issues[0]['message'])
        self.issues = issues


class InheritedClaim(dict):
    """In-memory origin from digest-checked input expansion, never a payload field."""

    def __init__(self, value, *, scope, checked, classes, demoted):
        super().__init__(value)
        self.origin = (scope, checked, classes, frozenset(demoted))


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalize(value):
    return ' '.join(value.split())


LOCATOR_MIN, LOCATOR_SPAN_MAX = 8, 1200
LOCATOR_HELP = ('Instead of copying evidence_span, support_check may carry evidence_locator {anchor, until}: anchor is a phrase of the '
                'saved original (at least 8 characters, occurring once in it), until an optional phrase that ends the passage within '
                '1,200 characters after the anchor; the engine cuts the passage from the original itself and checks the value in it (alpha.98).')


def _locate(locator, text, field):
    """alpha.98 (04 series doc 236): the supporting passage cut from the saved original by the engine, so the executor never retypes it -
    anchor must occur exactly once in the whitespace-normalised original; until, when given, ends the passage."""
    if not isinstance(locator, dict) or not isinstance(locator.get('anchor'), str) or len(_normalize(locator['anchor'])) < LOCATOR_MIN:
        raise SupportError(field, f'evidence_locator needs anchor: a phrase of the saved original, at least {LOCATOR_MIN} characters (alpha.98)')
    norm, anchor = _normalize(text), _normalize(locator['anchor'])
    first = norm.find(anchor)
    if first < 0:
        raise SupportError(field + '.anchor', 'the anchor is absent from the captured original - copy a phrase of that file exactly (alpha.98)')
    if norm.find(anchor, first + 1) >= 0:
        raise SupportError(field + '.anchor', 'the anchor occurs more than once in the captured original - lengthen it until it is unique (alpha.98)')
    until = locator.get('until')
    if until is None or (isinstance(until, str) and not until.strip()):
        return anchor
    if not isinstance(until, str):
        raise SupportError(field + '.until', 'until is a phrase of the saved original (alpha.98)')
    end = norm.find(_normalize(until), first + len(anchor))
    if end < 0 or end + len(_normalize(until)) - first > LOCATOR_SPAN_MAX:
        raise SupportError(field + '.until', f'until is absent within {LOCATOR_SPAN_MAX} characters after the anchor (alpha.98)')
    return norm[first:end + len(_normalize(until))]


WINDOW = 240   # alpha.99 (doc 239 S7): characters on each side of a passage in which the value may stand - about two sentences
_HTML_MARK = re.compile(r"<!doctype html|<html[\s>]|<body[\s>]|<div[\s>]|<table[\s>]", re.I)
CONVERSIONS = (Decimal(100), Decimal("0.01"), Decimal(1000), Decimal("0.001"), Decimal(10) ** 6, Decimal(10) ** -6, Decimal(10) ** 9, Decimal(10) ** -9)


def html_text(raw: str) -> str:
    """alpha.99 (doc 239 S5; isolated cache 66: passages quoted from the rendered page, the saved original was HTML source): the text a
    reader sees - scripts, styles and comments removed, tags turned into spaces, entities decoded, whitespace normalised."""
    t = re.sub(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1\s*>", " ", raw)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return _normalize(_html.unescape(t))


def _forms(raw: str, address: str, body=None) -> list[tuple[str, str]]:
    """the forms a passage may be found in: the parsed content as text, the raw bytes as text, the rendered text of an HTML original"""
    forms = []
    if body is not None:
        forms.append(("parsed", _normalize(_text(body))))
    if isinstance(raw, str):
        forms.append(("raw", _normalize(raw)))
        if _HTML_MARK.search(raw[:4000]) or address.lower().endswith((".htm", ".html")):
            forms.append(("html", html_text(raw)))
    seen, out = set(), []
    for kind, form in forms:
        if form and form not in seen:
            seen.add(form)
            out.append((kind, form))
    return out


def _numbers(text):
    out = set()
    for n in _NUMBER.findall(text):
        try:
            out.add(Decimal(n.replace(',', '')))
        except InvalidOperation:
            pass
    return out


def _significant(value) -> int:
    return len(format(Decimal(str(value)).copy_abs(), "f").replace(".", "").lstrip("0"))


_SCALAR_NUMBER = re.compile(r'[-+]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?')


def value_matches(span, value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return Decimal(str(value)) in _numbers(span)
        except InvalidOperation:
            return False
    norm = _normalize(str(value))
    percent = norm.endswith(('%', '％'))
    scalar = norm[:-1].rstrip() if percent else norm
    if _SCALAR_NUMBER.fullmatch(scalar):
        number = Decimal(scalar.replace(',', ''))
        text = _normalize(span)
        return any(Decimal(m[0].replace(',', '')) == number
                   for m in _NUMBER.finditer(text)
                   if not percent or re.match(r'\s*[%％]', text[m.end():]))
    return bool(norm) and norm in _normalize(span)


def validate(output, sources, resolve, *, raw_text=None, candidates=None, upstream_ids=(), notes=None, claim_scope=None):
    """alpha.99 (04 series doc 239 §3.4): every source_verified claim is checked against captured content, never external truth. What the
    engine can establish itself it establishes (a missing claim_id, located_in, the capture that holds the passage, the rendered text of
    an HTML original, the value just outside a short passage, a unit conversion that belongs to derived); a claim that still cannot be
    supported is DEMOTED to unverified with its reason - counted so, listed in the result, never refused. resolve(address, field) returns
    (engine metadata, content); raw_text(address) the capture's bytes as text; candidates() this run's saved files as (address, text).
    Only a cyclic / overdeep claim reference or an unreadable claim address still raises SupportError."""
    by_id, loaded, failed_loads, used, inherited = {}, {}, {}, {}, {}
    located, demoted, derived_by_engine, repairs = [], [], [], []
    counts = dict(source_verified=0, derived=0, unverified=0)
    checked_ids = set()
    classifications, dependencies, claim_sources = {}, {}, {}
    scoped_labels, scoped_inputs, carrier_origins = {}, {}, {}
    labelled = set()   # alpha.99: the claims this commit labels source_verified itself (not inherited) - the base of the evidence round
    counted = set()   # alpha.89 (doc 186): (claim_id, label) pairs already counted - a ledger referenced twice counts once per claim_id
    identities, unidentified = {}, set()
    engine_ids = iter(range(1, 1_000_000))
    texts, cand_list = {}, None

    for i, source in enumerate(sources):
        if ('content_kind' in source) != ('content_ref' in source):
            if 'content_ref' in source:
                source['content_kind'] = 'original'
            else:
                source.pop('content_kind', None)
            repairs.append(('SOURCE_CONTENT_PAIRED', f'evidence.sources[{i}]: content_kind and content_ref made a pair'))
        if source.get('source_id'):
            by_id.setdefault(source['source_id'], []).append((i, source))

    def load(address, field):
        if not isinstance(address, str):
            raise SupportError(field, 'expected a captured-content address')
        if address in failed_loads:
            raise failed_loads[address]
        if address not in loaded:
            try:
                loaded[address] = resolve(address, field)
            except SupportError as exc:
                failed_loads[address] = exc
                raise
        return loaded[address]

    def find(passage, address, body=None):
        """(form, kind) of the first form of this capture that holds the passage, or (None, None)"""
        if address not in texts:
            meta = (loaded.get(address) or ({}, None))[0]
            texts[address] = _forms(raw_text(address, meta) if raw_text else None, address, body)
        norm = _normalize(passage)
        for kind, form in texts[address]:
            if norm and norm in form:
                return form, kind
        return None, None

    def in_candidates(passage, exclude=None):
        nonlocal cand_list
        if not candidates:
            return []
        if cand_list is None:
            cand_list = [(a, t) for a, t in candidates() if isinstance(t, str)]
        hits = []
        for address, raw in cand_list:
            if address == exclude:
                continue
            if address not in texts:
                texts[address] = _forms(raw, address)
            if find(passage, address)[0] is not None:
                hits.append(address)
        return hits

    def count(cid, label, scope=None, field=None):
        key = (cid, label) if isinstance(cid, str) and cid else None
        if key:
            classifications.setdefault(cid, set()).add(label)
            identity = f'{scope}/{cid}' if scope else cid
            identities.setdefault(identity, set()).add(label)
        else:
            unidentified.add((scope, field))
        if key is None or key not in counted:
            counts[label] += 1
            if key:
                counted.add(key)

    def demote(cid, field, reason, scope=None):
        demoted.append(dict(claim_id=cid, field=field, reason=reason))
        count(cid, 'unverified', scope, field)

    def value_in(span, value):
        return value_matches(span, value)

    def locate(locator, form, value):
        """the passage an evidence_locator names in one text form: the anchor alone, or through until (WINDOW characters after the anchor
        when until is absent); a repeated anchor -> the one occurrence whose passage holds the value; otherwise None"""
        anchor = _normalize(locator['anchor'])
        until = locator.get('until')
        passages = []
        for m in re.finditer(re.escape(anchor), form):
            first = m.start()
            if isinstance(until, str) and until.strip():
                end = form.find(_normalize(until), first + len(anchor))
                if end >= 0 and end + len(_normalize(until)) - first <= LOCATOR_SPAN_MAX:
                    passages.append(form[first:end + len(_normalize(until))])
                    continue
                repairs.append(('SUPPORT_LOCATOR_REPAIRED', f'until absent: the anchor and the {WINDOW} characters after it'))
                passages.append(form[first:first + len(anchor) + WINDOW])
            else:
                passages.append(anchor)
        if len(passages) == 1:
            return passages[0]
        holding = [p for p in dict.fromkeys(passages) if value_in(p, value)]
        if len(holding) == 1 and len(passages) > 1:
            repairs.append(('SUPPORT_LOCATOR_REPAIRED', 'repeated anchor: the one occurrence whose passage holds the value'))
            return holding[0]
        return passages[0] if len(set(passages)) == 1 and passages else None

    def check(claim, field, prior=False, prior_demoted=frozenset(), scope=None, prior_classes=None):
        label = claim.get('verification')
        cid = claim.get('claim_id', claim.get('id'))
        def record(label):
            count(cid, label, scope, field)
        def lower(reason):
            return demote(cid, field, reason, scope)
        if not isinstance(label, str) or label not in counts:
            repairs.append(('SUPPORT_LABEL_INVALID', f'{field}.verification {label!r} counted as unverified'))
            record('unverified')
            return
        if prior and isinstance(cid, str) and isinstance(prior_classes, dict):
            labels = {k for k in (*counts, 'ambiguous') if cid in (prior_classes.get(k) or [])}
            if len(labels) == 1 and 'ambiguous' not in labels:
                checked_label = next(iter(labels))
                if checked_label == 'unverified' and label == 'source_verified':
                    return lower('demoted where it was first checked')
                if checked_label == 'source_verified':
                    checked_ids.add(cid)
                record(checked_label)
                return
        if label != 'source_verified':
            record(label)
            return
        if not isinstance(cid, str) or not cid:
            cid = f'E{next(engine_ids)}'
            repairs.append(('SUPPORT_CLAIM_ID_ASSIGNED', f'{field} -> {cid}'))
        if not prior:
            labelled.add(cid)
        if prior:
            if cid in prior_demoted:
                return lower('demoted where it was first checked')
            checked_ids.add(cid)
            record('source_verified')
            return
        support = claim.get('support_check')
        if not isinstance(support, dict):
            if cid in upstream_ids:
                repairs.append(('SUPPORT_INHERITED_BY_ID', f'{field} ({cid}) is a claim an upstream node checked'))
                checked_ids.add(cid)
                record('source_verified')
                return
            return lower('no captured-content support check')
        value = claim.get('value')
        if 'value' not in claim or value is None or (isinstance(value, str) and not value.strip()):
            return lower('no value to support')
        locator = support.get('evidence_locator') if isinstance(support.get('evidence_locator'), dict) else None
        anchor = locator.get('anchor') if locator and isinstance(locator.get('anchor'), str) and len(_normalize(locator['anchor'])) >= LOCATOR_MIN else None
        passage = support.get('evidence_span') if isinstance(support.get('evidence_span'), str) and support['evidence_span'].strip() else None
        if anchor is None and locator is not None and passage:
            repairs.append(('SUPPORT_LOCATOR_REPAIRED', f'{field}: evidence_locator unusable, evidence_span used'))
        probe = anchor or passage
        if probe is None:
            return lower('no evidence_span or evidence_locator')
        ids = [x for x in claim['source_ids'] if isinstance(x, str)] if isinstance(claim.get('source_ids'), list) else []
        sid = support.get('located_in')
        single = lambda s: isinstance(s, str) and len(by_id.get(s, [])) == 1
        if not single(sid):
            options = [s for s in dict.fromkeys(ids) if single(s)]
            if len(options) > 1:
                holders = []
                for s in options:
                    ref = by_id[s][0][1].get('content_ref')
                    if isinstance(ref, str):
                        try:
                            _meta, body = load(ref, field)
                        except SupportError:
                            continue
                        if find(probe, ref, body)[0] is not None:
                            holders.append(s)
                options = holders
            if len(options) != 1:
                return lower('located_in names no single declared source')
            repairs.append(('SUPPORT_LOCATED_IN_INFERRED', f'{field} -> {options[0]}'))
            sid = options[0]
        elif ids and sid not in ids:
            repairs.append(('SUPPORT_LOCATED_IN_INFERRED', f'{field}: located_in {sid} kept although source_ids {ids} omit it'))
        i, source = by_id[sid][0]
        address = source.get('content_ref')
        own = source.get('content_kind') == 'original' and isinstance(address, str) and address.startswith(('work:', 'proc:', 'artifact:', 'input:'))
        form, kind = None, None
        if own:
            try:
                _meta, body = load(address, f'evidence.sources[{i}].content_ref')
                form, kind = find(probe, address, body)
            except SupportError:
                form = None
        if form is None:
            hits = in_candidates(probe, exclude=address if own else None)
            if len(hits) != 1:
                where = 'nor in any saved file of this run' if not hits else f'and it is in {len(hits)} saved files'
                return lower(('the passage is not in the saved original ' if own else 'the source has no saved original, ') + where)
            repairs.append(('SOURCE_CAPTURE_REBOUND' if own else 'SOURCE_CAPTURE_BOUND', f'{field}: {sid} -> {hits[0]}'))
            address = hits[0]
            form, kind = find(probe, address)
        if kind == 'html':
            repairs.append(('SOURCE_HTML_TEXT_USED', f'{field}: found in the rendered text of {address}'))
        span = locate(locator, form, value) if anchor else _normalize(passage)
        if span is None:
            return lower('the evidence_locator names no single passage')
        if anchor and passage and _normalize(passage) not in span:   # the two disagree: the one that holds the value is the passage
            given = _normalize(passage)
            if value_in(span, value):
                repairs.append(('SUPPORT_LOCATOR_REPAIRED', f'{field}: evidence_span differs from the located passage; the located passage holds the value'))
            elif given in form:
                repairs.append(('SUPPORT_LOCATOR_REPAIRED', f'{field}: evidence_span differs from the located passage; evidence_span was used'))
                span = given
            else:
                return lower('evidence_span differs from the passage evidence_locator names')
        if anchor:
            located.append(dict(claim_id=cid, source_id=sid, chars=len(span), sha256=hashlib.sha256(span.encode('utf-8')).hexdigest()))
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if (numeric or support.get('method') != 'restatement') and not value_in(span, value):
            at = form.find(span)
            window = form[max(0, at - WINDOW): at + len(span) + WINDOW] if at >= 0 else span
            if value_in(window, value) and (not numeric or _significant(value) >= 3):
                repairs.append(('SUPPORT_SPAN_WIDENED', f'{field}: the value stands within {WINDOW} characters of the passage'))
            elif numeric and any(Decimal(str(value)) * k in _numbers(span) for k in CONVERSIONS):
                derived_by_engine.append(dict(claim_id=cid, field=field, reason='a unit / percent conversion of a number in the passage'))
                record('derived')
                return
            else:
                return lower('the value is not in the passage')
        if support.get('performed') is not True or support.get('result') != 'supported' or support.get('method') not in {'exact_span', 'numeric_equality', 'restatement'}:
            repairs.append(('SUPPORT_CHECK_NORMALIZED', f'{field}: performed / result / method read from the check the engine did'))
        meta = (loaded.get(address) or ({}, None))[0]
        used[sid] = dict(source_id=sid, locator=source.get('url') or source.get('path'), content_ref=address,
                         sha256=meta.get('sha256') or hashlib.sha256(form.encode('utf-8')).hexdigest(),
                         content_sha256=hashlib.sha256(form.encode('utf-8')).hexdigest())
        checked_ids.add(cid)
        claim_sources.setdefault(cid, set()).add(sid)
        record('source_verified')

    def walk(value, field, active=(), prior=False, classification=False, prior_demoted=frozenset(), scope=None, scoped_classes=None, carrier=None):
        if isinstance(value, dict):
            if isinstance(value, InheritedClaim):
                scope, prior, scoped_classes, prior_demoted = value.origin
            if '@ref' in value:
                address = value['@ref']
                if address in active or len(active) >= 16:
                    raise SupportError(field, 'cyclic or overdeep claim reference')
                meta, selected = load(address, field)
                checked = meta.get('prior_source_support')
                if checked:
                    inherited[address] = dict(reference=address, cache=meta['cache'], sha256=meta['sha256'])
                if checked and meta.get('kind') == 'input' and isinstance(meta.get('node'), str) and type(meta.get('visit')) is int:
                    scope = f"{meta['node']}@{meta['visit']}"
                    scoped_classes = meta.get('prior_claim_classifications')
                    carrier = scope
                walk(selected, field, (*active, address), prior or bool(checked), classification,
                     prior_demoted | frozenset(meta.get('prior_demoted') or ()), scope, scoped_classes, carrier)
            else:
                is_claim = 'verification' in value and ('claim_id' in value or value['verification'] == 'source_verified' or
                                               ('id' in value and isinstance(value['verification'], str) and value['verification'] in counts))
                if is_claim:
                    cid = value.get('claim_id', value.get('id'))
                    inputs = value.get('inputs')
                    # Qualified dependencies bind only byte-verified, explicitly referenced inputs; they never fetch by written ID.
                    if scope and isinstance(cid, str) and isinstance(scoped_classes, dict):
                        qualified = f'{scope}/{cid}'
                        labels = {label for label in (*counts, 'ambiguous') if cid in (scoped_classes.get(label) or [])}
                        scoped_labels.setdefault(qualified, set()).update(labels)
                        if labels == {'derived'} and isinstance(inputs, list):
                            scoped_inputs.setdefault(qualified, set()).update(
                                i if re.fullmatch(r'.+@[1-9][0-9]*/[^/]+', i) else f'{scope}/{i}'
                                for i in inputs if isinstance(i, str) and i)
                    if isinstance(cid, str) and value.get('verification') == 'derived' and isinstance(inputs, list):
                        dependencies.setdefault(cid, set()).update(i for i in inputs if isinstance(i, str) and i)
                    try:
                        check(value, field, prior, prior_demoted, scope, scoped_classes)
                        if scope and isinstance(cid, str) and 'ambiguous' in scoped_labels.get(f'{scope}/{cid}', ()):
                            identities.setdefault(f'{scope}/{cid}', set()).add('ambiguous')
                    except SupportError as exc:
                        demote(value.get('claim_id', value.get('id')), field, str(exc), scope)
                    if isinstance(value, InheritedClaim) and prior and carrier and scope and isinstance(cid, str) and cid:
                        carrier_origins.setdefault(f'{carrier}/{cid}', set()).add(f'{scope}/{cid}')
                for key, child in value.items():
                    if is_claim and (key in {'verification', 'support_check'} or (key == 'value' and child == 'source_verified')):
                        continue
                    label_field = classification or 'verif' in key.lower() or key in {'claim', 'claims', 'claim_ledger'}
                    walk(child, f'{field}.{key}', active, prior, label_field, prior_demoted, scope, scoped_classes, carrier)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f'{field}[{i}]', active, prior, classification, prior_demoted, scope, scoped_classes, carrier)
        elif classification and value == 'source_verified':
            repairs.append(('SOURCE_LABEL_UNBOUND', f'{field}: a scalar source_verified label without a claim record'))

    walk(output, 'output', scope=claim_scope)
    # A declared carrier is a dependency alias, not another evidence identity.
    for alias, origins in carrier_origins.items():
        if alias in identities:
            continue
        if len(origins) != 1:
            scoped_labels[alias] = {'ambiguous'}
            continue
        origin = next(iter(origins))
        scoped_labels[alias] = set(identities.get(origin, ()))
        if origin in scoped_inputs:
            scoped_inputs[alias] = set(scoped_inputs[origin])
    result = dict(**counts, claim_ids=sorted(checked_ids), sources=list(used.values()), inherited=list(inherited.values()), verification_scope=SCOPE,
                  retrieval_provenance='model_declared_not_provider_attested')
    result['claim_sources'] = {cid: sorted(sids) for cid, sids in sorted(claim_sources.items())}
    result['claim_classifications'] = {
        label: sorted(cid for cid, labels in classifications.items() if labels == {label}) for label in counts}
    result['claim_classifications']['ambiguous'] = sorted(cid for cid, labels in classifications.items() if len(labels) > 1)
    result['effective_classifications'] = {
        label: sorted(cid for cid, labels in identities.items() if labels == {label}) for label in counts}
    result['effective_classifications']['ambiguous'] = sorted(cid for cid, labels in identities.items()
        if len(labels) > 1 or 'ambiguous' in labels)
    result['effective_counts'] = {label: len(ids) for label, ids in result['effective_classifications'].items()}
    result['unique_claims'] = len(identities)
    result['unidentified_observations'] = len(unidentified)
    result['count_basis'] = 'legacy_id_label_pairs; effective_node_visit_claim_identity; ambiguous_not_verified'

    def uncertainty(cid, active=(), visited=None):
        visited = set() if visited is None else visited
        labels = scoped_labels.get(cid, classifications.get(cid, set()))
        inputs = scoped_inputs.get(cid, dependencies.get(cid, set()))
        reason = ('DEPENDENCY_CYCLE' if cid in active else 'DEPTH_LIMIT' if len(active) >= 16
                  else 'MISSING_CLAIM_ID' if not labels else 'AMBIGUOUS_CLASSIFICATION' if len(labels) != 1 or 'ambiguous' in labels else None)
        if reason:
            return set(), {cid: {reason}}
        if cid in visited:
            return set(), {}
        visited.add(cid)
        if labels == {'unverified'}:
            return {cid}, {}
        if labels == {'source_verified'}:
            return set(), {}
        if not inputs:
            return set(), {cid: {'DERIVED_INPUTS_UNDECLARED'}}
        unverified, unresolved = set(), {}
        for dep in inputs:
            a, b = uncertainty(dep, (*active, cid), visited)
            unverified.update(a)
            for key, reasons in b.items():
                unresolved.setdefault(key, set()).update(reasons)
        return unverified, unresolved

    result['dependency_observations'] = []
    for cid, inputs in sorted(dependencies.items()):
        if not inputs:
            continue
        unverified, unresolved = uncertainty(cid)
        if unverified or unresolved:
            result['dependency_observations'].append(dict(claim_id=cid, declared_inputs=sorted(inputs),
                unverified_inputs=sorted(unverified), unresolved_inputs=sorted(unresolved),
                unresolved_reasons={key: sorted(reasons) for key, reasons in sorted(unresolved.items())}))
    result['dependency_scope'] = 'declared_ids_not_formula_or_semantic_validation'
    if located:   # alpha.98: the passages the engine cut from the originals (claim, source, size, sha256)
        result['located'] = located
    result['labelled'] = len(labelled)   # alpha.99: claims labelled source_verified by this commit
    if demoted:   # alpha.99: claims the engine could not support - counted unverified (engine_core decides the one evidence round)
        result['demoted'] = demoted
    if derived_by_engine:
        result['reclassified_derived'] = derived_by_engine
    if notes is not None:
        by_code = {}
        for code, text in repairs:
            by_code.setdefault(code, []).append(text)
        for code, rows in by_code.items():
            notes.append({"code": code, "text": f"{len(rows)}x: " + "; ".join(rows[:8]) + (" …" if len(rows) > 8 else "") + " (alpha.99)"})
        if derived_by_engine:
            notes.append({"code": "SUPPORT_RECLASSIFIED_DERIVED", "text": f"{len(derived_by_engine)} claim(s) whose value is a conversion of a number in the passage "
                                                                          "are counted derived (alpha.99): " + ", ".join(str(d['claim_id']) for d in derived_by_engine[:12])})
        if demoted:
            notes.append({"code": "SOURCE_SUPPORT_DEMOTED", "text": f"{len(demoted)} claim(s) labelled source_verified could not be supported by captured content "
                                                                    "and are counted unverified (alpha.99): "
                                                                    + "; ".join(f"{d['claim_id']}: {d['reason']}" for d in demoted[:8]) + (" …" if len(demoted) > 8 else "")})
    return result


# alpha.82 (doc 172; production cache/40: 9 of 9 diagnostics were denials, zero statements, an identity and the diagnostic explaining
# itself). A negator must DIRECTLY govern the label; the enumeration must carry no values; both stay clause-level.
_LABEL = r'[\s`*「『"“\'(（]*source_verified'
_NEGATED_LABEL = re.compile(
    r'(?:不主张|不声称|未声称|不(?:能|得|可|应)?(?:标注?|记|写|算)(?:为|成|作)?|而非|而不是|并非|不是|不属于|不等于|不构成|'
    r'不存在(?:任何)?(?:需要)?|(?:(?<=[\s，,、（(:：])|(?<=[A-Za-z]))非|'
    r'未达到?|未取得|未能(?:取得|达到)|达不到|够不上|不支持|无法(?:用于)?支撑|未(?:声明|提交)(?:任何)?|'   # alpha.83 (doc 174 C; production cache/42)
    r'(?:没有|无)(?:任何)?(?:一(?:条|项|个))?(?:论断)?(?:是|为|属于|达到)?|'
    r'(?<![A-Za-z])(?:not|never|no|rather than|instead of)\b|'
    r'(?<![A-Za-z])(?:no|none)\b[^.;。；]{0,40}?\b(?:is|are|was|were))' + _LABEL, re.I)
_SEP = r'[\s`*]*(?:\+|/|、|,|，|\||与|和|或|and|or)[\s`*]*'
_LABEL_ENUMERATION = re.compile(r'source_verified' + _SEP + r'(?:derived' + _SEP + r')?unverified', re.I)   # three labels, or the two ends as alternatives
_ENUMERATION_VALUES = re.compile(r'unverified[\s`*]*(?:[:=：]|为|是)[\s`*]*(\d+)', re.I)
_DENIED_LABEL_ACTION = re.compile(r'(?:未|没有)(?:升级为|(?:登记|注册)(?:为)?(?:逐项|正式的)?)' + _LABEL)
_AMBIGUOUS_DENIAL = re.compile(r'并非|不是|不能说|不代表|不等于|不意味着|是否|如果|假如|除非|若|假设|可能|不确定')
_UNBOUND_LABEL_MENTION = re.compile(
    r'[^。；;]*?(?:出现|提及)的\s*source_verified\s*(?:字样|标签)(?:尚)?未绑定[^。；;，,]+[，,]\s*'
    r'(?:因此|故)?(?:不能|不得|不应)(?:视为|当作)(?:正式的?)?来源(?:验证|核验)')
_NAMED_CLAUSE_COUNT = re.compile(
    r'source_verified[\s`*]*(?:计数|数量|总数|论断(?:数)?|声明(?:数)?)[\s`*]*(?:[:=：]|为|是)[\s`*]*'
    r'([0-9]+|零)(?![\dA-Za-z_.%％点十百千万亿兆零一二三四五六七八九两])'
    r'(?![\s`*]*(?:[-–—~～至到]+[\s`*]*[0-9零一二三四五六七八九十]|[,，]\s*[0-9]))', re.I)
_CLAUSE_COUNT = re.compile(r'source_verified[\s`*]*(?:[:=：|]|为|是|共|计)[\s`*]*(\d+|零)|'
                           r'(?<![A-Za-z0-9_.\-非])(\d+|零)[\s`*]*(?:条|项|个|次|处|笔)?[\s`*]*(?:(?:真正|经原文核验)的\s*)?(?:为|是|属于)?[\s`*]*source_verified|'
                           r'source_verified[\s`*]+(\d+)(?![\d.:\-])', re.I)   # alpha.91 (doc 206 #2; production cache/63): "source_verified 0 / derived 41"   # alpha.83: 次 / 处 / 笔; alpha.84: "C1" is an ID, not the count 1

_EXACT_NUM = r'(?:[0-9]+|[二三四五六七八九]?十[一二三四五六七八九]?|[零〇一二两三四五六七八九])'
_NUM_CHARS = r'\d零〇一二两三四五六七八九十百千万亿兆点'
_NATURAL_COUNT = re.compile(
    r'(?<![A-Za-z_.%\-非第于至到~～' + _NUM_CHARS + r'])(' + _EXACT_NUM + r')'
    r'[\s`*]*(?:条|项|个)(?:论断|声明)?[\s`*]*(?:能达到|达到|属于|是|为)?[\s`*]*source_verified|'
    r'source_verified[\s`*]*(?:计数|数量|总数|论断数|声明数)[\s`*]*(?:[:=：]|为|是)[\s`*]*('
    + _EXACT_NUM + r')(?![' + _NUM_CHARS + r'A-Za-z_.%％])'
    r'(?![\s`*]*(?:[-–—~～至到]+[\s`*]*[' + _NUM_CHARS + r']|[,，]\s*[' + _NUM_CHARS + r']))', re.I)


def _count_value(text):
    if text.isascii() and text.isdigit():
        return int(text)
    digits = dict(zip('零〇一二两三四五六七八九', (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
    tens, sep, ones = text.partition('十')
    return (digits[tens] if tens else 1) * 10 + (digits[ones] if ones else 0) if sep else digits[text]


def _clause_count(clause):
    """The source_verified count a clause states, in its natural forms; None when it states none."""
    named = _NAMED_CLAUSE_COUNT.search(clause)
    if named:
        return 0 if named[1] == '零' else int(named[1])
    if _LABEL_ENUMERATION.search(clause):
        found = _ENUMERATION_VALUES.search(clause)   # source_verified / derived / unverified = 0 / 18 / 61: the first value is ours
        return int(found[1]) if found else None
    found = _CLAUSE_COUNT.search(clause)
    value = (found[1] or found[2] or found[3]) if found else None
    if value is not None:
        return 0 if value == '零' else int(value)
    natural = _NATURAL_COUNT.search(clause)
    return _count_value(natural[1] or natural[2]) if natural else None


def _future_source_support(clause):
    """A capture instruction whose purpose is future support, not a present-tense assertion."""
    if clause.count('source_verified') != 1:
        return False
    if re.search(r'已经|已(?:抓取|保存|捕获|补充|获取|具备|是|为)|(?:抓取|保存|捕获|补充|获取)了|\b(?:already|captured|saved|verified|has|have)\b', clause, re.I):
        return False
    return bool(re.search(
        r'(?:抓取|保存|捕获|补充|获取)[^。；;]{0,24}(?:来源原文|原文|原始响应)[，,\s]*(?:以让|让|以便|再将)[^。；;]{0,16}'
        r'(?:具备|标为|标注为)\s*source_verified(?:\s*(?:支持|支撑))?[。.!]?\s*$|'
        r'^Capture the original source before marking (?:a|the) claim as source_verified[.!]?\s*$', clause, re.I))


def _nonassertive_label_clause(text):
    """Narrow definitions/denials, never a blanket exception for a mixed paragraph."""
    clause = text.strip().replace('`', '').strip('* ')
    if _future_source_support(clause):
        return True
    if (re.fullmatch(r'(?:验收标准|Acceptance criterion)\s*[:：]\s*source_verified\s*>\s*0(?:\s*且[^。；;]+)?[.!]?', clause, re.I)
            and not re.search(r'已(?:达成|满足|通过|完成)|already|achieved|passed|fulfilled', clause, re.I)):
        return True
    if clause.count('source_verified') == 1 and re.search(r'(?:^|[，,])\s*把不确定的标为\s*source_verified\s*才是真正的失败模式[。.!]?$', clause):
        return True
    if clause.count('source_verified') == 1 and re.fullmatch(r'[^。；;]*(?:出现|提及)\s*source_verified\s*字样(?:却|但)未在同行注明(?:被核验的\s*)?claim_id', clause):
        return True
    if clause.count('source_verified') == 1 and re.fullmatch(r'[^。；;]*比给出几条看起来可信的\s*source_verified\s*更重要(?:——后者[^。；;]*)?', clause):
        return True
    if ('SOURCE_VERIFICATION_UNBOUND' in clause and re.search(r'字样|标签绑定|diagnostic', clause, re.I)
            and not re.search(r'(?:已|确实|均为|都是)\s*source_verified', clause)):
        return True
    if _LABEL_ENUMERATION.search(clause) and clause.count('source_verified') == 1 and not _ENUMERATION_VALUES.search(clause):
        return True   # alpha.82: the three labels as a formula / enumeration, no values attached
    negated = _NEGATED_LABEL.search(clause)
    if clause.count('source_verified') == 1 and negated and not re.search(r'source_verified\s*的\s*只有', clause):
        return not re.search(r'(?:并非|不是|不能说|不代表)[^，,。；;]*$', clause[:negated.start()])
    if clause.count('source_verified') == 1:
        # A denied action or an explicitly unbound label mention is not a checked claim.
        denied = _DENIED_LABEL_ACTION.search(clause)
        if denied and not _AMBIGUOUS_DENIAL.search(clause[:denied.start()]):
            return True
        if _UNBOUND_LABEL_MENTION.fullmatch(clause) and not _AMBIGUOUS_DENIAL.search(clause.split('source_verified', 1)[0]):
            return True
    if clause.count('source_verified') == 1 and re.search(
            r'(?:会以|将按|必须按|以)\s*source_verified\s*/\s*derived\s*/\s*unverified\s*三态(?:如实)?标注[。.!]?$', clause):
        return True
    if clause.count('source_verified') == 1 and re.search(
            r'(?:最终台账中|后续记录中)\s*source_verified\s*与\s*unverified\s*的比例.*(?:必须如实|不得).*$', clause):
        return True
    return bool(re.fullmatch(
        r'(?:不存在需要\s*source_verified\s*的外部数据|禁止声称\s*source_verified|'
        r'The source_verified label does not certify retrieval)[。.!]?', clause, re.I))


def _demotion_disclosure(clause, proof, upstream):
    """A historical label followed by its checked demotion is not a positive claim."""
    clause = re.sub(r'[`*]', '', clause).strip()
    if clause.count('source_verified') != 1:
        return False
    clause = re.sub(r'^(?:\d+\.\s*)?[^：:。；;]*被降级[^：:。；;]*[：:]\s*', '', clause)
    match = re.fullmatch(r'([A-Za-z0-9_.-]+(?:\s*[、,，/]\s*[A-Za-z0-9_.-]+)*)\s*'
                         r'(?:原标注|原标为|曾标注为?)\s*source_verified[^。；;]*?'
                         r'(?:计为|降级为)\s*unverified', clause)
    if not match:
        return False
    ids = re.split(r'\s*[、,，/]\s*', match[1])
    demoted = {d.get('claim_id') for row in [proof, *upstream] for d in row.get('demoted') or []}
    checked = {cid for row in [proof, *upstream] for cid in row.get('claim_ids') or []}
    return bool(ids) and set(ids) <= demoted and not set(ids) & checked


def _only_owner(stated, upstream):
    """alpha.84 (doc 176 A1; isolated run doc 175 §4.2: "28 条 source_verified" restated downstream without Node@visit - true, unscoped):
    a positive count held by exactly ONE upstream ledger names it. A module node forwards the ledger of its sub node - the same
    claim_ids are one ledger; two different ledgers with the same count, or no holder, stay unbound."""
    holders = [row for row in upstream if row.get('source_verified') == stated]
    ledgers = {tuple(row.get('claim_ids') or ()) for row in holders}
    return bool(stated) and bool(holders) and (len(holders) == 1 or (len(ledgers) == 1 and () not in ledgers))


def _aliases(node):
    """alpha.112 (doc 276; production cache/73): the names an executor writes for a node - the full id
    ('DelegateAnalysis/analysis.FetchData'), the id after its last '/' ('analysis.FetchData') and the bare name after its last '.'
    ('FetchData')."""
    node = str(node or '')
    tail = node.rsplit('/', 1)[-1]
    return {name for name in (node, tail, tail.rsplit('.', 1)[-1]) if name}


def _module_free_aliases(node):
    """docs/05SoulRun 87 (run 7: 'Research2/QualityResearch@1: source_verified: labelled=10, checked=9' written exactly as the
    evidence contract asks, judged unbound): the node path with each segment's module prefix removed and its tails after a '/' -
    'PipelineEntry/pipeline.Research2/research.QualityResearch' -> 'PipelineEntry/Research2/QualityResearch', 'Research2/QualityResearch'.
    Like every alias, one names a node only when exactly one known node has it."""
    parts = [part.rsplit('.', 1)[-1] for part in str(node or '').split('/')]
    return {'/'.join(parts[i:]) for i in range(len(parts) - 1) if all(parts[i:])}


_DUAL_COUNT_FORMS = ("the full node id, the id after its last '/', the bare name after its last '.', or the path with each segment's module "
                     "prefix removed (a short form only when exactly one node has it)")


# alpha.112 (doc 276): one written address '<node>@<visit>/<ID>', taken whole - the node part may not continue a longer ASCII token on
# its left (no tail of 'Other/sub.FetchData'); the visit is 1-6 ASCII digits without a leading zero; the ID may not continue into an
# ID character, '/', '@' or '.<char>' on its right - so a longer written ID is never cut back to a shorter checked one
# ('FD-C12/FD-C13' is not 'FD-C1'; review N1).
_ADDRESSED_ID = re.compile(r'(?<![A-Za-z0-9_./@\-])([A-Za-z0-9_\-]+(?:[./][A-Za-z0-9_\-]+)*)@([1-9][0-9]{0,5})/([A-Za-z0-9_\-]+)'
                           r'(?![A-Za-z0-9_\-/@]|\.[A-Za-z0-9_])')


def effective_view(row):
    """Legacy proofs stay readable; new label authority excludes ambiguous bare IDs."""
    if 'effective_counts' not in row:
        return row
    classes = row['effective_classifications']
    excluded = {cid.rsplit('/', 1)[-1] for label, ids in classes.items() if label != 'source_verified' for cid in ids}
    verified = {cid.rsplit('/', 1)[-1] for cid in classes['source_verified']} - excluded
    return dict(row, **row['effective_counts'], claim_ids=sorted(verified))


def public_diagnostics(payload, proof, *, upstream=(), visit=None, nodes=()):
    """Observe explicit labels, not arbitrary natural-language truth. Never rewrite ACP."""
    proof, upstream = effective_view(proof), [effective_view(row) for row in upstream]
    texts = {k: payload.get(k, '') for k in ('user_summary', 'explain')}
    texts.update({f'user_messages[{i}]': s for i, s in enumerate(payload.get('user_messages', []))})
    texts['semantics.final_answer'] = (payload.get('semantics') or {}).get('final_answer', '')
    issues = []
    ids = proof.get('claim_ids', [])
    owners = {}
    for row in upstream:
        for cid in row.get('claim_ids', []):
            owners.setdefault(cid, set()).add(f"{row['node']}@{row['visit']}")
    # alpha.112 (doc 276): a checked ID written with its holder's address, '<node>@<visit>/<ID>', names it too. The written node is
    # resolved against every node the run knows (the catalog the engine passes, this node, the upstream holders): an exact node id
    # names that node; otherwise an alias (id after the last '/', bare name after the last '.') names a node only when exactly one
    # known node has it. The ID must be held by that node at that visit - this node's own IDs only when the visit is given.
    current = str(payload.get('node') or '')
    known = {str(n) for n in nodes or () if n} | {str(r.get('node')) for r in upstream if r.get('node')} | ({current} if current else set())
    visit = visit if isinstance(visit, int) and not isinstance(visit, bool) else None   # the engine passes the occurrence's int visit
    alias_map = {}
    for name in known:
        for alias in _aliases(name) | _module_free_aliases(name):   # docs/05SoulRun 87: + the module-free path
            alias_map.setdefault(alias, set()).add(name)
    held = {}
    for row in upstream:
        held.setdefault((str(row.get('node')), row.get('visit')), set()).update(str(c) for c in row.get('claim_ids') or [])
    for row in [proof, *upstream]:
        for identity in (row.get('effective_classifications') or {}).get('source_verified', []):
            scope, sep, cid = identity.rpartition('/')
            node, at, v = scope.rpartition('@')
            if sep and at and v.isdigit() and node in known:
                held.setdefault((node, int(v)), set()).add(cid)
    if current and visit is not None:
        held.setdefault((current, visit), set()).update(str(c) for c in ids or [])

    def holder(written):
        if written in known:
            return written
        found = alias_map.get(written, ())
        return next(iter(found)) if len(found) == 1 else None

    def addressed(line):
        return any((node := holder(written)) is not None and cid in held.get((node, int(v)), ())
                   for written, v, cid in _ADDRESSED_ID.findall(line))

    def named(line, token):
        return re.search(r'(?<![\w/@-])' + re.escape(token) + r'(?![\w/@-])', line)

    def slash_ids(clause):
        # Resolve roles from accepted proofs, never from S/C prefixes. Legacy proofs bind a
        # source and claim to one holder, but do not certify every assertion in a table row.
        pattern = r'(?<![\w/@.\-])([A-Za-z][A-Za-z0-9_\-]*(?:/[A-Za-z][A-Za-z0-9_\-]*)+)(?![\w/@.\-])'
        rows = [proof, *upstream]
        source_ids = {s.get('source_id') for r in rows for s in r.get('sources') or []}
        all_claims = set(ids or []) | set(owners)
        groups = [g.split('/') for g in re.findall(pattern, clause)
                  if any(i in source_ids or i in all_claims or re.search(r'\d$', i) for i in g.split('/'))]
        if not groups:
            return None
        for group in groups:
            if any(i in source_ids and i in all_claims for i in group):
                return False
            if group[0] in source_ids:
                source, *claims = group
                holders = [r for r in rows if source in {s.get('source_id') for s in r.get('sources') or []}
                           and all(c in (r.get('claim_ids') or []) for c in claims)]
                if len(holders) != 1 or any(c in source_ids for c in claims):
                    return False
                mapping = holders[0].get('claim_sources')
                if mapping is not None and any(source not in mapping.get(c, []) for c in claims):
                    return False
            elif not all(cid in ids or len(owners.get(cid, ())) == 1 for cid in group):
                return False
        return True

    def source_scope(clause):
        clause = clause.replace('`', '').replace('*', '').strip()
        match = re.fullmatch(r'[^。；;]*?(?:这(?:正)?是)?只有基于\s*([A-Za-z][A-Za-z0-9_-]*)\s*的论断能达到\s*source_verified\s*的原因', clause)
        if clause.count('source_verified') != 1:
            return False
        if not match:
            return False
        checked = [r for r in [proof, *upstream] if r.get('source_verified')]
        return bool(checked) and all(r.get('sources') and {s.get('source_id') for s in r['sources']} == {match[1]} for r in checked)

    dual_misses = []   # docs/05SoulRun 87: why a dual count did not bind, said in the diagnostic instead of the claim_id hint

    def dual_count(clause):
        # Accept only a complete, explicitly typed pair, never a blanket line exemption.
        clause = clause.replace('`', '').replace('*', '').strip()
        clause = re.sub(r'^(?:[-+]|\d{1,3}[.)])\s+', '', clause)   # docs/05SoulRun 87: a leading list marker is no part of the count
        labelled = r'(?:工具标注|模型标注|labelled)'
        checked = r'(?:引擎复核|引擎核验|checked)'
        if not re.search(r'source_verified\s*[:：]?\s*' + labelled, clause, re.I):
            return None
        match = re.fullmatch(r'(?:(?P<node>[A-Za-z0-9_./-]+)@(?P<visit>[1-9][0-9]{0,5})\s*[:：]\s*)?'
                             r'source_verified\s*[:：]?\s*' + labelled + r'\s*[:=：]?\s*(?P<labelled>[0-9]{1,12})\s*[/,，]\s*'
                             + checked + r'\s*[:=：]?\s*(?P<checked>[0-9]{1,12})', clause, re.I)
        if not match:
            return False
        rows = [dict(proof, node=current, visit=visit), *upstream]
        if match['node']:
            node = holder(match['node'])
            if node is None:
                dual_misses.append(f"node name {match['node']!r} is not recognised - write {_DUAL_COUNT_FORMS}")
                return False
            rows = [r for r in rows if r.get('node') == node and r.get('visit') == int(match['visit'])]
        rows = [r for r in rows if type(r.get('labelled')) is int and type(r.get('source_verified')) is int
                and r['labelled'] == int(match['labelled']) and r['source_verified'] == int(match['checked'])]
        if len(rows) != 1:
            dual_misses.append(f"labelled={match['labelled']}, checked={match['checked']} are not the two counts of exactly one machine proof"
                               + (f" of {match['node']}@{match['visit']}" if match['node'] else " (name its <Node>@<visit>)"))
        return len(rows) == 1

    for field, text in texts.items():
        if not isinstance(text, str):
            continue
        fenced = False
        lines = []
        dual_misses.clear()
        claim_lines = []   # docs/05SoulRun 87: lines that failed on something other than a dual count
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(('```', '~~~')):
                fenced = not fenced
                continue
            if fenced or 'source_verified' not in line:
                continue
            clauses = []
            for sentence in re.split(r'[。；;]', line):
                # Keep a verified historical-to-checked demotion together across its contrast.
                parts = [sentence] if _demotion_disclosure(sentence, proof, upstream) else re.split(
                    r'[，,]\s*(?:但是|但|不过|然而|but\b|however\b)', sentence, flags=re.I)
                clauses.extend(s for s in parts if 'source_verified' in s)

            def fine(clause):   # alpha.82: every label-bearing clause must be a non-assertion or a count the machine holds
                dual = dual_count(clause)
                if dual is not None:
                    return dual
                if _nonassertive_label_clause(clause) or _demotion_disclosure(clause, proof, upstream):
                    return True
                stated = _clause_count(clause)
                if stated is not None:
                    return (stated == proof['source_verified'] or any(
                        named(clause, f"{row['node']}@{row['visit']}") and stated == row['source_verified'] for row in upstream)
                        or _only_owner(stated, upstream))
                grouped = slash_ids(clause)
                if grouped is False:
                    return False
                if clause.count('source_verified') == 1 and re.search(
                        r'(?:\bUse\s+|必须按\s*)source_verified\s*/\s*derived\s*/\s*unverified\s+(?:to label evidence\.|三态(?:如实)?标注[，。])', clause, re.I):
                    return True
                return (grouped is True or source_scope(clause) or any(named(clause, cid) for cid in ids)
                        or any((len(scopes) == 1 and named(clause, cid)) or any(named(clause, scope + '/' + cid) for scope in scopes)
                               for cid, scopes in owners.items())
                        or addressed(clause))

            misses = len(dual_misses)
            if clauses and all(fine(s) for s in clauses):
                continue
            lines.append(n)
            if len(dual_misses) == misses:
                claim_lines.append(n)
        if lines:
            choices = ', '.join(ids[:12]) or '(none)'
            hint = 'use the exact atomic ID, not its pre-split parent.'
            if dual_misses:   # docs/05SoulRun 87: the claim_id hint misleads for a dual count; say which name or counts did not bind
                hint = 'dual count: ' + '; '.join(dict.fromkeys(dual_misses)) + ('; otherwise ' + hint if claim_lines else '.')
            issues.append(dict(code='SOURCE_VERIFICATION_UNBOUND', text=f'{field} lines {lines}: source_verified has no same-line checked claim_id; label binding unverified, not a semantic falsehood verdict. Checked IDs (first 12): {choices}; {hint}'))
    return issues
