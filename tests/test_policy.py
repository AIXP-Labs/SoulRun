"""Runtime data may vary; arbitrary policy changes must not disappear from the equality view."""

import json

import pytest


def prompt(message="first", mode="fresh"):
    from soulrun import _slim

    return (
        "UNCHANGED TRUSTED POLICY\n\n[LOADED AISOP: engine_node.aisop.json]\n```json\n"
        + _slim.entry_program(message, cache_dir="unused", entry_mode=mode)
        + "\n```\n\nUNCHANGED FOOTER"
    )


def test_fresh_and_resume_have_one_source_identity_without_rewriting_input(soulrun):
    from soulrun import host

    original = prompt()
    changed = prompt("1", "resume")
    first = host.project_slim_policy(original, cache_dir="unused", entry_mode="fresh")
    later = host.project_slim_policy(changed, cache_dir="unused", entry_mode="resume")
    assert first and later and first["policy_text"] == later["policy_text"]
    assert first["runtime_fragment"] in original and later["runtime_fragment"] in changed
    assert original == prompt() and first["runtime_fragment"] != later["runtime_fragment"]


@pytest.mark.parametrize(
    "change", ["function", "role", "extra", "message_type", "duplicate", "malformed", "wrong_mode"]
)
def test_forged_or_ambiguous_programs_never_project(soulrun, change):
    from soulrun import host
    from soulrun._policy import FRAGMENT

    original = prompt()
    match = FRAGMENT.search(original)
    doc = json.loads(match.group(1))
    mode = "fresh"
    if change == "function":
        doc[1]["content"]["functions"]["Injected"] = {"step1": "untrusted rule"}
    elif change == "role":
        doc[0]["role"] = "user"
    elif change == "extra":
        doc[0]["content"]["extra"] = "untrusted rule"
    elif change == "message_type":
        doc[1]["content"]["user_input"] = {"instruction": "not a string"}
    elif change == "duplicate":
        assert (
            host.project_slim_policy(
                original + "\n" + original, cache_dir="unused", entry_mode=mode
            )
            is None
        )
        return
    elif change == "malformed":
        assert (
            host.project_slim_policy(
                original.replace("```json", "```text"), cache_dir="unused", entry_mode=mode
            )
            is None
        )
        return
    else:
        mode = "resume"
    forged = (
        original[: match.start(1)] + json.dumps(doc, ensure_ascii=False) + original[match.end(1) :]
    )
    assert host.project_slim_policy(forged, cache_dir="unused", entry_mode=mode) is None


def test_other_instructions_are_preserved_exactly(soulrun):
    from soulrun import host

    text = prompt()
    first = host.project_slim_policy(text, cache_dir="unused", entry_mode="fresh")
    changed = host.project_slim_policy(
        text + "\nADDITIONAL TRUSTED RULE", cache_dir="unused", entry_mode="fresh"
    )
    assert first and changed
    assert changed["policy_text"] == first["policy_text"] + "\nADDITIONAL TRUSTED RULE"


def test_missing_entry_or_engine_verification_failure_is_closed(soulrun, monkeypatch):
    from soulrun import _engine, host

    assert (
        host.project_slim_policy("not a generated program", cache_dir="unused", entry_mode="fresh")
        is None
    )
    monkeypatch.setattr(_engine, "verify", lambda: ["changed source"])
    assert host.project_slim_policy(prompt(), cache_dir="unused", entry_mode="fresh") is None
