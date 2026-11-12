"""stop-decision: the executor's judgement on the human's message after a Stop (alpha.104, 04 series doc 255 final_plan §3.2, doc 256 E2).

Usage
  python python_tools/stop_decision.py --cache-dir DIR --stop-id s-N --judge-id jK --decision continue|ask
        [--recommendation continue_run|new_task|end_run|none] [--explanation TEXT] [--advice TEXT] --reason TEXT

Called by the model in a [RUN STOPPED - JUDGE] turn, and by nothing else. Never writes _host_lifecycle.json: it archives every attempt in
_stop/<stop_id>.<judge_id>.json, writes _public/menu.stop-N.txt on `ask`, and on `continue` records the pause (HUMAN_STOP_WAIT) in the
index through the engine lock. Result JSON: status CONTINUE (public_note, next_action) | GATE (public_block_ref) | REJECTED (code
STOP_NOT_PENDING | STOP_DECISION_NOT_ALLOWED | STOP_GATE_FIELDS, with allowed / triggers / field / expected).
Exit 0 for CONTINUE / GATE, 1 for REJECTED, 2 for usage / engine errors (JSON on stdout in every case).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import engine_core, stop_flow  # noqa: E402
from lib.run_store import RunStoreError  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--stop-id", required=True)
    ap.add_argument("--judge-id", required=True)
    ap.add_argument("--decision", required=True, choices=("continue", "ask"))
    ap.add_argument("--recommendation", choices=("continue_run", "new_task", "end_run", "none"), default=None)
    ap.add_argument("--explanation", default=None)
    ap.add_argument("--advice", default=None)
    ap.add_argument("--reason", required=True, help="why this decision, in the user's language")
    args = ap.parse_args(argv)
    if not args.reason.strip():
        ap.error("--reason must not be empty")
    try:
        result = stop_flow.decide_stop(args.cache_dir, args.stop_id, args.judge_id, args.decision, recommendation=args.recommendation,
                                       explanation=args.explanation, advice=args.advice, reason=args.reason)
    except (engine_core.EngineError, RunStoreError) as exc:
        code = getattr(exc, "code", "ENGINE_ERROR")
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        print(json.dumps({"status": "ERROR", "errors": [{"code": code, "message": detail}]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") == "REJECTED" else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
