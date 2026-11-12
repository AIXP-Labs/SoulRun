"""Check SoulRun's documentation: links, anchors, fenced blocks, local paths, credentials, versions and footers.

    python tools/check_docs.py                  # every SoulRun Markdown file, and the repository-wide rules
    python tools/check_docs.py README.md docs   # only these files or folders (no repository-wide rules)

Scanned: SoulRun's own Markdown - everything except the bundled engine (src/soulrun/soulrun_aiap, the engine's
own files), run data, kept engines and build output. Each file is checked for UTF-8, relative links that
resolve, fragments that exist (GitHub's heading anchors), balanced fenced blocks, fenced Python that parses,
machine-specific absolute paths, and credential shapes. The repository-wide rules add:

* versions - the footers and the contribution guides' stage line name the current package version, and no
  document names an old development version or the engine's old name;
* footers - the README pair ends with the AIXP Labs project table (SoulRun marked as this project), the
  disclaimer, the license line, the Axiom 0 line with the current version, and the Alignment & Philosophy
  block; the policy documents end with the Axiom 0 line; the other documents carry no footer.

The rules follow SoulBot's documentation gate (tools/check_docs.py in SoulBot), standard library only. Syntax
checks do not run examples, and no external website is fetched.

    python tools/check_docs.py --set-version 1.0.1   # SoulRun's version: the package and every footer, in one step
"""
from __future__ import annotations

import ast
import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy_rules  # noqa: E402  - the rules every privacy check shares

ROOT = Path(__file__).resolve().parent.parent
DOC_SUFFIXES = {".md"}
SKIP_DIR_NAMES = {".execution_cache", ".soulrun_cache", ".soulrun", ".engine_backups", ".git", ".pytest_cache",
                  ".ruff_cache", ".venv", "venv", "__pycache__", "build", "dist"}
ENGINE_DIRNAME = "soulrun_aiap"                     # src/soulrun/soulrun_aiap: the engine's own files

# ---- the shared footer --------------------------------------------------------------------------------------
DOMAIN = "www.soulrun.dev"
ALIGN = "Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulRun V{version}. {domain}"
LICENSE_LINE = "[Apache License 2.0](LICENSE) - Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev"
PROJECTS = ("HSAW", "AIZP", "AIIP", "AIKP", "AIJP", "AINP", "AILP", "AIVP", "AIRP", "AIBP", "AIAP", "AISP", "AISOP",
            "AIXPStore", "SoulSkill", "SoulAgent", "SoulBot", "SoulRun", "SoulACP")
# Rows SoulRun lists before SoulBot's table has them (10-15, the user's request); every other row is SoulBot's word for word.
NOT_YET_SOULBOTS = ("AIIP", "AIKP", "AIJP", "AIXPStore")
README_FOOTERS = {
    "README.md": {
        "heading": "## AIXP Labs [aixp.dev](https://aixp.dev)",
        "marker": "**(this project)**",
        "sections": ("## ⚠️ Disclaimer", "## License"),
        "anchor": '<a id="alignment-philosophy"></a>',
        "block": ("## ⚓ Alignment & Philosophy\n\n"
                  "### Axiom 0: [HSAW | Human Sovereignty and Wellbeing](https://hsaw.dev)\n\n"
                  "- **No HITL, HSAW.**\n"
                  "  *Human Sovereignty and Wellbeing is Axiom 0, requiring no hypocritical human-in-the-loop.*\n"
                  "- **No w.a.s.h, Real h.s.a.w.**\n"
                  "- **人非蝼蚁，人为道。**\n"
                  "- **We are not beggars. We the People.**\n"),
    },
    "README_CN.md": {
        "heading": "## AIXP Labs [aixp.dev](https://aixp.dev)",
        "marker": "**（本项目）**",
        "sections": ("## ⚠️ 免责声明", "## 许可证"),
        "anchor": '<a id="values-philosophy"></a>',
        "block": ("## ⚓ 价值观与哲学 (Alignment & Philosophy)\n\n"
                  "### Axiom 0: [HSAW | Human Sovereignty and Wellbeing](https://hsaw.dev)\n\n"
                  "- **No HITL, HSAW.**\n"
                  "  *人类主权与福祉是第零公理，无需虚伪的人机协同。*\n"
                  "- **No w.a.s.h, Real h.s.a.w.**\n"
                  "- **人非蝼蚁，人为道。**\n"
                  "- **We are not beggars. We the People.**\n"),
    },
}
POLICY_DOCS = ("CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "CONTRIBUTING_CN.md", "GOVERNANCE.md", "SECURITY.md")
REQUIRED_DOCS = (*README_FOOTERS, *POLICY_DOCS, "CHANGELOG.md", "DEPENDENCIES.md", "DEPENDENCIES_CN.md",
                 "GUIDE.md", "INSTALL.md", "docs/README.md")
ALIGN_ANY = re.compile(r"^Align Axiom 0: .*$", re.M)

# ---- versions -----------------------------------------------------------------------------------------------
RELEASE = r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?"
RELEASE_VERSION = re.compile(RELEASE)                # a release version: 1.0.1, 1.1.0rc1 (also an engine version)
# Where a document names SoulRun's own version: the footers, the stage line of the contribution guides and the head
# lines of the guides. --set-version writes every one; the gate checks every one.
VERSION_SPOTS = (re.compile(r"(Version: SoulRun V)([0-9][0-9A-Za-z.+-]*?)(\. <?www\.soulrun\.dev)"),
                 re.compile(r"(Stage Status \(V)([0-9][0-9A-Za-z.+-]*)(\))"),
                 re.compile(r"(阶段状态（V)([0-9][0-9A-Za-z.+-]*)(）)"),
                 re.compile(rf"(current version: V)({RELEASE})(, )"),
                 re.compile(rf"(当前版本：V)({RELEASE})(，)"),
                 re.compile(rf"(\| SoulRun V)({RELEASE})(，引擎 )"),
                 re.compile(rf"(本指南对应 SoulRun V)({RELEASE})(。)"))
# Where a document names the engine's version: written by tools/upgrade_engine.py, checked against the engine manifest.
ENGINE_SPOTS = (re.compile(rf"(SoulRun engine `)({RELEASE})(` \(`soulrun\.ENGINE_VERSION`\))"),
                re.compile(rf"(SoulRun 引擎 `)({RELEASE})(`（`soulrun\.ENGINE_VERSION`）)"),
                re.compile(rf"(，引擎 )({RELEASE})( \|)"))
# What no document may name any more: the old development versions and the engine's old name.
STALE = re.compile(r"7\.0\.0(?:-alpha\.\d+|a\d+(?:\.dev\d+)?)|\balpha\.\d+|\ba1\d\d\b|SoulBot Execute Engine|"
                   r"SoulBot 执行引擎|soulbot_execute_engine(?!_aiap)")

# ---- the per-file rules (as SoulBot's gate) -----------------------------------------------------------------
_FENCE_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<rest>.*)$")
_INLINE_LINK_RE = re.compile(r"!?\[[^\]\r\n]*\]\(\s*(?P<target><[^>\r\n]+>|[^)\s]+)")
_REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]\r\n]+\]:\s*(?P<target><[^>\r\n]+>|\S+)", re.MULTILINE)
_HTML_LINK_RE = re.compile(r"\b(?:href|src)\s*=\s*[\"'](?P<target>[^\"']+)[\"']", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
# A Setext heading: a line of text (not a list item, quote, table row or heading) underlined with === or ---.
_SETEXT_RE = re.compile(r"^ {0,3}(?![-*+>|#]|\d+[.)]\s)(\S[^\n]*?)[ \t]*\n {0,3}(?:=+|-+)[ \t]*$", re.MULTILINE)
# Where a link is not a link: inside inline code, or inside an HTML comment.
_CODE_SPAN_RE = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_EXPLICIT_ANCHOR_RE = re.compile(r"<(?:a|span)\b[^>]*\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
# A document names no place on one machine: any drive-letter path, and every home-folder form the shared privacy rules
# know (tools/privacy_rules.py, which also holds the credential shapes and the e-mail rule).
_LOCAL_PATHS = (re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][A-Za-z_]"), *privacy_rules.HOME_PATHS)
_SECRET_PATTERNS = privacy_rules.CREDENTIALS


@dataclass(frozen=True, order=True)
class Finding:
    """One documentation problem."""

    path: str
    line: int
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.detail}"


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _fences(text: str) -> tuple[list[tuple[int, str, str]], int | None, str]:
    """Closed fenced blocks as (opening line, language, body); the opening line of an unclosed one; the text
    with every fenced line blanked (line numbers and offsets kept)."""
    blocks: list[tuple[int, str, str]] = []
    visible: list[str] = []
    fence: str | None = None
    opening, language, body = 0, "", []
    for number, line in enumerate(text.splitlines(keepends=True), start=1):
        content = line.rstrip("\r\n")
        match = _FENCE_RE.match(content)
        marker = match.group("marker") if match else None
        if fence is None and marker is not None:
            fence, opening, body = marker, number, []
            info = match.group("rest").strip()
            language = info.split(maxsplit=1)[0].lower() if info else ""
        elif fence is not None:
            if marker is not None and marker[0] == fence[0] and len(marker) >= len(fence) and not match.group("rest").strip():
                blocks.append((opening, language, "\n".join(body)))
                fence = None
            else:
                body.append(content)
        else:
            visible.append(line)
            continue
        visible.append(" " * len(content) + line[len(content):])
    return blocks, (opening if fence is not None else None), "".join(visible)


def github_slug(value: str) -> str:
    """The anchor GitHub gives a Markdown heading: its text in lower case with only letters, digits, marks, "_", "-"
    and spaces kept (punctuation and symbols such as an arrow, a check mark or an emoji go), each space a "-"."""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = value.replace("`", "").replace("*", "").replace("~", "").strip().lower()
    value = "".join(c for c in value if c.isalnum() or c in {"-", "_", " "} or unicodedata.category(c).startswith("M"))
    return re.sub(r"\s", "-", value)


def _headings(text: str) -> list[str]:
    """Every heading in order: ATX (# Title) and Setext (Title underlined with === or ---), fences already blanked."""
    found = [(m.start(), m.group(1)) for m in _HEADING_RE.finditer(text)]
    found += [(m.start(), m.group(1)) for m in _SETEXT_RE.finditer(text)]
    return [title for _, title in sorted(found)]


def _blank(pattern: re.Pattern, text: str) -> str:
    """The text with each match turned into spaces (line ends kept, so line numbers stay right)."""
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def anchors(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    resolved = path.resolve()
    if resolved not in cache:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            cache[resolved] = set()
            return cache[resolved]
        found = {unquote(value) for value in _EXPLICIT_ANCHOR_RE.findall(text)}
        seen: dict[str, int] = {}
        for heading in _headings(_fences(text)[2]):
            base = github_slug(heading)
            if base:
                found.add(base if not seen.get(base) else f"{base}-{seen[base]}")
                seen[base] = seen.get(base, 0) + 1
        cache[resolved] = found
    return cache[resolved]


def _name(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def scan_file(path: Path, root: Path = ROOT, cache: dict[Path, set[str]] | None = None) -> list[Finding]:
    """The per-file rules for one Markdown file."""
    cache = {} if cache is None else cache
    name = _name(path, root)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [Finding(name, 1, "encoding", "not valid UTF-8")]
    blocks, unclosed, visible = _fences(text)
    findings = []
    if unclosed is not None:
        findings.append(Finding(name, unclosed, "fence", "unterminated fenced code block"))
    for opening, language, body in blocks:
        if language in {"py", "python"}:
            try:
                ast.parse(body)
            except SyntaxError as exc:
                findings.append(Finding(name, opening + (exc.lineno or 1), "python", f"invalid fenced Python: {exc.msg}"))
    for label, pattern in _SECRET_PATTERNS.items():
        findings += [Finding(name, _line_number(text, m.start()), "secret", label) for m in pattern.finditer(text)]
    kept: list[tuple[int, int]] = []                       # one finding a path, though two rules may see it
    for start, end in sorted((m.start(), m.end()) for pattern in _LOCAL_PATHS for m in pattern.finditer(text)):
        if not kept or start >= kept[-1][1]:
            kept.append((start, end))
    findings += [Finding(name, _line_number(text, start), "local-path", "machine-specific absolute path") for start, _ in kept]
    findings += [Finding(name, _line_number(text, at), "email", f"an e-mail address: {address}")
                 for address, at in privacy_rules.emails(text)]
    visible = _blank(_CODE_SPAN_RE, _blank(_HTML_COMMENT_RE, visible))   # a link in code or in a comment is not one
    targets = [(m, _INLINE_LINK_RE) for m in _INLINE_LINK_RE.finditer(visible)]
    targets += [(m, _REFERENCE_LINK_RE) for m in _REFERENCE_LINK_RE.finditer(visible)]
    targets += [(m, _HTML_LINK_RE) for m in _HTML_LINK_RE.finditer(visible)]
    for match, _ in sorted(targets, key=lambda item: item[0].start()):
        target = match.group("target").strip().strip("<>")
        split = urlsplit(target)
        if not target or target.startswith("//") or split.scheme or split.netloc or any(c in target for c in "{}$"):
            continue
        raw, fragment = unquote(split.path), unquote(split.fragment)
        line = _line_number(visible, match.start())
        # A link starting with / is read from the repository's root, as GitHub reads it.
        destination = path if not raw else (root / raw.lstrip("/") if raw.startswith("/") else path.parent / raw)
        if not destination.exists():
            findings.append(Finding(name, line, "link", f"missing target: {target}"))
        elif fragment and destination.is_file() and destination.suffix.lower() in DOC_SUFFIXES \
                and fragment not in anchors(destination, cache):
            findings.append(Finding(name, line, "anchor", f"missing fragment: {target}"))
    return findings


def doc_files(root: Path = ROOT) -> list[Path]:
    """SoulRun's own Markdown files under root."""
    found = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in DOC_SUFFIXES or not path.is_file():
            continue
        folders = path.relative_to(root).parts[:-1]
        if any(part in SKIP_DIR_NAMES for part in folders) or ENGINE_DIRNAME in folders:
            continue
        found.append(path)
    return found


def current_versions(root: Path = ROOT) -> tuple[str, str]:
    """(package version, engine version) as the package records them."""
    init = (root / "src" / "soulrun" / "__init__.py").read_text(encoding="utf-8")
    package = re.search(r'^__version__ = "([^"]+)"$', init, re.M).group(1)
    engine = json.loads((root / "src" / "soulrun" / "engine_manifest.json").read_text(encoding="utf-8"))["engine_version"]
    return package, engine


def version_findings(root: Path = ROOT) -> list[Finding]:
    package, engine = current_versions(root)
    findings = []
    for path in doc_files(root):
        text = path.read_text(encoding="utf-8")
        name = _name(path, root)
        for spots, current, what in ((VERSION_SPOTS, package, "the package"), (ENGINE_SPOTS, engine, "the engine")):
            for spot in spots:
                for match in spot.finditer(text):
                    if match.group(2) != current:
                        findings.append(Finding(name, _line_number(text, match.start()), "version",
                                                f"names version {match.group(2)}, {what} is {current}"))
        for match in STALE.finditer(text):
            findings.append(Finding(name, _line_number(text, match.start()), "stale",
                                    f"{match.group(0)!r} is an old development version or the engine's old name"))
    return findings


def _table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith("| [") and line.endswith("|"):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def readme_footer_findings(name: str, text: str, version: str) -> list[Finding]:
    """The README footer: project table, disclaimer, license, Axiom 0 line, Alignment & Philosophy block."""
    rule = README_FOOTERS[name]
    findings = []

    def problem(detail: str) -> None:
        findings.append(Finding(name, max(1, text.count("\n")), "footer", detail))

    start = text.rfind(rule["heading"])
    if start < 0:
        problem(f"no '{rule['heading']}' section")
        return findings
    footer = text[start:]
    rows = _table_rows(footer.split(rule["sections"][0])[0])
    names = tuple(re.match(r"\[([^\]]+)\]", row[0]).group(1) for row in rows)
    if names != PROJECTS:
        problem(f"the project table lists {', '.join(names)}; expected {', '.join(PROJECTS)}")
    marked = [row for row in rows if rule["marker"] in row[1]]
    if len(marked) != 1 or not marked[0][0].startswith("[SoulRun]"):
        problem(f"exactly one row, SoulRun's, must carry {rule['marker']}")
    for row in rows:
        project = re.match(r"\[([^\]]+)\]\((https://[^)]+)\)", row[0])
        if not project or project.group(2) != f"https://{project.group(1).lower()}.dev" \
                or row[-1] != f"{project.group(1).lower()}.dev":
            problem(f"the row '{row[0]}' does not link its .dev site the way the ecosystem's tables do")
    if f"\n{rule['sections'][0]}\n\n" not in footer:
        problem(f"no {rule['sections'][0]} section after the table")
    if f"{rule['sections'][1]}\n\n{LICENSE_LINE}\n" not in footer:
        problem(f"the {rule['sections'][1]} section must read: {LICENSE_LINE}")
    align = ALIGN.format(version=version, domain=f"<{DOMAIN}>")
    ending = f"---\n\n{align}\n\n{rule['anchor']}\n\n{rule['block']}"
    if not text.endswith(ending):
        problem(f"the file must end with the Axiom 0 line ('{align}'), {rule['anchor']} and the "
                "Alignment & Philosophy block, exactly")
    return findings


def footer_findings(root: Path = ROOT) -> list[Finding]:
    package, _ = current_versions(root)
    findings = []
    for name in REQUIRED_DOCS:
        if not (root / name).is_file():
            findings.append(Finding(name, 1, "missing", "a required document is missing"))
    for name in README_FOOTERS:
        if (root / name).is_file():
            findings += readme_footer_findings(name, (root / name).read_text(encoding="utf-8"), package)
    align = ALIGN.format(version=package, domain=DOMAIN)
    for name in POLICY_DOCS:
        path = root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if not text.endswith(f"\n---\n\n{align}\n"):
                findings.append(Finding(name, max(1, text.count("\n")), "footer",
                                        f"must end with '---' and the line: {align}"))
    footed = {*README_FOOTERS, *POLICY_DOCS}
    for path in doc_files(root):
        name = _name(path, root)
        if name not in footed:
            text = path.read_text(encoding="utf-8")
            for match in ALIGN_ANY.finditer(text):
                findings.append(Finding(name, _line_number(text, match.start()), "footer",
                                        "carries an Axiom 0 footer line; only the README pair and the policy documents do"))
    return findings


def _as_is(path: Path) -> str:
    """A file's text with its own line endings. A Windows checkout (core.autocrlf) has CRLF where the repository has
    LF; a version written into a file changes that version and nothing else, so restoring it gives back every byte."""
    return path.read_bytes().decode("utf-8")


def set_version(root: Path, version: str) -> list[str]:
    """SoulRun's version in the package (src/soulrun/__init__.py) and in every place a document names it (the footers,
    the stage line). Returns the files changed."""
    if not RELEASE_VERSION.fullmatch(version):
        raise SystemExit(f"{version!r} is not a release version such as 1.0.1")
    changed = []
    init = root / "src" / "soulrun" / "__init__.py"
    text = _as_is(init)
    new = re.sub(r'^__version__ = "[^"]+"(?=\r?$)', f'__version__ = "{version}"', text, count=1, flags=re.M)
    if new != text:
        init.write_bytes(new.encode("utf-8"))
        changed.append("src/soulrun/__init__.py")
    for path in doc_files(root):
        text = _as_is(path)
        new = text
        for spot in VERSION_SPOTS:
            new = spot.sub(lambda m: m.group(1) + version + m.group(3), new)
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            changed.append(_name(path, root))
    return changed


def set_engine_version(root: Path, version: str) -> list[str]:
    """The engine's version where a document names it (tools/upgrade_engine.py calls this). Returns the files changed."""
    if not RELEASE_VERSION.fullmatch(version):
        raise SystemExit(f"{version!r} is not a release version such as 1.0.1")
    changed = []
    for path in doc_files(root):
        text = _as_is(path)
        new = text
        for spot in ENGINE_SPOTS:
            new = spot.sub(lambda m: m.group(1) + version + m.group(3), new)
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            changed.append(_name(path, root))
    return changed


def check(root: Path = ROOT, paths: list[Path] | None = None) -> tuple[int, list[Finding]]:
    files = paths if paths is not None else doc_files(root)
    cache: dict[Path, set[str]] = {}
    findings = [f for path in files for f in scan_file(path, root, cache)]
    if paths is None:
        findings += version_findings(root) + footer_findings(root)
    return len(files), sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    if args[:1] == ["--set-version"]:
        if len(args) != 2:
            print("usage: python tools/check_docs.py --set-version X.Y.Z", file=sys.stderr)
            return 2
        changed = set_version(ROOT, args[1])
        print(f"version {args[1]}: {len(changed)} file(s) changed" + (f": {', '.join(changed)}" if changed else ""))
        return 0
    paths = None
    if args:
        missing = [a for a in args if not Path(a).exists()]
        if missing:
            print(f"docs: missing: {', '.join(missing)}", file=sys.stderr)
            return 2
        paths = []
        for arg in map(Path, args):
            paths += [arg] if arg.is_file() else doc_files(arg)
    count, findings = check(ROOT, paths)
    for finding in findings:
        print(finding)
    print(f"docs: {count} file(s), {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
