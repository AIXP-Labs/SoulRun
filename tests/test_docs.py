"""The documentation gate (tools/check_docs.py): the repository passes it, it catches what it claims to, and the
shared footers, policy sections and license match the ecosystem's (SoulBot's): SoulBot's own documents when it is
beside this repository, else as recorded from them in tests/soulbot_samples.json."""
from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

import soulbot_side
from conftest import ROOT


def _check_docs():
    spec = importlib.util.spec_from_file_location("check_docs", ROOT / "tools" / "check_docs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_docs"] = module            # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


CHECK = _check_docs()


def test_the_repository_passes_the_documentation_gate():
    count, findings = CHECK.check(ROOT)
    assert count >= 16
    assert findings == [], "\n".join(map(str, findings))


def test_the_gate_scans_soulrun_documents_only():
    names = {p.relative_to(ROOT).as_posix() for p in CHECK.doc_files(ROOT)}
    assert {"README.md", "GUIDE.md", "docs/README.md", "docs/guide/01-design.md", "examples/README.md"} <= names
    assert not [n for n in names if "soulrun_aiap" in n or n.startswith(("dist/", ".engine_backups/"))]


def test_every_documented_python_block_and_link_is_checked(tmp_path):
    (tmp_path / "other.md").write_text("# Other\n\n## A & B\n", encoding="utf-8")
    page = tmp_path / "page.md"
    page.write_text(
        "# Page\n\n"
        "[ok](other.md#a--b) [gone](missing.md) [bad anchor](other.md#nope) [web](https://example.org/x)\n\n"
        "```python\ndef broken(:\n```\n\n"
        "see C:" + "\\" + "Users" + "\\" + "someone\\x and /ho" + "me/someone/x\n\n"   # split: this file names no path
        "token ghp_" + "a" * 36 + "\n\n"
        "```text\nunclosed\n", encoding="utf-8")
    kinds = sorted(f.kind for f in CHECK.scan_file(page, tmp_path))
    assert kinds == ["anchor", "fence", "link", "local-path", "local-path", "python", "secret"]
    page.write_text("# Fine\n\n[ok](other.md#a--b) [here](#fine)\n\n```python\nx = 1\n```\n", encoding="utf-8")
    assert CHECK.scan_file(page, tmp_path) == []


def test_heading_anchors_follow_github():
    slug = CHECK.github_slug
    assert slug("A & B") == "a--b"
    assert slug("SoulRun 里的公理 0") == "soulrun-里的公理-0"
    assert slug("Axiom 0 in SoulRun") == "axiom-0-in-soulrun"
    assert slug("`ctx.kind` and **bold**") == "ctxkind-and-bold"
    assert slug("Heading → arrow") == "heading--arrow" and slug("Done ✓") == "done-"      # symbols go, as on GitHub
    assert slug("snake_case name") == "snake_case-name" and slug("Café 🚀 menu") == "café--menu"


def test_links_are_read_as_github_reads_them(tmp_path):
    """Setext headings have anchors; a link inside inline code or an HTML comment is not a link; a link that starts
    with / is read from the repository's root - and checked like any other."""
    (tmp_path / "GUIDE.md").write_text("# Guide\n", encoding="utf-8")
    page = tmp_path / "docs" / "page.md"
    page.parent.mkdir()
    page.write_text("Title Here\n==========\n\nSub part\n--------\n\n"
                    "[top](#title-here) [sub](#sub-part) [guide](/GUIDE.md)\n"
                    "Write `[x](missing.md)` or ``[y](gone.md)``; <!-- [z](hidden.md)\n[w](also.md) -->\n"
                    "[bad](/docs/no_such_file.md) [arrow](#no-such-heading)\n", encoding="utf-8")
    found = [(f.line, f.kind, f.detail) for f in CHECK.scan_file(page, tmp_path)]
    assert found == [(10, "link", "missing target: /docs/no_such_file.md"), (10, "anchor", "missing fragment: #no-such-heading")]


def _repo_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "repo"
    (copy / "src" / "soulrun").mkdir(parents=True)
    for name in ("__init__.py", "engine_manifest.json"):
        shutil.copy2(ROOT / "src" / "soulrun" / name, copy / "src" / "soulrun" / name)
    for path in CHECK.doc_files(ROOT):
        target = copy / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return copy


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, old
    path.write_bytes(text.replace(old, new).encode("utf-8"))


def test_the_readme_footers_are_checked(tmp_path):
    repo = _repo_copy(tmp_path)
    assert CHECK.footer_findings(repo) == []
    _edit(repo / "README.md", " **(this project)** | soulrun.dev |", " | soulrun.dev |")
    _edit(repo / "README.md", "inter-agent comms) | soulbot.dev |", "inter-agent comms) **(this project)** | soulbot.dev |")
    _edit(repo / "README_CN.md", "- **人非蝼蚁，人为道。**\n", "")
    package, _ = CHECK.current_versions(repo)
    _edit(repo / "GOVERNANCE.md", f"SoulRun V{package}. www", "SoulRun V9.9.9. www")
    (repo / "GUIDE.md").write_text((repo / "GUIDE.md").read_text(encoding="utf-8") + "\nAlign Axiom 0: x\n", encoding="utf-8")
    (repo / "INSTALL.md").unlink()
    found = {(f.path, f.kind) for f in CHECK.footer_findings(repo)}
    assert found == {("README.md", "footer"), ("README_CN.md", "footer"), ("GOVERNANCE.md", "footer"),
                     ("GUIDE.md", "footer"), ("INSTALL.md", "missing")}


def test_set_version_changes_the_package_and_every_footer_and_nothing_else(tmp_path):
    repo = _repo_copy(tmp_path)
    package, _ = CHECK.current_versions(repo)
    assert CHECK.version_findings(repo) == []
    init = repo / "src" / "soulrun" / "__init__.py"
    _edit(init, f'__version__ = "{package}"', '__version__ = "1.2.3"')
    behind = {f.path for f in CHECK.version_findings(repo)}
    assert {"README.md", "README_CN.md", "GOVERNANCE.md", "SECURITY.md", "CONTRIBUTING.md", "CONTRIBUTING_CN.md"} <= behind
    before = {p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") for p in CHECK.doc_files(repo)}
    changed = CHECK.set_version(repo, "1.2.4")
    assert "src/soulrun/__init__.py" in changed and "README.md" in changed and "CHANGELOG.md" not in changed
    assert CHECK.version_findings(repo) == [] and CHECK.footer_findings(repo) == []
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "Version: SoulRun V1.2.4. <www.soulrun.dev>" in readme and "AIAP V1.0.0" not in readme.replace(before["README.md"], "")
    for name, text in before.items():                    # only the version spots changed
        after = (repo / name).read_text(encoding="utf-8")
        assert after.replace("1.2.4", package) == text, name
    with pytest.raises(SystemExit):
        CHECK.set_version(repo, "not-a-version")


def test_every_version_spot_is_still_written_somewhere():
    """A document reworded so a spot no longer matches would leave its version unchecked and unchanged by
    --set-version: each spot must match in the documents as they are."""
    texts = [path.read_text(encoding="utf-8") for path in CHECK.doc_files(ROOT)]
    for spot in CHECK.VERSION_SPOTS + CHECK.ENGINE_SPOTS:
        assert any(spot.search(text) for text in texts), spot.pattern


def test_set_version_reaches_the_status_lines_and_the_guides(tmp_path):
    repo = _repo_copy(tmp_path)
    package, _ = CHECK.current_versions(repo)
    _edit(repo / "src" / "soulrun" / "__init__.py", f'__version__ = "{package}"', '__version__ = "1.2.3"')
    behind = {f.path for f in CHECK.version_findings(repo)}
    assert {"GUIDE.md", "INSTALL.md", "README.md", "README_CN.md", "CONTRIBUTING.md", "CONTRIBUTING_CN.md"} <= behind
    CHECK.set_version(repo, "1.2.3")
    assert CHECK.version_findings(repo) == []


def test_the_engine_version_is_checked_and_set_apart_from_the_package_version(tmp_path):
    repo = _repo_copy(tmp_path)
    package, engine = CHECK.current_versions(repo)
    manifest = repo / "src" / "soulrun" / "engine_manifest.json"
    _edit(manifest, f'"engine_version": "{engine}"', '"engine_version": "2.0.1"')
    behind = CHECK.version_findings(repo)
    assert {f.path for f in behind} >= {"DEPENDENCIES.md", "DEPENDENCIES_CN.md", "GUIDE.md"}
    assert all("the engine is 2.0.1" in f.detail for f in behind)
    before = {p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") for p in CHECK.doc_files(repo)}
    changed = CHECK.set_engine_version(repo, "2.0.1")
    assert "DEPENDENCIES.md" in changed and CHECK.version_findings(repo) == []
    for name, text in before.items():                    # only the engine spots changed; the package version stays
        assert (repo / name).read_text(encoding="utf-8").replace("2.0.1", engine) == text, name
    assert CHECK.current_versions(repo)[0] == package
    with pytest.raises(SystemExit):
        CHECK.set_engine_version(repo, "../2.0.1")


def test_setting_a_version_keeps_each_files_line_endings(tmp_path):
    """A Windows checkout (core.autocrlf, as on GitHub's Windows runners) has CRLF where the repository has LF.
    Setting a version changes the version only: setting the old one back gives back every byte, which
    tools/upgrade_engine.py --restore relies on."""
    repo = _repo_copy(tmp_path)
    package, engine = CHECK.current_versions(repo)
    files = [repo / "src" / "soulrun" / "__init__.py", *CHECK.doc_files(repo)]
    for path in files:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    before = {path: path.read_bytes() for path in files}
    assert "src/soulrun/__init__.py" in CHECK.set_version(repo, "1.2.4") and CHECK.current_versions(repo)[0] == "1.2.4"
    assert "DEPENDENCIES.md" in CHECK.set_engine_version(repo, "2.0.1")
    for path in files:
        data = path.read_bytes()
        assert b"\n" not in data.replace(b"\r\n", b""), f"{path.name} lost its CRLF"
    CHECK.set_version(repo, package)
    CHECK.set_engine_version(repo, engine)
    assert {path: path.read_bytes() for path in files} == before


def test_an_old_development_version_or_engine_name_in_a_document_is_found(tmp_path):
    repo = _repo_copy(tmp_path)
    guide = repo / "GUIDE.md"
    old = "7.0.0" + "-alpha.1"                           # spelled apart: this file must not trip the rule itself
    guide.write_text(guide.read_text(encoding="utf-8") + f"\nThe engine {old}, the SoulBot " + "Execute Engine.\n", encoding="utf-8")
    kinds = [(f.path, f.kind) for f in CHECK.version_findings(repo)]
    assert kinds.count(("GUIDE.md", "stale")) == 2


def _footer(text: str, heading: str) -> str:
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == heading]
    assert len(starts) == 1, "the shared footer needs one unambiguous heading"
    return "".join(lines[starts[0]:])


def _shared_footer(text: str) -> str:
    heading = "## AIXP Labs [aixp.dev](https://aixp.dev)"
    end = "- **We are not beggars. We the People.**"
    lines = text.splitlines(keepends=True)
    assert lines and lines[0].rstrip("\r\n") == heading
    assert sum(line.rstrip("\r\n") == heading for line in lines) == 1, "duplicate shared heading"
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == end]
    assert len(ends) == 1, "the shared footer needs one standalone closing line"
    common, following = "".join(lines[:ends[0] + 1]), lines[ends[0] + 1:]
    if following:
        separated = 0
        while following and following[0] in ("\n", "\r\n"):
            separated += 1
            following = following[1:]
        assert separated and following, "unframed trailing content"
        assert re.fullmatch(r"## \S.*", following[0].rstrip("\r\n")), "a separate H2 section is required"
        shared_titles = {line[3:].rstrip("\r\n") for line in common.splitlines(keepends=True) if line.startswith("## ")}
        for line in following:
            match = re.match(r"^#{1,6}[ \t]+(.+)$", line.rstrip("\r\n"))
            assert match is None or match[1].rstrip() not in shared_titles, "disguised duplicate shared section"
    return common


def _rows(footer: str) -> dict[str, str]:
    rows = {}
    for line in footer.splitlines():
        if line.startswith("| ["):
            match = re.match(r"\| \[([^\]]+)\]", line)
            assert match is not None, "malformed project row"
            name = match.group(1)
            assert name not in rows, f"duplicate project: {name}"
            rows[name] = line
    return rows


def _assert_ecosystem_rows(mine: str, soulbot: str, marker: str) -> None:
    my_rows, its_rows = _rows(mine), _rows(soulbot)
    ahead = [name for name in CHECK.NOT_YET_SOULBOTS if name not in its_rows]
    assert list(my_rows) == list(CHECK.PROJECTS)
    required = set(CHECK.PROJECTS) - set(CHECK.NOT_YET_SOULBOTS) - {"SoulRun"}
    assert required <= set(its_rows), "missing non-optional project"
    assert [name for name in my_rows if name not in ahead] == [
        *[name for name in its_rows if name not in ("SoulRun", "SoulACP")], "SoulRun", "SoulACP"]
    for name, row in its_rows.items():
        own = my_rows[name].replace(f" {marker}", "") if name == "SoulRun" else my_rows[name]
        external = row.replace(f" {marker}", "") if name == "SoulBot" else row
        assert own == external, name


@pytest.mark.parametrize(("ours", "theirs", "marker"), [("README.md", "README.md", "**(this project)**"),
                                                       ("README_CN.md", "README_CN.md", "**（本项目）**")])
def test_the_readme_footer_is_the_ecosystems(ours, theirs, marker):
    heading = "## AIXP Labs [aixp.dev](https://aixp.dev)"
    mine = _footer((ROOT / ours).read_text(encoding="utf-8"), heading)
    soulbot = soulbot_side.readme_footer(theirs)
    package, _ = CHECK.current_versions(ROOT)
    _assert_ecosystem_footer(mine, soulbot, marker, package)


def _assert_ecosystem_footer(mine: str, soulbot: str, marker: str, package: str) -> None:
    mine, soulbot = _shared_footer(mine), _shared_footer(soulbot)
    _assert_ecosystem_rows(mine, soulbot, marker)
    # Compare every byte of the shared notice; unrelated document sections stay in the raw fixture.
    tail = soulbot.split("\n---\n", 1)[1].replace("SoulBot.dev", "SoulRun.dev").replace("www.soulbot.dev", "www.soulrun.dev")
    tail = re.sub(r"Version: SoulBot V\S+?\. ", f"Version: SoulRun V{package}. ", tail)
    assert mine.split("\n---\n", 1)[1] == tail


# Sections SoulBot has and SoulRun words differently or does not need: SoulRun proposes host examples rather
# than agent examples, ships no AISOP/AIAP packages of its own, and shares the executor layer with SoulBot.
NOT_SOULRUNS = {
    "CONTRIBUTING.md": {"### Proposing a New Agent Example", "### AISOP / AIAP Contributions"},
    "CONTRIBUTING_CN.md": {"### 提议新代理示例", "### AISOP / AIAP 贡献"},
    "GOVERNANCE.md": {"### 3. The Executor Layer (`soulbot.dev`)"},
}


@pytest.mark.parametrize("name", ["CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "CONTRIBUTING_CN.md", "GOVERNANCE.md", "SECURITY.md"])
def test_the_policy_documents_have_soulbots_sections_and_footer(name):
    package, _ = CHECK.current_versions(ROOT)
    theirs = soulbot_side.policy_document(name)
    mine = (ROOT / name).read_text(encoding="utf-8")
    _assert_ecosystem_policy(name, mine, theirs, package)


def _assert_ecosystem_policy(name: str, mine: str, theirs: dict, package: str) -> None:
    mine_headings = re.findall(r"^##+ .+$", mine, re.M)
    assert len(mine_headings) == len(set(mine_headings)), "duplicate local policy heading"
    assert len(theirs["headings"]) == len(set(theirs["headings"])), "duplicate external policy heading"
    assert theirs["last_line"].startswith("Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulBot V")
    assert mine.rstrip().splitlines()[-1] == f"Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulRun V{package}. www.soulrun.dev"
    missing = {h for h in theirs["headings"] if h.replace("SoulBot", "SoulRun") not in mine.splitlines()}
    assert missing <= NOT_SOULRUNS.get(name, set()), missing


def test_license_and_notice_follow_soulbots():
    import hashlib
    mine = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert hashlib.sha256(mine.encode("utf-8")).hexdigest() == soulbot_side.license_as_soulruns_sha256()
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8").splitlines()
    assert notice[1] == "Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev"
    assert notice[3:5] == ["This product includes software developed at", "AIXP Labs (https://aixp.dev/ | https://soulrun.dev/)."]


def test_an_email_address_in_a_document_is_found_and_soulruns_own_is_not(tmp_path):
    page = tmp_path / "page.md"
    address = "someone" + "@" + "mail.example.org"                      # put together here: this file holds none
    page.write_text(f"# Page\n\nWrite to {address}, or to noreply@soulrun.dev.\n", encoding="utf-8")
    assert [(f.kind, f.detail) for f in CHECK.scan_file(page, tmp_path)] == [("email", f"an e-mail address: {address}")]
