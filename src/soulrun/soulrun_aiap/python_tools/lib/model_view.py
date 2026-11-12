"""alpha.28 B4 (04 series doc 57 §4): the view of a reply that the model reads.

Since alpha.27 every public block travels to the human as one `⟦engine:<cache>/<file>⟧` reference line (R1). The CLI
wrappers print this view, in which the block texts that have a reference are blanked, so the model reads less per turn
and its context grows slower. The Python API keeps the full replies (B mode, tests, hosts); the files are the truth.
"""
from __future__ import annotations

import hashlib
import json

REPORT_CONTEXT_FIELDS = ('node_summaries', 'final_context', 'context', 'prev_node_summary')
REPORT_CONTEXT_FOLD_CHARS = 20000   # alpha.42 E3: a normal run's terminal materials stay complete in one reply (was 6000)


def context_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _report_view(out):
    ia = out.get('input_authority')
    if not isinstance(ia, dict) or 'final_context' not in ia:
        return out
    # Keep small complete replies. Large sections remain readable via a digest-bound, read-only page.
    if sum(len(context_text(ia.get(k))) for k in REPORT_CONTEXT_FIELDS) <= REPORT_CONTEXT_FOLD_CHARS:   # alpha.42 E3
        return out
    ia = dict(ia)
    directory = {}
    for field in REPORT_CONTEXT_FIELDS:
        value = ia.get(field)
        text = context_text(value)
        complete = len(text) <= 1200
        directory[field] = dict(complete=complete, total_chars=len(text),
                                sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())
        if not complete:
            ia[field] = ([{k: r.get(k) for k in ('node', 'visit', 'status', 'degraded_reason')} |
                          {'user_summary': None, 'content_complete': False} for r in value]
                         if field == 'node_summaries' else None)
    directory['read'] = (
        'This is a directory, not a summary. Reuse complete reports already in context; after compaction read missing '
        'main-node user_summary/user_messages via input_refs (list-inputs for earlier nodes), or read this complete section: '
        'next_node.py --cache-dir <same-cache> --read-report-context <field> --context-sha256 <sha256> '
        '[--offset N] [--limit N]. Join JSON pages in order until next_offset=null; no node serve, replay or public output. '
        'Do not synthesize from this directory or a truncated preview. Keep exact key facts, reasoning, conditions and recommendations.')
    ia['report_context'] = directory
    # Critical instructions must survive even if the caller limits tool output again.
    return {k: out[k] for k in ('node', 'payload_rules', 'payload_skeleton') if k in out} | {
        k: (ia if k == 'input_authority' else v) for k, v in out.items()
        if k not in ('node', 'payload_rules', 'payload_skeleton')}

_TEXT_FOR_REF = (
    ("public_plan", "public_plan_ref"),
    ("public_block", "public_block_ref"),
    ("final_answer_block", "final_answer_ref"),
    ("final_answer", "final_answer_ref"),
    ("evidence_block", "evidence_ref"),
    ("error_report", "error_report_ref"),
    ("public_plan_next", "public_plan_next_ref"),
)


def lean(reply):
    """A shallow copy of `reply` whose referenced block texts are None; nested `gate` and `next_plan` are leaned too."""
    if not isinstance(reply, dict):
        return reply
    out = dict(reply)
    for text_key, ref_key in _TEXT_FOR_REF:
        if out.get(ref_key) and out.get(text_key) is not None:
            out[text_key] = None
    gate = out.get("gate")
    if isinstance(gate, dict) and gate.get("public_prompt_ref") and gate.get("public_prompt") is not None:
        out["gate"] = dict(gate, public_prompt=None)
    if isinstance(out.get("next_plan"), dict):
        out["next_plan"] = lean(out["next_plan"])
    return _report_view(out)
