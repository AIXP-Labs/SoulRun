"""Development helper: recompute the governance hash (AIAP §18.1) and write the canonical
16-hex value into AIAP.md, agent_card.json and quality_baseline.json of this engine.

This is the only tool in tools/ that writes files. The release process (doc 01 P6) runs it once;
during the alpha series it is run after every main.aisop.json change so C-08 stays PASS.

Usage: python tools/refresh_governance_hash.py [DIR] [--check]
  --check   do not write; exit 1 if any carrier is stale
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1] / "python_tools"))

from lib import aiap_md  # noqa: E402

CARRIERS = ("AIAP.md", "agent_card.json", "quality_baseline.json")


def refresh(aiap_dir: Path, check_only: bool = False) -> dict:
    computed = aiap_md.governance_hash(aiap_dir)
    result = {"canonical": computed["canonical"], "files": computed["files"], "updated": [], "stale": []}
    for name in CARRIERS:
        path = aiap_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            data = json.loads(text)
            current = data.get("governance_hash")
            if current == computed["canonical"]:
                continue
            result["stale"].append(name)
            if not check_only:
                data["governance_hash"] = computed["canonical"]
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
                result["updated"].append(name)
        else:
            m = re.search(r'^governance_hash:\s*"?([^"\n]*)"?\s*$', text, re.M)
            current = m.group(1) if m else None
            if current == computed["canonical"]:
                continue
            result["stale"].append(name)
            if not check_only:
                if m:
                    new_text = text[:m.start()] + f'governance_hash: "{computed["canonical"]}"' + text[m.end():]
                else:
                    new_text = text.replace("---\n", f'---\ngovernance_hash: "{computed["canonical"]}"\n', 1)
                path.write_text(new_text, encoding="utf-8", newline="\n")
                result["updated"].append(name)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default=str(_HERE.parents[1]))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    result = refresh(Path(args.dir).resolve(), args.check)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if (args.check and result["stale"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
