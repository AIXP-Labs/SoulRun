"""node-commit: submit the model's payload for the current node.

Usage
  python python_tools/node_commit.py --cache-dir DIR --node NAME (--payload-stdin | --payload-file FILE)

--payload-stdin is the normal path (pipe a here-string / heredoc); --payload-file is for hosts that
cannot pipe and for the sanctioned large-payload fallback <cache_dir>/_payload.<node>.json (alpha.31 E2); it must
not be used to park payloads in the workspace (doc 07 §2). The fallback file is deleted after a successful commit
and kept when the commit is rejected or fails, so the named field can be fixed in place and the same path
resubmitted (alpha.32 E2; the result carries payload_file when the file was kept).

Result JSON: status COMMITTED | WAITING_USER | REJECTED (errors[] with code/field/expected/example/message, help).
Exit 0 for COMMITTED / WAITING_USER, 1 for REJECTED, 2 for usage/engine errors.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import engine_core  # noqa: E402
from lib import model_view  # noqa: E402
from lib import reply_io  # noqa: E402
from lib import stop_state  # noqa: E402
from lib.run_store import RunStoreError  # noqa: E402


SUCCESS_STATUSES = ("COMMITTED", "WAITING_USER")
STDIN_IDLE_SECONDS = 10.0   # docs/05SoulRun 87: --payload-stdin gives up when no byte arrives for this long
WORK_DIR = "_work"   # alpha.43 C1; alpha.49 (doc 103): a payload file put directly under it is settled like the sanctioned fallback file


def _is_cache_payload(payload_path: Path, cache_dir: Path) -> bool:
    """The sanctioned fallback file: <cache_dir>/_payload.<node>.json (alpha.31 E2) - or, since alpha.49 (doc 103), any .json placed
    directly under <cache_dir>/_work/ (production cache/72 left eight such payload files behind); files elsewhere are never touched."""
    try:
        parent, root = payload_path.resolve().parent, cache_dir.resolve()
        if payload_path.suffix != ".json":
            return False
        if parent == root:
            return payload_path.name.startswith("_payload.")
        return parent == root / WORK_DIR
    except OSError:
        return False


def _discard_cache_payload(payload_path: Path, cache_dir: Path) -> None:
    """Delete the sanctioned fallback file (and nothing else); a missing file is not an error."""
    try:
        if _is_cache_payload(payload_path, cache_dir):
            payload_path.unlink()
    except OSError:
        pass


def _settle_cache_payload(payload_path: Path, cache_dir: Path, status: str | None, *, accepted=True) -> str | None:
    """alpha.32 E2: the fallback file is deleted only after a successful commit (COMMITTED / WAITING_USER). A rejected or
    failed commit keeps it - the model fixes the named field in place and resubmits with the same --payload-file path
    (cache/30: a 30k payload was rewritten from scratch because alpha.31 deleted the file on read). Returns the note to put
    into the result when the file was kept, else None."""
    if accepted and status in SUCCESS_STATUSES:
        _discard_cache_payload(payload_path, cache_dir)
        return None
    if _is_cache_payload(payload_path, cache_dir) and payload_path.exists():
        if not accepted:
            return f'{payload_path.name} kept, not accepted: resolve the integrity gate, then recover pending_payload_refs; do not replay completed side effects.'
        return (f"{payload_path.name} kept: fix the named field(s) and their dependent facts in that file; resubmit with the same --payload-file path "
                "(preserve unrelated content; never rewrite accepted caches or earlier public output)")
    return None


def _read_payload_stdin(stream, idle: float):
    """docs/05SoulRun 87 (run 7: a heredoc bound to the next command left node_commit waiting on stdin for 120 s, then in the
    background, where an EOF could have handed it nothing): (text, None) once stdin closes, or (None, code) when no byte arrived for
    `idle` seconds - PAYLOAD_STDIN_EMPTY before the first byte, PAYLOAD_STDIN_INCOMPLETE after some. A daemon thread does the
    blocking os.read (Windows has no select() on pipes) and is left behind on a timeout; an in-memory stream is read at once."""
    import os
    import queue
    import threading
    if stream is None:   # no stdin at all (a windowless start): nothing can arrive
        return '', None
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return stream.read(), None
    chunks = queue.Queue()

    def pump():
        try:
            while chunk := os.read(fd, 65536):
                chunks.put(chunk)
        except OSError:
            pass
        chunks.put(b'')

    threading.Thread(target=pump, name='payload-stdin', daemon=True).start()
    data = bytearray()
    while True:
        try:
            chunk = chunks.get(timeout=idle)
        except queue.Empty:
            return None, 'PAYLOAD_STDIN_INCOMPLETE' if data else 'PAYLOAD_STDIN_EMPTY'
        if not chunk:
            text = data.decode(getattr(stream, 'encoding', None) or 'utf-8')
            return text.replace('\r\n', '\n').replace('\r', '\n'), None   # as text-mode stdin read it
        data += chunk


def _main(argv=None) -> int:
    if "--hsaw-help" in (argv if argv is not None else sys.argv[1:]):   # alpha.87 (doc 193): the hsaw_items field table and example
        from lib import hsaw_gate
        print(hsaw_gate.help_text())
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--node", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--payload-stdin", action="store_true")
    src.add_argument("--payload-file")
    ap.add_argument("--agent-ticket", help="sub-agent only: the dispatch ticket from the bootstrap (doc 10 §3.3)")
    ap.add_argument('--interpret-human-reply', action='store_true', help='Only interpret a declared conditional business reply; no business commit.')
    args = ap.parse_args(argv)
    payload_path = None
    if args.payload_stdin:
        text, problem = _read_payload_stdin(sys.stdin, STDIN_IDLE_SECONDS)
        if problem or not text.strip():   # docs/05SoulRun 87: nothing to commit - stop before the engine; the run is untouched
            problem = problem or 'PAYLOAD_STDIN_EMPTY'
            said = 'stopped after part of it' if problem == 'PAYLOAD_STDIN_INCOMPLETE' else 'carried nothing'
            print(json.dumps(dict(status='ERROR', errors=[dict(code=problem, field='payload_stdin', message=(
                f'standard input {said} within {STDIN_IDLE_SECONDS:g} s of quiet or before it closed; nothing was submitted and the run is unchanged'))],
                help='Pipe the payload into this same command (a quoted heredoc / here-string bound to node_commit, not to a later command), '
                     'or write it to a .json under <cache_dir>/_work/ and submit with --payload-file <that file>.'), ensure_ascii=False))
            return 2
    else:
        payload_path = Path(args.payload_file)
        try:
            text = payload_path.read_text(encoding="utf-8")   # alpha.32 E2: settled after the commit result is known
        except (OSError,UnicodeError) as exc:
            print(json.dumps(dict(status='ERROR',errors=[dict(code='PAYLOAD_FILE_UNREADABLE',message=str(exc),field='payload_file')]),ensure_ascii=False))
            return 2
    text = text.lstrip("\ufeff")   # doc 16 B-3: PowerShell-written payload files carry a UTF-8 BOM (QQQ cache/12 FetchData)
    from lib import write_observation, tool_faults
    write_observation.bind_request(node=args.node, agent_ticket=args.agent_ticket,
                                  interpretation=bool(args.interpret_human_reply), payload_text=text)
    try:
        version_store=engine_core.RunStore(args.cache_dir)
        if version_store.exists():engine_core.program_guard.assert_run_version(version_store.read_index())
        fence = stop_state.stop_fence(args.cache_dir)   # alpha.104 (doc 256 E3)
        if fence is not None:
            raise engine_core.EngineError("RUN_STOPPED_BY_HUMAN", fence["message"], field="cache_dir",
                                          expected="the human's next message (stop_decision.py in a judge turn)")
        from lib import tool_faults
        strategy = tool_faults.consume_retry(args.cache_dir)
        if strategy == 'ACCEPTED_REPLY':
            tool_faults.replay_reply(args.cache_dir)
            return 0
        tool_faults.require_clear(args.cache_dir,version_store.read_index())
        if strategy is None:
            from lib import accepted_replies
            with version_store.lock():
                current_index = version_store.read_index()
                tool_faults.require_clear(args.cache_dir, current_index)
                saved = accepted_replies.identical(args.cache_dir, current_index, write_observation.request())
            if saved is not None:
                print(json.dumps(saved, ensure_ascii=False, indent=2))
                return 0
        if strategy == 'FORWARD_ORPHAN_COMMIT':
            from lib import partial_commit
            result = partial_commit.recover(args.cache_dir)
        elif args.interpret_human_reply:
            if args.agent_ticket:
                raise engine_core.EngineError('HUMAN_INTERPRETATION_ACTOR_INVALID', 'Interpretation precedes dispatch; the main executor submits it without an agent ticket.')
            result = engine_core.interpret_human_reply(args.cache_dir, text, node=args.node)
        else:
            result = engine_core.commit(args.cache_dir, args.node, text, agent_ticket=args.agent_ticket, next_plan=True)
    except (engine_core.EngineError, RunStoreError) as exc:
        from lib import tool_faults
        diagnostic=tool_faults.capture(args.cache_dir,'node_commit',exc) if isinstance(exc,engine_core.EngineError) else {}
        if isinstance(exc,RunStoreError) and exc.code=='READ_BACK_MISMATCH':
            diagnostic=tool_faults.capture(args.cache_dir,'node_commit',engine_core.EngineError('ENGINE_UNEXPECTED_EXCEPTION',str(exc),example={'original_code':exc.code}))
        code = getattr(exc, "code", "ENGINE_ERROR")
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        out = {"status": "ERROR", "errors": [{"code": code, "message": detail}],**diagnostic}
        if payload_path is not None:
            note = _settle_cache_payload(payload_path, Path(args.cache_dir), "ERROR")   # alpha.32 E2: the file stays
            if note:
                out["payload_file"] = note
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2
    if result.get('status') in SUCCESS_STATUSES and result.get('submission_accepted') is not False:
        from lib import write_observation
        write_observation.accepted(result, kind='commit', node=args.node)
    out = model_view.lean(result)   # alpha.28 B4: references, not block text
    from lib import tool_faults
    for error in result.get('errors',[]):
        if error.get('code') in tool_faults.policy()['non_retryable']:
            out.update(tool_faults.capture(args.cache_dir,'node_commit',engine_core.EngineError(error['code'],error.get('message',''),
                field=error.get('field'),expected=error.get('expected'),example=error.get('example'))))
    if payload_path is not None:
        note = _settle_cache_payload(payload_path, Path(args.cache_dir), result.get("status"), accepted=result.get('submission_accepted') is not False)
        if note:
            out["payload_file"] = note
    rendered = reply_io.render(out, args.cache_dir, "commit", args.node)   # alpha.48 C2': echoed under _work/replies/, decisive fields first
    reply_io.emit(rendered)
    if result.get("status") == "REJECTED":
        reply_io.keep_rejected_payload(args.cache_dir, rendered, text)   # alpha.58: the rejected bytes stay beside the reply
    return 1 if result.get("status") == "REJECTED" else 0

def main(argv=None) -> int:
    from lib import write_observation, tool_faults
    args=list(argv if argv is not None else sys.argv[1:])
    cache=tool_faults.cli_args(args).cache_dir
    token=write_observation.begin('node_commit',cache) if cache else None
    try:
        return _main(argv)
    except Exception as exc:
        from lib import tool_faults
        args=list(argv if argv is not None else sys.argv[1:])
        parsed=tool_faults.cli_args(args);cache=parsed.cache_dir
        if cache and tool_faults.recover_reply(cache,'node_commit',exc):return 0
        out=tool_faults.unexpected(cache,'node_commit',exc)
        if parsed.payload_file:
            out['payload_file']='Payload retained: '+parsed.payload_file
        print(json.dumps(out,ensure_ascii=False,indent=2))
        return 2
    finally:
        if token is not None:write_observation.end(token)


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
