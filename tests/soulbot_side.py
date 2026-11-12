"""SoulBot's side of the comparisons: SoulBot itself when it is beside this repository (or where the SOULRUN_TEST_*
variables say), and tests/soulbot_samples.json, recorded from it by tools/record_soulbot_samples.py, everywhere
else - so CI compares too. With SoulBot beside, tests/test_soulbot_samples.py checks the samples are its today."""
from __future__ import annotations

import importlib.util

from conftest import ROOT

_spec = importlib.util.spec_from_file_location("record_soulbot_samples", ROOT / "tools" / "record_soulbot_samples.py")
TOOL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TOOL)

SAMPLES = TOOL.load()
AGENT_LIVE = TOOL.wording_live()        # SoulBot's agent.py is here and still carries the wording (not a SoulRun entry)
SEND_LAYER_LIVE = (TOOL.soulbot_package() / "models" / "acp_llm.py").is_file()
PACKAGE_LIVE = TOOL.soulbot_package().is_dir()                            # SoulBot's host source
DOCS_LIVE = (TOOL.soulbot_docs() / "README.md").is_file()                 # SoulBot's documents


def interruption_block():
    """SoulBot's _interruption_block, live; None when agent.py is not here (the samples hold its notes)."""
    return TOOL.original("_interruption_block") if AGENT_LIVE else None


def language_name():
    return TOOL.original("_language_name") if AGENT_LIVE else None


def turn_policy():
    """SoulBot's reader of the blocks: from its source when here, else from the source recorded in the samples."""
    return TOOL.turn_policy(TOOL.turn_policy_source() if SEND_LAYER_LIVE else SAMPLES["turn_policy_source"])


def host_modules() -> list[str]:
    return TOOL.host_modules() if PACKAGE_LIVE else SAMPLES["host_modules"]


def readme_footer(name: str) -> str:
    return TOOL.footer((TOOL.soulbot_docs() / name).read_text(encoding="utf-8")) if DOCS_LIVE else SAMPLES["readme_footers"][name]


def policy_document(name: str) -> dict:
    return TOOL.policy((TOOL.soulbot_docs() / name).read_text(encoding="utf-8")) if DOCS_LIVE else SAMPLES["policy_documents"][name]


def license_as_soulruns_sha256() -> str:
    if DOCS_LIVE:
        return TOOL._sha256(TOOL.soulruns_license((TOOL.soulbot_docs() / "LICENSE").read_text(encoding="utf-8")))
    return SAMPLES["license_as_soulruns_sha256"]
