"""gate-answer: host-only entry for a human's answer to a waiting gate.

Usage
  python python_tools/gate_answer.py --cache-dir DIR --question-id ID (--answer TEXT | --answer-file FILE) [--by host]
  python python_tools/gate_answer.py --cache-dir DIR --question-id ID --mark-delivered

Never called by the model. Result JSON: status ANSWERED | WAITING_USER (invalid answer, menu re-presented)
| ROUTED (confirm rejected with on_error handler) | REJECTED_BY_USER | TERMINATED | DELIVERED | REJECTED.
Exit 0, or 1 for WAITING_USER/REJECTED, 2 for usage/engine errors.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import engine_core  # noqa: E402
from lib.run_store import RunStoreError  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--question-id", required=True)
    ap.add_argument("--answer")
    ap.add_argument("--answer-file")
    ap.add_argument("--mark-delivered", action="store_true")
    ap.add_argument("--by", default="host")
    args = ap.parse_args(argv)
    try:
        if args.mark_delivered:
            result = engine_core.mark_delivered(args.cache_dir, args.question_id)
        else:
            if args.answer is None and not args.answer_file:
                ap.error("--answer or --answer-file is required")
            text = args.answer if args.answer is not None else Path(args.answer_file).read_text(encoding="utf-8")
            result = engine_core.answer_gate(args.cache_dir, args.question_id, text, by=args.by)
    except (engine_core.EngineError, RunStoreError) as exc:
        code = getattr(exc, "code", "ENGINE_ERROR")
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        print(json.dumps({"status": "ERROR", "errors": [{"code": code, "message": detail}]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") in ("WAITING_USER", "REJECTED") else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
