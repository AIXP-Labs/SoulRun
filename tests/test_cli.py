"""The command line: one command, same meaning as the Python call."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

QUESTION = "请运行 demo：跟我打个招呼"
HOST_ARGS = ["--model", "codex-acp/gpt-5.6", "--host-tool", "agent=false"]


def cli(env, cwd, *args, stdin: str | None = None):
    return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", *args], cwd=str(cwd), env=env,
                          input=None if stdin is None else stdin.encode("utf-8"), capture_output=True)


def out(done) -> str:
    return done.stdout.decode("utf-8")


def err(done) -> str:
    return done.stderr.decode("utf-8")


def test_no_arguments_prints_the_guide(agent, subprocess_env):
    done = cli(subprocess_env, agent)
    assert done.returncode == 0 and out(done).startswith("SoulRun ") and "ONE CALL" in out(done)
    assert not (agent / ".soulrun_cache").exists()


def test_version_names_both_versions(agent, subprocess_env, soulrun):
    done = cli(subprocess_env, agent, "--version")
    assert done.returncode == 0 and out(done).strip() == f"soulrun {soulrun.__version__} (engine {soulrun.ENGINE_VERSION})"


def test_engine_info_is_json(agent, subprocess_env, soulrun):
    info = json.loads(out(cli(subprocess_env, agent, "--engine-info")))
    assert info["engine_version"] == soulrun.ENGINE_VERSION and len(info["digest"]) == 64


def test_message_from_a_file_and_from_standard_input(agent, subprocess_env, tmp_path):
    message = tmp_path / "msg.txt"
    message.write_text(QUESTION, encoding="utf-8")
    from_file = cli(subprocess_env, agent, "--user-message-file", str(message), "--session-id", "cli-1", *HOST_ARGS)
    assert from_file.returncode == 0, err(from_file)
    assert out(from_file).startswith("[EXECUTION CONTEXT]\nturn_id: 1\n") and "[EXECUTE ENGINE ENTRY]" in out(from_file)
    from_stdin = cli(subprocess_env, agent, "--user-message-stdin", "--session-id", "cli-2", *HOST_ARGS, stdin=QUESTION)
    assert from_stdin.returncode == 0 and "turn_id: 2" in out(from_stdin) and "user_language: zh" in out(from_stdin)
    dash = cli(subprocess_env, agent, "--user-message-file", "-", "--session-id", "cli-3", *HOST_ARGS, stdin=QUESTION)
    assert dash.returncode == 0 and "turn_id: 3" in out(dash)


def test_a_byte_order_mark_is_not_part_of_the_words(agent, subprocess_env, tmp_path):
    """Notepad and PowerShell often save UTF-8 with a byte-order mark. Behind one the engine did not recognise
    "继续" and asked for confirmation instead of continuing."""
    def say(words: str, session: str, bom: bool) -> dict:
        message = tmp_path / f"{session}-{len(words)}.txt"
        message.write_bytes((b"\xef\xbb\xbf" if bom else b"") + words.encode("utf-8"))
        done = cli(subprocess_env, agent, "--user-message-file", str(message), "--session-id", session, "--json", *HOST_ARGS)
        assert done.returncode == 0, err(done)
        return json.loads(out(done))

    plain_first, plain_next = say(QUESTION, "bom-plain", False), say("继续", "bom-plain", False)
    marked_first, marked_next = say(QUESTION, "bom-marked", True), say("继续", "bom-marked", True)
    assert marked_first["entry_mode"] == plain_first["entry_mode"] == "fresh"
    assert marked_next["entry_mode"] == plain_next["entry_mode"] and marked_next["cache_dir"] == marked_first["cache_dir"]
    only_mark = tmp_path / "only-mark.txt"
    only_mark.write_bytes(b"\xef\xbb\xbf")
    guide = cli(subprocess_env, agent, "--user-message-file", str(only_mark))   # nothing but the mark: no words at all
    assert guide.returncode == 0 and out(guide).startswith("SoulRun ")


def test_json_output_carries_the_same_fields_as_the_python_object(agent, subprocess_env):
    done = cli(subprocess_env, agent, "--user-message-stdin", "--session-id", "cli-4", "--json", *HOST_ARGS, stdin=QUESTION)
    data = json.loads(out(done))
    assert data["kind"] == "program" and data["entry_mode"] == "fresh" and data["session_id"] == "cli-4"
    assert data["text"].startswith("[EXECUTION CONTEXT]") and Path(data["cache_dir"]).is_dir()
    assert Path(data["full_text_file"]).read_text(encoding="utf-8") == data["text"]


def test_cmd_passes_everything_else_to_the_engine_tool(agent, subprocess_env):
    started = json.loads(out(cli(subprocess_env, agent, "--user-message-stdin", "--session-id", "cli-5", "--json", *HOST_ARGS,
                                 stdin=QUESTION)))
    done = cli(subprocess_env, agent, "--cmd", "next-node", "--cache-dir", started["cache_dir"])
    assert done.returncode == 0, err(done)
    reply, end = json.JSONDecoder().raw_decode(out(done))      # the engine's reply, whole, then what its step needs
    assert reply["node"]["name"] == "Router.match"
    assert out(done)[end:].lstrip().startswith("[SOULRUN ENGINE NODE: Router.match]")


def test_usage_errors_exit_with_2_and_say_what_is_wrong(agent, subprocess_env, tmp_path):
    unknown = cli(subprocess_env, agent, "--cmd", "no-such")
    assert unknown.returncode == 2 and "UNKNOWN_CMD" in err(unknown) and "next-node" in err(unknown)
    both = cli(subprocess_env, agent, "--cmd", "next-node", "--user-message-stdin", stdin="x")
    assert both.returncode == 2 and "MESSAGE_AND_CMD" in err(both)
    bad_dir = cli(subprocess_env, agent, "--user-message-stdin", "--agent-dir", str(tmp_path / "missing"), stdin=QUESTION)
    assert bad_dir.returncode == 2 and "DIR_NOT_FOUND" in err(bad_dir)
    bad_tool = cli(subprocess_env, agent, "--user-message-stdin", "--host-tool", "agent", stdin=QUESTION)
    assert bad_tool.returncode == 2 and "HOST_TOOL_INVALID" in err(bad_tool)
    bad_option = cli(subprocess_env, agent, "--no-such-option")
    assert bad_option.returncode == 2
    as_json = cli(subprocess_env, agent, "--cmd", "no-such", "--json")
    assert json.loads(err(as_json))["error"]["code"] == "UNKNOWN_CMD"


def test_a_doubt_is_printed_as_a_question_and_is_not_an_error(agent, subprocess_env):
    done = cli(subprocess_env, agent, "--user-message-stdin", "--aiap", "demo_aiapp", stdin=QUESTION)
    assert done.returncode == 0 and "找不到" in out(done) and "demo_aiap" in out(done)
    assert not (agent / ".soulrun_cache" / ".execution_cache").exists()


def test_printing_stays_under_the_cap_and_names_the_file_when_the_program_does_not_fit(agent, subprocess_env, soulrun):
    from soulrun import _render
    cap = _render.print_cap()
    short = cli(subprocess_env, agent, "--user-message-stdin", "--session-id", "cli-6", "--inline-program", *HOST_ARGS, stdin=QUESTION)
    assert short.returncode == 0 and len(short.stdout) <= cap and '"user_input": "' + QUESTION in out(short)

    long_message = "请运行 demo：" + "我最近在考虑要不要换一个城市生活，" * 130
    long = cli(subprocess_env, agent, "--user-message-stdin", "--session-id", "cli-7", "--inline-program", "--json", *HOST_ARGS,
               stdin=long_message)
    data = json.loads(out(long))
    printed = data["text"]
    assert len(printed.encode("utf-8")) <= cap and printed.startswith("[EXECUTION CONTEXT]")
    marker = json.loads(printed.split("\n\n")[-1])["program"]
    assert marker["omitted"] is True and marker["read"] == data["full_text_file"]
    full = Path(data["full_text_file"]).read_text(encoding="utf-8")
    assert len(full.encode("utf-8")) > cap and long_message in json.loads(full[full.index("[\n"):])[1]["content"]["user_input"]


def test_the_help_describes_every_option_the_exit_codes_and_where_cmd_arguments_go(soulrun):
    """--help, the guide and the documents say the same: each option is described, the agent folder's variable is
    named, --cmd passes every other argument on, and the exit codes are listed."""
    from soulrun import cli
    parser = cli.build_parser()
    undescribed = [a.option_strings[0] for a in parser._actions if a.option_strings and not a.help]
    assert undescribed == []
    text = parser.format_help()
    assert "SOULRUN_AGENT_DIR" in " ".join(text.split()) and "exit codes: 0" in text
    assert "every other argument goes to that engine tool" in " ".join(text.split())
    guide = soulrun().text
    assert "SOULRUN_AGENT_DIR" in guide and "every other argument goes to the engine tool" in " ".join(guide.split())


def test_json_with_a_cmd_is_soulruns_own_and_not_passed_to_a_tool_that_refuses_it(agent, subprocess_env, tmp_path):
    payload = tmp_path / "payload.json"                  # every option node-commit requires: only --json could be refused
    payload.write_text("{}", encoding="utf-8")
    done = cli(subprocess_env, agent, "--json", "--cmd", "node-commit", "--cache-dir", str(tmp_path / "nowhere"), "--node", "x",
               "--payload-file", str(payload))
    assert "unrecognized arguments: --json" not in err(done) and "unrecognized arguments" not in out(done)
