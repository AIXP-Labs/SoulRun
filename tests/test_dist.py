"""The package checker (tools/check_dist.py): what it lets through and what it reports.

The wheels here are put together in the temporary folder from the source tree, with the wheel's own
exclude list applied - no build tool is needed to run these tests.
"""
from __future__ import annotations

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from conftest import ROOT
from test_install_shape import _excluded

PACKAGE = ROOT / "src" / "soulrun"
ENGINE = "soulrun/soulrun_aiap/"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_dist", ROOT / "tools" / "check_dist.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_wheel(folder: Path, *, extra: dict | None = None, drop: tuple = (), change: tuple = (), metadata: str = "",
               description: str = "SoulRun, [one call](https://soulrun.dev/).\n") -> Path:
    path = folder / "soulrun-0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        for file in sorted(PACKAGE.rglob("*")):
            if not file.is_file() or file.suffix == ".pyc" or _excluded(file.relative_to(ROOT).as_posix()):
                continue
            name = file.relative_to(ROOT / "src").as_posix()
            if name in drop:
                continue
            wheel.writestr(name, file.read_bytes() + (b"\n" if name in change else b""))
        wheel.writestr("soulrun-0.dist-info/METADATA", "Metadata-Version: 2.4\nName: soulrun\n" + metadata + "\n" + description)
        wheel.writestr("soulrun-0.dist-info/entry_points.txt", "[console_scripts]\nsoulrun = soulrun.cli:main\n")
        for name, data in (extra or {}).items():
            wheel.writestr(name, data)
    return path


def test_a_wheel_with_exactly_the_installed_engine_files_passes(checker, tmp_path):
    assert checker.check_wheel(make_wheel(tmp_path)) == []


def test_optional_extras_are_not_runtime_dependencies(checker, tmp_path):
    extras = "Provides-Extra: dev\nRequires-Dist: pytest<10,>=8; extra == 'dev'\n"
    assert checker.check_wheel(make_wheel(tmp_path, metadata=extras)) == []
    problems = checker.check_wheel(make_wheel(tmp_path, metadata=extras + "Requires-Dist: requests>=2\n"))
    assert len(problems) == 1 and "runtime dependency" in problems[0] and "requests" in problems[0]


def test_engine_files_that_are_extra_missing_or_changed_are_each_reported(checker, tmp_path):
    problems = checker.check_wheel(make_wheel(
        tmp_path,
        extra={ENGINE + "tests/test_x.py": "x = 1\n"},
        drop=(ENGINE + "AIAP.md",),
        change=(ENGINE + "main.aisop.json",),
    ))
    assert sorted(problems) == [
        "engine file differs from the manifest: main.aisop.json",
        "engine file missing from the wheel: AIAP.md",
        "file in the wheel's engine folder that the manifest does not install: tests/test_x.py",
    ]


def test_a_wheel_without_the_command_or_the_guide_is_reported(checker, tmp_path):
    problems = checker.check_wheel(make_wheel(tmp_path, drop=("soulrun/guide.txt",)))
    assert problems == ["missing from the wheel: soulrun/guide.txt"]
    path = make_wheel(tmp_path)
    rewritten = tmp_path / "no_command.whl"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(rewritten, "w") as target:
        for name in source.namelist():
            if not name.endswith("entry_points.txt"):
                target.writestr(name, source.read(name))
    assert checker.check_wheel(rewritten) == ["the wheel does not install the soulrun command"]


def test_a_long_description_that_is_missing_or_links_relatively_is_reported(checker, tmp_path):
    assert checker.check_wheel(make_wheel(tmp_path, description="")) == ["the wheel carries no long description (README.md)"]
    problems = checker.check_wheel(make_wheel(tmp_path, description="See the [guide](GUIDE.md) and [limits](#known-limits).\n"))
    assert problems == ["the long description links relatively, which leads nowhere on a package index: GUIDE.md"]


def _listed(problems: list[str]) -> list[str]:
    """The problems a test is about: a file it adds to find another rule is also one SoulRun does not ship."""
    return [p for p in problems if "does not ship" not in p]


def test_only_what_soulrun_ships_may_be_in_its_packages(checker, tmp_path):
    problems = checker.check_wheel(make_wheel(tmp_path, extra={"soulrun/stray_private_notes.txt": "notes",
                                                               "soulrun_extra_top_level/x.py": "x = 1\n"}))
    assert sorted(problems) == ["file in the wheel that SoulRun does not ship: soulrun/stray_private_notes.txt",
                                "file in the wheel that SoulRun does not ship: soulrun_extra_top_level/x.py"]
    archive = tmp_path / "extra.tar.gz"
    import tarfile
    with tarfile.open(archive, "w:gz") as tar:
        for member, text in (("soulrun-0/pyproject.toml", "[project]\n"), ("soulrun-0/scratch_notes.md", "mine"),
                             ("soulrun-0/src/soulrun/__init__.py", "")):
            info = tarfile.TarInfo(member)
            info.size = len(text.encode("utf-8"))
            tar.addfile(info, io.BytesIO(text.encode("utf-8")))
    assert "in the source archive but not in pyproject.toml's sdist include list: scratch_notes.md" in checker.check_sdist(archive)


def test_run_data_or_caches_in_a_wheel_are_reported(checker, tmp_path):
    problems = _listed(checker.check_wheel(make_wheel(tmp_path, extra={"soulrun/.soulrun/runs/1.json": "{}"})))
    assert problems == ["the wheel contains a cache or run-data folder"]


@pytest.mark.parametrize("name", ["soulrun/.mypy_cache/x.json", "soulrun/.soulrun_cache/s/turn.json",
                                  ".engine_backups/1.0.0-x/engine_manifest.json", "soulrun/.git/config"])
def test_every_kind_of_cache_or_kept_engine_in_a_wheel_is_reported(checker, tmp_path, name):
    assert _listed(checker.check_wheel(make_wheel(tmp_path, extra={name: "{}"}))) == ["the wheel contains a cache or run-data folder"]


def test_a_secrets_file_in_a_wheel_is_reported_and_a_template_is_not(checker, tmp_path):
    problems = _listed(checker.check_wheel(make_wheel(tmp_path, extra={"soulrun/.env": "K=1\n", "soulrun/.env.local": "K=1\n",
                                                               "soulrun/.env.example": "K=\n"})))
    assert sorted(problems) == ["the wheel contains a secrets file: soulrun/.env",
                                "the wheel contains a secrets file: soulrun/.env.local"]


def test_a_target_that_is_not_a_package_is_reported_and_nothing_checked_fails(checker, tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert checker.main([str(tmp_path / "missing.whl"), str(tmp_path / "notes.txt")]) == 1
    out = capsys.readouterr().out
    assert "PROBLEM: no such file:" in out and "PROBLEM: not a package (a .whl or a .tar.gz):" in out
    assert "PROBLEM: no package was checked" in out and "3 problem(s)" in out
    assert checker.main([str(make_wheel(tmp_path))]) == 0 and capsys.readouterr().out.rstrip().endswith("OK")


def test_a_credential_anywhere_in_a_package_is_reported(checker, tmp_path):
    token = "github" + "_pat_" + "11ABC" + "x" * 40                         # put together here: this file holds none
    utf16 = ("saved to C:" + "\\" + "Users" + "\\" + "someone").encode("utf-16")
    problems = _listed(checker.check_wheel(make_wheel(tmp_path, extra={"soulrun/leak_demo.py": f"TOKEN = '{token}'\n",
                                                               "soulrun/notes.txt": utf16})))
    path = "C:" + "\\" + "Users" + "\\" + "someone"
    assert sorted(problems) == ["credential (GitHub token) in soulrun-0-py3-none-any.whl:soulrun/leak_demo.py",
                                f"home-folder path in soulrun-0-py3-none-any.whl:soulrun/notes.txt: {path}"]


def test_personal_traces_are_reported(checker, tmp_path, monkeypatch):
    home = "C:" + "\\Users\\" + "someone\\project"                  # put together here so this file holds no such path
    posix_home = "/" + "home/" + "someone/project"
    address = "someone" + "@" + "mail.example.org"
    monkeypatch.setenv("SOULRUN_PRIVACY_WORDS", "Zebracorn, , quagga-pc")
    problems = _listed(checker.check_wheel(make_wheel(tmp_path, extra={
        "soulrun/a.txt": f"saved to {home}",
        "soulrun/b.txt": f"saved to {posix_home}",
        "soulrun/c.txt": f"write to {address}",
        "soulrun/d.txt": "built on QUAGGA-PC",
        "soulrun/e.txt": "noreply@soulrun.dev and user@example.com are fine, and so is plain text",
        "soulrun/f.txt": "the neutral example /home/user/notes.txt is fine",
    })))
    assert len(problems) == 4
    assert sum("home-folder path" in p for p in problems) == 2
    assert sum("e-mail address" in p and address in p for p in problems) == 1
    hit = [p for p in problems if "SOULRUN_PRIVACY_WORDS" in p]
    assert len(hit) == 1 and "d.txt" in hit[0] and "quagga" not in hit[0].lower()      # the word itself is not echoed


def test_a_source_archive_that_records_who_built_it_is_reported(checker, tmp_path):
    def archive(name: str, uname: str) -> Path:
        path = tmp_path / name
        with tarfile.open(path, "w:gz") as tar:
            for member, text in (("soulrun-0/pyproject.toml", "[project]\n"), ("soulrun-0/src/soulrun/__init__.py", "")):
                info = tarfile.TarInfo(member)
                data = text.encode("utf-8")
                info.size, info.uname, info.gname = len(data), uname, uname
                tar.addfile(info, io.BytesIO(data))
        return path
    named = checker.check_sdist(archive("named.tar.gz", "someone"))
    plain = checker.check_sdist(archive("plain.tar.gz", ""))
    assert any("user/group name" in p for p in named) and not any("user/group name" in p for p in plain)
    assert any(p == "missing from the source archive: LICENSE" for p in plain)


def test_the_packages_in_dist_pass_when_they_were_built(checker, soulrun):
    built = sorted((ROOT / "dist").glob(f"soulrun-{soulrun.__version__}*"))
    if not built:
        pytest.skip("nothing built for this version: python -m build")
    from helpers import committed_files
    newest = max(committed_files(ROOT), key=lambda p: p.stat().st_mtime)
    stale = [p.name for p in built if p.stat().st_mtime < newest.stat().st_mtime]
    if stale:                                       # a package older than the source says nothing about the source
        pytest.skip(f"{', '.join(stale)} older than {newest.relative_to(ROOT).as_posix()}: python -m build")
    for path in built:
        problems = checker.check_wheel(path) if path.suffix == ".whl" else checker.check_sdist(path)
        assert problems == [], path.name
