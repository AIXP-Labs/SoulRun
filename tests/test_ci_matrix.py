"""Check the small, explicit CI matrix and the README's current/history split."""
from __future__ import annotations

import json
import re

import pytest

from conftest import ROOT


def _job(workflow: str, name: str) -> str:
    matches = re.findall(rf"^  {name}:\n(.*?)(?=^  [a-z]+:\n|\Z)", workflow, re.MULTILINE | re.DOTALL)
    assert len(matches) == 1
    return matches[0]


def _assert_matrix(workflow: str) -> None:
    source = _job(workflow, "test")
    package = _job(workflow, "package")
    versions = re.findall(r"^        python-version: (\[.*\])$", source, re.MULTILINE)
    assert len(versions) == 1
    assert json.loads(versions[0]) == ["3.11", "3.12", "3.13", "3.14", "3.15"]
    for job in (source, package):
        # The OS flow list is intentionally literal, not an arbitrary YAML expression.
        assert re.findall(r"^        os: (.*)$", job, re.MULTILINE) == ["[ubuntu-latest, windows-latest]"]
        assert "      fail-fast: false\n" in job
        assert "continue-on-error" not in job
        assert "        run: python -m pytest -rs\n" in job
    assert '          python-version: "3.12"\n' in package
    assert "python -m twine check --strict dist/*" in package
    assert "permissions:\n  contents: read\n" in workflow


def test_ci_checks_python_315_on_both_platforms_without_dropping_old_jobs():
    _assert_matrix((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "os", "allow_failure", "non_strict"])
def test_ci_matrix_drift_is_rejected(mutation):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if mutation == "missing":
        changed = workflow.replace(', "3.15"', "", 1)
    elif mutation == "duplicate":
        changed = workflow.replace(', "3.15"', ', "3.15", "3.15"', 1)
    elif mutation == "os":
        changed = workflow.replace("[ubuntu-latest, windows-latest]", "[ubuntu-latest]", 1)
    elif mutation == "allow_failure":
        changed = workflow.replace("    timeout-minutes: 40\n", "    timeout-minutes: 40\n    continue-on-error: true\n", 1)
    else:
        changed = workflow.replace("python -m twine check --strict dist/*", "python -m twine check dist/*", 1)
    assert changed != workflow
    with pytest.raises(AssertionError):
        _assert_matrix(changed)


@pytest.mark.parametrize("page,old_heading,old_label", [
    ("README.md", "#### Historical Runtime-Head Table", "**Earlier builds.**"),
    ("README_CN.md", "#### \u5386\u53f2\u8fd0\u884c\u5934\u8868", "**\u66f4\u65e9\u7684\u6784\u5efa\u3002**"),
])
def test_readme_keeps_current_scope_and_links_to_preserved_history(page, old_heading, old_label):
    text = (ROOT / page).read_text(encoding="utf-8")
    history = (ROOT / "docs/verification-1.0.0.md").read_text(encoding="utf-8")
    assert old_heading not in text and old_label not in text
    assert old_heading in history and old_label in history
    assert "docs/verification-1.0.0.md#readme-history-archive" in text
    assert "3.11\u20133.15" in text
    assert "9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b" in text


def test_archived_readme_does_not_use_its_previous_relative_link_base():
    history = (ROOT / "docs/verification-1.0.0.md").read_text(encoding="utf-8")
    archive = history.split("## README History Archive\n", 1)[1]
    assert "(docs/verification-1.0.0.md)" not in archive
    assert "(.github/workflows/ci.yml)" not in archive
    for digest in ("9aaa6035d21381fe531cc480d137df1fcd25d7f24c9a395c72d107280d0f9e65",
                   "4b7cd1fc2269bf464b3c8ed13d36c85dbca3196ea44835bc5c373f49b86a7b2b",
                   "f1884f3ff58d61dd63a477ae9fb3d4b367895e513bbae159885f176770e24680"):
        assert archive.count(digest) == 2
