"""Mechanical bilingual facts; prose equivalence still requires human review."""
from __future__ import annotations

import ast
import json
import re
import tomllib
from collections import Counter

import pytest

from conftest import ROOT


def _section(text: str, heading: str) -> str:
    marker = f"### {heading}\n"
    assert text.count(marker) == 1
    return re.split(r"\n#{1,3} ", text.split(marker, 1)[1], maxsplit=1)[0]


def _argument_rows(text: str, heading: str) -> list[tuple[str, ...]]:
    rows = []
    for line in _section(text, heading).splitlines():
        if line.startswith("| `"):
            rows.append(tuple(re.findall(r"`([^`]+)`", line.split("|")[1])))
    assert rows and len(rows) == len(set(rows))
    return rows


def _assert_readme_facts(en: str, cn: str) -> None:
    assert _argument_rows(en, "Arguments") == _argument_rows(cn, "\u53c2\u6570")
    for pattern in (r"--[a-z][a-z-]*", r"ctx\.[a-z_]+", r"host\.[a-z_]+"):
        assert set(re.findall(pattern, en)) == set(re.findall(pattern, cn)), pattern
    manifest = json.loads((ROOT / "src/soulrun/engine_manifest.json").read_text(encoding="utf-8"))
    for text in (en, cn):
        assert manifest["digest"] in text
        assert "docs/verification-1.0.0.md" in text
        for option in ("execute", "cancel", "terminate"):
            assert f"`{option}`" in text


def _python_examples(text: str) -> list[str]:
    examples = []
    blocks = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)
    for index, block in enumerate(blocks):
        tree = ast.parse(block)
        if index == 0:
            # Only the introductory human request is translated; API literals stay exact.
            assignment = tree.body[1]
            assert isinstance(assignment, ast.Assign) and len(assignment.targets) == 1
            assert isinstance(assignment.targets[0], ast.Name) and assignment.targets[0].id == "message"
            assert isinstance(assignment.value, ast.Constant) and isinstance(assignment.value.value, str)
            assert assignment.value.value.strip()
            assignment.value = ast.Constant(value="localized-example-request")
        examples.append(ast.dump(tree, include_attributes=False))
    return examples


def test_readme_pairs_keep_mechanical_api_facts_aligned():
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    cn = (ROOT / "README_CN.md").read_text(encoding="utf-8")
    _assert_readme_facts(en, cn)
    assert _python_examples(en) == _python_examples(cn)


def test_translated_request_does_not_hide_a_changed_command_literal():
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    cn = (ROOT / "README_CN.md").read_text(encoding="utf-8")
    assert 'cmd="next-node"' in cn
    changed = cn.replace('cmd="next-node"', 'cmd="wrong-command"', 1)
    assert _python_examples(en) != _python_examples(changed)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong", "cli", "digest"])
def test_bilingual_drift_is_rejected(mutation):
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    cn = (ROOT / "README_CN.md").read_text(encoding="utf-8")
    row = next(line for line in cn.splitlines() if line.startswith("| `session_id` |"))
    if mutation == "missing":
        cn = cn.replace(row, "", 1)
    elif mutation == "duplicate":
        cn = cn.replace(row, row + "\n" + row, 1)
    elif mutation == "wrong":
        cn = cn.replace(row, row.replace("`session_id`", "`session_key`"), 1)
    elif mutation == "cli":
        cn = cn.replace("--machine-turn", "--machine-invalid")
    else:
        manifest = json.loads((ROOT / "src/soulrun/engine_manifest.json").read_text(encoding="utf-8"))
        cn = cn.replace(manifest["digest"], "0" * 64)
    with pytest.raises(AssertionError):
        _assert_readme_facts(en, cn)


def _constraints(text: str) -> Counter:
    return Counter(re.findall(r"`(>=[0-9][^`]*)`", text))


def test_dependency_pairs_match_declared_constraints_and_strict_ci():
    en = (ROOT / "DEPENDENCIES.md").read_text(encoding="utf-8")
    cn = (ROOT / "DEPENDENCIES_CN.md").read_text(encoding="utf-8")
    assert _constraints(en) == _constraints(cn)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dependencies"] == []
    for group in project["project"]["optional-dependencies"].values():
        for requirement in group:
            constraint = requirement[requirement.index(">="):]
            assert f"`{constraint}`" in en and f"`{constraint}`" in cn
    for page in ("CONTRIBUTING.md", "CONTRIBUTING_CN.md", "DEPENDENCIES.md", "DEPENDENCIES_CN.md"):
        text = (ROOT / page).read_text(encoding="utf-8")
        assert "python -m twine check --strict dist/*" in text
        assert "python -m twine check dist/*" not in text
    assert "python -m twine check --strict dist/*" in (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


@pytest.mark.parametrize("page", ["README.md", "README_CN.md"])
def test_intro_doubt_does_not_go_to_the_model(page):
    text = (ROOT / page).read_text(encoding="utf-8")
    block = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)[0]
    tree = ast.parse(block)
    branch = tree.body[3]
    assert isinstance(branch, ast.If)
    assert ast.dump(branch.test) == ast.dump(ast.parse("ctx.doubt", mode="eval").body)
    def calls(nodes):
        return [n.func.id for statement in nodes for n in ast.walk(statement)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "show_to_the_human" in calls(branch.body)
    assert "send_to_your_model" not in calls(branch.body)
    assert "send_to_your_model" in calls(branch.orelse)


def test_shipped_guide_matches_gate_publication_and_privacy():
    text = " ".join((ROOT / "src/soulrun/guide.txt").read_text(encoding="utf-8").split())
    assert "or earlier when the host records that sub-agent's return" not in text
    assert "never committed by" not in text
    assert "does not write its menu" in text
    assert "diagnostic" in text and "Cancel and terminate" in text
    assert "does not encrypt" in text


def test_governance_usage_does_not_require_a_specific_framework():
    text = (ROOT / "src/soulrun/soulrun_aiap/AIAP.md").read_text(encoding="utf-8")
    usage = text.split("## Usage\n", 1)[1].split("\n## ", 1)[0]
    assert "EXECUTE_ENGINE=true" not in usage
    assert "tests/requirements.txt" not in usage
    assert "SoulRun CLI or SDK" in usage
