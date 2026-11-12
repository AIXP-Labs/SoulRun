"""tools/clean_engine.py: development history comes out, nothing else changes."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys

import pytest

from conftest import ROOT
from legacy_snapshot import unpack


def _tool():
    spec = importlib.util.spec_from_file_location("clean_engine", ROOT / "tools" / "clean_engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["clean_engine"] = module
    spec.loader.exec_module(module)
    return module


CE = _tool()
DRIVE = "D" + ":/"                      # a machine path, spelled at run time: this file names none


@pytest.mark.parametrize(("before", "after"), [
    ("stops the business work (alpha.88).", "stops the business work."),
    ("write each backslash as \\\\ or use / (alpha.98)", "write each backslash as \\\\ or use /"),
    ("(alpha.58: intents are ^[a-z][a-z0-9_]*$; write them so)", "(intents are ^[a-z][a-z0-9_]*$; write them so)"),
    ("exactly as given ({ref, field, message_index?}; alpha.99) - never", "exactly as given ({ref, field, message_index?}) - never"),
    ("(severity is the model's; alpha.99, doc 233: a level below is raised)", "(severity is the model's; a level below is raised)"),
    ("Self-reported size (informational, doc 06 §2).", "Self-reported size (informational)."),
    ("the bootstrap (doc 10 §3.3)", "the bootstrap"),
    ("is unchanged. Alpha155: a complete accepted echo", "is unchanged. A complete accepted echo"),
    ("not supported in the alpha series (doc 02 D6).", "not supported."),
])
def test_texts_a_model_reads_lose_only_their_references(before, after):
    assert CE.scrub(before, thorough=False) == after


@pytest.mark.parametrize("text", [
    "Start from payload_skeleton; they define the accepted fields and node-specific evidence",
    "The user asked to export the report; the program says nothing about it",
    r"\s*(?:(\|\||&&|==|!=|>=|<=|[><!()])",
    "FIRST ACTION: run python {tool} --cache-dir {cache} ; follow its actual resume.kind",
    "(e.g. S3 for [S3]); kept verbatim",
    "SOULBOT_RESUME_INTERRUPTED_RUNS=true",
    "the [core.steps v1] section of commit.v1.json",
    "AISOP §6.12 / AIAP §23.6 (optional)",
])
def test_texts_without_references_are_left_exactly_as_they_are(text):
    assert CE.scrub(text, thorough=False) == text
    assert CE.scrub(text, thorough=True) == text


@pytest.mark.parametrize(("before", "after"), [
    ("alpha.104 (04 series doc 255 final_plan §2-§3, doc 256 E1): Stop is resumable.", "Stop is resumable."),
    ("final_plan §3.3 送达记录: the host's after-agent callback", "the host's after-agent callback"),
    ("the answer (doc 182, user ruling 2026-09-21) always carries it", "the answer always carries it"),
    ("rule r3 (user 2026-09-23 「声明必填」): the decision stays", "rule r3: the decision stays"),
    ("a quote such as (caches 42, 43, 49, 64) or a cache", "a quote such as or a cache"),
    ("Message (cache 64 streamed the question) here", "Message (a run streamed the question) here"),
    ("in production cache/66 a ledger", "in a run a ledger"),
])
def test_comments_and_docstrings_are_cleaned_thoroughly(before, after):
    assert CE.scrub(before, thorough=True) == after


def test_names_versions_and_machine_paths():
    text = ('SoulBot Execute Engine v7 core; dev.soulbot.execute_engine; soulbot_execute_engine.main; '
            'urn:soulbot:final-answer:1; 7.0.0-alpha.155; ' + DRIVE + 'someone/projects/targets; D:/dir/file; '
            '<agent>/soulbot_execute_engine_aiap; executor: soulbot.dev; SOULBOT_SUPPLY_WAIT_MAX_SECONDS')
    assert CE.rename(text, "1.0.0") == (
        'SoulRun engine; dev.soulrun.engine; soulrun_engine.main; urn:soulrun:final-answer:1; 1.0.0; D:/dir/targets; '
        'D:/dir/file; <agent>/soulbot_execute_engine_aiap; executor: soulbot.dev; SOULBOT_SUPPLY_WAIT_MAX_SECONDS')


def test_python_keeps_its_code_and_its_plain_comments():
    source = (
        '"""alpha.12 (doc 3): the module."""\n'
        "# ---------------------------------------------------------------\n"
        "# alpha.40\n"
        "X = 1   # alpha.41: the value\n"
        'MESSAGE = f"value {X} (alpha.99)"\n'
        'PATTERN = r"[><!()]"\n'
        "def f():\n"
        '    """doc 7 §2: the function."""\n'
        "    return X  # plain note\n"
    )
    cleaned = CE.clean_python(source, "1.0.0")
    assert CE.same_code(source, cleaned)
    assert cleaned == (
        '"""the module."""\n'
        "# ---------------------------------------------------------------\n"
        "X = 1   # the value\n"
        'MESSAGE = f"value {X}"\n'
        'PATTERN = r"[><!()]"\n'
        "def f():\n"
        '    """the function."""\n'
        "    return X  # plain note\n"
    )


def test_comments_only_keeps_every_string():
    source = 'TEXT = "kept (alpha.9)"  # alpha.9: a note\n'
    assert CE.clean_comments(source) == 'TEXT = "kept (alpha.9)"  # a note\n'


def test_a_whole_engine_is_cleaned_stamped_and_resealed(tmp_path):
    source = tmp_path / "engine"
    unpack(source, 'src/soulrun/soulrun_aiap/')
    core = source / "python_tools" / "lib" / "engine_core.py"
    core.write_text(core.read_text(encoding="utf-8") + "\n# alpha.300 (doc 9): a note\n", encoding="utf-8")
    contract = source / "contracts" / "core.contract.json"
    doc = json.loads(contract.read_text(encoding="utf-8"))
    doc["sections"][0]["text"] += " (alpha.300)"
    contract.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests" / "test_x.py").write_text("pass\n", encoding="utf-8")
    target = tmp_path / "clean"
    report = CE.build(source, target, "2.0.0")
    assert report["dropped"] == 1 and "governance hash" in report["resealed"]           # the new version changed the programs
    assert CE.check(target) == []
    import hashlib
    manifest = json.loads((target / "contracts" / "manifest.json").read_text(encoding="utf-8"))["files"]
    assert manifest == {n: hashlib.sha256((target / "contracts" / n).read_bytes()).hexdigest() for n in manifest}
    assert 'ENGINE_VERSION = "2.0.0"' in (target / "python_tools" / "lib" / "engine_core.py").read_text(encoding="utf-8")
    assert json.loads((target / "agent_card.json").read_text(encoding="utf-8"))["version"] == "2.0.0"
    assert "# a note" in (target / "python_tools" / "lib" / "engine_core.py").read_text(encoding="utf-8")
    assert (target / "AIAP.md").read_text(encoding="utf-8").rstrip().endswith("Version: AIAP V1.0.0. www.aiap.dev")
    assert not json.loads((target / "contracts" / "core.contract.json").read_text(encoding="utf-8"))["sections"][0]["text"].endswith(")")


def test_check_ignores_what_python_leaves_behind_but_names_a_stray_file(tmp_path):
    engine = tmp_path / "engine"
    unpack(engine, 'src/soulrun/soulrun_aiap/')
    (engine / "python_tools" / "lib" / "__pycache__").mkdir()
    (engine / "python_tools" / "lib" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"0")
    (engine / "tests").mkdir()
    (engine / "tests" / "test_x.py").write_text("pass\n", encoding="utf-8")
    assert CE.check(engine) == ["tests/test_x.py: a file the engine does not need at run time"]


def test_check_names_what_is_left(tmp_path):
    folder = tmp_path / 'legacy'
    unpack(folder, 'src/soulrun/soulrun_aiap/')
    assert CE.check(folder) == []
    assert CE.CHECK.search("see Codex 171") and CE.CHECK.search(DRIVE + "projects/x") and not CE.CHECK.search("D:/dir/file")


# ---- batch 4 (doc 35): the rules, what is kept, the check ---------------------------------------------------------
BS = "\\"                                                   # one backslash; paths below are spelled at run time


def test_machine_paths_of_every_kind_become_the_neutral_examples():
    windows = "C" + ":" + BS + "Users" + BS + "someone" + BS + "notes.txt"
    cases = ((windows, "D:/dir/notes.txt"), (windows.replace(BS, BS * 2), "D:/dir/notes.txt"),
             ("/ho" + "me/someone/projects/x.py", "/home/user/x.py"), ("/Us" + "ers/someone/x.md", "/home/user/x.md"),
             (BS * 2 + "fileserver" + BS + "share" + BS + "file.txt", "D:/dir/file.txt"))
    for text, neutral in cases:
        assert CE.CHECK.search(text), text
        assert CE.rename(text, "1.0.0") == neutral and not CE.CHECK.search(neutral)
    escaped_line_breaks = '"' + BS * 2 + "n" + BS * 2 + 'n"'                 # "\\n\\n" in a docstring: no share
    assert not CE.CHECK.search(escaped_line_breaks) and CE.rename(escaped_line_breaks, "1.0.0") == escaped_line_breaks


@pytest.mark.parametrize("text", ["fixed in a155", "见 355 号", "用户 10-08 裁决", "a v7 rewrite", "04系列 351 号",
                                  "authorization (first rule, 2026-09-21)", "(追记: 2026-09-06 network)"])
def test_the_check_knows_the_other_kinds_of_history(text):
    assert CE.CHECK.search(text)


@pytest.mark.parametrize("comment", ["# fixed in a155 the guard holds", "# 02 号 D6 / R-14: zero hits", "# 用户 10-08 裁决: one way",
                                     "# v7 semantics: a rule", "# the human decides (first rule, 2026-09-21)."])
def test_comments_lose_those_kinds_too(comment):
    cleaned = CE.clean_python(comment + "\nX = 1\n", "1.0.0")
    assert not CE.CHECK.search(cleaned), cleaned


def test_a_dated_note_goes_from_a_text_a_human_reads_too():
    assert CE.scrub("no folder is created (追记: 2026-09-06 network interruption)", thorough=False) == "no folder is created"


def test_the_bundled_engines_known_leftovers_are_named_and_a_changed_file_is_checked_in_full(tmp_path):
    folder = tmp_path / 'legacy'
    unpack(folder, 'src/soulrun/soulrun_aiap/')
    problems, known = CE.check_report(folder)
    assert problems == [] and {line.split(":")[0] for line in known} == set(CE.KNOWN_LEFTOVERS)
    if not CE.KNOWN_LEFTOVERS:                          # the next engine came in cleaned in full: nothing to exempt
        return
    name = sorted(n for n in CE.KNOWN_LEFTOVERS if n.endswith(".py"))[0]
    copy = tmp_path / "engine"
    shutil.copytree(folder, copy, ignore=shutil.ignore_patterns("__pycache__"))
    (copy / name).write_bytes((copy / name).read_bytes() + b"\n# changed\n")
    changed_problems, changed_known = CE.check_report(copy)
    assert changed_problems and all(line.startswith(f"{name}:") for line in changed_problems)
    assert len(changed_problems) == sum(line.startswith(f"{name}:") for line in known)
    assert len(changed_known) == len(known) - len(changed_problems)


@pytest.mark.parametrize("name", [".git/config", ".vscode/settings.json", "node_modules/x/index.js", "run.log", ".env",
                                  ".DS_Store", "python_tools/lib/notes.bak", "lib/.cache/x.py", "logs/run.out"])
def test_only_what_runs_is_kept(name):
    assert not CE.kept(name)


@pytest.mark.parametrize("name", ["main.aisop.json", "python_tools/next_node.py", "AIAP.md", "contracts/core.contract.json", "x.txt"])
def test_what_runs_is_kept(name):
    assert CE.kept(name)


@pytest.mark.parametrize("text", ["resume from live run state", "recover from live runs only", "mode (isolated)", "the (production) build",
                                  "isolated runs: 3", "Level (D1)", "r1: retry the node"])
def test_plain_words_in_a_text_are_not_references(text):
    assert CE.scrub(text, thorough=False) == text


def test_a_cut_between_two_words_leaves_a_space():
    assert CE.scrub("see(alpha.9)here", thorough=False) == "see here"


def test_cleaning_that_would_change_a_json_text_is_refused(monkeypatch):
    doc = json.dumps({"text": json.dumps({"rule": "kept (alpha.9)", "list": [1, 2]})})
    cleaned = json.loads(CE.clean_json(doc, "1.0.0"))["text"]
    assert json.loads(cleaned) == {"rule": "kept", "list": [1, 2]}
    monkeypatch.setattr(CE, "scrub", lambda text, thorough: text.replace("}", ""))
    with pytest.raises(SystemExit, match="would change the JSON it holds - refusing"):
        CE.clean_json(doc, "1.0.0")


def test_check_refuses_a_folder_that_is_not_an_engine(tmp_path):
    import subprocess
    for target in (tmp_path / "soulrun_aaip", ROOT / "src" / "soulrun" / "soulrun_aiap" / "AIAP.md"):
        done = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "clean_engine.py"), "--check", str(target)],
                              capture_output=True, text=True, encoding="utf-8")
        assert done.returncode == 2 and "is not an engine folder" in done.stdout


def test_a_reference_opening_a_piece_of_a_joined_string_keeps_the_sentence_whole():
    import ast
    cleaned = CE.clean_python('MSG = ("not evidence " "(alpha.99); redirect it")\n', "1.0.0")
    assert ast.literal_eval(cleaned.split("=", 1)[1].strip()) == "not evidence; redirect it"   # the separator kept, in place


@pytest.mark.parametrize("source, text", [
    ('MSG = (f"{m}: not evidence " "(alpha.99); redirect it")\n', "M: not evidence; redirect it"),    # an f-string before
    ('MSG = (f"see {m}" "(alpha.99); redirect it")\n', "see M; redirect it"),                        # ends with a field
    ('MSG = (f"{m} " \\\n       "(alpha.99); redirect it")\n', "M; redirect it"),                    # over two lines
    ('MSG = "(alpha.99); redirect it"\n', "redirect it")])                                             # standing alone
def test_the_piece_before_may_be_an_f_string(source, text):
    """Python 3.12 reads an f-string as several tokens; the cleaning must come out the same as on 3.11."""
    cleaned = CE.clean_python(source, "1.0.0")
    assert CE.same_code(source, cleaned)
    assert eval(cleaned.split("=", 1)[1].strip(), {"m": "M"}) == text


def test_the_check_sees_a_reference_split_across_pieces(tmp_path):
    core = tmp_path / "engine" / "python_tools" / "lib" / "engine_core.py"
    core.parent.mkdir(parents=True)
    core.write_text('X = ("see doc " "12 for the rule")\n', encoding="utf-8")
    assert any("joined string" in line and "doc 12" in line for line in CE.check(tmp_path / "engine"))


def test_a_module_docstring_used_as_help_is_a_text_and_is_listed():
    source = '"""Tool (alpha.9): does x."""\nimport argparse\nparser = argparse.ArgumentParser(description=__doc__)\n'
    cleaned = CE.clean_python(source, "1.0.0")
    assert CE.same_code(source, cleaned)
    assert CE.changed_texts("tool.py", source, cleaned) == [("tool.py", "Tool (alpha.9): does x.", "Tool: does x.")]


def test_a_form_feed_does_not_move_the_cleaning():
    cleaned = CE.clean_python('A = 1  # page\x0cbreak\nMSG = "kept text (alpha.9)"\n', "1.0.0")
    assert 'MSG = "kept text"' in cleaned and "page\x0cbreak" in cleaned


def test_a_section_after_the_version_history_stays():
    text = "# AIAP\n\n## Version History\n- 1.0 old\n\n## Data Handling\nkept\n\nAlign Axiom 0: x\n"
    cleaned = CE.clean_aiap_md(text, "1.0.0")
    assert "## Version History" not in cleaned and "## Data Handling\nkept" in cleaned and cleaned.rstrip().endswith("Align Axiom 0: x")


# ---- every refusal the cleaning tool has, set off once (doc 35 F89) --------------------------------------------
def _tree(root, files: dict):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


def test_cleaning_that_would_change_code_is_refused(tmp_path, monkeypatch):
    """Only text may change ("only text, never code"): a cleaning that touched code stops, for the comments of
    SoulBot's wording and for a whole engine tree alike."""
    real = CE.clean_python
    monkeypatch.setattr(CE, "clean_python", lambda source, version, strings=True: real(source, version, strings) + "Y = 2\n")
    with pytest.raises(SystemExit, match="cleaning the comments changed more than the comments - refusing"):
        CE.clean_comments("X = 1  # a note (alpha.9)\n")
    tree = _tree(tmp_path / "tree", {"python_tools/lib/engine_core.py": 'ENGINE_VERSION = "0.1.0"\n'})
    with pytest.raises(SystemExit, match="python_tools/lib/engine_core.py: cleaning changed the code, not only text"):
        CE.build(tree, tmp_path / "out", "1.0.1")


def test_a_tree_that_is_not_an_engine_or_a_target_that_exists_is_refused(tmp_path):
    tree = _tree(tmp_path / "tree", {"notes.md": "# notes\n"})
    with pytest.raises(SystemExit, match="no ENGINE_VERSION found in python_tools/lib/engine_core.py"):
        CE.build(tree, tmp_path / "out", "1.0.1")
    (tmp_path / "taken").mkdir()
    with pytest.raises(SystemExit, match="already exists"):
        CE.build(tree, tmp_path / "taken", "1.0.1")


@pytest.mark.parametrize(("tool", "said"), [("import sys\nsys.exit(1)\n", "refresh_governance_hash.py failed"),
                                            ('import sys\nsys.exit(1 if "--check" in sys.argv else 0)\n',
                                             "the governance hash is still stale")])
def test_an_engine_whose_integrity_record_cannot_be_renewed_is_refused(tmp_path, tool, said):
    engine = _tree(tmp_path / "engine", {"tools/refresh_governance_hash.py": tool})
    with pytest.raises(SystemExit, match=said):
        CE.reseal(engine)
