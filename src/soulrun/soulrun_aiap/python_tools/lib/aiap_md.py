"""AIAP.md frontmatter parsing, governance hash, trust-level normalisation.

Own implementation written from the AIAP V1.0.0 specification (§3.1–§3.5, §16.5, §18.1,
Appendix B) and docs/topics/security-model.md (hash algorithm steps). Zero third-party deps:
the YAML subset parser below covers the constructs used by AIAP.md frontmatter (scalars,
nested mappings, block lists, list-of-mappings, inline [a, b] lists, comments).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


class FrontmatterError(ValueError):
    """AIAP.md frontmatter missing or not parseable by the YAML subset."""


GOVERNANCE_FIELDS = ("protocol", "authority", "seed", "executor", "axiom_0", "governance_mode")
PROJECT_FIELDS = ("name", "version", "pattern", "flow_format", "summary", "tools", "modules", "license")
REQUIRED_FIELDS = GOVERNANCE_FIELDS + PROJECT_FIELDS
OPTIONAL_FIELDS = (
    # §3.2 basic
    "governance_hash", "quality", "description", "tags", "author", "copyright", "tool_dirs", "capabilities",
    # §3.2 security & runtime
    "trust_level", "permissions", "runtime",
    # §3.2 engineering
    "status", "deprecated_date", "successor", "intent_examples", "discovery_keywords",
    "dependencies", "min_protocol_version", "benchmark", "identity",
    # Appendix B / E / §9
    "terms_url", "contact", "insights", "sub_aiaps",
)
KNOWN_FIELDS = frozenset(REQUIRED_FIELDS + OPTIONAL_FIELDS)
FIXED_VALUES = {
    "authority": "aiap.dev", "seed": "aisop.dev", "executor": "soulrun.dev",
    "axiom_0": "Human_Sovereignty_and_Wellbeing",
}
GOVERNANCE_MODES = ("NORMAL", "DEV")
FLOW_FORMATS = ("mermaid", "jsonflow", "hybrid")
STATUSES = ("draft", "active", "deprecated", "archived")
SEALS = {
    "NORMAL": "Align Axiom 0: Human Sovereignty and Wellbeing. Version: AIAP V1.0.0. www.aiap.dev",
    "DEV": "[L0_BOOT: Success] [L1_REPORT: Success] [endNode_Align Axiom 0: Human Sovereignty and Wellbeing]. Version: AIAP V1.0.0. www.aiap.dev",
}
PATTERN_RE = re.compile(r"^[A-G](\+[A-G])*$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
PLAIN_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SPDX_RE = re.compile(r"^[A-Za-z0-9.+-]+$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
HEX16_RE = re.compile(r"^[0-9a-f]{16}$")


# ---------------------------------------------------------------------------
# YAML subset
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.\-]*)\s*:(?:\s+(.*))?$")


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _split_inline(s: str) -> list[str]:
    parts, cur, quote, depth = [], [], None, 0
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            cur.append(ch)
        elif ch in "[{":
            depth += 1
            cur.append(ch)
        elif ch in "]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail or parts:
        parts.append(tail)
    return [p for p in parts if p != ""]


def _parse_scalar(s: str, lineno: int):
    s = s.strip()
    if s == "":
        return None
    if s[0] == '"' and s[-1] == '"' and len(s) >= 2:
        return bytes(s[1:-1], "utf-8").decode("unicode_escape") if "\\" in s else s[1:-1]
    if s[0] == "'" and s[-1] == "'" and len(s) >= 2:
        return s[1:-1].replace("''", "'")
    if s[0] == "[" and s[-1] == "]":
        return [_parse_scalar(p, lineno) for p in _split_inline(s[1:-1])]
    if s[0] == "{" and s[-1] == "}":
        result = {}
        for pair in _split_inline(s[1:-1]):
            key, sep, value = pair.partition(":")
            if not sep:
                raise FrontmatterError(f"line {lineno}: bad inline mapping entry {pair!r}")
            result[key.strip().strip("'\"")] = _parse_scalar(value, lineno)
        return result
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", "none"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _parse_block(items, i, indent):
    if items[i][1].startswith("- ") or items[i][1] == "-":
        return _parse_list(items, i, indent)
    return _parse_map(items, i, indent)


def _parse_map(items, i, indent):
    result = {}
    while i < len(items) and items[i][0] == indent and not (items[i][1].startswith("- ") or items[i][1] == "-"):
        _, text, lineno = items[i]
        m = _KEY_RE.match(text)
        if not m:
            raise FrontmatterError(f"line {lineno}: cannot parse mapping entry {text!r}")
        key, rest = m.group(1), (m.group(2) or "").strip()
        i += 1
        if rest == "":
            if i < len(items) and (items[i][0] > indent or
                                   (items[i][0] == indent and (items[i][1].startswith("- ") or items[i][1] == "-"))):
                value, i = _parse_block(items, i, items[i][0])
            else:
                value = None
        else:
            value = _parse_scalar(rest, lineno)
        result[key] = value
    if i < len(items) and items[i][0] > indent:
        raise FrontmatterError(f"line {items[i][2]}: unexpected indentation")
    return result, i


def _parse_list(items, i, indent):
    result = []
    while i < len(items) and items[i][0] == indent and (items[i][1].startswith("- ") or items[i][1] == "-"):
        _, text, lineno = items[i]
        body = text[1:].strip()
        i += 1
        if body == "":
            if i < len(items) and items[i][0] > indent:
                value, i = _parse_block(items, i, items[i][0])
            else:
                value = None
        elif _KEY_RE.match(body) and not body.startswith(("'", '"', "[", "{")):
            sub_indent = items[i][0] if i < len(items) and items[i][0] > indent else indent + 2
            synthetic = [(sub_indent, body, lineno)]
            while i < len(items) and items[i][0] > indent:
                synthetic.append(items[i])
                i += 1
            value, consumed = _parse_map(synthetic, 0, sub_indent)
            if consumed != len(synthetic):
                raise FrontmatterError(f"line {synthetic[consumed][2]}: unexpected content in list item")
        else:
            value = _parse_scalar(body, lineno)
        result.append(value)
    return result, i


def parse_yaml_subset(text: str) -> dict:
    items = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw.replace("\t", "    "))
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        items.append((indent, line.strip(), n))
    if not items:
        return {}
    if items[0][0] != 0:
        raise FrontmatterError(f"line {items[0][2]}: frontmatter must start at column 0")
    value, i = _parse_map(items, 0, 0)
    if i != len(items):
        raise FrontmatterError(f"line {items[i][2]}: unexpected content {items[i][1]!r}")
    return value


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split an AIAP.md into (frontmatter dict, markdown body)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("missing opening --- line")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise FrontmatterError("missing closing --- line")
    return parse_yaml_subset("\n".join(lines[1:end])), "\n".join(lines[end + 1:])


def load_aiap_md(path: str | Path) -> tuple[dict, str]:
    return parse_frontmatter(Path(path).read_text(encoding="utf-8-sig"))


def closing_seal(body: str) -> str | None:
    """Last non-empty line of the markdown body (AIAP §3.5 file ending)."""
    for line in reversed(body.splitlines()):
        if line.strip():
            return line.strip()
    return None


# ---------------------------------------------------------------------------
# Governance hash (AIAP §18.1; security-model.md algorithm steps)
# ---------------------------------------------------------------------------

def governance_hash(aiap_dir: str | Path, pattern: str = "*.aisop.json") -> dict:
    """1 collect *.aisop.json, 2 sort by path bytes, 3 CRLF->LF, 4 strip trailing newlines,
    5 concatenate, 6 SHA-256. canonical = first 16 hex chars."""
    directory = Path(aiap_dir)
    files = sorted(directory.glob(pattern), key=lambda p: p.name.encode("utf-8"))
    stream = b"".join(p.read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n") for p in files)
    hex64 = hashlib.sha256(stream).hexdigest()
    return {"hex64": hex64, "canonical": hex64[:16], "files": [p.name for p in files]}


def match_governance_hash(declared, computed: dict) -> str:
    """MATCH_CANONICAL | MATCH_LEGACY_SHA256_PREFIX | MATCH_LEGACY_BARE64 | MISMATCH | MISSING | INVALID"""
    if declared is None or declared == "":
        return "MISSING"
    if not isinstance(declared, str):
        return "INVALID"
    d = declared.strip().lower()
    if d.startswith("sha256:"):
        return "MATCH_LEGACY_SHA256_PREFIX" if d[7:] == computed["hex64"] else "MISMATCH"
    if HEX64_RE.match(d):
        return "MATCH_LEGACY_BARE64" if d == computed["hex64"] else "MISMATCH"
    if HEX16_RE.match(d):
        return "MATCH_CANONICAL" if d == computed["canonical"] else "MISMATCH"
    return "INVALID"


# ---------------------------------------------------------------------------
# Trust level (AIAP §16.5)
# ---------------------------------------------------------------------------

def normalize_trust_level(value):
    """int 0-4 -> int; "T3"/"t3"/"3" -> 3; {"level": 3} -> 3; other non-empty str -> str; invalid -> None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 4 else None
    if isinstance(value, float):
        return None
    if isinstance(value, dict):
        return normalize_trust_level(value.get("level"))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        m = re.fullmatch(r"[Tt]?([0-4])", s)
        if m:
            return int(m.group(1))
        return s
    return None


def is_semver(value) -> bool:
    return isinstance(value, str) and bool(SEMVER_RE.match(value))


def is_plain_semver(value) -> bool:
    return isinstance(value, str) and bool(PLAIN_SEMVER_RE.match(value))
