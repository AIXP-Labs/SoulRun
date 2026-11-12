"""A child process for tests that need the bundled engine's own entry points in a process of their own: a printed reply
that fails, an Engine call with crafted facts. Never imported by the tests themselves (the engine's top-level names
must not enter the test process); run as ``python engine_child.py <mode> <result.json> [arguments]``.

Modes
  commit-failing-print <result> <cache_dir> <node> <fail_status>
      node_commit.main with the payload on standard input; printing a reply whose status is <fail_status> raises
      OSError(22) as a closed pipe does. Writes {"exit": ..., "printed": [...]}.
  proof <result> <cache_dir> <observation.json>
      tool_faults.rejected_reply_proof for the given write facts. Writes {"proof": ...}.
  terminate <result> <cache_dir>
      engine_core.terminate_run as a human ends a run. Writes {"result": ...}.
  next-cache-dir <result> <root>
      prepare_cache.next_cache_dir. Writes {"name": ...}.
  revision <result> <version>...
      runtime_identity.revision_match. Writes {"matches": {version: number or null}}.
"""
from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path


def tools_dir() -> Path:
    from soulrun import host
    return Path(host.program_root()) / "python_tools"


def main() -> int:
    mode, result_path = sys.argv[1], Path(sys.argv[2])
    sys.path.insert(0, str(tools_dir()))
    out: dict = {}
    if mode == "commit-failing-print":
        cache_dir, node, fail_status = sys.argv[3], sys.argv[4], sys.argv[5]
        import node_commit
        original, printed = builtins.print, []

        def failing(*args, **kwargs):
            text = args[0] if args else ""
            try:
                status = json.loads(text).get("status")
            except (TypeError, ValueError, AttributeError):
                status = None
            printed.append(status)
            if status == fail_status:
                raise OSError(22, "Invalid argument")
            return original(*args, **kwargs)

        builtins.print = failing
        try:
            code = node_commit.main(["--cache-dir", cache_dir, "--node", node, "--payload-stdin"])
        finally:
            builtins.print = original
        out = {"exit": code, "printed": printed}
    elif mode == "proof":
        from lib import tool_faults
        observed = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
        out = {"proof": tool_faults.rejected_reply_proof(sys.argv[3], observed)}
    elif mode == "terminate":
        from lib import engine_core
        out = {"result": engine_core.terminate_run(sys.argv[3], kind="human_termination", by="human",
                                                   reason="ended by the human in a test")}
    elif mode == "next-cache-dir":
        import prepare_cache
        out = {"name": prepare_cache.next_cache_dir(Path(sys.argv[3])).name}
    elif mode == "revision":
        from lib import runtime_identity
        matches = {}
        for version in sys.argv[3:]:
            m = runtime_identity.revision_match(version)
            matches[version] = int(m.group(1)) if m else None
        out = {"matches": matches}
    else:
        raise SystemExit(f"unknown mode {mode}")
    result_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
