"""Which conversation a message belongs to (session_id) and which run it is for (cache_dir)."""
from __future__ import annotations

from helpers import HOST, QUESTION, commit, index, route_payload, runs, take_node


def test_without_session_id_the_data_folder_is_one_conversation(soulrun, agent):
    first = soulrun(user_message=QUESTION, **HOST)
    second = soulrun(user_message="继续", **HOST)
    assert first.session_id == second.session_id == soulrun.DEFAULT_SESSION
    assert second.cache_dir == first.cache_dir and second.entry_mode == "recovery"


def test_different_session_ids_get_different_runs(soulrun, agent):
    a = soulrun(user_message=QUESTION, session_id="window-a", **HOST)
    b = soulrun(user_message=QUESTION, session_id="window-b", **HOST)
    assert a.cache_dir != b.cache_dir and (a.session_id, b.session_id) == ("window-a", "window-b")


def test_cache_dir_naming_the_conversations_own_unfinished_run_continues_it(soulrun, agent):
    a = soulrun(user_message=QUESTION, session_id="window-a", **HOST)
    again = soulrun(user_message="继续", session_id="window-a", cache_dir=a.cache_dir, **HOST)
    assert again.kind == "program" and again.cache_dir == a.cache_dir


def test_cache_dir_of_another_conversation_opens_a_doubt(soulrun, agent):
    a = soulrun(user_message=QUESTION, session_id="window-a", **HOST)
    b = soulrun(user_message=QUESTION, session_id="window-b", **HOST)
    before = runs(agent / ".soulrun_cache")
    doubt = soulrun(user_message="继续", session_id="window-a", cache_dir=b.cache_dir, **HOST)
    assert doubt.kind == "text_only" and doubt.doubt["code"] == "NAMED_RUN_MISMATCH"
    assert "window-b" not in doubt.text and doubt.doubt["owner_session_id"] == "window-b"   # for the host, not shown
    assert "不点名" in doubt.text and "取消" in doubt.text
    assert runs(agent / ".soulrun_cache") == before and a.cache_dir != b.cache_dir
    first, cancel = doubt.doubt["options"]
    assert (first["number"], first["action"], first["arguments"]) == (1, "call", {"cache_dir": None})
    assert (cancel["number"], cancel["action"]) == (2, "cancel")
    # The caller carries the human's choice back: option 1 = the same message, without naming a run.
    carried = soulrun(user_message="继续", session_id="window-a", **first["arguments"], **HOST)
    assert carried.kind == "program" and carried.cache_dir == a.cache_dir


def test_cache_dir_that_does_not_exist_or_lies_outside_the_data_folder_opens_a_doubt(soulrun, agent):
    soulrun(user_message=QUESTION, session_id="window-a", **HOST)
    before = runs(agent / ".soulrun_cache")
    missing = soulrun(user_message="继续", session_id="window-a",
                      cache_dir=agent / ".soulrun_cache" / ".execution_cache" / "9999", **HOST)
    outside = soulrun(user_message="继续", session_id="window-a", cache_dir=agent / "aiap", **HOST)
    for doubt in (missing, outside):
        assert doubt.kind == "text_only" and doubt.doubt["code"] == "NAMED_RUN_MISMATCH" and doubt.cache_dir is None
    assert runs(agent / ".soulrun_cache") == before


def test_cache_dir_of_a_finished_run_opens_a_doubt(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="window-a", aiap="demo_aiap", **HOST)
    cancelled = soulrun(user_message="取消", session_id="window-a", **HOST)
    assert cancelled.cache_dir == ctx.cache_dir and cancelled.entry_mode == "terminal"
    assert index(ctx.cache_dir)["run_state"] not in ("RUNNING", "WAITING_USER")
    doubt = soulrun(user_message="继续", session_id="window-a", cache_dir=ctx.cache_dir, **HOST)
    assert doubt.kind == "text_only" and "已经结束" in doubt.text


def test_cache_dir_of_an_older_run_of_the_same_conversation_opens_a_doubt(soulrun, agent):
    """The engine can only continue a conversation's latest run; SoulRun says so instead of guessing."""
    first = soulrun(user_message=QUESTION, session_id="window-a", aiap="demo_aiap", **HOST)
    reply = commit(soulrun, first, route_payload(take_node(soulrun, first), "demo_aiap"))
    assert reply["status"] == "COMMITTED"
    soulrun(user_message="取消", session_id="window-a", **HOST)
    second = soulrun(user_message=QUESTION, session_id="window-a", aiap="demo_aiap", **HOST)
    assert second.cache_dir != first.cache_dir and second.entry_mode == "fresh"
    doubt = soulrun(user_message="继续", session_id="window-a", cache_dir=first.cache_dir, **HOST)
    assert doubt.kind == "text_only" and doubt.doubt["code"] == "NAMED_RUN_MISMATCH"


def test_engine_today_without_any_session_id_the_engine_cannot_find_the_previous_run(soulrun, agent):
    """Why SoulRun supplies a default conversation name: the engine itself answers None."""
    from soulrun import host
    prepare = host.engine("prepare_cache")
    soulrun(user_message=QUESTION, **HOST)
    root = host.cache_root()
    assert prepare.latest_cache_for_session(root, None) is None
    assert prepare.latest_cache_for_session(root, soulrun.DEFAULT_SESSION) is not None


# ---- how often one call reads the conversation's latest run (docs/05SoulRun 87, #23) --------------------------------

def _count_soulruns_own_reads(monkeypatch) -> tuple[list[str], list[str]]:
    """Every run index SoulRun reads, and every lookup of a conversation's latest run - SoulRun's own, not the engine's
    while it prepares the run (prepare_execution_context reads the runs itself)."""
    from pathlib import Path

    from soulrun import _engine
    prepare = _engine.load("prepare_cache")
    reads, lookups, inside = [], [], []
    real_read, real_latest, real_prepare = prepare._read_index, prepare.latest_cache_for_session, prepare.prepare_execution_context

    def read(cache_dir):
        if not inside:
            reads.append(Path(cache_dir).name)
        return real_read(cache_dir)

    def latest(root, session_id):
        if not inside:
            lookups.append(session_id)
        return real_latest(root, session_id)

    def engine_prepares(*args, **kwargs):
        inside.append(True)
        try:
            return real_prepare(*args, **kwargs)
        finally:
            inside.pop()
    monkeypatch.setattr(prepare, "_read_index", read)
    monkeypatch.setattr(prepare, "latest_cache_for_session", latest)
    monkeypatch.setattr(prepare, "prepare_execution_context", engine_prepares)
    return reads, lookups


def test_one_call_looks_up_the_conversations_latest_run_once_and_reads_its_index_three_times(soulrun, agent, monkeypatch):
    """The checks before a run is prepared (another engine build, a kept named program, a gate a machine turn may not
    answer) all want the conversation's latest run and its index: the run is looked up once, and its index is read
    twice before the engine prepares the turn - once by the lookup itself, once for the checks. After the engine has
    prepared the turn, the index it wrote is read again (the slim-form check) - three reads where there were seven."""
    from pathlib import Path
    first = soulrun(user_message=QUESTION, session_id="r1", **HOST)
    run = Path(first.cache_dir).name
    reads, lookups = _count_soulruns_own_reads(monkeypatch)
    again = soulrun(user_message="继续", session_id="r1", **HOST)
    assert again.cache_dir == first.cache_dir
    assert lookups == ["r1"]
    assert reads == [run, run, run]          # the lookup's own read, the checks' one read, the read after the engine wrote


def test_a_new_conversations_first_call_scans_the_kept_runs_once(soulrun, agent, monkeypatch):
    for session in ("r2", "r3", "r4"):
        soulrun(user_message=QUESTION, session_id=session, **HOST)
    reads, lookups = _count_soulruns_own_reads(monkeypatch)
    soulrun(user_message=QUESTION, session_id="r5", **HOST)
    assert lookups == ["r5"] and sorted(reads) == ["1", "2", "3"]


def test_an_index_written_during_the_call_is_read_again(soulrun, agent):
    """The answers are kept for one call only, and an index is kept only while its file is unchanged."""
    import json
    from pathlib import Path

    from soulrun import _api, _engine
    ctx = soulrun(user_message=QUESTION, session_id="r6", **HOST)
    lookups = _api._RunLookups(_engine.load("prepare_cache"), Path(ctx.cache_dir).parent)
    assert lookups.latest("r6") == Path(ctx.cache_dir) and lookups.latest("nobody") is None
    first = lookups.index(ctx.cache_dir)
    assert lookups.index(ctx.cache_dir) is first                                    # unchanged: not read again
    path = Path(ctx.cache_dir) / "_index.json"
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["user_language"] = "en" if changed.get("user_language") != "en" else "zh"
    path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    again = lookups.index(ctx.cache_dir)
    assert again is not first and again["user_language"] == changed["user_language"]
