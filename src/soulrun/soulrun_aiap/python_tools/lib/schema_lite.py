"""Minimal JSON Schema (draft 2020-12 subset) validator. Zero dependencies.

Supported keywords: type (incl. lists; integer excludes bool), const, enum, properties, required,
additionalProperties (bool or schema), items, minItems, maxItems, uniqueItems, minLength, maxLength,
pattern, minimum, maximum, exclusiveMinimum, exclusiveMaximum, $ref (local "#/..." only),
allOf, anyOf, oneOf, not. Unknown keywords are ignored (annotations such as description, x-*).

Errors are dicts {field, code, expected, actual, message} so node_commit can turn them into
"error is help" rejections (doc 01 §4.1).
"""
from __future__ import annotations

import re
from typing import Any

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class SchemaError(ValueError):
    """The schema itself is malformed (bad $ref, unknown type name)."""


def _resolve_ref(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local refs are supported: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise SchemaError(f"unresolvable ref {ref}")
    if not isinstance(node, dict):
        raise SchemaError(f"ref {ref} does not point to a schema object")
    return node


def _join(path: str, key) -> str:
    return f"{path}[{key}]" if isinstance(key, int) else (f"{path}.{key}" if path else str(key))


def _err(field: str, code: str, expected, actual, message: str) -> dict:
    return {"field": field, "code": code, "expected": expected, "actual": actual, "message": message}


def _type_name(value) -> str:
    for name, check in _TYPE_CHECKS.items():
        if name != "number" and check(value):
            return name
    return type(value).__name__


def validate(instance, schema: dict, root: dict | None = None, path: str = "") -> list[dict]:
    """Return a list of error dicts (empty = valid)."""
    root = root if root is not None else schema
    if schema is True:
        return []
    if schema is False:
        return [_err(path, "SCHEMA_INVALID", "nothing", _type_name(instance), "no value allowed here")]
    if "$ref" in schema:
        target = _resolve_ref(schema["$ref"], root)
        merged = {k: v for k, v in schema.items() if k != "$ref"}
        errors = validate(instance, target, root, path)
        return errors + (validate(instance, merged, root, path) if merged else [])
    errors: list[dict] = []

    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        for t in allowed:
            if t not in _TYPE_CHECKS:
                raise SchemaError(f"unknown type {t!r}")
        if not any(_TYPE_CHECKS[t](instance) for t in allowed):
            errors.append(_err(path, "SCHEMA_INVALID", "|".join(allowed), _type_name(instance),
                               f"expected type {'|'.join(allowed)}, got {_type_name(instance)}"))
            return errors  # further keyword checks assume the right type
    if "const" in schema and instance != schema["const"]:
        errors.append(_err(path, "SCHEMA_INVALID", schema["const"], instance, f"must equal {schema['const']!r}"))
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(_err(path, "SCHEMA_INVALID", schema["enum"], instance, f"must be one of {schema['enum']!r}"))

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(_err(_join(path, key), "SCHEMA_INVALID", "present", "missing", f"required field {key!r} is missing"))
        for key, value in instance.items():
            if key in props:
                errors.extend(validate(value, props[key], root, _join(path, key)))
            else:
                extra = schema.get("additionalProperties", True)
                if extra is False:
                    errors.append(_err(_join(path, key), "SCHEMA_INVALID", "absent", "present",
                                       f"unexpected field {key!r}; allowed: {sorted(props)}"))
                elif isinstance(extra, dict):
                    errors.extend(validate(value, extra, root, _join(path, key)))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(_err(path, "SCHEMA_INVALID", f">= {schema['minItems']} items", len(instance), "too few items"))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(_err(path, "SCHEMA_INVALID", f"<= {schema['maxItems']} items", len(instance), "too many items"))
        if schema.get("uniqueItems"):
            seen = []
            for item in instance:
                if item in seen:
                    errors.append(_err(path, "SCHEMA_INVALID", "unique items", item, "duplicate item"))
                    break
                seen.append(item)
        if "items" in schema:
            for i, item in enumerate(instance):
                errors.extend(validate(item, schema["items"], root, _join(path, i)))
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(_err(path, "SCHEMA_INVALID", f"length >= {schema['minLength']}", len(instance), "string too short"))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(_err(path, "SCHEMA_INVALID", f"length <= {schema['maxLength']}", len(instance), "string too long"))
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(_err(path, "SCHEMA_INVALID", f"pattern {schema['pattern']}", instance, "string does not match pattern"))
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(_err(path, "SCHEMA_INVALID", f">= {schema['minimum']}", instance, "below minimum"))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(_err(path, "SCHEMA_INVALID", f"<= {schema['maximum']}", instance, "above maximum"))
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(_err(path, "SCHEMA_INVALID", f"> {schema['exclusiveMinimum']}", instance, "not above exclusive minimum"))
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append(_err(path, "SCHEMA_INVALID", f"< {schema['exclusiveMaximum']}", instance, "not below exclusive maximum"))

    for sub in schema.get("allOf", []):
        errors.extend(validate(instance, sub, root, path))
    if "anyOf" in schema:
        if not any(not validate(instance, sub, root, path) for sub in schema["anyOf"]):
            errors.append(_err(path, "SCHEMA_INVALID", "match any of the alternatives", _type_name(instance), "no anyOf alternative matched"))
    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not validate(instance, sub, root, path))
        if matches != 1:
            errors.append(_err(path, "SCHEMA_INVALID", "exactly one alternative", matches, f"{matches} oneOf alternatives matched"))
    if "not" in schema and not validate(instance, schema["not"], root, path):
        errors.append(_err(path, "SCHEMA_INVALID", "not matching the forbidden schema", _type_name(instance), "value matches a forbidden schema"))
    return errors


def machine_owned_hits(instance: dict, schema: dict) -> list[str]:
    """Keys of the payload that appear in the schema's x-machine-owned list (MACHINE_FIELD_REJECTED)."""
    owned = set(schema.get("x-machine-owned", []))
    return sorted(k for k in instance if k in owned) if isinstance(instance, dict) else []
