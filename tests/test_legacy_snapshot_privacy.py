"""Check the decoded historical fixture, rather than treating compressed bytes as text."""
import base64
import io
import json
import sys
import zipfile

from conftest import ROOT
from legacy_snapshot import ARCHIVE


def test_the_frozen_legacy_sources_contain_no_private_data():
    sys.path.insert(0, str(ROOT/'tools'))
    import privacy_rules
    raw = base64.b64decode(json.loads(ARCHIVE.read_text('utf-8'))['data'], validate=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            text = privacy_rules.text_of(archive.read(name))
            assert not privacy_rules.credentials(text), name
            assert not privacy_rules.home_paths(text), name
            assert not privacy_rules.emails(text), name
