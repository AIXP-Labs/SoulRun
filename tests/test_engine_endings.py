"""How the bundled engine ends and recovers when a turn goes wrong at its edges: a rejected reply that could not be printed
leaves the run going (an accepted one still stops for the human), every host-authorised end writes the accepted-facts
notice, 1.x versions keep the inherited feature set, and run numbers follow their own root only."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from helpers import index, route_payload, take_node

CHILD = Path(__file__).with_name("engine_child.py")


def child(tmp_path, env, mode, *args, stdin=None) -> dict:
    result = tmp_path / f"child-{mode}-{len(list(tmp_path.glob('child-*')))}.json"
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", str(CHILD), mode, str(result), *map(str, args)],
                          input=stdin, capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(result.read_text(encoding="utf-8"))


def faults(cache_dir) -> list[dict]:
    path = Path(cache_dir) / "_engine_faults.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def started(soulrun):
    ctx = soulrun(user_message="用 demo 给我抽一张签", aiap="demo_aiap", session_id="endings")
    node = take_node(soulrun, ctx)
    return ctx, node


def test_a_rejected_reply_that_could_not_be_printed_leaves_the_run_going(agent, soulrun, subprocess_env, tmp_path):
    ctx, node = started(soulrun)
    before = index(ctx.cache_dir)
    out = child(tmp_path, subprocess_env, "commit-failing-print", ctx.cache_dir, "Router.match", "REJECTED", stdin="{}")
    assert "REJECTED" in out["printed"] and out["exit"] == 2            # the reply was rejected, then lost on its way out
    rows = faults(ctx.cache_dir)
    assert rows[-1]["disposition"] == "REJECTED_REPLY_NOT_DELIVERED"
    proof = rows[-1]["recovery"]
    assert proof["accepted"] is False and proof["business_replayed"] is False and proof["run_unchanged"] is True
    echo = json.loads((Path(ctx.cache_dir) / proof["reply_ref"]).read_text(encoding="utf-8"))
    assert echo["status"] == "REJECTED"                                 # the rejection itself is kept, readable
    after = index(ctx.cache_dir)
    assert after["run_state"] == before["run_state"] == "RUNNING" and after["current"] == before["current"]
    life = Path(ctx.cache_dir) / "_host_lifecycle.json"
    assert not life.exists() or not json.loads(life.read_text(encoding="utf-8")).get("stop")   # no question opened
    again = soulrun(cmd="next-node", cache_dir=ctx.cache_dir)
    assert again.returncode == 0 and again.json().get("status") != "ERROR"
    done = soulrun(cmd="node-commit", cache_dir=ctx.cache_dir, node="Router.match",
                   payload=route_payload(node, "demo_aiap")).json()
    assert done["status"] == "COMMITTED"                                # the executor simply submits again


def test_an_accepted_reply_that_could_not_be_printed_still_stops_for_the_human(agent, soulrun, subprocess_env, tmp_path):
    ctx, node = started(soulrun)
    payload = json.dumps(route_payload(node, "demo_aiap"), ensure_ascii=False)
    out = child(tmp_path, subprocess_env, "commit-failing-print", ctx.cache_dir, "Router.match", "COMMITTED", stdin=payload)
    assert out["exit"] == 2
    rows = faults(ctx.cache_dir)
    assert rows and all(r.get("disposition") != "REJECTED_REPLY_NOT_DELIVERED" for r in rows)
    again = soulrun(cmd="next-node", cache_dir=ctx.cache_dir).json()
    assert again.get("status") == "ERROR"                               # unchanged fail-closed path: a human decides


def test_the_proof_refuses_anything_but_an_unchanged_rejection(agent, soulrun, subprocess_env, tmp_path):
    ctx, _ = started(soulrun)
    child(tmp_path, subprocess_env, "commit-failing-print", ctx.cache_dir, "Router.match", "REJECTED", stdin="{}")
    observed = faults(ctx.cache_dir)[-1]["write_observation"]

    def proof(change) -> object:
        facts = json.loads(json.dumps(observed))
        change(facts)
        path = tmp_path / f"observed-{len(list(tmp_path.glob('observed-*')))}.json"
        path.write_text(json.dumps(facts), encoding="utf-8")
        return child(tmp_path, subprocess_env, "proof", ctx.cache_dir, path)["proof"]

    assert proof(lambda f: None) is not None
    assert proof(lambda f: f.update(effect_phase="ACCEPTED")) is None
    assert proof(lambda f: f.update(tool="next_node")) is None
    assert proof(lambda f: f["writes"].append(dict(path=str(Path(ctx.cache_dir) / "_index.json"), phase="VERIFIED"))) is None
    assert proof(lambda f: f["writes"].append(dict(path=f["writes"][0]["path"].replace(".json", ".copy.json"),
                                                   phase="VERIFIED"))) is None
    assert proof(lambda f: f["baseline"].update(input_sha256="0" * 64)) is None
    assert proof(lambda f: f["baseline"].update(recovery_state_sha256="0" * 64, index_core_sha256="0" * 64)) is None
    reply = next(Path(w["path"]) for w in observed["writes"] if "_work" in Path(w["path"]).parts)
    reply.write_text(json.dumps({"status": "COMMITTED"}), encoding="utf-8")
    assert proof(lambda f: None) is None                                # the echo must still say REJECTED


def test_every_host_authorised_end_writes_the_accepted_facts_notice(agent, soulrun, subprocess_env, tmp_path):
    ctx, _ = started(soulrun)
    out = child(tmp_path, subprocess_env, "terminate", ctx.cache_dir)
    assert out["result"]["status"] == "TERMINATED"
    assert index(ctx.cache_dir)["run_state"] == "ABANDONED"
    ended = Path(ctx.cache_dir) / "_public" / "ended.txt"
    assert ended.is_file() and (Path(ctx.cache_dir) / "_terminal_facts.json").is_file()
    first = ended.read_bytes()
    assert child(tmp_path, subprocess_env, "terminate", ctx.cache_dir)["result"]["status"] == "ALREADY_TERMINAL"
    assert ended.read_bytes() == first                                  # an existing notice is never rewritten


def test_one_x_versions_keep_the_inherited_feature_set(subprocess_env, tmp_path):
    out = child(tmp_path, subprocess_env, "revision", "1.0.0", "1.2.3", "7.0.0-alpha.140", "2.0.0", "1.0", "")
    assert out["matches"] == {"1.0.0": 155, "1.2.3": 155, "7.0.0-alpha.140": 140, "2.0.0": None, "1.0": None, "": None}


def test_run_numbers_follow_their_own_root_only(subprocess_env, tmp_path):
    root = tmp_path / "soulrun_aiap" / ".execution_cache"
    root.mkdir(parents=True)
    (tmp_path / "soulbot_execute_engine_aiap" / ".execution_cache" / "7").mkdir(parents=True)
    assert child(tmp_path, subprocess_env, "next-cache-dir", root)["name"] == "1"
