"""The one call.

    import soulrun
    ctx = soulrun(user_message="...")        # start a run, or continue the one this message belongs to
    ctx = soulrun()                          # no message, no cmd: the guide
    out = soulrun(cmd="next-node", cache_dir=...)   # run one engine command

Everything a host needs is behind this call; everything the model needs is in ``ctx.text``.
"""
from __future__ import annotations

import contextlib
import dataclasses
import difflib
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence, TypeAlias, Union, overload

from . import _adapter, _blocks, _cmd, _engine, _filelock, _records, _select, _slim
from .errors import SoulRunError, UsageError

DEFAULT_SESSION = "default"            # no session_id: one conversation per agent folder (_default_session)
ENV_INLINE_PROGRAM = "SOULRUN_INLINE_PROGRAM"
ENV_SLIM_PROGRAM = "SOULRUN_SLIM_PROGRAM"
PROGRAM_FORMS = ("entry_path", "full", "slim")   # how a run's program reaches the model (ctx.program_form)
KINDS = ("guide", "program", "text_only")
Kind: TypeAlias = Literal["guide", "program", "text_only"]
PathArg: TypeAlias = Union[str, "os.PathLike[str]"]       # a folder or a program: a str or any path object
BOM = "﻿"
_PREPARE_LOCK = threading.RLock()


@dataclass(frozen=True)
class Ctx:
    """What one call hands back.

    ``kind``        "guide" | "program" | "text_only"
    ``text``        everything the model should be given for this turn (for a doubt: the question for the human)
    ``blocks``      the same text as separate blocks, in order
    ``cache_dir``   the run this turn belongs to (None for the guide and for a doubt raised before any run exists)
    ``entry_mode``  how the engine classified the message: fresh, resume, recovery, terminal, ...
    ``turn_id``     the engine's turn_id: the run's number (the last part of cache_dir), the same on every turn of the run
                    - not an id of this turn; the host's own id for the turn is the host_turn_id it passed
    ``program``     the program handed to the model with the user's words filled in, when it is handed over in the text
    ``program_form`` for a run: "slim" (the slim program, engine_node.aisop.json, in the text; the default),
                    "entry_path" (the model reads the program itself, SoulBot's text) or "full" (the whole main program
                    in the text)
    ``system_prompt`` the opening instruction that goes with this turn's form, for the host to put where it used to put
                    its own (None for the guide and for a doubt)
    ``slim_fallback`` why a turn that would have had the slim form has the entry-path form instead (None otherwise)
    ``doubt``       set when SoulRun itself must ask the human before any run can be created
    ``data``        the engine's own answer, unchanged
    """
    kind: Kind
    text: str
    blocks: tuple = ()
    cache_dir: str | None = None
    entry_mode: str | None = None
    turn_id: str | None = None
    session_id: str | None = None
    program: str | None = None
    doubt: Mapping | None = None
    places: Mapping | None = None
    data: Mapping = field(default_factory=dict)
    program_form: str | None = None
    system_prompt: str | None = None
    slim_fallback: str | None = None

    def __str__(self) -> str:
        return self.text

    def as_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "cache_dir": self.cache_dir, "entry_mode": self.entry_mode,
                "turn_id": self.turn_id, "session_id": self.session_id,
                **({"program_form": self.program_form} if self.program_form else {}),
                **({"system_prompt": self.system_prompt} if self.system_prompt else {}),
                **({"slim_fallback": self.slim_fallback} if self.slim_fallback else {}),
                **({"doubt": dict(self.doubt)} if self.doubt else {})}


def _guide() -> Ctx:
    text = (Path(__file__).resolve().parent / "guide.txt").read_text(encoding="utf-8")
    text = text.replace("{version}", _version()).replace("{engine_version}", _engine.version()).replace(
        "{commands}", ", ".join(_cmd.COMMANDS))
    return Ctx(kind="guide", text=text, blocks=(text,))


def _version() -> str:
    from . import __version__
    return __version__


def _language(user_message: str, fallback: str | None = None) -> str:
    """The language of the words; when they carry none ("1", "?"), ``fallback`` (the run's own language), else English."""
    try:
        found = _engine.load("lib.render").detect_language(user_message)
    except Exception:
        found = None
    return found or fallback or "en"


def _doubt(code: str, user_message: str, zh: tuple, en: tuple, *, facts: dict, actions: list,
           run_language: str | None = None) -> Ctx:
    """A question for the human, raised before any run exists. Nothing is created and no other program is used.

    Each option carries what to do when the human picks it: ``{"action": "call", "arguments": {...}}`` means
    "call soulrun again with the same message and these arguments changed" (an argument set to None is left out);
    ``"ask"`` means the argument set to None must be named first, then the call is made with it; ``"cancel"``
    means do nothing. SoulRun keeps no memory of the question - the caller that shows it is the one that carries
    the answer back. ``run_language``: the language of the run the question is about, for words that carry none (an
    option number answering that run's gate).
    """
    def written(headline, lines, options, advice) -> str:       # no options: a notice, shown as written
        return "\n".join([headline, *[f"- {line}" for line in lines], *([advice] if advice else []),
                          *([""] if options else []), *[f"{number}. {option}" for number, option in enumerate(options, 1)]])

    if user_message.strip() or run_language:
        chosen = zh if _language(user_message, run_language) == "zh" else en
        text, labels = written(*chosen), chosen[2]
    else:               # no words to tell the language by: both, the same numbers in each
        text, labels = written(*zh) + "\n\n" + written(*en), [f"{a} / {b}" for a, b in zip(zh[2], en[2], strict=True)]
    choices = [{"number": number, "label": label, **action}
               for number, (label, action) in enumerate(zip(labels, actions, strict=True), 1)]
    return Ctx(kind="text_only", text=text, blocks=(text,), entry_mode="soulrun_doubt",
               doubt={"code": code, "options": choices, **facts})


def _shown(path, places: _select.Places) -> str:
    """A folder as a human may read it: relative to the agent folder, or only its name. The machine's absolute path
    (it names the system account) stays out of the text; ctx.doubt keeps it for the host."""
    try:
        return Path(path).resolve().relative_to(places.agent_dir).as_posix() or "."
    except ValueError:
        return Path(path).name


def _designated_missing(item: _select.Designated, places: _select.Places, user_message: str) -> Ctx:
    big = places.aiap_dir if item.protocol == "aiap" else places.aisp_dir
    present = _select.programs_in(big)
    close = difflib.get_close_matches(Path(item.given).name, present, n=1, cutoff=0.5)
    kind_zh, kind_en = ("AIAP 程序", "AIAP program") if item.protocol == "aiap" else ("AISP 技能", "AISP skill")
    zh = (f"你指定的{kind_zh}「{item.given}」找不到。",
          (f"找过的位置：{_shown(item.directory, places)}", f"大目录 {_shown(big, places)} 里现有的：{'、'.join(present) if present else '没有'}"),
          (*([f"改用「{close[0]}」"] if close else []), "改用大目录里的另一个（请说出名字）", "取消"),
          f"建议：你指的可能是「{close[0]}」。这只是建议，由你决定。" if close else "建议：先确认名字或路径。这只是建议，由你决定。")
    en = (f"The designated {kind_en} \"{item.given}\" was not found.",
          (f"Looked in: {_shown(item.directory, places)}", f"Programs present in {_shown(big, places)}: {', '.join(present) if present else 'none'}"),
          (*([f"Use \"{close[0]}\" instead"] if close else []), "Use another one from the folder (name it)", "Cancel"),
          f"Suggestion: you may have meant \"{close[0]}\". This is only a suggestion; the choice is yours." if close
          else "Suggestion: check the name or the path. This is only a suggestion; the choice is yours.")
    actions = [*([{"action": "call", "arguments": {item.protocol: close[0]}}] if close else []),
               {"action": "ask", "arguments": {item.protocol: None}}, {"action": "cancel", "arguments": {}}]
    return _doubt("DESIGNATED_NOT_FOUND", user_message, zh, en, actions=actions,
                  facts={"protocol": item.protocol, "given": item.given, "looked_in": str(item.directory),
                         "present": present, "recommendation": close[0] if close else None})


def _which_designated(designated: list, places: _select.Places) -> Ctx:
    """No words, and both an AIAP program and an AISP skill named: nothing says which one to run - ask (axiom 0)."""
    aiap = next(item for item in designated if item.protocol == "aiap")
    aisp = next(item for item in designated if item.protocol == "aisp")
    a, s = aiap.directory.name, aisp.directory.name
    zh = (f"你同时指定了 AIAP 程序「{a}」和 AISP 技能「{s}」，但没有说要做什么，无法判断运行哪一个。",
          (f"AIAP 程序：{_shown(aiap.directory, places)}", f"AISP 技能：{_shown(aisp.directory, places)}"),
          (f"运行 AIAP 程序「{a}」", f"运行 AISP 技能「{s}」", "取消"),
          "建议：说出要做什么，或者只指定一个。这只是建议，由你决定。")
    en = (f"Both the AIAP program \"{a}\" and the AISP skill \"{s}\" were named, with no words saying what to do; "
          "which one to run cannot be told.",
          (f"AIAP program: {_shown(aiap.directory, places)}", f"AISP skill: {_shown(aisp.directory, places)}"),
          (f"Run the AIAP program \"{a}\"", f"Run the AISP skill \"{s}\"", "Cancel"),
          "Suggestion: say what you want done, or name only one. This is only a suggestion; the choice is yours.")
    actions = [{"action": "call", "arguments": {"aisp": None}}, {"action": "call", "arguments": {"aiap": None}},
               {"action": "cancel", "arguments": {}}]
    return _doubt("WHICH_DESIGNATED_PROGRAM", "", zh, en, actions=actions,
                  facts={"aiap": str(aiap.directory), "aisp": str(aisp.directory)})


class _RunLookups:
    """What one call asks the engine about the kept runs before it prepares a run, asked once (docs/05SoulRun 87, #23).

    Several checks want the conversation's latest run and its index (_check_named_run, _designated_vs_unfinished,
    _other_build, _kept_designation, _prepare); each looked it up and read and checked the index again - a scan of every
    kept run for a new conversation, and 77 ms a read for a run whose index is 1.87 MB. Kept for one call: the latest run
    of a conversation (made under the prepare lock, where no other call creates or removes a run), and a run's index while
    its file is unchanged (size, modification time, file id); one written meanwhile is read again."""

    def __init__(self, prepare, cache_root: Path):
        self.prepare, self.cache_root = prepare, cache_root
        self._index_name = _engine.load("lib.run_store").RunStore.INDEX
        self._latest: dict = {}
        self._indexes: dict = {}

    def latest(self, session_id: str) -> Path | None:
        if session_id not in self._latest:
            self._latest[session_id] = self.prepare.latest_cache_for_session(self.cache_root, session_id)
        return self._latest[session_id]

    def index(self, cache_dir) -> dict | None:
        """The run's index as the engine reads it (prepare_cache._read_index), or None when it cannot be read."""
        path = Path(cache_dir)
        try:
            stat = (path / self._index_name).stat()
            seen = (stat.st_size, stat.st_mtime_ns, stat.st_ino)
        except OSError:
            seen = None
        kept = self._indexes.get(path)
        if seen is not None and kept is not None and kept[0] == seen:
            return kept[1]
        index = self.prepare._read_index(path)
        self._indexes[path] = (seen, index)
        return index


def _check_named_run(cache_dir, session_id: str, places: _select.Places, user_message: str, lookups: _RunLookups, *,
                     by_marker: bool = False) -> Ctx | None:
    """``cache_dir`` says "this message is for that run". When it does not hold, ask - never guess, never start another run quietly.

    ``by_marker``: the run is named inside the message, by the re-entry text a host makes with ``host.resume_prompt``
    (the engine takes such a message as "continue that run"). The same check holds, so that words typed into
    one conversation never re-enter another conversation's run; such a message can only be cancelled.
    """
    prepare = _engine.load("prepare_cache")
    target = Path(str(cache_dir)).expanduser().resolve()
    root = places.cache_root.resolve()
    problems_zh, problems_en, owner = [], [], None
    if target.parent != root or not target.name.isdigit() or not target.is_dir():
        problems_zh.append("它不是这个数据目录里的一场运行")
        problems_en.append("it is not a run in this data folder")
    else:
        index = lookups.index(target) or {}
        owner, state = index.get("session_id"), index.get("run_state")
        if owner != session_id:              # whose it is goes to ctx.doubt only: another conversation's id is not shown
            problems_zh.append("它不属于这个对话")
            problems_en.append("it does not belong to this conversation")
        if state not in prepare.PROTECTED_STATES:
            problems_zh.append(f"它已经结束（{state}）")
            problems_en.append(f"it has already ended ({state})")
        latest = lookups.latest(session_id)
        if not problems_zh and latest is not None and latest.resolve() != target:
            problems_zh.append("它不是这个对话最近的一场（引擎现在只能接最近的一场）")
            problems_en.append("it is not the latest run of this conversation (the engine can only continue the latest one)")
    if not problems_zh:
        return None
    if by_marker:
        zh = (f"这句话里的接回记号点名的那一场（{target.name}）对不上，没有接回。", tuple(problems_zh), ("取消",),
              "建议：接回的文字由宿主用 soulrun.host.resume_prompt 生成，并交给那一场所属的对话。这只是建议，由你决定。")
        en = (f"The re-entry text in this message names a run ({target.name}) that does not match; it was not re-entered.",
              tuple(problems_en), ("Cancel",),
              "Suggestion: a host makes re-entry text with soulrun.host.resume_prompt and sends it in the run's own "
              "conversation. This is only a suggestion; the choice is yours.")
        return _doubt("NAMED_RUN_MISMATCH", user_message, zh, en, actions=[{"action": "cancel", "arguments": {}}],
                      facts={"cache_dir": str(target), "problems": problems_en, "named_by": "recovery_marker",
                             "owner_session_id": owner})
    zh = (f"你点名要接着的那一场（{target.name}）对不上。", tuple(problems_zh),
          ("不点名，把这句话交给引擎按这个对话来判断（这个对话有没做完的一场时，会接回那一场）", "取消"),
          "建议：先确认要接着的是哪一场。这只是建议，由你决定。")
    en = (f"The run you named ({target.name}) does not match.", tuple(problems_en),
          ("Send the message without naming a run; the engine decides from this conversation "
           "(an unfinished run of this conversation will be continued)", "Cancel"),
          "Suggestion: check which run you meant first. This is only a suggestion; the choice is yours.")
    actions = [{"action": "call", "arguments": {"cache_dir": None}}, {"action": "cancel", "arguments": {}}]
    return _doubt("NAMED_RUN_MISMATCH", user_message, zh, en, actions=actions,
                  facts={"cache_dir": str(target), "problems": problems_en, "named_by": "cache_dir", "owner_session_id": owner})


def _other_build(places: _select.Places, session_id: str, lookups: _RunLookups) -> dict | None:
    """This conversation's unfinished run, when this very engine build did not create it: its note records another
    digest, or it has no note. The engine must not continue it - not even under the same version number."""
    prepare = _engine.load("prepare_cache")
    latest = lookups.latest(session_id)
    if latest is None:
        return None
    index = lookups.index(latest) or {}
    if index.get("run_state") not in prepare.PROTECTED_STATES:
        return None
    note = _records.read_run_record(places.soulrun_cache_dir, Path(latest).name)
    digest = _engine.manifest().get("digest")
    if note and note.get("engine_digest") == digest:
        return None
    return {"cache_dir": str(latest), "run_state": index.get("run_state"), "user_language": index.get("user_language"),
            "run_engine_version": str(index.get("engine_version") or ""), "engine_version": _engine.version(),
            "recorded_digest": (note or {}).get("engine_digest"), "engine_digest": digest}


def _other_build_turn(other: dict, message: str, places: _select.Places, human_turn: bool) -> Ctx:
    """The unfinished run belongs to another engine build (docs/05SoulRun 80 B2). A machine turn is refused as before.
    A human is asked - end that run, or work in another conversation - instead of the turn failing on every message.

    Only a run of this very engine version can be ended here, and only by a message that is one of the engine's own
    cancel words (prepare_cache.is_cancel_message): the engine's terminate_run marks it ended as a human ended it
    (human_termination); no node of it is run by this build. A run of another version is left exactly as it is."""
    if not human_turn:
        raise UsageError('ENGINE_BUILD_MISMATCH', 'This unfinished run belongs to another or unknown engine build; '
                         'keep it in its original environment and use a new cache root.', field='cache_dir',
                         expected='the exact engine digest recorded when the run began')
    run = Path(other["cache_dir"]).name
    endable = other["run_engine_version"] == other["engine_version"]
    if endable and _engine.load("prepare_cache").is_cancel_message(message):
        _engine.load("lib.engine_core").terminate_run(
            other["cache_dir"], kind="human_termination", by="human",
            reason="ended by the human: this run belongs to another engine build and cannot be continued by this one")
        _records.add_to_run_record(places.soulrun_cache_dir, run, ended_as_other_build=other["engine_digest"])
        zh = (f"那一场旧运行（{run}）已经结束：只把它标记为终止，现在的引擎没有往下执行它的任何步骤。",
              ("它已有的记录原样保留", "现在可以在这个对话里发新的请求"), (), None)
        en = (f"The old run ({run}) has ended: it was only marked as ended; the engine in use ran none of its steps.",
              ("What it had recorded is kept as it was", "You can send a new request in this conversation now"), (), None)
        return _doubt("ENGINE_BUILD_RUN_ENDED", message, zh, en, actions=[], facts={**other, "ended": True},
                      run_language=other["user_language"])
    state_zh = "在等你回答" if other["run_state"] == "WAITING_USER" else "还在进行"
    state_en = "waiting for your answer" if other["run_state"] == "WAITING_USER" else "still in progress"
    why_zh = "没有记录是哪个引擎构建开的" if other["recorded_digest"] is None else "是另一个引擎构建开的"
    why_en = "has no record of the engine build that began it" if other["recorded_digest"] is None \
        else "was begun by another engine build"
    options = [({"action": "ask", "arguments": {"session_id": None}}, "在另一个对话里发新的请求（换一个 session_id）",
                "Send a new request in another conversation (another session_id)"),
               ({"action": "cancel", "arguments": {}}, "先不处理（那一场原样保留）", "Leave it for now (that run is kept as it is)")]
    if endable:
        options.insert(0, ({"action": "call", "arguments": {"user_message": "取消"}},
                           "回复「取消」：结束那一场（只标记为终止，不再执行它的任何步骤）",
                           "Reply \"cancel\": end that run (it is only marked as ended; none of its steps is run)"))
        lines_zh = ("那一场原样保留，这一轮什么也没有改", "现在的引擎不能接着跑它，即使版本号相同")
        lines_en = ("That run is kept as it was; nothing was changed this turn",
                    "The engine in use cannot continue it, even under the same version number")
        advice_zh = "建议：那一场不再需要就回复「取消」结束它；要接着跑，回到开它的那个环境。这只是建议，由你决定。"
        advice_en = ("Suggestion: if that run is no longer needed, reply \"cancel\" to end it; to continue it, go back to "
                     "the environment that began it. This is only a suggestion; the choice is yours.")
    else:
        lines_zh = ("那一场原样保留，这一轮什么也没有改",
                    f"那一场是引擎 {other['run_engine_version'] or '（未知版本）'} 开的，现在的引擎 {other['engine_version']} 不能接着跑，也不能结束它")
        lines_en = ("That run is kept as it was; nothing was changed this turn",
                    f"It was begun by engine {other['run_engine_version'] or '(unknown version)'}; the engine in use "
                    f"({other['engine_version']}) can neither continue it nor end it")
        advice_zh = "建议：要接着跑或结束那一场，回到开它的那个环境；新的请求放到另一个对话里。这只是建议，由你决定。"
        advice_en = ("Suggestion: to continue or end that run, go back to the environment that began it; send new requests "
                     "in another conversation. This is only a suggestion; the choice is yours.")
    zh = (f"这个对话有一场没做完的运行（{run}，{state_zh}），它{why_zh}，所以这一轮没有交给引擎。", lines_zh,
          tuple(label for _, label, _ in options), advice_zh)
    en = (f"This conversation has an unfinished run ({run}, {state_en}) that {why_en}, so this turn was not handed to the engine.",
          lines_en, tuple(label for _, _, label in options), advice_en)
    return _doubt("ENGINE_BUILD_MISMATCH", message, zh, en, actions=[action for action, _, _ in options],
                  facts={**other, "endable": endable}, run_language=other["user_language"])


def _run_programs(cache_dir: Path) -> list[Path] | None:
    """The program folders a run was created with (the engine's own snapshot), or None when it cannot be read."""
    try:
        snapshot = json.loads((cache_dir / "_run_input.json").read_text(encoding="utf-8")).get("snapshot")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(snapshot, list):
        return None
    return [Path(item["dir"]).resolve() for item in snapshot if isinstance(item, dict) and item.get("dir")] or None


def _designated_vs_unfinished(designated: list, session_id: str, places: _select.Places, user_message: str,
                              lookups: _RunLookups) -> Ctx | None:
    """A program is named, and this conversation still has an unfinished run that was not created for exactly it.

    The engine continues one run per conversation. Handed the message, it would take it as an answer to that run, or
    hand that run back as if it were new (the same message again within two minutes) - and the named program would
    quietly not run. So the human is asked first: a named program is never quietly replaced (axiom 0).
    """
    prepare = _engine.load("prepare_cache")
    latest = lookups.latest(session_id)
    if latest is None:
        return None
    state = (lookups.index(latest) or {}).get("run_state")
    in_run = _run_programs(Path(latest)) if state in prepare.PROTECTED_STATES else None
    named = [item.directory.resolve() for item in designated]
    if not in_run or set(in_run) == set(named):
        return None
    run, names, theirs = Path(latest).name, "、".join(p.name for p in named), ", ".join(p.name for p in named)
    # docs/05SoulRun 90 round 7 (line C, C5; decision 183 完全一样): a run that reads RUNNING only because its engine stop was
    # cut off before its index write waits at that stop, as the run that never crashed does - it is called what that run is
    waiting = state == "WAITING_USER" or (state == "RUNNING" and prepare._cut_off_stop_id(Path(latest)) is not None)
    state_zh = "在等你回答" if waiting else "还在进行"
    state_en = "waiting for your answer" if waiting else "still in progress"
    elsewhere = ({"action": "ask", "arguments": {"session_id": None}},
                 f"在另一个对话里运行「{names}」（换一个 session_id）", f"Run \"{theirs}\" in another conversation (another session_id)")
    if user_message.strip():        # the words can go to that run instead, without the named program
        options = [({"action": "call", "arguments": {"aiap": None, "aisp": None}},
                    "把这句话交给那一场（这次不运行点名的程序）", "Give these words to that run (the named program does not run)"),
                   elsewhere, ({"action": "cancel", "arguments": {}}, "取消", "Cancel")]
    else:                           # no words: nothing to give that run; it keeps waiting as it is
        options = [elsewhere, ({"action": "cancel", "arguments": {}}, "不运行（那一场照常等着）",
                               "Do not run it (that run waits as it is)")]
    zh = (f"这个对话还有一场没做完的运行（{run}，{state_zh}），你点名的「{names}」不在那一场里，所以没有开始。",
          (f"那一场的程序：{'、'.join(p.name for p in in_run)}", "引擎一个对话只接着一场运行；那一场不结束，点名的程序不会在这个对话里开始"),
          tuple(label for _, label, _ in options),
          "建议：先把那一场做完，或者在那一场里回答「取消」结束它，再点名运行。这只是建议，由你决定。")
    en = (f"This conversation has an unfinished run ({run}, {state_en}); the program you named (\"{theirs}\") is not in it, "
          "so it was not started.",
          (f"Programs of that run: {', '.join(p.name for p in in_run)}",
           "The engine continues one run per conversation; until that run ends, the named program does not start in it"),
          tuple(label for _, _, label in options),
          "Suggestion: finish that run first, or answer \"cancel\" in it to end it, then name the program again. "
          "This is only a suggestion; the choice is yours.")
    actions = [action for action, _, _ in options]
    return _doubt("DESIGNATED_RUN_UNFINISHED", user_message, zh, en, actions=actions,
                  facts={"cache_dir": str(latest), "run_state": state, "run_programs": [str(p) for p in in_run],
                         "designated": [str(p) for p in named]})


def _candidates_for(places: _select.Places, designated: list) -> dict:
    """What _adapter must tell the engine about the candidates ({} = leave the engine alone)."""
    if designated:
        return _designated_adapter([item.directory for item in designated])
    if places.standard_layout:
        return {}
    if places.aiap_dir == places.agent_dir / "aiap" and places.aisp_dir == places.agent_dir / "aisp":
        return dict(agent_dir=places.agent_dir)
    roots: list[Path] = []                    # one folder given for both kinds is scanned once, not twice
    for folder in (places.aiap_dir, places.aisp_dir):
        if folder.is_dir() and folder.resolve() not in [root.resolve() for root in roots]:
            roots.append(folder)
    return dict(registry_roots=roots)


def _registry_folders_need_their_agent(places: _select.Places) -> None:
    """A program folder with its registry script (aiap/aiap_list.py, aisp/aisp_list.py) lists which of its programs are
    enabled, and the engine runs that script only when it is given the agent folder the program folder sits in. Handed
    over as a folder of its own it would be scanned, and a program the script leaves out would be a candidate again:
    refused before anything is created, so a folder gives the same candidates however it is named."""
    if places.standard_layout or (places.aiap_dir == places.agent_dir / "aiap" and places.aisp_dir == places.agent_dir / "aisp"):
        return                                         # the engine is given the agent folder: it runs the scripts itself
    for protocol, folder in (("aiap", places.aiap_dir), ("aisp", places.aisp_dir)):
        script = folder / _select.REGISTRY_SCRIPTS[protocol]
        if script.is_file():
            agent = (f"agent_dir={folder.parent}" if folder.name == protocol
                     else f"an agent folder holding it as {protocol}/, given as agent_dir")
            raise UsageError("REGISTRY_FOLDER_ALONE",
                             f"{folder} has its registry script {script.name}, which decides which of its programs are "
                             f"enabled; the engine runs it only through the agent folder: give {agent}, or name one "
                             f"program with {protocol}=", field=f"{protocol}_dir", expected=f"{agent}, or {protocol}=<program>")

def _designated_adapter(chosen: list) -> dict:
    return dict(registry_roots=sorted({Path(d).parent for d in chosen}), only=[Path(d) for d in chosen])


def _require_programs(places: _select.Places) -> None:
    """Before anything is created: a call that names no program needs at least one to choose from. Programs may sit
    deeper than one level when a registry script lists them, so the whole folder is looked through."""
    for protocol, folder in (("aiap", places.aiap_dir), ("aisp", places.aisp_dir)):
        if folder.is_dir() and next(folder.rglob(_select.ENTRY_FILES[protocol]), None) is not None:
            return
    raise UsageError("NO_PROGRAM_FOLDER",
                     f"no program to choose from: no {_select.ENTRY_FILES['aiap']} under {places.aiap_dir} and no "
                     f"{_select.ENTRY_FILES['aisp']} under {places.aisp_dir}", field="agent_dir",
                     expected="an agent folder whose aiap/ or aisp/ holds programs (agent_dir=...), or aiap_dir= / aisp_dir=")


def _kept_designation(session_id: str, places: _select.Places, lookups: _RunLookups) -> tuple[list[Path], str] | None:
    """No program named this time, while the conversation's unfinished run was created for named ones: those stay the
    candidates should the engine start a new run from it (the human chose "as a new task" after a Stop, for example) -
    a named program is never quietly widened to every program. The run that is continued is not touched by this."""
    prepare = _engine.load("prepare_cache")
    latest = lookups.latest(session_id)
    if latest is None or (lookups.index(latest) or {}).get("run_state") not in prepare.PROTECTED_STATES:
        return None
    try:
        record = json.loads(_records.run_record_path(places.soulrun_cache_dir, Path(latest).name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    chosen = [Path(d) for d in record.get("designated") or [] if isinstance(d, str)]
    if record.get("candidates") != "designated" or not chosen or not all(d.is_dir() for d in chosen):
        return None
    return chosen, Path(latest).name


def _default_session(places: _select.Places) -> str:
    """No session_id: one conversation per agent folder. With the agent's own run folder that is "default"; with a run
    folder named elsewhere - which several agents may share - the agent folder's fingerprint is part of the name, so a
    "继续" said in one project never reaches another project's run."""
    if places.soulrun_cache_dir == places.agent_dir / _select.SOULRUN_CACHE:
        return DEFAULT_SESSION
    return f"{DEFAULT_SESSION}-{hashlib.sha256(os.path.normcase(str(places.agent_dir)).encode('utf-8')).hexdigest()[:12]}"


_TRUE, _FALSE = ("1", "true", "yes", "on"), ("0", "false", "no", "off", "")


def switch_given(value, env: str, name: str) -> bool | None:
    """A switch as given: the argument when given (True or False), else the environment variable when it is set to a
    value, else None (not given). A value that is set but is not a switch value is an error - never quietly read."""
    if value is not None:
        if not isinstance(value, bool):
            raise UsageError("SWITCH_INVALID", f"{name} must be True, False or None, not {value!r}", field=name,
                             expected="True, False or None")
        return value
    raw = os.environ.get(env)
    if raw is None or not raw.strip():
        return None
    if raw.strip().lower() in _FALSE:
        return False
    if raw.strip().lower() in _TRUE:
        return True
    raise UsageError("SWITCH_INVALID", f"{env}={raw!r}", field=env, expected="1, true, yes or on; 0, false, no or off")


def read_switch(value, env: str, name: str, default: bool = False) -> bool:
    """A switch: as given (switch_given), else ``default``."""
    given = switch_given(value, env, name)
    return default if given is None else given


_TEXT_ARGUMENTS = ("session_id", "user_id", "channel", "model", "host_turn_id", "origin_type")
_PATH_ARGUMENTS = ("aiap_dir", "aisp_dir", "aiap", "aisp", "agent_dir", "soulrun_cache_dir", "cache_dir")
_RUN_ONLY = ("aiap_dir", "aisp_dir", "aiap", "aisp", "agent_dir", "soulrun_cache_dir", *_TEXT_ARGUMENTS,
             "host_fences", "host_tools", "human_turn", "inline_program", "slim_program")


def _wrong(name: str, value, expected: str, why: str = "") -> UsageError:
    return UsageError("ARGUMENT_TYPE", f"{name} = {value!r}" + (f": {why}" if why else ""), field=name, expected=expected)


def _check_arguments(values: dict) -> None:
    """The types a call must have, checked before anything is read or written: a wrong one would otherwise reach the
    engine and leave a half-made run behind, or be turned into words the human never said."""
    message = values["user_message"]
    if message is not None and not isinstance(message, str):
        raise _wrong("user_message", message, "str (the human's words, already decoded) or None",
                     "decode it first" if isinstance(message, (bytes, bytearray)) else "")
    for name in _TEXT_ARGUMENTS:
        value = values[name]
        if value is None:
            continue
        if not isinstance(value, str):
            raise _wrong(name, value, "str or None")
        if any(mark in value for mark in ("\n", "\r", "\x00")):
            raise _wrong(name, value, "one line of text", "it holds a line break or NUL")
    if values["session_id"] is not None and not values["session_id"].strip():
        raise _wrong("session_id", values["session_id"], "a non-empty str, or None for the default conversation")
    for name in _PATH_ARGUMENTS:
        value = values[name]
        if value is None:
            continue
        if not isinstance(value, (str, os.PathLike)) or isinstance(os.fspath(value), bytes):
            raise _wrong(name, value, "a path (str or pathlib.Path) or None")
        if not os.fspath(value).strip() or "\x00" in os.fspath(value):
            raise _wrong(name, value, "a path (str or pathlib.Path) or None", "empty or holding NUL")
    fences = values["host_fences"]
    if fences is not None and (isinstance(fences, (str, bytes)) or not all(isinstance(f, str) for f in fences)):
        raise _wrong("host_fences", fences, "a list of str (the kinds of streamed text the host captures) or None")
    tools = values["host_tools"]
    if tools is not None and (not isinstance(tools, Mapping) or not all(isinstance(k, str) and isinstance(v, bool)
                                                                       for k, v in tools.items())):
        raise _wrong("host_tools", tools, "a mapping of str to True or False, e.g. {'agent': False}, or None")
    if not isinstance(values["human_turn"], bool):
        raise _wrong("human_turn", values["human_turn"], "True or False")


def _context(doubt: Ctx, places: _select.Places, session_id: str) -> Ctx:
    """A doubt carries the places and the conversation it was raised for, like every other answer."""
    return dataclasses.replace(doubt, session_id=session_id, places=_places_view(places))


def _places_view(places: _select.Places) -> dict:
    return {k: str(getattr(places, k)) for k in ("agent_dir", "aiap_dir", "aisp_dir", "soulrun_cache_dir")} \
        | {"sources": dict(places.sources)}


def _doubts(cache_dir, message: str, session_id: str, places: _select.Places, designated: list,
            lookups: _RunLookups) -> Ctx | None:
    """The questions that depend on the runs kept: a named run, re-entry text naming a run, a named program."""
    prepare = _engine.load("prepare_cache")
    if cache_dir is not None:
        doubt = _check_named_run(cache_dir, session_id, places, message, lookups)
    else:
        marked = prepare.recovery_reentry_dir(message, places.cache_root)
        doubt = _check_named_run(marked, session_id, places, message, lookups, by_marker=True) if marked is not None else None
    if doubt is None and designated:
        doubt = _designated_vs_unfinished(designated, session_id, places, message, lookups)
    return doubt


# On Windows a run's index can be refused for a moment while another process replaces it: the model's engine commands
# and host.after_turn write it outside the prepare lock (_filelock). The engine reads the other runs before it creates
# anything, so the preparation is tried again after a short pause; a refusal that lasts is reported (the run folder).
PREPARE_PAUSES = (0.05, 0.2, 0.5)


def _human_reply_required() -> UsageError:
    return UsageError('HUMAN_REPLY_REQUIRED', 'Only a human reply may answer this open gate.', field='human_turn', expected=True)


def _waits_at_a_cut_off_stop(prepare, message: str, lookups: _RunLookups, latest: Path, index: dict, session_id) -> bool:
    """docs/05SoulRun 90 round 6 (ledger decisions 183 and 185, 'vc 2' and 'vc 3' defect 1): with the restart switch off, a
    run that reads RUNNING only because its engine stop was cut off before its index write is the run that never stopped,
    waiting at that stop: a turn that is not the human's is refused there as at the waiting run (below), before the engine
    is called, so nothing is written. The engine's own read-only check decides (prepare_cache._cut_off_stop_id, the one its
    prepare holds such a turn by, gate_hold). Left to the engine as before: the host's own recovery re-entry of a run of this
    conversation (its recovery marker - a checkpoint re-entry, a supply probe the human authorised), and the switch on
    (problem 89). Round 7 (line C, C2): where the check cannot be made - the run lock a killed process left (it stays until
    the engine reclaims it as stale, after two minutes), a record the check cannot read - the turn is refused all the same
    (`undecided`); only a lock its live holder keeps past the check's wait leaves the turn to the engine, as before."""
    if index.get('run_state') != 'RUNNING' or prepare.resume_interrupted_enabled():
        return False
    marked = prepare.recovery_reentry_dir(message, lookups.cache_root)
    if marked is not None and (lookups.index(marked) or {}).get('session_id') == session_id:
        return False
    return prepare._cut_off_stop_id(latest, undecided=True) is not None


def _prepare(prepare, message: str, lookups: _RunLookups, **arguments):
    machine = not arguments.get('human_turn', True)
    latest = lookups.latest(arguments.get('session_id'))
    if latest is not None:
        index = lookups.index(latest) or {}
        if index.get('run_state') in prepare.PROTECTED_STATES:      # a run of another engine build was settled before (_other_build)
            if machine and (index.get('run_state') == 'WAITING_USER'
                            or _waits_at_a_cut_off_stop(prepare, message, lookups, latest, index, arguments.get('session_id'))):
                raise _human_reply_required()
    for pause in PREPARE_PAUSES:
        try:
            data = prepare.prepare_execution_context(message, **arguments)
            break
        except PermissionError:
            time.sleep(pause)
    else:
        data = prepare.prepare_execution_context(message, **arguments)
    if machine and data is not None and data.get('gate_hold'):
        # Round 6: should the run reach a gate between the check above and the engine's own (a sub-agent's late pause, say),
        # the engine holds the turn (gate_hold); it is refused all the same - never a program turn, whose next-node would show
        # the gate to the main executor from a turn that is not the human's
        raise _human_reply_required()
    return data

@overload
def run(user_message: str | None = None, *,
        aiap_dir: PathArg | None = None, aisp_dir: PathArg | None = None, aiap: PathArg | None = None,
        aisp: PathArg | None = None, agent_dir: PathArg | None = None, soulrun_cache_dir: PathArg | None = None,
        session_id: str | None = None, cache_dir: PathArg | None = None,
        user_id: str | None = None, channel: str | None = None, model: str | None = None,
        host_fences: Sequence[str] | None = None, host_tools: Mapping[str, bool] | None = None,
        human_turn: bool = True, host_turn_id: str | None = None, origin_type: str | None = None,
        inline_program: bool | None = None, slim_program: bool | None = None, cmd: None = None) -> Ctx: ...


@overload
def run(user_message: None = None, *, cmd: str, cache_dir: PathArg | None = None, args: Sequence[str] | None = None,
        stdin: str | None = None, payload: Any = None, timeout: float | None = None, **options: Any) -> _cmd.CmdResult: ...


def run(user_message: str | None = None, *,
        aiap_dir=None, aisp_dir=None, aiap=None, aisp=None, agent_dir=None, soulrun_cache_dir=None,
        session_id: str | None = None, cache_dir=None,
        user_id: str | None = None, channel: str | None = None, model: str | None = None,
        host_fences=None, host_tools: Mapping | None = None,
        human_turn: bool = True, host_turn_id: str | None = None, origin_type: str | None = None,
        inline_program: bool | None = None, slim_program: bool | None = None,
        cmd: str | None = None, **cmd_args: Any) -> Ctx | _cmd.CmdResult:
    """Start or continue a run for ``user_message``; or run one engine command (``cmd``); or hand back the guide.

    See the guide (``soulrun()``) for the meaning of every argument.
    """
    values = dict(locals())
    _check_arguments(values)
    if isinstance(user_message, str) and user_message.startswith(BOM):
        # A byte-order mark from a file saved on Windows is not part of the user's words, and the engine does not
        # recognise "继续" behind one: it asked for confirmation instead of continuing.
        user_message = user_message[len(BOM):]
    has_message = user_message is not None and user_message.strip() != ""
    if has_message and cmd is not None:
        raise UsageError("MESSAGE_AND_CMD", "user_message and cmd cannot be given together",
                         field="cmd", expected="either user_message or cmd")
    if cmd is not None:
        given = [name for name in _RUN_ONLY if values[name] != (True if name == "human_turn" else None)]
        if given:
            raise UsageError("ARGUMENT_NOT_FOR_CMD", f"{', '.join(given)}: not passed to an engine command",
                             field=given[0], expected="the command's own options as keyword arguments (cache_dir=..., "
                             "node=...); one whose name soulrun itself uses goes in args=[...]")
        return _cmd.run(cmd, cache_dir=cache_dir, **cmd_args)
    if cmd_args:
        raise UsageError("UNKNOWN_ARGUMENT", f"unknown argument(s): {', '.join(sorted(cmd_args))}",
                         field=sorted(cmd_args)[0], expected="see the guide: soulrun()")
    # No words: with no program named there is nothing to run - the guide. With one
    # program named it is run: some programs need no words, and one that does asks the human (the engine's HSAW law).
    # With both an AIAP program and an AISP skill named, nothing says which one: the human is asked first.
    if not has_message and aiap is None and aisp is None:
        return _guide()
    if (channel or "") == "heartbeat":
        raise UsageError("HEARTBEAT_NOT_ENGINE", "a heartbeat turn never goes through the engine; do not call soulrun for it",
                         field="channel", expected="any channel other than heartbeat")

    inline = read_switch(inline_program, ENV_INLINE_PROGRAM, "inline_program")
    slim_asked = switch_given(slim_program, ENV_SLIM_PROGRAM, "slim_program")
    if inline and slim_asked:
        raise UsageError("PROGRAM_FORMS_CONFLICT", "inline_program (the whole main program) and slim_program (the slim "
                         "program) cannot both be asked for", field="slim_program", expected="at most one of the two")
    slim = (not inline) if slim_asked is None else slim_asked   # the slim form is the default; the whole program turns it off

    message = user_message if has_message else ""
    # Every question for the human is settled before anything is created: a doubt leaves nothing behind.
    places = _select.resolve_places(agent_dir=agent_dir, aiap_dir=aiap_dir, aisp_dir=aisp_dir,
                                    soulrun_cache_dir=soulrun_cache_dir, create=False)
    sid = session_id if session_id is not None else _default_session(places)
    designated = [_select.resolve_designated(protocol, value, places)
                  for protocol, value in (("aiap", aiap), ("aisp", aisp)) if value is not None]
    for item in designated:
        if not item.found:
            return _context(_designated_missing(item, places, message), places, sid)
    if not has_message and len(designated) > 1:
        return _context(_which_designated(designated, places), places, sid)
    if not designated:
        _require_programs(places)
        _registry_folders_need_their_agent(places)

    prepare = _engine.load("prepare_cache")
    if not places.soulrun_cache_dir.is_dir():           # nothing kept yet: the checks find no run and need no lock
        with _engine.translated():
            doubt = _doubts(cache_dir, message, sid, places, designated, _RunLookups(prepare, places.cache_root))
        if doubt is not None:
            return _context(doubt, places, sid)
        _select.make_cache_dir(places)                  # made with its .gitignore
    elif not (places.soulrun_cache_dir / _records.SOULRUN_DIR).exists():
        # An existing folder taken for the first time is kept out of version control before the lock below makes
        # .soulrun in it: whatever this call then ends in - a question asked under the lock, a machine turn refused
        # there - the folder has its .gitignore. Once .soulrun is there the folder is SoulRun's, and its .gitignore, or
        # its absence, is the owner's.
        _select.keep_out_of_version_control(places.soulrun_cache_dir)
    try:
        # Other processes - and other threads of this one, each opening the lock file itself - queue on the file lock
        # of this run folder (see _filelock). Under it the checks see what the engine will see. _PREPARE_LOCK is held
        # only while the engine's functions are replaced for this call (_adapter): a busy run folder never holds up
        # calls for other run folders.
        with _filelock.held(places.soulrun_cache_dir / _records.SOULRUN_DIR):
            lookups = _RunLookups(prepare, places.cache_root)    # new under the lock: another call may have made a run
            with _engine.translated():
                doubt = _doubts(cache_dir, message, sid, places, designated, lookups)
                if doubt is None and (other := _other_build(places, sid, lookups)) is not None:
                    doubt = _other_build_turn(other, message, places, human_turn)
                kept = None if designated else _kept_designation(sid, places, lookups)
            if doubt is not None:
                return _context(doubt, places, sid)
            adapter = _designated_adapter(kept[0]) if kept else _candidates_for(places, designated)
            with _PREPARE_LOCK, _adapter.candidates(**adapter), _engine.translated(interface=True):
                data = _prepare(prepare, message, lookups, engine_aiap_dir=places.soulrun_cache_dir, session_id=sid,
                                origin_channel=channel or "", requested_model=model, host_fences=host_fences, user_id=user_id,
                                host_tools=host_tools, human_turn=human_turn, host_turn_id=host_turn_id, origin_type=origin_type)
            # Only a run that was really created gets a note: the engine also says "fresh" when it hands the same run
            # back for the same message within two minutes (rebootstrap), and that run's note stays as it was written.
            if data is not None and not data.get("init_error") and data.get("entry_mode") == "fresh" and not data.get("rebootstrap"):
                named = [str(item.directory) for item in designated] or ([str(d) for d in kept[0]] if kept else [])
                _records.write_run_record(          # under the lock too: writing a note also prunes notes of removed runs
                    places, data,
                    candidates="designated" if named else "folders" if adapter.get("registry_roots") else "agent folder",
                    designated=named, kept_from=kept[1] if kept and not designated else None)
            # docs/05SoulRun 87 (#25): the engine's turn_id is the run's number on every turn; which turn of the run this
            # is, SoulRun counts beside the runs - under the lock, so two calls never take the same number. The run's
            # trace tells a run number given again; a rebootstrap keeps the turn's number for the same host turn only.
            turn = _records.count_turn(places.soulrun_cache_dir, _run_name(data), turn_id=data.get("turn_id"),
                                       host_turn_id=host_turn_id, trace_id=data.get("trace_id"),
                                       entry_mode=data.get("entry_mode"), rebootstrap=bool(data.get("rebootstrap"))) \
                if data is not None and data.get("cache_dir") and not data.get("init_error") else None
    except OSError as exc:
        raise UsageError("SOULRUN_CACHE_DIR_INVALID", f"the run folder {places.soulrun_cache_dir} cannot be used: {exc}",
                         field="soulrun_cache_dir", expected="a writable location") from exc
    if data is None:
        raise SoulRunError("ENGINE_NO_ANSWER", "the engine did not hand back a run", field="user_message")
    if data.get("init_error"):
        error = data["init_error"]
        raise SoulRunError(str(error.get("code") or "ENGINE_UNAVAILABLE"),
                           str(error.get("detail") or error.get("message") or "the engine could not create a run"),
                           field=error.get("field"), expected=error.get("expected"))

    # The entry-path form's blocks. A turn that runs nothing keeps them in every form: the context, the note and the
    # text-only assertion, never an entry block that would send the model to read main.aisop.json (_blocks.TEXT_ONLY_KEYS).
    blocks = _blocks.build(data, channel or "")
    program = form = None
    kind = "text_only" if _blocks.runs_nothing(data) else "program"
    problem = _slim_problem(places, data) if slim else None          # looked for on every turn, text-only ones too
    fallback = f"EARLIER_SLIM_PROBLEM: {problem}" if problem else None
    if kind == "program":
        form = "entry_path"
        if slim and fallback is None:                    # a note about an interruption is followed first (_blocks)
            try:
                program = _slim.entry_program(message, cache_dir=data.get("cache_dir"), entry_mode=data.get("entry_mode"))
            except (SoulRunError, OSError, ValueError) as exc:     # the slim program cannot be built: entry-path form
                fallback = f"SLIM_PROGRAM_UNAVAILABLE: {getattr(exc, 'code', type(exc).__name__)}"
            else:
                blocks, form = _blocks.build_slim(data, channel or "", program), "slim"
                _records.add_to_run_record(places.soulrun_cache_dir, _run_name(data), slim_used=True)
        elif inline:
            program = _blocks.inline_program(message)
            blocks, form = [*blocks, program], "full"
    # The slim program is handed out by engine node: this turn starts a new record of what it was given, which SoulRun's
    # command line adds to after each engine reply. A turn in another form keeps nothing from an earlier slim turn.
    if data.get("cache_dir"):
        if form == "slim":
            _slim.start_turn(data["cache_dir"], data.get("entry_mode"), turn=turn)
        else:
            _records.clear_delivered(data["cache_dir"])
    prompt = _blocks.system_prompt(form if kind == "program" else ("slim" if slim and not problem else None))
    return Ctx(kind=kind, text=_blocks.join(blocks), blocks=tuple(blocks), cache_dir=data.get("cache_dir"),
               entry_mode=data.get("entry_mode"), turn_id=data.get("turn_id"), session_id=data.get("session_id"),
               program=program, places=_places_view(places), data=dict(data), program_form=form,
               system_prompt=prompt, slim_fallback=fallback)


# The slim form gives way to the entry-path form, for one turn or for the rest of a conversation, when it cannot be used
# (docs/05SoulRun 49 §5, the user's choice of conditions 10-15; a turn with a note about an interruption keeps the slim
# form since docs/05SoulRun 53, the note followed first):
#   SLIM_PROGRAM_UNAVAILABLE - the slim program cannot be built (engine_node.aisop.json missing, or from another engine);
#   EARLIER_SLIM_PROBLEM - this run, or this conversation's previous run, went wrong in the slim form: when the next
#       turn came it was still at Router.match with nothing committed although the model had its turn - it took the node
#       and did not commit it, or the host closed the turn with no engine call at all (STALLED_AT_ROUTER_MATCH; a run
#       interrupted before the model acted is not counted, and neither is one where the model put a question to the
#       human at Router.match - two programs fit, say - and the run waits for the answer or this turn brings it,
#       docs/05SoulRun 82) - or it failed at an engine node (ENGINE_NODE_FAILED). The
#       problem is written in the run's note, so the run - and every later run of the conversation, which inherits it -
#       keeps the entry-path form; other conversations keep the slim form. It is looked for first, on every turn.
ENGINE_NODES = ("Router.match", "Router.cache-setup", "Engine.execute-report", "Engine.final-answer")


def _run_name(data: Mapping) -> str:
    return str(data.get("cache_name") or Path(str(data.get("cache_dir") or "")).name)


def _bare(name) -> str:
    return str(name or "").split("/")[-1]


def _index(cache_dir) -> dict:
    """The engine's own record of a run (state, current node, completed nodes), or {} when it cannot be read."""
    with contextlib.suppress(Exception):
        return _engine.load("prepare_cache")._read_index(Path(cache_dir)) or {}
    return {}


def _model_had_its_turn(cache_dir, index: dict) -> bool:
    """Router.match was served to the model, or the host closed a turn of this run (after_turn): the model acted."""
    served = ((index.get("nodes") or {}).get("Router.match") or {}).get("serves") or 0
    if served:
        return True
    with contextlib.suppress(Exception):
        lifecycle = _engine.load("prepare_cache")._read_lifecycle(Path(cache_dir)) or {}
        return bool(lifecycle.get("reconciled_at"))
    return False


def _asked_the_human(data: Mapping, index: dict) -> bool:
    """The model asked the human at Router.match: the run waits for the answer, or this turn brings it."""
    return bool(data.get("gate_answer")) or index.get("run_state") == "WAITING_USER"


def _slim_problem(places: _select.Places, data: Mapping) -> str | None:
    root, name = places.soulrun_cache_dir, _run_name(data)
    note = _records.read_run_record(root, name)
    if note is None:                    # a run SoulRun did not create keeps no note: nothing is known about it
        return None
    if note.get("slim_problem"):
        return str(note["slim_problem"])
    problem = None
    if data.get("entry_mode") != "fresh":
        index = _index(data.get("cache_dir"))
        if note.get("slim_used") and _bare((index.get("current") or {}).get("name")) == "Router.match" \
                and not index.get("completed") and _model_had_its_turn(data.get("cache_dir"), index) \
                and not _asked_the_human(data, index):
            problem = "STALLED_AT_ROUTER_MATCH"
    else:
        earlier = [(other, record) for other, record in _records.session_runs(root, str(data.get("session_id") or ""))
                   if other != name]
        if earlier:
            previous, record = earlier[-1]
            if record.get("slim_problem"):
                problem = f"INHERITED from run {previous}"
            elif record.get("slim_used"):
                index = _index(places.cache_root / previous)
                if index.get("run_state") == "FAILED" and _bare((index.get("current") or {}).get("name")) in ENGINE_NODES:
                    problem = f"ENGINE_NODE_FAILED in run {previous}"
    if problem:
        _records.add_to_run_record(root, name, slim_problem=problem)
    return problem
