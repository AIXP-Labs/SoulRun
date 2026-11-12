"""The requirements of one optional extra in pyproject.toml, one per line.

CI installs the release tools with the ranges pyproject.toml declares - the one place Dependabot keeps current -
instead of a copy of them written into the workflow:

    python tools/extra_requirements.py release > release-requirements.txt
    python -m pip install -r release-requirements.txt
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def requirements(extra: str, root: Path = ROOT) -> list[str]:
    extras = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]
    if extra not in extras:
        raise SystemExit(f"pyproject.toml has no extra {extra!r}; it has: {', '.join(sorted(extras))}")
    return list(extras[extra])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    parser.add_argument("extra", help="the name of the extra, e.g. release")
    args = parser.parse_args(argv)
    print("\n".join(requirements(args.extra)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
