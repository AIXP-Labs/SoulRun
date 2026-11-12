"""Which folders SoulRun works with, and which programs are candidates.

Rule (docs: one call, section "which program"): the arguments only decide *what the candidates are*.
Which one runs is always judged by the engine's main program from the user's words; when that is not
clear the human is asked. A designated program is used as designated - it is never silently swapped.

Words used here:
    agent folder       the folder that holds the programs, in its aiap/ and aisp/ (SoulBot's word); the current
                       folder unless one is named (agent_dir)
    soulrun_cache_dir  the folder that holds every run SoulRun makes: <agent folder>/.soulrun_cache unless one is
                       named - and a named one is that folder itself, as pip, pytest and ruff use their cache-dir
    cache_dir          one run (the engine's word): <soulrun_cache_dir>/.execution_cache/<N>
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import UsageError

SOULRUN_CACHE = ".soulrun_cache"                      # the default folder name
ENGINE_MARKERS = ("python_tools", "main.aisop.json")   # what an engine *program* folder contains
CACHE_DIRNAME = ".execution_cache"                    # the engine's own folder of runs, inside soulrun_cache_dir
NOTES_DIRNAME = ".soulrun"                            # SoulRun's own notes, inside soulrun_cache_dir (see _records)
ENV_SOULRUN_CACHE_DIR = "SOULRUN_CACHE_DIR"
ENV_AGENT_DIR = "SOULRUN_AGENT_DIR"
ENTRY_FILES = {"aiap": "main.aisop.json", "aisp": "aisp.aisop.json"}
# A program folder's registry script: in the agent-folder layout the engine runs it (with the interpreter running
# SoulRun) and it decides which of the folder's programs are enabled.
REGISTRY_SCRIPTS = {"aiap": "aiap_list.py", "aisp": "aisp_list.py"}
IGNORE_FILE = ".gitignore"
IGNORE_TEXT = ("# Run data written by SoulRun: what was asked and what was answered.\n"
               "# It stays on this machine; this file keeps the whole folder out of version control.\n"
               "*\n")


def keep_out_of_version_control(cache: Path) -> None:
    """A run folder ignores itself.

    By default it sits inside the agent folder, which is often a project under version control. Run data holds the
    user's own words, so the folder says "do not commit me" from its first run on. Written when SoulRun makes the
    folder, or takes one for the first time (no .soulrun in it yet) - before it puts anything of its own there, so
    whatever that first call ends in - and only when it has no .gitignore; once the folder is SoulRun's (it holds
    .soulrun), the owner's .gitignore - or its absence - is left as it is.
    """
    if (cache / IGNORE_FILE).exists():
        return
    try:
        (cache / IGNORE_FILE).write_text(IGNORE_TEXT, encoding="utf-8", newline="\n")
    except OSError:
        pass                                      # a note that cannot be written never stops a run


# Files a system writes into any folder it shows (Finder, Explorer) or a placeholder that keeps a folder in git:
# a folder holding only these is still empty.
SYSTEM_FILES = (".ds_store", "desktop.ini", "thumbs.db", "ehthumbs.db", ".gitkeep")


def _other_files(cache: Path) -> list[str]:
    """What keeps an existing folder from becoming the run folder ([] = nothing). A folder SoulRun already keeps runs
    in (it has .soulrun) is fine. A folder taken for the first time may hold only a .gitignore, an engine's own runs
    (.execution_cache, runs brought over from another host) and system files: anything else - notes, a copy kept as
    evidence, a project - would get run data written among it, and its oldest runs rotated out."""
    names = sorted(p.name for p in cache.iterdir())
    if NOTES_DIRNAME in names:
        return []
    return [name for name in names if name not in (IGNORE_FILE, CACHE_DIRNAME) and name.lower() not in SYSTEM_FILES]


@dataclass(frozen=True)
class Places:
    agent_dir: Path
    aiap_dir: Path
    aisp_dir: Path
    soulrun_cache_dir: Path                           # every run is in it
    sources: dict = field(default_factory=dict)       # where each value came from: argument / environment / default

    @property
    def cache_root(self) -> Path:
        """The engine's folder of runs: each run (a cache_dir) is a numbered folder in it."""
        return self.soulrun_cache_dir / CACHE_DIRNAME

    @property
    def standard_layout(self) -> bool:
        """True when the engine can find everything by itself, the way it does inside a SoulBot agent folder. The engine
        takes the agent folder to be the parent of the run folder's real location, so a run folder that is a link (a
        junction or a symbolic link elsewhere) is not this layout: SoulRun then names the agent folder to the engine."""
        return (self.soulrun_cache_dir.resolve().parent == self.agent_dir.resolve()
                and self.aiap_dir == self.agent_dir / "aiap" and self.aisp_dir == self.agent_dir / "aisp")


@dataclass(frozen=True)
class Designated:
    protocol: str          # "aiap" | "aisp"
    given: str             # what the caller wrote
    directory: Path
    found: bool

    @property
    def entry(self) -> Path:
        return self.directory / ENTRY_FILES[self.protocol]


def _existing_dir(value, name: str, source: str) -> Path:
    path = Path(str(value)).expanduser().resolve()
    if not path.is_dir():
        raise UsageError("DIR_NOT_FOUND", f"{name} does not exist or is not a folder: {path} (given by {source})",
                         field=name, expected="an existing folder")
    return path


def program_places(*, agent_dir=None, aiap_dir=None, aisp_dir=None) -> tuple[Path, Path, Path, dict]:
    """(agent folder, aiap folder, aisp folder, where each came from): the program side of resolve_places, on its own
    so that a check can still look at the programs when the run folder is wrong."""
    sources: dict = {}
    if agent_dir is not None:
        agent, sources["agent_dir"] = _existing_dir(agent_dir, "agent_dir", "argument"), "argument"
    elif os.environ.get(ENV_AGENT_DIR):
        agent, sources["agent_dir"] = _existing_dir(os.environ[ENV_AGENT_DIR], "agent_dir", f"environment {ENV_AGENT_DIR}"), "environment"
    else:
        agent, sources["agent_dir"] = Path.cwd().resolve(), "default"

    def big(value, name: str) -> Path:
        if value is None:
            sources[name] = "default"
            return agent / name.split("_")[0]
        sources[name] = "argument"
        return _existing_dir(value, name, "argument")

    return agent, big(aiap_dir, "aiap_dir"), big(aisp_dir, "aisp_dir"), sources


def _cache_place(agent: Path, soulrun_cache_dir=None) -> tuple[Path, str]:
    """Where the runs go and who said so: argument > environment variable > <agent folder>/.soulrun_cache."""
    if soulrun_cache_dir is not None:
        return Path(str(soulrun_cache_dir)).expanduser().resolve(), "argument"
    if os.environ.get(ENV_SOULRUN_CACHE_DIR):
        return Path(os.environ[ENV_SOULRUN_CACHE_DIR]).expanduser().resolve(), "environment"
    return agent / SOULRUN_CACHE, "default"


def soulrun_cache_dir_of(*, agent_dir=None, soulrun_cache_dir=None) -> Path:
    """The folder a run with these arguments keeps its runs in, worked out only: nothing is checked or made."""
    agent, _aiap, _aisp, _sources = program_places(agent_dir=agent_dir)
    return _cache_place(agent, soulrun_cache_dir)[0]


def blocked_only_by(cache: Path, path: Path) -> bool:
    """True when the one thing keeping an existing folder from becoming the run folder is ``path`` (a file in it, or
    in a folder of its own there): the user's words written into the run folder before its first run."""
    try:
        rel = Path(path).resolve().relative_to(Path(cache).resolve())
    except (OSError, ValueError):
        return False
    if not cache.is_dir() or _other_files(cache) != [rel.parts[0]]:
        return False
    top = cache / rel.parts[0]
    return top.is_file() if len(rel.parts) == 1 else all(
        p.is_dir() or p.resolve() == Path(path).resolve() for p in top.rglob("*"))


def resolve_places(*, agent_dir=None, aiap_dir=None, aisp_dir=None, soulrun_cache_dir=None, create: bool = True) -> Places:
    """Argument > environment variable > default. A value that is set but unusable is an error, never a silent fallback.
    ``create=False`` only works the places out (for checks): the cache folder is not made.

    A named ``soulrun_cache_dir`` is the cache folder itself. It must be new, empty, or one SoulRun already uses;
    an existing folder holding other files (a project folder named by mistake) is refused, and so is one holding
    an engine program (another engine's runs live there)."""
    agent, aiap, aisp, sources = program_places(agent_dir=agent_dir, aiap_dir=aiap_dir, aisp_dir=aisp_dir)
    key = "soulrun_cache_dir"
    cache, sources[key] = _cache_place(agent, soulrun_cache_dir)
    given = sources[key]
    if cache.exists() and not cache.is_dir():
        raise UsageError("SOULRUN_CACHE_DIR_INVALID", f"soulrun_cache_dir is not a folder: {cache} (given by {given})",
                         field=key, expected="a folder, or a path that can be created")
    if cache.is_dir() and any((cache / marker).exists() for marker in ENGINE_MARKERS):
        # Another engine's home (for example a SoulBot agent's own engine folder): its runs belong to that engine,
        # and its oldest finished runs would be rotated out by this one.
        raise UsageError("SOULRUN_CACHE_DIR_HOLDS_AN_ENGINE",
                         f"soulrun_cache_dir holds an engine program, not just run data: {cache} (given by {given})",
                         field=key, expected="a folder used for SoulRun's run data only")
    others = _other_files(cache) if cache.is_dir() else []
    if others:
        shown = ", ".join(others[:5]) + (f" and {len(others) - 5} more" if len(others) > 5 else "")
        raise UsageError("SOULRUN_CACHE_DIR_NOT_EMPTY",
                         f"soulrun_cache_dir already holds other files: {cache} (given by {given}): {shown}; run data would "
                         "sit among them without a .gitignore", field=key,
                         expected="a new or empty folder, or one SoulRun already keeps runs in")
    places = Places(agent_dir=agent, aiap_dir=aiap, aisp_dir=aisp, soulrun_cache_dir=cache, sources=sources)
    if create:
        make_cache_dir(places)
    return places


def make_cache_dir(places: Places) -> None:
    """Create the run folder, with its .gitignore - only once a run is about to be prepared. A folder SoulRun makes is
    readable by its owner only (POSIX; on Windows it keeps the permissions of the folder it is made in)."""
    cache = places.soulrun_cache_dir
    try:
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        keep_out_of_version_control(cache)
    except OSError as exc:
        raise UsageError("SOULRUN_CACHE_DIR_INVALID", f"soulrun_cache_dir cannot be created: {cache} ({exc})",
                         field="soulrun_cache_dir", expected="a writable location") from exc


def resolve_designated(protocol: str, value, places: Places) -> Designated:
    """``aiap=`` / ``aisp=`` accept a folder path or a bare program name looked up in the big folder."""
    text = str(value)
    path = Path(text).expanduser()
    big = places.aiap_dir if protocol == "aiap" else places.aisp_dir
    is_path = path.is_absolute() or len(path.parts) > 1 or text.startswith(".")
    directory = (path if is_path else big / text).resolve()
    if directory.is_file() and directory.name == ENTRY_FILES[protocol]:
        directory = directory.parent          # the entry file itself was named: its folder is the program
    return Designated(protocol=protocol, given=text, directory=directory, found=(directory / ENTRY_FILES[protocol]).is_file())


def programs_in(folder: Path) -> list[str]:
    """Names of the program folders directly under ``folder`` (those that hold an entry file)."""
    if not folder.is_dir():
        return []
    return sorted(child.name for child in folder.iterdir()
                  if child.is_dir() and any((child / name).is_file() for name in ENTRY_FILES.values()))
