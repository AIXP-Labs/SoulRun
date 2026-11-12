"""Policy comparison never hides missing sections, duplicate headings or altered authority footers."""
from __future__ import annotations

import copy
import json

import pytest

import test_docs as docs
from soulbot_side import TOOL

POLICIES = {
    'CONTRIBUTING.md': '### Packaging and Privacy Review',
    'CONTRIBUTING_CN.md': '### 打包与隐私审查',
    'GOVERNANCE.md': '## Release Evidence and Authorization',
    'SECURITY.md': '## Handling a Suspected Disclosure',
}


def policy(name):
    mine = (docs.ROOT / name).read_text('utf-8')
    package, _ = docs.CHECK.current_versions(docs.ROOT)
    theirs = TOOL.policy(mine)
    theirs['last_line'] = 'Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulBot V0.0.0. www.soulbot.dev'
    return mine, theirs, package


@pytest.mark.parametrize('name', POLICIES)
@pytest.mark.parametrize('change', ['missing', 'local-duplicate', 'external-duplicate', 'local-footer', 'external-footer'])
def test_policy_mutations_cannot_be_accepted(name, change):
    mine, theirs, package = policy(name)
    docs._assert_ecosystem_policy(name, mine, theirs, package)
    heading = POLICIES[name]
    if change == 'missing':
        mine = mine.replace(heading + '\n', '', 1)
    elif change == 'local-duplicate':
        mine = mine.replace(heading, heading + '\n' + heading, 1)
    elif change == 'external-duplicate':
        theirs['headings'].append(heading)
    elif change == 'local-footer':
        mine = mine.replace('www.soulrun.dev', 'incorrect.invalid')
    else:
        theirs['last_line'] = 'Changed authority footer'
    with pytest.raises(AssertionError):
        docs._assert_ecosystem_policy(name, mine, theirs, package)


def neutral_recorder(tmp_path, monkeypatch):
    """Only synthetic source/documents; no real environment or credentials enter the fixture."""
    root = tmp_path / 'host'
    model = root / 'src/soulbot/models'
    model.mkdir(parents=True)
    (root / 'agent.py').write_text('from soulrun import soulrun\n', encoding='utf-8')
    (model / 'acp_llm.py').write_text(
        'def _engine_turn_policy(system, user, prompt_format="text"):\n'
        '    return system, user\n', encoding='utf-8')
    for name in ('README.md', 'README_CN.md'):
        (root / name).write_text(TOOL.FOOTER_HEADING + '\n\nNeutral public footer.\n', encoding='utf-8')
    for name in TOOL.POLICY_DOCUMENTS:
        (root / name).write_text('# Neutral policy\n\n## Neutral section\n\n'
            'Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulBot V0.0.0. www.soulbot.dev\n', encoding='utf-8')
    (root / 'LICENSE').write_text('Neutral synthetic license\n', encoding='utf-8')
    samples = tmp_path / 'samples.json'
    samples.write_text(TOOL.dump(copy.deepcopy(TOOL.load())), encoding='utf-8')
    monkeypatch.setattr(TOOL, 'ROOT', tmp_path)
    monkeypatch.setattr(TOOL, 'SAMPLES', samples)
    monkeypatch.setenv('SOULRUN_TEST_AGENT_PY', str(root / 'agent.py'))
    monkeypatch.setenv('SOULRUN_TEST_SOULBOT_SRC', str(root / 'src'))
    monkeypatch.setenv('SOULRUN_TEST_SOULBOT_DOCS', str(root))
    return root, samples


@pytest.mark.parametrize('change', ['heading', 'footer', 'host-source'])
def test_recorder_rejects_stale_public_inputs_and_can_regenerate(tmp_path, monkeypatch, change):
    root, samples = neutral_recorder(tmp_path, monkeypatch)
    agent_before = {key: TOOL.load()[key] for key in TOOL.AGENT_KEYS}
    assert TOOL.main([]) == 0 and TOOL.main(['--check']) == 0
    recorded = samples.read_bytes()
    if change == 'heading':
        path, before, after = root / 'SECURITY.md', '## Neutral section', '## Changed neutral section'
    elif change == 'footer':
        path, before, after = root / 'SECURITY.md', 'SoulBot V0.0.0', 'SoulBot V0.0.1'
    else:
        path, before, after = root / 'src/soulbot/models/acp_llm.py', 'return system, user', 'return user, system'
    path.write_text(path.read_text('utf-8').replace(before, after), encoding='utf-8')
    assert TOOL.main(['--check']) == 1 and samples.read_bytes() == recorded
    assert TOOL.main([]) == 0 and TOOL.main(['--check']) == 0
    assert {key: json.loads(samples.read_text('utf-8'))[key] for key in TOOL.AGENT_KEYS} == agent_before
