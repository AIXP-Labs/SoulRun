"""Delivery observation for the v7 engine (host contract: soulbot.engine_hooks after_agent_callback).

  observe_persisted_response(cache_dir, public_text, thought_accounting=None,
                             entry_observation_text=None, message_boundaries=None) -> dict

v7 records facts and issues no verdicts (doc 01 §6.2: no observer for the A-mode transition;
doc 02 §8). What is recorded, append-only in _delivery.json: sizes, sha256 of the delivered
message text, thought accounting as given by the host, whether the write-once final answer
appears verbatim inside the delivered text. Thought content itself is never stored.
alpha.21 (doc 41 §7.1): while the run is WAITING_USER, the record also carries gate_delivery; when the
menu block written for the waiting gate (or its question and every option label) appears in the
delivered text, engine_core.mark_delivered stamps delivered_at so the answer deducts the human wait.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.run_store import RunStore, RunStoreError, atomic_write_bytes, dumps, now_iso, sha256_bytes  # noqa: E402
from lib import engine_core, menu_history, dispatch_publication  # noqa: E402

DELIVERY_FILE = "_delivery.json"


_WS_RE = re.compile(r"\s+")
_PUBLIC_REF = re.compile(r"⟦engine:(?P<cache>\d{1,9})/(?P<file>[^⟧]{1,260})⟧")
_REF_NOTE = re.compile(r"（[^）]*）|\([^)]*\)|[\s\u3000]+")
_PUBLIC_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,200}\.txt")
_PREFIXES = ('plan.', 'pause.', 'node.', 'menu.', 'final_answer.txt', 'evidence.txt', 'ended.txt')


def _reference_projection(store, raw, final, final_block, evidence):
    """Reproducible local projection, never a claim that the host or DOM displayed it."""
    unresolved, loaded = [], {}

    def resolve(match):
        token = match.group(0)
        name = _REF_NOTE.sub('', match['file'])
        path = store.public_dir / name
        try:
            if (match['cache'] != store.cache_dir.name or not _PUBLIC_NAME.fullmatch(name)
                    or '..' in name or not name.startswith(_PREFIXES)
                    or not path.resolve().is_relative_to(store.public_dir.resolve())
                    or path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024):
                raise ValueError('unresolved or unsafe reference')
            if name not in loaded:
                loaded[name] = path.read_text(encoding='utf-8')
            return '\n' + loaded[name].strip('\n') + '\n'
        except (OSError, UnicodeError, ValueError):
            unresolved.append(token)
            return token

    text = _PUBLIC_REF.sub(resolve, raw)
    return dict(basis='same_cache_reference_projection_not_host_delivery', chars=len(text),
                sha256=sha256_bytes(text.encode('utf-8')), resolved_files=len(loaded),
                unresolved_references=list(dict.fromkeys(unresolved)),
                final_answer_verbatim=(final.rstrip() in text) if final else None,
                final_block_verbatim=(final_block.strip() in text) if final_block else None,
                evidence_block_verbatim=(evidence.strip() in text) if evidence else None,
                host_delivery_verified=False, dom_verified=False)


def _ref(store: RunStore, name: str) -> str:
    """alpha.27 R1: the reference line the model presents instead of a public block (render.ref_line, kept local)."""
    return engine_core._ref(store, name)


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def _observe_gate_delivery(store: RunStore, public_text: str) -> dict | None:
    """alpha.21 (doc 41 §7.1). Basis menu_verbatim: the _public/menu.<qid>.txt block is inside the delivered text
    (whitespace-normalised); basis menu_options: the gate question and every option label are. Either stamps
    delivered_at through engine_core.mark_delivered (idempotent; never raises into the host)."""
    try:
        index = store.read_index()
    except RunStoreError:
        return None
    qid = (index.get("gate") or {}).get("question_id")
    if not qid:
        return None
    result = {"question_id": qid, "observed": False, "basis": None, "delivered_at": (index.get("gate") or {}).get("delivered_at")}
    text = _norm(public_text)
    basis = None
    try:
        menu = (store.public_dir / f"menu.{qid}.txt").read_text(encoding="utf-8")
    except OSError:
        menu = ""
    try:
        refs = menu_history.current_refs(store.cache_dir, f"menu.{qid}.txt")
    except (RunStoreError, OSError, ValueError) as exc:
        return dict(result, error=str(exc))
    if menu and _norm(menu) in text:
        basis = "menu_verbatim"
    elif any(ref in (public_text or "") for ref in refs):
        basis = "menu_ref"   # alpha.27 R1: the reference line stands for the menu; the host expands it
    else:
        try:
            gate = store.read_json(store.gate_path(qid))
        except RunStoreError:
            gate = None
        if not menu_history.version_name(store, f"menu.{qid}.txt") and gate and _norm(gate.get("question") or "") and _norm(gate["question"]) in text \
                and all(_norm(o.get("label") or "") and _norm(o["label"]) in text for o in gate.get("options") or []):
            basis = "menu_options"
    if basis is None:
        return result
    result.update(observed=True, basis=basis)
    if not result["delivered_at"]:
        try:
            from lib import engine_core
            result["delivered_at"] = engine_core.mark_delivered(store.cache_dir, qid)["delivered_at"]
        except Exception as exc:  # noqa: BLE001 - observation must not raise into the host
            result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def observe_persisted_response(cache_dir: str | Path, public_text: str, thought_accounting=None,
                               entry_observation_text=None, message_boundaries=None) -> dict:
    cache_dir = Path(cache_dir)
    store = RunStore(cache_dir)
    final = None
    try:
        final = store.final_answer_path.read_text(encoding="utf-8")
    except OSError:
        pass
    evidence = None
    try:
        evidence = (store.public_dir / "evidence.txt").read_text(encoding="utf-8")
    except OSError:
        pass
    final_block = None
    try:
        final_block = (store.public_dir / "final_answer.txt").read_text(encoding="utf-8")
    except OSError:
        pass
    run_state = None
    index = {}
    try:
        index = store.read_index()
        engine_core.program_guard.assert_run_version(index)
        run_state = index["run_state"]
    except RunStoreError:
        pass
    record = {
        "raw_observation_basis": "raw_model_text_before_reference_expansion",
        "observed_at": now_iso(),
        "run_state": run_state,
        "public_chars": len(public_text or ""),
        "public_sha256": sha256_bytes((public_text or "").encode("utf-8")),
        "entry_observation_chars": len(entry_observation_text or "") if entry_observation_text is not None else None,
        "message_boundaries": len(message_boundaries or []),
        "thought_accounting": dict(thought_accounting) if isinstance(thought_accounting, dict) else None,
        "final_answer_present": final is not None,
        "final_answer_delivered_verbatim": (final.rstrip() in (public_text or "")) if final else None,
        "evidence_block_delivered_verbatim": (evidence.strip() in (public_text or "")) if evidence else None,   # alpha.22 E7
        "final_block_delivered_verbatim": (final_block.strip() in (public_text or "")) if final_block else None,   # alpha.23 R4: human_output_v5 envelope
        "final_ref_delivered": (_ref(store, "final_answer.txt") in (public_text or "")) if final_block else None,   # alpha.27 R1
        "evidence_ref_delivered": (_ref(store, "evidence.txt") in (public_text or "")) if evidence else None,
        "ended_ref_delivered": (_ref(store, "ended.txt") in (public_text or "")) if (store.public_dir / "ended.txt").exists() else None,
    }
    record['reference_projection'] = _reference_projection(store, public_text or '', final, final_block, evidence)
    record["gate_delivery"] = _observe_gate_delivery(store, public_text or "") if run_state == "WAITING_USER" else None
    path = cache_dir / DELIVERY_FILE
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except (OSError, ValueError):
        history = []
    eligible = not (isinstance(thought_accounting, dict)
                    and thought_accounting.get('channel_source') == 'mixed_fallback_all_thought')
    record['dispatch_publication'] = dispatch_publication.observation(store, index, public_text or '', history,
                                                                   message_eligible=eligible)
    history.append(record)
    atomic_write_bytes(path, dumps(history).encode("utf-8"))
    return record
