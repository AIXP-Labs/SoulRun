"""Declared review inputs and candidate bindings, not a filesystem sandbox."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re

MAX_BYTES = 16 * 1024 * 1024
MAX_FILES = 256


def fail(code, text, **fields):
    from .engine_core import EngineError
    raise EngineError(code, text, **fields)


def same_path(left,right):
    """Lexical aliases on this OS, confirmed by file identity; never swallow links."""
    try:
        paths=[Path(left),Path(right)]
        if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for path in paths for p in (path,*path.parents)):
            return False
        keys=[os.path.normcase(os.path.abspath(p)) for p in paths]
        return keys[0]==keys[1] and os.path.samefile(*paths)
    except (OSError,TypeError,ValueError):
        return False


def candidate_path(raw,observed,store,program,index):
    path=Path(raw)
    if path.is_absolute():return path
    # The committed machine observation fixes the base, not this process's CWD.
    if observed and Path(observed).is_absolute():return Path(observed)
    fail('BLIND_REVIEW_INPUT_SCOPE_INVALID','Relative candidate has no absolute commit-time observation; supply an absolute path.',
        field='blind_inputs.candidates',example=dict(declared=raw,observed=observed))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def content_identity(binding):
    """Snapshot content coordinates, separate from the unchanged authority digest."""
    invalid = lambda: fail('BLIND_REVIEW_CONTENT_IDENTITY_INVALID', 'Review content manifest is absent, ambiguous or malformed.')
    items = binding.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_FILES:
        invalid()
    groups = {}
    for row in items:
        if not isinstance(row, dict) or row.get('kind') not in ('candidate', 'standard'):
            invalid()
        original, source = row.get('original_root'), row.get('source')
        if not all(isinstance(v, str) and v and not any(ord(c) < 32 for c in v) for v in (original, source)):
            invalid()
        single = original.replace('\\', '/').rstrip('/') == source.replace('\\', '/').rstrip('/')
        # A POSIX backslash is a filename byte, not a Windows path separator.
        original_name = original if original.startswith('/') else original.replace('\\', '/')
        relative = original_name.rsplit('/', 1)[-1] if single else row.get('relative')
        if not isinstance(relative, str) or not relative or len(relative) > 2048 or '\\' in relative or ':' in relative \
                or any(ord(c) < 32 for c in relative) or any(p in ('', '.', '..') for p in relative.split('/')) \
                or type(row.get('bytes')) is not int or not 0 <= row['bytes'] <= MAX_BYTES \
                or not isinstance(row.get('sha256'), str) or re.fullmatch('[a-f0-9]{64}', row['sha256']) is None:
            invalid()
        key = row['kind'], original
        group = groups.setdefault(key, dict(kind='file' if single else 'directory', files=[]))
        if group['kind'] != ('file' if single else 'directory') or any(r['relative'] == relative for r in group['files']):
            invalid()
        group['files'].append(dict(relative=relative, bytes=row['bytes'], sha256=row['sha256']))
    result = dict(schema_version=1, algorithm='review_content_manifest_v1')
    for kind, name in (('candidate', 'candidates'), ('standard', 'standards')):
        trees = [dict(kind=g['kind'], files=sorted(g['files'], key=lambda r:r['relative']))
                 for (k, _), g in groups.items() if k == kind]
        if not trees:
            invalid()
        trees.sort(key=lambda g:json.dumps(g, sort_keys=True, separators=(',', ':')))
        result[name] = dict(groups=trees, sha256=digest(trees))
    context = binding.get('context_inputs')
    if context is not None:
        if not isinstance(context, dict) or any(not isinstance(row, dict) or not isinstance(row.get('value'), str)
                or not 0 < len(row['value']) <= 64 for row in context.values()):
            invalid()
        context = {name:row['value'] for name, row in context.items()}
    result['context_values'] = context
    return result


def declaration(row):
    value = row.get('blind_inputs')
    if value is None:
        return None
    if row.get('isolation') != 'blind_review' or not isinstance(value, dict) \
            or not {'candidates','standards'} <= set(value) or set(value) - {'candidates','standards','context'}:
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'blind_inputs requires candidates and standards on a blind_review root.')
    if not isinstance(value['candidates'], list) or not 1 <= len(value['candidates']) <= 16 \
            or not isinstance(value['standards'], list) or not 1 <= len(value['standards']) <= 16:
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Declare 1..16 candidate artifact selectors and standard files.')
    for item in value['candidates']:
        if not isinstance(item, dict) or set(item) != {'node','artifact'} or not isinstance(item['node'], str) \
                or not item['node'] or type(item['artifact']) is not int or item['artifact'] < 0:
            fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidates require committed node and nonnegative artifact ordinal.')
    if any(not isinstance(p, str) or not p or Path(p).root or ':' in p or '..' in p.replace('\\','/').split('/')
           for p in value['standards']) or len(set(value['standards'])) != len(value['standards']):
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Standards are distinct program-relative files without traversal.')
    if 'context' in value:
        from . import review_context
        review_context.declaration(value['context'])
    return value


def capture_context(store, index, selectors):
    from . import review_context
    return review_context.capture(store, index, selectors)


def root_declaration(program, entry):
    from . import dispatch_budget, engine_core as ec
    rows, _ = dispatch_budget.requirements(program)
    return next((r for r in rows if r['file'] == (entry.get('doc') or program.entry_file)
                 and r['node'] == ec._bare(entry) and r['isolation'] == 'blind_review'), None)


def _bytes(path):
    path = Path(path).absolute()
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (path, *path.parents)):
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Review inputs cannot traverse links or junctions.')
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Review file is absent or exceeds the bounded input size.')
    data = path.read_bytes()
    return data, dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def _tree(path):
    path = Path(path).absolute()
    if path.is_file():
        data, meta = _bytes(path)
        return [('content', path, data, meta)]
    if not path.is_dir() or path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidate must be an existing regular file or directory.')
    rows = []
    # Bound traversal before recursive descent; do not follow junctions to enumerate their contents.
    pending = [path]
    traversed = 0
    while pending:
        parent = pending.pop()
        _bytes_check = any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (parent, *parent.parents))
        traversed += 1
        if _bytes_check or traversed > MAX_FILES:
            fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidate traversal is linked or exceeds the bounded directory count.')
        for p in sorted(parent.iterdir()):
            if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
                fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidate directory contains a link or junction.')
            if p.is_dir():
                pending.append(p)
                if len(pending) + len(rows) > MAX_FILES:
                    fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidate exceeds the bounded file count.')
            else:
                data, meta = _bytes(p)
                rows.append((p.relative_to(path).as_posix(), p, data, meta))
                if len(rows) > MAX_FILES or sum(r[3]['bytes'] for r in rows) > MAX_BYTES:
                    fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidate exceeds the bounded file/byte count.')
    if not rows:
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Empty candidate directories are not review evidence.')
    return sorted(rows, key=lambda r: r[0])


def directory_manifest(path):
    """Bounded commit-time observation, never a new ordinary-artifact gate."""
    from .engine_core import EngineError
    try:
        members = [dict(path=rel, **meta) for rel, _, _, meta in _tree(path)]
        return dict(status='VERIFIED', members=members, sha256=digest(members))
    except (OSError, ValueError) as exc:
        return dict(status='EXISTENCE_ONLY', reason=type(exc).__name__)
    except EngineError as exc:
        return dict(status='EXISTENCE_ONLY', reason=exc.code)


def bind(store, index, program, entry, visit):
    from . import engine_core as ec
    row = root_declaration(program, entry)
    if row is None:
        return None
    spec = declaration(row)
    if spec is None:
        fail('BLIND_REVIEW_INPUT_SCOPE_UNDECLARED', 'Declare blind_inputs before executing an independent review.')
    root = dict(node=entry['name'], visit=visit)
    name = '_blind.' + digest(root)[:24] + '.json'
    path = store.cache_dir/name
    if path.exists():
        binding = store.read_json(path)
        if 'context' in spec and binding.get('context_declaration_sha256') != digest(spec['context']):
            fail('BLIND_REVIEW_CONTEXT_CHANGED', 'Existing review cannot be rebound to a new run-fact declaration.')
        verify(store, binding)
        return dict(path=name, sha256=digest(binding), candidate_digest=binding['candidate_digest'])
    context = capture_context(store, index, spec['context']) if 'context' in spec else None
    caches = ec._prev_business_caches(store, index)
    sources, provenance = [], []
    for ordinal,selector in enumerate(spec['candidates']):
        field=f'blind_inputs.candidates[{ordinal}]'
        cache = next((c for c in reversed(caches) if c['node'] == selector['node']), None)
        if cache is None:
            fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidate source is not a committed occurrence.',field=field,example=selector)
        payload = ec._latest_payload(cache)
        try:
            art = payload['evidence']['artifacts'][selector['artifact']]
            candidate = Path(art['path'])
            machine = (cache.get('continuations') or [cache])[-1].get('machine') or {}
            observed = (machine.get('artifacts') or [])[selector['artifact']]
            candidate=candidate_path(art['path'],observed.get('path'),store,program,index)
            if not same_path(candidate,observed.get('path')):
                fail('BLIND_REVIEW_INPUT_SCOPE_INVALID','Declared candidate and observed artifact are not the same unlinked location.',
                    field=field,expected='the committed artifact identity',example=dict(selector=selector,declared=art['path'],observed=observed.get('path')))
            if art.get('verified_by') != 'engine':
                if art.get('kind') != 'directory' or not candidate.is_dir():
                    raise ValueError('Unverified artifact')
        except (IndexError, KeyError, TypeError, ValueError):
            fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Candidate selector requires a machine-verified artifact.',field=field,example=selector)
        manifest = observed.get('directory_manifest') or {}
        committed_members = manifest.get('status') == 'VERIFIED'
        if committed_members and (not same_path(candidate,observed.get('path'))
                or manifest.get('sha256') != digest(manifest.get('members'))):
            fail('BLIND_REVIEW_CANDIDATE_CHANGED', 'Directory commit proof is invalid.',field=field,example=selector)
        try:
            files = _tree(candidate)
        except (OSError, ValueError) as exc:
            fail('BLIND_REVIEW_CANDIDATE_CHANGED' if committed_members else 'BLIND_REVIEW_INPUT_SCOPE_INVALID',
                 f'Candidate is unavailable: {type(exc).__name__}.')
        except ec.EngineError:
            if committed_members:
                fail('BLIND_REVIEW_CANDIDATE_CHANGED', 'Directory changed or became unreadable since commit.')
            raise
        if committed_members and [dict(path=rel, **meta) for rel, _, _, meta in files] != manifest['members']:
            fail('BLIND_REVIEW_CANDIDATE_CHANGED', 'Directory members changed since their source commit.')
        if candidate.is_file() and files[0][3]['sha256'] != art.get('sha256'):
            fail('BLIND_REVIEW_CANDIDATE_CHANGED', 'Candidate changed since its source commit.')
        sources.append(('candidate', candidate, files))
        provenance.append(dict(source=str(candidate), source_kind='directory' if candidate.is_dir() else 'file',
            commit_verification='directory_members' if committed_members else 'existence_only' if candidate.is_dir() else 'file_sha256',
            snapshot_basis='review_ticket_time', **({'commit_members_verified': committed_members} if candidate.is_dir() else {})))
    for rel in spec['standards']:
        standard = program.dir/rel
        if not standard.resolve().is_relative_to(program.dir.resolve()) or not standard.is_file():
            fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Standard file must be inside the declared program.')
        sources.append(('standard', standard, _tree(standard)))
    items = []
    for number, (kind, original, files) in enumerate(sources):
        for rel, source, data, meta in files:
            target = store.cache_dir/'_work'/'_blind'/digest(root)[:24]/str(number)/rel
            if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (target, *target.parents)):
                fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Snapshot destination traverses a link or junction.')
            from . import write_observation
            write_observation.writing(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != data:
                fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Existing review snapshot cannot be overwritten.')
            if not target.exists():
                target.write_bytes(data)
            write_observation.writing(target,'VERIFIED',receipt=meta['sha256'])
            items.append(dict(kind=kind, source=str(source), original_root=str(original), relative=rel,
                snapshot=target.relative_to(store.cache_dir).as_posix(), **meta))
    if len(items) > MAX_FILES or sum(r['bytes'] for r in items) > MAX_BYTES:
        fail('BLIND_REVIEW_INPUT_SCOPE_INVALID', 'Combined review inputs exceed the bounded size.')
    binding = dict(schema_version=1, root=root, items=items,
                   candidate_digest=digest([r for r in items if r['kind'] == 'candidate']),
                   candidate_provenance=provenance,
                   isolation='engine_api_inputs_not_filesystem_sandbox')
    if context is not None:
        from . import review_context
        binding.update(context_inputs=context, context_declaration_sha256=digest(spec['context']),
                       context_run=review_context.run_identity(store,index))
    store.write_json_once(path, binding)
    verify(store, binding)
    return dict(path=name, sha256=digest(binding), candidate_digest=binding['candidate_digest'])


def verify_evidence(store, binding):
    from . import review_context
    review_context.verify(store, binding)
    for item in binding['items']:
        snapshot = store.cache_dir/item['snapshot']
        if not snapshot.resolve().is_relative_to((store.cache_dir/'_work/_blind').resolve()):
            fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Review snapshot escaped its bound directory.')
        try:
            _, meta = _bytes(snapshot)
        except (OSError, ValueError):
            fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Review snapshot is missing or unreadable.')
        if any(meta[k] != item[k] for k in ('sha256','bytes')):
            fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Review snapshot changed; do not reconstruct review history.')


def verify(store, binding):
    verify_evidence(store, binding)
    for item in binding['items']:
        try:
            _, meta = _bytes(item['source'])
        except (OSError, ValueError) as exc:
            fail('BLIND_REVIEW_CANDIDATE_CHANGED', f'Review input is unavailable: {type(exc).__name__}.')
        if any(meta[k] != item[k] for k in ('sha256','bytes')):
            fail('BLIND_REVIEW_CANDIDATE_CHANGED', 'Bound candidate or standard changed; old review cannot accept the new candidate.')
    for root in {r['original_root'] for r in binding['items'] if r['kind'] == 'candidate'}:
        expected = {r['relative'] for r in binding['items'] if r['original_root'] == root}
        if {r[0] for r in _tree(root)} != expected:
            fail('BLIND_REVIEW_CANDIDATE_CHANGED', 'Candidate file set changed; a new independent review is required.')


def active(store, index):
    from . import engine_core as ec
    entry = ec._catalog_entry(index, index['current']['name'])
    _, dispatch = ec._self_dispatch(index, entry, index['current']['visit']) if entry else (None, None)
    ref = (dispatch or {}).get('review_binding')
    if not ref:
        return None
    return load(store, ref)


def _binding_path(store, ref):
    if not isinstance(ref.get('path'), str) or Path(ref['path']).name != ref['path'] or not ref['path'].startswith('_blind.'):
        fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Review binding path is invalid.')
    path = store.cache_dir/ref['path']
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Review binding cannot be a link or junction.')
    return path


def _binding(store, ref, path):
    # Validate the accepted digest before trusting any paths in this file.
    data, _ = _bytes(path)
    binding = json.loads(data)
    if digest(binding) != ref.get('sha256') or binding['candidate_digest'] != ref.get('candidate_digest') \
            or not isinstance(binding.get('items'), list) or not 1 <= len(binding['items']) <= MAX_FILES:
        fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Machine review binding changed.')
    return binding


def load(store, ref):
    binding = _binding(store, ref, _binding_path(store, ref))
    verify(store, binding)
    return binding


def source_state(binding):
    from .engine_core import EngineError
    changes = []
    roots = dict.fromkeys((r['kind'], r['original_root']) for r in binding['items'])
    for kind, root in roots:
        expected = {r['relative']: {k:r[k] for k in ('sha256','bytes')} for r in binding['items']
                    if r['kind'] == kind and r['original_root'] == root}
        try:
            current = {r[0]: r[3] for r in _tree(root)}
        except (EngineError, OSError, ValueError) as exc:
            changes.append(dict(kind=kind, root=root, source_status='UNAVAILABLE', reason=getattr(exc, 'code', type(exc).__name__)))
            continue
        added, removed = sorted(current.keys()-expected.keys()), sorted(expected.keys()-current.keys())
        changed = [dict(relative=k, **current[k]) for k in sorted(current.keys() & expected.keys()) if current[k] != expected[k]]
        if added or removed or changed:
            changes.append(dict(kind=kind, root=root, source_status='CHANGED', current_digest=digest(current),
                added=[dict(relative=k, **current[k]) for k in added[:32]], removed=removed[:32], changed=changed[:32],
                counts=dict(added=len(added), removed=len(removed), changed=len(changed))))
    return dict(status='CHANGED_AFTER_REVIEW' if changes else 'VERIFIED', source_changes=changes)


def observe(store, ref, root=None):
    from .engine_core import EngineError
    path = _binding_path(store, ref)
    result = dict(copy.deepcopy(ref), root=copy.deepcopy(root), status='EVIDENCE_CHANGED')
    try:
        binding = _binding(store, ref, path)
        result['root'] = copy.deepcopy(binding['root'])
        verify_evidence(store, binding)
    except (EngineError, OSError, ValueError, KeyError, TypeError) as exc:
        result['evidence_error'] = getattr(exc, 'code', type(exc).__name__)
        return result
    result.update(source_state(binding))
    try:
        result['content_identity'] = content_identity(binding)
    except (EngineError, ValueError, KeyError, TypeError) as exc:
        # A missing derived identity is not evidence that the original snapshot changed.
        result['content_identity_error'] = getattr(exc, 'code', type(exc).__name__)
    return result


def anomalies(observations):
    return [dict(code='BLIND_REVIEW_EVIDENCE_CHANGED', text=f"Review evidence for {r.get('root')} cannot be reverified ({r.get('evidence_error')}); "
                 'the committed result remains readable but does not certify current content.')
            for r in observations if r['status'] == 'EVIDENCE_CHANGED']


def owns(cache, binding):
    root = binding['root']
    record = (cache.get('continuations') or [cache])[-1]
    d = (record.get('machine') or {}).get('dispatch') or {}
    return d.get('scope_root') == root


def refs(binding):
    return [dict(kind=r['kind'], ref='blind:'+binding['candidate_digest']+':'+str(n),
                 bytes=r['bytes'], sha256=r['sha256'], relative=r['relative']) for n, r in enumerate(binding['items'])]


def read(store, binding, ref, field, offset, limit):
    if field != 'output':
        fail('INPUT_REF_INVALID', 'Review file references expose output only, never a Writer cache.')
    rows = refs(binding)
    row = next((r for r in rows if r['ref'] == ref), None)
    if row is None:
        fail('INPUT_REF_INVALID', 'Review reference is outside this root binding.')
    item = binding['items'][rows.index(row)]
    try:
        data, meta = _bytes(store.cache_dir/item['snapshot'])
        if any(meta[k] != item[k] for k in ('sha256','bytes')):
            fail('BLIND_REVIEW_SNAPSHOT_CHANGED', 'Review input changed during read.')
        text = data.decode('utf-8')
    except UnicodeError:
        fail('INPUT_REF_INVALID', 'Binary review assets require their bound snapshot, not a fabricated text view.')
    if offset > len(text):
        fail('INPUT_REF_INVALID', 'Offset is beyond the review input.')
    end = min(len(text), offset+limit)
    return dict(status='INPUT', kind=row['kind'], field='output', encoding='text', offset=offset,
                total_chars=len(text), complete=offset == 0 and end == len(text),
                next_offset=end if end < len(text) else None, value=text if offset == 0 and end == len(text) else None,
                text=text[offset:end] if offset or end < len(text) else None, sha256=item['sha256'],
                candidate_digest=binding['candidate_digest'])


def latest_results(store, caches):
    roots = {}
    for cache in caches:
        record = (cache.get('continuations') or [cache])[-1]
        ref = record.get('machine', {}).get('review_binding')
        if ref:
            root = (record.get('machine', {}).get('dispatch') or {}).get('scope_root')
            if not root and cache.get('node'):
                root = dict(node=cache['node'], visit=cache.get('visit'))
            roots[(ref['path'], ref['sha256'])] = (ref, root)
    return [observe(store, ref, root) for ref, root in roots.values()]


def filter_reply(store, index, reply):
    from . import engine_core as ec
    binding = active(store, index)
    if not binding or reply.get('input_authority') is None:
        return reply
    ia = reply['input_authority']
    own = [c for c in ec._prev_business_caches(store, index) if owns(c, binding)]
    ia['user_message'], ia['prev_node_summary'], ia['context'] = None, None, {}
    ia['input_refs'] = refs(binding) + ec._input_refs(store, index, own)
    prefix = ia.get('parent_prefix')
    if prefix:
        try:
            entry = ec._catalog_entry(index, prefix['node'])
            cached = store.read_json(ec._cache_path_for(store,index,entry,prefix['visit'])) if entry else None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            cached = None
        if cached is None or not owns(cached,binding):
            ia.pop('parent_prefix',None)
        else:
            ia['input_refs'] += ec._input_refs(store,index,[cached])
    ia['input_catalog'].update(total=len(ia['input_refs']), has_more=False)
    ia['review_inputs'] = dict(candidate_digest=binding['candidate_digest'], root=binding['root'],
        isolation=binding['isolation'], rule='Read only these candidates/standards and this root\'s own prior steps. '
        'Do not read Writer rationale, old scores, repairs or upstream Report. This is not a shell sandbox.')
    if 'context_inputs' in binding:
        ia['review_inputs']['context'] = copy.deepcopy(binding['context_inputs'])
        ia['review_inputs']['context_binding_sha256'] = digest(binding)
    ia['required_fields'] = ec._required_fields_status([], own, {})
    for key in ('human_conditions','human_compliance_records'):
        ia.pop(key, None)
    if reply.get('frame'):
        reply['frame']['parent_steps'] = []
        reply['frame']['siblings'] = []
    if reply.get('module'):
        reply['module'] = {k:v for k,v in reply['module'].items() if k in ('note','status')}
    reply['source_support_candidates'] = []
    from . import contracts as _contracts
    rule = _contracts.text('resume.blind_review')
    if rule not in reply['payload_rules']:
        reply['payload_rules'].append(rule)
    return reply
