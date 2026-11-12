"""Host-compatibility module (soulbot.engine_hooks imports `user_gate_audit.audit`).

In v7 every human gate is minted by node_commit from a machine-detected gate source and answered
only through gate_answer; the audit trail is _gate.<question_id>.json plus the index gate group.
The host's sweep is only triggered by the v6 index field `user_gates_presented`, which v7 never
writes, so this function is kept for import compatibility and reports N_A honestly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.run_store import RunStore, RunStoreError  # noqa: E402


def audit(cache_dir: str, aiap_name: str, node: str, entry_path: str) -> dict:
    store = RunStore(cache_dir)
    try:
        index = store.read_index()
    except RunStoreError as exc:
        return {"status": "N_A", "reason": f"v7 index unreadable: {exc}"}
    gates = [h for h in index["gate"]["history"] if h["node"] == node]
    return {"status": "N_A", "reason": "v7 gates are machine-minted and answered through gate_answer; see _gate.<question_id>.json",
            "node": node, "gates": [{"question_id": h["question_id"], "resolution_kind": h["resolution_kind"]} for h in gates]}
