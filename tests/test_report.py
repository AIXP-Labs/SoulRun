"""The complete execution report behind an ``engine-report:`` link (docs/05SoulRun 54 S2): ``host.execution_report``
and ``soulrun --report``, checked as SoulBot's web page checks it. The run is a real one; its Engine.execute-report
record and report file are laid out as the engine writes them, and the index records the record's digest through the
engine's own store, so the index stays one the engine accepts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from helpers import HOST, QUESTION, commit, route_payload, take_node

REPORT = "**执行报告**\n\n" + "完整的执行报告正文。" * 4000 + "\n\n结尾。"       # long enough to need paging


def _cli(capsys, *arguments) -> tuple[int, str, str]:
    from soulrun import cli
    code = cli.main(list(arguments))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def reported(soulrun, agent):
    """A run with an execution report: (ctx, link). The record and the report file are what the engine writes."""
    from soulrun import _engine
    ctx = soulrun(user_message=QUESTION, session_id="rep", aiap="demo_aiap", **HOST)
    assert commit(soulrun, ctx, route_payload(take_node(soulrun, ctx), "demo_aiap"))["status"] == "COMMITTED"
    run = Path(ctx.cache_dir)
    digest = hashlib.sha256(REPORT.encode("utf-8")).hexdigest()
    (run / "_reports").mkdir(exist_ok=True)
    (run / "_reports" / f"sha256-{digest}.txt").write_bytes(REPORT.encode("utf-8"))
    record = {"node": "Engine.execute-report", "visit": 1,
              "machine": {"execution_report": {"node": "Engine.execute-report", "visit": 1, "full_sha256": digest}}}
    raw = json.dumps(record, ensure_ascii=False).encode("utf-8")
    (run / "demo_aiap.Engine.execute-report.json").write_bytes(raw)
    store = _engine.load("lib.run_store").RunStore(run)
    index = store.read_index()
    index["nodes"]["Engine.execute-report"] = dict(index["nodes"]["Router.match"], cache_sha256=hashlib.sha256(raw).hexdigest())
    store.write_index(index)
    return ctx, f"engine-report:{run.name}/Engine.execute-report@1/{digest}"


def _files(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}


def test_the_report_behind_a_link_page_by_page(soulrun, agent, reported):
    from soulrun import _report, host
    ctx, link = reported
    before = _files(agent)
    text, offset, pages = "", 0, 0
    while offset is not None:
        page = host.execution_report(f"[完整执行报告（原文）]({link})", cache_dir=ctx.cache_dir, offset=offset)
        assert page["status"] == "OK" and page["total_chars"] == len(REPORT) and page["sha256"] == link.rsplit("/", 1)[1]
        assert len(json.dumps(page["text"], ensure_ascii=False).encode("utf-8")) <= _report.PAGE_BYTES
        text, offset, pages = text + page["text"], page["next_offset"], pages + 1
    assert text == REPORT and pages > 1                              # CJK text is paged by bytes too
    small = host.execution_report(link, cache_dir=ctx.cache_dir, limit=100)
    assert small["text"] == REPORT[:100] and small["next_offset"] == 100 and small["complete"] is False
    found = host.execution_report(link, agent_dir=agent)               # the runs found as soulrun(...) finds them
    assert found["status"] == "OK" and found["offset"] == 0
    assert _files(agent) == before                                   # nothing was written


def test_a_report_answers_with_a_status_when_it_cannot_be_shown(soulrun, agent, reported):
    from soulrun import host
    ctx, link = reported
    run = Path(ctx.cache_dir)
    digest = link.rsplit("/", 1)[1]
    assert host.execution_report(link, cache_dir=ctx.cache_dir, session_id="another")["status"] == "NOT_IN_SESSION"
    assert host.execution_report(link, cache_dir=ctx.cache_dir, session_id="rep")["status"] == "OK"
    gone = link.replace(f"engine-report:{run.name}/", "engine-report:999/")
    assert host.execution_report(gone, cache_dir=ctx.cache_dir)["status"] == "CACHE_EXPIRED"
    other = link.replace(digest, "0" * 64)                             # a digest no record of the run names
    assert host.execution_report(other, cache_dir=ctx.cache_dir)["status"] == "REPORT_UNBOUND"
    report = run / "_reports" / f"sha256-{digest}.txt"
    report.write_bytes(REPORT.encode("utf-8") + b"!")                  # the file no longer hashes to the link
    assert host.execution_report(link, cache_dir=ctx.cache_dir)["status"] == "REPORT_DIGEST_MISMATCH"
    report.unlink()
    assert host.execution_report(link, cache_dir=ctx.cache_dir)["status"] == "REPORT_FILE_MISSING"
    record = run / "demo_aiap.Engine.execute-report.json"
    record.write_bytes(record.read_bytes() + b" ")                     # the record changed after the index recorded it
    assert host.execution_report(link, cache_dir=ctx.cache_dir)["status"] == "REPORT_UNBOUND"


@pytest.mark.parametrize(("link", "arguments", "code"), [
    ("not a link", {}, "REPORT_LINK_INVALID"),
    ("engine-report:../Engine.execute-report@1/" + "a" * 64, {}, "REPORT_LINK_INVALID"),
    (None, {"offset": -1}, "PAGE_INVALID"),
    (None, {"limit": 0}, "PAGE_INVALID"),
    (None, {"offset": 10 ** 9}, "PAGE_INVALID"),
])
def test_a_wrong_report_question_is_refused_by_name(soulrun, reported, link, arguments, code):
    from soulrun import host
    ctx, good = reported
    with pytest.raises(soulrun.SoulRunError) as error:
        host.execution_report(link or good, cache_dir=ctx.cache_dir, **arguments)
    assert error.value.code == code


def test_the_report_command_line(soulrun, agent, reported, capsys):
    ctx, link = reported
    code, out, _ = _cli(capsys, "--report", link, "--cache-dir", ctx.cache_dir, "--limit", "50")
    page = json.loads(out)
    assert code == 0 and page["status"] == "OK" and page["text"] == REPORT[:50] and page["next_offset"] == 50
    code, out, _ = _cli(capsys, "--report", link, "--agent-dir", str(agent), "--session-id", "another")
    assert code == 0 and json.loads(out)["status"] == "NOT_IN_SESSION"
    code, _, err = _cli(capsys, "--report", "nothing", "--cache-dir", ctx.cache_dir, "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "REPORT_LINK_INVALID"
    code, _, err = _cli(capsys, "--offset", "5", "--json")                        # paging needs --program or --report
    assert code == 2 and json.loads(err)["error"]["code"] == "PROGRAM_OPTION_ALONE"
    code, _, err = _cli(capsys, "--report", link, "--node", "Start", "--json")      # --node is --program's only
    assert code == 2 and json.loads(err)["error"]["code"] == "PROGRAM_OPTION_ALONE"
    code, _, err = _cli(capsys, "--report", link, "--program", "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "MODES_CONFLICT"
