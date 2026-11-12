"""alpha.97 (04 series docs 214 / 215 / 230 / 233): the resident payload rules are data. contracts/*.contract.json hold every rule text the
engine serves in payload_rules, one section per rule; contracts/manifest.json lists every contract file with its sha256 and is checked on
the first load - a missing, extra or changed file stops the engine (CONTRACT_INTEGRITY). Dynamic parts are <<name>> placeholders the
engine fills; text() refuses an unfilled or unknown placeholder. The governance hash covers only the top-level *.aisop.json (AIAP §18.1),
so the manifest is the contracts' own integrity check. This module imports only the standard library (every other lib module imports it).

alpha.100 (04 series docs 214 / 215 / 241, mixed delivery): text() returns a Rule - the same str, plus the section it comes from (key), the
text the delivery sends (delivery: identical, except that a placeholder named in _facts names a node_facts field instead of carrying this
node's value) and the sections nested in it through placeholders (parts: {key: digest}). engine_core._deliver_contracts sends a section's
delivery text once per model session and names it afterwards; tag() is the label in front of a sent section. The contract texts and the
rules _payload_skeleton assembles are unchanged."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts"
MANIFEST = "manifest.json"
_TOKEN = re.compile(r"<<([a-z][a-z0-9_]*)>>")
_SECTIONS: dict[str, str] | None = None
_VERSIONS: dict[str, int] | None = None
_EXAMPLES: dict[str, dict] | None = None


class ContractIntegrityError(RuntimeError):
    code = "CONTRACT_INTEGRITY"

    def __init__(self, message: str):
        super().__init__(f"CONTRACT_INTEGRITY: {message}")


class Rule(str):
    """alpha.100: a served rule text that knows its contract section(s); compares, joins and serialises as the plain text."""
    key: str = ""
    delivery: str = ""
    parts: dict = {}


def _rule(value: str, key: str, delivery: str, parts: dict) -> Rule:
    out = Rule(value)
    out.key, out.delivery, out.parts = key, delivery, parts
    return out


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _load(directory: Path) -> tuple[dict[str, str], dict[str, int], dict[str, dict]]:
    directory = Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractIntegrityError(f"{directory / MANIFEST} unreadable: {exc}") from exc
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict) or not files:
        raise ContractIntegrityError("manifest.files must name every contract file with its sha256")
    present = sorted(p.name for p in directory.glob("*.contract.json"))
    if present != sorted(files):
        raise ContractIntegrityError(f"contract files {present} differ from the manifest {sorted(files)}")
    sections: dict[str, str] = {}
    versions: dict[str, int] = {}
    examples: dict[str, dict] = {}
    for name, digest_ in files.items():
        raw = (directory / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest_:
            raise ContractIntegrityError(f"{name} does not match its manifest sha256")
        doc = json.loads(raw.decode("utf-8"))
        if doc.get("id") + ".contract.json" != name:
            raise ContractIntegrityError(f"{name} carries id {doc.get('id')!r}")
        versions[doc["id"]] = int(doc.get("version") or 1)
        for section in doc.get("sections") or []:
            sid, text_ = section.get("id"), section.get("text")
            if not isinstance(sid, str) or not sid.startswith(doc["id"] + ".") or not isinstance(text_, str) or not text_:
                raise ContractIntegrityError(f"{name}: a section needs an id '{doc['id']}.<name>' and a nonempty text")
            if sid in sections:
                raise ContractIntegrityError(f"section {sid} is defined twice")
            sections[sid] = text_
            if isinstance(section.get("example"), dict):   # alpha.107 (doc 269 T4)
                examples[sid] = section["example"]
    return sections, versions, examples


def load_dir(directory: Path) -> dict[str, str]:
    """Every section of every contract in directory, after the manifest check: {section id: text}."""
    return _load(directory)[0]


def sections() -> dict[str, str]:
    global _SECTIONS, _VERSIONS, _EXAMPLES
    if _SECTIONS is None:
        _SECTIONS, _VERSIONS, _EXAMPLES = _load(CONTRACT_DIR)
    return _SECTIONS


def example(section_id: str) -> dict:
    """alpha.107 (doc 269 T4): the JSON example a section carries (hsaw.doubt_gate: a critical item with its gate), as a deep copy."""
    sections()
    try:
        return copy.deepcopy((_EXAMPLES or {})[section_id])
    except KeyError:
        raise ContractIntegrityError(f"{section_id} carries no example") from None


def versions() -> dict[str, int]:
    """alpha.100: {contract id: version} of the loaded contracts."""
    sections()
    return dict(_VERSIONS or {})


def contract_of(section_id: str) -> str:
    return section_id.split(".", 1)[0]


def placeholders(section_id: str) -> list[str]:
    return sorted(set(_TOKEN.findall(sections()[section_id])))


def tag(key: str) -> str:
    """alpha.100: the label in front of a sent section, e.g. '[core.steps v1] '; a composed rule names each of its sections."""
    known = versions()
    return "[" + " + ".join(f"{sid} v{known[contract_of(sid)]}" for sid in key.split("+")) + "] "


def text(section_id: str, _facts: dict | None = None, **values) -> Rule:
    """The rule text of one section, its <<name>> placeholders filled: a str as is, anything else as an f-string would format it.
    _facts (alpha.100): {placeholder: node_facts field name} for the delivery text; the returned text itself keeps the values."""
    try:
        body = sections()[section_id]
    except KeyError:
        raise ContractIntegrityError(f"unknown contract section {section_id}") from None
    wanted = set(_TOKEN.findall(body))
    if wanted != set(values):
        raise ContractIntegrityError(f"{section_id} takes {sorted(wanted)}, got {sorted(values)}")
    if _facts and not set(_facts) <= wanted:
        raise ContractIntegrityError(f"{section_id}: {sorted(set(_facts) - wanted)} are not its placeholders")

    def fill(vals: dict) -> str:
        return _TOKEN.sub(lambda m: vals[m.group(1)] if isinstance(vals[m.group(1)], str) else format(vals[m.group(1)]), body)

    parts: dict = {}
    for value in values.values():
        if isinstance(value, Rule):
            parts[value.key] = digest(value.delivery)
            parts.update(value.parts)
    shown = {k: (v.delivery if isinstance(v, Rule) else v) for k, v in values.items()}
    return _rule(fill(values), section_id, fill({**shown, **(_facts or {})}), parts)


def joined(*rules: Rule) -> Rule:
    """alpha.100: rules served as one text (joined by a space, as before), delivered and named as one."""
    parts: dict = {}
    for rule in rules:
        parts.update(rule.parts)
    return _rule(" ".join(rules), "+".join(r.key for r in rules), " ".join(r.delivery for r in rules), parts)
