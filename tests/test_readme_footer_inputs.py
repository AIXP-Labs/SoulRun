"""External footer compatibility keeps uniqueness, completeness and exact rows."""
from __future__ import annotations

import pytest

import test_docs as docs


def tables(language, has_soulrun):
    name, marker = ("README.md", "**(this project)**") if language == "en" else ("README_CN.md", "**\uff08\u672c\u9879\u76ee\uff09**")
    heading = "## AIXP Labs [aixp.dev](https://aixp.dev)"
    ours = docs._footer((docs.ROOT / name).read_text(encoding="utf-8"), heading)
    rows = docs._rows(ours)
    external = []
    for project, row in rows.items():
        if project == "SoulRun":
            if not has_soulrun:
                continue
            row = row.replace(" " + marker, "")
        if project == "SoulBot":
            row = row.replace(" | soulbot.dev |", " " + marker + " | soulbot.dev |")
        external.append(row)
    return ours, "\n".join(external), marker


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("has_soulrun", [False, True])
def test_external_table_may_or_may_not_already_list_soulrun(language, has_soulrun):
    ours, external, marker = tables(language, has_soulrun)
    docs._assert_ecosystem_rows(ours, external, marker)


@pytest.mark.parametrize("project", ["HSAW", "SoulRun"])
@pytest.mark.parametrize("language", ["en", "zh"])
def test_duplicate_project_rows_are_rejected(language, project):
    ours, _, _ = tables(language, True)
    row = docs._rows(ours)[project]
    with pytest.raises(AssertionError, match="duplicate"):
        docs._rows(ours + "\n" + row)


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("has_soulrun", [False, True])
@pytest.mark.parametrize("project", ["HSAW", "SoulACP"])
@pytest.mark.parametrize("side,change", [("ours", "missing"), ("external", "missing"),
                                        ("ours", "duplicate"), ("external", "duplicate"),
                                        ("ours", "content"), ("external", "content")])
def test_other_projects_cannot_be_missing_duplicated_or_reworded(language, has_soulrun, project, side, change):
    ours, external, marker = tables(language, has_soulrun)
    text = ours if side == "ours" else external
    row = docs._rows(text)[project]
    if change == "missing":
        text = "\n".join(line for line in text.splitlines() if line != row)
    elif change == "duplicate":
        text += "\n" + row
    else:
        domain = "hsaw.dev" if project == "HSAW" else "soulacp.dev"
        text = text.replace(row, row.replace(domain, "incorrect.invalid"))
    ours, external = (text, external) if side == "ours" else (ours, text)
    with pytest.raises(AssertionError):
        docs._assert_ecosystem_rows(ours, external, marker)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_an_existing_soulrun_row_still_needs_exact_content(language):
    ours, external, marker = tables(language, True)
    external = external.replace(docs._rows(external)["SoulRun"],
                                docs._rows(external)["SoulRun"].replace("soulrun.dev", "incorrect.invalid"))
    with pytest.raises(AssertionError):
        docs._assert_ecosystem_rows(ours, external, marker)


END = "- **We are not beggars. We the People.**"
HEADING = "## AIXP Labs [aixp.dev](https://aixp.dev)"


def full_footer(language, has_soulrun):
    ours, external_rows, marker = tables(language, has_soulrun)
    rows = docs._rows(external_rows)
    external = []
    for line in ours.splitlines(keepends=True):
        if line.startswith("| ["):
            project = next(iter(docs._rows(line)))
            if project in rows:
                external.append(rows[project] + "\n")
        else:
            external.append(line)
    before, tail = "".join(external).split("\n---\n", 1)
    package, _ = docs.CHECK.current_versions(docs.ROOT)
    tail = tail.replace(f"Version: SoulRun V{package}. ", "Version: SoulBot V0.0.0. ")
    tail = tail.replace("SoulRun.dev", "SoulBot.dev").replace("www.soulrun.dev", "www.soulbot.dev")
    return ours, before + "\n---\n" + tail, marker, package


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("has_soulrun", [False, True])
@pytest.mark.parametrize("appendix", ["", "\n## Neutral host section\n\nHost-owned documentation.\n"])
def test_shared_footer_accepts_only_separate_document_sections(language, has_soulrun, appendix):
    ours, external, marker, package = full_footer(language, has_soulrun)
    docs._assert_ecosystem_footer(ours, external + appendix, marker, package)


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("has_soulrun", [False, True])
@pytest.mark.parametrize("change", ["shared-text", "missing-row", "duplicate-row", "wrong-row", "end-missing",
    "end-duplicate", "tail-plain", "end-inline", "shared-heading-after", "bad-level", "duplicate-heading", "row-moved"])
def test_shared_footer_boundary_never_hides_tampering(language, has_soulrun, change):
    ours, external, marker, package = full_footer(language, has_soulrun)
    row = docs._rows(external)["HSAW"]
    if change == "shared-text":
        external = external.replace("We are not beggars.", "Changed shared wording.")
    elif change == "missing-row":
        external = external.replace(row + "\n", "", 1)
    elif change == "duplicate-row":
        external = external.replace(row, row + "\n" + row, 1)
    elif change == "wrong-row":
        external = external.replace(row, row.replace("hsaw.dev", "incorrect.invalid"), 1)
    elif change == "end-missing":
        external = external.replace(END, "", 1)
    elif change == "end-duplicate":
        external += "\n" + END + "\n"
    elif change == "tail-plain":
        external += "\nUnframed trailing content.\n"
    elif change == "end-inline":
        external = external.replace(END, "`" + END + "`", 1)
    elif change == "shared-heading-after":
        common_heading = next(line for line in ours.splitlines() if line.startswith("## ") and line != HEADING)
        external += "\n" + common_heading + "\n\nA disguised shared section.\n"
    elif change == "bad-level":
        external += "\n### Not a separate top-level section\n"
    elif change == "duplicate-heading":
        external = external.replace(HEADING, HEADING + "\n\n" + HEADING, 1)
    else:
        assert change == "row-moved"
        external = external.replace(row + "\n", "", 1) + "\n## Neutral appendix\n\n" + row + "\n"
    with pytest.raises(AssertionError):
        docs._assert_ecosystem_footer(ours, external, marker, package)
