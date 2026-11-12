"""Agent-local AIAP / AISP discovery catalog for Router.match (alpha.20; ported from the v6 python_tools/list.py).

The engine never parses package files for discovery metadata. Each protocol's registry owns it:
    aiap/aiap_list.py + aiap_list.json   AIAP packages: id, name, version, summary, path, loading_mode
    aisp/aisp_list.py + aisp_list.json   AISP skills:   id, name, summary, path, category, tags, when_to_use, risk_level
collect_registry() runs ``<script> --check`` (exit 0 = the JSON is current) and otherwise ``<script> --json`` to
regenerate it, reads the JSON, validates the schema and every entry path, normalises both protocols to one entry
shape, rejects duplicate route identities and fingerprints the catalog (entries + script / JSON sha256) so a route
can be bound to exactly what the Router saw. A protocol directory that is absent contributes nothing; one that
exists without its registry script is scanned for entry files instead (recorded as SCAN_FALLBACK, never silent).
A registry script that fails halts routing (RegistryError): the engine does not route on a partial catalog.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from . import program_loader
from .run_store import FileLock, now_iso

VALID_LOADING_MODES = frozenset({"normal", "node", "lite"})
SCRIPT_TIMEOUT_S = 30
LOCK_NAME = ".registry.lock"
# protocol, registry sub-directory, registry script, registry JSON, entry file name, JSON root key, JSON version key
SPECS = (
    ("AIAP", "aiap", "aiap_list.py", "aiap_list.json", "main.aisop.json", "packages", "aiap_list_version"),
    ("AISP", "aisp", "aisp_list.py", "aisp_list.json", "aisp.aisop.json", "skills", "aisp_list_version"),
)
ENTRY_FIELDS = ("package", "protocol", "registry_id", "package_name", "name", "version", "summary", "dir", "entry_file",
                "entry_path", "loading_mode", "category", "tags", "when_to_use", "risk")
PROJECTED_FIELDS = ("package", "protocol", "name", "version", "summary", "category", "tags", "when_to_use", "risk")

_Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class RegistryError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code, self.detail = code, detail


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(script: Path, argument: str, *, runner: _Runner):
    try:
        return runner([sys.executable, "-X", "utf8", "-B", str(script), argument], cwd=str(script.parent),
                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=SCRIPT_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RegistryError("REGISTRY_SCRIPT_TIMEOUT", f"{script.name} {argument} exceeded {SCRIPT_TIMEOUT_S}s") from exc


def _refresh_source(protocol: str, directory: Path, script_name: str, json_name: str, *, force_refresh: bool,
                    runner: _Runner) -> tuple[dict, dict]:
    script, output = directory / script_name, directory / json_name
    check = None if force_refresh else _run(script, "--check", runner=runner)
    freshness, refresh = "FRESH", None
    if check is None or check.returncode != 0:
        refresh = _run(script, "--json", runner=runner)
        if refresh.returncode != 0:
            detail = (refresh.stderr or refresh.stdout or "").strip()
            raise RegistryError(f"{protocol}_REGISTRY_REFRESH_FAILED", f"exit={refresh.returncode}:{detail[:500]}")
        freshness = "REFRESHED"
    try:
        raw = output.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RegistryError(f"{protocol}_REGISTRY_JSON_INVALID", str(exc)) from exc
    if not isinstance(data, dict):
        raise RegistryError(f"{protocol}_REGISTRY_JSON_ROOT_NOT_OBJECT")
    source = {"protocol": protocol, "freshness": freshness, "script_path": str(script), "script_sha256": _sha256(script),
              "json_path": str(output), "json_sha256": hashlib.sha256(raw).hexdigest(),
              "check_returncode": None if check is None else check.returncode,
              "refresh_returncode": None if refresh is None else refresh.returncode}
    return data, source


def _required_text(item: dict, key: str, protocol: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{protocol}_REGISTRY_FIELD_INVALID", key)
    return value.strip()


def _text_list(item: dict, key: str, protocol: str) -> list[str]:
    value = item.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(part, str) for part in value):
        raise RegistryError(f"{protocol}_REGISTRY_FIELD_INVALID", key)
    return list(value)


def _entry_path(agent_dir: Path, registry_dir: Path, relative_path: str, registry_id: str, expected_name: str, protocol: str) -> Path:
    candidate = (agent_dir / relative_path).resolve()
    if not candidate.is_file():
        raise RegistryError(f"{protocol}_REGISTRY_ENTRY_MISSING", f"{registry_id}: {relative_path}")
    try:
        candidate.relative_to(registry_dir.resolve())
    except ValueError as exc:
        raise RegistryError(f"{protocol}_REGISTRY_ENTRY_OUTSIDE_REGISTRY", registry_id) from exc
    if candidate.name != expected_name or candidate.parent.name != registry_id:
        raise RegistryError(f"{protocol}_REGISTRY_ENTRY_ID_PATH_MISMATCH", registry_id)
    return candidate


def make_entry(protocol: str, registry_id: str, entry: Path, **fields) -> dict:
    base = {"package": registry_id, "protocol": protocol, "registry_id": registry_id,
            "package_name": registry_id.removesuffix("_aiap") if protocol == "AIAP" else registry_id,
            "name": registry_id, "version": "", "summary": None, "dir": str(entry.parent), "entry_file": entry.name,
            "entry_path": str(entry), "loading_mode": "node" if protocol == "AISP" else "normal",
            "category": None, "tags": [], "when_to_use": [], "risk": None}
    base.update({k: v for k, v in fields.items() if k in ENTRY_FIELDS})
    return base


def _normalize(protocol: str, data: dict, agent_dir: Path, registry_dir: Path, entry_name: str, root_key: str, version_key: str) -> list[dict]:
    if data.get(version_key) != "1.0" or not isinstance(data.get(root_key), list):
        raise RegistryError(f"{protocol}_REGISTRY_SCHEMA_INVALID", f"{version_key} must be 1.0 with a {root_key} list")
    entries = []
    for raw in data[root_key]:
        if not isinstance(raw, dict):
            raise RegistryError(f"{protocol}_REGISTRY_ENTRY_NOT_OBJECT")
        registry_id = _required_text(raw, "id", protocol)
        relative_path = _required_text(raw, "path", protocol)
        entry = _entry_path(agent_dir, registry_dir, relative_path, registry_id, entry_name, protocol)
        if protocol == "AIAP":
            loading_mode = raw.get("loading_mode", "normal")
            if loading_mode not in VALID_LOADING_MODES:
                raise RegistryError("AIAP_REGISTRY_LOADING_MODE_INVALID", f"{registry_id}:{loading_mode}")
            entries.append(make_entry(protocol, registry_id, entry, name=raw.get("name") or registry_id, version=raw.get("version") or "",
                                  summary=raw.get("summary") or None, loading_mode=loading_mode))
        else:
            entries.append(make_entry(protocol, registry_id, entry, name=raw.get("name") or registry_id, summary=raw.get("summary") or None,
                                  category=raw.get("category"), tags=_text_list(raw, "tags", protocol),
                                  when_to_use=_text_list(raw, "when_to_use", protocol), risk=raw.get("risk_level")))
    return entries


def describe_entry(entry_path: str | Path) -> dict:
    """Discovery metadata of one package taken from its own entry document (the same fields the registry scripts
    derive), for the explicit --entry-path mode and the SCAN_FALLBACK path. No AIAP.md is read."""
    path = Path(entry_path)
    protocol = "AISP" if path.name == "aisp.aisop.json" else "AIAP"
    meta: dict[str, Any] = {"protocol": protocol}
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        system = doc[0]["content"] if isinstance(doc, list) and doc and isinstance(doc[0], dict) else {}
        user = doc[1]["content"] if isinstance(doc, list) and len(doc) > 1 and isinstance(doc[1], dict) else {}
    except (OSError, ValueError, IndexError, TypeError, AttributeError):
        return meta
    if not isinstance(system, dict):
        return meta
    meta["name"] = system.get("name") or None
    meta["version"] = system.get("version") or ""
    meta["summary"] = system.get("summary") or system.get("description") or None
    if protocol == "AIAP":
        meta["loading_mode"] = system.get("loading_mode", "normal")
    else:
        contract = user.get("aisp_contract") if isinstance(user, dict) else None
        contract = contract if isinstance(contract, dict) else {}
        discovery = contract.get("discovery") if isinstance(contract.get("discovery"), dict) else {}
        invocation = contract.get("invocation") if isinstance(contract.get("invocation"), dict) else {}
        meta["category"] = discovery.get("category")
        meta["tags"] = [t for t in (discovery.get("tags") or []) if isinstance(t, str)]
        meta["when_to_use"] = [t for t in (invocation.get("when_to_use") or []) if isinstance(t, str)]
        meta["risk"] = contract.get("risk_level")
        meta["loading_mode"] = "node"
    return meta


def scan_entries(protocol: str, directory: Path) -> list[dict]:
    """SCAN_FALLBACK: a registry directory without its script - entry files found by directory scan, metadata from
    each entry document. Used for test fixtures and legacy agent directories; recorded in sources.freshness."""
    out = []
    for item in program_loader.registry_snapshot(directory):
        entry = Path(item["dir"]) / item["entry_file"]
        meta = describe_entry(entry)
        if meta.get("protocol") != protocol:
            continue
        out.append(make_entry(protocol, item["package"], entry, **{k: v for k, v in meta.items() if k in ENTRY_FIELDS and k != "protocol" and v is not None}))
    return out


def collect_registry(agent_dir: str | Path, *, force_refresh: bool = False, runner: _Runner = subprocess.run) -> dict:
    root = Path(agent_dir).resolve()
    if not root.is_dir():
        raise RegistryError("REGISTRY_AGENT_DIR_MISSING", str(root))
    sources: dict[str, dict] = {}
    entries: list[dict] = []
    jobs = {}
    with FileLock(root / LOCK_NAME, timeout=35.0):
        with ThreadPoolExecutor(max_workers=2) as executor:
            for protocol, sub, script_name, json_name, entry_name, root_key, version_key in SPECS:
                directory = root / sub
                if not directory.is_dir():
                    sources[protocol] = {"protocol": protocol, "freshness": "ABSENT", "registry_dir": str(directory)}
                    continue
                if not (directory / script_name).is_file():
                    sources[protocol] = {"protocol": protocol, "freshness": "SCAN_FALLBACK", "registry_dir": str(directory)}
                    entries.extend(scan_entries(protocol, directory))
                    continue
                jobs[protocol] = (executor.submit(_refresh_source, protocol, directory, script_name, json_name,
                                                  force_refresh=force_refresh, runner=runner),
                                  directory, entry_name, root_key, version_key)
            for protocol, (future, directory, entry_name, root_key, version_key) in jobs.items():
                data, source = future.result()
                sources[protocol] = source
                entries.extend(_normalize(protocol, data, root, directory, entry_name, root_key, version_key))
    entries.sort(key=lambda item: (item["protocol"], item["package"]))
    identities = [(item["protocol"], item["package"]) for item in entries]
    if len(identities) != len(set(identities)):
        raise RegistryError("REGISTRY_DUPLICATE_ROUTE_IDENTITY")
    route_entries = [{k: item[k] for k in ("protocol", "package", "entry_path", "loading_mode")} for item in entries]
    # the fingerprint covers what the Router decides from (entries + the bytes they came from), not how fresh the
    # JSON was when read: FRESH and REFRESHED runs over the same bytes carry the same catalog_sha256
    source_sha = {p: {"script": s.get("script_sha256"), "json": s.get("json_sha256")} for p, s in sorted(sources.items())}
    material = {"registry_version": "1.0", "entries": entries, "source_sha256": source_sha}
    catalog_sha256 = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"status": "ok", "registry_version": "1.0", "catalog_sha256": catalog_sha256, "captured_at": now_iso(),
            "aiap_count": sum(item["protocol"] == "AIAP" for item in entries),
            "aisp_count": sum(item["protocol"] == "AISP" for item in entries),
            "sources": sources, "entries": entries, "route_entries": route_entries}


def provenance(catalog: dict) -> dict:
    """The compact record kept in _run_input.json / _index.route: what the Router decided from."""
    return {"catalog_sha256": catalog["catalog_sha256"], "captured_at": catalog["captured_at"],
            "aiap_count": catalog["aiap_count"], "aisp_count": catalog["aisp_count"],
            "sources": {p: {"freshness": s.get("freshness"), "script_sha256": s.get("script_sha256"), "json_sha256": s.get("json_sha256")}
                        for p, s in sorted(catalog["sources"].items())}}
