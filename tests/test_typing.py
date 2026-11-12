"""The package says it is typed (py.typed): a host written as the README writes one type-checks, and a wrong use is
reported. Runs where mypy is installed (the dev extra has it); a type checker cannot see that the module itself is
callable, so the README recommends ``from soulrun import run`` to hosts that type-check."""
from __future__ import annotations

import pytest

from conftest import INSTALLED, ROOT

mypy_api = pytest.importorskip("mypy.api", reason="mypy is not installed in this environment (it is in the dev extra)")

PROBE = '''\
from __future__ import annotations

from pathlib import Path

from soulrun import CmdResult, Ctx, host, run

ctx: Ctx = run(user_message="hi", session_id="c1", agent_dir=Path("."), host_tools={"agent": False})
text: str = ctx.text
kind: str = ctx.kind
out: CmdResult = run(cmd="next-node", cache_dir=ctx.cache_dir)
data = out.json()
shown: str = host.expand_refs("x", cache_dir=ctx.cache_dir)
state: dict = host.after_turn(ctx.cache_dir or "", "reply")
wrong: int = run(user_message="hi")
'''


def test_a_host_type_checks_and_a_wrong_use_is_reported(tmp_path, monkeypatch):
    probe = tmp_path / "host_example.py"
    probe.write_text(PROBE, encoding="utf-8")
    if not INSTALLED:
        monkeypatch.setenv("MYPYPATH", str(ROOT / "src"))          # the source tree, as an installed copy would be found
    report, errors, status = mypy_api.run([str(probe), "--follow-imports=silent", "--cache-dir", str(tmp_path / "cache"),
                                           "--no-error-summary", "--no-color-output"])
    found = [line for line in report.splitlines() if ": error:" in line]
    assert len(found) == 1 and 'expression has type "Ctx", variable has type "int"' in found[0], report + errors
