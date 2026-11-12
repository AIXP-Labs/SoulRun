"""tools/privacy_rules.py: the credentials, home-folder paths and e-mail addresses every privacy check looks for - each
kind found, the neutral examples SoulRun writes left alone - and no file that would be committed holds any of them.
Every sample here is put together at run time, so this file itself holds none."""
from __future__ import annotations

import importlib.util

import pytest

from conftest import ROOT
from helpers import committed_files

_spec = importlib.util.spec_from_file_location("privacy_rules", ROOT / "tools" / "privacy_rules.py")
RULES = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RULES)
BS = "\\"

CREDENTIAL_SAMPLES = {
    "PyPI or TestPyPI token": ["pypi-" + "AgEIcHlwaS5vcmc" + "x" * 30, "pypi-" + "AgENdGVzdC5weXBp" + "y" * 30],
    "API key": ["sk-" + "ant-api03-" + "z" * 40, "sk-" + "proj-" + "q" * 40],
    "GitHub token": ["gh" + "p_" + "a" * 36, "github" + "_pat_" + "11ABC" + "b" * 40],
    "npm token": ["np" + "m_" + "c" * 36],
    "AWS access key": ["AK" + "IA" + "ABCDEFGHIJKLMNOP"],
    "Slack token": ["xo" + "xb-" + "1234567890-abcdefghij"],
    "Hugging Face token": ["h" + "f_" + "d" * 34],
    "Google API key": ["AI" + "za" + "S" * 35],
    "Telegram bot token": ["1234567890" + ":AA" + "e" * 33],
    "private key": ["-----BEGIN " + "ENCRYPTED PRIVATE KEY-----", "-----BEGIN " + "OPENSSH PRIVATE KEY-----"],
}
HOME_SAMPLES = [
    "C:" + BS + "Users" + BS + "someone" + BS + "x", "c:" + BS + "users" + BS + "someone",
    "C:" + BS * 2 + "Users" + BS * 2 + "someone",                                   # JSON-escaped
    "C:" + "/Us" + "ers/someone/x", "/ho" + "me/someone", "/ho" + "me/Someone/", "HOME=/ho" + "me/x",
    "/Us" + "ers/someone", 'cwd="/Us' + 'ers/x"', "/ro" + "ot/.config", "/c/Us" + "ers/someone", "/mnt/c/Us" + "ers/someone",
    BS * 2 + "wsl$" + BS + "Ubuntu" + BS + "home",
]
NEUTRAL = ["D:/dir/file", "/home/user/file", "/home/user", "C:" + BS + "Users" + BS + "Public", "/Us" + "ers/Shared/x",
           "https://example.org/root/x", "the root/ folder", "/rooted", "noreply@soulrun.dev", "user@example.com"]


@pytest.mark.parametrize(("label", "sample"), [(label, s) for label, samples in CREDENTIAL_SAMPLES.items() for s in samples])
def test_every_kind_of_credential_is_found(label, sample):
    assert [found for found, _ in RULES.credentials(f"token = '{sample}'")] == [label]


@pytest.mark.parametrize("sample", HOME_SAMPLES)
def test_every_way_of_writing_a_home_folder_is_found(sample):
    assert RULES.home_paths(f"saved to {sample} today"), sample


@pytest.mark.parametrize("sample", NEUTRAL)
def test_the_neutral_examples_and_soulruns_addresses_are_not_traces(sample):
    text = f"see {sample} here"
    assert not RULES.credentials(text) and not RULES.home_paths(text) and not RULES.emails(text), sample


def test_a_utf16_file_is_read_as_text():
    data = ("saved to C:" + BS + "Users" + BS + "someone").encode("utf-16")
    assert RULES.home_paths(RULES.text_of(data))


@pytest.mark.parametrize('suffix', ['py', 'json', 'png'])
def test_email_shaped_suffixes_are_not_a_bypass(suffix):
    sample = 'fixture' + '@' + 'example.' + suffix
    assert RULES.emails(sample) == [(sample, 0)]


def test_no_file_that_would_be_committed_holds_a_credential_a_home_folder_or_an_address():
    found = []
    for path in committed_files(ROOT):
        relative = path.relative_to(ROOT).as_posix()
        if relative == RULES.SELF or path.suffix in (".whl", ".gz", ".zip", ".png"):
            continue
        text = RULES.text_of(path.read_bytes())
        found += [(relative, kind) for kind, hits in (("credential", RULES.credentials(text)), ("home", RULES.home_paths(text)),
                                                      ("e-mail", RULES.emails(text))) if hits]
    assert found == []
