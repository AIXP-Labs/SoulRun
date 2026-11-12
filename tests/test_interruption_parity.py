"""The interruption note and the language name, in every case: SoulRun's generated copy says exactly what SoulBot's
agent.py says. SoulBot's side is agent.py itself when SoulBot is beside this repository (its functions taken out and
run side by side with SoulRun's) and the notes recorded from it in tests/soulbot_samples.json everywhere else."""
from __future__ import annotations

import pytest

from soulbot_side import SAMPLES, TOOL, interruption_block, language_name

NOTES = SAMPLES["interruption_notes"]


@pytest.mark.parametrize("case", list(NOTES))
def test_the_interruption_note_is_soulbots_word_for_word(case):
    from soulrun import _agent_text
    recorded = NOTES[case]
    mine = _agent_text.interruption_block(recorded["context"], TOOL.ENGINE)
    assert TOOL.neutral(mine) == recorded["note"]
    original = interruption_block()
    if original is not None:                              # SoulBot beside: byte for byte against agent.py itself
        assert mine == original(recorded["context"])


def test_every_case_is_a_different_note():
    from soulrun import _agent_text
    notes = {case: _agent_text.interruption_block(recorded["context"], TOOL.ENGINE) for case, recorded in NOTES.items()}
    said = [note for note in notes.values() if note]
    assert notes["nothing to say"] is None and notes["a plain run"] is None
    assert len(said) == len(set(said)) == len(NOTES) - 2          # each case reaches its own branch


@pytest.mark.parametrize("recorded", SAMPLES["language_names"], ids=lambda r: repr(r["context"]))
def test_the_language_name_is_soulbots(recorded):
    from soulrun import _agent_text
    assert _agent_text.language_name(recorded["context"]) == recorded["name"]
    original = language_name()
    if original is not None:
        assert _agent_text.language_name(recorded["context"]) == original(recorded["context"])
