"""No host program between SoulRun and the model (docs/05SoulRun 69, 70): a turn SoulRun's command line printed tells the
model to show the human the blocks themselves, and the engine commands print the blocks' text after each reply; the
file holding the user's words goes into the turn's run."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import HOST, QUESTION

HOST_ARGS = ["--model", HOST["model"], "--host-tool", "agent=false"]


def cli(env, cwd, *args):
    return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", *args], cwd=str(cwd), env=env,
                          capture_output=True, text=True, encoding="utf-8")


def start(env, agent, tmp_path, session: str, *more) -> tuple[subprocess.CompletedProcess, str]:
    """A turn printed by the command line; its run folder."""
    message = tmp_path / f"{session}.txt"
    message.write_text(QUESTION, encoding="utf-8")
    done = cli(env, agent, "--user-message-file", str(message), "--session-id", session, *HOST_ARGS, *more)
    assert done.returncode == 0, done.stderr
    cache_dir = done.stdout.split("cache_dir: ", 1)[1].split("\n", 1)[0].strip()
    return done, cache_dir


# ---- which blocks a reply names ------------------------------------------------------------------------------------

def test_the_blocks_a_reply_names_in_the_order_the_program_presents_them():
    from soulrun import _screen
    r = lambda name: f"⟦engine:7/{name}⟧"  # noqa: E731
    assert _screen.refs_in({"public_plan_ref": r("plan.01.a.v1.txt")}) == [r("plan.01.a.v1.txt")]
    commit = {"public_block_ref": r("node.01.a.v1.txt"), "public_plan_next_ref": r("plan.02.b.v1.txt"),
              "next_plan": {"public_plan_ref": r("plan.02.b.v1.txt")}, "prev_public_block_ref": r("node.00.x.v1.txt")}
    assert _screen.refs_in(commit) == [r("node.01.a.v1.txt"), r("plan.02.b.v1.txt")]      # once, the old block not again
    gate = {"public_block_ref": r("pause.03.c.q001.v1.txt"), "gate": {"public_prompt_ref": r("menu.q001.txt")}}
    assert _screen.refs_in(gate) == [r("pause.03.c.q001.v1.txt"), r("menu.q001.txt")]
    final = {"terminal_delivery_refs": [r("final_answer.txt"), r("evidence.txt")], "final_answer_ref": r("final_answer.txt")}
    assert _screen.refs_in(final) == [r("final_answer.txt"), r("evidence.txt")]
    assert _screen.refs_in({"dispatch": {"public_refs": [r("plan.07.sub.d.v1.txt")]}}) == [r("plan.07.sub.d.v1.txt")]
    assert _screen.refs_in("not a reply") == [] and _screen.refs_in({"public_block_ref": None}) == []


# ---- a turn printed by the command line ----------------------------------------------------------------------------

def test_a_turn_printed_by_the_command_line_says_no_host_shows_the_blocks(soulrun, agent, tmp_path, subprocess_env):
    from soulrun import _records, _screen
    done, cache_dir = start(subprocess_env, agent, tmp_path, "s1")
    assert _screen.SCREEN_BLOCK in done.stdout
    assert done.stdout.index("\n\n[SOULRUN SCREEN]\n") < done.stdout.index("\n\n[LOADED AISOP: engine_node.aisop.json]")
    assertion = done.stdout[done.stdout.index("[TURN EXECUTION ASSERTION]"):]
    assert f"\n{_screen.SCREEN_ASSERTION}\nSHOW_THOUGHTS_FORWARDING=" in assertion
    assert _screen.SCREEN in _records.read_delivered(cache_dir)
    # --json is for a host program, which shows the blocks itself; so is the Python call (SoulBot)
    message = tmp_path / "s2.txt"
    message.write_text(QUESTION, encoding="utf-8")
    as_json = json.loads(cli(subprocess_env, agent, "--user-message-file", str(message), "--session-id", "s2", "--json",
                             *HOST_ARGS).stdout)
    assert "[SOULRUN SCREEN]" not in as_json["text"] and _screen.SCREEN not in _records.read_delivered(as_json["cache_dir"])
    ctx = soulrun(user_message=QUESTION, session_id="s3", **HOST)
    assert "[SOULRUN SCREEN]" not in ctx.text and _screen.SCREEN not in _records.read_delivered(ctx.cache_dir)


def test_after_each_reply_the_blocks_it_names_are_printed_once(soulrun, agent, tmp_path, subprocess_env):
    _done, cache_dir = start(subprocess_env, agent, tmp_path, "s4")
    served = cli(subprocess_env, agent, "--cmd", "next-node", "--cache-dir", cache_dir)
    reply, end = json.JSONDecoder().raw_decode(served.stdout)
    rest = served.stdout[end:]
    plan = reply["public_plan_ref"]
    assert plan.startswith("⟦engine:") and "[SOULRUN FOR THE HUMAN]" in rest
    assert rest.index("[SOULRUN ENGINE NODE: Router.match]") < rest.index("[SOULRUN FOR THE HUMAN]")
    run, name = plan[len("⟦engine:"):-1].split("/", 1)
    text = (Path(cache_dir) / "_public" / name).read_text(encoding="utf-8").strip("\n")
    assert f"----- {plan}\n{text}\n----- end of {plan}" in rest
    from soulrun import _screen
    assert _screen.human_part(cache_dir, reply) is None                         # once per turn
    copy = dict(reply, public_plan_ref=plan[:-len(".txt⟧")] + ".0123.txt⟧")     # a copy of the same text, another name
    (Path(cache_dir) / "_public" / (name[:-4] + ".0123.txt")).write_text(text, encoding="utf-8")
    assert _screen.human_part(cache_dir, copy) is None


def test_a_turn_with_a_host_program_gets_no_blocks_after_the_reply(soulrun, agent, subprocess_env):
    ctx = soulrun(user_message=QUESTION, session_id="s5", **HOST)               # SoulBot's way: it shows the blocks
    served = cli(subprocess_env, agent, "--cmd", "next-node", "--cache-dir", ctx.cache_dir)
    assert "[SOULRUN ENGINE NODE: Router.match]" in served.stdout and "[SOULRUN FOR THE HUMAN]" not in served.stdout


def test_blocks_that_would_pass_the_cap_are_named_with_the_command_that_prints_them(soulrun, agent, tmp_path,
                                                                                   subprocess_env):
    from soulrun import _records, _screen
    _done, cache_dir = start(subprocess_env, agent, tmp_path, "s6")
    served = soulrun(cmd="next-node", cache_dir=cache_dir).json()      # the Python call adds nothing to the reply
    line = _screen.human_part(cache_dir, served, room=50)
    plan = served["public_plan_ref"]
    assert line.startswith("[SOULRUN FOR THE HUMAN] ") and line.count("\n") == 1
    assert f'To print it now: <soulrun> --expand "{plan}" --cache-dir "{cache_dir}"' in line
    given = _records.read_delivered(cache_dir)
    assert _screen.SHOWN + plan not in given and f"{_screen.WAITING}0000:{plan}" in given
    printed = cli(subprocess_env, agent, "--expand", plan, "--cache-dir", cache_dir)
    assert printed.returncode == 0 and f"----- {plan}\n" in printed.stdout
    assert _screen.SHOWN + plan in _records.read_delivered(cache_dir)          # printed on request: shown
    assert _screen.human_part(cache_dir, {"reply_file": "r"}) is None           # and it does not come again


def test_blocks_that_do_not_fit_follow_the_next_reply_with_room(soulrun, agent, tmp_path, subprocess_env):
    from soulrun import _records, _screen
    _done, cache_dir = start(subprocess_env, agent, tmp_path, "s8")
    served = soulrun(cmd="next-node", cache_dir=cache_dir).json()
    plan = served["public_plan_ref"]
    assert _screen.human_part(cache_dir, served, room=50).count("\n") == 1                # waits
    later = _screen.human_part(cache_dir, {"reply_file": "r"})                            # a short reply: it follows
    assert later.startswith("[SOULRUN FOR THE HUMAN] PRINT THESE BLOCKS ON THE SCREEN NOW") and f"----- {plan}\n" in later
    given = _records.read_delivered(cache_dir)
    assert _screen.SHOWN + plan in given and not any(p.startswith(_screen.WAITING) for p in given)
    # of two blocks, the first fits and the second waits, in order
    run = Path(cache_dir).name
    public = Path(cache_dir) / "_public"
    for name, text in (("plan.09.a.v1.txt", "first block"), ("plan.10.b.v1.txt", "second block " * 400)):
        (public / name).write_text(text, encoding="utf-8")
    two = {"public_plan_ref": f"⟦engine:{run}/plan.09.a.v1.txt⟧", "public_plan_next_ref": f"⟦engine:{run}/plan.10.b.v1.txt⟧"}
    part = _screen.human_part(cache_dir, two, room=2_000)
    assert "first block" in part and "second block" not in part and f"⟦engine:{run}/plan.10.b.v1.txt⟧: not printed" in part
    assert "second block" in _screen.human_part(cache_dir, {"reply_file": "r"})


def test_expand_pages_long_text_and_refuses_what_is_not_a_block(soulrun, agent, tmp_path, subprocess_env):
    from soulrun import _screen
    _done, cache_dir = start(subprocess_env, agent, tmp_path, "s7")
    run = Path(cache_dir).name
    (Path(cache_dir) / "_public").mkdir(exist_ok=True)
    (Path(cache_dir) / "_public" / "final_answer.txt").write_text("答" * 20_000, encoding="utf-8")
    ref = f"⟦engine:{run}/final_answer.txt⟧"
    first = _screen.expand([ref], cache_dir)
    assert len(first.encode("utf-8")) <= _screen.PAGE_BYTES + 200 and "[more: run the same command with --offset " in first
    offset = int(first.rsplit("--offset ", 1)[1].split("]")[0])
    second = cli(subprocess_env, agent, "--expand", ref, "--cache-dir", cache_dir, "--offset", str(offset))
    assert second.returncode == 0 and second.stdout.startswith("答")
    for bad, code in (([f"⟦engine:{run}/../secret.txt⟧"], "EXPAND_REF_UNKNOWN"), ([f"⟦engine:{run}/nothing.txt⟧"], "EXPAND_REF_UNKNOWN")):
        with pytest.raises(soulrun.UsageError) as error:
            _screen.expand(bad, cache_dir)
        assert error.value.code == code
    with pytest.raises(soulrun.UsageError) as error:
        _screen.expand([ref], None)
    assert error.value.code == "CACHE_DIR_REQUIRED"


# ---- the file holding the user's words -----------------------------------------------------------------------------

def test_the_message_file_goes_into_its_run(soulrun, agent, tmp_path, subprocess_env):
    message = tmp_path / "inbox" / "words.txt"         # the folder the agent made for it stays: it writes there again
    message.parent.mkdir()
    message.write_text(QUESTION, encoding="utf-8")
    done = cli(subprocess_env, agent, "--user-message-file", str(message), "--session-id", "m1", "--json", *HOST_ARGS)
    cache_dir = Path(json.loads(done.stdout)["cache_dir"])
    assert not message.exists() and message.parent.is_dir()
    assert (cache_dir / "_soulrun" / "message.1.txt").read_text(encoding="utf-8") == QUESTION
    message = tmp_path / "words.txt"
    again = cli(subprocess_env, agent, "--user-message-file", str(message), "--session-id", "m1", *HOST_ARGS)
    assert again.returncode == 2 and "MESSAGE_FILE_UNREADABLE" in again.stderr and "_soulrun/message.<n>.txt" in again.stderr
    message.write_text("继续", encoding="utf-8")                                 # the next turn of the same run
    cli(subprocess_env, agent, "--user-message-file", str(message), "--session-id", "m1", "--json", *HOST_ARGS)
    assert (cache_dir / "_soulrun" / "message.2.txt").read_text(encoding="utf-8") == "继续"
    # the engine goes on as before: its own files are untouched, it reads none of SoulRun's
    served = cli(subprocess_env, agent, "--cmd", "next-node", "--cache-dir", str(cache_dir))
    assert json.JSONDecoder().raw_decode(served.stdout)[0].get("reply_file")


def test_a_message_file_kept_asked_to_keep_or_without_a_run_stays(soulrun, agent, tmp_path, subprocess_env):
    kept = tmp_path / "kept.txt"
    kept.write_text(QUESTION, encoding="utf-8")
    done = cli(subprocess_env, agent, "--user-message-file", str(kept), "--session-id", "m2", "--keep-message-file", *HOST_ARGS)
    assert done.returncode == 0 and kept.read_text(encoding="utf-8") == QUESTION
    asked = tmp_path / "asked.txt"                    # a question before any run: its options call again with this file
    asked.write_text(QUESTION, encoding="utf-8")
    doubt = cli(subprocess_env, agent, "--user-message-file", str(asked), "--aiap", "demo_aiapp", *HOST_ARGS)
    assert doubt.returncode == 0 and "demo_aiap" in doubt.stdout and asked.exists()
    piped = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--user-message-file", "-", "--session-id",
                            "m3", *HOST_ARGS], cwd=str(agent), env=subprocess_env, input=QUESTION.encode("utf-8"),
                           capture_output=True)
    assert piped.returncode == 0                                                  # standard input: nothing to move


@pytest.mark.parametrize("inside", ["words.txt", "in/words.txt"])
def test_words_written_into_a_new_run_folder_do_not_keep_it_from_being_used(soulrun, agent, tmp_path, subprocess_env, inside):
    runs = tmp_path / "runs"
    message = runs / inside
    message.parent.mkdir(parents=True)
    message.write_text(QUESTION, encoding="utf-8")
    done = cli(subprocess_env, agent, "--user-message-file", str(message), "--soulrun-cache-dir", str(runs), "--json",
               "--session-id", "m4", *HOST_ARGS)
    assert done.returncode == 0, done.stderr
    cache_dir = Path(json.loads(done.stdout)["cache_dir"])
    assert (cache_dir / "_soulrun" / "message.1.txt").read_text(encoding="utf-8") == QUESTION
    assert sorted(p.name for p in runs.iterdir()) == [".execution_cache", ".gitignore", ".soulrun"]
    # anything else there still keeps the folder from being used, and the words stay where they were written
    other = tmp_path / "other"
    (other / "notes.md").parent.mkdir()
    (other / "notes.md").write_text("mine", encoding="utf-8")
    (other / "words.txt").write_text(QUESTION, encoding="utf-8")
    refused = cli(subprocess_env, agent, "--user-message-file", str(other / "words.txt"), "--soulrun-cache-dir", str(other),
                  "--session-id", "m5", *HOST_ARGS)
    assert refused.returncode == 2 and "SOULRUN_CACHE_DIR_NOT_EMPTY" in refused.stderr and (other / "words.txt").exists()
