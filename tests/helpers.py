"""Test helpers. No model is ever called: where a model would act, the test sends the engine what a model would send."""
from __future__ import annotations

import copy
import json
from pathlib import Path

# A minimal host: captures none of the model's streamed text and cannot spawn sub-agents.
HOST = dict(model="codex-acp/gpt-5.6", host_fences=(), host_tools={"agent": False})
QUESTION = "请运行 demo：跟我打个招呼"


def committed_files(root: Path) -> list[Path]:
    """The files git would commit under root: everything except the repository folder and what root/.gitignore
    ignores. Its patterns as that file writes them: a name or a *-pattern matching at any depth, a trailing / for
    a folder, a leading **/ for any depth, a leading / for the top, ! taking a file back; the last match wins. Tests
    that look at "SoulRun's own files" use this, so a .venv or a scratch file on one machine never counts."""
    import fnmatch
    rules = []
    for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        pattern = line[1:] if negate else line
        folder = pattern.endswith("/")
        pattern = pattern.rstrip("/")
        anchored = pattern.startswith("/")
        pattern = pattern.lstrip("/").removeprefix("**/")
        rules.append((negate, folder, anchored, pattern))

    def ignored(parts: tuple[str, ...]) -> bool:
        result = False
        for negate, folder, anchored, pattern in rules:
            names = parts[:1] if anchored else (parts[:-1] if folder else parts)
            if folder and anchored and len(parts) == 1:
                names = ()
            if any(fnmatch.fnmatchcase(name, pattern) for name in names):
                result = not negate
        return result

    return sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts
                  and not ignored(p.relative_to(root).parts))


def run_input(ctx) -> dict:
    return json.loads((Path(ctx.cache_dir) / "_run_input.json").read_text(encoding="utf-8"))


def candidates(ctx) -> list[str]:
    return sorted(item["package"] for item in run_input(ctx)["snapshot"])


def index(cache_dir) -> dict:
    return json.loads((Path(cache_dir) / "_index.json").read_text(encoding="utf-8"))


def runs(soulrun_cache_dir: Path) -> list[int]:
    root = Path(soulrun_cache_dir) / ".execution_cache"
    return sorted(int(p.name) for p in root.iterdir() if p.is_dir() and p.name.isdigit()) if root.is_dir() else []


def take_node(soulrun, ctx) -> dict:
    result = soulrun(cmd="next-node", cache_dir=ctx.cache_dir)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.json()


def commit(soulrun, ctx, payload: dict, node: str = "Router.match") -> dict:
    result = soulrun(cmd="node-commit", cache_dir=ctx.cache_dir, node=node, payload=payload)
    return result.json()


def route_payload(node: dict, package: str, summary: str = "按请求选定程序。") -> dict:
    payload = copy.deepcopy(node["payload_skeleton"])
    payload.update(output=package, user_summary=summary,
                   route={"package": package, "rationale": "The request names this program and it fits."})
    return payload


def gate_payload(node: dict, packages: list[str], recommendation: str) -> dict:
    payload = copy.deepcopy(node["payload_skeleton"])
    payload.pop("route", None)
    payload.update(
        output="more than one program fits", user_summary="有不止一个程序能做这件事，需要你来选。",
        gate={"question": "有两个程序都能做这件事，用哪一个？",
              "options": [{"kind": "execute", "label": f"用 {name}", "intent": name} for name in packages]
              + [{"kind": "cancel", "label": "取消，不运行任何程序", "intent": "cancel"}],
              "closing": "请回复选项编号。", "recommendation": recommendation,
              "advice": "两个都能完成；想要完整流程建议第一个。", "explanation": "这个选择决定用哪个程序来做这件事。"})
    return payload
