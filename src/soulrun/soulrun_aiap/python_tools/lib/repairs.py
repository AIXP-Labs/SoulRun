"""alpha.99 (04 series doc 239): repairs instead of refusals for the shape of a node commit.

Every commit refusal seen since alpha.93 (162 of 907 commits in 49 runs) was a form the engine can put right itself or a fact it can
record honestly. This module holds the shape repairs that run while the payload is parsed: a field the schema does not know is removed
and kept in the record (a known synonym is renamed instead), a required field with a meaningless default gets it, a null or malformed
optional value is dropped, a search source without a locator leaves the source list for the record. Nothing is silent: every repair is
a note (engine_anomalies) and every removed value is kept in machine.dropped_fields. Integrity fields are never touched here - the
machine-owned check runs first and still refuses them.
"""
from __future__ import annotations

import copy
import json
import re

_PATH_RE = re.compile(r"[^.\[\]]+|\[\d+\]")
_MISSING = object()

# (the parent's name, the field the schema does not know) -> the field the executor meant
FIELD_SYNONYMS = {
    ("", "degraded_note"): "degraded_reason", ("", "degradation_reason"): "degraded_reason", ("", "degraded_reasons"): "degraded_reason",
    ("", "degrade_reason"): "degraded_reason", ("items", "note"): "what", ("items", "description"): "what",
    ("not_applicable", "note"): "reason", ("not_applicable", "why"): "reason",
}

# (the parent's name, a required field) -> the default a missing one gets; a field not listed here stays a refusal
REQUIRED_DEFAULTS = {
    ("", "schema_version"): 1, ("", "user_messages"): [], ("", "anomalies"): [],
    ("", "degraded_reason"): None, ("", "evidence"): {"tool_calls": [], "artifacts": [], "sources": []},
    ("evidence", "tool_calls"): [], ("evidence", "artifacts"): [], ("evidence", "sources"): [],
    ("tool_calls", "purpose"): "(not given)", ("items", "kind"): "content", ("not_applicable", "reason"): "n/a",
    ("steps", "done"): [], ("steps", "remaining"): [], ("steps", "not_applicable"): [],
}

# optional values whose malformed form is dropped (the field then counts as not given)
DROPPABLE_PATTERN_KEYS = ("stdout_path", "stdout_sha256", "sha256", "sys_call")

# the containers a field may be removed from: the payload itself, the User Message declaration, the evidence lists and the steps. Never
# semantics (report / answer structures), gate, route or an HSAW item (hsaw_gate.normalize_shape handles those) - a field the schema does
# not know there may be a forged one and stays a refusal.
REPAIRABLE_PARENTS = ("", "user_message", "items", "not_applicable", "evidence", "sources", "tool_calls", "artifacts", "steps")


def _steps(path: str) -> list[str]:
    return _PATH_RE.findall(path or "")


def _get(obj, steps):
    for s in steps:
        obj = obj[int(s[1:-1])] if s.startswith("[") else obj[s]
    return obj


def _tail(steps) -> str:
    """the name of the container the last step lives in: 'items' for user_message.items[2], '' for the payload itself"""
    for s in reversed(steps):
        if not s.startswith("["):
            return s
    return ""


def _short(value, n: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= n else text[: n - 1] + "…"


class _Log:
    def __init__(self):
        self.dropped, self.renamed, self.filled, self.times, self.unlocated, self.coerced = [], [], [], [], [], []


def _repair_one(payload: dict, err: dict, log: _Log) -> bool:
    msg, field = str(err.get("message") or ""), str(err.get("field") or "")
    steps = _steps(field)
    if not steps:
        return False
    if _tail(steps[:-1]) not in REPAIRABLE_PARENTS and not (_tail(steps) == "sources" and steps[-1].startswith("[")):
        return False
    try:
        m = re.match(r"unexpected field '(.+?)'; allowed", msg)
        if m:
            key = m.group(1)
            parent = _get(payload, steps[:-1])
            if not isinstance(parent, dict) or key not in parent:
                return False
            value = parent.pop(key)
            tail = _tail(steps[:-1])
            target = FIELD_SYNONYMS.get((tail, key))
            if target and not str(parent.get(target) or "").strip():
                parent[target] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                log.renamed.append(f"{field} -> {target}")
                return True
            log.dropped.append({"field": field, "value": value})
            return True
        m = re.match(r"required field '(.+?)' is missing", msg)
        if m:
            key = m.group(1)
            parent = _get(payload, steps[:-1])
            default = REQUIRED_DEFAULTS.get((_tail(steps[:-1]), key), _MISSING)
            if not isinstance(parent, dict) or default is _MISSING:
                return False
            parent[key] = copy.deepcopy(default)
            log.filled.append(field)
            return True
        key = steps[-1]
        if msg.startswith("expected type") and msg.endswith("got null"):
            parent = _get(payload, steps[:-1])
            if key.startswith("[") and isinstance(parent, list):
                parent.pop(int(key[1:-1]))
                log.dropped.append({"field": field, "value": None})
                return True
            if isinstance(parent, dict) and key in parent:
                default = REQUIRED_DEFAULTS.get((_tail(steps[:-1]), key), _MISSING)
                if default is not _MISSING and default is not None:
                    parent[key] = copy.deepcopy(default)
                    log.filled.append(field)
                else:
                    del parent[key]
                    log.dropped.append({"field": field, "value": None})
                return True
            return False
        if msg == "string does not match pattern":
            parent = _get(payload, steps[:-1])
            if isinstance(parent, dict) and key == "retrieved_at":
                log.times.append({"field": field, "value": parent.get(key)})
                parent[key] = None
                return True
            if isinstance(parent, dict) and key in DROPPABLE_PATTERN_KEYS:
                log.dropped.append({"field": field, "value": parent.pop(key)})
                return True
            return False
        m = re.match(r"(\d+) oneOf alternatives matched", msg)
        if m and _tail(steps) == "sources" and steps[-1].startswith("["):
            src = _get(payload, steps)
            if not isinstance(src, dict):
                return False
            has_url = isinstance(src.get("url"), str) and bool(src["url"].strip())
            has_path = isinstance(src.get("path"), str) and bool(src["path"].strip())
            if has_url and has_path:
                log.dropped.append({"field": field + ".url", "value": src.pop("url")})
                src.pop("retrieved_at", None)
                return True
            if has_url and "retrieved_at" not in src:
                src["retrieved_at"] = None
                log.filled.append(field + ".retrieved_at")
                return True
            if not has_url and not has_path:
                _get(payload, steps[:-1]).pop(int(steps[-1][1:-1]))
                log.unlocated.append({"field": field, "value": src})
                return True
            return False
        # docs/05SoulRun 87: steps.not_applicable takes a key or {step, reason} (anyOf); any other object is repaired as before
        if msg in ("expected type string, got object", "no anyOf alternative matched") and _tail(steps[:-1]) == "not_applicable" \
                and steps[-1].startswith("["):
            lst = _get(payload, steps[:-1])
            obj = lst[int(steps[-1][1:-1])]
            if not isinstance(obj, dict):
                return False
            name = next((obj.get(k) for k in ("step", "key", "name") if isinstance(obj.get(k), str) and obj.get(k).strip()), None)
            if isinstance(obj, dict) and name:
                lst[int(steps[-1][1:-1])] = name
                log.coerced.append({"field": field, "value": obj})
                return True
            return False
        if msg == "expected type array, got string" and field == "user_messages":
            payload["user_messages"] = [payload["user_messages"]]
            log.coerced.append({"field": field, "value": "string -> [string]"})
            return True
        if msg.startswith("must be one of") and key == "kind" and _tail(steps[:-1]) == "items":
            parent = _get(payload, steps[:-1])
            log.coerced.append({"field": field, "value": parent.get("kind")})
            parent["kind"] = "content"
            return True
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return False


def repair_schema(payload: dict, schema: dict, validate, notes: list | None) -> list[dict]:
    """alpha.99 (doc 239 P7): validate, repair the first repairable error, validate again - until the payload is valid or nothing more can
    be repaired. Returns the errors that remain (the caller still refuses those). Every repair is noted."""
    log = _Log()
    errors = validate(payload, schema)
    for _ in range(96):
        if not errors:
            break
        if not any(_repair_one(payload, err, log) for err in errors):
            break
        errors = validate(payload, schema)
    if notes is not None:
        if log.dropped or log.coerced:
            notes.append({"code": "SHAPE_FIELD_DROPPED",
                          "text": "fields the commit schema does not take were removed and kept in machine.dropped_fields (alpha.99): "
                                  + "; ".join(f"{d['field']}={_short(d['value'], 80)}" for d in (log.dropped + log.coerced)[:12]),
                          "fields": log.dropped + log.coerced})
        if log.renamed:
            notes.append({"code": "SHAPE_FIELD_RENAMED", "text": "; ".join(log.renamed) + " (alpha.99: the schema's own field name)"})
        if log.filled:
            notes.append({"code": "SHAPE_DEFAULT_FILLED", "text": f"{log.filled}: missing, set to the skeleton default (alpha.99)"})
        if log.times:
            notes.append({"code": "SOURCE_TIME_DROPPED", "text": "retrieved_at is a full timestamp or null; kept as null, the given value recorded (alpha.99): "
                                                                   + "; ".join(f"{t['field']}={t['value']!r}" for t in log.times),
                          "fields": log.times})
        if log.unlocated:
            notes.append({"code": "SOURCE_WITHOUT_LOCATOR", "text": f"{len(log.unlocated)} source(s) with neither url nor path left evidence.sources "
                                                                    "and are kept in machine.dropped_fields (alpha.99): "
                                                                    + "; ".join(_short(u['value'], 100) for u in log.unlocated[:4]),
                          "fields": log.unlocated})
    return errors


def dropped_fields(notes: list) -> list:
    """the removed values the notes carry, for machine.dropped_fields; the notes themselves keep code and text only"""
    out = []
    for n in notes:
        if isinstance(n, dict) and "fields" in n:
            out.extend(n.pop("fields"))
    return out
