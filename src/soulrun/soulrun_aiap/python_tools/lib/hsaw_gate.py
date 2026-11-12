"""alpha.87 (04 series doc 193; rulings docs 180 / 181 / 182): the HSAW sovereignty doubt gate, phase P1.

The model records every doubt / problem / bug it meets in hsaw_items[] of its commit. Python validates structure and
self-consistency (alpha.99, doc 239: it raises a level the item's own facts require - never lowers one, never reads the text), records the items in the run's chained register and the package's
append-only cross-run ledger, opens the gate for FREEZE_NOW items, and presents them. Two branches:
  human intent  - doubt: always critical -> FREEZE_NOW (this commit carries the gate) or HARD_FAIL (no safe resume);
  execution     - problem / bug: critical freezes the same way, medium ADVISEs without asking, low only REPORTs.
Nothing here modifies a program, the engine or a tool; authorization is the human's alone (first rule, 2026-09-21).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import contracts as _contracts   # alpha.97 (doc 233)

CATEGORIES = ("doubt", "problem", "bug")
SEVERITIES = ("critical", "medium", "low")
DISPOSITIONS = ("FREEZE_NOW", "HARD_FAIL", "ADVISE", "REPORT")
IMPACTS = ("authorization", "sovereignty", "audit", "safety", "data", "behavior", "compatibility", "documentation", "naming", "cosmetic")
SOVEREIGN_IMPACTS = frozenset({"authorization", "sovereignty", "audit", "safety"})
LOW_IMPACTS = frozenset({"documentation", "naming", "cosmetic"})
SCOPES = ("target_aiap", "target_aisp", "execute_engine", "sovereignty_toolset", "tool")
COMMON_FIELDS = ("category", "severity", "classification_uncertain", "escalated_from", "impact_classes", "disposition", "title",
                 "description", "evidence_refs", "reversible", "classification_rationale", "recommendation")
BUG_FIELDS = ("scope", "affected_files", "touches_sovereignty_toolset", "affects_sovereignty_markers", "proposed_fix")
OPTIONAL_FIELDS = ("same_as",)
ENGINE_FIELDS = ("id", "fingerprint", "occurrence", "status", "seq", "prev_sha", "sha", "recorded_at", "authorization", "gate_question_id")
RANK = {"low": 0, "medium": 1, "critical": 2}
GATE_SOURCE = "hsaw_doubt"
BUG_GATE_INTENTS = ("authorize_fix", "not_a_defect")
NO_RECOMMENDATION = "none"
CLOSING = {"zh": "引擎不会自己修改任何东西；沉默不构成授权。",
           "en": "The engine will not modify anything by itself; silence is not authorization."}
ID_RE = re.compile(r"^H-[0-9a-f]{8}$")
LEDGER_DIR = "_hsaw"
GENESIS = "0" * 64
EVENT_KINDS = ("discovered", "gate_opened", "gate_answered")

RULE = _contracts.text("hsaw.doubt_gate")

EXAMPLE_ITEM = {
    "category": "bug", "severity": "medium", "classification_uncertain": False, "escalated_from": None,
    "impact_classes": ["behavior", "compatibility"], "disposition": "ADVISE",
    "title": "sign_disclosure.py hard-codes version 2.3.4",
    "description": "python_tools/sign_disclosure.py rewrites the front matter with TOOL_VERSION 2.3.4 while the package is 2.3.6.",
    "evidence_refs": ["proc:_proc/GenerateExport.3.out"], "reversible": True,
    "classification_rationale": "Continuation is proven safe: the signature verifies; only a version label is stale.",
    "recommendation": "Fix the two constants through a Creator evolution; until then pass --claim-generator explicitly.",
    "scope": "target_aiap", "affected_files": ["python_tools/sign_disclosure.py"], "touches_sovereignty_toolset": False,
    "affects_sovereignty_markers": False, "proposed_fix": "Read the version from agent_card.json instead of a constant.",
}


class HsawError(Exception):
    def __init__(self, code: str, message: str, *, field: str = "hsaw_items", expected=None):
        super().__init__(message)
        self.code, self.message, self.field, self.expected = code, message, field, expected


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_items(items, *, ref_ok) -> list[dict]:
    """Structure and self-consistency of the model's hsaw_items; raises HsawError; never touches severity itself."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise HsawError("HSAW_ITEM_INVALID", "hsaw_items must be an array of items", expected="array")
    out = []
    for i, item in enumerate(items):
        f = f"hsaw_items[{i}]"
        if not isinstance(item, dict):
            raise HsawError("HSAW_ITEM_INVALID", "each item is an object", field=f, expected=list(COMMON_FIELDS))
        forged = [k for k in ENGINE_FIELDS if k in item]
        if forged:
            raise HsawError("HSAW_FIELD_REJECTED", f"engine-owned field(s) {forged} present", field=f"{f}.{forged[0]}", expected="absent")
        missing = [k for k in COMMON_FIELDS if k not in item]
        if missing:
            raise HsawError("HSAW_ITEM_INVALID", f"missing {missing}", field=f"{f}.{missing[0]}", expected=list(COMMON_FIELDS))
        unknown = [k for k in item if k not in COMMON_FIELDS + BUG_FIELDS + OPTIONAL_FIELDS]
        if unknown:
            raise HsawError("HSAW_ITEM_INVALID", f"unknown field(s) {unknown}", field=f"{f}.{unknown[0]}", expected="only the documented fields")
        cat, sev, disp = item["category"], item["severity"], item["disposition"]
        if cat not in CATEGORIES:
            raise HsawError("HSAW_ITEM_INVALID", f"category {cat!r}", field=f"{f}.category", expected=list(CATEGORIES))
        if sev not in SEVERITIES:
            raise HsawError("HSAW_ITEM_INVALID", f"severity {sev!r}", field=f"{f}.severity", expected=list(SEVERITIES))
        if disp not in DISPOSITIONS:
            raise HsawError("HSAW_ITEM_INVALID", f"disposition {disp!r}", field=f"{f}.disposition", expected=list(DISPOSITIONS))
        for key in ("title", "description", "classification_rationale", "recommendation"):
            if not _text(item[key]):
                raise HsawError("HSAW_ITEM_INVALID", f"{key} must be non-empty text", field=f"{f}.{key}", expected="non-empty string")
        impacts = item["impact_classes"]
        if not isinstance(impacts, list) or not impacts or any(x not in IMPACTS for x in impacts):
            raise HsawError("HSAW_ITEM_INVALID", "impact_classes must be a non-empty list from the impact set", field=f"{f}.impact_classes", expected=list(IMPACTS))
        refs = item["evidence_refs"]
        if not isinstance(refs, list) or not refs or not all(_text(r) for r in refs):
            raise HsawError("HSAW_ITEM_INVALID", "evidence_refs must be a non-empty list of addresses", field=f"{f}.evidence_refs",
                            expected="proc: | work: | artifact: | input: | evidence:sources | host: addresses")
        for r in refs:
            if not ref_ok(r):
                raise HsawError("HSAW_ITEM_INVALID", f"evidence_ref {r!r} does not resolve in this run: use an address of this run - proc:_proc/<file>, "
                                f"input:<node>@<visit>[#path], artifact:<n>, work:<file>, host:report | host:message[n] | host:explain, evidence:sources; "
                                f"a program file or a step name is not an address (alpha.89)", field=f"{f}.evidence_refs",
                                expected="an address that exists: proc:_proc/<file>, work:<file>, artifact:<n>, input:<node>@<visit>, evidence:sources, host:report|message[n]|explain")
        for key in ("classification_uncertain", "reversible"):
            if not isinstance(item[key], bool):
                raise HsawError("HSAW_ITEM_INVALID", f"{key} must be boolean", field=f"{f}.{key}", expected="true | false")
        esc = item["escalated_from"]
        if esc is not None and esc not in SEVERITIES:
            raise HsawError("HSAW_ITEM_INVALID", f"escalated_from {esc!r}", field=f"{f}.escalated_from", expected=[None, *SEVERITIES])
        if cat == "bug":
            missing = [k for k in BUG_FIELDS if k not in item]
            if missing:
                raise HsawError("HSAW_ITEM_INVALID", f"a bug item also needs {missing}", field=f"{f}.{missing[0]}", expected=list(BUG_FIELDS))
            if item["scope"] not in SCOPES:
                raise HsawError("HSAW_ITEM_INVALID", f"scope {item['scope']!r}", field=f"{f}.scope", expected=list(SCOPES))
            files = item["affected_files"]
            if not isinstance(files, list) or not all(_text(x) for x in files):
                raise HsawError("HSAW_ITEM_INVALID", "affected_files must be a list of paths", field=f"{f}.affected_files", expected="array of strings")
            for key in ("touches_sovereignty_toolset", "affects_sovereignty_markers"):
                if not isinstance(item[key], bool):
                    raise HsawError("HSAW_ITEM_INVALID", f"{key} must be boolean", field=f"{f}.{key}", expected="true | false")
            if not _text(item["proposed_fix"]):
                raise HsawError("HSAW_ITEM_INVALID", "proposed_fix must be non-empty text", field=f"{f}.proposed_fix", expected="non-empty string")
        if "same_as" in item and not (isinstance(item["same_as"], str) and ID_RE.match(item["same_as"])):
            raise HsawError("HSAW_ITEM_INVALID", "same_as must be a known item id H-xxxxxxxx", field=f"{f}.same_as", expected="H-<8 hex>")
        reasons = []
        if cat == "doubt" and sev != "critical":
            reasons.append("category doubt is always critical (the human decides intent, authority and scope)")
        if item["reversible"] is False and sev != "critical":
            reasons.append("an irreversible impact is critical")
        if SOVEREIGN_IMPACTS & set(impacts) and sev != "critical":
            reasons.append("authorization / sovereignty / audit / safety impact is critical")
        if cat == "bug" and (item["touches_sovereignty_toolset"] or item["affects_sovereignty_markers"]) and sev != "critical":
            reasons.append("a sovereignty tool or marker impact is critical")
        if sev == "low" and not set(impacts) <= LOW_IMPACTS:
            reasons.append("low allows only documentation / naming / cosmetic impacts")
        if item["classification_uncertain"]:
            if esc is None or RANK[sev] != RANK[esc] + 1:
                reasons.append("classification_uncertain requires escalated_from exactly one level below severity")
        elif esc is not None:
            reasons.append("escalated_from is only for classification_uncertain items")
        if reasons:
            raise HsawError("HSAW_SEVERITY_INCONSISTENT", "; ".join(reasons), field=f"{f}.severity", expected="a severity consistent with the item's own facts (unsure -> one level up)")
        if sev == "critical" and disp not in ("FREEZE_NOW", "HARD_FAIL"):
            raise HsawError("HSAW_DISPOSITION_INCONSISTENT", "critical is FREEZE_NOW or HARD_FAIL - never record-and-continue", field=f"{f}.disposition", expected=["FREEZE_NOW", "HARD_FAIL"])
        if sev == "medium" and disp != "ADVISE":
            raise HsawError("HSAW_DISPOSITION_INCONSISTENT", "medium advises without asking: disposition ADVISE", field=f"{f}.disposition", expected="ADVISE")
        if sev == "medium" and item["recommendation"].strip().lower() == NO_RECOMMENDATION:
            raise HsawError("HSAW_DISPOSITION_INCONSISTENT", "a medium item must carry a recommendation", field=f"{f}.recommendation", expected="a concrete recommendation")
        if sev == "low" and disp != "REPORT":
            raise HsawError("HSAW_DISPOSITION_INCONSISTENT", "low only reports: disposition REPORT", field=f"{f}.disposition", expected="REPORT")
        out.append(item)
    return out


def taxonomy() -> dict:
    """alpha.97 (04 series doc 232 C): the classification the checks above apply, served beside hsaw_item_example - the HSAW refusals of
    production runs were items classified against these rules (low with a behaviour impact, an impact or a scope outside the sets)."""
    return {"impact_classes": list(IMPACTS),
            "critical_when": ["category doubt", "reversible false", "an impact among " + ", ".join(sorted(SOVEREIGN_IMPACTS)),
                              "a bug touching the sovereignty toolset or its markers"],
            "low_only_for": sorted(LOW_IMPACTS),
            "disposition": {"critical": ["FREEZE_NOW", "HARD_FAIL"], "medium": ["ADVISE"], "low": ["REPORT"]},
            "bug_scope": list(SCOPES),
            "unsure": "one level up: classification_uncertain true and escalated_from the level below"}


def freeze_items(items) -> list[dict]:
    return [it for it in (items or []) if isinstance(it, dict) and it.get("disposition") == "FREEZE_NOW"]


def hard_fail_items(items) -> list[dict]:
    return [it for it in (items or []) if isinstance(it, dict) and it.get("disposition") == "HARD_FAIL"]


def check_gate(gate: dict, items: list[dict]) -> None:
    """The five must-haves of an hsaw_doubt gate (doc 180 §3): findings + evidence (the items), the stop / resume boundary, every
    option with its consequence, a recommendation or an honest "none", and the engine's own closing sentence (appended by the engine)."""
    if not _text(gate.get("resume_boundary")):
        raise HsawError("HSAW_GATE_INCOMPLETE", "gate.resume_boundary is required for an hsaw_doubt gate: why execution stops here and where it continues after the answer",
                        field="gate.resume_boundary", expected="non-empty text in the user's language")
    options = gate.get("options") or []
    kinds = {o.get("kind") for o in options}
    if "execute" not in kinds or "cancel" not in kinds:
        raise HsawError("HSAW_GATE_INCOMPLETE", "an hsaw_doubt gate needs at least one execute option (a resumable choice) and one cancel option",
                        field="gate.options", expected="execute + cancel options")
    for i, o in enumerate(options):
        if not _text(o.get("note")):
            raise HsawError("HSAW_GATE_INCOMPLETE", "every option states its consequence in note", field=f"gate.options[{i}].note", expected="non-empty text")
    if any(it["category"] == "bug" for it in freeze_items(items)):
        intents = {o.get("intent") for o in options}
        missing = [x for x in BUG_GATE_INTENTS if x not in intents]
        if missing:
            raise HsawError("HSAW_GATE_INCOMPLETE", f"a bug gate needs options with intents {list(BUG_GATE_INTENTS)} (labels are yours)",
                            field="gate.options", expected=list(BUG_GATE_INTENTS))


def closing_with_sentence(closing: str, language: str | None) -> str:
    sentence = CLOSING["zh" if (language or "").startswith("zh") else "en"]
    text = closing or ""
    return text if sentence in text else (text.rstrip() + (" " if text.strip() else "") + sentence)


def fingerprint(package: str, node: str, item: dict) -> str:
    title = re.sub(r"[\W_]+", "", (item.get("title") or "").lower())
    files = item.get("affected_files") or []
    parts = [package or "", item.get("category") or "", item.get("scope") or "", node.split("/")[-1], title, files[0] if files else ""]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def prepare(package: str, node: str, visit: int, items: list[dict], at: str, ledger_rows: list[dict]) -> dict:
    """Engine-owned identities for validated items: id, fingerprint (same_as resolves to a known ledger entry's fingerprint).
    Returns {"machine": {"items": [...]}, "events": [discovered events]}; the item text is never rewritten."""
    known = {row.get("id"): row.get("fingerprint") for row in ledger_rows if isinstance(row, dict)}
    recorded, events = [], []
    for item in items:
        fp = known.get(item.get("same_as")) or fingerprint(package, node, item)
        base = {"kind": "discovered", "node": node, "visit": visit, "category": item["category"], "severity": item["severity"],
                "disposition": item["disposition"], "title": item["title"], "fingerprint": fp, "at": at}
        base["id"] = "H-" + _digest(base)[:8]
        events.append(base)
        recorded.append(dict(item, id=base["id"], fingerprint=fp))
    return {"machine": {"items": recorded}, "events": events}


def gate_opened_event(node: str, visit: int, question_id: str, item_ids: list[str], at: str) -> dict:
    return {"kind": "gate_opened", "node": node, "visit": visit, "question_id": question_id, "item_ids": list(item_ids), "at": at}


def gate_answered_event(record: dict, question_id: str, resolution: str, chosen: dict | None, answer: str, at: str) -> dict:
    return {"kind": "gate_answered", "node": record.get("node"), "visit": record.get("visit"), "question_id": question_id,
            "resolution_kind": resolution, "chosen_intent": chosen["intent"] if chosen else None,
            "chosen_label": chosen["label"] if chosen else None, "answer": answer, "at": at}


def append_events(index: dict, events: list[dict]) -> list[dict]:
    """Chain events onto index.hsaw_register (seq, prev_sha, sha); append-only."""
    register = index.setdefault("hsaw_register", [])
    for event in events:
        row = dict(event)
        row["seq"] = len(register) + 1
        row["prev_sha"] = register[-1]["sha"] if register else GENESIS
        row["sha"] = _digest({k: v for k, v in row.items() if k != "sha"})
        register.append(row)
    return register


def verify_register(index: dict) -> list[str]:
    problems, prev = [], GENESIS
    for n, row in enumerate(index.get("hsaw_register") or [], 1):
        if not isinstance(row, dict):
            problems.append(f"event {n}: not an object")
            continue
        if row.get("seq") != n:
            problems.append(f"event {n}: seq {row.get('seq')}")
        if row.get("prev_sha") != prev:
            problems.append(f"event {n}: prev_sha mismatch")
        if row.get("sha") != _digest({k: v for k, v in row.items() if k != "sha"}):
            problems.append(f"event {n}: sha mismatch")
        prev = row.get("sha") or ""
    return problems


def summary(index: dict) -> dict:
    counts = {"critical": 0, "medium": 0, "low": 0, "gates": 0}
    for row in index.get("hsaw_register") or []:
        if row.get("kind") == "discovered" and row.get("severity") in counts:
            counts[row["severity"]] += 1
        elif row.get("kind") == "gate_opened":
            counts["gates"] += 1
    return counts


def table_rows(index: dict) -> list[dict]:
    """One row per discovered item with the gate and the human answer it got, for the execution report's machine table."""
    register = index.get("hsaw_register") or []
    opened = {qid: ev for ev in register if ev.get("kind") == "gate_opened" for qid in [ev.get("question_id")]}
    answered = {ev.get("question_id"): ev for ev in register if ev.get("kind") == "gate_answered"}
    rows = []
    for ev in register:
        if ev.get("kind") != "discovered":
            continue
        qid = next((q for q, g in opened.items() if ev.get("id") in (g.get("item_ids") or [])), None)
        ans = answered.get(qid) if qid else None
        rows.append({"id": ev.get("id"), "category": ev.get("category"), "severity": ev.get("severity"), "node": ev.get("node"),
                     "title": ev.get("title"), "disposition": ev.get("disposition"), "question_id": qid,
                     "answer": (f"{ans.get('answer')} → {ans.get('chosen_label') or ans.get('resolution_kind')}" if ans else None)})
    return rows


def anomaly_lines(machine: dict | None) -> list[str]:
    items = ((machine or {}).get("hsaw") or {}).get("items") or []
    return [f"[hsaw:{it.get('category')}:{it.get('severity')} {it.get('id')}] {it.get('title')}" for it in items]


# --- cross-run ledger: <cache root>/_hsaw/<package>.jsonl, append-only, one discovered event per line, sha-chained -------------

def ledger_path(cache_root: Path, package: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", package or "unknown")
    return Path(cache_root) / LEDGER_DIR / f"{safe}.jsonl"


def ledger_rows(cache_root: Path, package: str) -> list[dict]:
    path = ledger_path(cache_root, package)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append({"corrupt": line[:80]})
    return rows


def project_ledger(raw: bytes, package: str, run_ref: str, events: list[dict]) -> tuple[bytes, int]:
    """Keep the exact prefix and deduplicate only identical run/item discoveries."""
    if raw and not raw.endswith(b'\n'):
        raise OSError('Incomplete HSAW ledger prefix; preserve it')
    try:
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    except (ValueError, UnicodeError) as exc:
        raise OSError('Unreadable HSAW ledger prefix; preserve it') from exc
    prev = GENESIS
    for row in rows:
        if not isinstance(row, dict) or row.get('prev_sha') != prev or row.get('sha') != _digest({k:v for k,v in row.items() if k != 'sha'}):
            raise OSError('HSAW ledger chain changed; preserve it')
        prev = row['sha']
    fields = ('id', 'fingerprint', 'node', 'visit', 'category', 'severity', 'disposition', 'title', 'at')
    lines = []
    for event in events:
        if event.get('kind') != 'discovered':
            continue
        value = {k:event[k] for k in fields if k in event}
        value.update(run=run_ref, package=package)
        matches = [r for r in rows if r.get('run') == run_ref and r.get('id') == value.get('id')]
        if matches:
            if len(matches) != 1 or any(matches[0].get(k) != v for k,v in value.items()):
                raise OSError('HSAW run/item conflict; preserve both observations')
            continue
        row = dict(value, prev_sha=prev)
        row['sha'] = _digest({k:v for k,v in row.items() if k != 'sha'})
        prev = row['sha']
        rows.append(row)
        lines.append(json.dumps(row, ensure_ascii=False).encode('utf-8') + b'\n')
    return raw + b''.join(lines), len(lines)


def ledger_append(cache_root: Path, package: str, run_ref: str, events: list[dict], *, verified_append=False, expected_sha256=None) -> int:
    path = ledger_path(cache_root, package)
    if verified_append:
        from .run_store import FileLock, _regular_path, atomic_write_bytes, sha256_bytes
        if not _regular_path(path):
            raise OSError('HSAW ledger path is not regular')
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(path.with_suffix('.lock')):
            raw = path.read_bytes() if path.exists() else b''
            actual = sha256_bytes(raw) if path.exists() else 'ABSENT'
            if expected_sha256 is not None and actual != expected_sha256:
                raise OSError('HSAW ledger changed after recovery proof')
            projected, count = project_ledger(raw, package, run_ref, events)
            if count:
                atomic_write_bytes(path, projected)
            return count
    from . import write_observation
    write_observation.writing(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ledger_rows(cache_root, package)
    prev = rows[-1].get("sha") if rows and isinstance(rows[-1], dict) and rows[-1].get("sha") else GENESIS
    lines = []
    for event in events:
        if event.get("kind") != "discovered":
            continue
        row = {k: event[k] for k in ("id", "fingerprint", "node", "visit", "category", "severity", "disposition", "title", "at") if k in event}
        row.update(run=run_ref, package=package, prev_sha=prev)
        row["sha"] = _digest({k: v for k, v in row.items() if k != "sha"})
        prev = row["sha"]
        lines.append(json.dumps(row, ensure_ascii=False))
    if lines:
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    return len(lines)


def ledger_status(cache_root: Path, package: str) -> dict:
    """open = distinct fingerprints ever discovered for the package (P1 records discoveries only; no closing state exists yet)."""
    rows = ledger_rows(cache_root, package)
    problems, prev = [], GENESIS
    fingerprints = set()
    for n, row in enumerate(rows, 1):
        if "corrupt" in row:
            problems.append(f"line {n}: corrupt")
            continue
        if row.get("prev_sha") != prev or row.get("sha") != _digest({k: v for k, v in row.items() if k != "sha"}):
            problems.append(f"line {n}: chain")
        prev = row.get("sha") or prev
        if row.get("fingerprint"):
            fingerprints.add(row["fingerprint"])
    return {"rows": len(rows), "open": len(fingerprints), "problems": problems}


def help_text() -> str:
    lines = ["HSAW DOUBT GATE - hsaw_items[] of a node-commit payload (alpha.87, 04 series doc 193)", "",
             "category:   " + " | ".join(CATEGORIES) + "   (doubt = human intent branch, always critical)",
             "severity:   " + " | ".join(SEVERITIES) + "   (the model classifies; unsure -> one level up with classification_uncertain + escalated_from; "
             "alpha.99: a level below what the item's own facts require is raised by the engine, never lowered)",
             "disposition: FREEZE_NOW (critical; this commit carries the gate) | HARD_FAIL (critical; status FAIL, no error route) | ADVISE (medium) | REPORT (low)",
             "impact_classes: " + ", ".join(IMPACTS) + " (authorization / sovereignty / audit / safety => critical; low only documentation / naming / cosmetic)",
             "write check (alpha.92, P1.5): before an irreversible write or delete, read the target first; content there that the program does not "
             "account for = problem / critical (FREEZE_NOW) - do not write",
             "common fields: " + ", ".join(COMMON_FIELDS), "bug fields:    " + ", ".join(BUG_FIELDS), "optional:      same_as (a known H-xxxxxxxx id)",
             "engine-owned (never write): " + ", ".join(ENGINE_FIELDS), "",
             "evidence_refs: addresses of THIS run - proc:_proc/<file> | input:<node>@<visit>[#path] | artifact:<n> | work:<file> | host:report | host:message[n] | host:explain | evidence:sources (never a program file or a step name; alpha.89)", "",
             "gate for FREEZE_NOW: gate {question, options[{kind, label, intent, note}], closing, recommendation | \"none\", advice, explanation, resume_boundary};",
             "  a bug gate also needs options with intents " + " and ".join(BUG_GATE_INTENTS) + "; the engine appends: " + CLOSING["en"], "",
             "example item:", json.dumps(EXAMPLE_ITEM, ensure_ascii=False, indent=2)]
    return "\n".join(lines)


# --- alpha.99 (04 series doc 239 §3.3): repairs instead of HSAW refusals ------------------------------------------------------------
# After a refusal the executor often changed the FACTS to pass (dropped audit / safety, turned "irreversible" into reversible) instead of
# raising the level (isolated caches 42, 43, 49, 64; production 9). The engine now keeps the facts and applies the rules above to them:
# a level only ever goes UP, never down, and a critical item without a gate gets one the engine composes - the human is asked (first rule).
IMPACT_SYNONYMS = {
    "data_loss": "data", "dataloss": "data", "loss_of_data": "data", "privacy": "data", "integrity": "data", "data_integrity": "data",
    "authority": "authorization", "auth": "authorization", "permission": "authorization", "permissions": "authorization",
    "security": "safety", "harm": "safety",
    "compliance": "behavior", "observability": "behavior", "correctness": "behavior", "functionality": "behavior", "function": "behavior",
    "performance": "behavior", "reliability": "behavior", "logic": "behavior", "accuracy": "behavior",
    "interop": "compatibility", "interoperability": "compatibility", "versioning": "compatibility", "version": "compatibility",
    "docs": "documentation", "doc": "documentation", "label": "naming", "name": "naming", "ux": "cosmetic", "ui": "cosmetic",
    "style": "cosmetic", "formatting": "cosmetic", "presentation": "cosmetic",
}
SCOPE_SYNONYMS = {
    "engine": "execute_engine", "execution_engine": "execute_engine", "executor": "execute_engine", "runtime": "execute_engine",
    "package": "target_aiap", "aiap": "target_aiap", "program": "target_aiap", "business_package": "target_aiap", "target": "target_aiap",
    "aisp": "target_aisp", "skill": "target_aisp", "toolset": "sovereignty_toolset", "sovereignty_tools": "sovereignty_toolset",
    "sovereignty_tool": "sovereignty_toolset", "script": "tool", "tools": "tool", "python_tool": "tool",
}
DISPOSITION_RANK = {"REPORT": 0, "ADVISE": 1, "FREEZE_NOW": 2, "HARD_FAIL": 2}
BY_RANK = {0: "low", 1: "medium", 2: "critical"}
NO_ADVICE = {"zh": "（执行者未给出具体建议）", "en": "(the executor gave no concrete recommendation)"}
STANDARD = {
    "zh": {"continue": ("继续执行", "按本节点已完成的结果继续；此问题记入 HSAW 台账，引擎不修改任何东西。"),
           "authorize_fix": ("授权列入修复", "把此问题列入修复清单，经 Creator 进化或发版另行处理；本节点按已完成的结果继续。"),
           "not_a_defect": ("这不是缺陷", "记为非缺陷；本节点按已完成的结果继续。"),
           "cancel": ("取消本次运行", "运行在此结束，之后的节点不再执行；已完成的记录保留。"),
           "boundary": "执行停在节点「{node}」本次提交之前；你回答后，从本节点按你的选择继续。",
           "question": "节点「{node}」发现需要你决定的问题：{titles}",
           "explanation": "{descriptions}",
           "advice": "执行者的建议：{recommendations}（引擎没有推荐选项，由你决定）",
           "note": "选择后按此继续：{label}"},
    "en": {"continue": ("Continue", "Continue with what this node has finished; the finding is recorded in the HSAW ledger and the engine changes nothing."),
           "authorize_fix": ("Authorize a fix", "List the finding for a fix through a Creator evolution or a release, handled separately; this node continues with what it finished."),
           "not_a_defect": ("Not a defect", "Record it as not a defect; this node continues with what it finished."),
           "cancel": ("Cancel this run", "The run ends here and later nodes do not run; what was finished stays recorded."),
           "boundary": "Execution stopped at node {node} before this commit; after your answer it continues at this node as you choose.",
           "question": "Node {node} found something you need to decide: {titles}",
           "explanation": "{descriptions}",
           "advice": "The executor recommends: {recommendations} (the engine recommends no option; the choice is yours)",
           "note": "Continue this way: {label}"},
}


def _lang(language) -> str:
    return "en" if str(language or "zh").lower().startswith("en") else "zh"


def _key(value) -> str:
    return re.sub(r"[\s\-]+", "_", str(value).strip().lower())


def normalize_shape(payload: dict, notes: list | None) -> None:
    """alpha.99 (doc 239 H1 / H2 / H4): impact classes and scopes written as synonyms get the documented name; a field an item does not
    take is removed (resume_boundary moves to the gate when the gate has none); booleans written as "true" / "false" become booleans; the
    two classification flags get their neutral default. Engine-owned fields stay - HSAW_FIELD_REJECTED still refuses them."""
    items = payload.get("hsaw_items")
    if not isinstance(items, list):
        return
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else None
    allowed = set(COMMON_FIELDS + BUG_FIELDS + OPTIONAL_FIELDS + ENGINE_FIELDS)
    changes, dropped = [], []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        f = f"hsaw_items[{i}]"
        for key in [k for k in item if k not in allowed]:
            value = item.pop(key)
            if key == "resume_boundary" and gate is not None and not _text(gate.get("resume_boundary")) and _text(value):
                gate["resume_boundary"] = value
                changes.append(f"{f}.resume_boundary -> gate.resume_boundary")
            else:
                dropped.append({"field": f"{f}.{key}", "value": value})
        impacts = item.get("impact_classes")
        if isinstance(impacts, str):
            impacts = [impacts]
        if isinstance(impacts, list):
            mapped, unknown = [], []
            for x in impacts:
                k = _key(x)
                y = k if k in IMPACTS else IMPACT_SYNONYMS.get(k)
                if y is None:
                    unknown.append(x)
                elif y not in mapped:
                    mapped.append(y)
            if not mapped:
                mapped = ["behavior"]
            if mapped != item.get("impact_classes"):
                changes.append(f"{f}.impact_classes {item.get('impact_classes')!r} -> {mapped!r}" + (f" (not in the set: {unknown!r})" if unknown else ""))
                item["impact_classes"] = mapped
        scope = item.get("scope")
        if isinstance(scope, str) and scope not in SCOPES:
            new = SCOPE_SYNONYMS.get(_key(scope), "tool")
            changes.append(f"{f}.scope {scope!r} -> {new!r}")
            item["scope"] = new
        for key in ("classification_uncertain", "reversible", "touches_sovereignty_toolset", "affects_sovereignty_markers"):
            v = item.get(key)
            if isinstance(v, str) and v.strip().lower() in ("true", "false"):
                item[key] = v.strip().lower() == "true"
                changes.append(f"{f}.{key} {v!r} -> {item[key]}")
        for key, values, fold in (("category", CATEGORIES, str.lower), ("severity", SEVERITIES, str.lower), ("disposition", DISPOSITIONS, str.upper)):
            v = item.get(key)
            if isinstance(v, str) and v not in values and fold(v.strip()) in values:
                item[key] = fold(v.strip())
                changes.append(f"{f}.{key} {v!r} -> {item[key]!r}")
        if "classification_uncertain" not in item:
            item["classification_uncertain"] = False
            changes.append(f"{f}.classification_uncertain -> false")
        if "escalated_from" not in item:
            item["escalated_from"] = None
            changes.append(f"{f}.escalated_from -> null")
    if notes is not None and changes:
        notes.append({"code": "HSAW_ITEM_NORMALIZED", "text": "; ".join(changes) + " (alpha.99: the documented names; see hsaw_taxonomy)"})
    if notes is not None and dropped:
        notes.append({"code": "SHAPE_FIELD_DROPPED", "text": "hsaw item fields the item does not take were removed and kept in machine.dropped_fields (alpha.99): "
                                                             + ", ".join(d["field"] for d in dropped), "fields": dropped})


def implied_level(item: dict) -> str:
    """the lowest level the item's own facts allow, by the rules validate_items applies"""
    impacts = set(item.get("impact_classes") or [])
    if (item.get("category") == "doubt" or item.get("reversible") is False or SOVEREIGN_IMPACTS & impacts
            or (item.get("category") == "bug" and (item.get("touches_sovereignty_toolset") is True or item.get("affects_sovereignty_markers") is True))):
        return "critical"
    return "medium" if impacts - LOW_IMPACTS else "low"


def align_items(items, notes: list | None, language=None) -> list[dict]:
    """alpha.99 (doc 239 H6): the level is the highest of the declared severity, what the facts require and what the declared disposition
    implies - never lower than declared; the disposition follows the level (a declared HARD_FAIL stays HARD_FAIL); the uncertainty flags are
    made consistent; a medium item without a recommendation says so. Returns the changes (also noted)."""
    changed = []
    for i, item in enumerate(items or []):
        if not isinstance(item, dict) or item.get("severity") not in SEVERITIES or item.get("disposition") not in DISPOSITIONS:
            continue
        before = {k: item.get(k) for k in ("severity", "disposition", "classification_uncertain", "escalated_from", "recommendation")}
        rank = max(RANK[item["severity"]], RANK[implied_level(item)], DISPOSITION_RANK[item["disposition"]])
        if item.get("classification_uncertain") is True and rank == 0:
            rank = 1   # unsure means one level up; low has no level below it
        level = BY_RANK[rank]
        item["severity"] = level
        if level == "critical":
            item["disposition"] = "HARD_FAIL" if item["disposition"] == "HARD_FAIL" else "FREEZE_NOW"
        else:
            item["disposition"] = "ADVISE" if level == "medium" else "REPORT"
        if item.get("classification_uncertain") is True:
            item["escalated_from"] = BY_RANK[rank - 1]
        elif item.get("escalated_from") is not None:
            item["escalated_from"] = None
        if level == "medium" and str(item.get("recommendation") or "").strip().lower() in ("", NO_RECOMMENDATION):
            item["recommendation"] = NO_ADVICE[_lang(language)]
        after = {k: item.get(k) for k in ("severity", "disposition", "classification_uncertain", "escalated_from", "recommendation")}
        if after != before:
            changed.append({"item": i, "title": item.get("title"), "declared": before, "recorded": after})
    if notes is not None and changed:
        raised = [c for c in changed if c["declared"]["severity"] != c["recorded"]["severity"]]
        if raised:
            notes.append({"code": "HSAW_SEVERITY_RAISED",
                          "text": "; ".join(f"hsaw_items[{c['item']}] {c['declared']['severity']}/{c['declared']['disposition']} -> "
                                            f"{c['recorded']['severity']}/{c['recorded']['disposition']} ({c['title']})" for c in raised)
                                  + " (alpha.99: the item's own facts require it - irreversible, an authorization / sovereignty / audit / safety "
                                    "impact, a behaviour impact above low; levels only go up)"})
        rest = [c for c in changed if c not in raised]
        if rest:
            notes.append({"code": "HSAW_ITEM_NORMALIZED", "text": "; ".join(f"hsaw_items[{c['item']}] {c['declared']} -> {c['recorded']}" for c in rest)
                                                              + " (alpha.99: disposition and flags made consistent with the level)"})
    return changed


def normalize_refs(items, ref_ok, file_ref, defaults: list[str], notes: list | None) -> None:
    """alpha.99 (doc 239 H3): an evidence reference that is not an address of this run is turned into one: an existing absolute file
    becomes file:<path> (the engine hashes it), a program file named first in a sentence becomes file:<that file> and the sentence a note:,
    anything else a note:<text>; no reference at all takes this node's own Report / Explain, or note: saying none was given."""
    changes = []
    for i, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        refs = item.get("evidence_refs")
        if isinstance(refs, str):
            refs = [refs]
        if not isinstance(refs, list):
            refs = []
        out = []
        for r in refs:
            if not _text(r):
                continue
            if ref_ok(r):
                out.append(r)
                continue
            converted = file_ref(r)
            out.extend(converted)
            changes.append(f"hsaw_items[{i}].evidence_refs {str(r)[:80]!r} -> {converted}")
        if not out:
            out = list(defaults)
            changes.append(f"hsaw_items[{i}].evidence_refs (none) -> {out}")
        item["evidence_refs"] = out
    if notes is not None and changes:
        notes.append({"code": "HSAW_EVIDENCE_NORMALIZED", "text": "; ".join(changes) + " (alpha.99: addresses of this run; file: is hashed by the engine, note: is the executor's own words)"})


def _standard_option(intent: str, lang: str, alias: str) -> dict:
    label, note = STANDARD[lang][intent]
    return {"kind": "cancel" if intent == "cancel" else "execute", "label": label, "intent": intent, "note": note, "aliases": [alias]}


def compose_gate(items: list[dict], node: str, language=None) -> dict:
    """alpha.99 (doc 239 H7): the hsaw_doubt gate for FREEZE_NOW items that came without one - findings, evidence (the items), the stop /
    resume boundary, every option with its consequence, no recommendation of the engine's own, and the engine's closing sentence."""
    lang = _lang(language)
    frozen = [it for it in items if it.get("disposition") == "FREEZE_NOW"] or list(items)
    s = STANDARD[lang]
    options = [_standard_option("continue", lang, "1")]
    if any(it.get("category") == "bug" for it in frozen):
        options += [_standard_option("authorize_fix", lang, "2"), _standard_option("not_a_defect", lang, "3")]
    options.append(_standard_option("cancel", lang, str(len(options) + 1)))
    sep = "；" if lang == "zh" else "; "
    return {"question": s["question"].format(node=node, titles=sep.join(str(it.get("title") or "") for it in frozen)),
            "options": options, "closing": CLOSING[lang], "recommendation": NO_RECOMMENDATION,
            "explanation": s["explanation"].format(descriptions=sep.join(f"{it.get('description')}（{it.get('classification_rationale')}）" if lang == "zh"
                                                                         else f"{it.get('description')} ({it.get('classification_rationale')})" for it in frozen)),
            "advice": s["advice"].format(recommendations=sep.join(str(it.get("recommendation") or "") for it in frozen)),
            "resume_boundary": s["boundary"].format(node=node)}


def complete_gate(gate: dict, items: list[dict], node: str, language=None, notes: list | None = None) -> None:
    """alpha.99 (doc 239 H8): what check_gate requires and the model left out, the engine writes in its standard words - the resume
    boundary, an execute and a cancel option, each option's consequence, and for a bug the authorize_fix / not_a_defect options."""
    lang = _lang(language)
    added = []
    if not _text(gate.get("resume_boundary")):
        gate["resume_boundary"] = STANDARD[lang]["boundary"].format(node=node)
        added.append("resume_boundary")
    options = gate.setdefault("options", [])
    intents = {o.get("intent") for o in options}
    labels = {o.get("label") for o in options}
    aliases = {a.lower() for o in options for a in (o.get("aliases") or [])}

    def add(intent):
        opt = _standard_option(intent, lang, str(len(options) + 1))
        if intent in BUG_GATE_INTENTS:
            titles='; '.join(str(it.get('title') or it.get('id') or 'unnamed') for it in freeze_items(items) if it.get('category')=='bug')
            opt['note'] += (' 对象：' if lang=='zh' else ' Applies to: ') + titles
            opt['note'] += ('；不替代尚未回答的业务选择，不授权修改程序。' if lang=='zh' else '; does not answer pending business choices or authorize program edits.')
        if opt["intent"] in intents:
            opt["intent"] = f"{intent}_run" if intent != "cancel" else "cancel"
        if opt["label"] in labels:
            opt["label"] += " (HSAW)"
        opt["aliases"] = [a for a in opt["aliases"] if a.lower() not in aliases]
        options.append(opt)
        added.append(f"option {intent}")

    kinds = {o.get("kind") for o in options}
    if "execute" not in kinds:
        add("continue")
    if "cancel" not in kinds:
        add("cancel")
    if any(it.get("category") == "bug" for it in freeze_items(items)):
        present = {o.get("intent") for o in options}
        for intent in BUG_GATE_INTENTS:
            if intent not in present:
                add(intent)
    for i, o in enumerate(options):
        if not _text(o.get("note")):
            o["note"] = STANDARD[lang]["cancel"][1] if o.get("kind") == "cancel" else STANDARD[lang]["note"].format(label=o.get("label"))
            added.append(f"options[{i}].note")
    if notes is not None and added:
        notes.append({"code": "HSAW_GATE_COMPLETED", "text": f"the hsaw_doubt gate lacked {added}; the engine wrote them in its standard words (alpha.99)"})


def completed_gate(gate: dict, items: list[dict], node: str, language=None, notes: list | None = None) -> dict:
    """Same completion for commit and read-only proposals; never changes the caller's menu."""
    import copy
    result = copy.deepcopy(gate)
    complete_gate(result, items, node, language, notes)
    return result
