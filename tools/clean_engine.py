"""Turn an engine tree into SoulRun's engine: the runtime files only, SoulRun's name and version, no development history.

    python tools/clean_engine.py <engine tree> <output folder> --engine-version 1.0.0   # write the cleaned engine
    python tools/clean_engine.py --check <folder>                                       # what still looks like history

What changes:
  * files - only what runs is kept: an engine tree's own tests, release notes, test configuration and replay
    tooling stay out;
  * identity - the engine's name, ids and the notice on generated answers say SoulRun; its version is the one given;
  * history - development notes come out: version-series markers, references to internal planning documents, to
    individual runs and to who decided what, and machine-specific example paths. Comments and docstrings are
    cleaned thoroughly; texts the engine hands to a model or a human are cleaned conservatively, one reference at
    a time, and every such change can be listed (--show-strings).

What does not change: program logic and structure. Names that other software relies on stay as they are - the
SOULBOT_* environment variables a host sets, the host modules named in host contracts, business program names,
the AIAP protocol's fixed governance values, the folder name a SoulBot host looks for. tools/upgrade_engine.py runs
this on every engine it brings in. Every Python file must parse to the same structure as before (only text may
change), and --check must find nothing, or the step fails.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

DROP_DIRS = {"tests", "__pycache__", ".pytest_cache", ".execution_cache", "node_modules"}
DROP_FILES = {"pytest.ini", "tools/replay_v6_cache.py"}
DROP_PREFIXES = ("RELEASE",)
TEXT_SUFFIXES = {".py", ".json", ".md", ".txt"}    # an engine is these and nothing else: anything more stays out

# ---- identity -----------------------------------------------------------------------------------------------
IDENTITY = (
    ("SoulBot Execute Engine v7 core", "SoulRun engine"),
    ("SoulBot Execute Engine", "SoulRun engine"),
    ("SoulBot 执行引擎", "SoulRun 引擎"),
    ("SoulBot 実行エンジン", "SoulRun エンジン"),
    ("SoulBot 실행 엔진", "SoulRun 엔진"),
    ("dev.soulbot.execute_engine", "dev.soulrun.engine"),
    ("urn:soulbot:final-answer:1", "urn:soulrun:final-answer:1"),
    ("AIXP Labs AIXP.dev | SoulBot.dev", "AIXP Labs AIXP.dev | SoulRun.dev"),
    ("Execute Engine rule contract", "SoulRun engine rule contract"),
    ("author: SoulBot.dev", "author: SoulRun.dev"),
    ('"author": "SoulBot.dev"', '"author": "SoulRun.dev"'),
)
ENGINE_ID = re.compile(r"soulbot_execute_engine(?!_aiap)")       # the id, never the folder a SoulBot host looks for
# An example path naming a folder of one machine becomes the engine's own neutral example, D:/dir/<file> (or
# /home/user/<file> for a home folder): with forward slashes or backslashes, single or escaped, and network shares.
MACHINE_PATHS = (
    (re.compile(r"\b[A-Z]:(?:/|\\{1,2})(?!dir(?:/|\\))(?:[\w.-]+(?:/|\\{1,2}))*([\w.-]+)"), r"D:/dir/\1"),
    # \\server\share\...: a server name has three characters or more ("\\n\\n" is an escaped line break, not a share)
    (re.compile(r"(?<![\w\\])\\{2,4}[A-Za-z][\w.-]{2,}(?:\\{1,2}[\w.$-]+)*\\{1,2}([\w.$-]+)"), r"D:/dir/\1"),
    (re.compile(r"(?<![\w.])/(?:home|Users)/(?!user/)[\w.-]+/(?:[\w.-]+/)*([\w.-]+)"), r"/home/user/\1"),
)
VERSION_LITERAL = re.compile(r"7\.0\.0-alpha\.\d+")

# ---- references -----------------------------------------------------------------------------------------------
# E4, H3, B-3, B-1b, P1.5, F4', S3′, C2' (a letter or two with a number) and GA (two capitals standing alone).
CODE = r"(?:fix\s+)?(?:[A-Z]{1,2}-?\d+[a-z]?(?:\.\d+)?|[A-Z]{1,2}(?![A-Za-z]))['′]?(?![\w])"
ALPHA = rf"[Aa]lpha[ ._]?\d+[a-z]?(?:\s+{CODE})*"
ALPHAS = rf"(?:{ALPHA}(?:\s*(?:/|,|&|\+|and)\s*(?:{ALPHA}|\.?\d+(?![\d.])))*)"
SECTION = (r"(?:\s*§\s*[\d.]*\d[a-z.\dA-Z]*|\s+section\s*\d+(?:\.\d+)*|\s+(?:spec|plan|final_plan|item|row|steps?)\b(?:\s+[\d\-]+)?"
           r"|\s+#\d+|\s+\d+[a-z]\b|\s+v\d+\.\d+|\s+R-xx|\s+I-xx|\s+" + CODE + r")*")
DOCREF = rf"(?:(?:(?:the\s+)?04 series\s+|v7\s+)?(?:docs?|plans?)\s+\d{{1,3}}[a-z]?(?:\s*(?:/|,|&|and)\s*\d{{1,3}}[a-z]?)*{SECTION})"
PLANREF = rf"(?:final_plan{SECTION}(?:\s+Q\d+\s*[甲乙丙丁]?)?|spec\s*\d*\s*§\s*[\d.]*\d[a-z]?|spec\d+{SECTION}|04 series\b)"
NUMS = r"\d+(?:\s*(?:->|/|,|&|and)\s*\d+)*"
RUNREF = (rf"(?:\b(?:production|isolated|live)\s+(?:(?:caches|cache|runs|run|replays|replay|candidates|candidate)\b\s*[/ ]?{NUMS}|{NUMS})"
          rf"|\bcaches?\s*[/ ]{NUMS})")
USERREF = r"(?:\buser\s+(?:ruling(?:\s+\d{4}-\d\d-\d\d)?|\d{4}-\d\d-\d\d)(?:\s*「[^」]*」)?)"
V6REF = r"(?:\bv6(?:\.\d+)*(?:\s+[\w.:/]+(?:\s+/\s+[\w.:/]+)*)?)"
REF_TOKEN = re.compile(
    rf"{ALPHA}|\b04 series\b|\b(?:docs?|plans?)\s+\d{{1,3}}\b|\bcaches?\s*[/ ]\d+|\b(?:production|isolated|live)\s+(?:caches?|runs?|replays?)\s*[/ ]?\d|"
    rf"\bfinal_plan\b|\ba\d{{3}}\b|"
    rf"\bv7\b|\bv6(?:\.\d+)*\b|\bspec\s*\d*\s*§|\bspec\d+|\b\d{{1,3}}\s*号|\bcodex\d*\b|\bcycle\s?\d+\b|\buser\s+(?:ruling|\d{{4}}-\d\d-\d\d)",
    re.I)
FILLER = re.compile(r"(?i)\bR/I\b|\b(?:see|per|cf|also|and|the|of|in|incident|series|section|spec|plan|item|items|row|fix|example|review|"
                    r"references?|\d+|"
                    r"r\d+|n\d+)\b|§\s*[\d.]*|" + CODE + r"|[甲乙丙丁]|[\s,;:/&+.\-–—()′']")
PARENS = re.compile(r"\(([^()]*)\)")
# A note in brackets that dates a rule or a later addition - "(first rule, 2026-09-21)", "(追记: 2026-09-06 ...)" - is
# history in any text, a --help text as much as a comment.
DATED_NOTE = re.compile(r"\s*\((?=[^()]*\d{4}-\d\d-\d\d)[^()]*(?:\brules?\b|\bruling\b|\bdecided\b|\bnote\b|追记)[^()]*\)")
MARK = rf"(?:{ALPHAS}|{DOCREF}|{PLANREF}|r\d+)"
MARK_TEXT = rf"(?:{ALPHAS}|{DOCREF}|{PLANREF})"          # in a text a model reads, "r1:" may be the text's own label
LABEL = r"(?:\s+(?:review\s+)?fix(?:\s+[A-Z]\b)?|\s+[一-鿿]+(?:\s*\([A-Z]+\))?|\s+read side|\s+process evidence|\s+envelope)?"
LEAD = re.compile(rf"^(\s*(?:-{{2,}}\s*)?)(?:{MARK}(?:\s*\([^()]*\))?{LABEL}\s*(?:[,;/]\s*)?)+\s*[:\-–—](?:\s+|$)")
LEAD_TEXT = re.compile(rf"^(\s*(?:-{{2,}}\s*)?)(?:{MARK_TEXT}(?:\s*\([^()]*\))?{LABEL}\s*(?:[,;/]\s*)?)+\s*[:\-–—](?:\s+|$)")
ONLY_MARK = re.compile(rf"^\s*(?:-{{2,}}\s*)?(?:{MARK}{LABEL}\s*(?:[,;/]\s*)?)+[\s\-:]*$")
PREPS = r"(?i:per|see|cf\.?|from|since|as of|as in)"
INLINE = re.compile(rf"\s*,?\s*\b{PREPS}\s+(?:{DOCREF}|{RUNREF}|{ALPHAS}|{PLANREF})"
                    rf"|\s+in the alpha series|(?<=the ){ALPHA}\s+|(?<=the ){DOCREF}\s+|\s*\bfor {ALPHAS}\b|(?<![\w.]){ALPHAS}\s+(?=new\b)"
                    rf"|(?<=\. ){ALPHAS}:\s+|(?<![\w.]){RUNREF}\s*:\s+|(?<=\(){ALPHAS}\s*:\s*")
# Comments and docstrings only: whatever is still a reference goes, wherever it stands.
SWEEP = (
    (re.compile(rf"\b{ALPHA}\s+name\b"), "earlier name"),
    (re.compile(rf"\s*\b(?i:of|in|by|under|after|with)\s+(?:{DOCREF}|{PLANREF})"), ""),
    (re.compile(r"\b(?:production|isolated|live)\s+(?=(?:cache|caches|runs?|replays?)\b)"), ""),
    (re.compile(rf"\bcaches?\s*/\s*{NUMS}"), "a run"),
    (re.compile(rf"\bcaches?\s+{NUMS}(?=\s+[a-z])"), "a run"),            # "cache 64 streamed ..." -> "a run streamed ..."
    (re.compile(rf"{USERREF}"), ""),
    (re.compile(rf"(?<![\w.]){ALPHAS}\s*:?\s*"), ""),
    (re.compile(rf"(?:{DOCREF}|{PLANREF}|{V6REF})\s*:?\s*"), ""),
    (re.compile(r"\s*\b(?:fixed |added |changed )?(?:in|since|from) a\d{3}\b"), ""),
    (re.compile(r"(?<![\w.])a\d{3}\s*:?\s*"), ""),
    (re.compile(r"(?:\d{2}\s*系列\s*)?\d{1,3}\s*号(?:\s*[A-Z]{1,2}-?\d+)*(?:\s*/\s*[A-Z]{1,2}-?\d+)*\s*:?\s*"), ""),
    (re.compile(r"用户\s*(?:\d{4}-)?\d{1,2}-\d{1,2}\s*的?裁决\s*:?\s*"), ""),
    (re.compile(r"\s*\bfor v7\b"), ""),
    (re.compile(r"\bv7\s+(?=[a-z])"), ""),
)
# Texts a model reads: an engine generation named before a word ("v7 index unreadable") loses the name only.
V7_IN_TEXT = re.compile(r"\bv7\s+(?=[a-z])")
# Whole phrases that are history rather than references, as patterns (no quoted sentence is kept here).
SPECIAL = tuple((re.compile(pattern), new) for pattern, new in (
    (r"v7 core rewrite \([^)]*\)\. ", ""),
    (r"v7 core rewrite of the SoulRun engine\.", "The SoulRun engine."),
    (r"(?<=\)): the block shapes follow the\s+v6[\d.]* \S+ where a v7 equivalent exists -", ": The block shapes -"),
    (r" See the 04 series documents[^.]*\.", ""),
    (r" Historical alpha[.\d/]*[^.]*\.", ""),
    (r"and doc \d+ §[\d.]+ scans", "and feature-count scans"),
    (r"Pre-Alpha\d+ total", "Legacy total"),
    (r" One isolated real [^;]*;[^.]*\.", ""),
    (r"(?<=cache-setup) \(D\d+\)", ""),
    (r": hand-written v7 alpha;", ";"),
    (r"v7 core rewrite\. ", ""),
    (r"AISOP program executor \(v7 core\)", "AISOP program executor"),
    (r"\bfor the v7 engine\b", "for the engine"),
    (r"\bIn v7 every\b", "Every"),
    (r"\bthe v7 engine\b", "the engine"),
    (r"\bfor v7 \(", "("),
    (r"where a v7 equivalent exists", "where an equivalent exists"),
    (r"\bv7 core\b", "SoulRun engine"),
    (r"No code is taken from the v6 engine\.", ""),
    (r"  04 series doc \d+ {2,}[^\n]*\n(?: {20,}[^\n]*\n)*", ""),
))



def _pure_reference(part: str) -> bool:
    """True when a piece of text is nothing but references (and filler words around them)."""
    if not REF_TOKEN.search(part):
        return False
    rest = part
    for pattern in (USERREF, DOCREF, PLANREF, RUNREF, V6REF, ALPHAS):
        rest = re.sub(pattern, " ", rest, flags=re.I)
    rest = REF_TOKEN.sub(" ", rest)
    return FILLER.sub("", rest) == ""


CUT = "\x01"                                             # marks where something was taken out


def _parenthesis(thorough: bool):
    def clean(match: re.Match) -> str:
        inner = match.group(1)
        if not REF_TOKEN.search(inner):
            return match.group(0)
        if _pure_reference(inner):                       # "(caches 42, 43, 49, 64)", "(/ codex 102)"
            return CUT
        lead = re.match(rf"^\s*{ALPHAS}\s*[:,]\s*(.+)$", inner, re.S)
        if lead and not REF_TOKEN.search(lead.group(1)):
            return f"({lead.group(1).strip()})"
        # Keep every piece that says something, with the separators it had; a reference piece goes with the
        # separator before it, and a piece that only starts with a reference loses that start. In a comment or a
        # docstring (thorough) a reference left inside a kept piece is swept later.
        pieces = re.split(r"(\s*[;,]\s*)", inner)
        out, pending = [], None
        for i in range(0, len(pieces), 2):
            piece, before = pieces[i], pieces[i - 1] if i else ""
            if piece.strip() and _pure_reference(piece):
                pending = before if pending is None else pending      # "A; X, B" without X is "A; B"
                continue
            piece = re.sub(rf"^(\s*){MARK if thorough else MARK_TEXT}(?:\s*\([^()]*\))?\s*(?::|\s[-–—])\s*", r"\1", piece)
            out.append(("" if not out else (pending if pending is not None else before)) + piece)
            pending = None
        text = "".join(out).strip()
        return f"({text})" if text else CUT
    return clean


def scrub(text: str, thorough: bool) -> str:
    """The text without development-history references. Inside a parenthesis only the reference pieces go;
    thorough (comments, docstrings) also takes out a line that is only a reference and any reference left
    anywhere. Spacing is tidied only where something was taken out."""
    for pattern, new in SPECIAL:
        text = pattern.sub(new, text)
    text = DATED_NOTE.sub(CUT, text)
    clean = _parenthesis(thorough)
    previous = None
    while previous != text:                              # inner parentheses first, then the ones around them
        previous = text
        text = PARENS.sub(clean, text)
    text = re.sub(rf"[ \t]*{CUT}+(?=[ \t]*[:,;.)\]])", "", text)            # "alpha.23 (doc 5): x" -> "alpha.23: x"
    text = re.sub(rf"(?<=\. ){ALPHAS}:\s+([a-z])", lambda m: m.group(m.lastindex).upper(), text)   # a new sentence
    text = INLINE.sub(CUT, text)
    if not thorough:
        text = V7_IN_TEXT.sub(CUT, text)
    lines = []
    for line in text.split("\n"):
        if thorough and ONLY_MARK.match(line.replace(CUT, "")) and line.replace(CUT, "").strip():
            continue
        lines.append((LEAD if thorough else LEAD_TEXT).sub(r"\1" + CUT, line))
    text = "\n".join(lines)
    if thorough:
        for pattern, new in SWEEP:
            text = pattern.sub(new or CUT, text)
    text = re.sub(rf"\(\s*{CUT}+\s*\)", CUT, text)                       # a parenthesis emptied by a cut
    text = re.sub(rf"[ \t]*{CUT}+[ \t]*(?=[,.;:)\]}}\"'])", "", text)    # no space left before punctuation or a quote
    text = re.sub(rf"[ \t]*{CUT}+(?=\n|$)", "", text)                    # nor at the end of a line
    text = re.sub(rf"(?<=[ \t]){CUT}+[ \t]+", "", text)                   # no double space where words were cut
    text = re.sub(rf"(?<=\w){CUT}+(?=\w)", " ", text)                     # a cut between two words leaves a space
    return text.replace(CUT, "")


def rename(text: str, version: str) -> str:
    for old, new in IDENTITY:
        text = text.replace(old, new)
    text = ENGINE_ID.sub("soulrun_engine", text)
    for pattern, neutral in MACHINE_PATHS:
        text = pattern.sub(neutral, text)
    return VERSION_LITERAL.sub(version, text)


# ---- Python: only comments and string literals change ---------------------------------------------------------
def _docstring_nodes(tree: ast.AST) -> set[int]:
    """The docstrings, cleaned like comments - except a module docstring the module itself uses (a command-line tool
    passing __doc__ as its --help): that one is a text a model or a human reads, cleaned and listed as such."""
    found = set()
    help_text = any(isinstance(node, ast.Name) and node.id == "__doc__" for node in ast.walk(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Module) and help_text:
            continue
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def _docstring_starts(source: str) -> set[tuple[int, int]]:
    tree = ast.parse(source)
    ids = _docstring_nodes(tree)
    return {(n.lineno, n.col_offset) for n in ast.walk(tree) if id(n) in ids}


def _offsets(source: str) -> list[int]:
    """Where each line starts, on the lines tokenize reads (io.StringIO lines: only a line feed ends one - not a form
    feed or U+2028, which str.splitlines also splits at)."""
    out, total = [0], 0
    for line in io.StringIO(source).readlines():
        total += len(line)
        out.append(total)
    return out


def _clean_comment(raw: str, version: str) -> str:
    body = raw[1:]
    lead = body[: len(body) - len(body.lstrip())]
    text = _no_new_lead(body.strip(), scrub(rename(body.strip(), version), thorough=True))
    if text == body.strip():
        return raw                                       # nothing to clean: a comment (or a ---- rule) stays as it is
    if not text or ONLY_MARK.match(text) or not re.search(r"\w", text):
        return ""
    return "#" + lead + text


def _clean_string_token(raw: str, version: str, thorough: bool) -> str:
    match = re.match(r"^([rRbBuUfF]*)('''|\"\"\"|'|\")(.*)\2$", raw, re.S)
    if not match:                                        # an f-string piece (3.12 tokenizer): text only
        return scrub(rename(raw, version), thorough)
    prefix, quote, inner = match.groups()
    return prefix + quote + scrub(rename(inner, version), thorough) + quote


def clean_comments(source: str) -> str:
    """Only the comments and docstrings of a Python module - for code whose strings must stay exactly as written
    elsewhere (SoulRun's copy of SoulBot's agent wording keeps every string; only the notes beside it are cleaned)."""
    new = clean_python(source, version="", strings=False)
    if not same_code(source, new) or _texts(source) != _texts(new):
        raise SystemExit("cleaning the comments changed more than the comments - refusing")
    return new


def clean_python(source: str, version: str, strings: bool = True) -> str:
    starts = _docstring_starts(source)
    offsets = _offsets(source)
    edits, pieces = [], []
    middles = {tokenize.FSTRING_MIDDLE} if hasattr(tokenize, "FSTRING_MIDDLE") else set()
    kinds = {tokenize.COMMENT, tokenize.STRING} | middles
    fstring_end = getattr(tokenize, "FSTRING_END", None)
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if strings and tok.type == fstring_end:          # where an f-string closes: the next piece may continue it
            pieces.append(("end", offsets[tok.start[0] - 1] + tok.start[1], offsets[tok.end[0] - 1] + tok.end[1], None, None))
            continue
        if tok.type not in kinds or (not strings and tok.type != tokenize.COMMENT and tok.start not in starts):
            continue                                     # strings=False: comments and docstrings only
        start = offsets[tok.start[0] - 1] + tok.start[1]
        end = offsets[tok.end[0] - 1] + tok.end[1]
        original = source[start:end]
        if tok.type == tokenize.COMMENT:
            new = _clean_comment(original, version)
            if not new:
                line_start = offsets[tok.start[0] - 1]
                before = source[line_start:start]
                if before.strip() == "":                                     # a comment line of its own: drop it
                    edits.append((line_start, offsets[tok.start[0]], ""))
                else:                                                        # after code: drop it and its gap
                    edits.append((start - (len(before) - len(before.rstrip())), end, ""))
                continue
        else:
            new = _clean_string_token(original, version, thorough=tok.start in starts)
            kind = "string" if tok.type == tokenize.STRING else "middle"
            pieces.append((kind, start, end, original, new))  # string pieces are edited in the joined-string pass below
            continue
        if new != original:
            edits.append((start, end, new))
    edits += _joined(source, pieces)
    for start, end, new in sorted(edits, reverse=True):
        source = source[:start] + new + source[end:]
    return source


STRING_TOKEN = re.compile(r"^([rRbBuUfF]*)('''|\"\"\"|'|\")(.*)\2$", re.S)
NEW_LEAD = re.compile(r"^[;,][ \t]*")


def _no_new_lead(before: str, after: str) -> str:
    """A text that cleaning left opening with a separator it did not open with ("(alpha.99); x" -> "; x") loses it."""
    return NEW_LEAD.sub("", after) if NEW_LEAD.match(after) and not NEW_LEAD.match(before) else after


def _parts(kind: str, token: str) -> tuple[str, str, str]:
    """(opening, text, closing) of a string token; an f-string's literal piece ("middle") is all text."""
    match = STRING_TOKEN.match(token) if kind == "string" else None
    return (match.group(1) + match.group(2), match.group(3), match.group(2)) if match else ("", token, "")


def _joined(source: str, pieces: list[tuple]) -> list[tuple[int, int, str]]:
    """The edits of the string pieces, with the pieces of a string written in pieces seen together: when cleaning left
    a piece opening with a separator ("...not evidence " "(alpha.99); redirect..."), the separator goes back against
    the piece before it ("...not evidence; redirect..."); a string standing alone just loses it. An f-string ending
    just before counts as the piece before through its last literal piece - when that piece runs up to the closing
    quote (f"... {x}" ends with a field: nothing to move the separator against, so it stays)."""
    out, last, last_end = [], None, None             # the piece the string before ends with, and where that string ends
    for kind, start, end, original, new in pieces:
        if kind == "end":
            last = last if last is not None and out[last][2] == start else None
            last_end = end
            continue
        if kind == "string":
            opening, text, closing = _parts(kind, new)
            if NEW_LEAD.match(text) and not NEW_LEAD.match(_parts(kind, original)[1]):
                joined = last_end is not None and re.fullmatch(r"[\s\\]*", source[last_end:start])
                before = out[last] if joined and last is not None else None
                if before is not None and _parts(before[0], before[4])[1].endswith((" ", "\t")):
                    b_open, b_text, b_close = _parts(before[0], before[4])
                    out[last] = (*before[:4], b_open + b_text.rstrip(" \t") + b_close)
                elif not joined:
                    new = opening + NEW_LEAD.sub("", text) + closing
        out.append((kind, start, end, original, new))
        last, last_end = len(out) - 1, (end if kind == "string" else None)
    return [(start, end, new) for kind, start, end, original, new in out if new != original]


def _shape(tree: ast.AST) -> str:
    """The structure with docstrings dropped, f-string literal pieces dropped and string constants reduced."""
    docs = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            node.values = [v for v in node.values if not isinstance(v, ast.Constant)]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = "<doc>" if id(node) in docs else "<str>"
    return ast.dump(tree, include_attributes=False)


def same_code(before: str, after: str) -> bool:
    return _shape(ast.parse(before)) == _shape(ast.parse(after))


def _texts(source: str) -> list[str]:
    """The texts a model or a human may read, in order: string constants and whole f-string literal text."""
    tree = ast.parse(source)
    docs, inside, out = _docstring_nodes(tree), set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{…}" for v in node.values))
            inside.update(id(v) for v in node.values)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and id(node) not in inside:
            out.append(node.value)
    return out


def changed_texts(relative: str, before: str, after: str) -> list[tuple[str, str, str]]:
    return [(relative, a, b) for a, b in zip(_texts(before), _texts(after), strict=True) if a != b]


# ---- JSON and Markdown ----------------------------------------------------------------------------------------
NOTE_KEYS = {"$comment"}                                 # every other JSON text may be served to a model


def _clean_value(value, version: str, key: str = ""):
    if isinstance(value, str):
        return _no_new_lead(value, scrub(rename(value, version), thorough=key in NOTE_KEYS))
    if isinstance(value, list):
        return [_clean_value(v, version, key) for v in value]
    if isinstance(value, dict):
        return {k: _clean_value(v, version, k) for k, v in value.items()}
    return value


def _json_texts(value, path="") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, list):
        return [t for i, v in enumerate(value) for t in _json_texts(v, f"{path}[{i}]")]
    if isinstance(value, dict):
        return [t for k, v in value.items() for t in _json_texts(v, f"{path}.{k}")]
    return []


def _skeleton(value):
    if isinstance(value, dict):
        return {k: _skeleton(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_skeleton(v) for v in value]
    return type(value).__name__


def _embedded_json(text: str):
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, (dict, list)) else None


def clean_json(text: str, version: str) -> str:
    """Values change, keys and nesting do not; the file keeps its indentation style. A text value that is itself JSON
    (the engine reads some with json.loads) must still be JSON of the same shape after cleaning."""
    data = json.loads(text)
    cleaned = _clean_value(data, version)
    if cleaned == data:
        return text
    after = dict(_json_texts(cleaned))
    for where, before in _json_texts(data):
        inner = _embedded_json(before)
        if inner is not None and (after.get(where) is None or _embedded_json(after[where]) is None
                                  or _skeleton(_embedded_json(after[where])) != _skeleton(inner)):
            raise SystemExit(f"cleaning {where} would change the JSON it holds - refusing")
    indent = re.search(r"\n( +)[\"{\[]", text)
    out = json.dumps(cleaned, ensure_ascii=False, indent=len(indent.group(1)) if indent else None)
    return out + ("\n" if text.endswith("\n") else "")


def clean_aiap_md(text: str, version: str) -> str:
    """The engine's AIAP.md: its governance header and description, without the version history."""
    # The version history goes; the closing AIAP seal after it stays (the conformance check C-06 requires it).
    # A section after the history (a later "## " heading) stays too.
    text = re.sub(r"\n## Version History\n.*?(?=\n## |\n(?:Align Axiom 0:[^\n]*|\[L0_BOOT[^\n]*)\n*\Z|\Z)", "\n", text, flags=re.S)
    text = re.sub(r"(# Optional Fields\n)\n?(?:#[^\n]*\n)+", r"\1", text)
    text = re.sub(r" This revision adds only [^\n]*", "", text)
    text = text.replace("Development tests: install `tests/requirements.txt`, then run `python -m pytest tests`.\n"
                        "The independent JSON Schema validator is test-only; runtime remains standard-library-only.\n",
                        "The runtime is standard-library-only.\n")
    text = re.sub(r"## Current Recovery Policy \([^)]*\)", "## Current Recovery Policy", text)
    return scrub(rename(text, version), thorough=True)


# ---- the whole tree -------------------------------------------------------------------------------------------
def kept(relative: str) -> bool:
    """Only what runs: text files of the engine's own kinds, outside hidden folders (.git, .vscode, caches) and the
    folders and files an engine tree carries for its development (tests, release notes, logs, node_modules, .env)."""
    parts = relative.split("/")
    return not (any(part.startswith(".") for part in parts) or set(parts[:-1]) & DROP_DIRS or relative in DROP_FILES
                or parts[-1].startswith(DROP_PREFIXES)) and Path(parts[-1]).suffix in TEXT_SUFFIXES


def build(source: Path, target: Path, version: str) -> dict:
    card = source / 'agent_card.json'
    if card.is_file() and json.loads(card.read_text(encoding='utf-8')).get('program_id') == 'dev.soulrun.soulrun_aiap':
        raise SystemExit('canonical SoulRun source: use upgrade_engine.py without --legacy-clean; never rewrite its texts')
    if target.exists():
        raise SystemExit(f"{target} already exists")
    report = {"kept": 0, "dropped": 0, "changed": [], "texts": []}
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relative = path.relative_to(source).as_posix()
        if not kept(relative):
            report["dropped"] += 1
            continue
        report["kept"] += 1
        out = target / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix not in TEXT_SUFFIXES:
            shutil.copy2(path, out)
            continue
        text = path.read_bytes().decode("utf-8")
        if path.suffix == ".py":
            new = clean_python(text, version)
            if not same_code(text, new):
                raise SystemExit(f"{relative}: cleaning changed the code, not only text - refusing")
            report["texts"] += changed_texts(relative, text, new)
        elif path.suffix == ".json":
            new = clean_json(text, version)
            before, after = dict(_json_texts(json.loads(text))), dict(_json_texts(json.loads(new)))
            report["texts"] += [(f"{relative}{k}", v, after.get(k)) for k, v in before.items() if after.get(k) != v]
        elif path.name == "AIAP.md":
            new = clean_aiap_md(text, version)
        else:
            new = scrub(rename(text, version), thorough=True)
        if new != text:
            report["changed"].append(relative)
        out.write_bytes(new.encode("utf-8"))
    report["stamped"] = stamp_version(target, version)
    report["resealed"] = reseal(target)
    return report


VERSION_SPOTS = (
    ("python_tools/lib/engine_core.py", re.compile(r'^(ENGINE_VERSION = ")[^"]*(")', re.M)),
    ("AIAP.md", re.compile(r'^(version: ")[^"]*(")', re.M)),
    ("main.aisop.json", re.compile(r'("version": ")[^"]*(")')),
    ("agent_engine.aisop.json", re.compile(r'("version": ")[^"]*(")')),
    ("agent_card.json", re.compile(r'^(  "version": ")[^"]*(")', re.M)),
    ("quality_baseline.json", re.compile(r'^(  "version": ")[^"]*(")', re.M)),
)


def stamp_version(engine: Path, version: str) -> list[str]:
    """The engine's version, in every place the engine states it (the first occurrence in each file)."""
    stamped = []
    for name, pattern in VERSION_SPOTS:
        path = engine / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        new = pattern.sub(lambda m: m.group(1) + version + m.group(2), text, count=1)
        if new != text:
            path.write_bytes(new.encode("utf-8"))
        if pattern.search(new):
            stamped.append(name)
    if "python_tools/lib/engine_core.py" not in stamped:
        raise SystemExit("no ENGINE_VERSION found in python_tools/lib/engine_core.py - is this an engine tree?")
    return stamped


def reseal(engine: Path) -> list[str]:
    """The engine checks two records of its own files: contracts/manifest.json (sha256 of every contract file,
    checked when the contracts load) and the governance hash its AIAP.md, agent_card.json and quality_baseline.json
    declare for its programs. Both are recomputed from the cleaned files, the hash with the engine's own tool."""
    done = []
    manifest = engine / "contracts" / "manifest.json"
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8")
        data = json.loads(text)
        files = data.get("files", {})
        fresh = {name: hashlib.sha256((manifest.parent / name).read_bytes()).hexdigest() for name in files}
        if fresh != files:
            data["files"] = fresh
            indent = re.search(r"\n( +)[\"{\[]", text)
            manifest.write_bytes((json.dumps(data, ensure_ascii=False, indent=len(indent.group(1)) if indent else None)
                                  + ("\n" if text.endswith("\n") else "")).encode("utf-8"))
            done.append("contracts/manifest.json")
    tool = engine / "tools" / "refresh_governance_hash.py"
    if tool.is_file():
        result = subprocess.run([sys.executable, "-B", str(tool), str(engine)], capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise SystemExit(f"refresh_governance_hash.py failed: {result.stdout}{result.stderr}")
        check = subprocess.run([sys.executable, "-B", str(tool), str(engine), "--check"], capture_output=True, text=True,
                               encoding="utf-8")
        if check.returncode != 0:
            raise SystemExit(f"the governance hash is still stale: {check.stdout}{check.stderr}")
        done.append("governance hash")
    return done


# ---- what still looks like history ----------------------------------------------------------------------------
CHECK = re.compile(
    r"(?i)alpha[ ._]?\d+|(?-i:SoulBot\.dev)|\b04 series\b|\b(?:docs?|plans?) \d{1,3}\b|\bcaches? ?/\d+|\bcaches? \d+\b|"
    r"\bproduction (?:cache|run)|\bisolated (?:\d|cache|candidate|replay)|\bfinal_plan\b|\bcodex\b|\bv7\b|\bv6\.\d|"
    r"\b[A-Z]:/(?!dir/)\w|\b[A-Z]:\\{1,2}(?!dir\\)\w|(?<![\w.])/(?:home|Users)/(?!user/)\w|(?<![\w\\])\\{2,4}[A-Za-z][\w.-]{2,}\\|"
    r"\ba\d{3}\b|\d{1,3}\s*号|追记|用户\s*(?:\d{4}-)?\d{1,2}-\d{1,2}|"
    r"\((?=[^()]*\d{4}-\d\d-\d\d)[^()]*(?:\brules?\b|\bruling\b|\bdecided\b|\bnote\b)[^()]*\)|"
    r"user ruling|\buser \d{4}-\d\d-\d\d|SoulBot Execute Engine|SoulBot 执行引擎|dev\.soulbot|urn:soulbot|"
    r"soulbot_execute_engine(?!_aiap)")
# Development notes left in the engine bundled today (engine 1.0.0), found by rules added after it was cleaned. The
# human chose (doc 35, F47) to have them cleaned together with the next engine, not by hand: until then --check names
# them as known. Each entry is tied to its file's exact bytes, so an engine whose file differs is checked in full.
KNOWN_LEFTOVERS = {
    "python_tools/lib/aisop_parse.py": "26e435856ccbd1cb4458abed154a54c6dc3f88ee5bacc95191b5885fab17a40a",      # a comment naming a planning document (02 号)
    "python_tools/lib/engine_core.py": "443b4d4e7ac4bdf472e79877cbb630436a7454cdd26ee8eeaef9bc165768d3bd",      # the module docstring names the engine generation (v7)
    "python_tools/lib/hsaw_gate.py": "1a74b5ce9752cff0f20c771ffc89d32721b2094385abbaf30ec962e9b9fb893a",      # a docstring dates a rule (first rule, 2026-09-21)
    "python_tools/lib/render.py": "3650e1ee262c99d068ee10a0ffe5f307ddb6dc4110db9e48b3a794194757b30a",      # a docstring names the engine generation (v7)
    "python_tools/prepare_cache.py": "d0ebc8ae0524aa66cdfb54172f8af4a01ad72e73e4da6eefad348169875de966",      # its --help names the engine generation (v7) and dates a note (追记)
    "python_tools/public_delivery_observer.py": "523c4bde81f052b71886236881399bdee3babf19522247bc158b3e494e2d3aa7",      # the module docstring names the engine generation (v7)
    "python_tools/user_gate_audit.py": "fd7dfd7e57c1963a2d32a6ed657ce908ab449601345042e586552aaa7eecc943",      # a docstring and two texts a host reads name the engine generation (v7)
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _python_texts(text: str) -> list[tuple[int, str]]:
    """Every string constant of a Python file with its line - a string written in pieces ("see doc " "12") is one
    constant here, so a reference split across the pieces is seen whole."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    return [(node.lineno, node.value) for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def check_report(folder: Path) -> tuple[list[str], list[str]]:
    """(problems, known leftovers) of an engine folder."""
    problems, known = [], []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        relative = path.relative_to(folder).as_posix()
        if set(path.relative_to(folder).parts) & {"__pycache__", ".pytest_cache"} or path.suffix in (".pyc", ".pyo"):
            continue                                     # what Python leaves behind when the engine runs is not the engine
        if not kept(relative):
            problems.append(f"{relative}: a file the engine does not need at run time")
            continue
        text = path.read_text(encoding="utf-8")
        found, seen = [], set()
        for m in CHECK.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            seen.add((line, m.group(0)))
            found.append(f"{relative}:{line}: {m.group(0)!r} in ...{text[max(0, m.start() - 50): m.end() + 50]}...".replace("\n", " "))
        if path.suffix == ".py":
            for line, value in _python_texts(text):
                for m in CHECK.finditer(value):
                    if not any(seen_line >= line and match == m.group(0) for seen_line, match in seen):
                        found.append(f"{relative}:{line}: {m.group(0)!r} in the joined string ...{value[max(0, m.start() - 50): m.end() + 50]}...")
                        seen.add((line, m.group(0)))
        (known if found and KNOWN_LEFTOVERS.get(relative) == _sha256(path) else problems).extend(found)
    return problems, known


def check(folder: Path) -> list[str]:
    """What still looks like development history (known leftovers of the bundled engine excepted)."""
    return check_report(folder)[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", nargs="?", help="the engine tree to clean")
    parser.add_argument("target", nargs="?", help="a new folder for the cleaned engine")
    parser.add_argument("--engine-version", help="the version the cleaned engine carries")
    parser.add_argument("--check", metavar="FOLDER", help="only report what still looks like development history")
    parser.add_argument("--show-strings", action="store_true", help="print every changed text a model or a human may read")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    if args.check:
        folder = Path(args.check)
        if not (folder / "python_tools" / "lib" / "engine_core.py").is_file():
            print(f"{folder} is not an engine folder (no python_tools/lib/engine_core.py)")
            return 2
        problems, known = check_report(folder)
        for line in problems:
            print(line)
        if known:
            print(f"{len(known)} known leftover(s) of the bundled engine, cleaned with the next engine (see KNOWN_LEFTOVERS)")
        print(f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if not (args.source and args.target and args.engine_version):
        parser.error("give the engine tree, the output folder and --engine-version")
    report = build(Path(args.source), Path(args.target), args.engine_version)
    if args.show_strings:
        for relative, before, after in report["texts"]:
            print(f"--- {relative}\n  - {before!r}\n  + {after!r}")
    print(f"kept {report['kept']} file(s), dropped {report['dropped']}, changed {len(report['changed'])}; "
          f"{len(report['texts'])} text(s) a model or a human may read changed; resealed: {', '.join(report['resealed']) or 'nothing'}")
    problems = check(Path(args.target))
    for line in problems:
        print(line)
    print(f"check: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
