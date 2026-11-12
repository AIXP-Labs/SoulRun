"""tests/soulbot_samples.json, SoulBot's side of the comparisons for machines without SoulBot (CI): current with
SoulBot when it is beside this repository, complete, and free of anything that belongs to one machine."""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from conftest import ROOT
from soulbot_side import SAMPLES, TOOL

TOOL_PATH = ROOT / "tools" / "record_soulbot_samples.py"


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", "-X", "utf8", str(TOOL_PATH), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env)


@pytest.mark.skipif(not TOOL.soulbot_is_beside(), reason="SoulBot is not beside this repository: nothing to compare the samples with")
def test_the_samples_are_soulbots_today():
    done = _run("--check")
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_samples_hold_every_case_the_tool_knows():
    assert {case: recorded["context"] for case, recorded in SAMPLES["interruption_notes"].items()} == \
        {case: TOOL.context(case) for case in TOOL.CASES}
    assert [r["context"] for r in SAMPLES["language_names"]] == [TOOL.language_context(c) for c in TOOL.LANGUAGE_CODES] + [None]
    assert set(SAMPLES["readme_footers"]) == {"README.md", "README_CN.md"} and set(SAMPLES["policy_documents"]) == set(TOOL.POLICY_DOCUMENTS)
    assert SAMPLES["turn_policy_source"].startswith("def _engine_turn_policy(") and SAMPLES["host_modules"]


def test_the_samples_name_no_folder_of_this_machine():
    text = TOOL.SAMPLES.read_text(encoding="utf-8")
    assert "{ENGINE}/python_tools/next_node.py" in text                 # the engine folder is written neutrally
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:(?:\\|/(?!/))|/home/|/Users/|/tmp/", text)    # a drive, not a URL's ://


def test_without_soulbot_the_tool_records_nothing(tmp_path):
    before = TOOL.SAMPLES.read_bytes()
    env = {**os.environ, "SOULRUN_TEST_AGENT_PY": str(tmp_path / "agent.py"), "SOULRUN_TEST_SOULBOT_SRC": str(tmp_path),
           "SOULRUN_TEST_SOULBOT_DOCS": str(tmp_path)}
    done = _run(env=env)
    assert done.returncode == 2 and "SoulBot is not beside this repository" in done.stdout
    assert TOOL.SAMPLES.read_bytes() == before
