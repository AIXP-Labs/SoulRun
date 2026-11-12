"""Host request correlation, not a native identity or tool permission grant."""

from __future__ import annotations

import copy
import json
import re

from . import blind_review, dispatch_lifecycle, dispatch_prepare, dispatch_scope, independent_inputs, program_guard
from . import engine_core as ec
from .run_store import RunStore, sha256_bytes


def project(cache_dir, ticket, *, parent_session_id, parent_tool_call_id):
    """Internal prototype. No CLI accepts or records host authority through this API."""
    store = RunStore(cache_dir)
    with store.lock():
        return _project(store, ticket, parent_session_id, parent_tool_call_id)


def _project(store, ticket, parent_session_id, parent_tool_call_id):
    # Caller already holds the original run lock; never take a nested lock.
    index = store.read_index()
    program_guard.assert_run_version(index)
    if not dispatch_scope.enabled(index):
        return dict(status="NOT_APPLICABLE", tool_permission_granted=False)
    if not all(isinstance(v, str) and v for v in (ticket, parent_session_id, parent_tool_call_id)):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_CONTEXT_INVALID", "Exact ticket and parent call are required."
        )
    current = index.get("current") or {}
    entry = ec._catalog_entry(index, current.get("name"))
    if not entry or type(current.get("visit")) is not int:
        raise ec.EngineError("DISPATCH_RESOURCE_CONTEXT_INVALID", "No current occurrence.")
    dispatch_scope.assert_ticket(index, entry, current["visit"], ticket)
    owner_key, record = dispatch_scope.owner(index, entry, current["visit"])
    if not record or not record.get("scope_root") or record.get("exit_evidence"):
        raise ec.EngineError("DISPATCH_RESOURCE_CONTEXT_INVALID", "No active root segment.")
    actual = store.dispatch_path(ticket)
    if not store.exists_path(actual):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_CONTEXT_INVALID", "Prepared but unpublished is not an active ticket."
        )
    formal = store.read_json(actual)
    dispatch_prepare.verify(store, index, ticket, formal, dict(record, _owner_key=owner_key))
    if any(
        formal.get(k) != record.get(k)
        for k in ("input_binding", "review_binding", "resume_executor")
    ):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_CONTEXT_INVALID",
            "Ticket bindings differ from current root authority.",
        )
    start_path = store.cache_dir / f"_dispatch_start.{ticket}.json"
    start = store.read_json(start_path) if store.exists_path(start_path) else {}
    expected = dict(
        source="host_synchronous_agent_event",
        ticket=ticket,
        trace_id=index["trace_id"],
        bootstrap_sha256=record["bootstrap_sha256"],
        session_id=parent_session_id,
        tool_call_id=parent_tool_call_id,
    )
    if any(start.get(k) != v for k, v in expected.items()) or not all(
        isinstance(start.get(k), str) and start[k] for k in ("event_id", "at")
    ):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_PARENT_UNBOUND", "Recorded host parent call does not match."
        )
    resume = record.get("resume_executor")
    if resume and (
        resume.get("session_id") != parent_session_id
        or start.get("resume_agent_id") != resume.get("agent_id")
    ):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_PARENT_UNBOUND", "Recorded parent is not this original-child resume."
        )
    selected = None
    if record.get("input_binding"):
        selected = independent_inputs.load(store, record["input_binding"])
        expected_run = sha256_bytes(
            (str(store.cache_dir.resolve()) + index["trace_id"] + index["started_at"]).encode()
        )
        if selected.get("root") != record["scope_root"] or selected.get("run") != expected_run:
            raise ec.EngineError(
                "DISPATCH_RESOURCE_CONTEXT_INVALID",
                "Input snapshot belongs to another root or run.",
            )
    protocol = ec._engine_dir() / "agent_engine.aisop.json"
    raw = store.read_bytes(protocol)
    result = dict(
        status="DISPATCH_RESOURCE_CONTEXT",
        ticket=ticket,
        trace_id=index["trace_id"],
        current=copy.deepcopy(current),
        scope_root=copy.deepcopy(record["scope_root"]),
        execution_policy="inline",
        parent_event=copy.deepcopy(start),
        control_protocol=dict(
            path=str(protocol.resolve()), bytes=len(raw), sha256=sha256_bytes(raw)
        ),
        selected_input_refs=independent_inputs.refs(selected) if selected else [],
        tool_permission_granted=False,
        native_actor_bound=False,
        program_integrity_verified=False,
        verification_scope="local accepted Engine records only; not OS attestation or tool authority",
    )
    # This reader cannot claim, mint, rebind, retire, render or start any occurrence.
    if (
        store.read_index() != index
        or store.read_json(actual) != formal
        or store.read_json(start_path) != start
    ):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_CONTEXT_CHANGED", "Run evidence changed during projection."
        )
    return result


def _request_path(store, ticket, call):
    store.dispatch_path(ticket)
    if not isinstance(call, str) or not re.fullmatch(r"[A-Za-z0-9_:-]{1,160}", call):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_REQUEST_INVALID", "Invalid native tool call identity."
        )
    return store.cache_dir / f"_dispatch_tool.{ticket}.{sha256_bytes(call.encode())[:24]}.json"


def resolve_parent(cache_dir, ticket, *, parent_session_id, parent_tool_call_id, native_parent_tool_call_id):
    """SDK resume tools retain the original Agent parent; prove that exact lineage."""
    store = RunStore(cache_dir)
    with store.lock():
        return _resolve_parent(store, ticket, parent_session_id, parent_tool_call_id, native_parent_tool_call_id)


def _resolve_parent(store, ticket, session, call, native_call):
    context = _project(store, ticket, session, call)
    if native_call == call:
        return dict(status='DIRECT_PARENT', parent_tool_call_id=call, parent_lineage=None)
    if not isinstance(native_call, str) or not native_call:
        raise ec.EngineError('DISPATCH_RESOURCE_PARENT_UNBOUND', 'Exact native parent required.')
    index = store.read_index()
    current = index['current']
    _, record = dispatch_scope.owner(index, ec._catalog_entry(index,current['name']), current['visit'])
    if context.get('status') != 'DISPATCH_RESOURCE_CONTEXT' or not record:
        # docs/05SoulRun 88 (S1): a ticket no dispatch owns (a run that hands no node to a sub-agent) has no lineage to prove;
        # the engine's own error, as _project gives for a missing root segment - never a plain AttributeError.
        raise ec.EngineError('DISPATCH_RESOURCE_CONTEXT_INVALID', 'No active root segment owns this ticket.')
    target = record.get('resume_executor') or {}
    task_path = store.cache_dir / f'_dispatch_task_start.{ticket}.json'
    task = store.read_json(task_path) if store.exists_path(task_path) else {}
    expected = dict(source='host_sdk_task_event', ticket=ticket, trace_id=context['trace_id'],
        bootstrap_sha256=record['bootstrap_sha256'], session_id=session,
        agent_id=target.get('agent_id'), tool_call_id=call)
    if not target.get('agent_id') or target.get('session_id') != session \
            or any(task.get(k)!=v for k,v in expected.items()) or not task.get('event_id') or not task.get('at'):
        raise ec.EngineError('DISPATCH_RESOURCE_PARENT_UNBOUND', 'Actual same-child SDK start is required.')
    matches=[]
    for previous in record.get('history',[]):
        if not dispatch_lifecycle.returned(previous) or previous.get('scope_root') != record['scope_root']:
            continue
        proof = dispatch_lifecycle.verify(store, previous)
        origin = proof.get('call') or {}
        if proof.get('source')=='host_agent_tool_return' and not proof.get('tool_is_error') \
                and proof.get('agent_id') == target['agent_id'] and proof.get('trace_id') == context['trace_id'] \
                and origin.get('session_id') == session and origin.get('tool_call_id') == native_call \
                and (proof.get('result') or {}).get('status')=='completed':
            matches.append(previous)
    if len(matches)!=1:
        raise ec.EngineError('DISPATCH_RESOURCE_PARENT_UNBOUND', 'Original Agent return lineage is not unique.')
    original_path = store.cache_dir / matches[0]['exit_evidence']['path']
    return dict(status='RESUMED_PARENT_BOUND', parent_tool_call_id=call, native_parent_tool_call_id=native_call,
        parent_lineage=dict(original_return_ref=original_path.name,
            original_return_sha256=sha256_bytes(store.read_bytes(original_path)),
            current_task_start_ref=task_path.name, current_task_start_sha256=sha256_bytes(store.read_bytes(task_path))),
        tool_permission_granted=False, native_actor_bound=False)


def _result_path(path):
    return path.with_name(path.name.replace("_dispatch_tool.", "_dispatch_tool_result.", 1))


def _event(event_id, at):
    if not all(isinstance(v, str) and v for v in (event_id, at)):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_REQUEST_INVALID", "Actual host event identity and time are required."
        )


def _original_input(tool_name, raw_input):
    if (
        not isinstance(tool_name, str)
        or not tool_name
        or len(tool_name) > 160
        or not isinstance(raw_input, dict)
    ):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_REQUEST_INVALID",
            "Native tool name and original input object are required.",
        )
    try:
        raw = json.dumps(raw_input, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError) as failure:
        raise ec.EngineError(
            "DISPATCH_RESOURCE_REQUEST_INVALID", "Non-JSON native request."
        ) from failure
    if len(raw) > blind_review.MAX_BYTES:
        raise ec.EngineError(
            "DISPATCH_RESOURCE_REQUEST_INVALID", "Native input exceeds existing bounded input size."
        )
    if not _same_value(raw_input, json.loads(raw)):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_REQUEST_INVALID",
            "Native input must retain JSON key and value types.",
        )


def _same_value(left, right):
    """Python equality treats True as 1; original JSON types must not collapse."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(_same_value(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_value(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def record_request(
    cache_dir,
    ticket,
    *,
    parent_session_id,
    parent_tool_call_id,
    tool_call_id,
    tool_name,
    raw_input,
    event_id,
    at,
    native_parent_tool_call_id=None,
):
    """Host-only API called from actual pending child updates; no model-facing CLI."""
    _event(event_id, at)
    _original_input(tool_name, raw_input)
    store = RunStore(cache_dir)
    path = _request_path(store, ticket, tool_call_id)
    with store.lock():
        context = _project(store, ticket, parent_session_id, parent_tool_call_id)
        if context["status"] != "DISPATCH_RESOURCE_CONTEXT":
            return dict(status="NOT_APPLICABLE", tool_permission_granted=False)
        if tool_call_id == parent_tool_call_id:
            raise ec.EngineError(
                "DISPATCH_RESOURCE_REQUEST_INVALID", "Child cannot reuse the parent call identity."
            )
        identity = dict(
            schema_version=1,
            source="host_sdk_child_tool_request",
            ticket=ticket,
            trace_id=context["trace_id"],
            bootstrap_sha256=context["parent_event"]["bootstrap_sha256"],
            scope_root=context["scope_root"],
            parent_session_id=parent_session_id,
            parent_tool_call_id=parent_tool_call_id,
            parent_event_id=context["parent_event"]["event_id"],
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            raw_input=copy.deepcopy(raw_input),
        )
        if native_parent_tool_call_id is not None:
            lineage = _resolve_parent(store,ticket,parent_session_id,parent_tool_call_id,native_parent_tool_call_id)
            if lineage['parent_lineage'] is not None:
                identity.update(native_parent_tool_call_id=native_parent_tool_call_id,
                    parent_lineage=lineage['parent_lineage'])
        if store.exists_path(path):
            prior = store.read_json(path)
            if set(prior) != set(identity) | {"event_id", "at"} or any(
                not _same_value(prior.get(k), v) for k, v in identity.items()
            ):
                raise ec.EngineError(
                    "DISPATCH_RESOURCE_REQUEST_CONFLICT",
                    "Original child request cannot be overwritten or merged.",
                )
            if store.exists_path(_result_path(path)):
                raise ec.EngineError(
                    "DISPATCH_RESOURCE_REQUEST_CLOSED", "Completed tool cannot be rebound."
                )
        else:
            store.write_json_once(path, dict(identity, event_id=event_id, at=at))
        return dict(
            status="REQUEST_BOUND",
            request_ref=path.name,
            sha256=sha256_bytes(store.read_bytes(path)),
            tool_permission_granted=False,
            native_actor_bound=False,
        )


def record_result(
    cache_dir,
    ticket,
    *,
    parent_session_id,
    parent_tool_call_id,
    tool_call_id,
    tool_name,
    status,
    event_id,
    at,
    native_parent_tool_call_id=None,
):
    """Close an observed request, including after a pause; never reopen or grant."""
    _event(event_id, at)
    if status not in ("completed", "failed"):
        raise ec.EngineError(
            "DISPATCH_RESOURCE_REQUEST_INVALID",
            "Only actual tool terminal statuses close requests.",
        )
    store = RunStore(cache_dir)
    path = _request_path(store, ticket, tool_call_id)
    with store.lock():
        if not store.exists_path(path):
            return dict(status="REQUEST_UNBOUND", tool_permission_granted=False)
        prior = store.read_json(path)
        index = store.read_index()
        expected = dict(
            schema_version=1,
            source="host_sdk_child_tool_request",
            ticket=ticket,
            trace_id=index["trace_id"],
            parent_session_id=parent_session_id,
            parent_tool_call_id=parent_tool_call_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )
        if any(not _same_value(prior.get(k), v) for k, v in expected.items()):
            raise ec.EngineError(
                "DISPATCH_RESOURCE_REQUEST_CONFLICT",
                "Tool terminal event differs from its original request.",
            )
        if prior.get('native_parent_tool_call_id') != native_parent_tool_call_id:
            raise ec.EngineError('DISPATCH_RESOURCE_REQUEST_CONFLICT', 'Original SDK parent changed at terminal.')
        identity = dict(
            source="host_sdk_child_tool_terminal",
            ticket=ticket,
            trace_id=index["trace_id"],
            tool_call_id=tool_call_id,
            request_sha256=sha256_bytes(store.read_bytes(path)),
            status=status,
        )
        closed = _result_path(path)
        if store.exists_path(closed):
            saved = store.read_json(closed)
            if set(saved) != set(identity) | {"event_id", "at"} or any(
                not _same_value(saved.get(k), v) for k, v in identity.items()
            ):
                raise ec.EngineError(
                    "DISPATCH_RESOURCE_REQUEST_CONFLICT", "Conflicting tool terminal event."
                )
        else:
            store.write_json_once(closed, dict(identity, event_id=event_id, at=at))
        return dict(status="REQUEST_CLOSED", tool_permission_granted=False)


def same_input(tool_name, request, native):
    if _same_value(request, native):
        return True
    if (
        tool_name not in ("Read", "Write", "Edit")
        or not isinstance(request, dict)
        or not isinstance(native, dict)
        or set(request) != set(native)
    ):
        return False
    if tool_name == "Edit" and (
        not {"file_path", "old_string", "new_string"} <= set(request)
        or not set(request) <= {"file_path", "old_string", "new_string", "replace_all"}
        or not all(isinstance(request[k], str) for k in ("old_string", "new_string"))
        or ("replace_all" in request and type(request["replace_all"]) is not bool)
    ):
        return False
    left, right = request.get("file_path"), native.get("file_path")
    if not all(
        isinstance(p, str)
        and re.match(r"^[A-Za-z]:[\\/]", p)
        and not any(ord(c) < 32 for c in p)
        and ".." not in p.replace("\\", "/").split("/")
        for p in (left, right)
    ):
        return False
    return left.replace("\\", "/").casefold() == right.replace("\\", "/").casefold() and all(
        _same_value(request[k], native[k]) for k in request if k != "file_path"
    )


def read_request(cache_dir, ticket, *, session_id, tool_call_id, tool_name, raw_input):
    """Guard-side exact request check. Matching this receipt is not tool permission."""
    _original_input(tool_name, raw_input)
    store = RunStore(cache_dir)
    path = _request_path(store, ticket, tool_call_id)
    with store.lock():
        if not store.exists_path(path):
            raise ec.EngineError(
                "DISPATCH_RESOURCE_REQUEST_UNBOUND",
                "No actual host child request has been recorded.",
            )
        prior = store.read_json(path)
        if (
            type(prior.get("schema_version")) is not int
            or prior["schema_version"] != 1
            or prior.get("source") != "host_sdk_child_tool_request"
            or prior.get("ticket") != ticket
            or prior.get("tool_call_id") != tool_call_id
            or prior.get("tool_name") != tool_name
            or prior.get("parent_session_id") != session_id
            or not all(isinstance(prior.get(k), str) and prior[k] for k in ("event_id", "at"))
            or not same_input(tool_name, prior.get("raw_input"), raw_input)
        ):
            raise ec.EngineError(
                "DISPATCH_RESOURCE_REQUEST_CONFLICT",
                "Native request differs from the host API event.",
            )
        context = _project(store, ticket, session_id, prior.get("parent_tool_call_id"))
        if prior.get('native_parent_tool_call_id'):
            lineage = _resolve_parent(store,ticket,session_id,prior['parent_tool_call_id'],prior['native_parent_tool_call_id'])
            if lineage['parent_lineage'] != prior.get('parent_lineage'):
                raise ec.EngineError('DISPATCH_RESOURCE_REQUEST_CONFLICT', 'Resume parent lineage changed.')
        if (
            context.get("status") != "DISPATCH_RESOURCE_CONTEXT"
            or prior.get("trace_id") != context["trace_id"]
            or not _same_value(prior.get("scope_root"), context["scope_root"])
            or prior.get("bootstrap_sha256") != context["parent_event"]["bootstrap_sha256"]
            or prior.get("parent_event_id") != context["parent_event"]["event_id"]
        ):
            raise ec.EngineError(
                "DISPATCH_RESOURCE_REQUEST_CONFLICT", "Host request belongs to another run or root."
            )
        if store.exists_path(_result_path(path)):
            raise ec.EngineError("DISPATCH_RESOURCE_REQUEST_CLOSED", "Tool has already returned.")
        return dict(
            status="REQUEST_MATCHED",
            request_ref=path.name,
            sha256=sha256_bytes(store.read_bytes(path)),
            ticket=ticket,
            trace_id=context["trace_id"],
            scope_root=context["scope_root"],
            parent_tool_call_id=prior["parent_tool_call_id"],
            selected_input_refs=copy.deepcopy(context["selected_input_refs"]),
            request_link_verified=True,
            tool_permission_granted=False,
            native_actor_bound=False,
        )
