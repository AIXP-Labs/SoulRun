"""What must never be published: credentials, and paths or addresses that name a person or a machine.

One set of rules for every check that reads SoulRun's files before they leave this machine: tools/check_dist.py (each
file of a built package), tools/check_docs.py (the documents) and the tests (every file that would be committed). This
file spells the patterns out, so those scans leave it out (as they leave out each other's test samples).
"""
from __future__ import annotations

import re

SELF = "tools/privacy_rules.py"

# Credentials, by the shape their issuers give them.
CREDENTIALS = {
    "PyPI or TestPyPI token": re.compile(r"(?<![A-Za-z0-9_-])pypi-AgE[A-Za-z0-9_-]{20,}"),
    "API key": re.compile(r"(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-|ant-(?:api\d\d-)?)?[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})"),
    "npm token": re.compile(r"(?<![A-Za-z0-9_])npm_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
    "Slack token": re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}"),
    "Hugging Face token": re.compile(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{30,}"),
    "Google API key": re.compile(r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}"),
    "Telegram bot token": re.compile(r"(?<![0-9])[0-9]{8,10}:AA[A-Za-z0-9_-]{33}(?![A-Za-z0-9_-])"),
    "private key": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
}

# A person's home folder, written any of the ways tools write one. The neutral examples SoulRun's files use -
# D:/dir/... and /home/user/... (tools/clean_engine.py writes them in place of real ones) - are not traces.
HOME_PATHS = (
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:(?:\\\\|\\|/)+users(?:\\\\|\\|/)+(?!(?:public|default|all users)\b)[^\\/\s\"'*<>|]+", re.I),
    re.compile(r"(?<![\w.])/home/(?!user(?:/|\b))[A-Za-z0-9._-]+"),
    re.compile(r"(?<![\w.])/Users/(?!Shared\b)[A-Za-z][^/\s\"']*"),
    re.compile(r"(?<![\w.])/root(?:/|\b)(?![-.])"),
    re.compile(r"(?<![\w.])/(?:mnt/)?[a-z]/users/[^/\s\"']+", re.I),             # a Windows home seen from Git Bash or WSL
    re.compile(r"\\\\wsl(?:\$|\.localhost)\\", re.I),                              # a WSL file share
)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ALLOWED_EMAILS = {"noreply@soulrun.dev", "user@example.com"}


def text_of(data: bytes) -> str:
    """A file's text for these checks: UTF-16 when it starts with its byte-order mark, else UTF-8 (bad bytes replaced)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", "replace")


def credentials(text: str) -> list[tuple[str, int]]:
    """(label, offset) of every credential in the text."""
    return sorted((label, m.start()) for label, pattern in CREDENTIALS.items() for m in pattern.finditer(text))


def home_paths(text: str) -> list[tuple[str, int]]:
    """(the path as written, shortened; offset) of every home-folder path in the text."""
    return sorted((m.group(0)[:60], m.start()) for pattern in HOME_PATHS for m in pattern.finditer(text))


def emails(text: str) -> list[tuple[str, int]]:
    """(address, offset) of every e-mail address that is not one of SoulRun's own."""
    return [(m.group(0), m.start()) for m in EMAIL.finditer(text)
            if m.group(0).lower() not in ALLOWED_EMAILS and not m.group(0).lower().endswith((".png", ".json", ".py"))]
