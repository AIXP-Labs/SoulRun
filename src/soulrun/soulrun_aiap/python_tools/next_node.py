"""next-node: return the current node of a run (initialising the run on first call).

Usage
  python python_tools/next_node.py --cache-dir DIR [--registry-root DIR ...] [--entry-path PROGRAM]
                                   [--user-message TEXT | --user-message-file FILE] [--session-id ID] [--trace-id ID]
                                   [--workspace-dir DIR] [--json]

Read-only after initialisation except for the node's ready_at/ACTIVE marker (idempotent afterwards).
Exit 0 on success, 2 on usage/engine error (JSON error on stdout).
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
from lib.run_store import RunStore, RunStoreError  # noqa: E402


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--registry-root", action="append", default=[])
    ap.add_argument("--agent-dir", help="agent directory whose aiap/ and aisp/ registries are consulted (runs aiap_list.py / aisp_list.py)")
    ap.add_argument("--entry-path")
    ap.add_argument("--user-message")
    ap.add_argument("--user-message-file")
    ap.add_argument("--session-id")
    ap.add_argument("--trace-id")
    ap.add_argument("--workspace-dir")
    ap.add_argument("--agent-ticket", help="sub-agent only: the dispatch ticket from the bootstrap (doc 10 §3.3)")
    ap.add_argument("--dispatch-abandon", metavar="TICKET", help="main agent only: the spawned sub-agent holding TICKET failed (doc 10 §3.2)")
    ap.add_argument("--reason", help="with --dispatch-abandon: the Agent tool error, verbatim")
    ap.add_argument("--json", action="store_true", help="(default) JSON output")
    reader = ap.add_mutually_exclusive_group()
    reader.add_argument('--diagnostic-report',action='store_true',help='read-only fault/recovery disclosure, even when diagnostics are damaged; never authorize or serve')
    reader.add_argument('--observe-dispatch-return', metavar='TICKET', help='v2 diagnostic: inspect return evidence; local transcripts alone never authorize continuation')
    ap.add_argument('--return-transcript', metavar='PATH', help='only with --observe-dispatch-return: optional existing .claude/projects transcript; never arbitrary payload JSON')
    reader.add_argument('--check-write-target', metavar='PATH', help='optional artifact path check; for program staging/publication use --write-purpose program; read-only, not a filesystem sandbox')
    ap.add_argument('--write-purpose', choices=('artifact', 'program'), help='only with --check-write-target; default artifact; normal business records need no additional preflight call')
    reader.add_argument("--read-input-ref", help="read a complete input using its engine-issued reference; never init/serve")
    reader.add_argument('--read-write-authority', action='store_true', help='opt-in current writer only: actual complete answered gate history; read-only, never a semantic grant; blind/scoped executors forbidden')
    reader.add_argument("--list-inputs", action="store_true", help="read the paginated committed input catalog; never init/serve")
    reader.add_argument("--read-dispatch-bootstrap", metavar="TICKET", help="recover the original unclaimed, unexpired bootstrap; read-only, never spawn twice")
    reader.add_argument("--read-program-contract", help="read a full program rule via the served program_contracts ref; never init/serve")
    reader.add_argument('--read-report-context', choices=model_view.REPORT_CONTEXT_FIELDS, help='read a complete projected report section; never init/serve')
    ap.add_argument('--context-sha256', help='required with --read-report-context: digest from input_authority.report_context')
    reader.add_argument("--verify-evidence", action="store_true", help="alpha.22: verify the hash-chained _evidence.json ledger of the cache; read-only, never init/serve")
    reader.add_argument("--contract", metavar="ID", help="alpha.100: the full text of a contract or section (core, gate#declared, core.steps) as the replies send it; read-only, never init/serve")
    ap.add_argument("--input-field", default="output", choices=("output", "vars", "user_summary", "user_messages", "source_support"))
    ap.add_argument('--input-path', help='only with --read-input-ref: select an exact JSON subtree a.b[0] before paging; no extra files or authority')
    ap.add_argument("--no-deref", action="store_true", help="alpha.57: return output addresses ({\"@ref\": ...}) as stored instead of the content they name")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, help="read: 1..65536 characters (default 65536); catalog: 1..32 records (default 8)")
    args = ap.parse_args(argv)
    from lib import write_observation
    write_observation.bind_request(agent_ticket=args.agent_ticket, abandon=args.dispatch_abandon,
                                  reason=args.reason)
    try:
        if args.input_path is not None and args.read_input_ref is None:
            raise engine_core.EngineError('INPUT_REF_INVALID', '--input-path requires --read-input-ref')
        if args.return_transcript and not args.observe_dispatch_return:
            raise engine_core.EngineError('DISPATCH_RETURN_INVALID', '--return-transcript requires --observe-dispatch-return')
        if args.observe_dispatch_return:
            if args.agent_ticket or args.entry_path or args.registry_root or args.agent_dir or args.user_message is not None \
                    or args.user_message_file or args.dispatch_abandon or args.reason or args.session_id or args.trace_id or args.workspace_dir:
                raise engine_core.EngineError('DISPATCH_RETURN_INVALID', 'Return observation cannot initialize, serve, claim or abandon.')
            print(json.dumps(engine_core.observe_dispatch_return(args.cache_dir, args.observe_dispatch_return,
                transcript=args.return_transcript), ensure_ascii=False, indent=2))
            return 0
        if args.write_purpose and args.check_write_target is None:
            raise engine_core.EngineError('INVALID_WRITE_PATH', '--write-purpose requires --check-write-target')
        if args.context_sha256 and not args.read_report_context:
            raise engine_core.EngineError('REPORT_CONTEXT_INVALID', '--context-sha256 requires --read-report-context')
        if args.read_write_authority or args.diagnostic_report or args.check_write_target is not None or args.read_input_ref is not None or args.list_inputs or args.read_dispatch_bootstrap is not None or args.read_program_contract is not None or args.verify_evidence or args.read_report_context or args.contract is not None:
            if args.entry_path or args.registry_root or args.agent_dir or args.user_message is not None or args.user_message_file \
                    or args.dispatch_abandon or args.reason or args.session_id or args.trace_id or args.workspace_dir:
                raise engine_core.EngineError("INPUT_REF_INVALID", "read-only operations cannot initialize, serve or abandon")
            if args.read_write_authority:
                if args.offset or args.limit is not None or args.no_deref or args.input_field != 'output':
                    raise engine_core.EngineError('WRITE_AUTHORITY_INVALID', 'Authority is complete, not a paged or filtered transcript.')
                from lib import write_authority
                reply = write_authority.read(args.cache_dir, agent_ticket=args.agent_ticket)
            elif args.diagnostic_report:
                if args.agent_ticket:
                    raise engine_core.EngineError('INPUT_REF_INVALID','Diagnostic disclosure is main-agent read-only, not a dispatch execution entry.')
                from lib import tool_faults
                reply=dict(status='DIAGNOSTIC_ONLY',recovery_authorized=False,observations=tool_faults.report_diagnostics(args.cache_dir))
            elif args.check_write_target is not None:
                reply = engine_core.check_write_target(args.cache_dir, args.check_write_target, purpose=args.write_purpose or 'artifact')
            elif args.read_report_context:
                reply = engine_core.read_report_context(args.cache_dir, args.read_report_context, args.context_sha256,
                    offset=args.offset, limit=args.limit if args.limit is not None else 4096, agent_ticket=args.agent_ticket)
            elif args.read_dispatch_bootstrap is not None:
                if args.agent_ticket:
                    raise engine_core.EngineError('DISPATCH_TICKET_INVALID', 'bootstrap retrieval is main-agent only')
                reply = engine_core.read_dispatch_bootstrap(args.cache_dir, args.read_dispatch_bootstrap)
            elif args.list_inputs:
                reply = engine_core.list_inputs(args.cache_dir, offset=args.offset, limit=args.limit if args.limit is not None else 8,
                                                agent_ticket=args.agent_ticket)
            elif args.verify_evidence:
                reply = engine_core.verify_evidence_ledger(args.cache_dir)
            elif args.contract is not None:   # alpha.100 (doc 241 S6)
                reply = engine_core.read_contract(args.cache_dir, args.contract, agent_ticket=args.agent_ticket)
            elif args.read_program_contract is not None:
                reply = engine_core.read_program_contract(args.cache_dir, args.read_program_contract,
                                                         offset=args.offset, limit=args.limit if args.limit is not None else 16384,
                                                         agent_ticket=args.agent_ticket)
            else:
                reply = engine_core.read_input(args.cache_dir, args.read_input_ref, field=args.input_field,
                                                offset=args.offset, limit=args.limit if args.limit is not None else 65536,   # alpha.50: one page for a 34k output
                                                agent_ticket=args.agent_ticket, deref=not args.no_deref, path=args.input_path)   # alpha.140
            print(json.dumps(reply, ensure_ascii=False, indent=2))
            return 0
        version_store=RunStore(args.cache_dir)
        if version_store.exists():engine_core.program_guard.assert_run_version(version_store.read_index())
        fence = stop_state.stop_fence(args.cache_dir)   # alpha.104 (doc 256 E3): a human-stopped run serves nothing
        if fence is not None:
            raise engine_core.EngineError("RUN_STOPPED_BY_HUMAN", fence["message"], field="cache_dir",
                                          expected="the human's next message (stop_decision.py in a judge turn)")
        from lib import tool_faults
        if version_store.exists() and (version_store.cache_dir / tool_faults.FILE).exists() and not any((args.entry_path, args.registry_root, args.agent_dir,
                args.user_message is not None, args.user_message_file, args.dispatch_abandon,
                args.reason, args.session_id, args.trace_id, args.workspace_dir)):
            from lib import fault_reentry
            projection = fault_reentry.project_commit_reentry(args.cache_dir, version_store.read_index(),
                                                              agent_ticket=args.agent_ticket)
            if projection is not None:
                print(json.dumps(projection, ensure_ascii=False, indent=2))
                return 0
        recovered_stage=tool_faults.consume_retry(args.cache_dir)
        from lib import accepted_replies
        if recovered_stage=='ACCEPTED_REPLY' and accepted_replies.enabled(RunStore(args.cache_dir).read_index()):
            tool_faults.replay_reply(args.cache_dir)
            return 0
        store = RunStore(args.cache_dir)
        if store.exists():
            from lib import tool_faults
            tool_faults.require_clear(args.cache_dir,store.read_index())
        if not store.exists():
            message = args.user_message or ""
            if args.user_message_file:
                message = Path(args.user_message_file).read_text(encoding="utf-8")
            engine_core.init_run(args.cache_dir, agent_dir=args.agent_dir, registry_roots=args.registry_root, entry_path=args.entry_path,
                                 user_message=message, session_id=args.session_id, trace_id=args.trace_id,
                                 workspace_dir=args.workspace_dir)
        reply = engine_core.serve(args.cache_dir, agent_ticket=args.agent_ticket, abandon=args.dispatch_abandon, abandon_reason=args.reason)
        if recovered_stage=='PUBLISH_ACCEPTED_TICKET' and reply.get('dispatch',{}).get('state')=='ISSUED':
            index=store.read_index()
            entry=engine_core._catalog_entry(index,index['current']['name'])
            _,dispatch=engine_core._self_dispatch(index,entry,index['current']['visit'])
            if dispatch and dispatch.get('ticket')==reply['dispatch']['ticket']:
                reply['dispatch']=engine_core._dispatch_view(store,dispatch,note='Registered ticket publication completed; use this exact bootstrap once, without a new child or charge.')
    except (engine_core.EngineError, RunStoreError) as exc:
        from lib import tool_faults
        diagnostic=tool_faults.capture(args.cache_dir,'next_node',exc) if isinstance(exc,engine_core.EngineError) else {}
        if isinstance(exc,RunStoreError) and exc.code=='READ_BACK_MISMATCH':
            diagnostic=tool_faults.capture(args.cache_dir,'next_node',engine_core.EngineError('ENGINE_UNEXPECTED_EXCEPTION',str(exc),example={'original_code':exc.code}))
        code = getattr(exc, "code", "ENGINE_ERROR")
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        print(json.dumps({"status": "ERROR", "errors": [{"code": code, "message": detail}],**diagnostic}, ensure_ascii=False, indent=2))
        return 2
    from lib import write_observation
    write_observation.accepted(reply, kind='serve', node=(reply.get('node') or {}).get('name') or 'run')
    lean = model_view.lean(reply)   # alpha.28 B4: references, not block text
    reply_io.emit(reply_io.render(lean, args.cache_dir, "serve", (lean.get("node") or {}).get("name") or "run"))
    return 0

def main(argv=None) -> int:
    from lib import write_observation, tool_faults
    args=list(argv if argv is not None else sys.argv[1:])
    cache=tool_faults.cli_args(args).cache_dir
    token=write_observation.begin('next_node',cache) if cache else None
    try:
        return _main(argv)
    except Exception as exc:
        from lib import tool_faults
        args=list(argv if argv is not None else sys.argv[1:])
        cache=tool_faults.cli_args(args).cache_dir
        if cache and tool_faults.recover_reply(cache,'next_node',exc):return 0
        print(json.dumps(tool_faults.unexpected(cache,'next_node',exc),ensure_ascii=False,indent=2))
        return 2
    finally:
        if token is not None:write_observation.end(token)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
