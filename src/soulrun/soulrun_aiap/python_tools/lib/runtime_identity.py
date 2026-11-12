"""Public SoulRun identity; preserve the inherited runtime's feature boundaries."""
import re

NAME = 'soulrun_aiap'
VERSION = '1.0.0'
HOMEPAGE = 'https://soulrun.dev'
LICENSE_URL = 'https://github.com/AIXP-Labs/SoulRun/blob/main/LICENSE'
COPYRIGHT = 'Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev'


def revision_match(version):
    # This is a compatibility selector, never a rewritten persisted version. Every SoulRun 1.x engine (1.0.0 and any later
    # 1.y.z) carries the feature set the inherited 7.0.0-alpha.155 runtime enabled, so a run recorded by an earlier 1.x
    # version keeps its features after an upgrade. A feature added after 1.0.0 is switched by its own name, never by
    # comparing release numbers against this selector.
    text = str(version or '')
    inherited = '7.0.0-alpha.155' if re.fullmatch(r'1\.\d+\.\d+', text) else text
    return re.fullmatch(r'7\.0\.0-alpha\.(\d+)', inherited)
