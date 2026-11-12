"""Engine core for v7: init_run, serve (next-node), commit (node-commit), answer_gate (gate-answer).

Pure functions over RunStore + Program; the CLIs in python_tools/ are thin wrappers.
Rules: 04 series doc 01 v0.2 §4–§6 (protocol, lock-internal steps, rejection codes),
doc 02 R-xx / I-xx. Own implementation; nothing copied from v6.

Scope (doc 02 D5/D6, doc 05, doc 10): module sub-graphs ([aisop.<task>], [<file>.aisop.json],
RUN aisop.<task>) run through the very same next-node / node-commit protocol: the engine pushes a
frame, serves the sub-graph nodes under qualified ids (Parent/ns.Node, unlimited depth), keeps their
caches in _<Parent>/ with an engine-owned _manifest.json, and serves the module node itself once the
sub-graph reached its end node; map/join/context_filter rejected (UNSUPPORTED_RESERVED_KEY).
Executor (doc 305 / codex 102): normal / lite programs force main-inline. In node mode each
entry-file main node follows its execute_mode, in any graph. Same-file graph containers expand
their independent stages first; external modules inherit the nearest main executor. One bound
child reads agent_engine.aisop.json and runs its root and external descendants inline through
the common kernel, without nested Agent calls. HSAW stops for main to present the gate and receive
the human answer; native-child resume requires its bound parent and trusted host evidence.
Tickets never authorize another main node. Exhausted non-independent fallback needs actual
completion proof; independent ownership conflicts stop rather than silently self-review.

Write ordering (crash safety, R-37): every commit validates everything first, then writes the
node cache, then the index; a paused gate writes gate record -> cache -> index. A cache or gate
record without its index transition is an orphan. With replacement accounting the next serve or
commit forwards it only with a complete proof of the original transition (partial_commit, under the
resume policy) and otherwise stops with ENGINE_ORPHAN_WRITE_SET_UNPROVEN; without it, the next serve
re-applies an orphan cache as it always has. The only exception is an engine stop the Engine wrote
itself (gate record -> index) - dispatch_budget.pause()'s or program_guard.pause()'s program-integrity
stop - never delivered and never answered, that matches the run: the next serve, commit,
interpretation command or gate-answer installs it back into the index as its writer would have
(dispatch_budget.reinstall), whatever the accounting, and it still needs the human's answer. Each of
these four installs it first, before anything else reads the run: next-node (_serve), node-commit
(commit), the interpretation command (interpret_human_reply, since record 90 round 6) and gate-answer
(answer_gate); and
program_guard.pause() installs a cut-off integrity stop itself before it would open a second one - a
backstop for the one call that reaches pause() without installing first under the same lock (serve()'s
drift path, which takes the run lock again after _serve released it). pause()'s stop is recognised
while the run is RUNNING, the integrity stop also while
the run waits at a business gate or an engine dispatch stop - never while it already waits at an
integrity stop, where pause() writes none; the host's prepare calls gate-answer only while the run
waits at a gate, so there gate-answer installs only an integrity stop cut off over a waiting gate.
Matching includes the types and option frame its writer writes, with numbers compared by type as well
as value (a bool or a float never passes for an int); a dispatch stop's code with the facts its writer
writes for that code (the replacement basis that code offers, the liveness stop's fixed explanation,
the lapsed choice, the figures a budget code is given on - dispatch_budget._code_facts, round 7); the
values the index holds that the writer copied
or stamped (the node's status; for the integrity stop also the run state, the ticket it abandoned - or
that ticket with the host's return recorded since; none while the run waits at an engine dispatch stop,
whose ticket the writer leaves as it is (problem 94) - the payload it kept and the program it bound:
the one it loads at that node, the routed program, or at Router.match the registry snapshot entry the
kept payload's route names); an instant in order; a supersedes link to the answered engine stop it
retired (with the intent its reason names, and retired by that answer: a replacement choice refused, a
recorded replacement record 88's recovery could not carry out (its ticket no longer the part's), a
recheck that moved on - never a replacement carried out), on the stop opened for that answer (no return
query offered for the part since, where the retired liveness stop's basis records the query);
a budget proposal and its extension option as the writer computes them from the run now (while the
program's files differ from the run's binding, from the record's own default and roots); a lapsed
choice the record discloses, lapsed now; and that it can be served (rendered without writing). Not
checked: the wording of the question, explanation, advice, cause, closing and recommendation and the
labels and notes of the options other than the extension; the dispatch_error the writer copied; the
replacement basis's values, which answer() compares with the run's when the replacement is chosen (a
mismatch replaces nothing); which code a stop names that carries no fact of its own (no basis,
proposal or lapse facts, not the liveness stop - preflight's verdict is never recomputed); whether a
linked stop is the one opened for that answer where the retired stop records no query. Such a rewrite
changes what the stop says and where a recheck leads, or withholds a replacement, never authorises one.
Anything else - malformed data included, which never raises here - is left to the
rules above, as before problem 85 (with accounting the next step stops with
ENGINE_ORPHAN_WRITE_SET_UNPROVEN, or first opens a stop of its own where its preflight blocks).
Only a serve to the main executor writes a stop's menu and so marks it served - dispatch_budget.reply
and program_guard.reply with publish, from next-node and node-commit without an agent ticket, from the
interpretation command, and from a gate-answer at a stop already shown (an option not matched, a recheck
that does not pass); a sub-agent's next-node or node-commit, the reply of a gate-answer that opened,
installed or asked it and the render check write none - and until then no message is taken as its
answer (answer_gate, _unshown_stop); its first serve to the
main executor is its writer's reply (dispatch_budget.served), with, for a stop asked again, the line on
the answer before rebuilt from the records. Installed, the stop, its number, link and record, every
answer's outcome, ticket, dispatch and authorisation and what is served to the main executor are those
of the run that never stopped. That first serve cannot tell an answer completed by record 88's recovery
(which set the human's newer reply aside) from a first attempt where both leave the same records - a
refused replacement choice, a recheck that moved on to another condition: its line is then the first
attempt's, which states what was done and calls no reply valid, true of both (record 90, ledger
decision 190); where the records show the recovery - a recorded
replacement it could not carry out, a move back to the retired stop's own condition - the line says
what became of the recorded answer and that the reply received after it was not used, and calls no
reply valid (ledger decision 186, dispatch_budget._recovered_line) - with or without a crash in this
window (see dispatch_budget.reinstall);
a bookkeeping value the cut-off call had changed only in memory may lag. A host re-entry before that
step (prepare_cache's recovery and interrupted-turn paths, its restart question and the human-Stop judge
path) recognises the stop read-only and records no transport wait and no interruption, as for the run
waiting at it; it never installs it. The host's lifecycle calls answer on the run with a cut-off
integrity stop installed (program_guard.landed_view): an Agent-tool start (observe_dispatch_start) or
a failed delivery of the ticket it abandoned binds nothing, as on the run waiting at it; an SDK task
start of that ticket (record_dispatch_task_event) is bound as on that run, and a return of that ticket
is recorded and still lets the stop be installed. While an integrity stop is open over a waiting engine
dispatch stop, that stop's ticket is left as it is: no agent can be served or commit for it (every
serve and commit is refused; a commit's payload is kept, not accepted, and after the recheck it is named
to no later serve, as the run whose files never changed keeps it), though the host may still record its
start or return and an old agent may still be running. Over a waiting business gate likewise a commit's
payload is kept and, after the recheck, named to no later serve nor in the recheck's reply (the run whose
files never changed refuses that commit; round 7). An answer at the integrity stop cut off after its
gate record is completed as recorded by the next reply, never decided again
(program_guard._complete_answer, round 7), as record 88 completes one at a dispatch stop; no gate
record is rewritten.
"""
from __future__ import annotations

from . import runtime_identity

import base64
import binascii
import copy
import hashlib
import json
import os
import time
import re
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path

from . import aisop_parse, delivery_obligations, evidence_views, final_answer, hsaw_gate, program_loader, registry, render, schema_lite, source_support
from . import repairs   # alpha.99 (doc 239): repairs instead of refusals
from . import program_binding, program_guard, dispatch_budget, conditional_reply, dispatch_scope, dispatch_lifecycle, hsaw_readjudication
from . import model_view, reply_io   # alpha.106 (doc 265 E3): the resume brief's next capture and printed size
from . import contracts as _contracts   # alpha.97 (doc 233): the resident payload rules are contract data
from .run_store import MANIFEST, RunStore, RunStoreError, atomic_write_bytes, dumps, now_iso, seal_process_output, sha256_bytes, strict_loads

ENGINE_VERSION = "1.0.0"
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
NODE_MATCH, NODE_SETUP, NODE_REPORT, NODE_DIRECT = "Router.match", "Router.cache-setup", "Engine.execute-report", "DirectReply"
NODE_FINAL = "Engine.final-answer"   # alpha.45 (doc 90/91): the answer node after the execution report - no PLAN block, no node block; its public block is final_answer.txt
# alpha.85 (doc 182, user ruling 2026-09-21): the execution report is not routing and "final" did not say what the node is. The earlier
# identities stay readable AND finishable - a run whose catalog was planned under them completes under them.
LEGACY_REPORT, LEGACY_FINAL = "Router.report", "final"
NODE_SUMMARY = NODE_REPORT  # Python caller compatibility; old persisted identities remain distinct.
LEGACY_SUMMARY = "Router.summary"
ACCOUNTING_NODES = (NODE_REPORT, LEGACY_REPORT)   # the execution report node (accounting only); Router.summary carried the answer too and is not one
ANSWER_NODES = (NODE_FINAL, LEGACY_FINAL)   # the answer node
REPORT_NODES = (*ACCOUNTING_NODES, LEGACY_SUMMARY)
FINAL_NODES = (*ANSWER_NODES, LEGACY_SUMMARY, NODE_DIRECT)   # alpha.45: the commits that write the final answer (the execution report no longer does)
ANSWER_PART_NODES = (*ANSWER_NODES, LEGACY_SUMMARY)   # alpha.45: where semantics.report_parts is accepted
LEGACY_REPORT_MESSAGE_CONTEXT_MIN = 300  # Preserve old Report fallback coverage; NEVER filters mandatory messages.
FINAL_KEY_REPORT_MIN = 1300           # alpha.69: default key node - a main-graph Report this long, when the run delivered no User Message report
FINAL_KEY_REPORT_MIN_WITH_MESSAGES = 1800   # alpha.69: ... and this long when User Message reports exist (they are the primary deliverable then)
FINAL_REFERENCE_RULE = _contracts.text("final-answer.reference_required")
FINAL_NOTE = "final answer delivered as final_answer.txt"   # alpha.45: the machine-owned L1 placeholder of the `Engine.final-answer` node
FINAL_ANSWER_MIN_CHARS = 500
NO_MATCH = "no_match"
TERMINAL_STATES = ("COMPLETED", "ABANDONED", "FAILED")
BUDGET_DEFAULT_MS = {"engine": 300_000, "business": 1_200_000, "sub": 1_200_000}   # alpha.115: user-approved active-time observation budget, never a hard timeout.
SIBLING_OUTPUT_CAP = 3000      # doc 06 §3: frame.siblings output clip (legacy clip helper)
SIBLING_OUTPUT_INLINE_MAX = 600   # alpha.49 (doc 103): a sibling output above this rides as a marker + 300-character preview; the complete output is read through input_refs
ADDRESS_REF_KEY = "@ref"   # alpha.57 (doc 121 §8.5 / doc 122): an address inside output - the engine verifies the target and stores the address, never a copy
ADDRESS_REF_RESOLVED = "@resolved"   # alpha.57: the engine-owned companion of an address - kind, sha256, size, preview
ADDRESS_REF_VALUE = "@value"         # alpha.64 (doc 140 §2 #1): a resolved value under ADDRESS_INLINE_LIMIT characters rides beside its address
ADDRESS_REF_SELECT = "@select"       # alpha.64: engine-internal - the ledger coordinates an auto-converted evidence:sources carries into resolution
ADDRESS_REF_PREVIEW = 300
ADDRESS_INLINE_LIMIT = 500   # alpha.63 (doc 137 §6.4): an output value of this many characters or more is an address, else OUTPUT_VALUE_INLINE_OVER_LIMIT
ADDRESS_AUTO_MIN = 300       # alpha.63 (doc 137 §3 L2): a verbatim copy of an existing text at least this long is converted to its address
ADDRESS_INLINE_LIMIT_STRUCTURED = 2000   # alpha.64 (doc 140 §2 #3): an inline object or list is reported as OUTPUT_VALUE_INLINE_OVER_LIMIT only from this size
ADDRESS_TINY_LIMIT = 100                 # alpha.65 (doc 141): a resolved value under this many characters keeps only {"kind"} in @resolved
_BAD_ESCAPE_RE = re.compile(r'\\(?!["\\/bfnrtu])')   # alpha.58: a backslash before a character JSON cannot escape (the model's Markdown \_ \* \()
_INTENT_BAD_RE = re.compile(r"[^a-z0-9_]+")   # alpha.58: gate intents are normalised to ^[a-z][a-z0-9_]*$ instead of rejected
_OUTPUT_VERBATIM_KEYS = ("raw_user_message", "user_message", "user_input", "user_request", "user_question", "divination_question", "question",
                         "human_decisions")   # alpha.58 B8 (doc 125 §9.3 #7-8): never counted as undeclared narration
SIBLINGS_TOTAL_CAP = 20000
MODULE_OUTPUT_INLINE_MAX = 4000   # alpha.48 C3' (doc 80 / 101): a module's last_node.output above this rides as a marker, never inline
RUN_INPUT = "_run_input.json"
GOVERNANCE_PATTERNS = (".aisop.json", "AIAP.md", "quality_baseline.json", "agent_card.json", ".version_history")
# doc 10 §3: sub-agent dispatch tickets
SPAWN_HARD_LIMIT = 48               # ordinary claims; declared independent work has its own 16/20 pool
DISPATCH_ATTEMPTS_MAX = 2           # unclaimed / abandoned attempts before dispatch is EXHAUSTED (inline fallback allowed)
DISPATCH_CLAIM_GRACE_MS = 60_000    # an ISSUED ticket younger than this is not re-issued: the sub-agent may still be starting
DISPATCH_CLAIMED_STALE_MS = 3_600_000   # doc 11 §2.3: a CLAIMED ticket is only silently abandoned after this (explicit abandon / host recovery are the normal paths)
DISPATCH_POLICY_NODE, DISPATCH_POLICY_INLINE = "node_mode_follows_execute_mode", "normal_forces_inline"
# docs/05SoulRun 87 (record 86 #2; 04 series doc 291 §5): what the main agent's reply to a dispatch it must start keeps - it spawns the
# sub-agent, waits and presents refs and gates, never executes the node; the node package goes whole to the sub-agent's CLAIMED reply
MAIN_DISPATCH_VIEW = ("node", "steps", "dispatch", "gate", "resume", "public_plan", "public_plan_ref", "payload_rules")
MAIN_DISPATCH_SECTIONS = ("resume.dispatch_segments", "resume.presentation")   # the rule sections addressed to the main executor
CANCEL_WORDS = {"取消", "cancel", "拒绝", "reject", "no", "否"}
TERMINATE_WORDS = {"终止", "stop", "abort", "结束", "terminate", "quit"}
# docs/05SoulRun 90 (problem 41; ledger decisions 183 to 187, protection first): a self-reported execution time is a digit tied
# to a timing field - after the field in its clause or inside a bracket opened there; in the structure below a heading, label or
# caption line that names the field (decision 185: a caption is a line naming it that does not end a sentence; decision 186: below
# a caption as below a heading; decision 187 (b): below a caption that reads as a clause too, except that a line starting with a
# digit there is no claim and is not carried over); beside a line whose value is the field, in its bracket or
# YAML mapping; in a table column the field heads; or in a structured output under a key naming the field, beside a value that is
# the field or a caption, or in its column of a table given as lists - not a field merely named (for example to explain a
# program's instruction). Every rule is a forward scan or a bounded look, a range scanned without a digit is never scanned
# again for a later field inside it, and no pattern can match a character two ways inside a repetition (round 7, A1: the HTML tag,
# the blockquote marks before a key, leader runs, the caption tail), so the check is linear in the text.
# TIMING_CLAIM_RULE states exactly what is refused and what is accepted.
TIMING_FIELDS = ("started_at", "ended_at", "elapsed_ms", "active_elapsed_ms", "human_wait_ms", "committed_at")
_TIMING_NAMES = "|".join(sorted(TIMING_FIELDS, key=len, reverse=True))
# the field as a whole name: not inside a longer identifier (max_elapsed_ms, started_at_1); Markdown underscores around it
# (_x_, __x__, ___x___) are markup; any other text right before or after it (耗时elapsed_ms：1200, elapsed_ms约1200) does not hide it
_TIMING_FIELD_RE = re.compile(r"(?<![A-Za-z0-9_])_{0,3}(" + _TIMING_NAMES + r")(?!_*[A-Za-z0-9])")
_TIMING_DIGIT_RE = re.compile("[0-9０-９]")                       # a digit: ASCII or full-width
_TIMING_VALUE_RE = re.compile(r"[0-9０-９][\w:.+\-]{0,40}")      # the value a claim quotes, from its first digit (masked text)
# no value: the digits of an HTML tag's name (<h2>, </h3>) and of an HTML entity (&#58;) - an attribute value is text
# (elapsed_ms="1200"), and an entity that encodes a digit (&#49;) is a digit; _timing_masked hides the others
# round 7 (line-A-41_2 defect 2): each tag has one way to match - a '/' before '>' belongs to the attributes when there are any
# (up to 200 characters, or 200 and the '/') - so a run of tags repeated in a pattern never backtracks exponentially; the same
# tags match as before (<br />, <br/>, <td data-x="1">)
_TIMING_HTML_TAG = r"</?[A-Za-z][A-Za-z0-9]{0,9}(?:/|[^\S\n](?:[^<>\n]{0,200}|[^<>\n]{200}/))?>"
_TIMING_ENTITY = r"&(?:#([0-9]{1,7})|#[xX]([0-9A-Fa-f]{1,6})|[A-Za-z][A-Za-z0-9]{1,9});"
_TIMING_MARKUP_RE = re.compile(_TIMING_HTML_TAG + "|" + _TIMING_ENTITY)
_TIMING_ENTITY_MARK_RE = re.compile(_TIMING_ENTITY)                 # an entity inside a tag's attributes
_TIMING_TAG_NAME_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]{0,9}")    # a tag's name: its digits are no value
# (1) where a field's clause ends: 。；！？; anywhere, . ! ? before a space or the end (a '.' right after another '.' is a run of dots)
_TIMING_CLAUSE_END_RE = re.compile(r"[\n。；！？;]|[!?](?=\s|\Z)|(?<!\.)\.(?=\s|\Z)")
_TIMING_ABBREVIATION_RE = re.compile(   # a '.' that ends one of these words does not end the clause: elapsed_ms approx. 1200
    r"(?<![A-Za-z0-9_.])(approx|appr|apx|ca|circa|est|avg|tot|min|max|no|nr|vs|etc|incl|excl|resp|cf|abt|e\.g|i\.e|a\.m|p\.m"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\Z", re.I)
_TIMING_NEXT_WORD_RE = re.compile(r"[^\S\n]+(\S)")               # after 'etc.': a new sentence starts with a capital or CJK letter
_TIMING_CJK = tuple((chr(low), chr(high)) for low, high in ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF),
                                                           (0xF900, 0xFAFF)))   # kana, CJK ideographs, hangul
_TIMING_ENTITY_RE = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{1,9}|#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6})\Z")   # a ';' ending &nbsp; or &#58;
_TIMING_ASIDE_RE = re.compile(r"[(（][^()（）\n]{0,40}[)）]")      # a terminator inside it does not end the clause
# (2) a { or [ opened in the clause: up to its matching bracket, or a blank line (where an unclosed structure ends)
_TIMING_BRACKET_RE = re.compile(r"[{}\[\]]|\n[^\S\n]*(?=\n)")
# (3) a label line: it ends with a separator, an opening bracket, 'approx.' or a YAML block indicator (trailing blanks, markup, tags
# and a '#' comment after the separator that follows the field - or, with none, after the field - aside), or holds only the field
# (a heading mark, bullet or ordered-list number before it allowed); a heading line names the field
# a separator: : ： = ＝, also written as an HTML entity (&#58; &colon; &#61; &equals;, the full-width ones too)
_TIMING_SEP = r"(?:[:：=＝]|&(?:#0*(?:58|61|6530[69])|#[xX]0*(?:3[aAdD]|[fF][fF]1[aAdD])|colon|equals);)"
_TIMING_SEPARATOR_RE = re.compile(_TIMING_SEP)
_TIMING_COMMENT_RE = re.compile(r"(?<=\s)#")
_TIMING_TAG = r"</?[A-Za-z][A-Za-z0-9]{0,9}>"                       # an HTML tag: <b>, </td>
_TIMING_TAG_RE = re.compile(_TIMING_TAG)
# whitespace, zero-width characters too
_TIMING_BLANK = r"[^\S\n]|[\N{ZERO WIDTH SPACE}-\N{ZERO WIDTH JOINER}\N{WORD JOINER}\N{ZERO WIDTH NO-BREAK SPACE}]"
_TIMING_TRAILING_RE = re.compile(r"(?:" + _TIMING_BLANK + r")*")    # on the reversed line
_TIMING_TAIL_RE = re.compile(r"(?:" + _TIMING_BLANK + r"|[*_`~'\"”’」』|]|>[A-Za-z0-9]{0,9}[A-Za-z]/?<|;psbn&)*")   # reversed line
_TIMING_LABEL_END_RE = re.compile(r"(?:" + _TIMING_SEP + r"(?:[^\S\n]*[|>][-+]?)?|[{\[]"
                                  r"|(?<![A-Za-z])(?:approx|appr|apx|ca|circa|abt|est)\.)\Z", re.I)
_TIMING_QUOTED = r"[^\S\n]*(?:>[^\S\n]*)*"                          # indentation and blockquote marks
_TIMING_QUOTED_RE = re.compile(_TIMING_QUOTED)   # read once before a key (_timing_key, _timing_valued): a key may start with '>'
# an ordered-list number: 1. 1) 1、 1） 1． (1) （1） [1], also inside ** * __ _
_TIMING_ORDINAL = r"(?:[*_]{1,3})?(?:[(（][0-9０-９]{1,3}[)）]|[\[［][0-9０-９]{1,3}[\]］]|[0-9０-９]{1,3}[.)、）．])(?:[*_]{1,3})?"
_TIMING_FIELD_LINE_RE = re.compile(_TIMING_QUOTED + r"(?:#{1,6}[^\S\n]+|[-*+•][^\S\n]+|" + _TIMING_ORDINAL + r"[^\S\n]*)?(?:[*_`~'\"“”‘’「」『』]|"
                                   + _TIMING_TAG + ")*(?:" + _TIMING_NAMES + ")")
_TIMING_HEADING_RE = re.compile(_TIMING_QUOTED + r"(?:[-*+•][^\S\n]+)?(?:#{1,6}(?=\s|\Z)|<[hH][1-6](?=[\s>]))")   # Markdown, HTML
_TIMING_EMPHASIS_RE = re.compile(_TIMING_QUOTED + r"(?:[-*+•][^\S\n]+)?(\*{1,3}|_{1,3})(?=\S)[^\n]*\1")   # a line wholly emphasised
_TIMING_UNDERLINE_RE = re.compile(r"[^\S\n]*(?:=+|-{2,})[^\S\n]*")                               # a setext heading's underline
# a line holding only the field in brackets: [elapsed_ms], [[started_at]] (a TOML or INI section)
_TIMING_BRACKET_HEADING_RE = re.compile(_TIMING_QUOTED + r"\[{1,2}[^\S\n]*(?:[*_`~'\"]|" + _TIMING_TAG + ")*(?:" + _TIMING_NAMES
                                        + r")(?:[*_`~'\"]|" + _TIMING_TAG + r")*[^\S\n]*\]{1,2}")
# a caption line (decision 185) names the field and ends no sentence: with trailing blanks, markup, closing brackets and quotes, a
# footnote mark ([1], [^2]), HTML tags and &nbsp; aside - and, round 7 (line-A-41_1 defect 9), symbols and emoji (✅ 👍 ★ →), a
# Markdown hard break (a trailing \) and a code span holding no _ (`#41`) - (read from the end), its last character is none of
# 。．.!?！？；;… - and it is no table row (but a table's title row, whose one non-empty cell names the field, and an HTML <caption>
# line are captions). Each alternative starts with its own characters (']' of a footnote mark and '`' of a code span are taken
# only by theirs): one way to read each character
_TIMING_SYMBOLS = "←-⇿⌀-⏿①-⓿■-➿⤀-⥿⬀-⯿️⃣\U0001f000-\U0001faff"
_TIMING_CAPTION_TAIL_RE = re.compile(r"(?:\][0-9０-９]{1,3}\^?\[|" + _TIMING_BLANK
                                     + r"|`[^`_\n]{1,60}`|[*_~'\"”’」』)}）］｝】》〉»›\\" + _TIMING_SYMBOLS + r"]"
                                     + r"|\](?![0-9０-９]{1,3}\^?\[)|`(?![^`_\n]{1,60}`)|>[^<>\n]{0,210}<|;psbn&)*")   # reversed
_TIMING_SENTENCE_END = frozenset("。．.!?！？；;")
_TIMING_CAPTION_END = _TIMING_SENTENCE_END | frozenset("…⋯")      # a line ending with one of these is a complete sentence
_TIMING_TABLE_ROW_RE = re.compile(r"[^\S\n]*</?(?:table|thead|tbody|tfoot|tr|th|td)(?=[\s>/])", re.I)   # a line that is a table row
_TIMING_HTML_ROW_TAG_RE = re.compile(r"</?t[rdh](?=[\s>/])", re.I)   # a row or cell tag anywhere in a line: <tr> <td> <th> </td>
# decision 186: a caption whose field follows at least four words on its line (outside a bracket) reads as a clause - the
# words counted between blanks, each holding a letter or digit, and three CJK characters counting as two words (_timing_clause)
_TIMING_CLAUSE_UNITS = 12                                            # four words, in thirds of a word
# the structure below a heading, label or caption: a fenced code block, a list or indented block, a { or [, a table, a run of
# 'key: value', definition-list or 'name number' lines
# a list bullet: - * + • followed by a blank, or one of these signs (a blank after it optional), circled numbers too
_TIMING_BULLET_SIGNS = "·・●○◦▪▫■□◆◇►▶▸▹‣⁃→⇒➤➢✓✔☑✗✘※★☆◎"
_TIMING_BULLET = r"(?:[-*+•][^\S\n]|[" + _TIMING_BULLET_SIGNS + r"①-⒛❶-➓])"
# a letter or CJK ordinal: a) b. i. iv) 一、 二． （三） (四) - a single letter or roman numeral before . or ) and a blank
_TIMING_WORD_ORDINAL = (r"(?:(?:[A-Za-z]|(?:i{1,3}|iv|vi{0,3}|ix|x|I{1,3}|IV|VI{0,3}|IX|X))[.)][^\S\n]|[一二三四五六七八九十]{1,3}[、．.)）]"
                        r"|[(（][一二三四五六七八九十]{1,3}[)）])")
_TIMING_LIST_RE = re.compile(_TIMING_QUOTED + r"(?:" + _TIMING_BULLET + "|" + _TIMING_ORDINAL + "|" + _TIMING_WORD_ORDINAL
                             + ")")                                  # a line that starts a list item
_TIMING_LIST_HEADS = frozenset("-*+•>_(（[［0123456789０１２３４５６７８９一二三四五六七八九十" + _TIMING_BULLET_SIGNS
                               + "".join(map(chr, range(0x2460, 0x249C))) + "".join(map(chr, range(0x2776, 0x2794)))
                               + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
# the start of a structure line that is not a value: indentation, quote marks, a bullet, an ordered-list number followed by words
_TIMING_ITEM_RE = re.compile(_TIMING_QUOTED + r"(?:" + _TIMING_BULLET + r"[^\S\n]*)?(?:" + _TIMING_ORDINAL
                             + r"(?=[^\S\n]*[^\s0-9０-９]))?")
_TIMING_FENCE_RE = re.compile(r"[^\S\n]*(```|~~~)")
_TIMING_OPENER_RE = re.compile(r"[^\S\n]*[{\[]")
_TIMING_HTML_ROW_RE = re.compile(r"[^\S\n]*</?(?:table|thead|tbody|tfoot|tr|th|td|caption)(?=[\s>/])", re.I)
# a 'key: value' line: a key of up to 80 characters that does not start with a digit (digits may follow: Step 1, 第1步) - or
# starts with up to three digits and a letter right after them (1号节点, 1st node) - then : ： = or ＝; only a digit after the
# separator is a value. Round 7 (A1): the indentation and blockquote marks before it are read once (_TIMING_QUOTED_RE), the key
# after them; the key that starts at the last '>' of them - the only other key that can end at the same separator - is read
# by _timing_key (round 6's single pattern tried every '>' as a key start: 80 steps per mark)
_TIMING_KEY_TAIL_RE = re.compile(r"(?:" + _TIMING_BULLET + r"[^\S\n]*)?(?=[^\s:：=＝0-9０-９]|[0-9０-９]{1,3}[^\W\d_])"
                                 r"[^\s:：=＝][^:：=＝\n]{0,79}[:：=＝]")
_TIMING_KEY_GT_RE = re.compile(r">[^:：=＝\n]{0,79}[:：=＝]")
_TIMING_DEFINITION_RE = re.compile(_TIMING_QUOTED + r"[:：][^\S\n]+")   # a definition-list line: ': Start 1200'
# a 'name number' row (Start 1200 ms, Start -> 1200, Start (1200 ms), Start ........ 1200, Start,1200,...): what stands between
# the name and the number (read from the end), and what stands around the name (indentation, quote marks, HTML tags, markup)
_TIMING_ROW_SEP_RE = re.compile(r"(?:[^\S\n]|>-|>=|[-–—→⇒=＝:：~≈(\[（［,，]|\.{2,}(?!\.)|…+(?!…)|·{2,}(?!·))+")   # a leader run: whole
_TIMING_ROW_EDGE_RE = re.compile(r"(?:[^\S\n]|>|<[^<>\n]{1,80}>|[*_`~'\"“”‘’「」『』])*")
_TIMING_ROW_TAIL_RE = re.compile(r"(?:[^\S\n]|>[^<>\n]{1,80}<|[*_`~'\"“”‘’「」『』])*")           # reversed
# after the number: where the row's value part ends - the next pair (, ; ， ； 、 / ／ | ｜ or a tab), a note in brackets, a dash
# between blanks or an en or em dash, or two blanks or more (an aligned column)
_TIMING_ROW_STOP_RE = re.compile(r"[,;，；、/／|｜\t(（\[［]|[^\S\n]{2,}|[^\S\n]-[^\S\n]|[–—]")
_TIMING_ROW_CLAUSE_MARKS = frozenset(",;，；、")                   # clause punctuation is no part of a row's name
_TIMING_CJK_CHARS = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff"   # kana, CJK ideographs, hangul
_TIMING_CJK_CHAR_RE = re.compile("[" + _TIMING_CJK_CHARS + "]")
_TIMING_CJK_RUN_RE = re.compile("[" + _TIMING_CJK_CHARS + "]{5}")   # five CJK characters in a row: prose
_TIMING_WORD_CHAR_RE = re.compile("[^\\W_" + _TIMING_CJK_CHARS + "]")   # a letter or digit that is no CJK character
_TIMING_ROW_UNIT_RE = re.compile(r"(?:ms|毫秒|秒|seconds?|secs?|s|minutes?|mins?|分钟)", re.I)
_TIMING_CJK_UNIT_RE = re.compile("毫秒|秒|分钟")                     # a CJK unit, also with CJK text right after it: 1200 毫秒用于
_TIMING_NUMBER_RE = re.compile(r"[0-9０-９]+(?:[.:][0-9０-９]+)*")    # a value's number: 1200, 1.2, 10:00 (a unit may follow it)
_TIMING_WORD_MARKS = "。．.!?！？；;…*_`~'\"”’」』)）]］"                  # around a word after a value: no word of its own
# the start of the next line before its first digit: markup (an HTML tag or entity, _) and punctuation other than '#' (#1 is a heading)
_TIMING_LEAD_RE = re.compile(r"(?:(?:" + _TIMING_HTML_TAG + r"|&[A-Za-z][A-Za-z0-9]{1,9};|[^\w\s#]|_)[^\S\n]*)*[0-9０-９]")
# (4) tables: a Markdown delimiter row, the cell tags of an HTML row, CSV/TSV header cells
_TIMING_DELIMITER_RE = re.compile(r"(?:\s|[|:\-\N{ZERO WIDTH SPACE}-\N{ZERO WIDTH JOINER}\N{WORD JOINER}\N{ZERO WIDTH NO-BREAK SPACE}])*")
_TIMING_HTML_CELL_RE = re.compile(r"<t[hd](?=[\s>])[^>\n]{0,80}>", re.I)
_TIMING_HTML_SPLIT_RE = re.compile(r"(?=<t[hd][\s>])", re.I)          # an HTML row split before each cell tag: the tag stays
_TIMING_MARKS = r"[\s\"'`*_~]*"
_TIMING_UNIT = r"(?:[(\[（][^()\[\]（）\n0-9０-９]{0,12}[)\]）]" + _TIMING_MARKS + ")?"
# the field itself as a cell or a string value: quotes, markup, a unit in brackets and a trailing separator aside
_TIMING_FIELD_CELL_RE = re.compile(_TIMING_MARKS + "(?:" + _TIMING_NAMES + ")" + _TIMING_MARKS + _TIMING_UNIT
                                   + "(?:[:：=＝]" + _TIMING_MARKS + ")?")
# what _TIMING_MARKS matches, as characters to strip from a cell's ends: every character \s matches (all lie below U+3001) and quotes,
# markup; a header cell's name holds none of " ' ( ) [ ] （ ） or a line break, its unit no bracket or line break
_TIMING_MARK_CHARS = "".join(c for c in map(chr, range(0x3001)) if c.isspace()) + "\"'`*_~"
_TIMING_NAME_STOP_RE = re.compile("[\"'()\\[\\]（）\n]")
_TIMING_BRACKETS_RE = re.compile("[()\\[\\]（）\n]")
_TIMING_DIGIT_LED_RE = re.compile(_TIMING_MARKS + "[0-9０-９]")       # a cell that starts with a digit
_TIMING_ROW_KINDS = (("html", None), ("pipe", "|"), ("tab", "\t"), ("comma", ","), ("semicolon", ";"))
# (3) a line whose value is the field (text JSON, YAML, TOML): a key (quoted or not), : ： = or ＝, then the field alone. Round 7:
# the marks before the key are read once, the rest of the line by _TIMING_VALUED_RE, a bare key from their last '>' by
# _timing_valued (as for _timing_key)
_TIMING_VALUED_TAIL = "[:：=＝]" + _TIMING_MARKS + "(?:" + _TIMING_NAMES + ")" + _TIMING_MARKS + _TIMING_UNIT + r"(?:[,;][^\S\n]*)?"
_TIMING_VALUED_RE = re.compile(r"(?:[-*+•][^\S\n]+)?(?:\"[^\"\n]{1,80}\"[^\S\n]{0,8}|'[^'\n]{1,80}'[^\S\n]{0,8}"
                               r"|[^\s:：=＝\"'][^:：=＝\n]{0,79})" + _TIMING_VALUED_TAIL)
_TIMING_VALUED_GT_RE = re.compile(r">[^:：=＝\n]{0,79}" + _TIMING_VALUED_TAIL)
_TIMING_ELEMENT_RE = re.compile(r"[^\S\n]*[\"']" + "(?:" + _TIMING_NAMES + r")[\"'][^\S\n]*(?:,[^\S\n]*)?")   # an array element: "elapsed_ms",
TIMING_CLAIM_RULE = (
    "Refused: any digit (0-9, ０-９) tied to a timing field - the name itself, also inside Markdown underscores or right next to "
    "other text (耗时elapsed_ms：1200), not a longer identifier (ASCII letters, digits or _ joined to it: started_at_1, "
    "max_elapsed_ms). Line breaks are \\n, \\r\\n or \\r. The digits of an HTML tag's name (<h2>, </h3>) and of an entity (&#58;) "
    "are not digits, but an attribute value is text (elapsed_ms=\"1200\"), also in a table cell's own tag, and an entity encoding "
    "a digit (&#49;) is one. A digit is tied to the field (1) after it in its clause, on its line - a clause ends at 。；！？; or at . "
    "! ? before a space or the line end, but not inside a parenthesis of up to 40 characters (opened before or after the field), "
    "at the ; of an HTML entity (&nbsp;), in a run of dots, or at the . of an abbreviation: approx appr apx ca circa est avg tot "
    "min max no nr vs incl excl resp cf abt e.g i.e a.m p.m jan feb mar apr jun jul aug sep sept oct nov dec mon tue tues wed thu "
    "thur thurs fri sat sun, in any case - etc. too unless a space and a capital or CJK letter follow; (2) inside a { or [ opened "
    "in that clause, up to its closing bracket or a blank line; (3) below a heading, label or caption line that names it, after at "
    "most two blank lines: in what the first line there opens; if that line is no list item or indented line and starts with a "
    "digit after markup or punctuation other than # (protection first: even '2 nodes were sent back', '1: …' or '1 - …'), also "
    "when it opens a key run ('1号节点：…'), that digit; if it opens nothing, or a structure without a digit that is one line (a "
    "fenced block holding at most one line, or a run of key: lines with nothing after their separators: 'Unit: ms', 'Values in "
    "milliseconds:'), in what the next non-blank line opens (at most two blank lines before it) - after the own one-line block of "
    "an indented or list-item line, only when that next line is indented deeper. Below a caption that is a clause the same holds, "
    "except that a first line starting with a digit (after indentation, markup or punctuation other than #: '1. Router.match chose "
    "mini', '2 nodes were sent back') is not carried over: only what it opens counts, or that line when it is only a value - "
    "what follows its value reads as a row's does: '1200', '1200 ms', '1200 ms for Start'. A heading line is a Markdown # heading, "
    "an HTML <h1>-<h6> line, a line wholly in ** __ * or _ that ends no sentence inside it ('**Never write started_at.**' is a "
    "sentence; quote marks or a bullet may come first), a line holding only the field in [ ] or [[ ]], or a line underlined by a "
    "line of = or of two or more - (what follows the underline counts). A label line is one where the field's clause runs to the line end "
    "and which - trailing whitespace (zero-width too), markup, HTML tags and a # comment after the separator that follows the "
    "field aside, or cut at a # comment between the field and its first separator (with none, anywhere after the field) - ends "
    "with : ： = or ＝ (also as an HTML entity), an opening { or [, approx. (appr. apx. ca. circa. abt. est.) or a YAML block "
    "indicator after a separator (| > |- >- |+ >+), or holds only the field (a heading mark, quote marks, a bullet, an "
    "ordered-list number or markup allowed), except a table row inside its table (see the caption line). A caption line is any "
    "other line naming it that is no table row (it holds no | and starts with no HTML table tag other than <caption>; a table's "
    "title row, whose one non-empty cell names the field, counts as that cell's text - a row of two cells or more only when it is "
    "the row just above a |---| row, or the first or the last row of its table: no row of the table directly above it (past "
    "<table>, <thead> or <tbody> lines) or directly below it; '| started_at | |' between other rows leaves the field empty and is "
    "no heading, label or caption, only (4) reads it) and that - trailing whitespace, markup, closing brackets and quotes, a "
    "footnote mark ([1], [^1]), HTML tags, &nbsp;, "
    "symbols and emoji (✅ 👍 ★ →), a trailing \\ (a Markdown hard break) and a code span holding no _ (`#41`) aside - does not end "
    "with 。．.!?！？；; (a complete sentence is no caption) or with an ellipsis (… ⋯). A caption is a clause when at least four words "
    "stand before the field on its line (words inside a closed bracket count) and no bracket opened before the field is still "
    "open at it (a word: a run between blanks holding a letter or digit other than CJK; three CJK characters count as two words): "
    "'The program asks each node to report started_at', '程序要求自报started_at'. "
    "What a line opens: a fenced code block, to the next line starting with the same fence or the end; a { or [, to its closing "
    "bracket or a blank line; a list or indented block - the lines that are indented or list items (a bullet: - * + • and a blank, "
    "or · ・ ● ○ ◦ ▪ ▫ ■ □ ◆ ◇ ► ▶ ▸ ▹ ‣ ⁃ → ⇒ ➤ ➢ ✓ ✔ ☑ ✗ ✘ ※ ★ ☆ ◎ or a circled number; an ordered-list number; a letter or roman "
    "numeral before . or ) and a blank, or a CJK numeral before 、 ． . ) ） or in brackets: a), i., 一、 or （一）), at most two blank "
    "lines in a row; below an indented or list-item line naming the field, the block ends at a line indented less than its first "
    "line when that first line is no deeper than the line naming the field, else at a line indented no deeper than the line naming "
    "the field - except an ordered-list number followed by words (1. 1) 1、 1） 1． (1) （1） [1], also inside ** * __ _ or after >); a "
    "table: lines holding |, lines starting with an HTML table tag, or lines split by commas, semicolons or tabs whose first line "
    "is a header line (each cell the field or - quotes, markup, blanks and a unit in brackets aside - nothing or a name of at most "
    "40 characters and three words without quotes or brackets); a run of key: value lines (a key of up to 80 characters not "
    "starting with a digit - or starting with up to three digits and a letter: 1号节点, 1st node - then : ： = or ＝; only a digit "
    "after it counts), definition-list lines (': Start 1200') and name-number rows ('Start 1200 ms', 'Start (1200 ms)', 'Start "
    "........ 1200 ms ok', 'Start,1200,wrote it', 'Router.match 1200 毫秒': a name of one or two words, or three when the value's "
    "whole part has two digits or more or a unit follows it ('Router match step 1200', not 'Router.match chose Opus 5.5'), a CJK "
    "run counting as one word - at most 40 characters, starting with a letter, without , ; ， ； 、 and ending no sentence, markup "
    "and HTML tags around it aside; then blanks, an arrow (-> => → ⇒), a dash (- – —), = ＝ : ： ~ ≈, ( [ （ ［, a comma (, ，) or "
    "leaders (.. … ··); the line's first digit; and after its value, up to the next , ; ， ； 、 / ／ | ｜ tab, opening bracket, dash "
    "between blanks, en or em dash or two blanks: a unit right after the value (ms s sec secs second seconds min mins minute "
    "minutes 毫秒 秒 分钟, glued or as the next word; 毫秒 秒 分钟 also with CJK text right after them) and then anything ('Start 1200 "
    "毫秒用于读取请求'), or else at most one word (sentence marks and markup aside), no run of five CJK characters ('共 2 个节点被退回' is "
    "prose) and not one word on a line that ends a sentence ('路由重试了 2 次。' and 'Router.match retried 2 times.' are prose; "
    "'Start 1200.', 'Start took 1200 ms.' and '路由 1200 毫秒。' are rows)). Also tied, to a line whose value is "
    "the field (\"metric\": \"elapsed_ms\", metric: elapsed_ms, - metric: elapsed_ms, metric = \"elapsed_ms\", with a key of up to "
    "80 characters, or an array element \"elapsed_ms\",): any digit on the other lines of the { or [ enclosing the field, up to "
    "its closing bracket or a blank line; outside one (not for an element), a digit on the lines of its YAML mapping - below it "
    "and, unless it is a list item, above it back to the list item it belongs to, the lines indented deeper or as deep holding "
    "key: value (in a key: value line only a digit after the key counts, in another line none in an ordered-list number followed "
    "by words), at most two blank lines in a row. (4) in a later row, in a column whose header names it: of a Markdown table (the "
    "header is the row just above the |---| row), or of lines split into as many cells as the header line by |, tabs, commas, "
    "semicolons or HTML cells (from each <td> or <th> tag on), at most two blank lines in a row between them - a CSV cell may be "
    "quoted and then hold the separator; a CSV/TSV header cell is the field itself (quotes, markup, a unit in brackets aside) and "
    "the other cells are free, but when a cell names a field among other words and the line is no header line (see (3)), only a "
    "cell starting with a digit counts; a line is split by the first of these separators that makes it a header line, else by the "
    "first that gives a column, which does not replace the header line whose row it is; (5) in a structured output: under a key "
    "that names it (at any depth, keys too); beside a string value that is the field (quotes, markup, a unit in brackets or a "
    "trailing : or = aside) - or, in a dict and in a list holding more than strings, a one-line caption naming it (see (3)), else "
    "a dict value whose one value is either, or a key that is such a caption (not the field alone) and holds nothing (None, '', [] "
    "or {}) - in the other values of its dict or list (the caption's own digits are text), except another value that is or "
    "names a field so: its digits are its own too ({'summary': 'Step 2 left started_at out', 'detail': 'Step 3 left ended_at "
    "out'}); in its column of a list of lists (the rows after the first row naming a field), of a list of lists beside a list of "
    "strings or of dicts naming it (a split table's "
    "header), also of the lists inside a dict beside that header or inside a dict row, and of the row strings (in a list, or the "
    "lines of a string) beside a one-line header string naming it, split as that string, or beside such a header list, split by | "
    "tab , or ; into as many cells; each key and string is checked as a text, a list of strings also joined by line breaks. The "
    "texts among user_messages, user_summary, the output and the answer are also read together, each once and in that order - "
    "the order a node shows them, its User Message above its Report; the answer only where it is not user_summary itself - as "
    "paragraphs of one text, by (1)-(4); a structured output is read on its own. Also refused: took, elapsed, 耗时 or 用时 "
    "followed by a number "
    "(unit optional), also at the end of a longer word (overtook 2), when the same text, or any key or string of the structured "
    "output, also holds an ISO date-time (2026-11-02T10:00, seconds optional); without one it is not caught here. Accepted: naming "
    "the field alone, with no digit tied to it - e.g. the clause 'The program asks each node to report started_at' followed on the "
    "next line by '1. Router.match chose mini' or by '2 nodes were sent back', then by one more line that does not continue that "
    "list - and a digit before "
    "the field, except on a line beside a line whose value is the field (see (3)). Spelled-out numbers (twelve hundred, 一千二百) are "
    "not caught here but are self-reports all the same.")
# the prose form (took 1200 ms with an ISO time in the same text): one optional ':' between two blank runs, so it is linear
_TIMING_PROSE_RE = re.compile(r"(耗时|用时|elapsed|took)\s*(?:[:：]\s*)?\d+(\.\d+)?\s*(ms|毫秒|秒|s|sec|seconds?|分钟|min)?", re.I)
_TIMING_PROSE_NUMBER_RE = re.compile(r"\s*(?:[:：]\s*)?\d+(?:\.\d+)?")   # its quote: the number, and a unit only as a whole word
_TIMING_PROSE_UNIT_RE = re.compile(r"\s*(?:ms|毫秒|秒|seconds?|secs?|s|minutes?|mins?|分钟)(?![A-Za-z])", re.I)
_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")                # an ISO date-time, with or without seconds

ENGINE_STEPS = {
    NODE_MATCH: [
        {"key": "step1", "mode": "natural_language", "text": "Read input_authority.user_message and input_authority.registry_snapshot. AIAP packages and AISP skills are peers, each listed with protocol, summary, tags and when_to_use; route to the single package whose domain fits the request, or \"no_match\" for a direct reply."},
        {"key": "step2", "mode": "natural_language", "text": "If more than one package's domain fits the request, submit a gate whose options are all fitting candidates (kind execute, intent = package name) plus one cancel option; do not choose for the user, but always fill gate.recommendation (the candidate you would pick), gate.advice (why, in the user's language, judged by what the request needs — depth or speed — never by entry length) and gate.explanation (what this choice decides and how the candidates differ). Never break the tie by which entry is longer, more specific or better worded: an AIAP package and an AISP skill of the same domain is a tie. When input_authority.previous_route names a package that is among the fitting candidates, list that candidate first with a label saying it continues the session's previous program and set gate.recommendation to its intent; the gate still opens and the human still chooses (a recommendation is never a choice). The cancel option means the user declines to run any program (the run ends ABANDONED); it is not a skip choice."},
        {"key": "step3", "mode": "natural_language", "text": "node-commit with route {package, rationale}; output = the package name or no_match; user_summary = one sentence in the user's language."},
    ],
    NODE_SETUP: [
        {"key": "step1", "mode": "natural_language", "text": "Read the program entry file at input_authority.program.entry_path. List outer_nodes_in_path: the ordered main-graph nodes this request will traverse, starting at the entry node, following graph edges, excluding end nodes."},
        {"key": "step2", "mode": "natural_language", "text": "node-commit with outer_nodes_in_path; output = the path joined by ' > '; do not execute any business step here."},
    ],
    NODE_SUMMARY: [
        {"key": "step1", "mode": "natural_language", "text": "Write semantics {intent, result_summary, functional_status, nodes_skipped, per_node[]} from input_authority.node_summaries; functional_status must agree with the per-node statuses."},
        {"key": "step2", "mode": "natural_language", "text": "node-commit; the tool writes the final answer once. Emit every terminal_delivery_refs line in returned order: node-info, final answer, EVIDENCE. Copy references verbatim on separate lines with a blank line between; do not paste block text or call next-node again."},
    ],
    NODE_DIRECT: [
        {"key": "step1", "mode": "natural_language", "text": "Answer the user directly in their language; user_summary is the full answer; output = direct_reply."},
        {"key": "step2", "mode": "natural_language", "text": "node-commit; emit every terminal_delivery_refs line in returned order: node-info, final answer, EVIDENCE. Copy references verbatim on separate lines with a blank line between; do not paste block text or call next-node again."},
    ],
}

ENGINE_STEPS[LEGACY_SUMMARY] = copy.deepcopy(ENGINE_STEPS[NODE_REPORT])
ENGINE_STEPS[NODE_REPORT] = ENGINE_STEPS[LEGACY_REPORT] = [
    {"key": "step1", "mode": "natural_language", "text": "Use the served execution facts and complete main-node results. Write the detailed execution report in user_summary under EXECUTION REPORT and fill the semantics accounting. The business answer is NOT written here: the next node `Engine.final-answer` delivers it (alpha.45)."},
    {"key": "step2", "mode": "natural_language", "text": "Commit once; the reply carries this node-info reference and the next_plan for `Engine.final-answer`. Emit the node-info reference verbatim, then continue with `Engine.final-answer` without another next-node call."},
]
ENGINE_STEPS[NODE_FINAL] = ENGINE_STEPS[LEGACY_FINAL] = [   # alpha.45 (doc 91): the answer node
    {"key": "step1", "mode": "natural_language", "text": "Deliver the self-contained whole-request synthesis under FINAL SYNTHESIS, with or without references. Keep all served required report_parts. Stream it between a line `:::answer Engine.final-answer` and a line `:::` and commit semantics.final_answer \"@host\" (inline on the fallback). No Report, no Explain, no User Message here: keep user_summary and output exactly as served."},
    {"key": "step2", "mode": "natural_language", "text": "Emit every terminal_delivery_refs line in returned order: final business answer, EVIDENCE. Copy references verbatim on separate lines with a blank line between; then stop."},
]


def _report_node(index):
    for entry in index['catalog']:
        if entry['name'] in REPORT_NODES:
            return entry['name']
    version = runtime_identity.revision_match(index.get('engine_version', ''))
    return LEGACY_SUMMARY if version and int(version[1]) < 39 else NODE_REPORT


def _answer_body(payload):
    """Count the synthesis alone, preserving its bytes and reference semantics."""
    if payload['node'] in ANSWER_NODES:
        semantics = payload.get('semantics') or {}
        text = semantics.get('final_answer')
        count = sum(not char.isspace() for char in text) if isinstance(text, str) else 0
        if not isinstance(text, str) or text.strip() == '@host' or count < FINAL_ANSWER_MIN_CHARS:
            raise EngineError('FINAL_ANSWER_REQUIRED', 'final needs a self-contained whole-request synthesis of at least 500 non-whitespace Unicode code points; references do not count',
                              field='semantics.final_answer', expected={'minimum': FINAL_ANSWER_MIN_CHARS, 'basis': 'non_whitespace_unicode_codepoints'},
                              example={'actual': count})
        return text
    return payload['user_summary']


def _compose_answer(payload, report_parts):
    """Business answer = the model's lead + the referenced reports verbatim (alpha.42 E1; same composition for validation and
    finalization). Each report keeps its own source-ID scope; no semantic merge or renumbering."""
    lead = _answer_body(payload)
    groups = {}
    for part in report_parts or []:
        if sha256_bytes(part['text'].encode('utf-8')) != part['text_sha256']:
            raise EngineError('REPORT_PART_INVALID', 'machine report snapshot digest changed')
        revision = f"> revision {part['revision']}\n\n" if part.get('historical_user_message') else ''
        text = part.get('execution_report_display', part['text']) if part['node'] == NODE_REPORT else part['text']
        key = (part['node'], part['visit'])
        note = (f"> Source status: {part['source_status']}"
                + ("; not completed" if not part.get('occurrence_completed') else '') + "\n\n"
                if key not in groups and part.get('source_status') else '')
        groups.setdefault(key, []).append(note + revision + text)
    if not groups:
        return lead
    # Group the display only; atomic revision/index identities remain in report_parts.
    blocks = [f"### {node} · {visit}\n\n" + "\n\n".join(texts) for (node, visit), texts in groups.items()]
    return (lead.rstrip("\n") + "\n\n" if lead.strip() else "") + "\n\n".join(blocks)

_GATE_FIELDS = "gate {question, options[{kind: execute|cancel, label, intent, aliases?}], closing, recommendation, advice, explanation}"
_GATE_SCOPE_RULE = _contracts.text("gate.scope")
_DECLARED_GATE_SCOPE = _contracts.text("gate.declared_scope")

_HELP = {
    "FINAL_ANSWER_REQUIRED": "Fill semantics.final_answer with a self-contained synthesis answering the original whole request: at least 500 non-whitespace Unicode code points, excluding references, disclosure and footer. Length is only a floor, not proof of quality; do not pad, duplicate reports or invent evidence. Keep every required report_parts item. Stream :::answer Engine.final-answer ... ::: and commit \"@host\", or submit inline. Fix only this payload; do not replay business work.",
    "REPORT_SEMANTICS_INVALID": "Engine.execute-report semantics must carry the accounting {intent, result_summary, functional_status, nodes_skipped, per_node} and nothing of the business answer (final_answer / report_parts / answer_details belong to `Engine.final-answer`).",
    "FINAL_SEMANTICS_INVALID": "final semantics carry only final_answer (plus optional report_parts and answer_details); the accounting stays at Engine.execute-report.",
    "FINAL_REFERENCE_REQUIRED": "The run already delivered reports the final answer must carry: add every item of `expected` to semantics.report_parts exactly as given ({ref, field, message_index?}; the full required list is in `example`, in this reply's input_authority.report_candidates.required and pre-filled in payload_skeleton.semantics.report_parts - start from the skeleton, alpha.80) and keep semantics.final_answer as the lead. Nothing is retyped: the engine appends the referenced reports verbatim (alpha.69). On a PASS answer you may instead leave report_parts out: the pre-filled list is taken (alpha.106).",
    "REPORT_PART_INVALID": "report_parts items are {ref, field, message_index?} - no node / index keys. ref must be a ref from the `Engine.final-answer` reply's input_authority.input_refs (or its short id <node>@<visit>, alpha.59): a ref is bound to its consumer and to the current digest, so a ref saved earlier under _work/ or minted for another node fails as INPUT_REF_INVALID. Take the ref from this reply and resubmit (alpha.55).",
    "REPORT_SEMANTICS_INCONSISTENT": "semantics.functional_status must agree with the per-node statuses the engine holds: it cannot be PASS while a node of this run is DEGRADED or FAILED - write DEGRADED (a node ran with limits), PARTIAL (a failed node was handled / skipped) or FAIL; the accounting states what happened, it is not a judgement of the answer's usefulness (alpha.54). In the same resubmission repair every Report sentence listed in example.dependent_report_statements and the dependent semantics.result_summary / explain text (re-stream :::report Engine.execute-report when user_summary is \"@host\"); example.node_states counts main, sub and engine occurrences separately (alpha.79).",
    "REPORT_SEMANTICS_INCOMPLETE": "The execution report covers the whole run since the user's request - every turn, also the nodes committed before a human reply - not only the turn you are in. semantics.per_node must hold one {node, material_action, result} entry for every main node this run committed (`example` is the complete list, pre-filled in payload_skeleton.semantics.per_node); a main node may be left out only by naming it in semantics.nodes_skipped. Add the entries named in `expected` and make the Report text cover them too (alpha.83).",
    "FINAL_LEAD_POINTER": "semantics.final_answer points at the referenced reports instead of answering (the phrase in `example`) and carries neither a heading nor a table. The synthesis must answer the whole request and pass its independent 500-character floor; references are not its substitute. Rewrite it and resubmit with the same report_parts. This pointer-shape repair is asked once; a second submission is recorded without bypassing the length floor.",
    "REPORT_FACTS_INCONSISTENT": "The Report states a whole-run status or an all-PASS node count the accepted node records contradict. Every such sentence is in `expected` ({found, expected}); rewrite each one so it agrees with example.node_states and example.functional_status - main, sub and engine occurrences are counted separately - and keep the rest. Re-stream :::report Engine.execute-report when user_summary is \"@host\" (the earlier stream is history and is never edited); write no rejected/error numbers, the machine table carries them (alpha.79).",
    "REPORT_NOT_RECEIVED": "No bound streamed Report was available at commit; this code alone does not identify the cause. If you did not stream it, submit the complete Report inline, not @host. If you did stream it but capture is absent, resubmit inline without replaying business work. For subsequent nodes stream first or submit complete inline text directly; never use @host for unstreamed text.",
    "HOST_TEXT_NOT_RECEIVED": "Stream the text first: a line ':::<kind> <node id>' (kind = message | explain | answer | gate), the text, a line ':::' - then commit with the \"@host\" marker in that field (user_messages [\"@host\"], explain \"@host\", semantics.final_answer \"@host\", gate.question \"@host\" with the gate text in the menu layout). If the host cannot deliver it, resubmit this node with the full text inline and keep streaming the following nodes.",
    "RUN_STATE_FORBIDS_COMMIT": "The run is not accepting commits. WAITING_USER: the host must answer the gate first (gate-answer). Terminal: only report.",
    "NODE_MISMATCH": "Commit the node named in the latest next-node reply (node.name, exactly; sub-graph nodes carry a qualified id such as Parent/ns.Node); nodes cannot be skipped, replayed or committed out of order.",
    "JSON_INVALID": "Payload must be strict JSON: no duplicate keys, no NaN/Infinity, no trailing text (a leading UTF-8 BOM is stripped). Windows paths: use forward slashes (D:/dir/file) or escape every backslash as \\\\; a bare \\ before a letter is an invalid escape.",
    "SCHEMA_INVALID": "Fix only the named field; see expected/example. The next-node reply's payload_skeleton / payload_rules already say what this node accepts; the full schema is schemas/commit.v1.json. Start from payload_skeleton and keep every key it has (a PASS commit without a gate may leave out steps if all were done, and semantics.report_parts; alpha.106) - never build the payload from scratch; an object such as gate accepts only the keys the skeleton and rules name (further reasoning goes into gate.advice / gate.explanation, not into new keys) (alpha.68).",
    "MACHINE_FIELD_REJECTED": "Remove the machine-owned field(s); the tool computes coordinates, timings, hashes and accounting.",
    "STEPS_NOT_CLOSED": "steps.done + steps.remaining + steps.not_applicable must be exactly the served step keys; status PASS requires remaining = []. A not_applicable entry is the step key or {\"step\": \"<key>\", \"reason\": \"<why>\"} - the reason is kept in the record (docs/05SoulRun 87).",
    "GATE_ALREADY_ANSWERED": "Consume the existing gate_answer. A different material question may open a new gate; never repeat the answered menu.",
    "DEGRADED_REASON_REQUIRED": "status DEGRADED needs a non-null degraded_reason.",
    "ARTIFACT_MISSING": "Every evidence.artifacts.path must exist on disk (absolute path preferred); a self-reported sha256 must match.",
    "SELF_MODIFY_FORBIDDEN": "Governance files of the running program are read-only at runtime (AIAP Appendix D). Use target_aiap_dir for generator outputs.",
    "PERMISSION_VIOLATION": "A tool call or sys.* step is outside the program's declared permissions (AIAP §17). Do not perform it; put the step in not_applicable and commit DEGRADED with the reason.",
    "EVIDENCE_MISSING_FOR_SYS_STEP": "Each done sys.* step needs one evidence.tool_calls entry with step=<key> (or sys_call=<name>).",
    "ASSERTION_RESULT_MISMATCH": "Each done sys.assert step needs evidence.sys_assert_results[{step, expression, context_snapshot, result}] and the engine must reach the same result.",
    "UNTRUSTED_TIMING_CLAIM": "Do not invent or self-report execution timings (started_at/ended_at/elapsed_ms/active_elapsed_ms/human_wait_ms/committed_at); the engine measures them. Source-observed data times such as as_of/retrieved_at may be copied with provenance; never invent missing times. Engine execution measurements appear in the Audit line and Engine.execute-report accounting. What exactly is refused and accepted: this refusal's errors[0].expected.",
    "NEXT_HINT_INVALID": "topology.next_candidates plus branch targets has more than one entry: set next_hint to exactly one of them.",
    "GATE_REQUIRED": "This node has a human gate: submit " + _GATE_FIELDS + "; for advisory/conditional gates you may instead give gate_not_triggered_reason.",
    "USER_MESSAGE_REQUIRED": "This node gives the user something (user_message.has is true, or the program says to show / present / output it): put it in user_messages - generated content in full, quoted program texts verbatim - inline or as the existing :::message stream, not only in the Report, output or a _work file; then resubmit. A question instead needs a gate. (alpha.93; formerly NODE_MESSAGE_REQUIRED)",
    "USER_MESSAGE_DECISION_MISSING": "Every business / sub node commit declares user_message: {\"has\": true, \"items\": [{\"step\": \"step1\", \"kind\": \"content\", \"what\": \"...\"}, {\"step\": \"step3\", \"kind\": \"literal\", \"text\": \"<the program's quoted text, verbatim, placeholders filled>\"}], \"not_applicable\": [{\"step\": \"...\", \"reason\": \"<why its condition did not occur>\"}], \"none_reason\": null} when the program gives the user anything (user_messages then carries it), or {\"has\": false, \"items\": [], \"not_applicable\": [], \"none_reason\": \"<why this node's program gives the user nothing>\"}. An empty none_reason is recorded as n/a. The reply's user_message_hints list candidates from the program text (alpha.93).",
    "USER_MESSAGE_DECISION_INCONSISTENT": "user_message.has is false but user_messages carries text: declare has true and list the items (alpha.93).",
    "USER_MESSAGE_STEP_UNKNOWN": "user_message items / not_applicable name this node's own step keys (the reply's steps[].key) (alpha.93).",
    "USER_MESSAGE_STEP_NOT_DONE": "A user_message item names the step that produced its text, and that step must be in this commit's steps.done: a text the user gets cannot come from a step listed as remaining or not_applicable. Fix the item's step, or move the step to done if it was executed (alpha.95).",
    "USER_MESSAGE_LITERAL_UNKNOWN": "A literal item is a text this node's program quotes for the user ('...', \u300c...\u300d, \u201c...\u201d) copied verbatim with its placeholders filled; this text is not one of them. Your own generated text is kind content. A literal item carries the program's text itself in text; a description goes in what (alpha.93). Or leave text out: the engine then finds the step's program text in user_messages itself (alpha.98).",
    "GATE_QUESTION_AS_MESSAGE": "The gate of this node was answered in this occurrence. Its question - the program's request for a human reply - is not a User Message: remove it from user_messages and the Report text, declare has false with a none_reason if nothing else remains, and never open another gate for the same question (alpha.98). A genuinely new question still needs its own gate.",
    "ROUTE_CHOICE_CONFLICT": "route.package must be the program bound to the human's accepted Router choice. Do not substitute another candidate or no_match; retain the original answer and submit only the authorized route.",
    "USER_MESSAGE_LITERAL_MISSING": "The declared program text must appear verbatim in user_messages (only runs of whitespace are normalised): copy it exactly - no rewording, no shortening, no characters added inside it (alpha.93). Markdown marks count as characters (alpha.96) except paired backticks and ** bold, which are set aside when comparing (alpha.98): list markers, words, numbers and punctuation still count. A Windows path in JSON needs each backslash written as \\\\ (or /), else \\n becomes a line break. Leaving text out avoids the copy: the engine finds the step's program text in user_messages (alpha.98).",
    "GATE_SHAPE_INVALID": "Submit " + _GATE_FIELDS + ". Intents, labels and aliases must be unique, with at least one execute option; recommendation is a required exact option intent, never a choice. Advice and explanation must be nonempty.",
    "GATE_CANCEL_INTENT_INVALID": "kind=cancel needs intent=cancel and means the human refuses this gate as a whole: the business work stops and Engine.execute-report / Engine.final-answer follow. A choice that declines one optional step (\"do not export\", \"skip\", \"不保存\") is kind=execute with an intent naming that skip path (e.g. skip_export); a cancel option whose label reads as such a skip is rejected (alpha.88).",
    "ROUTE_INVALID": "route.package must be one of input_authority.registry_snapshot[].package or \"no_match\".",
    "REGISTRY_INVALID": "The agent registry (aiap/aiap_list.py, aisp/aisp_list.py) could not be collected; routing halts until it passes --check or --json.",
    "EVIDENCE_STDOUT_MISSING": "A tool_calls entry that ran a process (sys.run*, python_tool_run, bash / shell, a *.py script ...) must name stdout_path: the file under <cache_dir>/_proc/ into which the process stdout was redirected (e.g. `cmd > <cache_dir>/_proc/<node>.<n>.out`), plus exit_code (or a <same stem>.exit file holding it). The engine hashes that file itself; self-reported hashes are not evidence.",
    "EVIDENCE_STDOUT_MISMATCH": "The stdout_sha256 or exit_code you reported differs from the captured file under _proc/ (or its .exit file). Report only what the file holds, or omit them and let the engine fill them.",
    "CONTINUATION_EVIDENCE_CHANGED": "The accepted occurrence cache no longer matches its index digest. Preserve the files; do not re-run or rewrite prior evidence to repair it.",
    "SOURCE_URL_INVALID": "evidence.sources[].url must be an absolute http(s) URL with a host; a tool-produced source still names the page it came from.",
    "SOURCE_SUPPORT_INVALID": source_support.RULE + " " + source_support.REPAIR_RULE + " " + source_support.LOCATOR_HELP,   # alpha.98 (doc 236)
    "EVIDENCE_SNAPSHOT_INVALID": "stdout_snapshot is machine-owned. Do not submit it or overwrite _proc/sha256-*.out. Keep each original capture; a damaged historical snapshot cannot be repaired by changing its digest.",
    "PATH_INVALID": "outer_nodes_in_path must be main-graph node names in graph order (each consecutive pair joined by an edge), without end nodes or duplicates.",
    "SUBSTEPS_INCOMPLETE": "This module node's sub-graph is still open: commit the sub node named by next-node; the module node itself is served again once the sub-graph reaches its end node.",
    "UNSUPPORTED_RESERVED_KEY": "map / join / context_filter are not supported in the alpha series (doc 02 D6).",
    "PROGRAM_INVALID": "The routed program failed structural load checks; see errors.",
    "GATE_MISMATCH": "question_id must be the active gate's id (see the index gate group).",
    "TICKET_NOT_READY": "The gate ticket was already consumed or retired.",
    "DISPATCH_REQUIRED": "This node runs in a sub-agent (execute_mode agent, loading_mode node). Spawn one sub-agent with the host's Agent tool, prompt = dispatch.bootstrap verbatim (it names agent_engine.aisop.json), wait for it, then call next-node again. Do not do the node's steps yourself.",
    "DISPATCH_TICKET_STALE": "The ticket was superseded or already closed; a sub-agent holding a stale ticket must stop and return the rejection as its final text.",
    "DISPATCH_TICKET_INVALID": "The ticket does not belong to the current node occurrence, or it was not claimed with next-node --agent-ticket first.",
    "DISPATCH_RETURN_QUERY_PENDING": "The run was interrupted while a resumed sub-agent held this part's ticket. Nothing was committed and the run is not paused; a node-commit payload is kept (pending_payload_refs). A sub-agent must stop now and return this rejection as its final text, without resubmitting. The main agent calls next-node: it offers the one bounded return query first, then the human decides.",
    "SPAWN_NOT_ATTEMPTED": "Use dispatch.evidence_required: reason plus exhaustion_ticket for machine quota exhaustion; reason plus spawn_failure_evidence for actual Agent failure. Never invent a tool error.",
    "REF_TARGET_INVALID": "An address inside output is {\"@ref\": \"proc:<stdout_path>[#path]\"} (a captured stdout named in THIS payload's tool_calls), {\"@ref\": \"input:<node>@<visit>[#field.path]\"} (a committed occurrence of this run, as listed in input_authority.input_refs; field = output | vars | user_summary | user_messages), {\"@ref\": \"artifact:<n>[#path]\"} (THIS payload's evidence.artifacts[n], a file) {\"@ref\": \"host:report\" | \"host:message[<n>]\" | \"host:explain\"} (this node's own streamed Report / User Message / Explain, no #path) {\"@ref\": \"work:<file>[#path]\"} (a file under this run's _work/, alpha.63) or {\"@ref\": \"evidence:sources\"} (the run's evidence ledger - every source recorded so far, alpha.64). evidence.sources may be one address artifact:<n>[#path] | proc:<stdout_path>[#path] selecting a list of source objects. output itself is never an address, the target must exist and a #path must resolve. #path starts at the real JSON root: #items[0].name, not #json.items[0].name unless json is an actual key. All independent invalid output references are reported together; correct every errors[] field before retrying. Fix the address or inline the value; an address never shortens what a program step requires on disk. host:message[<n>] counts this node's streamed message fences, not the User Message items: with one fence only host:message[0] exists and the items are parts of it (alpha.96).",
    "OUTPUT_SCHEMA_INVALID": "This program declares output_strict for the node: output must match payload_schema.output of the reply (declared keys and types; a declared value may be an address {\"@ref\": ...}; keys typed with null may be omitted). Fix only the named field.",
    "HOST_TEXT_UNAVAILABLE_SUBAGENT": "A sub-agent's visible stream is not captured by the host, so \"@host\" markers cannot be resolved there: put the Report in user_summary, the User Message items in user_messages, the Explain in explain and a gate's question / explanation / advice / closing in the gate fields, each in full inline; never stream `:::` fences from a sub-agent (alpha.62).",
    "HSAW_ITEM_INVALID": "hsaw_items[] items carry exactly the documented fields (node_commit.py --hsaw-help): category doubt|problem|bug, severity critical|medium|low, classification_uncertain, escalated_from, impact_classes, disposition FREEZE_NOW|HARD_FAIL|ADVISE|REPORT, title, description, evidence_refs (addresses of THIS run: proc:_proc/<file> | input:<node>@<visit>[#path] | artifact:<n> | work:<file> | host:report | host:message[n] | host:explain | evidence:sources - a program file or a step name is not an address, alpha.89), reversible, classification_rationale, recommendation (or \"none\"); a bug item also carries scope, affected_files, touches_sovereignty_toolset, affects_sovereignty_markers, proposed_fix. The execution report and the answer node accept no items. Fix only the named field (alpha.87).",
    "HSAW_FIELD_REJECTED": "id, fingerprint, occurrence, status, seq, prev_sha, sha, recorded_at, authorization and gate_question_id are engine-owned: remove them; the engine records identities and the register itself (alpha.87).",
    "HSAW_SEVERITY_INCONSISTENT": "The item's own facts fix a floor for its severity: category doubt, reversible=false, an authorization / sovereignty / audit / safety impact or a sovereignty tool / marker impact are critical; low allows only documentation / naming / cosmetic impacts; classification_uncertain=true means you already went one level up (escalated_from names the level below). Raise the severity (or correct the fact you misrecorded); never lower it (alpha.87).",
    "HSAW_DISPOSITION_INCONSISTENT": "critical = FREEZE_NOW (this commit carries the gate) or HARD_FAIL (status FAIL, no error route) - never record-and-continue; medium = ADVISE with a concrete recommendation (advise, do not ask); low = REPORT (alpha.87).",
    "HSAW_GATE_REQUIRED": "A FREEZE_NOW item stops execution here: the same commit must carry the hsaw_doubt gate - gate {question, options[{kind, label, intent, note}], closing, recommendation | \"none\", advice, explanation, resume_boundary} - and the payload stays PARTIAL with the unfinished steps in steps.remaining (alpha.87).",
    "HSAW_GATE_INCOMPLETE": "An hsaw_doubt gate needs its five parts: the findings with evidence (the items), gate.resume_boundary (why it stops here, where it continues after the answer), every option with its consequence in note plus at least one execute and one cancel option, a recommendation (an option intent, or \"none\" with advice saying why there is no reliable one); a bug gate also offers the intents authorize_fix and not_a_defect. The engine appends its own closing sentence (alpha.87).",
    "HSAW_ITEM_REQUIRED": "This node declares no gate, so a question of your own is an HSAW doubt gate: add one FREEZE_NOW hsaw_items entry (category doubt / problem / bug) beside the gate, or - if the program already says what to do - do it without asking (alpha.87).",
    "HSAW_HARD_FAIL_STATUS": "A HARD_FAIL item means no safe resume boundary exists: the commit is status FAIL without error_type (no program error route) and without a gate; the engine ends the run and reports it. If a safe choice exists, use FREEZE_NOW with a gate instead (alpha.87).",
    "HSAW_REGISTER_INTEGRITY": "index.hsaw_register is engine-written and hash-chained; its chain no longer verifies, so the run was terminated. Report this verbatim: it is tamper evidence, not a payload problem (alpha.87).",
    "INDEX_PROJECTION_INVALID": "The engine refused to record this gate because the index transition would not validate; nothing was written. Report the message verbatim: this is an engine defect, not a payload problem.",
}
_EXAMPLES = {
    "steps": {"done": ["step1"], "remaining": [], "not_applicable": []},
    "evidence": {"tool_calls": [], "artifacts": [], "sources": []},
    "gate": {"question": "…?", "options": [{"kind": "execute", "label": "A", "intent": "a"}, {"kind": "execute", "label": "跳过 B", "intent": "skip_b"},
                                          {"kind": "cancel", "label": "取消", "intent": "cancel"}], "closing": "沉默不构成授权。",
             "recommendation": "a", "advice": "建议选 A：…（建议不是选择，决定权在您）", "explanation": "这道门决定 …；A、跳过 B 与取消的差别是 …"},   # alpha.28 GA; alpha.88 (doc 196 F3): a skip is an execute option
    "route": {"package": "soulbot_yijing_divination_aiap", "rationale": "…"},
    "outer_nodes_in_path": ["Start", "NLU", "CastHexagram"],
    "semantics": {"intent": "…", "result_summary": "…", "functional_status": "PASS", "nodes_skipped": [], "per_node": []},
    "dispatch_fallback": {"reason": "Agent tool unavailable in this host", "spawn_failure_evidence": "<tool error text verbatim>"},
    "hsaw_item": hsaw_gate.EXAMPLE_ITEM,   # alpha.87 (doc 193)
    "user_message": {"has": True, "items": [{"step": "step1", "kind": "content", "what": "the advice for the user"},   # alpha.93 (doc 218)
                                           {"step": "step3", "kind": "literal", "text": "<the program's quoted text, verbatim>"}],
                     "not_applicable": [], "none_reason": None},
}


# doc 16 B-4: examples for the item shapes that are rejected most often; looked up by the error's field path.
_ITEM_EXAMPLES = {
    "evidence.tool_calls": {"tool": "Bash", "purpose": "run tool_dirs/cast_hexagram.py", "step": "step2"},
    "evidence.artifacts": {"path": "D:/dir/out.json", "kind": "file"},
    "evidence.sources": {"url": "https://example.org/page", "retrieved_at": "2026-09-07T12:00:00Z", "title": "…"},
    "evidence.sys_assert_results": {"step": "step1", "expression": "…", "context_snapshot": {}, "result": True},
    "semantics.per_node": {"node": "Start", "material_action": "…", "result": "…"},
    "gate.options": {"kind": "execute", "label": "A", "intent": "a"},
    "steps.not_applicable": {"step": "step3", "reason": "<why this step did not apply>"},   # docs/05SoulRun 87: or the bare step key
    "hsaw_items": hsaw_gate.EXAMPLE_ITEM,   # alpha.90 (doc 202 B; production cache/61: ~43 rejections for guessed field names)
}


def _example_for(field: str, head: str):
    """The example for a rejected field: the item shape when the path points into a known array, else the top-level example."""
    for prefix, example in _ITEM_EXAMPLES.items():
        if field == prefix or field.startswith(prefix + "[") or field.startswith(prefix + "."):
            return example
    return _EXAMPLES.get(head)


class EngineError(Exception):
    """A rejection (node-commit / gate-answer) or a fatal engine condition; carries error-is-help fields."""

    def __init__(self, code: str, message: str, field: str | None = None, expected=None, example=None, errors: list | None = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.field, self.expected, self.example = code, message, field, expected, example
        self.errors = errors or []

    def as_dict(self) -> dict:
        return {"code": self.code, "field": self.field, "expected": self.expected, "example": self.example, "message": self.message}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_commit_schema_cache: dict | None = None


def commit_schema() -> dict:
    global _commit_schema_cache
    if _commit_schema_cache is None:
        _commit_schema_cache = strict_loads((SCHEMA_DIR / "commit.v1.json").read_text(encoding="utf-8"))
    return _commit_schema_cache


def _parse_ts(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None


def _ms_between(start: str | None, end: str | None) -> int | None:
    a, b = _parse_ts(start), _parse_ts(end)
    if a is None or b is None:
        return None
    return max(0, int((b - a).total_seconds() * 1000))


def _active_elapsed_ms(node: dict, end: str) -> int:
    """Deduct the union of recovery intervals inside this occurrence's measured window."""
    elapsed = _ms_between(node.get("ready_at"), end) or 0
    intervals = node.get("transport_wait_intervals")
    if intervals is None:  # Historical caches have totals only; never invent their interval anchors.
        transport = node.get("transport_wait_ms") or 0
    else:
        transport = node.get("transport_wait_legacy_ms") or 0
        start, finish = _parse_ts(node.get("ready_at")), _parse_ts(end)
        if start and finish and finish > start:
            clipped = sorted((max(start, _parse_ts(i["started_at"])), min(finish, _parse_ts(i["ended_at"]))) for i in intervals)
            cursor = start
            for left, right in clipped:
                left = max(left, cursor)
                if right > left:
                    transport += int((right - left).total_seconds() * 1000)
                    cursor = right
    return max(0, elapsed - (node.get("human_wait_ms") or 0) - transport)


def _node_key(name: str, visit: int) -> str:
    return name if visit <= 1 else f"{name}@v{visit}"


def _visible_total(index: dict) -> int:
    """alpha.45: the `Engine.final-answer` answer node has no PLAN / node block, so the [n/N] positions the human sees do not count it."""
    return sum(1 for e in index["catalog"] if e["name"] not in ANSWER_NODES)


def _catalog_entry(index: dict, name: str) -> dict | None:
    entry=next((e for e in index['catalog'] if e['name']==name),None) or index.get('catalog_history',{}).get(name)
    if not entry and any(k.partition('@')[0]==name and s.get('cache_sha256') for k,s in index.get('nodes',{}).items()):
        raise EngineError('CATALOG_HISTORY_MISSING',f'Accepted node definition is missing: {name}; preserve evidence and stop.')
    return entry


def _track_path(index: dict, entry: dict) -> str:
    """alpha.84: "4" for the fourth main node, "4.2" for its second sub node, "4.2.1" inside a nested module."""
    if not entry or not any(e['name']==entry['name'] for e in index['catalog']):
        raise EngineError('HISTORY_POSITION_UNAVAILABLE','History is a source, not an active plan coordinate; read the original block position.')
    if not entry.get("parent"):
        mains = [e["name"] for e in index["catalog"] if e["kind"] != "engine" and not e.get("parent")]
        return str(mains.index(entry["name"]) + 1)
    siblings = [e["name"] for e in index["catalog"] if e.get("parent") == entry["parent"]]
    parent = _catalog_entry(index, entry["parent"])
    return (_track_path(index, parent) + "." if parent else "") + str(siblings.index(entry["name"]) + 1)


def _track_position(index: dict, entry: dict | None, visit: int) -> dict:
    """alpha.84 (doc 176; one run showed [3/9] on the blocks, [2/10] on the Web bar, "10 nodes" in EVIDENCE and "九个主节点" in the
    model's report - six main nodes): the position a human and the model see. Three tracks that never share a count:
      main    "3/8"     the third main node of the eight planned so far (the total moves only when the program re-plans a branch)
      sub     "4.2"     the second sub node of main node 4; no total - a module's route is decided node by node
      engine  "engine"  Router.* / final carry no number and are in no total
    `ordinal` is the 1-based catalog position: it names the _public files (plan.07.*), it is not a human count."""
    if entry is None or entry["kind"] == "engine":
        return {"track": "engine", "n": None, "total": None, "label": "engine", "ordinal": (entry["ordinal"] + 1) if entry else 0, "visit": visit}
    path = _track_path(index, entry)
    if entry.get("parent"):
        return {"track": "sub", "n": int(path.rpartition(".")[2]), "total": None, "label": path, "ordinal": entry["ordinal"] + 1, "visit": visit}
    total = sum(1 for e in index["catalog"] if e["kind"] != "engine" and not e.get("parent"))
    return {"track": "main", "n": int(path), "total": total, "label": f"{path}/{total}", "ordinal": entry["ordinal"] + 1, "visit": visit}


def _track_counts(index: dict) -> dict:
    """Committed occurrences by definition-file role, without changing cache paths or coordinates."""
    counts = {"main": 0, "sub": 0, "engine": 0}
    for done in index["completed"]:
        entry = _catalog_entry(index, done["name"])
        if entry:
            counts["engine" if entry["kind"] == "engine" else "main" if dispatch_scope.is_main(index, entry) else "sub"] += 1
    return counts


# --- sub-node tree helpers (doc 05 §4) ------------------------------------------------------------

HOST_REPORT_WAIT_S = float(os.environ.get("SOULBOT_HOST_REPORT_WAIT_S", "5"))   # alpha.30 A5; alpha.31: 5 s (a miss costs little, the model resubmits inline)
HOST_TEXT_FRESH_SLACK_S = 2.0   # alpha.68 (doc 145 E2): a host text older than the occurrence's ready_at by more than this is an earlier occurrence's file
HOST_FENCES = ("report", "message", "explain", "answer", "gate")   # alpha.44 / alpha.45: the texts a host may hand over from the visible stream (doc 84, 88)
HOST_FIELDS = {"report": "user_summary", "message": "user_messages", "explain": "explain", "answer": "semantics.final_answer", "gate": "gate.question"}


def recovery_diagnostic_summary(cache_dir, index=None):
    from . import recovery_counts
    return recovery_counts.project(cache_dir, index)


def host_text_name(kind: str, node_id: str) -> str:
    """alpha.30 A5 / alpha.44: the file the host writes with a node's streamed text (`:::<kind> <node>` … `:::`); the host applies
    the same rule (last id segment, unsafe characters replaced, 100 characters at most)."""
    local = re.sub(r"[^A-Za-z0-9_.\-]", "_", node_id.rsplit("/", 1)[-1])[:100]
    return f"_host_{kind}.{local}.txt"


def host_report_name(node_id: str) -> str:
    return host_text_name("report", node_id)


def _has_host_marker(messages) -> bool:
    """alpha.95 (doc 224, cache 48): a user_messages list carries the host marker when any entry is "@host" - the model wrote
    ["@host", "@host"] and ["@host", "<an item inline>"], and the literal string was archived as a message."""
    return isinstance(messages, list) and any(m == "@host" for m in messages)


def _host_markers(payload: dict) -> list[str]:
    """alpha.44: which payload fields carry the "@host" marker, in HOST_FENCES order."""
    kinds = []
    if payload.get("user_summary") == "@host":
        kinds.append("report")
    if _has_host_marker(payload.get("user_messages")):   # alpha.95 (doc 224): any "@host" entry, not only the exact list
        kinds.append("message")
    if payload.get("explain") == "@host":
        kinds.append("explain")
    semantics = payload.get("semantics")
    if isinstance(semantics, dict) and semantics.get("final_answer") == "@host":
        kinds.append("answer")
    gate = payload.get("gate")
    if isinstance(gate, dict) and gate.get("question") == "@host":   # alpha.45: the gate text streamed in the menu layout
        kinds.append("gate")
    return kinds


_GATE_REC_MARK = re.compile(r"[（(]\s*(?:建议|推荐|recommended|推奨|추천)\s*[)）]|\[\s*recommended\s*\]", re.I)
_GATE_OPTION_LINE = re.compile(r"^\s*[*_]*(\d+)[.、)．]\s*(.+?)\s*$")
# alpha.51 (doc 108): the options may be a Markdown table row `| N | label | sentences |`; header / separator rows are skipped
_GATE_TABLE_ROW = re.compile(r"^\s*\|\s*[*_]*(\d+)[.、)．]?[*_]*\s*\|\s*(.*?)\s*\|(?:\s*(.*?)\s*\|)?\s*$")
_GATE_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_GATE_LABEL_LINE = re.compile(r"^\s*[*_]*[·•]\s*[*_]*([^:：*_]+?)[*_]*\s*[:：]\s*(.*)$")


def _gate_plain(text: str) -> str:
    """alpha.51 / alpha.53 (doc 113): a label as compared - without `*` / backticks, without `_` used as emphasis around a word (a
    word-internal underscore stays: soulbot_yijing_divination_aiap), without the （建议）/ (recommended) mark; the shown text keeps them."""
    plain = re.sub(r"[*`]+", "", _GATE_REC_MARK.sub("", text or ""))
    plain = re.sub(r"(?:(?<=\s)|^)_+(?=\S)|(?<=\S)_+(?=\s|$)", "", plain)
    return re.sub(r"\s+", " ", plain).strip()


def _gate_key(text: str) -> str:
    """alpha.59 (doc 127 §5 #1; production cache/93): the comparison key of a label - _gate_plain without any whitespace, so
    「风雷益 →山地剥」 and 「风雷益→山地剥」 are the same option; the shown text keeps its spacing."""
    return re.sub(r"\s+", "", _gate_plain(text))


def _split_gate_text(text: str, node: str, gate: dict | None = None, language=None, notes: list | None = None) -> dict:
    """alpha.45 (doc 88) / alpha.50 (doc 104 / 106): the streamed gate text in the menu layout - the question paragraph, a
    `· <explanation label>: …` line, a `· <advice label>: …` line, the options - a Markdown table `| N | label | sentences |` (alpha.51,
    doc 108) or numbered lines (`1. <label>` + sentences), the recommended one marked （建议）/ (recommended) - and one closing `· …`
    line - split back into the prose fields plus options_text = [{label, note, recommended}] (labels in any UI language, compared
    without Markdown emphasis; the text itself is written like a Report and rendered as Markdown)."""
    exp_labels = {v["explanation"] for v in render.GATE_LABELS.values()}
    adv_labels = {v["advice"] for v in render.GATE_LABELS.values()}
    question, explanation, advice, closing = [], [], [], None
    options: list[dict] = []
    bucket = question
    for line in text.strip("\n").split("\n"):
        s = line.rstrip()
        m = _GATE_LABEL_LINE.match(s)   # alpha.51: `**· 说明:** …` / `· **说明**: …` count as the label line
        label = m.group(1).strip() if m else None
        if label in exp_labels:
            bucket = explanation
            bucket.append(re.sub(r"^[*_]+\s*", "", m.group(2)))
            continue
        if label in adv_labels:
            bucket = advice
            bucket.append(re.sub(r"^[*_]+\s*", "", m.group(2)))
            continue
        tm = _GATE_TABLE_ROW.match(s) if bucket is not question else None
        if tm:   # alpha.51 (doc 108): a table row is one option; its third cell is the option's sentences
            raw_label = tm.group(2)
            recommended = bool(_GATE_REC_MARK.search(raw_label))
            options.append({"label": _gate_plain(raw_label), "raw": raw_label.strip(), "note": [tm.group(3).strip()] if tm.group(3) else [], "recommended": recommended})
            bucket = options[-1]["note"]
            continue
        if bucket is not question and _GATE_TABLE_LINE.match(s):   # the table's header / separator rows carry no text
            continue
        om = _GATE_OPTION_LINE.match(s)
        if om and bucket is not question:   # option lines follow the explanation / advice, never the question paragraph
            raw_label = om.group(2)
            recommended = bool(_GATE_REC_MARK.search(raw_label))
            options.append({"label": _gate_plain(raw_label), "raw": raw_label.strip(), "note": [], "recommended": recommended})
            bucket = options[-1]["note"]
            continue
        if re.match(r"^\s*[*_]*[·•]", s) and bucket is not question and (advice or options):
            closing = re.sub(r"^\s*[*_]*[·•]\s*", "", s).strip()
            bucket = None
            continue
        if bucket is not None:
            bucket.append(s)
    parts = {"question": "\n".join(question).strip(), "explanation": "\n".join(explanation).strip(),
             "advice": "\n".join(advice).strip(), "closing": (closing or "").strip()}
    missing = [k for k, v in parts.items() if not v]
    if missing and gate is not None:   # alpha.99 (doc 239 G6): the missing parts are composed from the gate's options, recorded
        composed = _compose_gate_text({k: v for k, v in gate.items() if k not in missing}, node, language)
        parts.update({k: composed[k] for k in missing})
        if notes is not None:
            notes.append({"code": "GATE_TEXT_COMPOSED", "text": f"the streamed gate text of {node!r} lacked {missing}; composed from the gate's options (alpha.99)"})
        missing = []
    if missing:
        raise EngineError("HOST_TEXT_NOT_RECEIVED", f"the streamed gate text of node {node!r} lacks {missing}", field="gate.question",
                          expected="the question paragraph, then `· <explanation label>: …`, `· <advice label>: …`, the options as a Markdown table "
                                   "`| 编号 | 选项 | 说明 |` (or numbered lines `1. <label>` + two or three sentences each) and one closing `· …` line, "
                                   "between ':::gate <node>' and ':::' - or the gate fields inline")
    parts["options_text"] = [{"label": o["label"], "raw": o["raw"], "note": "\n".join(o["note"]).strip(), "recommended": o["recommended"]} for o in options]
    return parts


def _apply_gate_text(gate: dict, parts: dict, node: str, notes: list | None = None) -> dict:
    """alpha.50 (doc 104 / 106): the streamed option lines must match gate.options (count, order, labels; the recommended mark, when
    present, must name gate.recommendation); each option's sentences become options[i].note. The engine stays the author: the
    JSON options are validated as before and the menu is rendered from them."""
    lines = parts.pop("options_text")
    merged = dict(gate, **parts)
    opts = list(merged.get("options") or [])
    labels = [o.get("label") or "" for o in opts]
    if lines and [_gate_key(l["label"]) for l in lines] != [_gate_key(x) for x in labels]:   # alpha.51 / .53 / .59: without emphasis, the mark and whitespace
        # alpha.99 (doc 239 G3; production cache 5): the JSON options stay the menu; the streamed sentences are kept by position when the counts agree
        if notes is not None:
            notes.append({"code": "GATE_TEXT_MISMATCH", "text": f"the streamed option lines {[l['raw'] for l in lines]} differ from gate.options {labels}; "
                                                                "gate.options is the menu (alpha.99)"})
        lines = lines if len(lines) == len(opts) else []
    if not lines:   # alpha.99 (doc 239 G6): no option lines - the options as the JSON gives them
        if notes is not None and not parts.get("options_text_missing_noted"):
            notes.append({"code": "GATE_TEXT_COMPOSED", "text": f"the streamed gate text of {node!r} carried no option lines usable for the menu; gate.options is the menu (alpha.99)"})
        merged["options"] = [dict(o, label=_GATE_REC_MARK.sub("", o.get("label") or "").strip()) for o in opts]
        return merged
    marked = [i for i, l in enumerate(lines) if l["recommended"]]
    if marked and opts[marked[0]].get("intent") != merged.get("recommendation") and notes is not None:   # alpha.99: gate.recommendation stands
        notes.append({"code": "GATE_TEXT_MISMATCH", "text": f"the option marked as recommended ({lines[marked[0]]['raw']!r}) is not gate.recommendation "
                                                            f"{merged.get('recommendation')!r}; gate.recommendation stands (alpha.99)"})
    # alpha.53: a mark the model put into the JSON label is dropped - gate.recommendation carries the recommendation, the menu says so once
    merged["options"] = [dict(o, label=_GATE_REC_MARK.sub("", o.get("label") or "").strip(), **({"note": l["note"]} if l["note"] else {}))
                         for o, l in zip(opts, lines)]
    return merged


def _poll_host_texts(store: RunStore, kinds, node: str, deadline: float, not_before: float | None = None) -> dict:
    """One shared deadline; each requested file gets its own two-poll stability check."""
    pending = {kind: store.cache_dir / host_text_name(kind, node) for kind in kinds}
    last, ready = {}, {}
    while True:
        for kind, path in list(pending.items()):
            try:
                text = path.read_text(encoding="utf-8")
                if not_before is not None and path.stat().st_mtime < not_before - HOST_TEXT_FRESH_SLACK_S:
                    text = None
            except (OSError, UnicodeDecodeError):
                text = None
            if text is not None and text.strip() and text == last.get(kind):
                ready[kind] = text.strip("\n")
                del pending[kind]
            last[kind] = text
        remaining = deadline - time.monotonic()
        if not pending or remaining <= 0:
            return ready
        time.sleep(min(0.25, remaining))


def _missing_host_text(kind: str, node: str) -> EngineError:
    name = host_text_name(kind, node)
    if kind == "report":
        return EngineError("REPORT_NOT_RECEIVED", f"the streamed Report of node {node!r} has not reached the engine ({name})",
                           field="user_summary", expected="the Report streamed between ':::report <node>' and ':::' before this commit, or the full Report inline")
    return EngineError("HOST_TEXT_NOT_RECEIVED", f"the streamed {kind} of node {node!r} has not reached the engine ({name})",
                       field=HOST_FIELDS[kind], expected=f"the text streamed between ':::{kind} <node>' and ':::' before this commit, or the full text inline")


def _read_host_text(store: RunStore, kind: str, node: str, deadline: float, not_before: float | None = None) -> str:
    ready = _poll_host_texts(store, (kind,), node, deadline, not_before)
    if kind not in ready:
        raise _missing_host_text(kind, node)
    return ready[kind]


def _compose_gate_text(gate: dict, node: str, language=None) -> dict:
    """alpha.99 (04 series doc 239 G6; isolated cache 56): gate prose that never reached the engine is composed from the gate's own options -
    a plain question, the options as the explanation, the recommended option as the advice, and a closing line."""
    zh = not str(language or "zh").lower().startswith("en")
    opts = [o for o in gate.get("options") or [] if isinstance(o, dict)]
    rec = next((o.get("label") for o in opts if o.get("intent") == gate.get("recommendation")), None)
    texts = {"question": f"请选择节点「{node}」接下来怎么做：" if zh else f"How should node {node} continue?",
             "explanation": ("可选：" if zh else "Options: ") + ("；" if zh else "; ").join(str(o.get("label")) for o in opts) +
                 ("。来源：执行者未提供完整说明，引擎仅按既有选项整理。" if zh else ". Source: the executor omitted a complete explanation; the Engine composed this from existing options only."),
             "advice": ((f"执行者建议：{rec}" if zh else f"The executor recommends: {rec}") if rec else ("执行者未给建议。" if zh else "No recommendation was given.")),
             "closing": "请回复选项编号或文字。" if zh else "Reply with an option number or its words."}
    out = dict(gate)
    for key, text in texts.items():
        if not isinstance(out.get(key), str) or not out[key].strip() or out[key].strip() == "@host":
            out[key] = text
    return out


def _resolve_host_texts(store: RunStore, node: str, payload: dict, not_before: float | None = None, notes: list | None = None, language=None) -> dict:
    """alpha.30 A5 / alpha.44: every "@host" marker (user_summary, user_messages, explain, semantics.final_answer) is replaced by the
    text the host wrote beside the cache from the model's visible stream; one shared wait budget for the whole commit.
    alpha.99 (doc 239 P6 / G6): an Explain, a User Message or a gate text that never arrived is recorded, not refused - the Explain is kept
    empty, the message marker dropped, the gate prose composed from its options; the Report and the answer are still required."""
    kinds = _host_markers(payload)
    if not kinds:
        return payload
    deadline = time.monotonic() + HOST_REPORT_WAIT_S
    ready = _poll_host_texts(store, kinds, node, deadline, not_before)
    out = dict(payload)
    for kind in kinds:
        try:
            if kind not in ready:
                raise _missing_host_text(kind, node)
            text = ready[kind]
        except EngineError as exc:
            if exc.code != "HOST_TEXT_NOT_RECEIVED" or kind not in ("explain", "message", "gate"):
                raise
            if notes is not None:
                notes.append({"code": "HOST_TEXT_MISSING", "text": f"the streamed {kind} of {node!r} had not reached the engine at commit time "
                                                                    f"({host_text_name(kind, node)}): " + {"explain": "explain recorded empty",
                                                                    "message": "the @host marker dropped", "gate": "the gate prose composed from its options"}[kind]
                                                                    + " (alpha.99) - stream the text before the commit"})
            if kind == "explain":
                out["explain"] = ""
            elif kind == "message":
                out["user_messages"] = [m for m in out.get("user_messages") or [] if m != "@host"]
            else:
                from . import gate_delivery
                gate_delivery.missing(store,node,payload)
            continue
        if kind == "report":
            out["user_summary"] = text
        elif kind == "message":   # alpha.95: the first marker becomes the streamed text, further markers drop, inline items stay in order
            merged, placed = [], False
            for m in payload.get("user_messages") or []:
                if m == "@host":
                    if not placed:
                        merged.append(text)
                        placed = True
                elif isinstance(m, str) and m.strip() and m.strip() in text:
                    continue   # an item inlined beside the marker that the stream already carries is not repeated
                else:
                    merged.append(m)
            out["user_messages"] = merged
        elif kind == "explain":
            out["explain"] = text
        elif kind == "gate":
            out["gate"] = _apply_gate_text(out["gate"], _split_gate_text(text, node, out["gate"], language, notes), node, notes)   # alpha.50 / alpha.99
        else:
            out["semantics"] = dict(out["semantics"], final_answer=text)
    return out


_resolve_host_report = _resolve_host_texts   # alpha.30 name


def _safe_name(node_id: str) -> str:
    """File-name stem of a node id for _public/ files. Depth-0 names are used as they are; a sub node uses
    its last segment (the ordinal in the file name already makes it unique), shortened with an id hash when
    it would approach the 255-character file-name component limit."""
    local = node_id.rsplit("/", 1)[-1]
    if "/" in node_id:
        local = "sub." + local
    if re.search(r'[^A-Za-z0-9_.-]', local):
        local = re.sub(r'[^A-Za-z0-9_.-]', '_', local) + '-' + sha256_bytes(node_id.encode('utf-8'))[:8]
    if len(local) > 100:
        local = local[:88] + "-" + sha256_bytes(node_id.encode("utf-8"))[:8]
    return local


def _local(node_id: str) -> str:
    return node_id.rsplit("/", 1)[-1]


def _bare(entry: dict) -> str:
    return entry.get("node") or entry["name"]


def _cache_path_for(store: RunStore, index: dict, entry: dict, visit: int) -> Path:
    if entry is None:
        raise EngineError('CATALOG_HISTORY_MISSING','Accepted node definition is missing; preserve the run and stop. Never skip its source.')
    if entry["kind"] == "sub":
        return store.sub_cache_path(entry["parent"], _local(entry["name"]), visit)
    program = 'engine' if entry['kind'] == 'engine' and entry['name'] == NODE_MATCH else _program_name(index)
    return store.node_cache_path(program, entry["name"], visit)


def _graph_for(program, entry: dict) -> dict:
    pd = program.docs[entry["doc"]] if entry.get("doc") else program.entry
    return pd.tasks[entry.get("task") or "main"]


def _frame_of(index: dict, entry: dict) -> dict | None:
    """The open frame a sub node executes in (None for depth-0 nodes)."""
    if entry["kind"] != "sub":
        return None
    return next((f for f in reversed(index["call_stack"]) if f["parent"] == entry["parent"]), None)


def _sibling_entry(entry: dict, node: str, ordinal: int) -> dict:
    """A catalog entry for another node of the same graph as `entry` (same frame at any depth)."""
    if entry["kind"] == "sub":
        ns = _local(entry["name"]).split(".", 1)[0]
        return program_loader.sub_entry(entry["parent"], entry["depth"], entry["doc"], entry["task"], ns, node, ordinal)
    return program_loader.business_entry(node, ordinal)


def _frame_children(index: dict, parent: str, parent_visit: int) -> list[tuple[str, dict]]:
    """(node key, node entry) of the direct sub nodes of one module occurrence, in commit order."""
    out = [(k, v) for k, v in index["nodes"].items() if v.get("parent") == parent and v.get("parent_visit") == parent_visit]
    out.sort(key=lambda kv: (kv[1].get("order") if kv[1].get("order") is not None else 10**9, kv[1]["visit"]))
    return out


# --- sub-agent dispatch (doc 10 §2–§3) ------------------------------------------------------------

def _engine_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _fs(path) -> str:
    return str(path).replace("\\", "/")


def _dispatch_group(index: dict) -> dict:
    return index.setdefault("dispatch", RunStore.new_dispatch_group())


def _effective_loading_mode(index: dict) -> str:
    pg = index['program']
    return 'node' if pg.get('loading_mode') == 'node' and pg.get('execution_loading_mode', 'node') != 'normal' else 'normal'


def _dispatch_policy(index: dict) -> str:
    mode = _effective_loading_mode(index)
    return DISPATCH_POLICY_NODE if mode == "node" else DISPATCH_POLICY_INLINE


def _no_agent_normal(index: dict) -> bool:
    pg = index.get('program') or {}
    return pg.get('loading_mode') == 'node' and pg.get('execution_loading_mode') == 'normal'


def _declared_mode(program, entry: dict) -> str:
    view = _view_for(program, entry)
    return str((view["reserved"].get("execute_mode") if view else None) or "inline")


def _self_dispatch(index: dict, entry: dict, visit: int) -> tuple[str, dict | None]:
    """Resolve the root occurrence through parent visits, not textual prefixes."""
    if dispatch_scope.enabled(index):
        key, record = dispatch_scope.owner(index, entry, visit)
        if record:
            return key, record
    key = _node_key(entry["name"], visit)
    return key, (index["nodes"].get(key) or {}).get("dispatch")


def _should_dispatch(index: dict, program, entry: dict) -> bool:
    """Every entry-file graph may contain independently dispatched main nodes."""
    return dispatch_scope.is_main(index, entry) and _declared_mode(program, entry) == "agent" and _dispatch_policy(index) == DISPATCH_POLICY_NODE \
        and _host_has_agent_tool(index) and dispatch_budget.available(index, dispatch_budget.pool(program, entry))


def _ticket_known(index: dict, ticket: str) -> bool:
    """True when the ticket was issued in this run (current or historical, any occurrence): a stale ticket, not a foreign one."""
    for ne in index["nodes"].values():
        d = ne.get("dispatch") or {}
        if d.get("ticket") == ticket or any(h.get("ticket") == ticket for h in d.get("history") or []):
            return True
    return False


def _ticket_error(index: dict, key: str, agent_ticket: str, current: dict | None) -> EngineError:
    if _ticket_known(index, agent_ticket):
        return EngineError("DISPATCH_TICKET_STALE", f"ticket {agent_ticket} was superseded or closed", field="agent_ticket",
                           expected=current["ticket"] if current and current.get("state") in ("ISSUED", "CLAIMED") else "none: stop")
    return EngineError("DISPATCH_TICKET_INVALID", f"ticket {agent_ticket} does not belong to {key}", field="agent_ticket",
                       expected="the ticket in the bootstrap for this node")


def _return_query_pending() -> EngineError:
    """Review of docs/05SoulRun 87 (C1): a call that would open the liveness stop of an interrupted, SendMessage-resumed
    child before the main agent's next-node offered its one bounded return query is refused instead - no pause, nothing
    committed - so that query still comes first and the stop after it can carry the human's replacement option."""
    return EngineError('DISPATCH_RETURN_QUERY_PENDING',
        'The run was interrupted while a resumed sub-agent held the ticket of this part; whether it stopped cannot be '
        "verified. Until the main agent's next-node has offered its one bounded return query, no call for this part is "
        'accepted: nothing was committed and the run is not paused. A sub-agent: stop now and return this error as your '
        'final text. The main agent: call next-node.', field='agent_ticket')


def _host_has_agent_tool(index: dict) -> bool:
    """alpha.62 (doc 135 §4 B): False only when the host declared host_tools.agent = false (prepare_cache host_tools=); an older host or
    an absent declaration keeps the alpha.7 path (spawn, then two unclaimed / abandoned attempts before EXHAUSTED)."""
    tools = (index.get("host") or {}).get("host_tools")
    return not (isinstance(tools, dict) and tools.get("agent") is False)


def _executor_mode(index: dict, program, entry: dict, visit: int) -> dict:
    """Loading mode and entry-file main node decide ownership; external descendants inline."""
    if entry["kind"] == "engine" or _view_for(program, entry) is None:
        return {"declared": "inline", "effective": "inline", "downgrade": None}
    root = dispatch_scope.root_entry(index, entry)
    declared = _declared_mode(program, root or entry)
    if dispatch_scope.enabled(index) and dispatch_scope.pending_root(index, entry, visit):
        return {"declared": declared, "effective": "inline", "downgrade": None}
    if declared not in ("inline", "agent"):
        return {"declared": declared, "effective": "inline", "downgrade": "EXECUTE_MODE_UNKNOWN"}
    if declared == "inline":
        return {"declared": "inline", "effective": "inline", "downgrade": None}
    if _dispatch_policy(index) != DISPATCH_POLICY_NODE:
        return {"declared": "agent", "effective": "inline", "downgrade": "NORMAL_MODE_FORCES_INLINE"}
    if not dispatch_scope.is_main(index, entry):
        return {"declared": declared, "effective": "inline", "downgrade": None}
    _, existing = _self_dispatch(index, entry, visit)
    if existing and existing.get('mode') == 'agent':
        return {"declared": "agent", "effective": "agent", "downgrade": None}
    if not _host_has_agent_tool(index):
        return {"declared": "agent", "effective": "inline", "downgrade": "HOST_NO_AGENT_TOOL"}
    if not dispatch_budget.available(index, dispatch_budget.pool(program, entry)):
        return {"declared": "agent", "effective": "inline", "downgrade": "SPAWN_BUDGET_EXHAUSTED"}
    return {"declared": "agent", "effective": "agent", "downgrade": None}


def _bootstrap_text(store: RunStore, index: dict, entry: dict, ticket: str, position: dict, resume_qid: str | None) -> str:
    """doc 12 §1.3: the sub-agent's whole prompt — one head line naming the standard sub-agent program plus key=value
    parameters. Behaviour lives in agent_engine.aisop.json, never in this text."""
    engine, cache = _fs(_engine_dir()), _fs(store.cache_dir.resolve())
    lines = [
        f'[EXECUTE ENGINE SUB-AGENT] Read and execute "{engine}/agent_engine.aisop.json" with the parameters below, then stop.',
        f"cache_dir={cache}",
        f"engine_dir={engine}",
        f"ticket={ticket}",
        f"node={entry['name']}",
        f"position={position['label']}",
        f"user_language={index.get('user_language') or 'zh'}",
        f"resume_gate={resume_qid or 'none'}",
    ]
    return "\n".join(lines)


def _issue_ticket(store: RunStore, index: dict, owner: dict, served: dict, visit: int, *, attempt: int, reason: str,
                  resume_qid: str | None = None, pool: str = 'ordinary', handoff: dict | None = None,
                  identity_handoff: dict | None = None) -> dict:
    """Mint a dispatch ticket for the outer occurrence `owner` (index node entry), bootstrapping the node `served`
    (the outer node itself, or the sub node the sub-agent must continue from). Writes _dispatch.<ticket>.json."""
    from . import blind_review
    program = _load_routed_program(_read_run_input(store))
    prev = owner.get('dispatch')
    resume_requested = bool(prev and reason in {'gate_resume', 'segment_resume'})
    if reason == 'segment_resume' and not dispatch_lifecycle.unfinished_return(index, prev):
        raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'Only a verified returned unfinished root permits a non-gate continuation.')
    resume_target = dispatch_lifecycle.resume_executor(store, prev) if resume_requested else None
    if resume_requested and not resume_target:
        raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'No trusted native agent identity; do not replace it silently.')
    binding = copy.deepcopy((prev or {}).get('review_binding'))
    if binding:
        blind_review.load(store, binding)
    elif program:
        binding = blind_review.bind(store, index, program, served, visit)
    from . import independent_inputs
    input_binding = copy.deepcopy((prev or {}).get('input_binding'))
    if input_binding:
        independent_inputs.load(store, input_binding)
    elif program:
        input_binding = independent_inputs.bind(store, index, program, served, visit)
    now = now_iso()
    group = _dispatch_group(index)
    group["tickets_issued"] += 1
    ticket = f"d{group['tickets_issued']:03d}-{secrets.token_hex(4)}"
    position = _track_position(index, served, visit)
    text = _bootstrap_text(store, index, served, ticket, position, resume_qid)
    continuation = dispatch_lifecycle.continuation_state(store, index) if reason == 'segment_resume' else None
    if continuation:
        text += '\ncontinuation_state_sha256=' + sha256_bytes(json.dumps(continuation, ensure_ascii=False, sort_keys=True).encode())
    sha = sha256_bytes(text.encode("utf-8"))
    history = list(prev.get("history") or []) if prev else []
    if prev and prev.get("ticket"):
        history.append({k: prev.get(k) for k in ("ticket", "attempt", "state", "reason", "issued_at", "claimed_at", "mode", "actor", "pool")})
        if prev.get('scope_root'):
            history[-1].update(scope_root=copy.deepcopy(prev['scope_root']), public_refs=list(prev.get('public_refs') or []))
            history[-1].update({k: copy.deepcopy(prev.get(k)) for k in ('lifecycle', 'exit_evidence', 'last_progress_at', 'contract_delivery',
                'resume_executor', 'bootstrap_sha256', 'paused_at', 'replacement_count', 'handoff', 'identity_handoff', 'closed_reason', 'closed_at') if prev.get(k) is not None})
    owner["dispatch"] = {"mode": "agent", "ticket": ticket, "attempt": attempt, "state": "ISSUED", "reason": reason,
                         "issued_at": now, "claimed_at": None, "committed_at": None, "paused_at": None, "actor": None,
                         "bootstrap_sha256": sha, "downgrade": None, "fallback": None, "history": history, "pool": pool}
    if dispatch_scope.enabled(index):
        root = prev.get('scope_root') if prev else None
        owner['dispatch'].update(scope_root=root or dict(node=served['name'], visit=visit), public_refs=[],
            lifecycle='UNKNOWN', exit_evidence=None, last_progress_at=now,
            context_resume='ORIGINAL_SESSION_RESUME_UNVERIFIED' if prev else 'NEW_SEGMENT')
        if resume_requested:
            owner['dispatch'].update(resume_executor=resume_target, context_resume='ORIGINAL_SESSION_RESUME_REQUESTED')
    if binding:
        owner['dispatch']['review_binding'] = binding
    if input_binding:
        owner['dispatch']['input_binding'] = input_binding
    if dispatch_lifecycle.replacement_accounting(index) and prev:
        owner['dispatch']['replacement_count'] = prev.get('replacement_count', 0) + bool(handoff)
    if handoff:
        owner['dispatch']['handoff'] = handoff
        owner['dispatch']['context_resume'] = 'REPLACEMENT_SESSION_REQUESTED'
    if identity_handoff:
        owner['dispatch']['identity_handoff'] = copy.deepcopy(identity_handoff)
        owner['dispatch']['context_resume'] = 'REPLACEMENT_SESSION_REQUESTED'
    from . import dispatch_prepare
    store.write_json_once(dispatch_prepare.path(store,ticket), {
        "schema_version": 1, "ticket": ticket, "trace_id": index["trace_id"], "node": served["name"], "visit": visit,
        "attempt": attempt, "reason": reason, "issued_at": now, "claimed_at": None, "committed_at": None,
        "bootstrap": text, "bootstrap_sha256": sha, "pool": pool,
        **({'scope_root': owner['dispatch']['scope_root']} if dispatch_scope.enabled(index) else {}),
        **({'resume_executor': owner['dispatch']['resume_executor']} if owner['dispatch'].get('resume_executor') else {}),
        **({'handoff': handoff} if handoff else {}),
        **({'identity_handoff': identity_handoff} if identity_handoff else {}),
        **({'continuation': continuation} if continuation else {}),
        **({'review_binding': binding} if binding else {}),
        **({'input_binding': input_binding} if input_binding else {})})
    dispatch_prepare.note(store,ticket)
    return owner["dispatch"]


def _dispatch_view(store: RunStore, dispatch: dict, *, wait: bool = False, note: str | None = None) -> dict:
    """The `dispatch` object of a next-node reply to the main agent."""
    state = dispatch["state"]
    view = {"required": state in ("ISSUED", "CLAIMED"), "state": state, "ticket": dispatch["ticket"], "attempt": dispatch["attempt"],
            "budget_pool": dispatch.get('pool', 'ordinary'),
            "reason": dispatch.get("reason"), "wait": wait, "bootstrap": None,
            "spawn": {"tool": "Agent", "synchronous": True, "prompt": "dispatch.bootstrap verbatim"} if state == "ISSUED" and not wait else None,
            "fallback_allowed": state == "EXHAUSTED",
            "evidence_required": (["dispatch_fallback.reason", "dispatch_fallback.exhaustion_ticket" if dispatch.get('downgrade') == 'SPAWN_BUDGET_EXHAUSTED' else "dispatch_fallback.spawn_failure_evidence"] if state == "EXHAUSTED" else []),
            "note": note}
    if state == "ISSUED" and not wait:
        from . import dispatch_prepare
        view["bootstrap"] = dispatch_prepare.read(store,dispatch["ticket"])["bootstrap"]
        if dispatch.get('resume_executor'):
            target = dispatch['resume_executor']
            view['spawn'] = dict(tool='SendMessage', to=target['agent_id'], message='dispatch.bootstrap verbatim',
                parent_session_id=target['session_id'], completion='sent ACK is not exit; retrieve the actual result with TaskOutput',
                wait_for_result=dict(tool='TaskOutput', task_id=target['agent_id'], block=True))
            if dispatch_lifecycle.pause_continuation(store.read_index()):
                view['spawn'].pop('wait_for_result')
                view['spawn']['completion'] = 'Wait for the next engine-accepted gate or root result. ACK is not completion; missing return remains UNKNOWN, not a continuation prerequisite.'
    if dispatch.get('reason') in {'segment_resume', 'segment_replacement'}:
        view['continuation_rule'] = _contracts.text('resume.non_gate_handoff')
    if dispatch.get('scope_root'):
        view.update(dispatch_scope.view(dispatch))
        view.update(lifecycle=dispatch.get('lifecycle', 'UNKNOWN'), last_progress_at=dispatch.get('last_progress_at'),
                    context_resume=dispatch.get('context_resume', 'ORIGINAL_SESSION_RESUME_UNVERIFIED'),
                    return_observer='next_node.py --cache-dir <this cache> --observe-dispatch-return '+dispatch['ticket'])
        view['note'] = (note or '') + ' The root ticket owns its reached subtree. Only its executor works inside. Return/present the served public_refs in order once; after a returned WAITING_USER main calls next-node once before presenting them (resume.dispatch_segments). Host start/return reports are diagnostic only, not qualified identity. Only the current explicit human handover authorizes a new executor. UNKNOWN is not exit; do not start a competing executor.'
    return view


def read_dispatch_bootstrap(cache_dir: str | Path, ticket: str) -> dict:
    """Recover an unread, still-valid ISSUED bootstrap without serving or minting a ticket."""
    store = RunStore(cache_dir)
    if not store.exists():
        raise RunStoreError('INDEX_MISSING', str(store.index_path))
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        entry = _catalog_entry(index, index['current']['name'])
        if index['run_state'] != 'RUNNING' or entry is None:
            raise EngineError('DISPATCH_TICKET_INVALID', 'no running occurrence')
        key, dispatch = _self_dispatch(index, entry, index['current']['visit'])
        if not dispatch or dispatch.get('ticket') != ticket or dispatch.get('state') != 'ISSUED':
            raise _ticket_error(index, key, ticket, dispatch)
        age = _ms_between(dispatch.get('issued_at'), now_iso())
        if not dispatch_scope.enabled(index) and (age is None or age >= DISPATCH_CLAIM_GRACE_MS):
            raise EngineError('DISPATCH_TICKET_INVALID', 'bootstrap expired; use normal next-node recovery')
        record = store.read_json(store.dispatch_path(ticket))
        text = record.get('bootstrap')
        if record.get('ticket') != ticket or record.get('trace_id') != index['trace_id'] \
                or record.get('node') != entry['name'] or record.get('visit') != index['current']['visit'] \
                or record.get('state', 'ISSUED') != 'ISSUED' or not isinstance(text, str) \
                or sha256_bytes(text.encode('utf-8')) != dispatch.get('bootstrap_sha256') \
                or record.get('bootstrap_sha256') != dispatch.get('bootstrap_sha256'):
            raise EngineError('DISPATCH_TICKET_INVALID', 'bootstrap record does not match current authority')
        return {'ticket': ticket, 'bootstrap': text, 'state': 'ISSUED', 'read_only': True}


def _dispatch_step(store: RunStore, index: dict, d: dict | None, gate_answer: dict | None, abandon: str | None, *,
                   pool='ordinary', now: str | None = None) -> tuple:
    """next-node without a ticket on a dispatched occurrence (doc 10 §3.2): the step it takes for the occurrence's
    dispatch `d`. Review of docs/05SoulRun 87, round 4: decided here, without writing anything, and carried out by
    _main_agent_dispatch, so dispatch_budget.recheck_outcome reads the very decision to say what a recheck on an engine
    stop leads to. A condition that opens an engine stop is raised as an EngineError, as before. Returns (step, detail):
      human_replacement (authority) | handoff (authority) | restored (question id) | gate_resume | segment_resume |
      fresh | exhaust (anomaly code or None: the ticket is closed first when set) | reissue (anomaly code or None) |
      wait_handoff | wait_issued | wait_claimed | inline | view"""
    from . import dispatch_identity
    identity_authority = dispatch_identity.authority(store, index, d)
    if identity_authority:
        return 'identity_handoff', identity_authority
    scope = dispatch_scope.enabled(index)
    if scope and dispatch_lifecycle.returned(d):
        dispatch_lifecycle.verify(store, d)
    # docs/05SoulRun 84/87: a replacement the human chose at an engine stop - for a child that came back with an error
    # (paused at a gate or not) or one whose liveness an interruption left unknown - is rechecked here, then issued.
    authority = dispatch_lifecycle.human_replacement(store, index, d) if scope and d else None
    if authority:
        return 'human_replacement', authority
    if scope and d and d.get('state') in ('ABANDONED', 'EXHAUSTED', 'FALLBACK'):
        raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE',
                          'No qualified child identity; an explicit human handover is required before unfinished work continues.')
    if scope and d and abandon == d.get('ticket') and not dispatch_lifecycle.returned(d):
        handoff = dispatch_lifecycle.handoff(store, index, d)
        if not handoff:
            raise EngineError('DISPATCH_LIVENESS_UNKNOWN', 'Observe the actual synchronous Agent return; model error text is not exit evidence.')
        return _unlapsed(store, index, d, 'handoff', handoff)
    restored = program_guard.dispatch_resume_gate(store, index, d) if d else None
    paused_answered = bool(d and d.get('state') == 'CLAIMED' and gate_answer and d.get('paused_at'))
    needs_claim = d is None or restored or paused_answered
    continuing = bool(d and (restored or paused_answered))
    if continuing and not dispatch_lifecycle.resume_executor(store, d):
        raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'The original child identity must be verified before continuation.')
    free_continuation = continuing and (dispatch_budget.resume_accounting(index) if pool == 'ordinary'
                                       else dispatch_budget.independent_resume_accounting(index))
    if needs_claim and not free_continuation and not dispatch_budget.available(index, pool):
        return _exhausted(store, index, d, pool, None)
    if restored:
        if not dispatch_lifecycle.resume_executor(store, d):
            raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'Restore the original child identity and parent; a new Agent is not authorized.')
        return _unlapsed(store, index, d, 'restored', restored)
    if d is None:
        return 'fresh', None
    if paused_answered:
        if not dispatch_lifecycle.resume_executor(store, d):
            raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'The gate is answered, but the original child cannot yet be resumed.')
        return _unlapsed(store, index, d, 'gate_resume', None)
    if dispatch_lifecycle.unfinished_return(index, d):
        if not dispatch_lifecycle.resume_executor(store, d):
            # docs/05SoulRun 84: a child that returned with an error is replaced only by the human's recorded choice (above).
            raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'The unfinished root returned without a trusted resumable child; stop, never silently replace it.')
        if d['attempt'] >= DISPATCH_ATTEMPTS_MAX:
            raise EngineError('ORIGINAL_EXECUTOR_CONTINUATION_EXHAUSTED', 'The existing incomplete-attempt bound was reached; preserve accepted work and ask the human, never take over inline.')
        return _unlapsed(store, index, d, 'segment_resume', None)
    now = now or now_iso()
    anomaly = None
    if d["state"] == "ISSUED":
        if not dispatch_budget.available(index, pool, d):
            return _exhausted(store, index, d, pool, None)
        age = _ms_between(d["issued_at"], now) or 0
        if abandon != d["ticket"] and (scope or age < DISPATCH_CLAIM_GRACE_MS):
            return ('wait_handoff' if dispatch_lifecycle.handoff(store, index, d) else 'wait_issued'), None
        anomaly = 'DISPATCH_UNCLAIMED'
    elif d["state"] == "CLAIMED":
        age = _ms_between(d["claimed_at"], now) or 0
        if abandon != d["ticket"] and (scope or age < DISPATCH_CLAIMED_STALE_MS):
            return 'wait_claimed', None
        anomaly = 'DISPATCH_ABANDONED'
    elif d["state"] in ("EXHAUSTED", "FALLBACK"):
        if pool == 'independent':
            raise EngineError('INDEPENDENT_ATTEMPTS_EXHAUSTED', 'Independent execution cannot fall back inline.')
        return _unlapsed(store, index, d, 'inline', None)
    elif d["state"] != "ABANDONED":   # ABANDONED: abandoned by the host at recovery (abandon_dispatch): re-issue or exhaust
        return 'view', None
    if d["attempt"] >= DISPATCH_ATTEMPTS_MAX or not dispatch_budget.available(index, pool):
        return _exhausted(store, index, d, pool, anomaly or '')
    return _unlapsed(store, index, d, 'reissue', anomaly or '')


def _exhausted(store, index, d, pool, detail):
    """The exhaust step: _exhaust_dispatch raises its stop (the independent pool, or no ticket to close), else the main
    agent continues inline - work going on for this part, so the lapse check applies (round 4, b)."""
    if _exhaust_code(index, d, pool):
        return 'exhaust', detail
    return _unlapsed(store, index, d, 'exhaust', detail)


def _unlapsed(store: RunStore, index: dict, d: dict, step: str, detail=None) -> tuple:
    """Review of docs/05SoulRun 87, round 4 (b): where the engine would issue a ticket other than the human's replacement
    or let work go on inline for this part, it first checks that the human's accepted choice to retire this ticket has
    not lapsed unacknowledged (dispatch_lifecycle.lapsed_replacement): the choice was not carried out, and neither the old
    agent's resume nor anything else runs for this part without a new answer. Where the engine would instead open
    another stop, that stop opens and says so (dispatch_budget.pause)."""
    lapsed = dispatch_lifecycle.lapsed_replacement(store, index, d) if dispatch_scope.enabled(index) and d else None
    if lapsed:
        facts = dispatch_lifecycle.lapse_facts(store, index, d)
        resume = step in ('segment_resume', 'gate_resume', 'restored')
        raise EngineError('DISPATCH_REPLACEMENT_LAPSED', f"The human chose a new agent at {lapsed['question_id']}, but the host "
                          f"recorded {dispatch_lifecycle.lapse_words(facts, zh=False)} after that choice: nothing was replaced, "
                          f"and {'the old agent is not resumed' if resume else 'nothing goes on for this part'} without a new answer.")
    return step, detail


def _main_agent_dispatch(store: RunStore, index: dict, owner: dict, served: dict, visit: int, gate_answer: dict | None,
                         abandon: str | None, abandon_reason: str | None, *, pool='ordinary') -> dict:
    """next-node without a ticket on a dispatched occurrence: issue, wait, re-issue or exhaust (doc 10 §3.2) - the step
    _dispatch_step decides, carried out."""
    now = now_iso()
    d = owner.get("dispatch")
    step, detail = _dispatch_step(store, index, d, gate_answer, abandon, pool=pool, now=now)
    if step == 'identity_handoff':
        from . import dispatch_identity
        failures = dispatch_identity.same_progress_claims(d, detail['progress_key'])
        d = _issue_ticket(store, index, owner, served, visit, attempt=d['attempt'],
            reason='identity_handoff', resume_qid=gate_answer['question_id'] if gate_answer else None,
            pool=pool, identity_handoff=detail)
        d['replacement_count'] = failures
        return _dispatch_view(store, d, note='The human explicitly authorized ONE NEW agent. The old ticket is fenced. '
            'Continue only recorded unfinished work; verify uncertain external operations before any retry. '
            'Native identity and physical process exit remain unverified.')
    if step == 'human_replacement':
        return _issue_human_replacement(store, index, owner, served, visit, d, detail, gate_answer, pool)
    if step == 'handoff':
        handoff = detail
        handoff.update(reason=abandon_reason or 'original child unavailable', reason_source='main_report_unverified')
        # Publication and old-ticket retirement occur only after _write_index accepts this conversion.
        d['state'] = 'ABANDONED'
        segment = d.get('reason') == 'segment_resume'
        d.update(closed_reason='segment_handoff' if segment else 'gate_handoff', closed_at=now)
        d = _issue_ticket(store, index, owner, served, visit, attempt=d['attempt'], reason='segment_replacement' if segment else 'gate_replacement',
                          resume_qid=handoff['question_id'], pool=pool, handoff=handoff)
        return _dispatch_view(store, d, note='Returned old segment; unused continuation revoked. Spawn one replacement child '
            'with agent_engine.aisop.json; continue only the current authorized task and remaining steps, never replay business effects. '
            'A non-gate continuation carries no new human answer; fencing is not proof of physical process death.')
    if step == 'restored':
        d['state'] = 'ABANDONED'  # Publish retirement only after the replacement index is accepted.
        d = _issue_ticket(store, index, owner, served, visit, attempt=d['attempt'], reason='gate_resume',
                          resume_qid=gate_answer['question_id'] if gate_answer else detail, pool=pool)
        return _dispatch_view(store, d, note='Program integrity restored. Continue preserved work with this new ticket; '
                              'the old ticket is revoked. Do not replay completed side effects.')
    if step == 'fresh':
        d = _issue_ticket(store, index, owner, served, visit, attempt=1,
                          reason="gate_resume" if gate_answer else "fresh", resume_qid=gate_answer["question_id"] if gate_answer else None, pool=pool)
        return _dispatch_view(store, d, note="Spawn one sub-agent with this bootstrap and wait for its final text (its node-commit result). If it is "
                                             "WAITING_USER, call next-node once (it shows and serves the gate), then present "
                                             "that result's public_block_ref and the served gate once each; otherwise present "
                                             "that result's public_block_ref verbatim, once, then call next-node again.")
    if step == 'gate_resume':
        d['state'] = 'ABANDONED'
        d = _issue_ticket(store, index, owner, served, visit, attempt=d["attempt"], reason="gate_resume", resume_qid=gate_answer["question_id"], pool=pool)
        return _dispatch_view(store, d, note="The gate was answered: resume the original child in its bound parent session with this bootstrap; "
                                             "never replace it or replay completed work. Present its ordered returned refs "
                                             "(at WAITING_USER after one next-node, which shows and serves the gate).")
    if step == 'segment_resume':
        d = _issue_ticket(store, index, owner, served, visit, attempt=d['attempt'] + 1,
                          reason='segment_resume', pool=pool)
        return _dispatch_view(store, d, note='The root returned before completion. Resume its original child in the bound parent session; '
            'continue the first unfinished served node with this ticket. This is not a human answer or permission to replay accepted work.')
    if step == 'wait_handoff':
        # docs/05SoulRun 87 (record 86 #11): this continuation may never reach its child; the engine still replaces nothing itself.
        return _dispatch_view(store, d, wait=True, note=f"This continuation ticket is issued and not yet claimed. If the SendMessage to the "
            f"original child was sent, wait for it, then call next-node again. If that SendMessage failed or was never sent, call next-node "
            f"--dispatch-abandon {d['ticket']} --reason <the actual reason>.")
    if step == 'wait_issued':
        return _dispatch_view(store, d, wait=True, note="A ticket was issued moments ago and is not yet claimed: wait for the spawned sub-agent, then call next-node again.")
    if step == 'wait_claimed':
        return _dispatch_view(store, d, wait=True, note="The sub-agent holding this ticket is working: wait for the Agent tool to return, then call next-node again "
                                                        "(if the Agent tool failed, call next-node with --dispatch-abandon <ticket> --reason <error>).")
    if step == 'inline':
        return _dispatch_view(store, d, note="Continue remaining work inline; supply dispatch_fallback.reason and the evidence_required field. Quota exhaustion is not an Agent tool failure.")
    if step == 'view':
        return _dispatch_view(store, d)
    if step == 'exhaust' and detail is None:
        return _exhaust_dispatch(store, index, d, served, pool)
    if detail == 'DISPATCH_UNCLAIMED':
        index["anomalies_summary"].append({"node": served["name"], "code": "DISPATCH_UNCLAIMED",
                                           "text": f"ticket {d['ticket']} (attempt {d['attempt']}) was never claimed" + (f": {abandon_reason}" if abandon_reason else "")})
    elif detail == 'DISPATCH_ABANDONED':
        index["anomalies_summary"].append({"node": served["name"], "code": "DISPATCH_ABANDONED",
                                           "text": f"ticket {d['ticket']} (attempt {d['attempt']}) claimed but never committed" + (f": {abandon_reason}" if abandon_reason else "")})
    _record_ticket_state(store, d, "ABANDONED")
    if step == 'exhaust':
        return _exhaust_dispatch(store, index, d, served, pool)
    d = _issue_ticket(store, index, owner, served, visit, attempt=d["attempt"] + 1, reason="reissue",
                      resume_qid=gate_answer["question_id"] if gate_answer else None, pool=pool)
    return _dispatch_view(store, d, note="Previous attempt did not complete: spawn a new sub-agent with this bootstrap and wait for it.")


def _issue_human_replacement(store, index, owner, served, visit, d, authority, gate_answer, pool):
    """docs/05SoulRun 84/87: issue the one new child the human chose. The old ticket is retired first (any later commit
    or claim with it is DISPATCH_TICKET_STALE); the new ticket keeps the attempt - a replacement is counted by
    replacement_count, never as a dispatch attempt, and as a new task only for a part never charged before (owner ruling
    352 §8 item 2; its claim decides) - and carries the answered gate this occurrence resumes, as gate_replacement does."""
    count = int(d.get('replacement_count') or 0)
    interrupted = 'interruption_observation' in authority['basis']
    d['state'] = 'ABANDONED'  # Publish retirement only after the replacement index is accepted.
    d.update(closed_reason='human_replacement', closed_at=now_iso())
    d = _issue_ticket(store, index, owner, served, visit, attempt=d['attempt'], reason='human_replacement',
                      resume_qid=gate_answer['question_id'] if gate_answer else None, pool=pool)
    d.update(human_replacement=copy.deepcopy(authority), replacement_count=count + 1,
             context_resume='REPLACEMENT_SESSION_REQUESTED')
    cause = ('liveness of the previous child could not be verified after an interruption, and its ticket is now retired'
             if interrupted else 'the previous child returned with an error and is not resumed')
    return _dispatch_view(store, d, note=f"The {cause}; at {authority['question_id']} the human chose a replacement. Spawn ONE NEW "
        'sub-agent with this bootstrap: it continues the first unfinished served node of this scope and its remaining steps. '
        'Accepted nodes stay; never replay completed business effects.')


def _exhaust_code(index, dispatch, pool):
    """The stop _exhaust_dispatch raises instead of closing the ticket for inline work, or None (round 4: read by
    _dispatch_step too)."""
    if pool == 'independent':
        return 'INDEPENDENT_BUDGET_EXHAUSTED' if not dispatch_budget.available(index, pool) else 'INDEPENDENT_ATTEMPTS_EXHAUSTED'
    return 'DISPATCH_BUDGET_EXHAUSTED' if dispatch is None else None


def _exhaust_dispatch(store, index, dispatch, entry, pool):
    code = _exhaust_code(index, dispatch, pool)
    if code == 'DISPATCH_BUDGET_EXHAUSTED':
        raise EngineError(code, 'No new claim is available.')
    if code:
        raise EngineError(code, 'No legal independent attempt remains; ask the human, never self-review.')
    quota = not dispatch_budget.available(index, pool)
    _record_ticket_state(store, dispatch, 'EXHAUSTED', downgrade='SPAWN_BUDGET_EXHAUSTED' if quota else 'DISPATCH_ATTEMPTS_EXHAUSTED')
    index['anomalies_summary'].append(dict(node=entry['name'], code='DISPATCH_EXHAUSTED',
        text=f"Ticket {dispatch['ticket']} closed; ordinary {dispatch_budget.usage(index, pool)}/{dispatch_budget.limit(index, pool)}. Preserve completed work."))
    return _dispatch_view(store, dispatch, note='The old execution right is closed. Continue ONLY remaining work inline from the sealed node cache, '
        'gate answer and captures; do not replay completed side effects. Supply reason and exhaustion_ticket for confirmed '
        'returned or quota-exhausted tickets; otherwise supply actual spawn_failure_evidence. Never invent an Agent error.')


def _record_ticket_state(store: RunStore, dispatch: dict, state: str, *, preserve_equal=False, **fields) -> None:
    dispatch["state"] = state
    dispatch.update(fields)
    path = store.dispatch_path(dispatch["ticket"])
    if store.exists_path(path):
        rec = store.read_json(path)
        before = copy.deepcopy(rec) if preserve_equal else None
        rec["state"] = state
        rec.update({k: v for k, v in fields.items() if k in ("claimed_at", "committed_at", "paused_at", "actor", "downgrade", 'lifecycle', 'exit_evidence', 'interruption_observation')})
        if not preserve_equal or rec != before:
            _write_json(path, rec)


def abandon_dispatch(cache_dir: str | Path, reason: str) -> dict:
    """Record interruption, not child death. Native UNKNOWN keeps its execution right."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        if index["run_state"] != "RUNNING" or not index["current"]["name"]:
            return {"status": "NOOP", "reason": "run not RUNNING"}
        entry = _catalog_entry(index, index["current"]["name"])
        if entry is None:
            return {"status": "NOOP", "reason": "no current entry"}
        key, d = _self_dispatch(index, entry, index["current"]["visit"])
        if not d or d.get("mode") != "agent" or d.get("state") not in ("ISSUED", "CLAIMED"):
            return {"status": "NOOP", "reason": "no open ticket", "owner": key}
        version = runtime_identity.revision_match(index.get('engine_version', ''))
        native134 = bool(version and int(version[1]) >= 134 and dispatch_scope.enabled(index))
        if native134 and not dispatch_lifecycle.returned(d):
            observation = dict(at=now_iso(), reason=reason, physical_exit='UNVERIFIED')
            d['interruption_observation'] = observation
            _record_ticket_state(store, d, d['state'], interruption_observation=observation)
            index['anomalies_summary'].append(dict(node=key.split('@')[0], code='DISPATCH_LIVENESS_UNKNOWN',
                text='Host interruption does not prove child or tool exit; preserve the original execution right.'))
            _write_index(store, index)
            return dict(status='DISPATCH_LIVENESS_UNKNOWN', owner=key, ticket=d['ticket'], attempt=d['attempt'],
                capability='NO_TRUSTED_CHILD_DOMAIN_EXIT_EVIDENCE', replacement_authorized=False)
        if native134:
            dispatch_lifecycle.verify(store, d)
        index["anomalies_summary"].append({"node": key.split("@")[0], "code": "DISPATCH_ABANDONED",
                                           "text": f"ticket {d['ticket']} (attempt {d['attempt']}) abandoned: {reason}"})
        _record_ticket_state(store, d, "ABANDONED")
        if dispatch_scope.enabled(index) and not native134:
            d['lifecycle'] = 'UNKNOWN'
            d['interruption_observation'] = dict(at=now_iso(), reason=reason, physical_exit='UNVERIFIED')
        _write_index(store, index)
        return {"status": "ABANDONED", "owner": key, "ticket": d["ticket"], "attempt": d["attempt"]}


def native_parent_policy(cache_dir: str | Path, session_id: str) -> str | None:
    """Unqualified host reports cannot supply an authorizing parent-policy token."""
    reported_parent_policy(cache_dir, session_id)  # Preserve receipt-integrity checks, discard the unqualified label.
    return None


def reported_parent_policy(cache_dir: str | Path, session_id: str) -> str | None:
    """Diagnostic-only policy label from existing report records."""
    store = RunStore(cache_dir)
    index = store.read_index()
    program_guard.assert_run_version(index)
    if not dispatch_scope.enabled(index):
        return None
    refs = set()
    for row in index['nodes'].values():
        dispatch = row.get('dispatch') or {}
        for record in [dispatch, *dispatch.get('history', [])]:
            if not dispatch_lifecycle.returned(record):
                continue
            proof = dispatch_lifecycle.verify(store, record)
            if (proof.get('result') or {}).get('session_id') != session_id:
                continue
            ref = (proof.get('call') or {}).get('policy_ref')
            if proof.get('agent_id') and isinstance(ref, str) and re.fullmatch(r'[0-9a-f]{64}', ref):
                refs.add(ref)
    return next(iter(refs)) if len(refs) == 1 else None


def observe_dispatch_start(cache_dir: str | Path, bootstrap_sha: str, *, session_id: str, tool_call_id: str, event_id: str, at: str,
                           resume_agent_id: str | None = None, policy_ref: str | None = None) -> dict:
    """Host-only tool event ingress. No model-facing CLI accepts these authority fields. Record 90 round 4 (B7): on the run
    as the next step will hold it once a program-integrity stop cut off before its index write is installed
    (program_guard.landed_view, read-only): the ticket that stop's pause() abandoned binds no start, as on the run that never
    stopped, and nothing is written for it; a ticket pause() left as it is (round 5, problem 94: the run waits at an engine
    dispatch stop) binds as on the run whose files never changed."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        index = program_guard.landed_view(store, index)
        if not dispatch_scope.enabled(index):
            return dict(status='NOT_APPLICABLE')
        if index.get('run_state') in {'COMPLETED', 'FAILED', 'ABANDONED'}:
            return dict(status='UNBOUND')
        rows = [r['dispatch'] for r in index['nodes'].values() if (r.get('dispatch') or {}).get('scope_root')
                and r['dispatch'].get('bootstrap_sha256') == bootstrap_sha and r['dispatch'].get('state') in {'ISSUED','CLAIMED'}]
        if len(rows) != 1 or not all(isinstance(v, str) and v for v in (session_id,tool_call_id,event_id,at)):
            return dict(status='UNBOUND')
        # The already-written identity gate fences this ticket even before its index lands.
        from . import dispatch_identity
        if dispatch_identity.orphan_stop(store, index):
            return dict(status='UNBOUND')
        d = rows[0]
        target = d.get('resume_executor')
        if target and (target['session_id'] != session_id or target['agent_id'] != resume_agent_id):
            return dict(status='RESUME_EXECUTOR_MISMATCH', ticket=d['ticket'])
        if resume_agent_id and not target:
            return dict(status='UNBOUND')
        if policy_ref is not None and (not isinstance(policy_ref, str) or not re.fullmatch(r'[0-9a-f]{64}', policy_ref)):
            return dict(status='UNBOUND')
        path = store.cache_dir/f"_dispatch_start.{d['ticket']}.json"
        proof = dict(ticket=d['ticket'], trace_id=index['trace_id'], bootstrap_sha256=bootstrap_sha,
                     session_id=session_id, tool_call_id=tool_call_id, event_id=event_id, at=at, source='host_synchronous_agent_event')
        if target:
            proof['resume_agent_id'] = resume_agent_id
        if policy_ref:
            proof['policy_ref'] = policy_ref
        if store.exists_path(path):
            prior = store.read_json(path)
            if any(prior.get(k) != proof[k] for k in ('ticket','trace_id','bootstrap_sha256','session_id','tool_call_id')):
                raise EngineError('DISPATCH_CONCURRENT_EXECUTOR', 'A different Agent already owns this segment.')
            proof = prior
        else:
            store.write_json_once(path, proof)
        return dict(status='START_BOUND', ticket=d['ticket'])


def record_dispatch_resume_failure(cache_dir: str | Path, ticket: str, *, session_id: str,
                                   agent_id: str, tool_call_id: str, event_id: str, at: str) -> dict:
    """Host-only failed SendMessage; no claim of child death or business completion. Record 90 round 5 (B6): on the run as
    the next step will hold it (program_guard.landed_view, read-only, as observe_dispatch_start): a continuation ticket a
    program-integrity stop cut off before its index write abandoned is not bound, as on the run that never stopped."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        index = program_guard.landed_view(store, index)
        refused = dict(status='DELIVERY_FAILURE_UNBOUND')
        if not dispatch_lifecycle.replacement_accounting(index) or index.get('run_state') in {
                'COMPLETED', 'FAILED', 'ABANDONED'} or not all(isinstance(v, str) and v
                    for v in (session_id, agent_id, tool_call_id, event_id, at)):
            return refused
        rows = [r.get('dispatch') or {} for r in index['nodes'].values()
                if (r.get('dispatch') or {}).get('ticket') == ticket]
        if len(rows) != 1:
            return refused
        d = rows[0]
        target = d.get('resume_executor') or {}
        if d.get('state') != 'ISSUED' or d.get('reason') not in {'gate_resume', 'segment_resume'} or d.get('claimed_at') \
                or target.get('session_id') != session_id or target.get('agent_id') != agent_id \
                or any(store.exists_path(store.cache_dir/f'_dispatch_{kind}.{ticket}.json')
                       for kind in ('task', 'task_start', 'return')):
            return refused
        start_path = store.cache_dir/f'_dispatch_start.{ticket}.json'
        start = store.read_json(start_path) if store.exists_path(start_path) else {}
        if any(start.get(k) != v for k, v in dict(source='host_synchronous_agent_event', ticket=ticket,
                trace_id=index['trace_id'], bootstrap_sha256=d['bootstrap_sha256'], session_id=session_id,
                resume_agent_id=agent_id, tool_call_id=tool_call_id).items()) or not start.get('event_id'):
            return refused
        proof = dict(source='host_send_message_failure', ticket=ticket, trace_id=index['trace_id'],
            bootstrap_sha256=d['bootstrap_sha256'], session_id=session_id, agent_id=agent_id,
            tool_call_id=tool_call_id, start_event_id=start['event_id'], event_id=event_id, at=at,
            status='failed', verification_scope='delivery_failure_not_child_exit')
        path = store.cache_dir/f'_dispatch_resume_failure.{ticket}.json'
        if store.exists_path(path):
            return dict(status='DELIVERY_FAILURE_BOUND', ticket=ticket) if store.read_json(path) == proof else refused
        store.write_json_once(path, proof)
        return dict(status='DELIVERY_FAILURE_BOUND', ticket=ticket)


def native_resume_start(cache_dir: str | Path, *, session_id: str, agent_id: str, bootstrap_sha: str) -> dict | None:
    """Recover a bound SendMessage start for a later trusted TaskOutput event."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        if not dispatch_scope.enabled(index) or index.get('run_state') in {'COMPLETED', 'FAILED', 'ABANDONED'}:
            return None
        matches = []
        for row in index.get('nodes', {}).values():
            d = row.get('dispatch') or {}
            if not d.get('scope_root') or d.get('exit_evidence') or d.get('closed_reason') or d.get('bootstrap_sha256') != bootstrap_sha:
                continue
            path = store.cache_dir/f"_dispatch_start.{d['ticket']}.json"
            if not store.exists_path(path):
                continue
            start = store.read_json(path)
            if start.get('ticket') == d['ticket'] and start.get('trace_id') == index['trace_id'] \
                    and start.get('bootstrap_sha256') == bootstrap_sha and start.get('session_id') == session_id \
                    and start.get('resume_agent_id') == agent_id and start.get('tool_call_id'):
                matches.append(dict(ticket=d['ticket'], tool_call_id=start['tool_call_id']))
        return matches[0] if len(matches) == 1 else None


def record_dispatch_task_event(cache_dir: str | Path, *, session_id: str, agent_id: str, tool_call_id: str,
                               event_id: str, at: str, event_type: str, status: str | None = None) -> dict:
    """Host-only SDK bookends, paired with this resumed SendMessage's machine start. Record 90 round 5 (B6): the start
    (task_started) is bound on the run as the next step will hold it (program_guard.landed_view, read-only, as
    observe_dispatch_start); unlike observe_dispatch_start it does not require the ticket to be ISSUED or CLAIMED (only not
    closed), so the SDK start of a ticket a cut-off integrity stop abandoned is bound (TASK_START_BOUND), as on the run
    that never stopped (round 6, B4).
    The terminal event goes on to record_dispatch_return, which records a return as the run that never stopped does."""
    refused = dict(status='RETURN_UNVERIFIED')
    if event_type not in {'task_started', 'task_notification'} or not all(
            isinstance(v, str) and v and len(v) <= 160 for v in (session_id, agent_id, tool_call_id, event_id, at)) \
            or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', agent_id) \
            or (event_type == 'task_started' and status is not None) \
            or (event_type == 'task_notification' and status not in {'completed', 'failed'}):
        return refused
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        if event_type == 'task_started':
            index = program_guard.landed_view(store, index)
        version = runtime_identity.revision_match(index.get('engine_version', ''))
        if not version or int(version[1]) < 135 or not dispatch_scope.enabled(index) \
                or index.get('run_state') in {'COMPLETED', 'FAILED', 'ABANDONED'}:
            return refused
        matches = []
        for node in index['nodes'].values():
            d = node.get('dispatch') or {}
            target = d.get('resume_executor') or {}
            if not d.get('scope_root') or d.get('closed_reason') or target.get('session_id') != session_id \
                    or target.get('agent_id') != agent_id:
                continue
            path = store.cache_dir/f"_dispatch_start.{d['ticket']}.json"
            if store.exists_path(path) and store.read_json(path).get('tool_call_id') == tool_call_id \
                    and dispatch_lifecycle._started_executor(store, index, d):
                matches.append(d)
        if len(matches) != 1:
            return refused
        d = matches[0]
        task_path = store.cache_dir/f"_dispatch_task_start.{d['ticket']}.json"
        binding = dict(source='host_sdk_task_event', ticket=d['ticket'], trace_id=index['trace_id'],
            bootstrap_sha256=d['bootstrap_sha256'], session_id=session_id, agent_id=agent_id,
            tool_call_id=tool_call_id)
        if event_type == 'task_started':
            started = dict(binding, event_id=event_id, at=at)
            if store.exists_path(task_path):
                return dict(status='TASK_START_BOUND') if store.read_json(task_path) == started else refused
            store.write_json_once(task_path, started)
            return dict(status='TASK_START_BOUND', ticket=d['ticket'])
        if not store.exists_path(task_path):
            return refused
        started = store.read_json(task_path)
        if any(started.get(k) != v for k, v in binding.items()) or not started.get('event_id') \
                or started['event_id'] == event_id:
            return refused
        native = dict(source='host_sdk_task_event', session_id=session_id, agent_id=agent_id,
            tool_call_id=tool_call_id, started_event_id=started['event_id'], terminal_event_id=event_id, status=status)
        if d.get('exit_evidence'):
            proof = dispatch_lifecycle.verify(store, d)
            return dict(status='RETURN_ALREADY_OBSERVED', ticket=d['ticket']) \
                if proof.get('native_task_event') == native else refused
        ticket = d['ticket']
    return record_dispatch_return(cache_dir, ticket, session_id=session_id, agent_id=agent_id,
        tool_call_id=tool_call_id, event_id=event_id, at=at, status=status, native_task_event=native)


def record_dispatch_return(cache_dir: str | Path, ticket: str, *, session_id: str, tool_call_id: str, event_id: str, at: str, status: str,
                            agent_id: str | None = None, completion_tool_call_id: str | None = None, observation: dict | None = None,
                            native_task_event: dict | None = None) -> dict:
    """Host-only terminal tool update; bind it to the previously observed synchronous start."""
    store = RunStore(cache_dir)
    path = store.cache_dir/f'_dispatch_start.{ticket}.json'
    if not store.exists_path(path):
        return dict(status='RETURN_UNVERIFIED', ticket=ticket)
    start = store.read_json(path)
    if start.get('ticket') != ticket or start.get('session_id') != session_id or start.get('tool_call_id') != tool_call_id \
            or status not in {'completed','failed'} or not event_id or not at:
        return dict(status='RETURN_UNVERIFIED', ticket=ticket)
    if agent_id is not None and (not isinstance(agent_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', agent_id)):
        return dict(status='RETURN_UNVERIFIED', ticket=ticket)
    if start.get('resume_agent_id') and start['resume_agent_id'] != agent_id:
        return dict(status='RETURN_UNVERIFIED', ticket=ticket)
    if completion_tool_call_id is not None and (not isinstance(completion_tool_call_id, str) or not completion_tool_call_id):
        return dict(status='RETURN_UNVERIFIED', ticket=ticket)
    proof = dict(source='host_agent_tool_return', call=start,
        result=dict(session_id=session_id, tool_call_id=tool_call_id, event_id=event_id, at=at, status=status),
        bootstrap_sha256=start['bootstrap_sha256'], tool_is_error=status == 'failed',
        verification_scope='synchronous_tool_return_not_external_side_effect_completion')
    if agent_id:
        proof['agent_id'] = agent_id
    if completion_tool_call_id:
        proof['result']['completion_tool_call_id'] = completion_tool_call_id
        proof['verification_scope'] = 'native_task_output_terminal_bound_to_send_message'
    if native_task_event is not None:
        keys = {'source', 'session_id', 'agent_id', 'tool_call_id', 'started_event_id', 'terminal_event_id', 'status'}
        if completion_tool_call_id or not isinstance(native_task_event, dict) or set(native_task_event) != keys \
                or any(native_task_event.get(k) != v for k, v in dict(source='host_sdk_task_event',
                    session_id=session_id, agent_id=agent_id, tool_call_id=tool_call_id,
                    terminal_event_id=event_id, status=status).items()) or not native_task_event.get('started_event_id'):
            return dict(status='RETURN_UNVERIFIED', ticket=ticket)
        task_path = store.cache_dir/f'_dispatch_task_start.{ticket}.json'
        task_start = store.read_json(task_path) if store.exists_path(task_path) else {}
        expected = dict(source='host_sdk_task_event', ticket=ticket, trace_id=start['trace_id'],
            bootstrap_sha256=start['bootstrap_sha256'], session_id=session_id, agent_id=agent_id,
            tool_call_id=tool_call_id, event_id=native_task_event['started_event_id'])
        if any(task_start.get(k) != v for k, v in expected.items()):
            return dict(status='RETURN_UNVERIFIED', ticket=ticket)
        proof['native_task_event'] = dict(native_task_event)
        proof['verification_scope'] = 'native_sdk_task_terminal_bound_to_send_message'
    if observation is not None:
        keys = {'classification', 'response_chars', 'response_bytes', 'host_elapsed_ms', 'basis'}
        if not isinstance(observation, dict) or set(observation) != keys or observation['classification'] not in {
            'provider_early_termination', 'tool_terminal'} or observation['basis'] != 'host_tool_event_interval_not_model_or_provider_latency' \
                or any(observation[k] is not None and (type(observation[k]) is not int or observation[k] < 0)
                       for k in ('response_chars', 'response_bytes', 'host_elapsed_ms')):
            return dict(status='RETURN_UNVERIFIED', ticket=ticket)
        proof['observation'] = dict(observation)
    return observe_dispatch_return(cache_dir, ticket, _host_event=proof)


def observe_dispatch_return(cache_dir: str | Path, ticket: str, *, transcript: str | Path | None = None, _host_event=None) -> dict:
    """Bind paired host tool events; local transcripts remain diagnostic only."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        if not dispatch_scope.enabled(index):
            raise EngineError('DISPATCH_RETURN_UNSUPPORTED', 'Return observation requires a node-mode root executor.')
        rows = [(key, segment) for key, row in index['nodes'].items()
                for segment in ([row.get('dispatch') or {}] +
                    ((row.get('dispatch') or {}).get('history', []) if dispatch_lifecycle.pause_continuation(index) else []))
                if segment.get('ticket') == ticket]
        if len(rows) != 1:
            raise EngineError('DISPATCH_TICKET_STALE', 'Observe only this cache current segment; old evidence remains sealed.')
        key, d = rows[0]
        ref = d.get('exit_evidence')
        if ref:
            dispatch_lifecycle.verify(store, d)
            return dict(status='RETURN_ALREADY_OBSERVED', evidence_ref=ref, ticket=ticket,
                        original_session_resume='UNVERIFIED', reason='Stored host reports are diagnostic only.')
        rec = store.read_json(store.dispatch_path(ticket))
        if rec.get('trace_id') != index['trace_id'] or rec.get('bootstrap_sha256') != d.get('bootstrap_sha256') \
                or sha256_bytes(rec['bootstrap'].encode()) != d['bootstrap_sha256']:
            raise EngineError('DISPATCH_TICKET_INVALID', 'Bootstrap binding changed.')
        proof = _host_event
        if proof and (proof.get('source') != 'host_agent_tool_return' or proof.get('bootstrap_sha256') != d['bootstrap_sha256']
                      or proof['call'].get('trace_id') != index['trace_id']):
            raise EngineError('DISPATCH_RETURN_INVALID', 'Host event does not bind this segment.')
        if not proof:
            start_path = store.cache_dir/f'_dispatch_start.{ticket}.json'
            start = store.read_json(start_path) if start_path.exists() else {}
            observation = dispatch_lifecycle.receipt(d['bootstrap_sha256'], transcript,
                session_id=start.get('session_id'), workspace=_read_run_input(store).get('acp_workspace'))
            return dict(status='RETURN_UNVERIFIED', ticket=ticket, lifecycle='UNKNOWN',
                original_session_resume='UNVERIFIED', local_observation=observation,
                reason='Local logs are diagnostic only. A host synchronous tool return bound to its start is required.')
        proof.update(ticket=ticket, trace_id=index['trace_id'], scope_root=d['scope_root'])
        path = f'_dispatch_return.{ticket}.json'
        if store.exists_path(store.cache_dir/path):
            saved = store.read_json(store.cache_dir/path)
            if 'public_artifacts' in saved:
                proof['public_artifacts'] = saved['public_artifacts']
            if {k:v for k,v in saved.items() if k != 'observed_at'} != proof:
                raise EngineError('DISPATCH_RETURN_EVIDENCE_CHANGED', 'An unindexed receipt exists; recover it without overwriting.')
            proof = saved
        else:
            from . import dispatch_public_blocks
            proof['public_artifacts'] = dispatch_public_blocks.seal_return(store, index, d)
            proof['observed_at'] = now_iso()
            store.write_json_once(store.cache_dir/path, proof)
        ref = dict(path=path, sha256=sha256_bytes(json.dumps(proof, ensure_ascii=False, sort_keys=True).encode()))
        _record_ticket_state(store, d, d['state'] if d.get('paused_at') or d['state'] == 'COMMITTED' else 'ABANDONED',
                             lifecycle='RETURNED', exit_evidence=ref)
        if d.get('resume_executor'):
            _record_ticket_state(store, d, d['state'], context_resume='ORIGINAL_SESSION_RESUME_OBSERVED')
        _write_index(store, index)
        return dict(status='RETURN_OBSERVED', ticket=ticket, evidence_ref=ref, lifecycle='RETURNED',
                    original_session_resume='UNVERIFIED',
                    reason='Host reports are diagnostic only; no native identity source is qualified.')


def _unshown_dispatch_gate_ref(store, index, d) -> str | None:
    """Decision 193, problem 98: identify the one unpublished business-menu reference without publishing it.

    Return sealing may omit this menu from its separate plan/node/pause artifact proof only when the current paused
    commit binds it to this ticket. A host return never writes a menu or marks delivery. The main next-node alone
    publishes the child's gate through _show_unshown_gate; unrelated or unbound missing references remain invalid.
    """
    try:
        gate = index.get('gate') or {}
        qid = gate.get('question_id')
        if index.get('run_state') != 'WAITING_USER' or gate.get('state') != 'WAITING_USER' or not qid or not d.get('paused_at'):
            return
        rec = store.read_json(store.gate_path(qid))
        if rec.get('program_drift') or rec.get('dispatch_block') or not _unshown_stop(store, index, rec):
            return
        name = f"menu.{qid}.txt"
        if _menu_ref(store, name, render.menu_block(rec, user_language=index.get("user_language"))) not in (d.get('public_refs') or []):
            return
        entry = _catalog_entry(index, rec['node'])
        cache = store.read_json(_cache_path_for(store, index, entry, rec['visit'])) if entry else {}
        machine = ((cache.get('continuations') or [cache])[-1] if cache else {}).get('machine') or {}
        if machine.get('paused_gate') != qid or (machine.get('dispatch') or {}).get('ticket') != d.get('ticket') \
                or (machine.get('dispatch') or {}).get('actor') != 'sub_agent':
            return
        return _menu_ref(store, name, render.menu_block(rec, user_language=index.get("user_language")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RunStoreError, EngineError):
        return


def _claim_ticket(store: RunStore, index: dict, entry: dict, visit: int, agent_ticket: str) -> tuple[dict, bool]:
    """next-node --agent-ticket: bind the calling sub-agent to the occurrence's ticket. Returns (dispatch, claimed_now)."""
    key, d = _self_dispatch(index, entry, visit)
    if d is None or d.get("mode") != "agent" or d.get("ticket") != agent_ticket:
        raise _ticket_error(index, key, agent_ticket, d if d and d.get("mode") == "agent" else None)
    if d.get('review_binding'):
        from . import blind_review
        blind_review.load(store, d['review_binding'])
    if d.get('input_binding'):
        from . import independent_inputs
        independent_inputs.load(store, d['input_binding'])
    if d["state"] == "ISSUED":
        if d.get('identity_handoff'):
            from . import dispatch_identity
            dispatch_identity.verify_ticket(store, index, d)
        if dispatch_budget.replacement(index, d):
            if d.get('reason') == 'human_replacement':   # docs/05SoulRun 87: checked once, counted as a replacement
                dispatch_lifecycle.verify_human_replacement(store, index, d)
            else:
                dispatch_lifecycle.verify_handoff(store, index, d)
        if d.get('resume_executor'):
            target = d['resume_executor']
            path = store.cache_dir/f"_dispatch_start.{d['ticket']}.json"
            start = store.read_json(path) if path.exists() else {}
            if start.get('bootstrap_sha256') != d['bootstrap_sha256'] or start.get('session_id') != target['session_id'] \
                    or start.get('resume_agent_id') != target['agent_id'] or start.get('trace_id') != index['trace_id']:
                raise EngineError('ORIGINAL_EXECUTOR_START_UNVERIFIED', 'A bound native resume start is required before claiming.')
        pool = d.get('pool', 'ordinary')
        # Review of docs/05SoulRun 87 (S1): a human-chosen replacement of a part never charged is that part's task claim.
        if not dispatch_budget.available(index, pool, d, claim=True):
            raise EngineError('DISPATCH_BUDGET_EXHAUSTED', 'Claim refused without consuming the ticket; main agent must resolve dispatch.')
        now = now_iso()
        _record_ticket_state(store, d, "CLAIMED", claimed_at=now, actor="sub_agent")
        if dispatch_scope.enabled(index):
            dispatch_lifecycle.progress(store, d, now)
        _dispatch_group(index)["spawns_claimed"] += 1
        if dispatch_budget.ordinary_resume(index, d):
            group = _dispatch_group(index)
            group['ordinary_resumes_claimed'] = group.get('ordinary_resumes_claimed', 0) + 1
        if dispatch_budget.replacement(index, d, claim=True):
            group = _dispatch_group(index)
            counter = f'{pool}_replacements_claimed'
            group[counter] = group.get(counter, 0) + 1
        if pool == 'independent':
            group = _dispatch_group(index)
            group['independent_claimed'] = group.get('independent_claimed', 0) + 1
            if dispatch_budget.independent_resume(index, d):
                group['independent_resumes_claimed'] = group.get('independent_resumes_claimed', 0) + 1
        return d, True
    if d["state"] == "CLAIMED":
        if d.get('identity_handoff'):
            from . import dispatch_identity
            dispatch_identity.verify_ticket(store, index, d)
        if d.get('paused_at'):
            raise EngineError('DISPATCH_TICKET_STALE', 'Paused ticket is closed to this executor; the main agent must resolve continuation.', field='agent_ticket')
        dispatch_lifecycle.progress(store, d, now_iso())
        return d, False
    raise EngineError("DISPATCH_TICKET_STALE", f"ticket {agent_ticket} is {d['state']}", field="agent_ticket", expected="an ISSUED or CLAIMED ticket")


def _check_dispatch_for_commit(index: dict, program, entry: dict, visit: int, payload: dict, agent_ticket: str | None, *, store) -> dict | None:
    """The executor gate of node-commit (doc 10 §3.2/§3.3, doc 12 §1.5: per node). Returns the machine `dispatch` block
    (None for plain inline nodes). Mutates nothing; the index transition happens in _apply_dispatch_commit after the writes."""
    key, d = _self_dispatch(index, entry, visit)
    if d and d.get("mode") != "agent":   # a declared-agent node that runs inline (downgrade record): no ticket rules apply
        d = None
    if agent_ticket:
        if d is None or d.get("ticket") != agent_ticket:
            raise _ticket_error(index, key, agent_ticket, d)
        if d.get('identity_handoff'):
            from . import dispatch_identity
            dispatch_identity.verify_ticket(store, index, d)
        if (d.get('human_replacement') or {}).get('previous_ticket') == agent_ticket:   # docs/05SoulRun 87: the human chose its replacement
            raise _ticket_error(index, key, agent_ticket, None)
        if d.get('paused_at') or d["state"] != "CLAIMED":
            raise EngineError("DISPATCH_TICKET_INVALID", f"ticket {agent_ticket} is {d['state']}: claim it with next-node --agent-ticket first",
                              field="agent_ticket", expected="a CLAIMED ticket")
        return {"actor": "sub_agent", "ticket": agent_ticket, "fallback": None,
                **({'scope_root': dict(d['scope_root'])} if d.get('scope_root') else {})}
    if d is None:
        if _should_dispatch(index, program, entry):   # never served: the main agent skipped next-node
            raise EngineError("DISPATCH_REQUIRED", f"node {key} runs in a sub-agent; call next-node to obtain its bootstrap", field="agent_ticket",
                              expected="next-node, then node-commit --agent-ticket by the spawned sub-agent")
        return None
    if d.get('scope_root') and d['state'] in ('EXHAUSTED', 'FALLBACK'):
        raise EngineError('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE',
                          'Unqualified reports or exhausted tickets cannot authorize main-agent takeover; obtain a human handover.')
    if d["state"] in ("ISSUED", "CLAIMED", "ABANDONED"):
        raise EngineError("DISPATCH_REQUIRED", f"node {key} is dispatched to a sub-agent (ticket {d['ticket']}, {d['state']})", field="agent_ticket",
                          expected="node-commit --agent-ticket by the spawned sub-agent")
    if d["state"] == "EXHAUSTED":
        if d.get('pool') == 'independent':
            raise EngineError('INDEPENDENT_DISPATCH_UNAVAILABLE', 'Independent nodes cannot commit inline.')
        fb = payload.get("dispatch_fallback")
        if d.get('scope_root') and dispatch_lifecycle.returned(d):
            if not isinstance(fb, dict) or not fb.get('reason') or fb.get('exhaustion_ticket') != d['ticket']:
                raise EngineError('SPAWN_NOT_ATTEMPTED', 'Use the confirmed returned machine ticket.', field='dispatch_fallback.exhaustion_ticket')
            return dict(actor='main_agent', ticket=d['ticket'], fallback=dict(reason=fb['reason'],
                        spawn_failure_evidence=None, exhaustion_ticket=d['ticket']))
        if d.get('downgrade') == 'SPAWN_BUDGET_EXHAUSTED' and isinstance(fb, dict) and fb.get('reason'):
            supplied = fb.get('exhaustion_ticket')
            # Older inputs carried a text field; retain compatibility without asserting an Agent failure.
            if supplied == d['ticket'] or (supplied is None and fb.get('spawn_failure_evidence')):
                return dict(actor='main_agent', ticket=d['ticket'], fallback=dict(reason=fb['reason'],
                    spawn_failure_evidence=None, exhaustion_ticket=d['ticket']))
            raise EngineError('SPAWN_NOT_ATTEMPTED', 'Use the actual exhausted machine ticket, not an Agent error.',
                              field='dispatch_fallback.exhaustion_ticket', expected=d['ticket'])
        if not isinstance(fb, dict) or not fb.get("reason") or not fb.get("spawn_failure_evidence"):
            raise EngineError("SPAWN_NOT_ATTEMPTED", "dispatch exhausted: inline commit needs dispatch_fallback evidence", field="dispatch_fallback",
                              expected="{reason, spawn_failure_evidence}", example=_EXAMPLES["dispatch_fallback"])
        return {"actor": "main_agent", "ticket": d["ticket"], "fallback": {"reason": fb["reason"], "spawn_failure_evidence": fb["spawn_failure_evidence"]}}
    if d["state"] == "FALLBACK":
        return {"actor": "main_agent", "ticket": d["ticket"], "fallback": d.get("fallback")}
    return {"actor": "main_agent", "ticket": d.get("ticket"), "fallback": None}


def _apply_dispatch_commit(store: RunStore, index: dict, entry: dict, visit: int, machine_dispatch: dict | None, *, paused: bool, at=None) -> dict | None:
    """Index transition of the node's ticket after its commit or pause; returns the `dispatch` object of the commit result."""
    if not machine_dispatch:
        return None
    key, d = _self_dispatch(index, entry, visit)
    if d is None or d.get("mode") != "agent":
        return None
    now = at or now_iso()
    dispatch_lifecycle.progress(store, d, now, preserve_equal=bool(at))
    if machine_dispatch.get("fallback") and d["state"] == "EXHAUSTED":
        _dispatch_group(index)["fallbacks"] += 1
        index["anomalies_summary"].append({"node": entry["name"], "code": "AGENT_FALLBACK_INLINE",
                                           "text": f"dispatch exhausted after {d['attempt']} attempt(s); executed inline by the main agent: {machine_dispatch['fallback']['reason']}"})
        _record_ticket_state(store, d, "FALLBACK", actor="main_agent", fallback=machine_dispatch["fallback"])
    if paused:
        _record_ticket_state(store, d, d["state"], paused_at=now, preserve_equal=bool(at))
        return {"ticket": d["ticket"], "actor": machine_dispatch["actor"], "closed": True, "reason": "gate",
                **(dispatch_scope.view(d) if d.get('scope_root') else {})}
    if d.get('scope_root') and d['scope_root'] != dict(node=entry['name'], visit=visit):
        return dict(ticket=d['ticket'], actor=machine_dispatch['actor'], closed=False, reason='subtree_progress', **dispatch_scope.view(d, include_refs=False))
    if d["state"] == "CLAIMED" or (d.get('scope_root') and d['state'] == 'FALLBACK'):
        _record_ticket_state(store, d, "COMMITTED", committed_at=now, actor=machine_dispatch["actor"], preserve_equal=bool(at))
    else:
        d["committed_at"] = now
    return {"ticket": d["ticket"], "actor": machine_dispatch["actor"], "closed": True, "reason": "committed",
            **(dispatch_scope.view(d) if d.get('scope_root') else {})}


def _read_run_input(store: RunStore) -> dict:
    data = store.read_json(store.cache_dir / RUN_INPUT)
    if 'program_binding_policy' not in data:
        version = str(store.read_index().get('engine_version', ''))
        match = runtime_identity.revision_match(version)
        if match and int(match[1]) >= 119:
            data['program_binding_policy'] = 1  # missing new-run authority never becomes legacy
    return data


def _write_run_input(store: RunStore, data: dict) -> None:
    atomic_write_bytes(store.cache_dir / RUN_INPUT, dumps(data).encode("utf-8"))


def _write_json(path: Path, obj) -> str:
    return atomic_write_bytes(path, dumps(obj).encode("utf-8"))


def _load_routed_program(run_input: dict) -> program_loader.Program | None:
    routed = run_input.get("routed")
    return _load_bound_program(run_input, routed) if routed else None


def _load_bound_program(run_input, target):
    if not isinstance(target, dict) or not target.get('dir') or not target.get('entry_file'):
        raise EngineError('PROGRAM_INVALID', 'no bound program identity is available')
    binding = None
    if run_input.get('program_binding_policy'):
        key = str((Path(target['dir']) / target['entry_file']).resolve())
        bindings = run_input.get('program_bindings')
        binding = (bindings.get(key) if isinstance(bindings, dict) else None) or {}
    try:
        program = program_loader.load_program(target['dir'], target['entry_file'], binding=binding)
        routed = run_input.get('routed') or {}
        if (routed.get('dir'), routed.get('entry_file')) == (target['dir'], target['entry_file']) \
                and routed.get('execution_loading_mode') in {'node', 'normal'}:
            program.runtime_loading_mode = routed['execution_loading_mode']
        return program
    except program_loader.ProgramError as exc:
        error = EngineError(exc.code, exc.detail, field='program',
                            expected='original bound program bytes; call next-node to present the integrity gate' if exc.code == 'PROGRAM_DRIFT_DETECTED'
                            else 'a valid program; repair separately before starting a fresh run')
        error.changes = getattr(exc, 'changes', [])
        error.binding_target = dict(dir=target['dir'], entry_file=target['entry_file'])
        raise error from exc


def _program_name(index: dict) -> str:
    return index["program"].get("name") or "engine"


def _budget_for(kind: str, program: program_loader.Program | None) -> dict:
    """Per-node active budget. AIAP §19 runtime.timeout_seconds is a whole-execution limit, so it is
    reported as a run-level advisory at Router.summary (RUN_TIMEOUT_ADVISORY), never as a node budget."""
    return {"source": "engine_default", "active_ms": BUDGET_DEFAULT_MS.get(kind, BUDGET_DEFAULT_MS["business"])}


def _program_timeout_ms(program: program_loader.Program | None) -> int | None:
    rt = program.runtime if program else None
    if rt and isinstance(rt.get("timeout_seconds"), (int, float)) and not isinstance(rt.get("timeout_seconds"), bool) and rt["timeout_seconds"] > 0:
        return int(rt["timeout_seconds"] * 1000)
    return None


def _flag(v):
    if v is False:
        return False
    if isinstance(v, dict):
        return bool(v.get("allowed"))
    return None


def _permission_for(program: program_loader.Program | None, sys_name: str | None) -> str:
    """R-24 sys.* permission pre-check: allowed / denied / undeclared."""
    if not sys_name:
        return "undeclared"
    perms = program.permissions if program else None
    if not perms:
        return "undeclared"
    if sys_name.startswith("sys.run"):
        f = _flag(perms.get("shell"))
    elif sys_name.startswith("sys.llm"):
        f = _flag(perms.get("network"))
    elif sys_name.startswith("sys.code"):
        f = _flag(perms.get("code_execution"))
    elif sys_name in ("sys.io.read", "sys.io.write"):
        fs = perms.get("file_system")
        if not isinstance(fs, dict):
            return "undeclared"
        need = "read" if sys_name.endswith("read") else "write"
        return "allowed" if need in (fs.get("operations") or []) else "denied"
    else:
        return "allowed"
    return "undeclared" if f is None else ("allowed" if f else "denied")


def _tool_permission(program: program_loader.Program | None, tool: str, sys_call: str | None) -> str:
    if sys_call:
        return _permission_for(program, sys_call)
    t = (tool or "").lower()
    if t in ("bash", "shell", "powershell", "cmd", "subprocess"):
        return _permission_for(program, "sys.run")
    if t in ("websearch", "webfetch", "web_search", "web_fetch", "fetch", "http", "curl"):
        perms = program.permissions if program else None
        f = _flag(perms.get("network")) if perms else None
        return "undeclared" if f is None else ("allowed" if f else "denied")
    return "allowed"


def _timing_text(text: str) -> str:
    """docs/05SoulRun 90 (problem 41): a text with its line breaks as '\\n' - '\\r\\n' and a lone '\\r' are line breaks too."""
    return text.replace("\r\n", "\n").replace("\r", "\n") if "\r" in text else text


def _timing_mask(m: re.Match) -> str:
    code = m.group(1) or m.group(2)
    if code:
        value = int(code, 10 if m.group(1) else 16)
        if value <= 0x10FFFF and _TIMING_DIGIT_RE.fullmatch(chr(value)):
            return "0" + "x" * (len(m.group(0)) - 1)     # an entity that encodes a digit is one digit, at its '&'
    markup = m.group(0)
    if markup[0] != "<":
        return _TIMING_DIGIT_RE.sub("x", markup)
    name = _TIMING_TAG_NAME_RE.match(markup).end()      # a tag: the digits of its name and of the entities in it are no values
    return _TIMING_DIGIT_RE.sub("x", markup[:name]) + _TIMING_ENTITY_MARK_RE.sub(_timing_mask, markup[name:])


def _timing_masked(text: str) -> str:
    """docs/05SoulRun 90 (problem 41): `text` with the digits of HTML tag names and entities hidden (same length): no values."""
    return _TIMING_MARKUP_RE.sub(_timing_mask, text) if "<" in text or "&" in text else text


def _timing_digit(text: str) -> bool:
    return bool(_TIMING_DIGIT_RE.search(_timing_masked(text)))


def _timing_rstrip(line: str) -> str:
    return line[:len(line) - _TIMING_TRAILING_RE.match(line[::-1]).end()]


def _timing_clause_goes_on(text: str, t: int, field_end: int) -> bool:
    """docs/05SoulRun 90 (problem 41): whether the '.', '!', '?' or ';' at `t` leaves the clause of the field ending at `field_end`
    open - a '.' ending an abbreviation ('etc.' only when no capital or CJK letter starts a new sentence after it), a ';' ending an
    HTML entity, or a terminator inside a parenthesis of up to 40 characters that closes on the line (opened before the field or
    after it). Each test looks at a bounded window, and the blank run after 'etc.' is read once."""
    if text[t] == ".":
        word = _TIMING_ABBREVIATION_RE.search(text, max(0, t - 8), t)
        if word:
            if word.group(1).lower() != "etc":
                return True
            nxt = _TIMING_NEXT_WORD_RE.match(text, t + 1)
            c = nxt.group(1) if nxt else ""
            return not (c.isupper() or any(low <= c <= high for low, high in _TIMING_CJK))
    if text[t] == ";" and _TIMING_ENTITY_RE.search(text, max(0, t - 12), t):
        return True
    lo = max(0, t - 41)
    opening = max(text.rfind("(", lo, t), text.rfind("（", lo, t))   # the only parenthesis that can hold it (no nesting)
    aside = _TIMING_ASIDE_RE.match(text, opening) if opening >= 0 else None
    return bool(aside) and t < aside.end() - 1


def _timing_label(line: str, field_end: int) -> bool:
    """docs/05SoulRun 90 (problem 41): a label line - with trailing blanks, markup and HTML tags aside, and a '#' comment that
    starts after the separator following the field (at `field_end`) - ends with : ： = ＝ (also as an HTML entity), an opening { or
    [, 'approx.' (or appr., apx., ca., circa., abt., est.) or a YAML block indicator after a separator (| > |- >- |+ >+); or it holds
    only the field (a heading mark, quote marks, a bullet, an ordered-list number or markup allowed). The line is also a label when
    it is one once cut at a '#' comment that starts after the field and before its first separator (or with none, anywhere after
    the field): round 6 adds that reading to round 4's instead of replacing it (va 1 defect 6, va 2 defect 2)."""
    sep = _TIMING_SEPARATOR_RE.search(line, field_end)
    after = _TIMING_COMMENT_RE.search(line, sep.end()) if sep else None
    before = _TIMING_COMMENT_RE.search(line, field_end, sep.start() if sep else len(line))
    for rest in (line[:after.start()] if after else line, line[:before.start()] if before else None):
        if rest is None:
            continue
        rest = rest[:len(rest) - _TIMING_TAIL_RE.match(rest[::-1]).end()]   # read from the end: trailing blanks, markup and tags
        if _TIMING_LABEL_END_RE.search(rest) or _TIMING_FIELD_LINE_RE.fullmatch(rest):
            return True
    return False


def _timing_last(line: str) -> str:
    """The last character of `line` with trailing blanks, markup, closing brackets and quotes, a footnote mark ([1], [^2]), HTML
    tags, &nbsp;, symbols and emoji, a trailing backslash and a code span holding no _ aside (read once from the end), or '' - the
    line ends a sentence when it is one of 。．.!?！？；;…"""
    reverse = line[::-1]
    tail = _TIMING_CAPTION_TAIL_RE.match(reverse).end()
    return reverse[tail] if tail < len(reverse) else ""


def _timing_sentence_end(line: str) -> bool:
    last = _timing_last(line)
    return last != "" and last in _TIMING_CAPTION_END


def _timing_title_row(line: str) -> tuple[str | None, int]:
    """A table row whose one non-empty cell names a field (a '|' row, or an HTML row: the cell's tags aside) - (that cell's text,
    else None; the row's number of cells): a title row over the table below it (va 1 defect 4); a row of two cells or more is one
    only when it does not lie inside its table (round 7: _timing_row_inside)."""
    if "|" in line:
        cells = _table_cells(line)
        named = [cell for cell in cells if cell.strip()]
    elif "<" in line and _TIMING_HTML_CELL_RE.search(line):
        cells = _TIMING_HTML_CELL_RE.split(line)[1:]
        named = [text for cell in cells if (text := _TIMING_TAG_RE.sub("", cell).strip())]
    else:
        return None, 0
    return (named[0] if len(named) == 1 and _TIMING_FIELD_RE.search(named[0]) else None), len(cells)


def _timing_table_start(text: str, line_start: int, line_end: int) -> bool:
    """docs/05SoulRun 90 (problem 41, round 7: line-A-41_1 defect 4): whether the table row [line_start, line_end) heads or starts
    its table - the next line is a Markdown delimiter row (|---|), or the line above it is no row of a table: for a '|' row a line
    without |, for an HTML row a line without a row or cell tag (<tr> <td> <th>, their end tags too), after at most three lines
    that are other HTML table tags (<table>, <thead>, <tbody>). A row inside a table - '| started_at | |' below '|---|', a field
    left empty - is no title row: only rule (4) reads it. Reads at most five lines."""
    if line_end < len(text):
        below = _timing_line(text, line_end + 1)[0]
        if "|" in below and "-" in below and _TIMING_DELIMITER_RE.fullmatch(below):
            return True
    pipe = "|" in text[line_start:line_end]
    pos = line_start
    for _ in range(4):
        if pos == 0:
            return True
        above_start = text.rfind("\n", 0, pos - 1) + 1
        above = text[above_start:pos - 1]
        if pipe:
            return "|" not in above
        if _TIMING_HTML_ROW_TAG_RE.search(above):
            return False
        if not _TIMING_TABLE_ROW_RE.match(above):
            return True
        pos = above_start
    return True


def _timing_row_inside(text: str, line_start: int, line_end: int) -> bool:
    """docs/05SoulRun 90 (problem 41, round 7): whether the table row [line_start, line_end) lies inside its table - it neither
    heads nor starts it (_timing_table_start) and the next line is a row of it too (it holds | for a '|' row; for an HTML row a
    row or cell tag). A row at the table's end is read as a title row, as round 6 read every such row."""
    if line_end >= len(text) or _timing_table_start(text, line_start, line_end):
        return False
    below = _timing_line(text, line_end + 1)[0]
    return "|" in below if "|" in text[line_start:line_end] else bool(_TIMING_HTML_ROW_TAG_RE.search(below))


def _timing_row_in_table(text: str, line_start: int, line_end: int) -> bool:
    """A table row of two cells or more whose one non-empty cell names a field (_timing_title_row) and that lies inside its table
    (_timing_row_inside): it leaves the field's cell empty ('| started_at | |' or '<tr><td>started_at</td><td></td></tr>'
    between a table's header row and its next row) - no heading, label or caption; rule (4) reads its cells (round 7,
    line-A-41_1 defect 4). A '|' row starts with | here (a YAML block indicator 'started_at: |' is no row)."""
    line = text[line_start:line_end]
    if not (_TIMING_TABLE_ROW_RE.match(line) or line.lstrip().startswith("|")):
        return False
    title, cells = _timing_title_row(line)
    return title is not None and cells >= 2 and _timing_row_inside(text, line_start, line_end)


def _timing_caption(line: str, start: bool = True) -> bool:
    """docs/05SoulRun 90 (problem 41, decision 185): a line naming a field is a caption unless it ends a sentence
    (_timing_sentence_end) or is a table row (it holds | or starts with an HTML table tag other than <caption>; rule (4) reads tables
    by their columns) - except a title row, whose one non-empty cell names the field and ends no sentence, unless it lies inside
    its table (`start`: not _timing_row_inside; a one-line value does). Linear."""
    if "|" in line or _TIMING_TABLE_ROW_RE.match(line):
        line = (_timing_title_row(line)[0] if start else None) or ""
    last = _timing_last(line)
    return last != "" and last not in _TIMING_CAPTION_END


def _timing_clause(line: str, start: int) -> bool:
    """docs/05SoulRun 90 (problem 41, decisions 186 and 187): whether the caption `line`, whose first field starts at `start`, reads
    as a clause - at least four words before the field (a word: a run between blanks holding a letter or digit other than CJK;
    three CJK characters count as two words; words inside a closed bracket count) and no bracket opened before the field still
    open at it - so that a line below it that starts with a digit is no claim and is not carried over (decision 183's example:
    'The program asks each node to report started_at' over '1. Router.match chose mini' or '2 nodes were sent back'; decision 187
    (b): any other line is carried over as below a caption). The words are counted from the field back, each token once, until four
    are reached: linear."""
    head = line[:start]
    if max(head.rfind(c) for c in "(（[［") > max(head.rfind(c) for c in ")）]］"):
        return False
    units = 0
    for token in reversed(head.split()):   # counted from the field back, in thirds of a word
        units += 2 * (len(token) - len(_TIMING_CJK_CHAR_RE.sub("", token))) + (3 if _TIMING_WORD_CHAR_RE.search(token) else 0)
        if units >= _TIMING_CLAUSE_UNITS:
            return True
    return False


def _timing_csv_cells(line: str, sep: str) -> list[str]:
    """docs/05SoulRun 90 (problem 41): a CSV/TSV line's cells - a cell that starts (after spaces) with '"' runs to its closing quote
    ('""' inside is one quote), so it may hold the separator; an unclosed quote runs to the line end. One pass: linear."""
    cells, i, n = [], 0, len(line)
    while True:
        j = i
        while j < n and line[j] == " ":
            j += 1
        if j < n and line[j] == '"':
            k, parts = j + 1, []
            while True:
                q = line.find('"', k)
                if q < 0:
                    parts.append(line[k:])
                    k = n
                    break
                parts.append(line[k:q])
                if line.startswith('"', q + 1):
                    parts.append('"')
                    k = q + 2
                    continue
                k = q + 1
                break
            s = line.find(sep, k)
            s = n if s < 0 else s
            cells.append("".join(parts) + line[k:s])
        else:
            s = line.find(sep, i)
            s = n if s < 0 else s
            cells.append(line[i:s])
        if s >= n:
            return cells
        i = s + 1


def _timing_row_cells(line: str, kind: str, sep: str | None) -> list[str] | None:
    """A line's cells for the separated-row rule: HTML cells - each from its <td> or <th> tag on, so that the tag's attribute
    values are the cell's text (va 1 defect 7) - '|', or a CSV/TSV separator (quotes as in CSV); None without it."""
    if kind == "html":
        return _TIMING_HTML_SPLIT_RE.split(line) if "<" in line and _TIMING_HTML_CELL_RE.search(line) else None
    if sep not in line:
        return None
    return line.split(sep) if kind == "pipe" else _timing_csv_cells(line, sep)


def _timing_header_cell(cell: str) -> bool:
    """A CSV/TSV header cell that reads as a short name: with quotes, markup and blanks at both ends and a unit in brackets (up to
    12 characters) at its end aside, nothing, or a name of at most 40 characters and three words without quotes or brackets.
    Each end is stripped once (no backtracking: linear on long blank or markup runs)."""
    core = cell.strip(_TIMING_MARK_CHARS)
    if core[-1:] in (")", "]", "）"):
        opening = max(core.rfind(c, max(0, len(core) - 14), len(core) - 1) for c in "([（")
        if opening >= 0 and not _TIMING_BRACKETS_RE.search(core, opening + 1, len(core) - 1):
            core = core[:opening].rstrip(_TIMING_MARK_CHARS)
    return not core or (len(core) <= 40 and not _TIMING_NAME_STOP_RE.search(core) and len(core.split(None, 3)) <= 3)


def _timing_header_like(cells: list[str]) -> bool:
    """Every cell of a CSV/TSV line is the field itself or reads as a short header name (_timing_header_cell)."""
    return all(_TIMING_FIELD_CELL_RE.fullmatch(cell) or _timing_header_cell(cell) for cell in cells)


def _timing_row_header(cells: list[str], kind: str) -> tuple[dict[int, str], bool]:
    """The columns a header line gives a timing field and whether every digit in them counts: a cell naming it (HTML, '|'); a
    CSV/TSV cell that is the field itself. A CSV/TSV line where a cell names a field among other words, and which does not read as
    a header line (_timing_header_like), is prose with commas: only a cell that starts with a digit counts in its columns."""
    if kind in ("html", "pipe"):
        return {k: m.group(1) for k, cell in enumerate(cells) if (m := _TIMING_FIELD_RE.search(cell))}, True
    columns = {k: _TIMING_FIELD_RE.search(cell).group(1) for k, cell in enumerate(cells) if _TIMING_FIELD_CELL_RE.fullmatch(cell)}
    if not columns:
        return columns, True
    prose = (any(_TIMING_FIELD_RE.search(cell) and not _TIMING_FIELD_CELL_RE.fullmatch(cell) for cell in cells)
             and not _timing_header_like(cells))
    return columns, not prose


def _timing_line(text: str, pos: int) -> tuple[str, int]:
    end = text.find("\n", pos)
    end = len(text) if end < 0 else end
    return text[pos:end], end


def _timing_bracket_end(text: str, pos: int) -> int:
    """The end of the { or [ at `pos`: after its matching bracket (all kinds counted), at a blank line, or the text's end."""
    depth = 0
    for b in _TIMING_BRACKET_RE.finditer(text, pos):
        if text[b.start()] == "\n":
            return b.start()
        depth += 1 if text[b.start()] in "{[" else -1
        if depth == 0:
            return b.end()
    return len(text)


def _timing_value_tail(mline: str, d: int) -> tuple[bool, int, bool]:
    """docs/05SoulRun 90 (problem 41, rounds 6 and 7): what follows the value starting at `d` in the masked line `mline`, up to
    the next pair or note (_TIMING_ROW_STOP_RE) - (whether it reads as a value, the length of its whole-number part, whether a time
    unit follows it). A value: a time unit right after it (glued, 1200ms, or the next word, 1200 毫秒), whatever follows it ('Start
    1200 毫秒用于读取请求': line-A-41_1 defect 6); else at most one word (sentence marks and markup aside), no run of five CJK
    characters ('共 2 个节点被退回' is prose), and not one word on a line that ends a sentence (round 7, line-A-41_1 defect 2:
    '路由重试了 2 次。' and 'Router.match retried 2 times.' are prose; decision 187 (c): 'Start 1200.', 'Start took 1200 ms.' and
    '路由 1200 毫秒。' are values). Reads the line a bounded number of times."""
    value = _TIMING_VALUE_RE.match(mline, d).group(0)
    number = _TIMING_NUMBER_RE.match(value).end()
    rest = mline[d + len(value):]
    stop = _TIMING_ROW_STOP_RE.search(rest)
    rest = rest[:stop.start()] if stop else rest
    tail = rest.split(None, 2)
    whole = len(value) - len(value.lstrip("0123456789０１２３４５６７８９"))
    glued, after = value[number:].rstrip("."), tail[0].rstrip(_TIMING_WORD_MARKS) if tail else ""
    if (_TIMING_ROW_UNIT_RE.fullmatch(glued) or _TIMING_CJK_UNIT_RE.match(glued)
            or _TIMING_ROW_UNIT_RE.fullmatch(after) or _TIMING_CJK_UNIT_RE.match(after)):
        return True, whole, True
    words = sum(1 for word in tail if word.strip(_TIMING_WORD_MARKS))
    return words <= 1 and not _TIMING_CJK_RUN_RE.search(rest) and not (words and _timing_sentence_end(mline)), whole, False


def _timing_row_number(mline: str) -> int | None:
    """docs/05SoulRun 90 (problem 41, decisions 185 to 187): where the number of a 'name number' row starts, or None. The name:
    one or two words, or three when the value's whole part has two digits or more or a unit follows it (Router match step 1200,
    Start ran for 1200 ms - not Router.match chose Opus 5.5) - words counted between blanks, a CJK run as one word - at most 40
    characters, starting with a letter, without , ; ， ； 、 and not ending a sentence (indentation, quote marks, HTML tags and
    markup around it aside). Between it and the number: blanks, an arrow, a dash, = : ~ ≈, an opening bracket ( [ （, a comma, or
    leaders (.. … ··). Then the line's first digit, and what follows its value reads as a value (_timing_value_tail).
    ('Start 1200 ms', 'Start (1200 ms)', 'Start ........ 1200 ms ok', 'Router.match 1200 毫秒', '路由 1200 毫秒。')"""
    d = _TIMING_DIGIT_RE.search(mline)
    if not d:
        return None
    head = mline[:d.start()]
    between = _TIMING_ROW_SEP_RE.match(head[::-1])
    if not between:
        return None
    name = head[:len(head) - between.end()]
    name = name[_TIMING_ROW_EDGE_RE.match(name).end():]
    name = name[:len(name) - _TIMING_ROW_TAIL_RE.match(name[::-1]).end()]
    if (not name or not name[0].isalpha() or len(name) > 40 or name[-1] in _TIMING_SENTENCE_END
            or any(c in _TIMING_ROW_CLAUSE_MARKS for c in name)):
        return None
    words = len(name.split(None, 3))
    value, whole, unit = _timing_value_tail(mline, d.start())
    if words > 3 or (words == 3 and whole < 2 and not unit):
        return None
    return d.start() if value else None


def _timing_key(s: str, pos: int = 0, end: int | None = None) -> re.Match | None:
    """The 'key:' at the start of the line [pos, end) of `s`, or None: indentation and blockquote marks, a bullet, a key of up to
    80 characters and its separator (_TIMING_KEY_TAIL_RE). Round 7 (A1, the audit of every timing pattern): the marks are read
    once; when no key follows them, the only other key that can end at the same separator - one starting at their last '>' ('>
    1200: x', '>: x') - is tried once, as round 6's pattern found by backtracking. Linear in the line."""
    end = len(s) if end is None else end
    quoted = _TIMING_QUOTED_RE.match(s, pos, end).end()
    key = _TIMING_KEY_TAIL_RE.match(s, quoted, end)
    if key is None:
        gt = s.rfind(">", pos, quoted)
        key = _TIMING_KEY_GT_RE.match(s, gt, end) if gt >= 0 else None
    return key


def _timing_valued(text: str, start: int, end: int) -> bool:
    """A line whose value is the field, the whole line [start, end): its indentation and blockquote marks read once, then
    _TIMING_VALUED_RE; the bare key from the last '>' of the marks is tried once, as for _timing_key."""
    quoted = _TIMING_QUOTED_RE.match(text, start, end).end()
    if _TIMING_VALUED_RE.fullmatch(text, quoted, end):
        return True
    gt = text.rfind(">", start, quoted)
    return gt >= 0 and bool(_TIMING_VALUED_GT_RE.fullmatch(text, gt, end))


def _timing_row_line(mline: str) -> tuple[bool, int | None, bool]:
    """docs/05SoulRun 90 (problem 41, decisions 185 and 186): a line of a 'key: value' run - a key line (its key may hold digits
    after its first character, or start with digits and a letter, and run to 80 characters), a definition-list line (': Start
    1200') or a 'name number' row - as (is one, the offset of its first digit that is a value - after the key's separator, never
    in the key - or None, whether it is a key line with nothing after its separator, such as 'Values in milliseconds:')."""
    key = _timing_key(mline)
    if key:
        d = _TIMING_DIGIT_RE.search(mline, key.end())
        return True, d.start() if d else None, not mline[key.end():].strip(" \t*_`~ 　")
    definition = _TIMING_DEFINITION_RE.match(mline)
    if definition:
        d = _TIMING_DIGIT_RE.search(mline, definition.end())
        return True, d.start() if d else None, False
    d = _timing_row_number(mline)
    return (True, d, False) if d is not None else (False, None, False)


def _timing_run_digit(text: str, masked: str, pos: int, kind: str, look, done: dict) -> tuple[int | None, int | None]:
    """The first digit in the run of lines from `pos` that `look(line, masked line)` keeps - it returns (kept, the offset of the
    line's first counting digit or None, whether the line is a key with nothing after its separator) - or None; and, for a run
    without a digit that is one line or only such key lines ('Values in milliseconds:', 'Node timings:'), the end of its last line
    (it is carried over, see _timing_below), else None. The lines read are recorded for `kind` in `done`: (the run's start, the
    end of its last line, where the trailing lines with nothing after their separators start) - a run starting inside it ends
    where it ends, so _timing_structure answers it without reading it again."""
    n = len(text)
    count, intro, last, first, streak = 0, True, None, pos, n + 1
    while pos <= n:
        line, line_end = _timing_line(text, pos)
        kept, d, empty = look(line, masked[pos:line_end])
        if not kept:
            break
        if d is not None:
            return pos + d, None
        count, intro = count + 1, intro and empty
        streak = (pos if streak > n else streak) if empty else n + 1
        last = line_end
        done[kind] = (first, last, streak)
        pos = line_end + 1
    return None, last if count == 1 or (count and intro) else None


def _timing_any_digit(line: str, mline: str) -> tuple[bool, int | None, bool]:
    d = _TIMING_DIGIT_RE.search(mline)
    return True, d.start() if d else None, False


def _timing_next_line(text: str, end: int) -> int | None:
    """The start of the first non-blank line after the line ending at `end`, after at most two blank lines; None."""
    n, pos, blanks = len(text), end + 1, 0
    while pos <= n:
        line, line_end = _timing_line(text, pos)
        if line.strip():
            return pos
        blanks += 1
        if blanks > 2:
            return None
        pos = line_end + 1
    return None


def _timing_structure(text: str, masked: str, pos: int, indent: int, nested: bool, done: dict
                      ) -> tuple[bool, int | None, int | None]:
    """docs/05SoulRun 90 (problem 41), rule (3): whether the line at `pos` opens a structure - a fenced code block, a list or
    indented block, a { or [, a table (| lines, HTML table lines, CSV/TSV lines under a line that reads as a header line), a run of
    'key: value' / definition-list / 'name number' lines - the first digit in it (None: none), and, when it holds no digit and is
    one line (a fenced block: at most one line between its fences; a run of key lines: also several with nothing after their
    separators), the end of its last line: that structure is carried over like a line that opens nothing (decision 186, va 1
    defect 1); else None. `indent` and `nested` describe the line above it (see _timing_below). `done` maps a structure kind to
    what was read for it without a digit - a bracket: its end; a block: (its end, its least indentation, the blank lines at its
    end, the start of its last non-blank line); a run: (its start, its end, where its trailing key lines with nothing after their
    separators start) - and a structure of that kind starting inside it is answered from it: it lies inside it (a block as shallow
    or deeper), ends where it ends (a run) or goes on after it (a shallower block: only the lines after it are read); one that is
    one line - a bracket closing on its line, a block starting at the last line of the one read - is still carried over (round 7:
    a clause's carried-over line can be the first line below a heading under it)."""
    n = len(text)
    line, line_end = _timing_line(text, pos)
    mline = masked[pos:line_end]
    head = mline.lstrip()[:1]          # the first visible character: which structures can start here
    fence = _TIMING_FENCE_RE.match(mline) if head in ("`", "~") else None
    if fence:                          # a fenced code block: to the next line starting with the same fence, or the end
        mark, stop, p, inner, closed = fence.group(1), n, line_end + 1, 0, False
        while p <= n:
            fence_line, fence_end = _timing_line(text, p)
            if fence_line.lstrip().startswith(mark):
                stop, closed = p, True
                break
            inner += 1
            p = fence_end + 1
        d = _TIMING_DIGIT_RE.search(masked, pos, stop)
        return True, d.start() if d else None, (_timing_line(text, stop)[1] if not d and closed and inner <= 1 else None)
    listed = _TIMING_LIST_RE.match(mline) if head in _TIMING_LIST_HEADS else None
    opener = _TIMING_OPENER_RE.match(mline) if head in ("{", "[") and not listed else None
    if opener:                         # a { or [: to its matching bracket or a blank line
        start = pos + opener.end() - 1
        if start <= done.get("bracket", -1):  # inside a bracket read before: no digit; carried over if it closes on its line
            depth = 0
            for b in _TIMING_BRACKET_RE.finditer(text, start, line_end):
                depth += 1 if text[b.start()] in "{[" else -1
                if depth == 0:
                    return True, None, line_end
            return True, None, None
        stop = _timing_bracket_end(text, start)
        d = _TIMING_DIGIT_RE.search(masked, start, stop)
        if d:
            return True, d.start(), None
        done["bracket"] = stop
        return True, None, (line_end if stop <= line_end else None)
    if listed or line[:1].isspace():   # a list or indented block, except an ordered-list number followed by words
        least = min(len(line) - len(line.lstrip()), indent + 1) if nested else 0
        blanks, items, first_end = 0, 0, line_end
        last = pos
        read = done.get("block")       # (end, least, blank lines at its end, its last line's start) of the block read last
        if read and pos <= read[0]:    # inside it: a block as shallow or deeper lies within it, a shallower one goes on after it
            if least >= read[1]:       # one line when it starts at the read block's last line
                return True, None, (first_end if pos == read[3] else None)
            pos, blanks, items, last = read[0] + 1, read[2], 1 if pos == read[3] else 2, read[3]
        while pos <= n:
            line, line_end = _timing_line(text, pos)
            if not line.strip():
                blanks += 1
                if blanks > 2:
                    break
            else:
                deep = len(line) - len(line.lstrip())
                if deep < least or not (deep or _TIMING_LIST_RE.match(masked, pos, line_end)):
                    break
                blanks = 0
                items += 1
                last = pos
                d = _TIMING_DIGIT_RE.search(masked, _TIMING_ITEM_RE.match(masked, pos, line_end).end(), line_end)
                if d:
                    return True, d.start(), None
            done["block"] = (line_end, least, blanks, last)
            pos = line_end + 1
        return True, None, (first_end if items == 1 else None)
    kind = look = None
    if "|" in mline:                   # a table: '|' rows, HTML table rows, CSV/TSV lines under a header line
        kind, look = "pipe", lambda row, mrow: ("|" in row and bool(row.strip()),) + _timing_any_digit(row, mrow)[1:]
    elif head == "<" and _TIMING_HTML_ROW_RE.match(mline):
        kind, look = "html", lambda row, mrow: (bool(_TIMING_HTML_ROW_RE.match(mrow)),) + _timing_any_digit(row, mrow)[1:]
    else:
        sep = next((s for s in ",;\t" if s in line and _timing_header_like(_timing_csv_cells(line, s))), None)
        if sep:
            kind, look = "csv" + sep, lambda row, mrow: (sep in row and bool(row.strip()),) + _timing_any_digit(row, mrow)[1:]
        elif _timing_row_line(mline)[0]:   # a run of 'key: value', definition-list or 'name number' lines
            kind, look = "row", lambda row, mrow: _timing_row_line(mrow)
    if kind:
        read = done.get(kind)          # a run of this kind read without a digit: one starting inside it ends where it ends
        if read and read[0] <= pos <= read[1]:
            return True, None, (read[1] if line_end == read[1] or pos >= read[2] else None)
        return (True,) + _timing_run_digit(text, masked, pos, kind, look, done)
    return False, None, None


def _timing_bare_value(masked: str, line_start: int, d: int, end: int) -> int | None:
    """A line [line_start, end) whose digit at `d` starts it - after indentation, markup or punctuation other than '#' - and that
    is only a value (decision 186, below a clause): what follows the value reads as a value (_timing_value_tail: '1200',
    '2026-11-02T10:00:00Z', '1200 ms', '1200 ms for Start, 300 ms for Report') - the digit; None for a sentence that starts with a
    number ('2 nodes were sent back', '2 个节点因此退回', '2 nodes.')."""
    return d if _timing_value_tail(masked[line_start:end], d - line_start)[0] else None


def _timing_below(text: str, masked: str, end: int, indent: int, nested: bool, done: dict, strict: bool) -> int | None:
    """docs/05SoulRun 90 (problem 41, decisions 185 to 187), rule (3): the first digit tied to the heading, label or caption line
    whose structure starts after `end`, or None - in what its first non-blank line below opens (after at most two blank lines).
    With `strict` (below a heading, a label or a caption that reads as no clause, _timing_clause): also a digit starting that line
    when it is no list item or indented line (it may open a key run: '1号节点：n/a'). Without `strict` (below a clause, decision
    187 (b)): a line starting with a digit - after indentation, markup or punctuation other than '#': decision 183's examples '1.
    Router.match chose mini' and '2 nodes were sent back' - is not carried over: only what it opens counts, or the line itself
    when it is only a value (_timing_bare_value). Else, when the first line opens nothing, or a one-line structure without a digit
    (_timing_structure), it is carried over: what the next non-blank line opens - after the own one-line block of an indented or
    list-item line, only a line indented deeper than it. `indent`: the line's indentation; `nested`: it is indented or a list item.
    Each call reads at most two structures, and a structure read before is answered from `done`: linear."""
    pos = _timing_next_line(text, end)
    if pos is None:
        return None
    opened, d, carry = _timing_structure(text, masked, pos, indent, nested, done)
    if d is not None:
        return d
    line, line_end = _timing_line(text, pos)
    block = line[:1].isspace() or bool(_TIMING_LIST_RE.match(masked, pos, line_end))
    if not strict:                     # below a clause: a digit-led line stops here (decision 187 (b))
        start = _TIMING_LEAD_RE.match(masked, pos + len(line) - len(line.lstrip()), line_end)
        if start:
            return None if opened else _timing_bare_value(masked, pos, start.end() - 1, line_end)
    elif not block:                    # a digit starting that line ('1号节点：n/a' opens a key run and still starts with one)
        start = _TIMING_LEAD_RE.match(masked, pos, line_end)
        if start:
            return start.end() - 1
    if not opened:
        carry = line_end
    if carry is None:
        return None
    pos = _timing_next_line(text, carry)
    if pos is None:
        return None
    if nested and block:               # below an indented or list-item line, after its own one-line block: only a deeper line
        after = _timing_line(text, pos)[0]
        if len(after) - len(after.lstrip()) <= indent:
            return None
    return _timing_structure(text, masked, pos, indent, nested, done)[1]


def _timing_heading_end(text: str, start: int, end: int) -> int | None:
    """docs/05SoulRun 90 (problem 41): for a line naming a field, whether it is a heading line (a Markdown '#' heading, an HTML
    <h1>-<h6> line, a line wholly in ** __ * or _ that ends no sentence inside it - round 7, line-A-41_1 defect 9: '**Never write
    started_at.**' is a sentence -, quote marks or a bullet first, a line holding only the field in brackets, or a line with a
    setext underline of = or of two or more -): where what follows it starts (its end, or the underline's end); None for another
    line."""
    line = text[start:end]
    first = line.lstrip()[:1]
    if first and first in "#<*_>-+•[":
        if _TIMING_HEADING_RE.match(line):
            return end
        rest = _timing_rstrip(line)
        if ((_TIMING_EMPHASIS_RE.fullmatch(rest) and not _timing_sentence_end(rest))
                or (first in "[>" and _TIMING_BRACKET_HEADING_RE.fullmatch(rest))):
            return end
    if end < len(text):
        underline, underline_end = _timing_line(text, end + 1)
        if underline.lstrip()[:1] in ("=", "-") and _TIMING_UNDERLINE_RE.fullmatch(underline):
            return underline_end
    return None


class _TimingSiblings:
    """docs/05SoulRun 90 (problem 41, decision 185): the sibling rule for a line whose value is the field ('"metric":
    "elapsed_ms"', 'metric: elapsed_ms', '- metric: elapsed_ms', 'metric = "elapsed_ms"', or an array element '"elapsed_ms",'): the
    first digit on another line of the { or [ that encloses the field (to its matching bracket or a blank line), or - outside any
    bracket, and not for an element - on the lines of its YAML mapping: below it and, unless it is a list item, above it back to the
    list item it belongs to, the lines indented deeper than its key, or as deep and holding 'key: value' or 'key:' (in such a line
    only a digit after the separator counts), at most two blank lines in a row. Built once per text, on the first such line, and
    asked in text order: brackets are matched in one pass and digits found by bisection in their positions; a mapping read without
    a digit covers every later line inside it whose key is as deep or deeper (its mapping lies inside), and a walk up for a
    shallower key jumps over it (a walk down never meets one: each starts above the line it was read for) - so each line is read
    a bounded number of times: linear."""

    def __init__(self, text: str, masked: str):
        self.text, self.masked = text, masked
        self.digits = [m.start() for m in _TIMING_DIGIT_RE.finditer(masked)]
        self.events = [(b.start(), text[b.start()]) for b in _TIMING_BRACKET_RE.finditer(text)]
        self.ends: dict[int, int] = {}                 # a { or [ -> the end of what it encloses
        stack: list[int] = []
        for pos, c in self.events:
            if c in "{[":
                stack.append(pos)
            elif c == "\n":                            # a blank line ends every open bracket
                self.ends.update((o, pos) for o in stack)
                stack.clear()
            elif stack:
                self.ends[stack.pop()] = pos + 1
        self.ends.update((o, len(text)) for o in stack)
        self.next_event, self.open = 0, []             # the brackets open before the latest field asked about
        self.cover = (-1, -1, 0)                       # the latest mapping read without a digit: (first, last line start, key column)
        self.lasts: dict[int, tuple[int, int]] = {}    # the last line start of such a mapping -> (its first line start, key column)

    def _first_digit(self, lo: int, hi: int, skip_lo: int, skip_hi: int) -> int | None:
        from bisect import bisect_left
        for start in (lo, max(lo, skip_hi)):
            i = bisect_left(self.digits, start)
            if i < len(self.digits) and self.digits[i] < hi and not skip_lo <= self.digits[i] < skip_hi:
                return self.digits[i]
        return None

    def digit(self, field_start: int, line_start: int, line_end: int, element: bool) -> int | None:
        """The first digit tied to the line [line_start, line_end) whose value is the field starting at `field_start`; `element`:
        the line is an array element holding only the field ('"elapsed_ms",'), which counts inside a { or [ only."""
        while self.next_event < len(self.events) and self.events[self.next_event][0] < field_start:
            pos, c = self.events[self.next_event]
            if c in "{[":
                self.open.append(pos)
            elif c == "\n":
                self.open.clear()
            elif self.open:
                self.open.pop()
            self.next_event += 1
        if self.open:
            return self._first_digit(self.open[-1], self.ends[self.open[-1]], line_start, line_end)
        return None if element else self._mapping_digit(line_start, line_end)

    @staticmethod
    def _column(row: str) -> tuple[int, int, bool]:
        """A line's indentation, the column of its key (after a list bullet) and whether it is a list item."""
        indent = len(row) - len(row.lstrip(" \t"))
        body = row[indent:]
        if body[:1] in ("-", "*", "+", "•") and body[1:2] in (" ", "\t"):
            return indent, indent + 1 + len(body[1:]) - len(body[1:].lstrip(" \t")), True
        return indent, indent, False

    def _member(self, pos: int, end: int, column: int) -> tuple[bool, int | None]:
        row = self.text[pos:end]
        deep = len(row) - len(row.lstrip(" \t"))
        if deep < column:
            return False, None
        key = _timing_key(self.masked, pos, end)
        if deep == column and not key:
            return False, None
        start = key.end() if key else _TIMING_ITEM_RE.match(self.masked, pos, end).end()   # an ordinal followed by words is no value
        d = _TIMING_DIGIT_RE.search(self.masked, start, end)
        return True, d.start() if d else None

    def _mapping_digit(self, line_start: int, line_end: int) -> int | None:
        text, masked, n = self.text, self.masked, len(self.text)
        _, column, item = self._column(text[line_start:line_end])
        first, last, covered = self.cover
        if first <= line_start <= last and covered <= column:   # inside a mapping read for a key as deep or shallower
            return None
        first = last = line_start
        pos, blanks = line_end + 1, 0                   # below: the rest of the mapping
        while pos <= n:
            row, end = _timing_line(text, pos)
            if not row.strip():
                blanks += 1
                if blanks > 2:
                    break
            else:
                blanks = 0
                kept, d = self._member(pos, end, column)
                if not kept:
                    break
                if d is not None:
                    return d
                last = pos
            pos = end + 1
        end, blanks = line_start - 1, 0                 # above: the mapping's earlier lines, back to its list item
        while not item and end > 0:
            pos = text.rfind("\n", 0, end) + 1
            jump = self.lasts.get(pos)
            if jump and jump[1] >= column:              # a mapping already read for a key as deep or deeper ends here
                first, blanks, end = jump[0], 0, jump[0] - 1
                continue
            row = text[pos:end]
            if not row.strip():
                blanks += 1
                if blanks > 2:
                    break
            else:
                blanks = 0
                kept, d = self._member(pos, end, column)
                if not kept:
                    deep, key_column, listed = self._column(row)
                    key = _timing_key(masked, pos, end) if listed and key_column == column else None
                    d = _TIMING_DIGIT_RE.search(masked, key.end(), end) if key else None
                    if d:
                        return d.start()
                    break
                if d is not None:
                    return d
                first = pos
            end = pos - 1
        self.cover = (first, last, column)
        self.lasts[last] = (first, column)
        return None


def _timing_field_claim(text: str) -> str | None:
    """docs/05SoulRun 90 (problem 41): the first timing field in `text` with a digit tied to it by rules (1)-(3) of TIMING_CLAIM_RULE
    - the field and its value, as written - else the table rule (4), else the first digit below a caption line (rule (3), kept
    until rule (4) has quoted its column); None when there is none. Linear: one digit search serves the
    clauses, a clause or bracket already scanned without a digit is not scanned again for a later field inside it (that field's
    range lies within it), each line is read once as a field's line, the lines below it are read at most twice as the first or the
    carried-over line of a structure (see _timing_below) and not at all when no digit follows (one forward search serves the
    lines), each kind of structure once, and the sibling rule once per text (see _TimingSiblings)."""
    if "_" not in text:                # every field name holds one, and every rule starts from a field
        return None
    text = _timing_text(text)
    first = _TIMING_FIELD_RE.search(text)
    if not first:
        return None
    n = len(text)
    masked = _timing_masked(text)      # the digits of HTML tag names and entities hidden: no values
    digit = -1                         # the first digit at or after the latest field's end (n: none): one search serves them all
    done: dict[str, int] = {}          # a structure kind -> the end of the last line read for it below a line, without a digit
    clause_done = struct_done = 0
    line_start, line_end, line_field, heading, decided, below = 0, -1, first, None, True, True
    siblings = caption = None          # caption: the first claim below a caption, quoted after the table rule's (4) own quote
    below_digit = -1                   # the first digit at or after the latest line asked about below (n: none); lines come in order

    def nested_below(strict: bool, after: int) -> int | None:
        nonlocal below_digit
        if below_digit < after:
            m = _TIMING_DIGIT_RE.search(masked, after)
            below_digit = m.start() if m else n
        if below_digit >= n:                            # no digit below: nothing there can be a claim
            return None
        label = text[line_start:line_end]
        indent = len(label) - len(label.lstrip())
        return _timing_below(text, masked, after, indent, bool(indent or _TIMING_LIST_RE.match(masked, line_start, line_end)),
                             done, strict)

    def caption_line() -> bool:                         # the line is a caption - a table's title row of two cells or more
        line = text[line_start:line_end]                # only when it does not lie inside its table (round 7)
        table_row = "|" in line or _TIMING_TABLE_ROW_RE.match(line)
        return _timing_caption(line, not table_row or _timing_title_row(line)[1] < 2
                               or not _timing_row_inside(text, line_start, line_end))

    for field in _TIMING_FIELD_RE.finditer(text, first.start()):
        end = field.end()
        if end > line_end:                              # the first field on its line (nothing to read below the last line)
            if not (below or caption) and caption_line():   # the line before: a caption, if no heading or label
                clause = _timing_clause(text[line_start:line_end], line_field.start() - line_start)
                d = nested_below(not clause, line_end)
                caption = None if d is None else _timing_value_quote(text, masked, line_field, d)
            line_start = text.rfind("\n", max(line_end, 0), field.start()) + 1
            line_end = text.find("\n", end)
            line_end = n if line_end < 0 else line_end
            line_field = field
            decided = below = line_end >= n
            heading = None if decided else _timing_heading_end(text, line_start, line_end)
            before = text[field.start() - 1] if field.start() > line_start else ""   # a value: after quotes, markup or a separator
            valued = before and before in " \t\"'`*_~:：=＝" and _timing_valued(text, line_start, line_end)
            element = before in ("\"", "'") and not valued and _TIMING_ELEMENT_RE.fullmatch(text, line_start, line_end)
            if valued or element:
                siblings = siblings or _TimingSiblings(text, masked)
                d = siblings.digit(field.start(), line_start, line_end, bool(element))
                if d is not None:
                    return f"{field.group(1)} … {text[d:_TIMING_VALUE_RE.match(masked, d).end()]}"
        if end >= clause_done:                          # (1) a digit after the field in its clause
            if digit < end:
                m = _TIMING_DIGIT_RE.search(masked, end)
                digit = m.start() if m else n
            pos = end
            while True:
                stop = _TIMING_CLAUSE_END_RE.search(text, pos)
                t = stop.start() if stop else n
                if digit < t:
                    return _timing_value_quote(text, masked, field, digit)
                if t >= n or text[t] == "\n" or not _timing_clause_goes_on(text, t, end):
                    clause_done = t
                    break
                pos = t + 1
            depth, start = 0, max(end, struct_done)     # (2) a { or [ opened in the clause and still open at its end
            if text.find("{", start, t) >= 0 or text.find("[", start, t) >= 0:
                for b in _TIMING_BRACKET_RE.finditer(text, start, t):
                    depth = depth + 1 if text[b.start()] in "{[" else max(0, depth - 1)
            stop = t
            if depth:
                for b in _TIMING_BRACKET_RE.finditer(text, t):
                    if text[b.start()] == "\n":
                        stop = b.start()
                        break
                    depth += 1 if text[b.start()] in "{[" else -1
                    if depth == 0:
                        stop = b.end()
                        break
                else:
                    stop = n
                if digit < stop:
                    return _timing_value_quote(text, masked, field, digit)
            struct_done = max(struct_done, stop)
        if not decided and (heading is not None or clause_done == line_end):   # (3) once per line: a heading, else the first
            decided = True                              # field whose clause runs to the line end decides whether it is a label
            after = heading
            if (after is None and not _timing_row_in_table(text, line_start, line_end)
                    and _timing_label(text[line_start:line_end], end - line_start)):
                after = line_end
            if after is not None:
                below = True
                d = nested_below(True, after)
                if d is not None:
                    return _timing_value_quote(text, masked, field, d)
    if not (below or caption) and caption_line():
        d = nested_below(not _timing_clause(text[line_start:line_end], line_field.start() - line_start), line_end)
        caption = None if d is None else _timing_value_quote(text, masked, line_field, d)
    table = "\n" in text and _TIMING_DIGIT_RE.search(masked, first.start())   # a table has two lines at least and a digit
    return (_timing_table_claim(text, masked) if table else None) or caption


def _timing_value_quote(text: str, masked: str, field: re.Match, d: int) -> str:
    """A claim as quoted: the field through the value starting at `d`, as written (shortened as 'field … value' past 120)."""
    value = _TIMING_VALUE_RE.match(masked, d)
    quote = text[field.start(1):value.end()]
    return quote if len(quote) <= 120 else f"{text[field.start(1):field.start(1) + 60]} … {text[d:value.end()]}"


def _table_cells(line: str) -> list[str]:
    row = line.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") else row
    return row.split("|")


def _timing_table_claim(text: str, masked: str) -> str | None:
    """docs/05SoulRun 90 (problem 41), rule (4): a digit in a later row's cell of a column whose header names a timing field -
    '<field> column: <cell>' - or None. A Markdown table's header is the row just above its delimiter row (|---|); separated rows
    (HTML cells, '|', tabs, commas, semicolons) follow a header line with as many cells, split by its separator, at most two blank
    lines in a row between them; a CSV/TSV header cell is the field itself, and under a prose line with commas (_timing_row_header)
    only a cell that starts with a digit counts. Each row's own cells are read once (never rows x columns)."""
    if not any(c in text for c in "|,;\t<"):
        return None
    lines, mlines = text.split("\n"), masked.split("\n")
    delimiter = ["|" in line and "-" in line and bool(_TIMING_DELIMITER_RE.fullmatch(line)) for line in lines]
    for i in range(1, len(lines)):
        if not (delimiter[i] and "|" in lines[i - 1]):
            continue
        columns = {k: m.group(1) for k, cell in enumerate(_table_cells(lines[i - 1])) if (m := _TIMING_FIELD_RE.search(cell))}
        j = i + 1
        while columns and j < len(lines) and "|" in lines[j] and not delimiter[j]:
            for k, (cell, mcell) in enumerate(zip(_table_cells(lines[j]), _table_cells(mlines[j]))):
                if k in columns and _TIMING_DIGIT_RE.search(mcell):
                    return f"{columns[k]} column: {cell.strip()[:40]}"
            j += 1
    header, blanks = None, 0                            # (kind, separator, cell count, {column: field}, every digit counts)
    for line in lines:
        if header and not line.strip():                 # at most two blank lines between a header and its rows
            blanks += 1
            if blanks > 2:
                header = None
            continue
        blanks = 0
        row = False                                     # the line is a row of a header line whose every digit counts
        if header:
            cells = _timing_row_cells(line, header[0], header[1])
            if cells is not None and len(cells) == header[2]:
                row = header[4]
                for k, cell in enumerate(cells):
                    if k in header[3] and (_timing_digit(cell) if header[4] else _TIMING_DIGIT_LED_RE.match(_timing_masked(cell))):
                        return f"{header[3][k]} column: {_TIMING_TAG_RE.sub('', cell).strip()[:40]}"
            else:
                header = None
        if "_" not in line or not _TIMING_FIELD_RE.search(line):    # a header line names a field
            continue
        choice = None                                   # the first separator whose split is a header line, else the first
        for kind, sep in _TIMING_ROW_KINDS:             # prose split - unless the line is a row of a header line (va 2 defect 4)
            cells = _timing_row_cells(line, kind, sep)
            columns, strict = _timing_row_header(cells, kind) if cells is not None else ({}, True)
            if columns and (strict or choice is None):
                choice = (kind, sep, cells, columns, strict)
                if strict:
                    break
        if choice and (choice[4] or not row):
            kind, sep, cells, columns, strict = choice
            same = header and header[:3] == (kind, sep, len(cells))
            header = (kind, sep, len(cells), {**(header[3] if same else {}), **columns}, strict or bool(same and header[4]))
    return None


def _timing_path(path) -> str:
    keys = []
    while path:
        path, key = path
        keys.append(key)
    keys = [key if isinstance(key, str) else f"[{key}]" for key in reversed(keys)]   # a list index is kept as an int until quoted
    keys = keys[next((i for i, key in enumerate(keys) if _TIMING_FIELD_RE.search(key)), 0):]
    return ".".join(keys if len(keys) <= 3 else [keys[0], "…", keys[-1]]).replace(".[", "[")


def _timing_quote(under: tuple, path, value=None) -> str:
    """How a digit in a structured output is quoted: under a field key '<keys>: <value>'; beside a value that is the field or a
    caption '<field> … <keys>: <value>'; in a field's column of a table given as lists '<field> column: <value>'."""
    keys = _timing_path(path)
    if under[0] == "column":
        return f"{under[1]} column: {keys if value is None else value}"
    head = keys if under[0] == "key" else f"{under[1]} … {keys}"
    return head if value is None else f"{head}: {value}"


def _timing_named(values, captions: bool) -> tuple[str, int, set] | None:
    """The field a string value of a container is - the field itself, quotes, markup, a unit in brackets and a trailing separator
    aside ('elapsed_ms', '**elapsed_ms** (ms)') - or, with `captions`, the field a one-line string value names as a caption
    ('elapsed_ms per node', 'Elapsed time (elapsed_ms)': _timing_caption), also as the one value of a dict value ({'title':
    'elapsed_ms per node'}, {'name': 'elapsed_ms'}: va 1 defect 8) when no string value names one: (that field, the value's
    position, the positions of every value that names a field so - round 7, line-A-41_2 defect 7: a second caption beside the
    first is no sibling of it, its digits are its own text); None. Each value is read once."""
    values = list(values)
    found, own = None, set()
    for dicts in (False, True) if captions else (False,):
        for i, value in enumerate(values):
            if dicts:
                if not (isinstance(value, dict) and len(value) == 1):
                    continue
                value = next(iter(value.values()))
            if isinstance(value, str) and "_" in value:
                field = None
                if _TIMING_FIELD_CELL_RE.fullmatch(value):
                    field = _TIMING_FIELD_RE.search(value).group(1)
                elif captions:
                    line = _timing_text(value).strip()
                    named = _TIMING_FIELD_RE.search(line) if "\n" not in line else None
                    field = named.group(1) if named and _timing_caption(line) else None
                if field:
                    own.add(i)
                    found = found or (field, i)
    return (found[0], found[1], own) if found else None


def _timing_caption_key(items) -> tuple[str, int, set] | None:
    """A key of a dict that is a one-line caption naming a field - not the field alone: {'started_at': None} is a record that
    leaves the field empty - and holds nothing (None, '', [] or {}): a caption written as a key ({'elapsed_ms per node': None,
    'Start': 1200}) - (that field, its position, {its position}); None."""
    for i, (key, child) in enumerate(items):
        if (child is None or (isinstance(child, (str, list, dict)) and not child)) and not _TIMING_FIELD_CELL_RE.fullmatch(str(key)):
            named = _timing_named([str(key)], True)
            if named:
                return named[0], i, {i}
    return None


def _timing_header_row(row) -> dict[int, str]:
    """The columns a header row of a table given as lists names a timing field in: {position: field} - a string cell naming one,
    or a dict cell with a string value naming one ([{'title': 'Node'}, {'title': 'elapsed_ms'}]: va 1 defect 8)."""
    columns = {}
    for k, cell in enumerate(row):
        if isinstance(cell, dict):
            cell = next((value for value in cell.values() if isinstance(value, str) and _TIMING_FIELD_RE.search(value)), None)
        if isinstance(cell, str) and (m := _TIMING_FIELD_RE.search(cell)):
            columns[k] = m.group(1)
    return columns


def _timing_split_row(line: str, count: int, split) -> list[str] | None:
    """A row string's cells for a split table's header of `count` cells: split as the header string (`split`: its kind and
    separator), or - for a header given as a list - by the first of | tab , ; that gives `count` cells; None."""
    for kind, sep in ((split,) if split else _TIMING_ROW_KINDS[1:]):
        cells = _table_cells(line) if kind == "pipe" and not split and "|" in line else _timing_row_cells(line, kind, sep)
        if cells is not None and len(cells) == count:
            return cells
    return None


def _timing_split_rows(items) -> str | None:
    """docs/05SoulRun 90 (problem 41, decisions 185 and 186): a table split over a dict's values - a header (a one-line header
    string: '| node | elapsed_ms |', 'node,elapsed_ms'; or a list of strings or of dicts naming a field) beside row strings (in a
    list, or the lines of a string): a digit in a row's cell of a column the header names a field in, each row split as the
    header string is, or by | tab , ; into as many cells as the header has - '<field> column: <cell>', or None. One header per
    dict, each row split at most four times: linear."""
    header = None                                       # (cell count, {column: field}, (kind, separator) or None, the value)
    for _, value in items:
        if isinstance(value, str) and "_" in value and "\n" not in value.strip() and _TIMING_FIELD_RE.search(value):
            for kind, sep in _TIMING_ROW_KINDS[1:]:
                cells = _timing_row_cells(value, kind, sep)
                columns = _timing_header_row(cells) if cells is not None and len(cells) > 1 else {}
                if columns:
                    header = (len(cells), columns, (kind, sep), value)
                    break
        elif isinstance(value, list) and len(value) > 1 and all(isinstance(cell, (str, dict)) for cell in value):
            columns = _timing_header_row(value)
            header = (len(value), columns, None, value) if columns else None
        if header:
            break
    if not header:
        return None
    count, columns, split, own = header
    for _, value in items:
        if value is own:
            continue
        rows = value if isinstance(value, list) else [value] if isinstance(value, str) and "\n" in value.strip() else ()
        for row in rows:
            for line in (_timing_text(row).split("\n") if isinstance(row, str) else ()):
                cells = _timing_split_row(line, count, split)
                for k, cell in enumerate(cells or ()):
                    if k in columns and _timing_digit(cell):
                        return f"{columns[k]} column: {cell.strip()[:40]}"
    return None


def _timing_output_claim(output) -> str | None:
    """docs/05SoulRun 90 (problem 41), rule (5): a structured output walked in document order, without recursion - each key and
    each string as a text (with its real line breaks, not the JSON text's escaped ones), each list of strings also joined by line
    breaks, and any digit (in a key, a string or a number) under a key that names a timing field; beside a string value that is a
    field - or, in a dict and in a list holding more than strings, a one-line caption naming one, also as the one value of a dict
    value - in the other values of its dict or list (the caption's own digits are text: vd 1 defect 2); in a field's column of a
    table given as lists: the rows after the first row naming a field in a list of lists, the rows of a list of lists - or the
    lists of a dict row or of a dict of rows - beside a list of strings or of dicts naming one (a split table's header), the row
    strings beside a header string or list. The prose form counts as for a text: a prose timing in one key or string and an ISO
    time in any. Linear: each node is visited once, each string at most three times, a list of lists shares one column map among
    its rows (va 2 defect 1), and a list with its own header row looks a column up in it first and then in the one it inherits,
    without copying either (round 7: a wide inherited header beside many such lists)."""
    from collections import ChainMap
    stack, prose, iso = [(output, None, None, None, None)], None, False   # (node, path, why a digit there is a claim, row columns,
    while stack:                                                           #  the columns of each row of this list of lists)
        node, path, under, columns, table = stack.pop()
        if isinstance(node, dict):
            items = list(node.items())
            named = _timing_named([value for _, value in items], True) or _timing_caption_key(items)
            split = _timing_split_rows(items)
            if split:
                return split
            heads: dict[int, str] = {}                  # a split table's header: a list of strings or of dicts naming a field
            for _, value in items:
                if isinstance(value, list) and value and (all(isinstance(cell, str) for cell in value)
                                                          or all(isinstance(cell, dict) for cell in value)):
                    heads.update(_timing_header_row(value))
            for i in range(len(items) - 1, -1, -1):
                key, child = items[i]
                key = _timing_text(str(key))
                found = _timing_field_claim(key)
                if found:
                    return found
                if under and _timing_digit(key):
                    return _timing_quote(under, (path, key))
                prose = prose or _TIMING_PROSE_RE.search(key)
                iso = iso or bool(_ISO_RE.search(key))
                why = under or (("key",) if _TIMING_FIELD_RE.search(key) else
                                ("sibling", named[0]) if named and i not in named[2] else None)
                stack.append((child, (path, key), why, table if isinstance(child, list) else None, heads or None))
        elif isinstance(node, list):
            strings = len(node) > 1 and all(isinstance(item, str) for item in node)
            named = _timing_named(node, not strings)
            if strings:
                joined = "\n".join(map(_timing_text, node))
                found = _timing_field_claim(joined)
                if found:
                    return found
                prose = prose or _TIMING_PROSE_RE.search(joined)
            own, start = None, len(node)                # the first row naming a field heads the rows after it
            for i, item in enumerate(node):
                if isinstance(item, list):
                    own = _timing_header_row(item) or None
                    if own:
                        start = i
                        break
            # one column map for every row after the header row: its own header first, then the one it inherits - not copied
            # (round 7, line-A-41_1 defect 5 / line-A-41_2 defect 3: a wide inherited header beside many lists with their own)
            merged = ChainMap(own, table) if own and table else own or table
            for i in range(len(node) - 1, -1, -1):
                item = node[i]
                why = (under or (("sibling", named[0]) if named and i not in named[2] else None)
                       or (("column", columns[i]) if columns and i in columns else None))
                if isinstance(item, list):
                    stack.append((item, (path, i), why, (merged if own and i > start else table) or None, None))
                else:                                   # a row given as a dict: its lists are rows of this table
                    stack.append((item, (path, i), why, None, table if isinstance(item, dict) else None))
        elif isinstance(node, str):
            text = _timing_text(node)
            found = _timing_field_claim(text)
            if found:
                return found
            if under and _timing_digit(text):
                return _timing_quote(under, path, text.strip()[:40])
            prose = prose or _TIMING_PROSE_RE.search(text)
            iso = iso or bool(_ISO_RE.search(text))
        elif under and not isinstance(node, bool) and node is not None and _TIMING_DIGIT_RE.search(str(node)):
            return _timing_quote(under, path, node)
    return _timing_prose_quote(prose) if prose and iso else None


def _timing_prose_quote(prose: re.Match) -> str:
    """The prose timing as quoted: the word and the number, and the unit only as a whole word ('took 3 sessions' is 'took 3')."""
    number = _TIMING_PROSE_NUMBER_RE.match(prose.string, prose.end(1))
    unit = _TIMING_PROSE_UNIT_RE.match(prose.string, number.end())
    return prose.string[prose.start():(unit or number).end()]


def _timing_claim(*values) -> str | None:
    """docs/05SoulRun 90 (problem 41): the first timing claim in user-facing values - a text, or a structured output (dict or list)
    walked by _timing_output_claim - as TIMING_CLAIM_RULE states, or a prose timing next to an ISO time; None when there is none.
    The values come as commit passes them: (user_summary, output, *user_messages, answer). Each is read once, in the order a node
    shows its texts to the human - user_messages in order, then user_summary (the User Message stands above the Report:
    render.node_block, the core contract's stream order :::message, :::report), then the output, then the answer when it is not
    user_summary itself (commit passes user_summary as the answer outside the answer node: round 7, line-A-41_1 defect 3,
    line-A-41_2 defect 1) - and the texts among them are also read together, in that order, as paragraphs of one text, so that a
    caption or label in one and the list or table in the next are read as the human sees them (va 1 defect 9); a structured output
    is walked on its own."""
    summary, output = values[:1], values[1:2]
    messages, answer = (values[2:-1], values[-1:]) if len(values) > 2 else ((), ())
    if answer and (answer[0] is summary[0] or answer[0] == summary[0]):
        answer = ()                                     # the summary again: read once
    texts = []
    for value in (*messages, *summary, *output, *answer):
        if isinstance(value, (dict, list)):
            claim = _timing_output_claim(value)
        elif isinstance(value, str):
            text = _timing_text(value)
            texts.append(text)
            claim = _timing_field_claim(text)
            prose = None if claim else _TIMING_PROSE_RE.search(text)
            claim = claim or (_timing_prose_quote(prose) if prose and _ISO_RE.search(text) else None)
        else:
            claim = None
        if claim:
            return claim
    return _timing_field_claim("\n\n".join(texts)) if len(texts) > 1 else None


def _served_steps(entry: dict, program: program_loader.Program | None) -> list[dict]:
    if entry["kind"] == "engine":
        return [dict(s) for s in ENGINE_STEPS[entry["name"]]]
    view = _view_for(program, entry)
    out = []
    for s in view["steps"]:
        sysc = s["sys"]
        out.append({
            "key": s["key"], "mode": s["mode"], "text": s["text"], "work_mode": s["work_mode"],
            "sys": {k: sysc[k] for k in ("name", "args", "store", "valid", "forced_blocking")} if sysc else None,
            "sub_task": s["sub_task"], "mixed": s["mixed"],
            "assert": {"predecessors": s["assert"]["predecessors"], "required": s["assert"]["required"],
                       "backtrack_to": s["assert"]["backtrack_to"]} if s["assert"] else None,
            "permission": _permission_for(program, sysc["name"]) if sysc else None,
        })
    return out


def _module_delegation_steps(program, entry, view) -> set[str]:
    """Only a step-leading call to this exact subgraph is delegation evidence."""
    module = view.get('module') or {}
    matched = set()
    for step in view['steps']:
        work = (step.get('assert') or {}).get('work') or step['text']
        target = step.get('sub_task')
        if not target and isinstance(work, str):
            call = re.match(r'(?:Delegate\s+to|委托|进入)\s+([A-Za-z0-9_][\w.-]*(?:::[A-Za-z_]\w*)?)',
                            work.strip(), re.I)
            target = call.group(1) if call else None
        resolved = program_loader.resolve_module(program, entry.get('doc') or program.entry_file, target) if target else None
        if resolved and all(resolved.get(k) == module.get(k) for k in ('doc','task','entry_node')):
            matched.add(step['key'])
    return matched


def _gate_summary(sources: list[dict]) -> dict:
    required = [g for g in sources if g["required"]]
    advisory = [g for g in sources if not g["required"]]
    pick = required[0] if required else (advisory[0] if advisory else None)
    return {"required": bool(required), "source": pick["source"] if pick else "none",
            "kind": pick["kind"] if pick else None, "prompt_text": pick.get("prompt_text") if pick else None,
            "advisory": bool(advisory) and not required}


def _view_for(program, entry: dict) -> dict | None:
    if entry["kind"] not in ("business", "sub") or program is None:
        return None
    try:
        view = program_loader.node_view(program, _bare(entry), entry.get("task") or "main", entry.get("doc"))
        from . import module_inputs
        module_inputs.values(view)
        return view
    except program_loader.ProgramError as exc:
        raise EngineError(exc.code, str(exc)) from exc


# ---------------------------------------------------------------------------
# host projection and host-owned facts (schemas/index.v1.json: status/functional_execution_status/failure_code/terminal_reason/host)
# ---------------------------------------------------------------------------

_FAILURE_CODES = {"fatal": "ENGINE_FATAL", "assertion": "ASSERTION_ERROR", "timeout": "RUN_TIMEOUT",
                  "rejection": "CONFIRM_REJECTED", "human_termination": "HUMAN_TERMINATION"}


def project_host_fields(index: dict) -> dict:
    """Derive the fields soulbot.engine_hooks reads (status / functional_execution_status / failure_code / terminal_reason)."""
    rs = index["run_state"]
    term = index.get("run_termination") or {}
    index["status"] = rs.lower()
    if rs == "COMPLETED":
        sem = index.get("semantics") if isinstance(index.get("semantics"), dict) else {}
        fs = sem.get("functional_status")
        index["functional_execution_status"] = fs if fs in ("PASS", "DEGRADED", "PARTIAL", "FAIL") else ("DEGRADED" if term.get("kind") == "degraded" else "PASS")
        index["failure_code"] = None
    elif rs in ("FAILED", "ABANDONED"):
        index["functional_execution_status"] = "FAIL"
        index["failure_code"] = _FAILURE_CODES.get(term.get("kind") or "", "ENGINE_FUNCTIONAL_FAILURE")
    elif rs == "WAITING_USER":
        index["functional_execution_status"] = "WAITING_USER"
        index["failure_code"] = None
    else:
        index["functional_execution_status"] = "UNVERIFIED"
        index["failure_code"] = None
    index["terminal_reason"] = term.get("reason")
    return index


def _write_index(store: RunStore, index: dict) -> str:
    from . import catalog_history
    catalog_history.remember(index)
    index["updated_at"] = now_iso()   # last engine write: the fallback anchor for transport-wait accounting (doc 06 §2 1b)
    digest=store.write_index(project_host_fields(index))
    from . import dispatch_prepare
    dispatch_prepare.publish(store,index)
    return digest


def set_host_fields(cache_dir: str | Path, **fields) -> dict:
    """Record host-reported facts (turn id, channel, model, entry mode, persistence) in the index `host` group."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        host = index.get("host") or {}
        host.update({k: v for k, v in fields.items()})
        index["host"] = host
        _write_index(store, index)
        return host


def record_transport_wait(cache_dir: str | Path, *, since: str | None = None, reason: str = "", code: str = "TRANSPORT_WAIT") -> dict:
    """Record host recovery anchors and raw wait; only their overlap with ready->end is deducted."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        if index["run_state"] != "RUNNING" or not index["current"].get("name"):
            return {"status": "SKIPPED", "run_state": index["run_state"]}
        name, visit = index["current"]["name"], index["current"]["visit"]
        node_entry = index["nodes"].setdefault(_node_key(name, visit), RunStore.new_node_entry(visit))
        anchor = since or index.get("updated_at") or node_entry.get("ready_at")
        end = now_iso()
        gap = _ms_between(anchor, end) or 0
        if "transport_wait_intervals" not in node_entry:
            node_entry["transport_wait_legacy_ms"] = node_entry.get("transport_wait_ms") or 0
            node_entry["transport_wait_intervals"] = []
        if anchor and gap:
            interval = {"started_at": anchor, "ended_at": end}
            if interval not in node_entry["transport_wait_intervals"]:
                node_entry["transport_wait_intervals"].append(interval)
        node_entry["transport_wait_ms"] = (node_entry.get("transport_wait_ms") or 0) + gap
        index["anomalies_summary"].append({"node": name, "code": code,
                                           "text": f"{gap} ms recorded; only measured-window overlap excluded ({reason or 'recovery re-entry'}; anchor {anchor}; end {end})"})
        _write_index(store, index)
        return {"status": "RECORDED", "node": name, "visit": visit, "gap_ms": gap, "transport_wait_ms": node_entry["transport_wait_ms"], "anchor": anchor}


def unindexed_stop(cache_dir: str | Path) -> bool:
    """Read-only (docs/05SoulRun 90 round 3, ledger decision 183): True when the run holds an engine stop cut off before its
    index write that the next next-node, node-commit, interpretation command or gate-answer installs
    (dispatch_budget.unindexed_stop: a dispatch stop while the run is RUNNING, the program-integrity stop also while it waits
    at a gate). prepare_cache's re-entry (and, since round 4, its restart question and the human-Stop judge path) then
    records no transport wait and no interruption of the open ticket, as for the run that never stopped, waiting at that
    stop. Nothing is installed or written here, so the human's message in that turn never answers a stop the human has not
    seen. Each of those four calls installs the stop at its start (dispatch_budget.reinstall; the interpretation command
    since the round-6 merge) - for an integrity stop cut off over a waiting gate, the human's next message through the
    host's prepare reaches gate-answer, which installs it, serves it unpublished and takes no answer at it - and
    program_guard.pause() installs a cut-off integrity stop itself before it would open another (round 6; a backstop for
    serve()'s drift path, which takes the run lock again). Its first published serve is the main executor's: next-node,
    node-commit without an agent ticket, or the interpretation command (record 90 round 7, B5).
    Record 90 round 4 (B6): malformed data never raises here - it is not recognised (False), and prepare records the
    transport wait and the interruption as before (dispatch_budget.unindexed_stop)."""
    store = RunStore(cache_dir)
    with store.lock():
        return dispatch_budget.unindexed_stop(store, store.read_index()) is not None


def record_run_observation(cache_dir: str | Path, *, code: str, text: str) -> dict | None:
    """docs/05SoulRun 90 (problem 21): one host-side observation in the run index (anomalies_summary, at the current node), so
    the run's records and its report carry it; the same row is never added twice. Returns the index as written (or as found
    when the row was there), None for an ended run."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        if index["run_state"] in TERMINAL_STATES:
            return None
        row = {"node": index["current"].get("name") or NODE_MATCH, "code": code, "text": text}
        if row not in index["anomalies_summary"]:
            index["anomalies_summary"].append(row)
            _write_index(store, index)
            index = store.read_index()
        return index


def terminate_run(cache_dir: str | Path, *, kind: str, by: str, reason: str) -> dict:
    """Host-authorised termination of a non-terminal run (supersede, recovery exhausted, shutdown)."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        if index["run_state"] in TERMINAL_STATES:
            return {"status": "ALREADY_TERMINAL", "run_state": index["run_state"]}
        if index["run_state"] == "WAITING_USER":
            for t in index["tickets"]:
                if t["state"] == "READY":
                    t["state"] = "RETIRED"
            index["gate"]["state"] = "CLEAR"
        _terminate(index, kind=kind, by=by, reason=reason)
        _write_index(store, index)
    # Every host-authorised end leaves the same accepted-facts notice the gate and commit paths write (_public/ended.txt,
    # and _terminal_facts.json for a human end), so a run ended from a stop, supply or fault question is not left without
    # one. Best effort, outside the lock: the termination above already stands, and an existing notice is never rewritten.
    try:
        _error_report(store, store.read_index())
    except Exception:  # noqa: BLE001 - the notice must never undo or fail a termination
        pass
    return {"status": "TERMINATED", "run_state": index["run_state"], "kind": kind}


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def _snapshot_entry(directory: Path, entry_file: str) -> dict:
    """One explicit (--entry-path) or scanned (--registry-root) package for the registry snapshot: discovery metadata
    from its own entry document (lib.registry.describe_entry, the fields the registry scripts derive). AIAP.md is not read."""
    meta = registry.describe_entry(directory / entry_file)
    return registry.make_entry(meta.get("protocol", "AIAP"), directory.name, directory / entry_file,
                               **{k: v for k, v in meta.items() if k in registry.ENTRY_FIELDS and k != "protocol" and v is not None})


def init_run(cache_dir: str | Path, *, agent_dir: str | Path | None = None, registry_roots: list | None = None,
             entry_path: str | None = None, user_message: str = "", session_id: str | None = None,
             trace_id: str | None = None, workspace_dir: str | None = None, previous_route: dict | None = None) -> dict:
    """Create _index.json and _run_input.json; the first node is Router.match (doc 01 §4.6).

    Discovery (alpha.20): `agent_dir` runs the agent's own registry scripts (aiap/aiap_list.py, aisp/aisp_list.py)
    through lib.registry and records the catalog fingerprint; a failing registry halts here (REGISTRY_INVALID).
    `entry_path` (one explicit program) and `registry_roots` (directory scan) remain for tests and legacy callers.
    No path reads AIAP.md: discovery metadata comes from the registries or from the entry documents."""
    store = RunStore(cache_dir)
    if store.exists():
        raise EngineError("RUN_EXISTS", f"{store.index_path} already exists; call next-node without initialisation")
    snapshot: list[dict] = []
    registry_info = None
    if entry_path:
        p = program_loader.load_program(entry_path)
        snapshot.append(_snapshot_entry(p.dir, p.entry_file))
    if agent_dir:
        try:
            catalog = registry.collect_registry(agent_dir)
        except registry.RegistryError as exc:
            raise EngineError("REGISTRY_INVALID", str(exc), field="registry",
                              expected="aiap/aiap_list.py and aisp/aisp_list.py that pass --check or regenerate with --json")
        snapshot.extend(catalog["entries"])
        registry_info = registry.provenance(catalog)
    for root in registry_roots or []:
        for item in program_loader.registry_snapshot(root):
            snapshot.append(_snapshot_entry(Path(item["dir"]), item["entry_file"]))
    if not snapshot:
        raise EngineError("PROGRAM_INVALID", "no program found: give --entry-path, --agent-dir or --registry-root with at least one package")
    trace_id = trace_id or f"t-{secrets.token_hex(6)}"
    index = RunStore.new_index(ENGINE_VERSION, trace_id, session_id,
                               {"name": None, "entry_path": None, "entry_file": None, "trust_level": None,
                                "loading_mode": None, "permissions_digest": None, "checks": [], "skipped_files": []},
                               _budget_for("engine", None), render.detect_language(user_message))
    index["route"]["snapshot"] = [s["package"] for s in snapshot]
    if registry_info:
        index["route"]["catalog_sha256"] = registry_info["catalog_sha256"]
        index["route"]["sources"] = registry_info["sources"]
    index["catalog"] = [program_loader.engine_entry(NODE_MATCH, 0)]
    index["current"] = {"name": NODE_MATCH, "visit": 1}
    index["nodes"][NODE_MATCH] = RunStore.new_node_entry(1)
    with store.lock():
        _write_run_input(store, {"user_message": user_message, "snapshot": snapshot, "registry_roots": list(registry_roots or []),
                                 "agent_dir": str(agent_dir) if agent_dir else None, "registry": registry_info,
                                 "entry_path": entry_path, "workspace_dir": workspace_dir, "routed": None,
                                 "previous_route": dict(previous_route) if isinstance(previous_route, dict) else None,
                                 "program_binding_policy": 1,
                                 "program_bindings": {str((Path(s['dir']) / s['entry_file']).resolve()):
                                     program_binding.capture(s['dir'], s['entry_file']) for s in snapshot}})
        _write_index(store, index)
    return index


# ---------------------------------------------------------------------------
# serve (next-node)
# ---------------------------------------------------------------------------

def serve(cache_dir: str | Path, *, agent_ticket: str | None = None, abandon: str | None = None, abandon_reason: str | None = None,
          session: str = "new") -> dict:
    """Deliver main's external contracts with the existing session-entry call."""
    initial_store=RunStore(cache_dir)
    if initial_store.exists():program_guard.assert_run_version(initial_store.read_index())
    entry = None
    if session == "new" and not agent_ticket:
        # Validate before _serve can mutate run state; continuations already have these texts.
        entry = {
            "source_support_contract": str(_contracts.text("entry.source_support_contract")),
            "report_delivery_contract": str(_contracts.text("entry.report_delivery_contract")),
            "quality_execution_contract": str(_contracts.text("entry.quality_execution_contract")),
            "loading_mode_contract": str(_contracts.text("entry.loading_mode_contract")),
        }
    try:
        return _serve(cache_dir, agent_ticket=agent_ticket, abandon=abandon, abandon_reason=abandon_reason,
                      session=session, entry_contracts=entry)
    except EngineError as exc:
        if exc.code != 'PROGRAM_DRIFT_DETECTED':
            raise
        store = RunStore(cache_dir)
        with store.lock():
            index = store.read_index()
            if index['run_state'] in TERMINAL_STATES:
                raise
            # docs/05SoulRun 90 round 5 (ledger decision 185): a sub-agent's next-node (its agent ticket) is served the stop
            # without its menu - not yet shown; the main executor's next-node gives the first published serve
            return program_guard.pause(store, index, exc, publish=not agent_ticket)


def _serve(cache_dir: str | Path, *, agent_ticket: str | None = None, abandon: str | None = None, abandon_reason: str | None = None,
           session: str = "new", entry_contracts: dict | None = None) -> dict:
    """next-node. `agent_ticket`: the calling process is the sub-agent holding that dispatch ticket (doc 10 §3.3);
    `abandon`: the main agent reports that the sub-agent holding that ticket failed (Agent tool error in `abandon_reason`).
    `session` (alpha.100, doc 241): "new" for a direct next-node call (a new model session: every contract section in full), "continue"
    for the next_plan of a commit (sections given earlier in the session are only named)."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        # Problem 85 (docs/05SoulRun 90 §2, ledger decisions 181 and 183): an engine stop whose index write never landed
        # (dispatch_budget.pause()'s or program_guard.pause()'s) is installed as its writer would have, before anything reads
        # the run; any mismatch is left to _recover_orphan_cache.
        dispatch_budget.reinstall(store, index)
        if index.get('run_state')=='RUNNING':
            from . import gate_delivery
            pending_text=gate_delivery.current(cache_dir,index)
            if pending_text:
                return dict(schema_version=1,status='GATE_TEXT_PENDING',run=dict(trace_id=index['trace_id'],state=index['run_state']),
                    node=dict(name=index['current']['name'],kind=_catalog_entry(index,index['current']['name'])['kind']),steps=[],
                    gate=dict(required=True,state='DELIVERY_PENDING'),public_plan=None,public_plan_ref=None,
                    resume=dict(kind='gate_text_delivery',source=gate_delivery.FILE),
                    payload_rules=['Resubmit the complete original gate at this same occurrence; no business execution, simplified menu or next-node advance is authorized.'],
                    gate_delivery_receipt=pending_text)
            program_guard.assert_run_version(index)
            active={e['name'] for e in index.get('catalog',[])}|set(index.get('catalog_history',{}))
            missing=next((k.partition('@')[0] for k,s in index.get('nodes',{}).items() if s.get('cache_sha256') and k.partition('@')[0] not in active),None)
            if missing:raise EngineError('CATALOG_HISTORY_MISSING',f'Accepted node definition is missing: {missing}; preserve evidence and stop.')
        if index['run_state']=='RUNNING' and not any(e['name']==index['current']['name'] for e in index.get('catalog',[])):
            raise EngineError('CURRENT_PLAN_ENTRY_MISSING','Current node is not in the active plan; history cannot authorize execution.')
        dispatch_scope.assert_ticket(index, _catalog_entry(index, index['current']['name']), index['current']['visit'], agent_ticket)
        run_input = _read_run_input(store)
        # docs/05SoulRun 90 round 5 (ledger decision 185): `publish` - only a serve to the main executor (no agent ticket) writes
        # a stop's menu, the mark of a stop shown (_unshown_stop); a sub-agent's next-node that opens or is served an engine
        # stop is served it plain (as node-commit with its ticket, record 90 round 4 B1), so the stop's first published serve
        # stays for the main executor's next-node
        publish = not agent_ticket
        integrity_gate = program_guard.record(store, index)
        program_guard.assert_run_version(index)
        if integrity_gate:
            return program_guard.reply(store, index, integrity_gate, publish=publish)
        program = _load_routed_program(run_input) if index['run_state'] not in TERMINAL_STATES else None
        from . import dispatch_identity
        if dispatch_identity.recover_answer(store, index):
            index = store.read_index()
        identity_gate = dispatch_identity.record(store, index)
        if identity_gate:
            auth_path = dispatch_identity._authorization_path(store, identity_gate['question_id'])
            if store.exists_path(auth_path):
                dispatch_identity.finish_answer(store, index, identity_gate)
                index = store.read_index()
            else:
                return dispatch_identity._publication(store, index, identity_gate, publish=publish)
        blocked_dispatch = dispatch_budget.record(store, index)
        if blocked_dispatch:
            return (dispatch_budget.served(store, index, blocked_dispatch) if publish else
                    dispatch_budget.reply(store, index, blocked_dispatch, publish=False))
        pending = _conditional_pending(store, index)
        if pending:
            if agent_ticket:
                raise EngineError('HUMAN_INTERPRETATION_ACTOR_INVALID', 'The main executor must interpret this original before any dispatch resumes.')
            return _conditional_serve(store, index, pending)
        if index['run_state'] == 'RUNNING' and program:
            reason = dispatch_budget.preflight(index, program, store=store)
            _, current_dispatch = _self_dispatch(index, _catalog_entry(index, index['current']['name']), index['current']['visit'])
            if reason in ('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'DISPATCH_LIVENESS_UNKNOWN'):
                try:
                    if dispatch_identity.authority(store, index, current_dispatch):
                        reason = None
                    elif current_dispatch and current_dispatch.get('scope_root'):
                        return dispatch_identity.open_gate(store, index, publish=publish)
                except EngineError as exc:
                    if exc.code == 'ENGINE_ORPHAN_WRITE_SET_UNPROVEN':
                        raise
                    reason = exc.code
            if reason:
                if reason == 'DISPATCH_LIVENESS_UNKNOWN':
                    _, current_dispatch = _self_dispatch(index, _catalog_entry(index, index['current']['name']), index['current']['visit'])
                    if not agent_ticket:
                        probe = dispatch_lifecycle.request_return(store, index, current_dispatch)
                        if probe:
                            return probe
                    elif dispatch_lifecycle.return_query_due(store, index, current_dispatch):
                        raise _return_query_pending()
                return dispatch_budget.pause(store, index, reason, publish=publish)
        if _recover_orphan_cache(store, index, run_input, program):
            _write_index(store, index)
            run_input = _read_run_input(store)
            program = _load_routed_program(run_input)
        if dispatch_scope.enabled(index) and index['run_state'] == 'RUNNING':
            active_entry = _catalog_entry(index, index['current']['name'])
            root_key, root_record = _self_dispatch(index, active_entry, index['current']['visit'])
            if agent_ticket:
                _claim_ticket(store, index, active_entry, index['current']['visit'], agent_ticket)
            elif root_record and root_record.get('scope_root'):
                gate_answer = _pending_gate_answer(store, index, active_entry['name'], index['current']['visit'])
                try:
                    dispatch = _main_agent_dispatch(store, index, index['nodes'][root_key], active_entry, index['current']['visit'],
                        gate_answer, abandon, abandon_reason, pool=root_record.get('pool', 'ordinary'))
                except EngineError as exc:
                    if exc.code == 'DISPATCH_LIVENESS_UNKNOWN':
                        probe = dispatch_lifecycle.request_return(store, index, root_record)
                        if probe:
                            return probe
                    if exc.code.startswith(('INDEPENDENT_', 'ORIGINAL_EXECUTOR_')) \
                            or exc.code in ('DISPATCH_LIVENESS_UNKNOWN', 'DISPATCH_REPLACEMENT_LAPSED'):
                        if exc.code in ('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'DISPATCH_LIVENESS_UNKNOWN') and publish:
                            return dispatch_identity.open_gate(store, index)
                        return dispatch_budget.pause(store, index, exc.code, error=exc, publish=publish)
                    raise
                if dispatch.get('state') not in ('EXHAUSTED', 'FALLBACK'):
                    _write_index(store, index)
                    waiting = dict(schema_version=1, run=dict(trace_id=index['trace_id'], state=index['run_state']),
                        node=dict(name=active_entry['name'], kind=active_entry['kind']), steps=[],
                        dispatch=dispatch, public_plan=None, public_plan_ref=None,
                        gate=dict(required=False, state='CLEAR'), resume=dict(kind='scope_wait', source=None))
                    prev_ref = _prev_dispatched_block_ref(store, index)
                    if prev_ref:
                        waiting['prev_public_block_ref'] = prev_ref
                        from . import dispatch_publication
                        waiting['previous_dispatch_publication'] = dispatch_publication.previous(store, index, prev_ref)
                    return waiting
        if index["run_state"] == "RUNNING" and _open_frames(store, index, program, agent_ticket=agent_ticket):
            _write_index(store, index)
        state = index["run_state"]
        base = {"schema_version": 1, "run": {"trace_id": index["trace_id"], "state": state},
                "program": _program_group(index), "schema_ref": "schemas/commit.v1.json",
                "program_binding": {"status": 'MATCH' if program and run_input.get('program_binding_policy') else
                                    'NOT_LOADED' if run_input.get('program_binding_policy') else 'LEGACY_UNBOUND'}}
        if entry_contracts is not None:
            base["entry_contracts"] = entry_contracts
        clear_gate = {"state": "CLEAR", "required": False, "source": "none", "kind": None, "prompt_text": None, "public_prompt": None, "advisory": False}
        if state in TERMINAL_STATES:
            base.update({"node": None, "steps": [], "reserved": None, "topology": None, "input_authority": None, "budget": None,
                         "gate": clear_gate, "resume": {"kind": "terminal_continuation", "source": index["run_termination"].get("kind")},
                         "public_plan": None, "public_plan_ref": None, "final_answer": _final_answer_text(store) if state == "COMPLETED" else None,
                         "final_answer_block": _final_block_text(store) if state == "COMPLETED" else None,   # alpha.23 R4
                         "final_answer_ref": _ref(store, "final_answer.txt") if state == "COMPLETED" else None,   # alpha.27 R1
                         "evidence_block": _evidence_block_text(store) if state == "COMPLETED" else None,
                         "evidence_ref": _ref(store, "evidence.txt") if state == "COMPLETED" else None,
                         "error_report": _error_report(store, index) if state != "COMPLETED" else None,
                         "error_report_ref": _ref(store, "ended.txt") if state != "COMPLETED" else None})
            base.update(_terminal_delivery(store, index))
            return base
        if state == "WAITING_USER":
            gate = store.read_json(store.gate_path(index["gate"]["question_id"]))
            entry = _catalog_entry(index, index["current"]["name"])
            _, current_dispatch = _self_dispatch(index, entry, index['current']['visit'])
            if publish and current_dispatch and current_dispatch.get('scope_root') and current_dispatch.get('paused_at') \
                    and not (gate.get('program_drift') or gate.get('dispatch_block')) and _unshown_stop(store, index, gate):
                return dispatch_identity.open_gate(store, index, business=gate)
            menu = gate.get('clarification_menu') or f"menu.{gate['question_id']}.txt"
            if _unshown_stop(store, index, gate):
                # docs/05SoulRun 90 round 5 (problem 95, ledger decision 185): a business gate the human has not been shown
                # (_finish_pause's index write landed, the process died before its menu; round 7, decision 187 (a): a
                # sub-agent's pause whose return the host has not recorded - decision 189: the main executor calls this
                # next-node before presenting a returned gate, in every host) is published by the main executor's serve, as
                # _finish_pause publishes it (_show_unshown_gate); a sub-agent is served a gate not yet shown plain, naming no
                # menu (_open_frames' stop included)
                if not publish:
                    menu = None
                elif not (gate.get('program_drift') or gate.get('dispatch_block')):
                    _show_unshown_gate(store, index, gate)
            base.update({"node": {"name": entry["name"], "kind": entry["kind"], "parent": entry.get("parent"), "depth": entry["depth"],
                                  "bare": _bare(entry), "position": _position(index), "mode": None},
                         "steps": [], "reserved": None, "topology": None, "input_authority": None, "budget": None,
                         "gate": {"state": "WAITING_USER", "required": True, "source": gate["source"], "kind": gate["kind"],
                                  "prompt_text": gate.get("prompt_text"), "public_prompt": render.menu_block(gate, user_language=index.get("user_language")),
                                  "public_prompt_ref": _ref(store, menu) if menu else None, "advisory": False},   # alpha.27 R1
                         "resume": {"kind": "waiting_user", "source": gate["question_id"]}, "public_plan": None, "public_plan_ref": None,
                         "public_block": _pause_block_text(store, gate["question_id"]),   # alpha.25: the ⏸ mid-state node info
                         "public_block_ref": _pause_ref(store, gate["question_id"])})
            if publish:
                _, owner = _self_dispatch(index, entry, index['current']['visit'])
                if owner and owner.get('scope_root'):
                    # Presentation only: retain the child's plans and accepted receipts before this gate.
                    base['dispatch'] = dispatch_scope.view(owner)
            return base
        entry = _catalog_entry(index, index["current"]["name"])
        visit = index["current"]["visit"]
        if (not agent_ticket or dispatch_scope.enabled(index)) and program:
            reason = dispatch_budget.preflight(index, program, entry, store=store)
            if reason:
                return dispatch_budget.pause(store, index, reason, publish=publish)
        restored_payloads = program_guard.restored_payloads(store, index, entry['name'], visit)
        if restored_payloads:
            base['pending_payload_refs'] = restored_payloads
        node_entry = index["nodes"].setdefault(_node_key(entry["name"], visit), RunStore.new_node_entry(visit))
        # doc 15 F1 (alpha.10): "first serve" means this occurrence was never served by next-node. ready_at cannot
        # decide that - _open_frame and _close_frame both stamp a module node's ready_at before the node is ever served,
        # which made the module node's own turn after its sub-graph look like a re-serve (cache/12 DelegateAnalysis).
        first_serve = int(node_entry.get("serves") or 0) == 0
        preparing = dispatch_scope.enabled(index) and not agent_ticket and not dispatch_scope.pending_root(index, entry, visit) \
            and _should_dispatch(index, program, entry)
        if first_serve and not preparing:
            node_entry["ready_at"] = node_entry["ready_at"] or now_iso()
            node_entry["status"] = "ACTIVE"
            if dispatch_lifecycle.replacement_accounting(index):
                try:
                    node_entry['resume_capture_boundary'] = sorted(p.name for p in store.proc_dir.iterdir()) if store.proc_dir.is_dir() else []
                except OSError:
                    pass  # No trustworthy inventory: keep the legacy timestamp diagnostic.
        if preparing:
            node_entry['prepares'] = node_entry.get('prepares', 0) + 1
        else:
            node_entry["serves"] = int(node_entry.get("serves") or 0) + 1
        gate_answer = _pending_gate_answer(store, index, entry["name"], visit)
        # doc 14 D7: a second next-node for the same occurrence without a gate answer is `re_serve` (formerly
        # `crash_reentry`, which named a host crash the engine cannot see: in cache/7 all ten were the main agent
        # re-reading the plan after a rejected commit or --help). The reply carries resume.serve_no.
        resume_kind = "same_occurrence" if gate_answer else ("fresh" if first_serve else "re_serve")
        mode = _executor_mode(index, program, entry, visit)
        dispatch = None
        if dispatch_scope.enabled(index) and not agent_ticket:
            _, inherited = _self_dispatch(index, entry, visit)
            if inherited and inherited.get('state') in {'EXHAUSTED', 'FALLBACK'}:
                dispatch = _dispatch_view(store, inherited)
                mode = dict(mode, effective='inline', downgrade='DISPATCH_EXHAUSTED')
        reissued_claim = False
        if agent_ticket:   # the sub-agent: bind to the ticket of this occurrence (its outer node for a sub node)
            d, claimed_now = _claim_ticket(store, index, entry, visit, agent_ticket)
            if claimed_now and not gate_answer:
                resume_kind = "fresh"
            # alpha.106 review fix (doc 265 E3 amendment): the claim of a re-issued ticket (attempt > 1: Stop -> continue abandoned the
            # earlier sub-agent, or it failed) resumes an occurrence an earlier sub-agent may have worked on - it carries the brief too
            reissued_claim = claimed_now and int(d.get("attempt") or 1) > 1
            dispatch = {"required": False, "state": d["state"], "ticket": d["ticket"], "attempt": d["attempt"], "actor": "sub_agent",
                        "scope": "this node occurrence only", "closed": False, "wait": False, "bootstrap": None,
                        "note": "Do this node's steps and commit it with node-commit --agent-ticket; the commit result says dispatch.closed = true, then stop."}
            if d.get('scope_root'):
                dispatch.update(dispatch_scope.view(d, include_refs=False), note='Commit each reached node with this ticket. Use next_plan until dispatch.closed; return public_refs in order.')
            elif mode["effective"] != "agent":
                mode = dict(mode, effective="agent")
        elif mode["effective"] == "agent" or preparing:
            if (node_entry.get("dispatch") or {}).get("mode") == "inline":
                node_entry["dispatch"] = None
            try:
                dispatch = _main_agent_dispatch(store, index, node_entry, entry, visit, gate_answer, abandon, abandon_reason,
                                                 pool=dispatch_budget.pool(program, entry))
            except EngineError as exc:
                if exc.code.startswith(('INDEPENDENT_', 'BLIND_REVIEW_', 'ORIGINAL_EXECUTOR_')) \
                        or exc.code in ('DISPATCH_LIVENESS_UNKNOWN', 'DISPATCH_REPLACEMENT_LAPSED'):
                    return dispatch_budget.pause(store, index, exc.code, error=exc, publish=publish)
                raise
            if dispatch["state"] == "EXHAUSTED":
                mode = dict(mode, effective="inline", downgrade="DISPATCH_EXHAUSTED")
        elif mode["downgrade"] in ("NORMAL_MODE_FORCES_INLINE", "SPAWN_BUDGET_EXHAUSTED", "EXECUTE_MODE_UNKNOWN", "HOST_NO_AGENT_TOOL") and not node_entry.get("dispatch"):
            # declared agent, runs inline: record the downgrade once on this occurrence
            node_entry["dispatch"] = {"mode": "inline", "ticket": None, "attempt": 0, "state": "INLINE", "reason": None, "issued_at": None,
                                      "claimed_at": None, "committed_at": None, "paused_at": None, "actor": "main_agent",
                                      "bootstrap_sha256": None, "downgrade": mode["downgrade"], "fallback": None, "history": []}
        hands_out_steps = bool(agent_ticket) or not (dispatch and (dispatch.get("required") or dispatch.get("wait")))   # alpha.106 (doc 265 E3)
        _write_index(store, index)
        reply = _build_reply(store, index, run_input, program, entry, visit, resume_kind, gate_answer, mode=mode, dispatch=dispatch,
                             write_plan=not (dispatch and dispatch.get("wait")), sub_agent=bool(agent_ticket))
        if dispatch and dispatch.get("required") and not agent_ticket:
            reply["steps"] = []   # the steps are the sub-agent's: the main agent only spawns it
            if dispatch_scope.enabled(index):
                # docs/05SoulRun 87 (record 86 #2): the dispatch view a gate resume already gives the main agent (scope_wait above) - a
                # view for the party that does not execute the node, not a fold; run 7 sent it 32-69 KB of node package 17 times. The
                # contract ledger of the main session then records only the sections it was given.
                reply = {key: reply[key] for key in MAIN_DISPATCH_VIEW if key in reply}
                reply['payload_rules'] = [rule for rule in reply.get('payload_rules') or []
                                          if getattr(rule, 'key', None) in MAIN_DISPATCH_SECTIONS]
        if dispatch_scope.enabled(index) and agent_ticket:
            _, record = _self_dispatch(index, entry, visit)
            dispatch_scope.append_ref(record, reply.get('public_plan_ref'))
        if not agent_ticket:
            prev_ref = _prev_dispatched_block_ref(store, index)   # alpha.62 (doc 135 G3): the block a sub-agent just committed
            if prev_ref:
                reply["prev_public_block_ref"] = prev_ref
                from . import dispatch_publication
                reply['previous_dispatch_publication'] = dispatch_publication.previous(store, index, prev_ref)
        if dispatch_scope.enabled(index) and dispatch:
            reply['payload_rules'].append(_contracts.text('resume.dispatch_segments'))
        _deliver_contracts(index, reply, session=session, sub_agent=bool(agent_ticket))   # alpha.100 (doc 241): mixed contract delivery
        _write_index(store, index)
        reply.update(base)
        if hands_out_steps and (resume_kind in ("same_occurrence", "re_serve") or reissued_claim) and entry["kind"] in ("business", "sub"):   # alpha.106 (doc 265 E3)
            _attach_resume_brief(store, index, entry, visit, reply, printed=(session == "new"))
        from . import blind_review
        from . import independent_inputs
        return independent_inputs.filter_reply(store, index, blind_review.filter_reply(store, index, reply))


# --- alpha.106 (04 series doc 265 E3): the resume brief ------------------------------------------------------------------------------
# What this occurrence already did before a same_occurrence / re_serve of a business or sub node that hands out steps (a gate answer,
# Stop -> continue, a supply re-entry, a fresh CLI turn): data in input_authority, never a rule; a resumed session read _proc, the replies
# and the node cache for it (production 51: seven exploration calls) or re-ran a done step (49).
RESUME_BRIEF_MAX_BYTES = 2_500   # UTF-8 bytes of the compact JSON
RESUME_BRIEF_ITEM_CHARS = 120
RESUME_BRIEF_HEAD_CHARS = 120
RESUME_BRIEF_MAX_CAPTURES = 12
RESUME_BRIEF_NOTE = (
    "What this occurrence already did before this serve, from the engine's records: do not re-run its done steps unless gate_answer asks "
    "for it, and do not re-list _proc or re-read replies or the node cache for it; Read a listed capture only for content a remaining step "
    "needs. A new capture takes next_capture."
)
RESUME_BRIEF_LEVELS = 5   # L1 texts / heads to 60 characters, L2 heads dropped, L3 six capture rows, L4 tool calls counted and item texts dropped, L5 core only


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _proc_rel(path) -> str:
    """a stdout_path as the brief names captures: `_proc/<name>` (an absolute or backslash path cut at its _proc/ segment)"""
    text = str(path or "").replace("\\", "/")
    at = text.rfind("_proc/")
    return text[at:] if at >= 0 else text


def _attach_resume_brief(store: RunStore, index: dict, entry: dict, visit: int, reply: dict, *, printed: bool) -> None:
    """alpha.106 (doc 265 E3): input_authority.resume_brief. Never raises - the brief is an aid; a resume (gate answer, Stop -> continue,
    supply recovery) never fails on it. The index is already written and the brief writes nothing, so a failure leaves the run exactly
    as a serve without a brief. printed: the reply is printed by next_node (a new session) - the brief never pushes a reply that would
    print within reply_io.PRINT_CAP over it."""
    ia = reply.get("input_authority")
    if not isinstance(ia, dict):
        return
    if not (reply.get('dispatch') or {}).get('scope_root') and _host_has_fences(index):
        ready = (index['nodes'].get(_node_key(entry['name'], visit)) or {}).get('ready_at')
        reply.setdefault('node_facts', {})['report_input'] = _report_input_state(store, entry['name'], visit, ready)['status']
    try:
        raw = _resume_brief(store, index, entry, visit)
        if raw:
            for ref in ia.get("input_refs") or []:
                ref.pop("output_shape", None)
            brief = _cap_resume_brief(raw)
            ia["resume_brief"] = _fit_resume_brief(raw, brief, reply, store.cache_dir, entry["name"]) if printed else brief
        from . import sealed_diagnostics
        own = [c for c in _prev_business_caches(store, index) if c['node'] == entry['name'] and c['visit'] == visit]
        diagnostics = sealed_diagnostics.summary(store, own)
        if diagnostics:
            ia['sealed_capture_diagnostics'] = diagnostics
    except Exception as exc:  # noqa: BLE001 - the brief is an aid; a resume never fails on it
        ia["resume_brief"] = {"omitted": True, "reason": f"brief unavailable: {type(exc).__name__}"}


def _host_has_fences(index):
    return 'report' in ((index.get('host') or {}).get('host_fences') or [])


def _report_input_state(store, node, visit, ready_at):
    result = dict(node=node, visit=visit, status='NOT_CAPTURED', semantic_currentness='UNVERIFIED')
    path = store.cache_dir/host_report_name(node)
    try:
        if path.is_symlink():
            return dict(result, status='CAPTURE_UNAVAILABLE')
        if not path.exists() or not path.read_text(encoding='utf-8').strip():
            return result
        ready = datetime.fromisoformat(ready_at.replace('Z', '+00:00')).timestamp() if ready_at else None
        return dict(result, status='STALE_CAPTURE' if ready and path.stat().st_mtime < ready-HOST_TEXT_FRESH_SLACK_S else 'CAPTURE_PRESENT')
    except (OSError, UnicodeDecodeError, ValueError):
        return dict(result, status='CAPTURE_UNAVAILABLE')


def _brief_before(record: dict) -> tuple[dict, set, dict]:
    """the LAST record of the occurrence's node cache as the brief states it; returns (before, cited capture paths, exit code by path)"""
    payload = record.get("payload") or {}
    machine = record.get("machine") or {}
    calls = [t for t in ((payload.get("evidence") or {}).get("tool_calls") or []) if isinstance(t, dict)]
    cited = {_proc_rel(t["stdout_path"]) for t in calls if t.get("stdout_path")}
    exits = {_proc_rel(t["stdout_path"]): t["exit_code"] for t in calls if t.get("stdout_path") and type(t.get("exit_code")) is int}
    decl = payload.get("user_message") if isinstance(payload.get("user_message"), dict) else {}
    items = []
    for it in decl.get("items") or []:
        if not isinstance(it, dict):
            continue
        row = {"step": it.get("step"), "kind": it.get("kind")}
        if it.get("text"):
            row["text"] = str(it["text"])[:RESUME_BRIEF_ITEM_CHARS]
        elif it.get("what"):
            row["what"] = str(it["what"])[:RESUME_BRIEF_ITEM_CHARS]
        row["chars"] = len(str(it.get("text") or it.get("what") or ""))
        items.append(row)
    before = {"status": payload.get("status"), "paused_gate": machine.get("paused_gate"), "committed_at": machine.get("committed_at"),
              "steps": payload.get("steps"),
              "tool_calls": [{k: t[k] for k in ("step", "tool", "stdout_path") if t.get(k)} for t in calls],
              "user_message": {"has": decl.get("has"), "items": items,
                               "not_applicable": [{"step": na.get("step")} for na in decl.get("not_applicable") or [] if isinstance(na, dict)]},
              "user_messages_chars": [len(m) for m in payload.get("user_messages") or [] if isinstance(m, str)]}
    return before, cited, exits


def _resume_brief(store: RunStore, index: dict, entry: dict, visit: int) -> dict | None:
    """alpha.106 (doc 265 E3): the uncapped brief of this occurrence, or None when there is nothing to state (no earlier record of the
    occurrence, no capture). Every file access has its own guard. Revision 5 (E1 withdrawn): no payload file is stated - a file written
    before this serve is never offered for resubmission, as in alpha.105."""
    cache = store.cache_dir
    key = _node_key(entry["name"], visit)
    ready = [_parse_ts(s) for s in [(index["nodes"].get(key) or {}).get("ready_at")] if isinstance(s, str) and s]
    others = [_parse_ts(s) for s in [n.get("committed_at") for k, n in index["nodes"].items() if k != key] if isinstance(s, str) and s]
    times = ready + others
    since = max(times) if times else None   # the start of this occurrence's own work
    # alpha.106 review fix (doc 265 E3 amendment): an uncited capture counts from ready_at less the alpha.68 slack, never from before
    # another node's latest commit - a capture the previous node wrote just before its commit is that node's, not this occurrence's
    bounds = [t.timestamp() - HOST_TEXT_FRESH_SLACK_S for t in ready] + ([max(others).timestamp()] if others else [])
    threshold = max(bounds) if bounds else None
    inventory = (index['nodes'].get(key) or {}).get('resume_capture_boundary')
    inventory = set(inventory) if isinstance(inventory, list) and all(isinstance(n, str) for n in inventory) else None
    brief: dict = {"occurrence": f"{entry['name']}@{visit}", "since": _iso_from_ts(since.timestamp()) if since else None}
    cited: set = set()
    exits: dict = {}
    try:
        path = _cache_path_for(store, index, entry, visit)
        if store.exists_path(path):
            cached = store.read_json(path)
            record = (cached.get("continuations") or [cached])[-1]
            brief["before"], cited, exits = _brief_before(record)
    except Exception as exc:  # noqa: BLE001 - an unreadable node cache gives no `before`, never a failed serve
        brief["before_error"] = type(exc).__name__
    rows, skipped = [], 0
    proc = cache / "_proc"
    for name in sorted(p.name for p in proc.iterdir()) if proc.is_dir() else []:
        if name.startswith("sha256-") or name.endswith((".exit", ".err")):
            continue
        rel = f"_proc/{name}"
        capture = proc / name
        try:   # one row per capture; one that cannot be stat'ed or read is skipped and counted
            st = capture.stat()
            fresh = threshold is not None and st.st_mtime >= threshold
            if inventory is not None:
                own_capture = re.fullmatch(re.escape(_bare(entry)) + r'\.\d+\.out', name) is not None
                fresh = name not in inventory and (own_capture or fresh)
            if not stat.S_ISREG(st.st_mode) or not (rel in cited or fresh):
                continue
            code = exits.get(rel)
            exit_file = capture.with_suffix(".exit")
            if exit_file.is_file():
                raw_exit = exit_file.read_text(encoding="utf-8", errors="replace").strip()
                if re.fullmatch(r"-?\d+", raw_exit):
                    code = int(raw_exit)
            with capture.open("rb") as handle:
                head = " ".join(handle.read(2048).decode("utf-8", errors="replace").split())[:RESUME_BRIEF_HEAD_CHARS]
            rows.append({"path": rel, "bytes": st.st_size, **({"exit": code} if code is not None else {}), "cited": rel in cited, "head": head})
        except OSError:
            skipped += 1
    brief["captures"] = rows[:RESUME_BRIEF_MAX_CAPTURES]
    if len(rows) > RESUME_BRIEF_MAX_CAPTURES:
        brief["captures_more"] = len(rows) - RESUME_BRIEF_MAX_CAPTURES
    if skipped:
        brief["captures_skipped"] = skipped
    brief["next_capture"] = reply_io.next_numbered(cache, "_proc", _bare(entry), ".out")
    brief["note"] = RESUME_BRIEF_NOTE
    if not ("before" in brief or "before_error" in brief or rows or skipped):
        return None
    return brief


def _brief_bytes(brief: dict) -> int:
    return len(json.dumps(brief, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _brief_level(raw: dict, level: int) -> dict:
    """the deterministic byte ladder of doc 265 §1.E3, levels 1..level applied to a copy of the uncapped brief; a trimmed brief records
    the level reached as capped_at"""
    brief = copy.deepcopy(raw)
    if level <= 0:
        return brief
    before = brief.get("before") or {}
    items = (before.get("user_message") or {}).get("items") or []
    rows = brief.get("captures") or []
    for it in items:   # L1
        for k in ("text", "what"):
            if k in it:
                it[k] = it[k][:60]
    for r in rows:
        if "head" in r:
            r["head"] = r["head"][:60]
    if level >= 2:
        for r in rows:
            r.pop("head", None)
    if level >= 3 and len(rows) > 6:
        brief["captures_more"] = brief.get("captures_more", 0) + len(rows) - 6
        brief["captures"] = rows[:6]
    if level >= 4 and before:
        before["tool_calls_count"] = len(before.pop("tool_calls", None) or [])
        for it in items:
            it.pop("text", None)
            it.pop("what", None)
    if level >= 5:
        core = {"occurrence": brief["occurrence"]}
        if before:
            core["before"] = {k: before.get(k) for k in ("status", "paused_gate", "steps")}
        core["items_count"] = len(items)
        core["captures_count"] = len(raw.get("captures") or []) + raw.get("captures_more", 0)
        for k in ("next_capture", "note"):
            core[k] = brief[k]
        brief = core
    brief["capped_at"] = f"L{level}"
    return brief


def _cap_resume_brief(raw: dict) -> dict:
    """the first ladder level whose compact JSON is at most RESUME_BRIEF_MAX_BYTES (L5 at the latest)"""
    for level in range(RESUME_BRIEF_LEVELS + 1):
        brief = _brief_level(raw, level)
        if _brief_bytes(brief) <= RESUME_BRIEF_MAX_BYTES:
            return brief
    return _brief_level(raw, RESUME_BRIEF_LEVELS)


def _fit_resume_brief(raw: dict, brief: dict, reply: dict, cache_dir, node: str) -> dict:
    """alpha.106 (doc 265 E3, display-cap rule): measured with the printer's own reply_io.printed_size on the model view next_node prints
    (base keys, order, indent / compact, the folding of held values and previews). When the reply without the brief prints within
    reply_io.PRINT_CAP and with it would not, the brief steps down the ladder until it fits, else it is an omitted marker; a reply over the
    cap even without the brief keeps the byte-capped brief (the CLI saves it and the model reads it whole either way)."""
    path = reply_io.next_reply_file(cache_dir, "serve", node)

    def printed(value) -> int:
        ia = {k: v for k, v in reply["input_authority"].items() if k != "resume_brief"}
        if value is not None:
            ia["resume_brief"] = value
        return reply_io.printed_size(model_view.lean(dict(reply, input_authority=ia)), path)

    cap = reply_io.PRINT_CAP
    if printed(None) > cap or printed(brief) <= cap:
        return brief
    start = int(str(brief.get("capped_at") or "L0")[1:])
    for level in range(start + 1, RESUME_BRIEF_LEVELS + 1):
        candidate = _brief_level(raw, level)
        if printed(candidate) <= cap:
            return candidate
    return {"omitted": True, "reason": "the reply would pass the CLI display cap"}


def _prev_dispatched_block_ref(store: RunStore, index: dict) -> str | None:
    """alpha.62 (doc 135 §3.2 G3): the node block of the last committed occurrence when a sub-agent committed it - the main agent saw
    that reference only inside the sub-agent's returned text, so the next reply repeats it (present once)."""
    if not index.get("completed"):
        return None
    last = index["completed"][-1]
    d = (index["nodes"].get(_node_key(last["name"], last["visit"])) or {}).get("dispatch") or {}
    if d.get("mode") != "agent" or d.get("actor") != "sub_agent":
        return None
    entry = _catalog_entry(index, last["name"])
    if entry is None or entry["name"] in FINAL_NODES:
        return None
    name = f"node.{entry['ordinal'] + 1:02d}.{_safe_name(entry['name'])}.v{last['visit']}.txt"
    return _ref(store, name) if (store.public_dir / name).is_file() else None


def _open_frames(store: RunStore, index: dict, program, *, agent_ticket=None) -> bool:
    """At the cursor, open the module sub-graph of a module node (doc 05 §4.2): push a frame, plan the
    sub-graph's entry node as the current node. Repeats while the new current node is itself a module
    node (unlimited depth). Returns True when the index changed."""
    changed = False
    while index["run_state"] == "RUNNING":
        entry = _catalog_entry(index, index["current"]["name"])
        if not entry or entry["kind"] == "engine" or program is None:
            break
        visit = index["current"]["visit"]
        scope = dispatch_scope.pending_root(index, entry, visit) if dispatch_scope.enabled(index) else None
        if scope and scope['scope_root'] != dict(node=entry['name'], visit=visit) and dispatch_budget.pool(program, entry) == 'independent':
            break
        node_entry = index["nodes"].setdefault(_node_key(entry["name"], visit), RunStore.new_node_entry(visit))
        if node_entry.get("module"):
            break  # CLOSED: the module node's own steps are served now
        view = _view_for(program, entry)
        if view["module_unresolved"]:
            code = "MODULE_UNRESOLVED_INLINE"
            if not any(a["node"] == entry["name"] and a["code"] == code for a in index["anomalies_summary"]):
                index["anomalies_summary"].append({"node": entry["name"], "code": code,
                                                   "text": f"module target {view['module_unresolved']!r} has no sub-graph in this program; executed as a plain node"})
                changed = True
            break
        module = view["module"]
        same_file_graph = module and module['doc'] == program.entry_file
        if dispatch_scope.enabled(index) and agent_ticket and same_file_graph:
            # docs/05SoulRun 90 round 5 (ledger decision 185): opened for a sub-agent's next-node - not published (_serve)
            dispatch_budget.pause(store, index, 'SUBTREE_MAIN_GRAPH_SCOPE_CONFLICT', publish=not agent_ticket)
            return True
        if dispatch_scope.enabled(index) and not agent_ticket and not same_file_graph \
                and _dispatch_policy(index) == DISPATCH_POLICY_NODE and dispatch_scope.is_main(index, entry) \
                and _declared_mode(program, entry) == 'agent' and not scope:
            break
        if not module or not module.get("entry_node"):
            break
        from . import module_order
        if module_order.pending(index, entry, visit, module_order.boundary(program, entry, view)):
            changed = module_order.capture_cache(store, index, program, entry, visit, view) or changed
            break
        stuck = _recursion_without_progress(index, module)
        if stuck:
            _terminate(index, kind="fatal", by="engine", reason=f"MODULE_RECURSION_NO_PROGRESS: {stuck}")
            return True
        _open_frame(store, index, entry, visit, node_entry, module)
        changed = True
    return changed


def _recursion_without_progress(index: dict, module: dict) -> str | None:
    """Immediate self-recursion guard (not a depth cap): the same sub-graph is opened again while no node
    has been committed since an earlier frame of it was opened -> the run could never progress."""
    stack = index["call_stack"]
    for i, frame in enumerate(stack):
        if frame["doc"] == module["doc"] and frame["task"] == module["task"] and all(f["order"] == 0 for f in stack[i:]):
            return f"{module['doc']}:{module['task']} re-entered at depth {len(stack) + 1} with no node committed since it opened at depth {i + 1}"
    return None


def _open_frame(store: RunStore, index: dict, entry: dict, visit: int, node_entry: dict, module: dict) -> None:
    now = now_iso()
    if node_entry["ready_at"] is None:
        node_entry["ready_at"] = now
        node_entry["status"] = "ACTIVE"
    parent_id, depth = entry["name"], entry["depth"] + 1
    dir_rel = RunStore.frame_dir_rel(parent_id)
    frame = {"parent": parent_id, "parent_visit": visit, "doc": module["doc"], "task": module["task"], "ns": module["ns"],
             "dir": dir_rel, "entered_at": now, "order": 0}
    index["call_stack"].append(frame)
    node_entry["module"] = {"state": "OPEN", "doc": module["doc"], "task": module["task"], "ns": module["ns"], "dir": dir_rel,
                            "entry_node": module["entry_node"], "opened_at": now, "closed_at": None, "status": None,
                            "sub_count": 0, "status_counts": {}, "max_depth": depth, "manifest_sha256": None}
    first = program_loader.sub_entry(parent_id, depth, module["doc"], module["task"], module["ns"], module["entry_node"], entry["ordinal"] + 1)
    _splice(index, entry["ordinal"], [first])
    _set_current(index, first["name"], parent=parent_id, parent_visit=visit, depth=depth, order=0)
    _update_manifest(store, index, frame)


def _update_manifest(store: RunStore, index: dict, frame: dict, *, state: str = "OPEN", status: str | None = None,
                     closed_at: str | None = None) -> str:
    """Engine-owned _<Parent>/_manifest.json: rewritten atomically on open, after every sub commit and on close."""
    entries, counts, nested_depths = [], {}, []
    for key, ne in _frame_children(index, frame["parent"], frame["parent_visit"]):
        name, _, v = key.partition("@")
        visit = int(v[1:]) if v else 1
        local = _local(name)
        counts[ne["status"] or "PLANNED"] = counts.get(ne["status"] or "PLANNED", 0) + 1
        mod = ne.get("module") or {}
        if mod:
            nested_depths.append(mod.get("max_depth") or 0)
        entries.append({"id": name, "local": local, "node": local.split(".", 1)[-1], "visit": visit, "order": ne.get("order"),
                        "status": ne["status"], "path": f"{frame['dir']}/{local}{'' if visit <= 1 else f'.visit{visit}'}.json",
                        "cache_sha256": ne["cache_sha256"], "logical_tool_calls": ne["logical_tool_calls"],
                        "sources_count": ne["sources_count"], "artifacts": len(ne["artifacts"]),
                        "module": {"dir": mod["dir"], "state": mod["state"], "status": mod["status"], "manifest_sha256": mod["manifest_sha256"]} if mod else None})
    child_ids = {e["id"] for e in entries}
    committed = [e for e in entries if e["status"] in ("COMMITTED", "DEGRADED", "FAILED")]
    manifest = {"schema_version": 1, "engine_version": ENGINE_VERSION, "trace_id": index["trace_id"],
                "parent": frame["parent"], "parent_visit": frame["parent_visit"], "doc": frame["doc"], "task": frame["task"], "ns": frame["ns"],
                "dir": frame["dir"], "state": state, "status": status, "opened_at": frame["entered_at"], "closed_at": closed_at,
                "entries": entries, "sub_count": len(committed), "status_counts": counts,
                "total_tool_calls": sum(e["logical_tool_calls"] for e in entries), "sources_total": sum(e["sources_count"] for e in entries),
                "artifacts_total": sum(e["artifacts"] for e in entries),
                "anomalies_total": sum(1 for a in index["anomalies_summary"] if a["node"] in child_ids),
                "max_depth": max([len(frame["parent"].split("/"))] + nested_depths)}
    return store.write_json(store.manifest_path(frame["parent"]), manifest)


def _close_frame(store: RunStore, index: dict, frame: dict, *, status: str | None, reason: str | None, closed_at=None) -> None:
    """The sub-graph reached its end node (or failed without a handler): pop the frame, finalise the manifest,
    hand the cursor back to the module node whose own steps are served next (doc 05 §4.2)."""
    now = closed_at or now_iso()
    if index["call_stack"] and index["call_stack"][-1] is frame:
        index["call_stack"].pop()
    else:
        index["call_stack"] = [f for f in index["call_stack"] if f is not frame]
    children = _frame_children(index, frame["parent"], frame["parent_visit"])
    counts: dict = {}
    for _, ne in children:
        counts[ne["status"] or "PLANNED"] = counts.get(ne["status"] or "PLANNED", 0) + 1
    if status is None:
        status = "DEGRADED" if any(ne["status"] in ("DEGRADED", "FAILED") for _, ne in children) else "PASS"
    pkey = _node_key(frame["parent"], frame["parent_visit"])
    pentry = index["nodes"][pkey]
    depth = (pentry.get("depth") or 0) + 1
    max_depth = max([depth] + [(ne.get("module") or {}).get("max_depth", 0) for _, ne in children])
    sha = _update_manifest(store, index, frame, state="CLOSED", status=status, closed_at=now)
    pentry["module"].update({"state": "CLOSED", "closed_at": now, "status": status, "sub_count": len(children),
                             "status_counts": counts, "max_depth": max_depth, "manifest_sha256": sha})
    pentry["ready_at"] = now      # the module node's own work starts now; the sub-graph's time is in the manifest
    pentry["status"] = "ACTIVE"
    index["current"] = {"name": frame["parent"], "visit": frame["parent_visit"]}
    if reason:
        index["anomalies_summary"].append({"node": frame["parent"], "code": "SUBGRAPH_FAILED", "text": reason})


def _clip_output(output, cap: int = SIBLING_OUTPUT_CAP):
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    if len(text) <= cap:
        return output, False
    return text[:cap] + "…", True


def _module_last_output(output, cache_path, cache_dir):
    """alpha.48 C3' (doc 80 §5 / doc 101): the module node is served its sub-graph's last output; production cache/66 carried a
    52k claims ledger there (a 152k reply, far past the host's 30k output cap). Above MODULE_OUTPUT_INLINE_MAX the output rides
    as a marker - size, digest, where it lives, how to read it - and the model reads it through input_authority.input_refs only
    when a remaining step needs it."""
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    if len(text) <= MODULE_OUTPUT_INLINE_MAX:
        return output
    try:
        where = Path(cache_path).relative_to(Path(cache_dir)).as_posix()
    except ValueError:
        where = Path(cache_path).name
    return {"output_omitted": True, "chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "cache": where,
            "read": "the complete output stays in that sub node's cache (payload.output); read it through input_authority.input_refs "
                    "(next_node.py --read-input-ref <ref> --input-field output) only when a remaining step needs it"}


def _sibling_output(output, cache_path, cache_dir):
    """alpha.49 (doc 102 §4 #3 / doc 103): frame.siblings and module.sub_nodes carry a sibling's output inline only when it is
    small; above SIBLING_OUTPUT_INLINE_MAX it rides as a marker with a 300-character preview (size, digest, where it lives, how to
    read it). Production cache/72: the 3,000-character clips of five to seven siblings made 14-21k of every sub-graph reply - the
    part the host's 30k output cap cut first - and GenerateReport finished from input_refs regardless. Returns (output, truncated)."""
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    if len(text) <= SIBLING_OUTPUT_INLINE_MAX:
        return output, False
    try:
        where = Path(cache_path).relative_to(Path(cache_dir)).as_posix()
    except ValueError:
        where = Path(cache_path).name
    return {"output_omitted": True, "chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "preview": text[:120] + "…",
            "cache": where, "read": "complete output through input_authority.input_refs (next_node.py --read-input-ref <ref> --input-field output)"}, True


def _frame_siblings(store: RunStore, index: dict, parent: str, parent_visit: int) -> list[dict]:
    """Committed sub nodes of one module occurrence with their outputs (doc 06 §3): what a sub node or the
    module node needs from its frame without re-reading cache files. Outputs are clipped per node and the
    oldest are reduced to identity when the projection would exceed SIBLINGS_TOTAL_CAP."""
    out = []
    for key, ne in _frame_children(index, parent, parent_visit):
        if ne["status"] not in ("COMMITTED", "DEGRADED", "FAILED"):
            continue
        name, _, v = key.partition("@")
        visit = int(v[1:]) if v else 1
        item = {"id": name, "node": _local(name).split(".", 1)[-1], "order": ne.get("order"), "status": ne["status"],
                "logical_tool_calls": ne["logical_tool_calls"], "sources_count": ne["sources_count"],
                "module": (ne.get("module") or {}).get("status")}
        child = _catalog_entry(index, name)
        path = _cache_path_for(store, index, child, visit) if child else None
        if path and store.exists_path(path):
            payload = _latest_payload(store.read_json(path))
            output, truncated = _sibling_output(payload.get("output"), path, store.cache_dir)   # alpha.49: marker + preview above SIBLING_OUTPUT_INLINE_MAX
            item.update({"output": output, "output_truncated": truncated, "user_summary": (payload.get("user_summary") or "")[:300]})
            if payload.get("vars"):   # alpha.50: an empty vars object carries nothing
                item["vars"] = payload.get("vars")
        out.append(item)
    i = 0
    while len(json.dumps(out, ensure_ascii=False)) > SIBLINGS_TOTAL_CAP and i < len(out):
        out[i] = {k: out[i][k] for k in ("id", "node", "order", "status", "module")} | {"output_omitted": True}
        i += 1
    return out


def _module_result(store: RunStore, index: dict, entry: dict, visit: int) -> dict | None:
    """What the module node is served after its sub-graph closed: statuses, last node's output, evidence roll-up."""
    node_entry = index["nodes"].get(_node_key(entry["name"], visit)) or {}
    mod = node_entry.get("module")
    if not mod or mod["state"] != "CLOSED":
        return None
    children = _frame_children(index, entry["name"], visit)
    subs, artifacts, sources, last = _frame_siblings(store, index, entry["name"], visit), [], 0, None
    for key, ne in children:
        name, _, v = key.partition("@")
        artifacts.extend(ne["artifacts"])
        sources += ne["sources_count"]
        last = (name, int(v[1:]) if v else 1)
    last_node = None
    if last:
        child = _catalog_entry(index, last[0])
        path = _cache_path_for(store, index, child, last[1]) if child else None
        if path and store.exists_path(path):
            payload = _latest_payload(store.read_json(path))
            last_node = {"id": last[0], "status": payload["status"], "output": _module_last_output(payload["output"], path, store.cache_dir), "user_summary": payload["user_summary"],
                         "vars": payload.get("vars")}
    child_ids = {s["id"] for s in subs}
    return {"state": "CLOSED", "status": mod["status"], "dir": mod["dir"], "doc": mod["doc"], "task": mod["task"],
            "manifest": {"path": f"{mod['dir']}/{MANIFEST}", "sha256": mod["manifest_sha256"]},
            "sub_count": mod["sub_count"], "status_counts": mod["status_counts"], "max_depth": mod["max_depth"],
            "sub_nodes": subs, "last_node": last_node, "artifacts": artifacts, "sources_total": sources,
            "anomalies": [{"node": a["node"], "code": a["code"], "text": a["text"]} for a in index["anomalies_summary"] if a["node"] in child_ids]}


def _program_group(index: dict) -> dict | None:
    pg = index["program"]
    if not pg.get("name"):
        return None
    result = {"aiap_name": pg["name"], "trust_level": pg["trust_level"], "permissions_digest": pg["permissions_digest"],
            "loading_mode": pg["loading_mode"], "execution_loading_mode": _effective_loading_mode(index),
            "entry_path": pg["entry_path"]}
    if _no_agent_normal(index):
        result['mode_selection_reason'] = 'HOST_NO_AGENT_TOOL'
    return result


def _position(index: dict) -> dict:
    return _track_position(index, _catalog_entry(index, index["current"]["name"]), index["current"]["visit"])


def _final_answer_text(store: RunStore) -> str | None:
    try:
        return store.final_answer_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _final_block_text(store: RunStore) -> str | None:
    """alpha.23 R4: the human_output_v5 envelope the engine wrote to _public/final_answer.txt."""
    try:
        return (store.public_dir / "final_answer.txt").read_text(encoding="utf-8")
    except OSError:
        return None


def _error_report(store: RunStore, index: dict) -> str:
    """alpha.25 (doc 47 item 1): the run-ended report carries the rejected gate (question + options + answer) and the
    stopped node's landed User Message / Report; both are read back from the run store, never from the model."""
    ended_path = store.public_dir / 'ended.txt'
    try:
        if store.exists_path(ended_path):
            return store.read_bytes(ended_path).decode('utf-8')
    except (OSError, RunStoreError, UnicodeError):
        pass  # A side-file failure must not suppress the terminal reply.
    term = index["run_termination"]
    gate = report = messages = None
    if term.get("rejection_report"):
        qid = (index.get("gate") or {}).get("question_id")
        try:
            gate = store.read_json(store.gate_path(qid)) if qid else None
        except Exception:  # noqa: BLE001 - the report must never fail the terminal reply
            gate = None
    cur = index.get("current") or {}
    try:
        entry = _catalog_entry(index, cur["name"])
        cache_path = _cache_path_for(store, index, entry, cur["visit"])
        if store.exists_path(cache_path):
            landed = _latest_payload(store.read_json(cache_path))
            report, messages = landed.get("user_summary"), landed.get("user_messages") or []
    except Exception:  # noqa: BLE001
        report = messages = None
    execution_report = None   # alpha.90 (doc 202 D): a run that ends after its execution report was committed still hands the human the accounting
    if cur.get("name") not in ACCOUNTING_NODES:
        try:
            accounting = _accounting_report_cache(store, index)
            execution_report = _latest_payload(accounting).get("user_summary") if accounting is not None else None
            if accounting:
                meta = (accounting.get('continuations') or [accounting])[-1].get('machine', {}).get('execution_report')
                if meta:
                    execution_report = meta['display']
        except Exception:  # noqa: BLE001 - the report must never fail the terminal reply
            execution_report = None
    facts = _fatal_facts(store, index) if term.get('kind') in {'fatal','human_termination'} else None
    if facts is not None and not (store.public_dir / 'ended.txt').exists():
        evidence_path = store.cache_dir / '_terminal_facts.json'
        try:
            if not store.exists_path(evidence_path):
                store.write_json(evidence_path, facts)
            if store.read_json(evidence_path) == facts:
                facts = dict(facts, evidence_ref=str(evidence_path))
        except (OSError, RunStoreError, ValueError):
            pass  # Full metadata stays inline if its evidence file cannot be preserved.
    text = render.error_report_block(term, cur.get("name"), [c for c in index["program"]["checks"] if c["severity"] == "FATAL"],
                                     index.get("user_language"), gate=gate, report=report, messages=messages,
                                     execution_report=execution_report if isinstance(execution_report, str) else None,
                                     terminal_facts=facts, compact=bool(runtime_identity.revision_match(index.get('engine_version', ''))
                                         and int(runtime_identity.revision_match(index.get('engine_version', ''))[1]) >= 135))
    try:   # alpha.27 R1: the run-ended report is a public file too, so the model can deliver it by reference
        if not (store.public_dir / "ended.txt").exists():
            store.write_public("ended.txt", text)
    except Exception:  # noqa: BLE001 - the terminal reply must never fail on the side file
        pass
    return text


def _fatal_facts(store: RunStore, index: dict) -> dict:
    """Accepted-cache facts only; not a replacement commit or proof of unregistered effects."""
    stages, artifacts, unavailable = [], [], []
    for done in index.get('completed') or []:
        name, visit = done['name'], done['visit']
        try:
            entry = _catalog_entry(index, name)
            path = _cache_path_for(store, index, entry, visit)
            expected = (index['nodes'].get(_node_key(name, visit)) or {}).get('cache_sha256')
            if sha256_bytes(store.read_bytes(path)) != expected:
                unavailable.append(f'{name}@{visit}: cache digest mismatch')
                continue
            cache = store.read_json(path)
            stages.append(dict(node=name, visit=visit, status=_latest_payload(cache).get('status'),
                               cache=str(path), sha256=expected))
            for revision in _evidence_records(cache):
                for artifact in (revision.get('machine') or {}).get('artifacts') or []:
                    artifacts.append(dict(node=name, visit=visit, accepted_metadata=artifact))
        except (RunStoreError, OSError, KeyError, TypeError, ValueError) as exc:
            unavailable.append(f'{name}@{visit}: {type(exc).__name__}')
    unconsumed = []
    for event in index.get('gate', {}).get('history', []):
        if not event.get('answered_at') or event.get('resolution_kind') == 'invalid_retry':
            continue
        try:
            path = store.gate_path(event['question_id'])
            record = store.read_json(path)
            if record.get('consumed_by_commit') or not record.get('answered_at'):
                continue
            original = record.get('answer_text_original', record.get('answer_text'))
            if isinstance(original, str):
                unconsumed.append(dict(question_id=event['question_id'], answer_text=original,
                    path=str(path), sha256=sha256_bytes(store.read_bytes(path)), consumed_by_commit=False))
        except (RunStoreError, OSError, KeyError, TypeError, ValueError):
            unavailable.append(f"gate {event.get('question_id')}: original answer unavailable")
    return dict(basis='accepted_cache_digests_not_unregistered_write_receipts', stages=stages,
                artifacts=artifacts, unconsumed_answers=unconsumed, unavailable=unavailable, cache=str(store.cache_dir))


def _ref(store: RunStore, name: str) -> str:
    """alpha.27 R1: ⟦engine:<cache>/<file>⟧ — the cache name keeps the reference resolvable across a session's runs."""
    if name.startswith('menu.'):
        from . import menu_history
        return menu_history.ref(store.cache_dir, name)
    return render.ref_line(store.cache_dir.name, name)


def _terminal_delivery(store: RunStore, index: dict, block_ref: str | None = None) -> dict:
    """Project existing terminal files in one order, without replaying work or writing a receipt."""
    completed = index["run_state"] == "COMPLETED"
    if completed and not block_ref and index.get("completed"):
        last = index["completed"][-1]
        entry = _catalog_entry(index, last["name"])
        if entry and entry["name"] in FINAL_NODES:
            name = f"node.{entry['ordinal'] + 1:02d}.{_safe_name(entry['name'])}.v{last['visit']}.txt"
            if (store.public_dir / name).is_file():
                block_ref = _ref(store, name)
    names = ("final_answer.txt", "evidence.txt") if completed else ("ended.txt",)
    refs = ([block_ref] if block_ref else []) + [_ref(store, name) for name in names if (store.public_dir / name).is_file()]
    if not completed:   # alpha.90 (doc 202 D): the committed execution report's block travels with the run-ended report
        for done in index.get("completed") or []:
            if done["name"] in ACCOUNTING_NODES:
                entry = _catalog_entry(index, done["name"])
                if entry:
                    name = f"node.{entry['ordinal'] + 1:02d}.{_safe_name(entry['name'])}.v{done['visit']}.txt"
                    if (store.public_dir / name).is_file() and _ref(store, name) not in refs:
                        refs.insert(0, _ref(store, name))
    return {"public_block_ref": block_ref, "terminal_delivery_refs": refs}


def _menu_ref(store: RunStore, name: str, text: str) -> str:
    """docs/05SoulRun 90 round 7 (ledger decision 187 (a)): the reference line the menu `name` gets once `text` is written
    (store.write_public: under replacement accounting its immutable version, menu_history.preserve) - what _ref names after
    that write - for a sub-agent's pause, which names its menu in the reply and the scope's ordered public_refs before the
    menu is written (_finish_pause)."""
    from . import menu_history
    return render.ref_line(store.cache_dir.name, menu_history.version_name(store, name, text) or name)


def _pause_ref(store: RunStore, qid: str) -> str | None:
    """alpha.27 R1: the reference line of the ⏸ mid-state node info written at the pause."""
    for p in sorted(store.public_dir.glob(f"pause.*.{qid}.v*.txt")):
        return _ref(store, p.name)
    return None


def _pause_block_text(store: RunStore, qid: str) -> str | None:
    """alpha.25: the ⏸ mid-state node info written at the pause, served again while the run is WAITING_USER."""
    for p in sorted(store.public_dir.glob(f"pause.*.{qid}.v*.txt")):
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def _pending_gate_answer(store: RunStore, index: dict, node: str, visit: int) -> dict | None:
    """The latest answered, not yet consumed gate of this node occurrence (same_occurrence resume)."""
    for h in reversed(index["gate"]["history"]):
        if h["node"] != node or h["resolution_kind"] == "invalid_retry":
            continue
        if h["resolution_kind"] in ("chosen", "free_text") and h["answered_at"]:
            rec = store.read_json(store.gate_path(h["question_id"]))
            if rec.get('program_drift') or rec.get('dispatch_block'):
                continue  # resource/integrity choices must not mask an earlier business answer
            if rec.get("visit") == visit and not rec.get("consumed_by_commit"):
                if any(rec.get(key) != h.get(key) for key in
                       ("question_id", "node", "resolution_kind", "answered_at")):
                    raise EngineError("HUMAN_REPLY_BINDING_INVALID",
                                      "Gate answer disagrees with this run's accepted question history; do not borrow or invent an answer.")
                return {"question_id": h["question_id"], "resolution_kind": h["resolution_kind"],
                        "answer_text": rec.get("answer_text"), "chosen_intent": rec.get("chosen_intent"),
                        "node": node, "visit": visit,
                        "answered_at": rec["answered_at"], "answered_by": rec.get("answered_by"),
                        "question": rec.get("question"),
                        **({"answer_text_original": rec['answer_text_original']} if 'answer_text_original' in rec else {}),
                        **({"invalid_answers": copy.deepcopy(rec['invalid_answers'])} if rec.get('invalid_answers') else {}),   # alpha.79
                        "chosen_label": rec.get("chosen_label"),
                        **({'business_authorization':False,
                            'disposition_notice':'Finding disposition only. The original business choice still requires a new real gate; preserve prior work and the original reply.'}
                           if rec.get('chosen_intent') in (rec.get('hsaw') or {}).get('finding_only_intents',[]) else {}),
                        **({"next_hint": target} if (target := _record_gate_target(rec)) else {})}
        return None
    return None


def _conditional_pending(store, index):
    if index['run_state'] != 'RUNNING':
        return None
    current = index['current']
    try:
        answer = _pending_gate_answer(store, index, current['name'], current['visit'])
    except EngineError as exc:
        if exc.code != 'HUMAN_REPLY_BINDING_INVALID':
            raise
        # A clarification may have reset the record before the index write crashed.
        # This path only reopens WAITING_USER; it supplies no business answer.
        h = next((h for h in reversed(index['gate']['history'])
                  if h['node'] == current['name'] and h['resolution_kind'] != 'invalid_retry'), None)
        rec = store.read_json(store.gate_path(h['question_id'])) if h else {}
        row = conditional_reply.latest(rec)
        if (h and h['resolution_kind'] == 'free_text' and rec.get('conditional_reply') and row
                and row['state'] == 'CLARIFICATION_REQUIRED' and row['answered_at'] == h['answered_at']
                and rec.get('question_id') == h['question_id'] and rec.get('node') == current['name']
                and rec.get('visit') == current['visit'] and not rec.get('consumed_by_commit')
                and rec.get('answered_at') is None and rec.get('resolution_kind') is None):
            return rec
        raise
    if answer and answer['resolution_kind'] == 'free_text':
        rec = store.read_json(store.gate_path(answer['question_id']))
        row = conditional_reply.latest(rec)
        if rec.get('conditional_reply') and row is None:
            raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'Conditional original record is incomplete; no business authority exists.')
        return rec if row and row['state'] in ('PENDING', 'CLARIFICATION_REQUIRED') else None
    return None


def _conditional_nodes(program, index):
    names = [n for d in program.docs.values() for n in d.functions]
    return set(e['name'] for e in index['catalog'] if e['kind'] in ('business', 'sub')) | {
        n for n in names if names.count(n) == 1} | {f'{d.name}::{n}' for d in program.docs.values() for n in d.functions}


def _conditional_node_aliases(program, index, name):
    entry = _catalog_entry(index, name)
    if not entry or entry['kind'] not in ('business', 'sub'):
        return {name}
    view = _view_for(program, entry)
    bare = view['node']
    names = [n for d in program.docs.values() for n in d.functions]
    return {name, f"{view['file']}::{bare}"} | ({bare} if names.count(bare) == 1 else set())


def _conditional_declaration(gate, view, entry, program):
    value = gate.get('conditional_reply', (view or {}).get('extra', {}).get('conditional_reply'))
    try:
        declaration = conditional_reply.declaration(value, view, business=entry['kind'] in ('business', 'sub'))
        if declaration:
            names = [n for d in program.docs.values() for n in d.functions]
            valid = {n for n in names if names.count(n) == 1} | {f'{d.name}::{n}' for d in program.docs.values() for n in d.functions}
            if set(declaration['nodes']) - valid:
                raise conditional_reply.ReplyError('CONDITIONAL_REPLY_INVALID', 'Declare unique bare or file::node identities in this program.')
            gate['conditional_reply'] = declaration
    except conditional_reply.ReplyError as exc:
        raise EngineError(exc.code, exc.message, field=exc.field) from exc


def _conditional_records(store, index):
    try:
        return conditional_reply.records(store, index)
    except conditional_reply.ReplyError as exc:
        raise EngineError(exc.code, exc.message, field=exc.field) from exc


def _conditional_compliance_records(caches):
    return [dict(node=c['node'], visit=c['visit'], **r) for c in caches
            for r in ((c.get('continuations') or [c])[-1]['machine'].get('human_compliance') or {}).get('declarations', [])]


def _conditional_serve(store, index, rec):
    answer = conditional_reply.latest(rec)
    entry = _catalog_entry(index, rec['node'])
    if answer['state'] == 'CLARIFICATION_REQUIRED':
        _conditional_reopen(store, index, rec)
        return dict(schema_version=1, run=dict(trace_id=index['trace_id'], state='WAITING_USER'),
                    node=dict(name=rec['node'], kind=entry['kind']), steps=[], dispatch=None, payload_skeleton=None,
                    gate=dict(state='WAITING_USER', source=rec['source'], required=True, question_id=rec['question_id'],
                              public_prompt=render.menu_block(rec, user_language=index.get('user_language'))),
                    public_plan=None, public_plan_ref=None, conditional_reply=dict(state='CLARIFICATION_REQUIRED'))
    skeleton = dict(question_id=rec['question_id'], answer_sha256=answer['sha256'], choice_intent=None,
                    selected_items=[], rejected_items=[], instructions=[], ambiguity=dict(status='needs_human', reason=''))
    action = ('完整保留并解读人类原文；通过前不得执行业务步骤或写入。' if str(index.get('user_language') or '').startswith('zh') else
              'Preserve and interpret the original; no business steps or side effects before acceptance.')
    plan = render.plan_block(_position(index), rec['node'], entry['kind'], 'interpretation-only', action,
        'same_occurrence', user_language=index.get('user_language'))
    plan_name = store.write_public_snapshot(f"plan.conditional.{rec['question_id']}.txt", plan).name
    return dict(schema_version=1, run=dict(trace_id=index['trace_id'], state=index['run_state']),
                program=_program_group(index), node=dict(name=rec['node'], kind=entry['kind'], parent=entry.get('parent'),
                    depth=entry['depth'], bare=_bare(entry), position=_position(index), mode=None),
                steps=[], dispatch=None, reserved=None, topology=None, budget=None, payload_skeleton=None,
                gate=dict(state='CLEAR', required=False, source=rec['source'], public_prompt=None),
                resume=dict(kind='same_occurrence', source=rec['question_id']), public_plan=plan, public_plan_ref=_ref(store, plan_name),
                conditional_reply=dict(state='INTERPRETATION_REQUIRED', question_id=rec['question_id'],
                    declaration=rec['conditional_reply'], answer_text_original=answer['text_original'],
                    answer_sha256=answer['sha256'], answered_by=answer['answered_by'],
                    interpretation_skeleton=skeleton, rule=conditional_reply.RULE,
                    submit='node_commit.py --cache-dir <same-cache> --node <this-node> --interpret-human-reply --payload-stdin'),
                payload_rules=[_contracts.text('conditional-reply.interpretation')])


def interpret_human_reply(cache_dir, payload_text, *, node=None):
    """Only validates an interpretation. Never commits business work or grants tool execution authority."""
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        # docs/05SoulRun 90 round 6 (merge, line B's note 1): an engine stop cut off before its index write is installed first,
        # as next-node, node-commit and gate-answer install it - so a retry after the files were restored is served that stop
        dispatch_budget.reinstall(store, index)
        blocked = program_guard.record(store, index)
        if blocked:
            program_guard.pending_payload(store, payload_text, blocked)
            return program_guard.reply(store, index, blocked)
        blocked = dispatch_budget.record(store, index)
        if blocked:
            # docs/05SoulRun 90 round 5 (ledger decision 185): the interpretation command is the main executor's alone
            # (node_commit.py refuses it with an agent ticket; the call takes none), so this is a serve to the main executor:
            # served(), which publishes - for a stop asked again and never served yet, pause()'s reply (record 90 round 3 B1)
            return dispatch_budget.served(store, index, blocked)
        try:
            program = _load_routed_program(_read_run_input(store))
        except EngineError as exc:
            if exc.code == 'PROGRAM_DRIFT_DETECTED':
                return program_guard.pause(store, index, exc, payload_text)
            raise
        rec = _conditional_pending(store, index)
        if rec and conditional_reply.latest(rec)['state'] == 'CLARIFICATION_REQUIRED':
            _conditional_reopen(store, index, rec)
            return dict(status='WAITING_USER', question_id=rec['question_id'], run_state='WAITING_USER',
                        submission_accepted=False,
                        public_prompt=render.menu_block(rec, user_language=index.get('user_language')))
        try:
            candidate = strict_loads(payload_text)
        except (ValueError, TypeError) as exc:
            return dict(status='REJECTED', errors=[dict(code='HUMAN_INTERPRETATION_INVALID', message=str(exc))])
        if not rec:
            qid = candidate.get('question_id') if isinstance(candidate, dict) else None
            if isinstance(qid, str) and re.fullmatch(r'q\d+-[0-9a-f]+', qid) and store.gate_path(qid).exists():
                prior = store.read_json(store.gate_path(qid))
                proof = conditional_reply.accepted(prior)
                if proof and proof['interpretation'] == candidate:
                    _conditional_finish_interpretation(store, index, prior)
                    return dict(status='ALREADY_INTERPRETED', question_id=qid, semantic_correctness='UNVERIFIED')
            raise EngineError('HUMAN_INTERPRETATION_NOT_PENDING', 'No conditional reply awaits interpretation; do not replace an accepted interpretation.')
        if (node is not None and node != rec['node']) or not isinstance(candidate, dict) or candidate.get('question_id') != rec['question_id']:
            return dict(status='REJECTED', errors=[dict(code='HUMAN_REPLY_BINDING_INVALID', message='Different node/gate cannot supply this interpretation.')])
        answer = conditional_reply.latest(rec)
        try:
            done = set().union(*(_conditional_node_aliases(program, index, c['name']) for c in index['completed'])) if index['completed'] else set()
            plan, option = conditional_reply.validate(rec, candidate, _conditional_nodes(program, index), done)
        except conditional_reply.ReplyError as exc:
            answer['attempts'].append(dict(at=now_iso(), candidate=copy.deepcopy(candidate), code=exc.code, message=exc.message))
            clarify = len(answer['attempts']) >= 2 or exc.code == 'HUMAN_CLARIFICATION_REQUIRED'
            if clarify:
                answer['state'] = 'CLARIFICATION_REQUIRED'
                rec['clarification_reason'] = exc.message
                rec.setdefault('invalid_answers', []).append(dict(at=now_iso(), text=answer['text_original'],
                    text_original=answer['text_original'], reason='INTERPRETATION_NEEDS_HUMAN'))
                rec.update(answered_at=None, resolution_kind=None, chosen_intent=None, chosen_label=None, delivered_at=None)
            _write_json(store.gate_path(rec['question_id']), rec)
            if clarify:
                _conditional_reopen(store, index, rec)
            _write_index(store, index)
            return dict(status='WAITING_USER' if clarify else 'REJECTED', run_state=index['run_state'], question_id=rec['question_id'],
                submission_accepted=False,
                errors=[dict(code=exc.code, field=exc.field, message=exc.message)],
                public_prompt=render.menu_block(rec, user_language=index.get('user_language')) if clarify else None,
                help='Preserve the complete original. Correct structure only; semantic doubt requires the human.')
        answer.update(state='ACCEPTED', interpretation=plan)
        rec.update(chosen_intent=option['intent'], chosen_label=option['label'])
        conditional_reply.seal(rec)
        _write_json(store.gate_path(rec['question_id']), rec)
        _conditional_finish_interpretation(store, index, rec)
        value = conditional_reply.accepted(rec)
        public = render.robot_frame(conditional_reply.table([value], [], index.get('user_language')), index.get('user_language'))
        name = store.write_public_snapshot(f"menu.interpretation.{rec['question_id']}.txt", public).name
        return dict(status='INTERPRETATION_ACCEPTED', question_id=rec['question_id'], verification_scope=conditional_reply.SCOPE,
                    semantic_correctness='UNVERIFIED', actual_compliance='UNVERIFIED', public_block=public,
                    public_block_ref=_ref(store, name), next=dict(node=rec['node'], kind=_catalog_entry(index, rec['node'])['kind']))


def _conditional_finish_interpretation(store, index, rec):
    answer = conditional_reply.latest(rec)
    if index['run_state'] in TERMINAL_STATES:
        return
    event = dict(kind='human_interpretation', at=now_iso(), trace_id=index['trace_id'], engine_version=ENGINE_VERSION,
                 question_id=rec['question_id'], node=rec['node'], visit=rec['visit'], proof_sha256=answer['proof'],
                 answer_sha256=answer['sha256'], verification_scope=conditional_reply.SCOPE, semantic_correctness='UNVERIFIED')
    if not any(e.get('kind') == 'human_interpretation' and e.get('proof_sha256') == answer['proof']
               for e in store.read_json(store.evidence_path)):
        _ledger_append(store, index, event)
    _write_index(store, index)


def _conditional_reopen(store, index, rec):
    index['gate'].update(state='WAITING_USER', answered_at=None, delivered_at=None)
    if not any(h['question_id'] == rec['question_id'] and h['resolution_kind'] is None for h in index['gate']['history']):
        index['gate']['history'].append(dict(question_id=rec['question_id'], node=rec['node'], source=rec['source'],
            prompt_text=rec.get('prompt_text'), presented_at=now_iso(), answered_at=None, resolution_kind=None,
            answer_ref=f"_gate.{rec['question_id']}.json"))
    next(t for t in index['tickets'] if t['question_id'] == rec['question_id'])['state'] = 'READY'
    index['nodes'][_node_key(rec['node'], rec['visit'])]['status'] = 'WAITING_USER'
    index['run_state'] = 'WAITING_USER'
    public = render.menu_block(rec, user_language=index.get('user_language'))
    rec['clarification_menu'] = store.write_public_snapshot(f"menu.clarification.{rec['question_id']}.txt", public).name
    _write_json(store.gate_path(rec['question_id']), rec)
    _write_index(store, index)


def _prev_business_caches(store: RunStore, index: dict, exclude: tuple | None = None) -> list[dict]:
    out = []
    for c in index["completed"]:
        if exclude and (c["name"], c["visit"]) == exclude:
            continue
        entry = _catalog_entry(index, c["name"])
        if not entry or entry["kind"] not in ("business", "sub"):
            continue
        path = _cache_path_for(store, index, entry, c["visit"])
        if store.exists_path(path):
            out.append(store.read_json(path))
    return out


def _public_reference_cache(store: RunStore, index: dict, name: str, visit: int) -> dict | None:
    """One digest-bound public source; no execution or resume authority."""
    entry = _catalog_entry(index, name)
    state = index.get('nodes', {}).get(_node_key(name, visit)) or {}
    if not entry or entry['kind'] not in ('business', 'sub') or not state.get('cache_sha256'):
        return None
    path = _cache_path_for(store, index, entry, visit)
    if not path.resolve().is_relative_to(store.cache_dir.resolve()):
        raise EngineError('INPUT_REF_INVALID', f'accepted report escapes its run: {name}')
    try:
        raw = store.read_bytes(path)
    except OSError as exc:
        raise EngineError('INPUT_REF_INVALID', f'accepted report is unavailable: {name}') from exc
    if sha256_bytes(raw) != state['cache_sha256']:
        raise EngineError('INPUT_REF_INVALID', f'source digest changed: {name}')
    try:
        cache = strict_loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise EngineError('INPUT_REF_INVALID', f'source is not valid JSON: {name}') from exc
    if (cache.get('node'), cache.get('visit')) != (name, visit):
        raise EngineError('INPUT_REF_INVALID', f'accepted report identity changed: {name}')
    frame = (cache.get('continuations') or [cache])[-1]
    payload, machine = frame['payload'], frame['machine']
    if machine.get('trace_id') != index['trace_id']:
        raise EngineError('INPUT_REF_INVALID', f'accepted report belongs to another run: {name}')
    completed = any(c['name'] == name and c['visit'] == visit for c in index['completed'])
    if payload.get('status') in ('PARTIAL', 'FAIL') or not completed:
        qid = machine.get('paused_gate')
        public_pause = bool(qid and _pause_block_text(store, qid))
        public_node = completed and store.exists_path(store.public_dir / f"node.{entry['ordinal'] + 1:02d}.{_safe_name(name)}.v{visit}.txt")
        if payload.get('status') not in ('PARTIAL', 'FAIL') or not (public_pause or public_node):
            return None  # A module prefix/planned payload is not a public report.
    return cache


def _public_reference_caches(store: RunStore, index: dict) -> list[dict]:
    """Closing may quote accepted public pauses, never treat them as executed inputs."""
    if store is None or (index.get('current') or {}).get('name') not in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY):
        return _prev_business_caches(store, index)
    found = []
    for key in index.get('nodes', {}):
        name, _, suffix = key.partition('@')
        cache = _public_reference_cache(store, index, name, int(suffix[1:]) if suffix else 1)
        if cache is not None:
            found.append(cache)
    return sorted(found, key=lambda c: _part_order_key(index, c['node'], c['visit'], 'user_summary', None))


def _latest_payload(cache: dict) -> dict:
    return (cache["continuations"][-1] if cache.get("continuations") else cache)["payload"]


def _main_nodes_committed(index: dict) -> list[str]:
    """alpha.83 (doc 174): the main business nodes this run has committed so far - every turn - in execution order, each name once."""
    rows, order = [], {}
    for i, done in enumerate(index['completed']):
        order.setdefault(done['name'], i)
    for key, state in index['nodes'].items():
        name = key.partition('@')[0]
        entry = _catalog_entry(index, name)
        if dispatch_scope.is_main(index, entry) and state.get('cache_sha256'):
            rows.append((order.get(name, len(order)), state.get('ready_at') or '', entry.get('ordinal', 0), name))
    names = []
    for *_, name in sorted(rows):
        if name not in names:
            names.append(name)
    return names


_LEAD_POINTER = re.compile(r'详见下方|见下方|详见下文|见下文各|详见以下|详见各节点|详见后文|详见上方|详见上文|见上文|'
                           r'\bsee (?:the )?(?:reports? |sections? |records? )?(?:below|above)\b|\b(?:as )?detailed (?:below|above)\b|'
                           r'\brefer to the (?:reports?|sections?|records?) (?:below|above)\b', re.I)


def _check_final_lead(store: RunStore, payload: dict, report_parts) -> dict | None:
    """alpha.83 (doc 174 B; production cache/43: a 416-character lead ending in "详见下方各节点的完整记录"): with references attached, a lead
    that points at them and carries neither a heading nor a table is refused once. No length floor (doc 93): a short lead that answers
    is fine, a structured lead may point. The "once" is read from the archived commit replies, so a rejection still writes nothing."""
    if payload.get('status') == 'FAIL' or not report_parts:
        return None
    lead = _answer_body(payload) or ''
    match = _LEAD_POINTER.search(lead)
    if not match or re.search(r'^\s{0,3}#{1,6}\s', lead, re.M) or re.search(r'^\s*\|?\s*:?-{3,}:?\s*\|', lead, re.M):
        return None
    asked = any(r.get('node') in ANSWER_NODES and 'FINAL_LEAD_POINTER' in (r.get('codes') or [])
                for r in evidence_views.protocol_attempts(store.cache_dir)['records'])
    if asked:
        return {"code": "FINAL_LEAD_POINTER", "text": f"the lead still points at the referenced reports ({match.group(0)!r}, no heading, no table); "
                                                        "asked once, accepted as submitted (alpha.83)"}
    raise EngineError('FINAL_LEAD_POINTER', 'the final lead points at the referenced reports instead of answering',
                      field='semantics.final_answer', expected='a self-contained business answer in the lead; the referenced reports follow it verbatim',
                      example=match.group(0))


def _functional_floor(index: dict) -> dict:
    """alpha.79 (doc 163): the mildest whole-run functional_status the accepted node statuses allow - the alpha.54 rule, also served up front."""
    business = {k: v for k, v in index['nodes'].items() if (_catalog_entry(index, k.partition('@')[0]) or {}).get('kind') in ('business', 'sub')}
    degraded = sorted(k.partition('@')[0] for k, v in business.items() if v.get('status') == 'DEGRADED')
    failed = sorted(k.partition('@')[0] for k, v in business.items() if v.get('status') == 'FAILED')
    return dict(floor='PARTIAL or FAIL' if failed else 'DEGRADED' if degraded else 'PASS', degraded_nodes=degraded, failed_nodes=failed)


def _node_facts(store: RunStore, index: dict) -> dict:
    """alpha.79: what Engine.execute-report / final are told before they write - the same counts the commit checks against."""
    try:
        states, basis = evidence_views.node_state_counts(_report_records(store, index), index), 'latest_accepted_status_per_occurrence'
    except EngineError as exc:   # a changed cache is refused at commit; the serve stays readable
        states, basis = None, f'UNAVAILABLE_{exc.code}'
    floor = _functional_floor(index)
    return dict(states=states, functional_status_floor=floor['floor'], degraded_nodes=floor['degraded_nodes'], failed_nodes=floor['failed_nodes'],
                human_instructions_not_reached=_conditional_unreached(store, index),
                basis=basis, note='main, sub and engine occurrences are separate counts',
                cancelled=copy.deepcopy(index.get('cancelled')))   # alpha.88 (doc 196 F4'): where the human cancelled and what was not run


def _report_records(store: RunStore, index: dict, *, review_only: bool = False) -> list[dict]:
    """Accepted node revisions only; check integrity before projecting facts."""
    records = []
    for key, state in index['nodes'].items():
        if not state.get('cache_sha256'):
            continue
        name, _, visit_text = key.partition('@')
        entry = _catalog_entry(index, name)
        visit = int(visit_text.removeprefix('v') or 1)
        if review_only:
            _, owner = _self_dispatch(index, entry, visit)
            if not (owner or {}).get('review_binding'):
                continue
        path = _cache_path_for(store, index, entry, visit)
        if name == NODE_MATCH and not store.exists_path(path):
            path = store.node_cache_path('engine', name, visit)
        raw = store.read_bytes(path)
        if sha256_bytes(raw) != state['cache_sha256']:
            raise EngineError('FINAL_SOURCE_CHANGED', 'report source cache changed', field='evidence')
        records.append(json.loads(raw))
    return records


def _conditional_unreached(store, index):
    conditions = _conditional_records(store, index)
    if not conditions:
        return []
    program = _load_routed_program(_read_run_input(store))
    reached = set()
    for record in _report_records(store, index):
        if _latest_payload(record)['status'] in {'PASS', 'DEGRADED'}:
            reached.update(_conditional_node_aliases(program, index, record['node']))
    return conditional_reply.unreached(conditions, reached)


def _run_inputs(run_input: dict | None) -> dict:
    """alpha.91 (doc 206 #1): the AISOP input variables the engine itself supplies - `user_input` is the run's user message."""
    return {"user_input": (run_input or {}).get("user_message")}


def _required_fields_status(required: list[str], prev_caches: list[dict], context: dict, inputs: dict | None = None) -> dict:
    present, missing = [], []
    for name in required:
        found = name in context or bool(str((inputs or {}).get(name) or "").strip())   # alpha.91: a supplied input variable is present
        for cache in prev_caches:
            payload = _latest_payload(cache)
            output = payload.get("output")
            if name in (payload.get("vars") or {}) or (isinstance(output, dict) and name in output) \
                    or re.search(rf"\b{re.escape(name)}\b", _output_text(payload)):
                found = True
                break
        (present if found else missing).append(name)
    return {"present": present, "missing": missing}


def _input_identity(store, index, cache) -> dict:
    key = _node_key(cache["node"], cache["visit"])
    return {"run": sha256_bytes((_fs(store.cache_dir.resolve()) + index["trace_id"] + index["started_at"]).encode()),
            "consumer": dict(index["current"]), "node": cache["node"], "visit": cache["visit"],
            "revision": len(cache.get("continuations") or []), "sha256": index["nodes"][key]["cache_sha256"]}


def _input_refs(store, index, caches) -> list[dict]:
    refs = []
    for cache in caches:
        identity = _input_identity(store, index, cache)
        token = base64.urlsafe_b64encode(json.dumps(identity, separators=(",", ":")).encode()).decode().rstrip("=")
        refs.append({"node": cache["node"], "visit": cache["visit"], "revision": identity["revision"], "ref": token,
                     "id": f"{cache['node']}@{cache['visit']}",   # alpha.59 B2: the short form accepted in semantics.report_parts[].ref
                     "user_messages_count": len(_latest_payload(cache).get("user_messages", []))})
        rows = evidence_views.source_support_rows([cache])
        if rows:
            refs[-1]['source_support'] = evidence_views.source_support_preview(rows[0], token)
        machine = (cache.get('continuations') or [cache])[-1].get('machine') or {}
        state = index['nodes'][_node_key(cache['node'], cache['visit'])]
        review = machine.get('review_binding') or (state.get('dispatch') or {}).get('review_binding')
        root = (machine.get('dispatch') or {}).get('scope_root')
        if review and root == dict(node=cache['node'], visit=cache['visit']):
            refs[-1]['review_result'] = dict(root=root, binding_sha256=review.get('sha256'),
                status=state.get('status'),
                verification_scope='Review observation, not score eligibility. Read the original ref; never silently skip a degraded or unavailable current review.')
        if index['current']['name'] not in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY):
            output = _latest_payload(cache).get('output')
            keys = [k for k in output if len(k) <= 128] if isinstance(output, dict) else []
            refs[-1]['output_shape'] = dict(kind='object' if isinstance(output, dict) else 'array' if isinstance(output, list) else 'scalar',
                                           keys=keys[:8], keys_truncated=isinstance(output, dict) and len(output) > len(keys[:8]))
    return refs


def _read_input_authority(store, agent_ticket):
    index = store.read_index()
    if index["run_state"] != "RUNNING":
        raise EngineError("INPUT_REF_INVALID", "input reads require a running, current occurrence")
    entry = _catalog_entry(index, index["current"]["name"])
    key, dispatch = _self_dispatch(index, entry, index["current"]["visit"])
    if agent_ticket:
        if not dispatch or dispatch["state"] != "CLAIMED" or dispatch["ticket"] != agent_ticket:
            raise _ticket_error(index, key, agent_ticket, dispatch)
    elif dispatch and dispatch["state"] in ("ISSUED", "CLAIMED"):
        raise EngineError("INPUT_REF_INVALID", "dispatched input requires its claimed agent ticket")
    return index


def list_inputs(cache_dir, *, offset=0, limit=8, agent_ticket=None) -> dict:
    """Read-only paginated catalog; no lock/init/serve/claim or public rendering."""
    if not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 32:
        raise EngineError("INPUT_REF_INVALID", "catalog requires offset >= 0 and limit 1..32")
    store = RunStore(cache_dir)
    index = _read_input_authority(store, agent_ticket)
    from . import blind_review
    binding = blind_review.active(store, index)
    from . import independent_inputs
    scoped = independent_inputs.active(store, index)
    caches = _public_reference_caches(store, index)
    refs = (blind_review.refs(binding) if binding else []) + _input_refs(store, index,
        [c for c in caches if blind_review.owns(c, binding)] if binding else caches)
    if scoped:
        refs = independent_inputs.refs(scoped) + _input_refs(store, index, [c for c in caches if blind_review.owns(c, scoped)])
    if store.read_index() != index:
        raise EngineError("INPUT_REF_INVALID", "run changed during catalog read; retry")
    return {"status": "INPUT_CATALOG", "items": refs[offset:offset + limit], "total": len(refs),
            "next_offset": offset + limit if offset + limit < len(refs) else None}


def read_input(cache_dir, ref, *, field="output", offset=0, limit=16384, agent_ticket=None, deref=True, path=None) -> dict:
    """Resolve one engine-projected identity, not a caller-supplied filesystem path."""
    if field not in ("output", "vars", "user_summary", "user_messages", "source_support") or type(offset) is not int or offset < 0 \
            or type(limit) is not int or not 1 <= limit <= 65536:
        raise EngineError("INPUT_REF_INVALID", "field must be output|vars|user_summary|user_messages|source_support; offset >= 0; limit 1..65536")
    selection = path
    if selection is not None and (not isinstance(selection, str) or len(selection) > 2048 or not re.fullmatch(
            r'(?:[^.\[\]]+|\[[0-9]+\])(?:\.[^.\[\]]+|\[[0-9]+\])*', selection)):
        raise EngineError('INPUT_REF_INVALID', 'input-path must be a nonempty a.b[0] JSON field path, at most 2048 characters')
    from . import blind_review
    store = RunStore(cache_dir)
    index = _read_input_authority(store, agent_ticket)
    binding = blind_review.active(store, index)
    from . import independent_inputs
    scoped = independent_inputs.active(store, index)
    if isinstance(ref, str) and ref.startswith('scoped:'):
        if not scoped:
            raise EngineError('INPUT_REF_INVALID', 'No active scoped input binding.')
        return independent_inputs.read(scoped, ref, field, offset, limit, selection)
    if isinstance(ref, str) and ref.startswith('blind:'):
        if selection is not None:
            raise EngineError('INPUT_REF_INVALID', 'Use the dedicated complete blind input reader; input-path cannot widen its scope')
        if not binding:
            raise EngineError('INPUT_REF_INVALID', 'No active review input binding.')
        return blind_review.read(store, binding, ref, field, offset, limit)
    try:
        if not isinstance(ref, str) or len(ref) > 4096:
            raise ValueError("oversized reference")
        identity = strict_loads(base64.b64decode(ref + "=" * (-len(ref) % 4), altchars=b"-_", validate=True).decode("utf-8"))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise EngineError("INPUT_REF_INVALID", "invalid input reference") from exc
    store = RunStore(cache_dir)
    index = _read_input_authority(store, agent_ticket)
    from . import module_order
    closing = index['current']['name'] in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY)
    public_source = (_public_reference_cache(store, index, identity.get('node'), identity.get('visit'))
                     if closing and isinstance(identity, dict) and isinstance(identity.get('node'), str)
                     and type(identity.get('visit')) is int else None)
    if not isinstance(identity, dict) or not (any(c["name"] == identity.get("node") and c["visit"] == identity.get("visit")
                                               for c in index["completed"]) or public_source is not None or
            module_order.input_allowed(index, identity.get('node'), identity.get('visit'))):
        raise EngineError("INPUT_REF_INVALID", "source is not a committed occurrence")
    entry = _catalog_entry(index, identity["node"])
    if not entry or entry["kind"] not in ("business", "sub"):
        raise EngineError("INPUT_REF_INVALID", "source is not an authorized business input")
    path = _cache_path_for(store, index, entry, identity["visit"])
    if not path.resolve().is_relative_to(store.cache_dir.resolve()):
        raise EngineError("INPUT_REF_INVALID", "source escapes its run")
    if public_source is not None:
        # Reuse the already digest-checked snapshot, not a second filesystem read.
        cache = public_source
        source_sha256 = index['nodes'][_node_key(cache['node'], cache['visit'])]['cache_sha256']
    else:
        raw = store.read_bytes(path)
        source_sha256 = sha256_bytes(raw)
        if source_sha256 != identity.get('sha256'):
            raise EngineError('INPUT_REF_INVALID', 'source digest changed')
        try:
            cache = strict_loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise EngineError("INPUT_REF_INVALID", "source is not valid JSON") from exc
    if source_sha256 != identity.get("sha256"):
        raise EngineError("INPUT_REF_INVALID", "source digest changed")
    expected = _input_identity(store, index, cache)
    accepted = [expected]
    if index["current"]["name"] in ANSWER_NODES:   # alpha.45: references served to Engine.execute-report stay valid for its answer node `Engine.final-answer`
        accepted.append(dict(expected, consumer=dict(identity.get("consumer") or {})) if (identity.get("consumer") or {}).get("name") in ACCOUNTING_NODES else expected)
    if identity not in accepted or source_sha256 != expected["sha256"]:
        raise EngineError("INPUT_REF_INVALID", "source identity or digest changed")
    payload = _latest_payload(cache)
    machine = (cache.get('continuations') or [cache])[-1]['machine']
    completed = any(c['name'] == cache['node'] and c['visit'] == cache['visit'] for c in index['completed'])
    incomplete_public = closing and (not completed or payload.get('status') == 'PARTIAL' and bool(machine.get('paused_gate')))
    if incomplete_public and (public_source is None or field not in ('user_summary', 'user_messages') or selection is not None):
        raise EngineError('INPUT_REF_INVALID', 'unfinished sources are public report/message references only')
    if binding and not blind_review.owns(cache, binding):
        raise EngineError('INPUT_REF_INVALID', 'Blind review cannot read upstream Writer records.')
    if scoped and not independent_inputs.allows(scoped, cache):
        raise EngineError('INPUT_REF_INVALID', 'Use the selected scoped value, never its whole source cache.')
    review_status = None
    if machine.get('review_binding'):
        review_status = blind_review.observe(store, machine['review_binding'],
            (machine.get('dispatch') or {}).get('scope_root') or dict(node=cache['node'], visit=cache['visit']))
    acceptance = None
    if review_status:
        acceptance = dict(run=identity['run'], consumer=dict(identity['consumer']),
            status=index['nodes'][_node_key(cache['node'], cache['visit'])].get('status'),
            order=next((n for n, row in enumerate(index['completed'], 1)
                if row['name'] == cache['node'] and row['visit'] == cache['visit']), None))
    owner = machine if field == 'source_support' else payload
    value = owner.get(field)
    if selection is not None:
        # Only expand addresses encountered along this path, not unrelated report/ledger siblings.
        for step in _JSON_PATH_STEP_RE.findall(selection):
            if deref and field == 'output' and isinstance(value, dict) and ADDRESS_REF_KEY in value:
                value = _deref_address_refs(store, {'selected': value}, payload)['selected']
            value = _json_path_select(value, [step], 'input_path')
    if deref and field == "output":
        if selection is not None:
            try:
                value = independent_inputs._selected_value(store, index, value, payload)
            except EngineError as exc:
                raise EngineError('INPUT_REF_INVALID', 'Selected address chain is unavailable; no source-cache fallback.',
                    field='input_path', expected=selection, example=exc.as_dict()) from exc
        else:
            value = _deref_address_refs(store, value, payload)
    encoded = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if offset > len(encoded):
        raise EngineError("INPUT_REF_INVALID", "offset is beyond the end of this field")
    end = min(len(encoded), offset + limit)
    complete = offset == 0 and end == len(encoded)
    if store.read_index() != index:
        raise EngineError("INPUT_REF_INVALID", "run changed during input read; retry")
    from . import sealed_diagnostics
    proof = copy.deepcopy(machine.get('source_support')) if field == 'output' else None
    projection = {}
    if selection is not None:
        projection['selection_path'] = selection
        if field == 'output':
            projection.update(source_support_complete=False, source_support_read=dict(ref=ref, field='source_support'))
        if proof is not None:
            proof = {k: proof.get(k) for k in ('source_verified', 'derived', 'unverified', 'verification_scope', 'retrieval_provenance')}
    return {"status": "INPUT", "node": cache["node"], "visit": cache["visit"], "revision": identity["revision"],
            "sealed_capture_diagnostics": sealed_diagnostics.summary(store, [cache]),
            **(dict(review_binding_status=review_status, source_acceptance=acceptance) if review_status else {}),
            "field": field, "field_present": field in owner, "cache_sha256": expected["sha256"],
            "source_support": proof, **projection,
            **(dict(source_status=payload['status'], occurrence_completed=not incomplete_public)
               if closing and payload.get('status') in ('PARTIAL', 'FAIL') and field in ('user_summary', 'user_messages') else {}),
            **(dict(read_scope='public_only') if incomplete_public else {}),
            "encoding": "text" if isinstance(value, str) else "json", "offset": offset, "total_chars": len(encoded),
            "complete": complete, "next_offset": end if end < len(encoded) else None,
            "value": value if complete else None, "text": None if complete else encoded[offset:end]}


def _program_contract_items(store, index, program, entry):
    """Project existing program rules, not a generated synopsis or a new precedence policy."""
    if not program or entry['kind'] not in ('business', 'sub'):
        return []
    docs = list(dict.fromkeys((program.entry_file, entry.get('doc') or program.entry_file)))
    run = sha256_bytes((_fs(store.cache_dir.resolve()) + index['trace_id'] + index['started_at']).encode())
    items = []
    for doc in docs:
        pd = program.docs[doc]
        for field in ('output_mode', 'shared_constraints'):
            if field not in pd.system:
                continue
            value = pd.system[field]
            encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            identity = {'kind': 'program_contract', 'run': run, 'consumer': dict(index['current']),
                        'doc': doc, 'field': field, 'value_sha256': sha256_bytes(encoded.encode('utf-8'))}
            ref = base64.urlsafe_b64encode(json.dumps(identity, separators=(',', ':')).encode()).decode().rstrip('=')
            items.append({'scope': 'entry_program' if doc == program.entry_file else 'current_module',
                          'doc': doc, 'field': field, 'ref': ref, 'total_chars': len(encoded),
                          'value_sha256': identity['value_sha256'], 'complete': len(encoded) <= 768,
                          'value': value if len(encoded) <= 768 else None})
    return items


def read_report_context(cache_dir, field, digest, *, offset=0, limit=4096, agent_ticket=None):
    """Recover a complete terminal section; never writes PLAN, claims, caches or timing."""
    from .model_view import REPORT_CONTEXT_FIELDS, context_text
    code = 'REPORT_CONTEXT_INVALID'
    if field not in REPORT_CONTEXT_FIELDS or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 16384:
        raise EngineError(code, 'use a projected field; offset >= 0; limit 1..16384')
    store = RunStore(cache_dir)
    index = _read_input_authority(store, agent_ticket)
    entry = _catalog_entry(index, index['current']['name'])
    if entry['name'] not in (*REPORT_NODES, *ANSWER_NODES):
        raise EngineError(code, 'report context is only available to the current report or final occurrence')
    for cached in _prev_business_caches(store, index):
        source = _catalog_entry(index, cached['node'])
        raw = store.read_bytes(_cache_path_for(store, index, source, cached['visit']))
        if sha256_bytes(raw) != index['nodes'][_node_key(cached['node'], cached['visit'])]['cache_sha256']:
            raise EngineError(code, 'source digest changed')
    run_input = _read_run_input(store)
    reply = _build_reply(store, index, run_input, _load_routed_program(run_input), entry,
                         index['current']['visit'], 're_serve', None, write_plan=False)
    text = context_text(reply['input_authority'].get(field))
    if sha256_bytes(text.encode('utf-8')) != digest or store.read_index() != index:
        raise EngineError(code, 'report context changed; read the current directory')
    if offset > len(text):
        raise EngineError(code, 'offset exceeds section length')
    end = min(len(text), offset + limit)
    return dict(status='REPORT_CONTEXT', field=field, sha256=digest, encoding='json', offset=offset,
                total_chars=len(text), complete=offset == 0 and end == len(text),
                next_offset=end if end < len(text) else None, text=text[offset:end])


def read_program_contract(cache_dir, ref, *, offset=0, limit=16384, agent_ticket=None):
    """Read a served contract only; same occurrence/ticket checks as complete cache inputs."""
    code = 'PROGRAM_CONTRACT_REF_INVALID'
    if not isinstance(ref, str) or len(ref) > 4096 or type(offset) is not int or offset < 0 \
            or type(limit) is not int or not 1 <= limit <= 65536:
        raise EngineError(code, 'use the projected ref; offset >= 0 and limit 1..65536')
    store = RunStore(cache_dir)
    index = _read_input_authority(store, agent_ticket)
    program = _load_routed_program(_read_run_input(store))
    entry = _catalog_entry(index, index['current']['name'])
    row = next((r for r in _program_contract_items(store, index, program, entry) if r['ref'] == ref), None)
    if row is None:
        raise EngineError(code, 'contract source, consumer or content changed; read the current directory')
    value = program.docs[row['doc']].system[row['field']]
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if offset > len(encoded):
        raise EngineError(code, 'offset is beyond this contract')
    end = min(len(encoded), offset + limit)
    complete = offset == 0 and end == len(encoded)
    # Re-read both authorities before returning, without initializing or serving a node.
    fresh = _load_routed_program(_read_run_input(store))
    if store.read_index() != index or not any(r['ref'] == ref for r in _program_contract_items(store, index, fresh, entry)):
        raise EngineError(code, 'run or program changed during contract read; retry')
    return {'status': 'PROGRAM_CONTRACT', 'doc': row['doc'], 'field': row['field'],
            'value_sha256': row['value_sha256'], 'encoding': 'json', 'offset': offset,
            'total_chars': len(encoded), 'complete': complete, 'next_offset': end if end < len(encoded) else None,
            'value': value if complete else None, 'text': None if complete else encoded[offset:end]}


def _resume_label(reply: dict) -> str:
    """Block-header text for resume: `fresh`, `same_occurrence`, or `re_serve #n` (doc 14 D7)."""
    r = reply["resume"]
    return f"{r['kind']} #{r['serve_no']}" if r["kind"] == "re_serve" and r.get("serve_no", 1) > 1 else r["kind"]


def _ref_for_short_id(store, short: str, i: int) -> str:
    """alpha.59 B2: the input ref token for the committed occurrence <node>@<visit>, minted for the current node exactly as
    input_authority.input_refs mints it (so a short id from an older reply resolves to the same identity checks)."""
    index = store.read_index()
    om = _INPUT_OCCURRENCE_RE.match(short)
    if om and index['current']['name'] in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY):
        cache = _public_reference_cache(store, index, om.group(1), int(om.group(2)))
        if cache is not None:
            identity = _input_identity(store, index, cache)
            return base64.urlsafe_b64encode(json.dumps(identity, separators=(",", ":")).encode()).decode().rstrip("=")
    expected = []
    for cache in _public_reference_caches(store, index):
        node, visit = cache['node'], cache['visit']
        entry = _catalog_entry(index, node)
        expected.append(f"{node}@{visit}")
        if om and node == om.group(1) and visit == int(om.group(2)):
            raw = store.read_bytes(_cache_path_for(store, index, entry, visit))
            if sha256_bytes(raw) != index["nodes"][_node_key(node, visit)]["cache_sha256"]:
                raise EngineError("INPUT_REF_INVALID", "source digest changed")
            cache = strict_loads(raw.decode("utf-8"))
            identity = _input_identity(store, index, cache)
            return base64.urlsafe_b64encode(json.dumps(identity, separators=(",", ":")).encode()).decode().rstrip("=")
    raise EngineError('REPORT_PART_INVALID', f'{short} is not a committed business occurrence of this run', field=f'semantics.report_parts[{i}].ref',
                      expected=expected)


def _part_order_key(index: dict, node: str, visit: int, field: str, message_index, fallback: int = 0, revision: int = 0) -> tuple:
    """alpha.89 (doc 198; production cache/57 / 58: the answer listed every User Message before every Report): node order = the
    occurrence's position in index.completed (executed order, as the final basis uses), then the User Message items before the
    Report, messages by index. The execution report is committed last, so it stays last. An occurrence the index has not completed
    (bare projections in tests) keeps its listed position (`fallback`) after every completed one."""
    done = {(c["name"], c["visit"]): i for i, c in enumerate(index.get("completed") or [])}
    position = done.get((node, visit))
    pending_order = ('', 0, 0)
    if position is None:
        state = (index.get('nodes') or {}).get(_node_key(node, visit)) or {}
        if state.get('cache_sha256'):
            position = next((i for i, c in enumerate(index.get('completed') or []) if c['name'] in ACCOUNTING_NODES), len(done)) - 0.5
            entry = _catalog_entry(index, node) or {}
            pending_order = (state.get('ready_at') or '', entry.get('ordinal', 0), visit)
        else:
            position = 10 ** 6 + fallback
    return (position, pending_order, 0 if field == "user_messages" else 1, revision, message_index if isinstance(message_index, int) else -1)


def _part_label(part: dict) -> str:
    return f"{part['node']}@{part['visit']} {part['field']}" + (f"[{part['message_index']}]" if isinstance(part.get('message_index'), int) else "")


def _report_candidates(store, index, program) -> dict:
    """Keep accepted messages and main Reports independently, without a length floor."""
    caches = _public_reference_caches(store, index)
    # Bare projections carry no acceptance/publication proof for stopped frames.
    statuses = ('PASS', 'DEGRADED', 'PARTIAL', 'FAIL') if store is not None and (index.get('current') or {}).get('name') in (
        *ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY) else ('PASS', 'DEGRADED')
    rows = []
    for cache in caches:
        entry = _catalog_entry(index, cache["node"])
        try:
            view = _view_for(program, entry) or {}
        except Exception:   # a view problem never blocks the answer node
            view = {}
        extra = view.get("extra") or {}
        decl = extra.get("final_reference") if extra.get("final_reference") in ("required", "never") else None
        rows.append((cache, _latest_payload(cache), entry, decl, view))

    def item(cache, field, chars, why, message_index=None, revision=None):
        part = {"ref": f"{cache['node']}@{cache['visit']}", "field": field}
        if message_index is not None:
            part["message_index"] = message_index
        if revision is not None:
            part["revision"] = revision
        return {"report_part": part, "node": cache["node"], "chars": chars, "why": why,
                "revision": len(cache.get('continuations') or []) if revision is None else revision}

    required, optional = [], []
    for cache, p, _entry, decl, _view in rows:
        if p.get("status") not in statuses:
            continue
        frames = [cache, *(cache.get('continuations') or [])]
        for revision, record in enumerate(frames):
            prior = record['payload']
            if prior.get('status') not in ('PASS', 'DEGRADED', 'PARTIAL', 'FAIL'):
                continue
            historical = revision < len(frames) - 1
            for i, message in enumerate(prior.get("user_messages") or []):
                if isinstance(message, str) and message.strip():
                    required.append(item(cache, "user_messages", len(message), "accepted historical User Message" if historical else "nonblank User Message",
                                         i, revision if historical else None))
    for cache, p, entry, decl, view in rows:
        if p.get("status") not in statuses:
            continue
        summary = p.get("user_summary") if isinstance(p.get("user_summary"), str) else ""
        if not summary.strip():
            continue
        is_main = dispatch_scope.is_main(index, entry)
        public_steps = delivery_obligations.obligations(view)['required_steps']
        public_report = bool(public_steps) or delivery_obligations.write_receipt(cache, p)
        if is_main and public_report:
            required.append(item(cache, 'user_summary', len(summary), f"accepted {p['status']} public delivery or registered write receipt; no length floor"))
            continue
        if decl == 'never':
            continue
        if decl == "required":
            required.append(item(cache, "user_summary", len(summary), "declared key node (final_reference: required)"))
            continue
        if is_main:
            required.append(item(cache, "user_summary", len(summary), "main Report; messages and child Reports do not replace it"))
    report = _accounting_report_cache(store, index)
    if report is not None:   # alpha.85 (doc 182 R-b, user ruling): the answer always carries the execution report, last
        summary = _latest_payload(report).get("user_summary") or ""
        if isinstance(summary, str) and summary.strip():
            required.append(item(report, "user_summary", len(summary), "the execution report (alpha.85): the run's own accounting, always last"))
    for group in (required, optional):   # alpha.89 (doc 198): node (execution) order - the pre-filled list is the delivery order
        group[:] = [c for _, c in sorted(enumerate(group), key=lambda ic: _part_order_key(
            index, ic[1]["report_part"]["ref"].rsplit("@", 1)[0], int(ic[1]["report_part"]["ref"].rsplit("@", 1)[1]),
            ic[1]["report_part"]["field"], ic[1]["report_part"].get("message_index"), fallback=ic[0], revision=ic[1]['revision']))]
    return {"required": required, "optional": optional}


def _accounting_report_cache(store, index) -> dict | None:
    """The committed execution report of this run (its cache carries the projected Report with the machine tables), or None."""
    if store is None or not isinstance(index.get("program"), dict):   # a candidate computation over a bare index (tests, projections)
        return None
    for done in index.get("completed") or []:
        if done["name"] in ACCOUNTING_NODES:
            path = store.node_cache_path(_program_name(index), done["name"], done["visit"])
            if store.exists_path(path):
                return store.read_json(path)
    return None


def _check_required_references(store, index, program, payload: dict, report_parts) -> None:
    """alpha.69: a `Engine.final-answer` commit must carry every required report_part (FINAL_REFERENCE_REQUIRED); a FAIL answer is exempt."""
    if payload.get("status") == "FAIL":
        return
    required = _report_candidates(store, index, program)["required"]
    if not required:
        return
    have = {(p["node"], p["visit"], p['revision'], p["field"], p.get("message_index")) for p in report_parts or []}

    def key(candidate):
        part = candidate["report_part"]
        node, visit = part["ref"].rsplit("@", 1)
        return (node, int(visit), candidate['revision'], part["field"], part.get("message_index"))

    missing = [c["report_part"] for c in required if key(c) not in have]
    if missing:
        raise EngineError("FINAL_REFERENCE_REQUIRED",
                          f"the final answer omits {len(missing)} of {len(required)} reports this run already delivered: "
                          + ", ".join(f"{m['ref']} {m['field']}" + (f"[{m['message_index']}]" if 'message_index' in m else '') for m in missing),
                          field="semantics.report_parts", expected=missing, example=[c["report_part"] for c in required])


def _resolve_report_parts(store, payload):
    """Snapshot selected public text before any commit write; persisted in machine provenance."""
    parts = (payload.get('semantics') or {}).get('report_parts')
    if parts is None:
        return None
    if payload['node'] not in ANSWER_PART_NODES or payload.get('gate'):
        raise EngineError('REPORT_PART_INVALID', 'report_parts is only for the `Engine.final-answer` commit (or a legacy Router.summary)', field='semantics.report_parts')
    resolved, seen = [], set()
    for i, part in enumerate(parts):
        field, message_index = part['field'], part.get('message_index')
        if (field == 'user_messages') != ('message_index' in part):
            raise EngineError('REPORT_PART_INVALID', 'user_messages requires message_index; user_summary forbids it', field=f'semantics.report_parts[{i}]')
        if 'revision' in part and field != 'user_messages':
            raise EngineError('REPORT_PART_INVALID', 'historical revisions only select accepted User Messages', field=f'semantics.report_parts[{i}].revision')
        ref = part['ref']
        om = _INPUT_OCCURRENCE_RE.match(ref) if isinstance(ref, str) else None
        if om and om.group(1) in ACCOUNTING_NODES:   # alpha.85 (doc 182 R-b): the execution report, from its own cache
            index = store.read_index()
            node, visit = om.group(1), int(om.group(2))
            if field != 'user_summary' or not any(c['name'] == node and c['visit'] == visit for c in index['completed']):
                raise EngineError('REPORT_PART_INVALID', 'the execution report is referenced as <report node>@<visit> with field user_summary, once committed',
                                  field=f'semantics.report_parts[{i}]')
            raw = store.read_bytes(store.node_cache_path(_program_name(index), node, visit))
            if sha256_bytes(raw) != index['nodes'][_node_key(node, visit)]['cache_sha256']:
                raise EngineError('REPORT_PART_INVALID', 'execution report digest changed', field=f'semantics.report_parts[{i}].ref')
            cache = strict_loads(raw.decode('utf-8'))
            value = _latest_payload(cache).get('user_summary')
            if not isinstance(value, str) or not value.strip():
                raise EngineError('REPORT_PART_INVALID', 'the execution report is empty', field=f'semantics.report_parts[{i}]')
            identity = dict(_input_identity(store, index, cache), cache_sha256=index['nodes'][_node_key(node, visit)]['cache_sha256'], field=field, message_index=None)
            key = (node, visit, identity['revision'], field, None)
            if key in seen:
                raise EngineError('REPORT_PART_INVALID', 'duplicate source selection', field=f'semantics.report_parts[{i}]')
            seen.add(key)
            extra = {}
            meta = (cache['continuations'][-1] if cache.get('continuations') else cache).get('machine', {}).get('execution_report')
            if meta:
                from . import execution_report
                try:
                    extra['execution_report_display'] = execution_report.verify(meta, value,store.cache_dir.name,node,visit)
                except ValueError as exc:
                    raise EngineError('REPORT_PART_INVALID', str(exc)) from exc
            resolved.append(dict(identity, text=value, text_sha256=sha256_bytes(value.encode('utf-8')), **extra))
            continue
        if om:   # alpha.59 B2 (doc 121 §6): <node>@<visit> from input_refs[].id
            ref = _ref_for_short_id(store, ref, i)
        chunks, offset, identity = [], 0, None
        while True:
            try:
                page = read_input(store.cache_dir, ref, field=field, offset=offset, limit=65536)
            except EngineError as exc:
                raise EngineError('REPORT_PART_INVALID', str(exc), field=f'semantics.report_parts[{i}].ref') from exc
            identity = {k: page[k] for k in ('node', 'visit', 'revision', 'cache_sha256', 'field')}
            if page['complete']:
                value = page['value']
                break
            chunks.append(page['text'])
            if page['next_offset'] is None:
                value = ''.join(chunks)
                if page['encoding'] == 'json':
                    value = strict_loads(value)
                break
            offset = page['next_offset']
        if 'revision' in part:
            # Final composition alone may select accepted history; ordinary input reads remain latest-bound.
            revision = part['revision']
            if type(revision) is not int or not 0 <= revision < identity['revision']:
                raise EngineError('REPORT_PART_INVALID', 'revision must identify an earlier accepted frame', field=f'semantics.report_parts[{i}].revision')
            index = store.read_index()
            path = _cache_path_for(store, index, _catalog_entry(index, identity['node']), identity['visit'])
            raw = store.read_bytes(path)
            if sha256_bytes(raw) != identity['cache_sha256']:
                raise EngineError('REPORT_PART_INVALID', 'source digest changed', field=f'semantics.report_parts[{i}].ref')
            prior = _payload_at_revision(strict_loads(raw.decode('utf-8')), revision)
            if prior.get('status') not in ('PASS', 'DEGRADED', 'PARTIAL', 'FAIL'):
                raise EngineError('REPORT_PART_INVALID', 'revision is not an accepted public message frame', field=f'semantics.report_parts[{i}].revision')
            value = prior.get('user_messages')
            identity = dict(identity, revision=revision, historical_user_message=True)
        if field == 'user_messages':
            if not isinstance(value, list) or type(message_index) is not int or message_index >= len(value):
                raise EngineError('REPORT_PART_INVALID', 'message_index is outside the original array', field=f'semantics.report_parts[{i}].message_index')
            value = value[message_index]
        if not isinstance(value, str) or not value.strip():
            raise EngineError('REPORT_PART_INVALID', 'selected public report is empty or missing', field=f'semantics.report_parts[{i}]')
        key = (identity['node'], identity['visit'], identity['revision'], field, message_index)
        if key in seen:
            raise EngineError('REPORT_PART_INVALID', 'duplicate source selection', field=f'semantics.report_parts[{i}]')
        seen.add(key)
        source_state = {}
        if page.get('source_status'):
            source_state = dict(source_status=page['source_status'], occurrence_completed=page['occurrence_completed'])
        resolved.append(dict(identity, message_index=message_index, text=value, text_sha256=sha256_bytes(value.encode('utf-8')), **source_state))
    return resolved


_SKELETON_BASE_KEYS = ["schema_version", "node", "status", "output", "user_summary", "user_messages", "steps", "evidence",
                       "anomalies", "degraded_reason"]
_SKELETON_OPTIONAL_KEYS = ["error_type", "vars", "next_hint", "dispatch_fallback", "gate", "gate_not_triggered_reason", "explain"]


STREAM_REPORT_RULE = _contracts.text("core.stream_report")
STREAM_TEXTS_RULE = _contracts.text("core.stream_texts")


GATE_STREAM_RULE = _contracts.text("gate.stream")


SUBAGENT_TEXTS_RULE = _contracts.text("core.subagent_texts")   # alpha.62 (doc 135 §3.2 G1): a spawned sub-agent has no captured stream


def _gate_streams(host_fences) -> bool:
    return "gate" in {str(f) for f in (host_fences or ())}


def _stream_rule(host_fences) -> str:
    """alpha.44: which texts the model streams before committing follows what the host captures (index host.host_fences, reported by
    prepare_cache); a host that captures only the Report keeps the alpha.30 wording, so an un-restarted host changes nothing."""
    fences = {str(f) for f in (host_fences or ()) if str(f) in HOST_FENCES}
    return STREAM_TEXTS_RULE if fences & {"message", "explain"} else STREAM_REPORT_RULE


ADDRESS_REF_RULE = _contracts.text("evidence.address_refs")   # alpha.57/58/63/64 (docs 121 §8.5 / §9, 122, 125, 137, 140): reference first - a value that exists in a file is its address
OUTPUT_SCHEMA_RULE = _contracts.text("node.output_schema")   # alpha.59 (doc 128 §6): the program's output declaration, compiled and served as a JSON Schema fragment
OUTPUT_CONTENT_RULE = _contracts.text("node.output_content")   # alpha.58 B8 / B9 (doc 125 §5, §9.2): output = declared keys + machine facts; narration belongs in Explain


def _payload_skeleton(name: str, steps: list, *, gate_required: bool = False, gate_advisory: bool = False,
                      successors: list | None = None, default_successor: str | None = None,
                      gate_answered: dict | None = None, host_fences: list | tuple | None = None, sub_agent: bool = False,
                      facts: dict | None = None, write_target: str | None = None) -> tuple[dict, list[str]]:
    """doc 16 B-1: a ready-to-fill node-commit payload for this node plus the rules the schema will enforce on it.
    sub_agent (alpha.62): the reply goes to a spawned sub-agent - SUB-AGENT TEXTS replaces the STREAM rules (doc 135 G1).

    Pure: no store / index access, so the shape can be unit-tested and the sub-agent can rely on it instead of reading
    schemas/commit.v1.json. The skeleton keeps the required ten keys, presets steps.done to every served step key and
    adds the node-kind specific keys (route / outer_nodes_in_path / semantics / gate / next_hint) as placeholders.
    facts (alpha.100, doc 241 D7): a dict to fill with the node values the rules name (step / accepted / sys keys, next_hint, answered gate);
    the rules themselves are unchanged - their delivery texts point to those fields (_deliver_contracts)."""
    keys = [s["key"] for s in steps]
    skeleton = {"schema_version": 1, "node": name, "status": "PASS", "output": {}, "user_summary": "", "user_messages": [],
                "steps": {"done": list(keys), "remaining": [], "not_applicable": []},
                "evidence": {"tool_calls": [], "artifacts": [], "sources": []}, "anomalies": [], "degraded_reason": None, "explain": ""}
    allowed = list(_SKELETON_BASE_KEYS) + list(_SKELETON_OPTIONAL_KEYS)
    if write_target or any(re.search(r'\btarget_aiap_dir\b', str(s.get('text', ''))) for s in steps):
        allowed.append('target_aiap_dir')
    rules = [
        _contracts.text("core.skeleton"),
        _contracts.text("core.steps", _facts=_FACT_POINTERS["core.steps"], keys=keys),
        _contracts.text("core.status"),
        _contracts.text("core.tool_calls"),
        _contracts.text("evidence.process"),
        _contracts.text("evidence.artifacts"),
        _contracts.text("evidence.sources"),
        _contracts.text("core.anomalies"),
        _contracts.text("core.no_timings"),
        _contracts.text("core.json_text"),
    ]
    rules.extend([   # alpha.23 (doc 45, v6.25.0 render_contract business_node_info): how the three rendered bodies are written
        _contracts.text("core.user_message"),
        _contracts.text("core.report"),
        SUBAGENT_TEXTS_RULE if sub_agent else _stream_rule(host_fences),   # alpha.30 STREAM THE REPORT, or alpha.44 STREAM YOUR TEXTS; alpha.62 sub-agent
        _contracts.text("core.explain"),
        _contracts.text("core.final_answer_frame"),
    ])
    if name in ANSWER_NODES:   # alpha.45: the answer node streams only the answer - no Report / Explain / User Message rules
        rules = [r for r in rules if not r.startswith(("USER MESSAGE (", "REPORT (", "STREAM ", "EXPLAIN (", "FINAL ANSWER:"))]
    if name not in (NODE_MATCH, NODE_SETUP):
        if any('source_verified' in str(s.get('text', '')) or 'support_check' in str(s.get('text', '')) for s in steps):
            rules.append(source_support.RULE)
        rules.extend([
            _contracts.text("node.quality"),
            _contracts.text("evidence.attitude"),
        ])
    if name not in (NODE_MATCH, NODE_SETUP, *ANSWER_NODES) and name not in REPORT_NODES:
        rules.append(ADDRESS_REF_RULE)   # alpha.57: business / sub nodes address large existing values instead of retyping them
        rules.append(OUTPUT_CONTENT_RULE)   # alpha.58 B8 / B9
        allowed.append("user_message")   # alpha.93 (doc 218): the executor's declaration of what this node gives the user
        skeleton["user_message"] = {"has": None, "items": [], "not_applicable": [], "none_reason": None}
    if name not in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY):   # alpha.87 (doc 193): every node the model may meet a doubt / problem / bug at
        allowed.append("hsaw_items")
    sys_keys = [s["key"] for s in steps if s.get("sys")]
    assert_keys = [s["key"] for s in steps if s.get("sys") and str(s["sys"].get("name") or "").startswith("sys.assert")]
    if sys_keys:
        rules.append(_contracts.text("core.sys_steps", _facts=_FACT_POINTERS["core.sys_steps"], sys_keys=sys_keys))
    if assert_keys:
        rules.append(_contracts.text("core.sys_assert", _facts=_FACT_POINTERS["core.sys_assert"], assert_keys=assert_keys))
    if name == NODE_MATCH:
        skeleton["route"] = {"package": "<one of input_authority.registry_snapshot[].package, or no_match>", "rationale": ""}
        allowed += ["route", "gate"]
        rules.append(_contracts.text("start.route", gate_fields=_GATE_FIELDS))
        if _gate_streams(host_fences):
            rules.append(GATE_STREAM_RULE)   # alpha.45: the candidates gate streams its text too
    elif name == NODE_SETUP:
        skeleton["outer_nodes_in_path"] = []
        allowed.append("outer_nodes_in_path")
        rules.append(_contracts.text("cache.outer_path"))
    elif name in REPORT_NODES:
        skeleton["semantics"] = {"intent": "", "result_summary": "", "functional_status": "PASS", "nodes_skipped": [],
                                 "per_node": [{"node": "<node name>", "material_action": "", "result": ""}]}
        allowed.append("semantics")
        rules.append(_contracts.text("execute-report.semantics", name=name))
        rules.append(_contracts.text("execute-report.streams", name=name))
        rules.append(_contracts.text("execute-report.report_delivery"))
        if name in ACCOUNTING_NODES:
            rules = [rule for rule in rules if not rule.startswith(('REPORT DELIVERY', 'FINAL ANSWER:'))]
            rules.append(final_answer.EXECUTION_REPORT_RULE)
            rules.append(_contracts.text("execute-report.no_business_answer"))
        else:
            rules.append(final_answer.LEGACY_SYNTHESIS_RULE)
    elif name in ANSWER_NODES:   # alpha.45 (doc 91): the answer node - REFERENCE FIRST -> FINAL SYNTHESIS -> STREAM THE ANSWER -> FINAL FORMAT -> H2
        skeleton["user_summary"] = FINAL_NOTE
        skeleton["output"] = "final_answer"
        skeleton["semantics"] = {"final_answer": ""}
        allowed.append("semantics")
        rules.append(_contracts.text("final-answer.keep", final_note=repr(FINAL_NOTE)))
        rules.append(final_answer.REFERENCE_RULE)   # alpha.42 E1: reference complete reports instead of retyping them
        rules.append(FINAL_REFERENCE_RULE)   # alpha.69 (doc 147): the required references are a hard requirement
        rules.append(final_answer.SYNTHESIS_RULE)
        if "answer" in {str(f) for f in (host_fences or ())}:
            rules.append(final_answer.ANSWER_STREAM_RULE)   # alpha.44 / alpha.45: the whole answer streams as :::answer Engine.final-answer
        rules.append(_contracts.text("final-answer.format"))
    else:
        if gate_answered:   # doc 16 B-1b: same_occurrence resume - the gate is closed, never resubmit it
            rules.append(_contracts.text("resume.answered_note"))
            allowed += ["gate_not_triggered_reason"]
            rules.append(_contracts.text("resume.prior_gate", question_id=gate_answered.get('question_id'), chosen_intent=repr(gate_answered.get('chosen_intent'))))
            if facts is not None:
                facts["answered_gate"] = {"question_id": gate_answered.get("question_id"), "chosen_intent": gate_answered.get("chosen_intent")}
        elif gate_required or gate_advisory:
            skeleton["gate"] = json.loads(json.dumps(_EXAMPLES["gate"]))
            allowed += ["gate", "gate_not_triggered_reason"]
            rules.append(_contracts.text("gate.declared", gate_fields=_GATE_FIELDS, declared_gate_scope=_DECLARED_GATE_SCOPE, gate_scope_rule=_GATE_SCOPE_RULE))
        if (gate_required or gate_advisory) and _gate_streams(host_fences) and not sub_agent:
            rules.append(GATE_STREAM_RULE)   # alpha.45: a program gate streams its text too (never from a sub-agent, alpha.62)
        succ = list(successors or [])
        if len(succ) > 1:
            if default_successor is None:
                skeleton["next_hint"] = "<one of: " + " | ".join(succ) + ">"
            rules.append(f"next_hint must be one of {succ}" + (f" (omit it to take the planned successor {default_successor!r})." if default_successor else " (required: no planned successor)."))
            if facts is not None:   # alpha.100 (doc 241 D7): delivered as node_facts.next_hint instead of this sentence
                facts["next_hint"] = {"one_of": succ, "omit_to_take": default_successor} if default_successor else {"one_of": succ, "required": True}
    if name not in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY):   # alpha.88 (doc 196 F2): the HSAW rule follows the node's own gate / branch rules
        rules.append(hsaw_gate.RULE)
    if not any(_GATE_SCOPE_RULE in rule for rule in rules):
        rules.append(_GATE_SCOPE_RULE)
    rules.append(_contracts.text("core.top_level_keys", _facts=_FACT_POINTERS["core.top_level_keys"], accepted=", ".join(dict.fromkeys(allowed))))
    rules.append(_contracts.text("core.submit"))
    if facts is not None:   # alpha.100 (doc 241 D7): the values the sections refer to, as fields of the reply
        extra = {k: facts.pop(k) for k in list(facts)}
        facts.update(step_keys=keys, accepted_keys=list(dict.fromkeys(allowed)))
        if sys_keys:
            facts["sys_step_keys"] = sys_keys
        if assert_keys:
            facts["sys_assert_step_keys"] = assert_keys
        facts.update(extra)
    if not sub_agent and name not in ANSWER_NODES:
        stream_rule = _stream_rule(host_fences)
        rules.remove(stream_rule)
        rules.insert(0, stream_rule)
    return skeleton, rules


# ---------------------------------------------------------------------------
# alpha.100 (04 series docs 214 / 215 / 241): mixed contract delivery
# ---------------------------------------------------------------------------

CONTRACT_RESEND_AFTER = 25   # S3: a section given this many serves ago in the same session is sent again (a long session may be summarised)
CONTRACT_REFUSAL_CAP = 6000   # S4: at most this many characters of section text ride on one refusal; the rest are named
CONTRACTS_LINE = (
    "CONTRACTS (alpha.100): contracts names every rule section of this node. inline: full text below, each tagged [<section> vN]. "
    "given: sent earlier in this session and still binding; no longer in your context? run next_node.py --cache-dir <same-cache> "
    "--contract <section>. node_facts: this node's values the sections refer to."
)
_FACT_POINTERS = {   # D7: the four values that change on every node are node_facts fields, so these sections read the same on every node
    "core.steps": {"keys": "node_facts.step_keys"},
    "core.top_level_keys": {"accepted": "node_facts.accepted_keys"},
    "core.sys_steps": {"sys_keys": "node_facts.sys_step_keys"},
    "core.sys_assert": {"assert_keys": "node_facts.sys_assert_step_keys"},
}
_NEXT_HINT_LINE = "next_hint must be one of "
_CODE_SECTIONS = (   # S4: the sections a refusal concerns; the first entry whose prefix the code starts with decides
    (("SCHEMA_INVALID", "MACHINE_FIELD_REJECTED", "NODE_MISMATCH"), ("core.skeleton", "core.top_level_keys")),
    (("JSON_INVALID",), ("core.json_text", "core.submit")),
    (("UNTRUSTED_TIMING_CLAIM",), ("core.no_timings",)),
    (("STEPS_NOT_CLOSED", "SUBSTEPS_INCOMPLETE"), ("core.steps",)),
    (("EVIDENCE_MISSING_FOR_SYS_STEP",), ("core.sys_steps", "core.tool_calls")),
    (("ASSERTION_RESULT_MISMATCH",), ("core.sys_assert",)),
    (("PROCESS_", "EVIDENCE_STDOUT", "EVIDENCE_SNAPSHOT"), ("evidence.process", "core.tool_calls")),
    (("ARTIFACT_", "DIRECTORY_MEMBERS", "PATH_INVALID"), ("evidence.artifacts",)),
    (("SOURCE_SUPPORT", "SOURCE_VERIFICATION", "SOURCE_DIAGNOSTICS"), ("evidence.source_support", "evidence.source_repair")),
    (("SOURCE_",), ("evidence.sources",)),
    (("REF_TARGET",), ("evidence.address_refs",)),
    (("OUTPUT_SCHEMA",), ("node.output_schema", "node.output_content")),
    (("USER_MESSAGE_",), ("core.user_message", "node.public_obligations")),
    (("HOST_TEXT_UNAVAILABLE_SUBAGENT",), ("core.subagent_texts",)),
    (("HOST_TEXT_", "REPORT_NOT_RECEIVED"), ("core.stream_texts", "core.stream_report", "gate.stream", "execute-report.streams",
                                            "final-answer.answer_stream")),
    (("GATE_ALREADY_ANSWERED",), ("resume.answered_note", "resume.prior_gate")),
    (("GATE_", "ROUTE_"), ("start.route", "gate.declared", "gate.scope")),
    (("HSAW_",), ("hsaw.doubt_gate",)),
    (("REPORT_PART", "FINAL_REFERENCE", "FINAL_LEAD", "FINAL_SOURCE"), ("final-answer.reference_required", "final-answer.reference")),
    (("FINAL_",), ("final-answer.keep", "final-answer.synthesis", "final-answer.format")),
    (("REPORT_",), ("execute-report.semantics", "execute-report.execution_report")),
    (("CONTINUATION_EVIDENCE",), ("resume.continuation_evidence",)),
)


def _new_delivery_ledger() -> dict:
    return {"sessions": 0, "serves": 0, "session_serves": 0, "given": {}, "reads": [], "last": None,
            "stats": {"inline_sections": 0, "inline_chars": 0, "given_sections": 0, "resent_after_gap": 0, "sub_agent_full": 0}}


def _group_sections(keys: list[str]) -> dict:
    """{contract: [section names]} in serve order; a composed rule is one entry (e.g. synthesis+reasoning)"""
    out: dict = {}
    for key in keys:
        cid = _contracts.contract_of(key)
        out.setdefault(cid, []).append("+".join(p.split(".", 1)[1] if _contracts.contract_of(p) == cid else p for p in key.split("+")))
    return out


def _deliver_contracts(index: dict, reply: dict, *, session: str, sub_agent: bool) -> None:
    """alpha.100 (doc 241; doc 215 D2 / D7 / D8, S1-S7): payload_rules carry a section's full text the first time this model session needs
    it and only name it afterwards (reply.contracts). session "new" - a direct next-node call, each one a new CLI session (doc 214 §1.1) -
    clears the session ledger; "continue" - the next_plan of a commit - keeps it. A spawned sub-agent always gets every section in full
    and leaves the main session's ledger alone (S1). A section whose delivery text differs from the one given (this node's values) or
    that was given CONTRACT_RESEND_AFTER serves ago is sent again (S3). The texts are those _payload_skeleton assembled: tagged, and the
    four node values pointing to node_facts; the next_hint sentence becomes node_facts.next_hint."""
    rules = reply.get("payload_rules")
    if not isinstance(rules, list):
        return
    if session not in ("new", "continue"):
        raise ValueError(f"session must be new or continue, not {session!r}")
    led = index.get("contract_delivery") or _new_delivery_ledger()
    index["contract_delivery"] = led
    stats = led["stats"]
    if sub_agent:
        scope = None
        if dispatch_scope.enabled(index):
            _, scope = _self_dispatch(index, _catalog_entry(index, index['current']['name']), index['current']['visit'])
        segment = scope.setdefault('contract_delivery', dict(serves=0, given={})) if scope else None
        if segment is not None:
            if session == 'new':
                segment['given'] = {}
            segment['serves'] += 1
        given: dict = segment['given'] if segment else {}
        stats["sub_agent_full"] += 1
    else:
        if session == "new":
            led["sessions"] += 1
            led["session_serves"] = 0
            led["given"] = {}
        led["session_serves"] += 1
        led["serves"] += 1
        given = led["given"]
    now = segment['serves'] if sub_agent and segment else led["session_serves"]
    facts = reply.get("node_facts") or {}
    out, inline, named, applicable = [CONTRACTS_LINE], [], [], set()
    for rule in rules:
        if not isinstance(rule, _contracts.Rule):
            if not (facts.get("next_hint") and rule.startswith(_NEXT_HINT_LINE)):
                out.append(rule)
            continue
        applicable.update(rule.key.split("+"))
        applicable.update(rule.parts)
        sha = _contracts.digest(rule.delivery)
        seen = given.get(rule.key)
        if seen and seen["sha"] == sha and now - seen["serve"] < CONTRACT_RESEND_AFTER:
            named.append(rule.key)
            continue
        if seen and seen["sha"] == sha:
            stats["resent_after_gap"] += 1
        text = _contracts.tag(rule.key) + rule.delivery
        out.append(text)
        inline.append(rule.key)
        stats["inline_sections"] += 1
        stats["inline_chars"] += len(text)
        if not sub_agent or segment is not None:
            given[rule.key] = {"sha": sha, "serve": now}
            for key, part_sha in rule.parts.items():
                given[key] = {"sha": part_sha, "serve": now}
    stats["given_sections"] += len(named)
    reply["payload_rules"] = out
    reply["contracts"] = {"inline": _group_sections(inline), "given": _group_sections(named)}
    if inline:   # S5: named at the top of the reply
        known = _contracts.versions()
        reply["contracts_attached"] = "CONTRACTS ATTACHED: " + ", ".join(
            f"{cid} v{known[cid]} ({len(names)} section{'s' if len(names) > 1 else ''})" for cid, names in _group_sections(inline).items()
        ) + " - full text in payload_rules"
    if "hsaw.doubt_gate" not in inline:   # D8: the HSAW item example and taxonomy travel with their section
        reply.pop("hsaw_item_example", None)
        reply.pop("hsaw_taxonomy", None)
    if not sub_agent:
        led["last"] = {"node": (reply.get("node") or {}).get("name"), "sections": sorted(applicable)}


def _contract_read_text(section_id: str) -> str:
    """The delivery text of one section outside a node reply: the four node values point to node_facts; the other placeholders carry
    their fixed value or name the node_facts field / node they depend on."""
    fixed = {"gate_fields": _GATE_FIELDS, "declared_gate_scope": _DECLARED_GATE_SCOPE, "gate_scope_rule": _GATE_SCOPE_RULE,
             "final_note": repr(FINAL_NOTE), "name": NODE_REPORT,
             "question_id": "node_facts.answered_gate.question_id", "chosen_intent": "node_facts.answered_gate.chosen_intent",
             "where": "node_facts.cancelled.where", "dropped": "node_facts.cancelled.dropped", "dropped_count": "len(node_facts.cancelled.dropped)"}
    values = {p: fixed.get(p, f"<{p}>") for p in _contracts.placeholders(section_id)}
    return _contracts.text(section_id, _facts=_FACT_POINTERS.get(section_id), **values).delivery


def _refusal_sections(index: dict, node: str, codes: list, help_text: str, sub_agent: bool) -> dict:
    """alpha.100 (doc 241 S4): a refused commit carries the full text of the sections it concerns - the moment the model corrects is the
    moment the exact text helps (doc 211). Narrowed to the sections served to this node when the ledger knows them; a section the help
    already quotes is not repeated; at most CONTRACT_REFUSAL_CAP characters, further sections named."""
    wanted: list[str] = []
    for code in codes:
        for prefixes, ids in _CODE_SECTIONS:
            if any(str(code or "").startswith(p) for p in prefixes):
                wanted.extend(i for i in ids if i not in wanted)
                break
    last = (index.get("contract_delivery") or {}).get("last") or {}
    if wanted and not sub_agent and last.get("node") == node:
        wanted = [s for s in wanted if s in set(last.get("sections") or ())] or wanted
    known = _contracts.sections()
    wanted = [s for s in wanted if known[s][:80] not in (help_text or "")]
    if not wanted:
        return {}
    sections, more, size = {}, [], 0
    for sid in wanted:
        text = _contracts.tag(sid) + _contract_read_text(sid)
        if sections and size + len(text) > CONTRACT_REFUSAL_CAP:
            more.append(sid)
            continue
        sections[sid] = text
        size += len(text)
    return {"contract_sections": sections, **({"contract_sections_more": more} if more else {})}


def _contract_ids(ident: str) -> list[str]:
    known = _contracts.sections()
    ids: list[str] = []
    for part in str(ident or "").replace("#", ".").split("+"):
        part = part.strip()
        found = [part] if part in known else [s for s in known if _contracts.contract_of(s) == part]
        if not found:
            raise EngineError("CONTRACT_UNKNOWN", f"{part!r} is neither a contract ({', '.join(_contracts.versions())}) nor one of their sections "
                                                  "(e.g. gate, gate#declared, core.steps)")
        ids.extend(s for s in found if s not in ids)
    return ids


def read_contract(cache_dir: str | Path, ident: str, *, agent_ticket: str | None = None) -> dict:
    """alpha.100 (doc 241 S6): next_node.py --contract <id>[#section] - the full text of a contract or of sections, as the node replies
    send it. Read-only: it never initialises, serves or commits; a read in an existing run is recorded in the index
    (contract_delivery.reads, the last 200) without touching updated_at, so the delivery can be audited."""
    ids = _contract_ids(ident)
    out = {"status": "CONTRACT", "contract": ident, "sections": {sid: _contracts.tag(sid) + _contract_read_text(sid) for sid in ids},
           "note": "The text the node replies send; node_facts.<field> names a field of the current node reply."}
    if any(_contracts.contract_of(s) == "hsaw" for s in ids):
        out["hsaw_item_example"] = _contracts.example("hsaw.doubt_gate")
        out["hsaw_taxonomy"] = hsaw_gate.taxonomy()
    store = RunStore(cache_dir)
    out["recorded"] = False
    if store.exists():
        with store.lock():
            index = store.read_index()
            led = index.get("contract_delivery") or _new_delivery_ledger()
            led["reads"] = (led["reads"] + [{"at": now_iso(), "id": str(ident)[:200], "agent": bool(agent_ticket), "serve": led["serves"]}])[-200:]
            index["contract_delivery"] = led
            store.write_index(project_host_fields(index))
        out["recorded"] = True
    return out


_CANDIDATE_SUFFIXES = (".md", ".txt", ".html", ".htm", ".json", ".csv", ".xml")
_CANDIDATE_MAX = 80
_ENGINE_WORK_DIRS = ("replies", "_receipts")   # docs/05SoulRun 87: the engine's reply echoes and their acceptance receipts under _work/
SOURCE_CANDIDATES_RULE = (
    "A source_verified claim needs content_kind original and a content_ref naming the saved original it was located in: one of these "
    "work: files when it holds fetched original content (never your own notes, scripts or reconstructions), proc:<stdout_path> of a capture "
    "in THIS payload's tool_calls, or a file this node saves now (work: / artifact:). evidence_span is copied verbatim from that file and "
    "contains the claim's value. A source without a saved original is search_summary / unknown and its claims are unverified (alpha.97). "
    "Instead of copying evidence_span you may give support_check.evidence_locator {anchor, until}: the engine cuts the passage from "
    "the saved original itself (alpha.98)."
)


def _source_support_candidates(store: RunStore) -> dict:
    """alpha.97 (04 series doc 232 A): the files saved under this run's _work/ that a source_verified claim may name as its original, served
    beside the source input template - in production GenerateReport claimed source_verified for URL-only sources in 12 refused commits."""
    root = store.cache_dir / "_work"
    found = []
    if root.is_dir():
        for path in root.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if rel.split("/", 1)[0] in _ENGINE_WORK_DIRS or path.suffix.lower() not in _CANDIDATE_SUFFIXES or not path.is_file():
                continue
            stat = path.stat()
            if 0 < stat.st_size <= PROC_MAX_BYTES:
                found.append((rel.count("/"), -stat.st_mtime_ns, rel, path, stat.st_size))
    # docs/05SoulRun 87 (doc 233 plan: _work's top level): top level first, then each deeper level, newest first within a level - a
    # program's own deep copies (sandbox / backup trees) no longer fill the cap before the saved originals, and the list follows the run
    # (run 7: one name-sorted list of 80 copies sent 94 times, the saved originals never in it). Deeper files fill only the room left.
    found.sort(key=lambda row: row[:3])
    items = [{"address": f"work:{rel}", "bytes": size, "sha256": sha256_bytes(path.read_bytes())[:12]}
             for _depth, _age, rel, path, size in found[:_CANDIDATE_MAX]]
    return {"items": items, "more": len(found) > _CANDIDATE_MAX, "rule": SOURCE_CANDIDATES_RULE}


def _source_template_needed(program, entry, steps, schema_out, prev_caches):
    shared = []
    if program:
        for doc in dict.fromkeys((program.entry_file, entry.get('doc') or program.entry_file)):
            system = program.docs[doc].system
            shared.extend(system[field] for field in ('shared_constraints', 'output_mode') if field in system)
    # Assistance follows explicit declarations, never the user's query or a business-node name.
    text = json.dumps([steps, schema_out, shared], ensure_ascii=False)
    return bool(re.search(r'(?<!\w)(?:source_verified|support_check|web_search|web_fetch)(?!\w)', text) or
                (re.search(r'(?<!\w)sources(?!\w)', text) and re.search(r'(?<!\w)retrieved_at(?!\w)', text)) or
                any(r['machine'].get('source_support') for c in prev_caches for r in _evidence_records(c)))


def _build_reply(store, index, run_input, program, entry, visit, resume_kind, gate_answer, *, mode: dict | None = None,
                 dispatch: dict | None = None, write_plan: bool = True, sub_agent: bool = False) -> dict:
    kind = entry["kind"]
    position = _position(index)
    steps = _served_steps(entry, program)
    prev_caches = _public_reference_caches(store, index)
    prev_summary = _latest_payload(prev_caches[-1])["user_summary"] if prev_caches else None
    mode = mode or {"declared": "inline", "effective": "inline", "downgrade": None}
    reply = {"node": {"name": entry["name"], "kind": kind, "parent": entry.get("parent"), "depth": entry["depth"], "bare": _bare(entry),
                      "position": position, "mode": mode},
             "steps": steps, "budget": _budget_for(kind, program),
             "resume": {"kind": resume_kind, "source": gate_answer["question_id"] if gate_answer else None,
                        "serve_no": int((index["nodes"].get(_node_key(entry["name"], visit)) or {}).get("serves") or 1)},
             "frame": None, "module": None, "dispatch": dispatch}
    if kind == "engine":
        reply["reserved"], reply["topology"] = None, None
        ia = {"prev_node_summary": prev_summary, "user_message": run_input.get("user_message"),
              "assert": None, "required_fields": None, "context": index["context"], "gate_answer": gate_answer}
        if entry["name"] == NODE_MATCH:
            ia["registry_snapshot"] = [{k: s.get(k) for k in registry.PROJECTED_FIELDS} for s in run_input["snapshot"]]
            ia["previous_route"] = run_input.get("previous_route")   # alpha.21: the session's last routed package (doc 41 §7.3)
        elif entry["name"] == NODE_SETUP:
            main = program.entry.tasks.get("main") if program else None
            ia["program"] = {"entry_path": index["program"]["entry_path"], "name": index["program"]["name"],
                             "main_nodes": list(main["order"]) if main else [],
                             "entry_node": aisop_parse.entry_nodes(main)[0] if main and main["order"] else None,
                             "end_nodes": [n for n in main["order"] if main["node_types"].get(n) == "end"] if main else []}
        elif entry["name"] in REPORT_NODES or entry["name"] in ANSWER_NODES:   # alpha.45: the answer node reads the same materials
            from . import tool_faults
            main_caches = [c for c in prev_caches if dispatch_scope.is_main(index, _catalog_entry(index, c['node']))]
            ia["node_summaries"] = [{"node": c["node"], "visit": c["visit"], "status": _latest_payload(c)["status"],
                                     "user_summary": _latest_payload(c)["user_summary"], "output": _output_text(_latest_payload(c))[:400],
                                     "anomalies": _latest_payload(c).get("anomalies", [])}
                                    for c in main_caches]
            ia['final_context'] = {
                'human_decisions': [copy.deepcopy(h) for h in index['gate']['history'] if h.get('resolution_kind') in ('chosen', 'free_text')],
                'recorded_exceptions': [dict(node=c['node'], visit=c['visit'], revision=n, record=a)
                                        for c in prev_caches for n, r in enumerate(_evidence_records(c))
                                        for a in (r['payload'].get('anomalies') or []) + (r['machine'].get('engine_anomalies') or [])],
                'run_observations': copy.deepcopy(index['anomalies_summary']),
                'machine_recoveries': tool_faults.report_diagnostics(store.cache_dir),
                **({'recovery_counts': recovery_diagnostic_summary(store.cache_dir, index)}
                   if dispatch_lifecycle.replacement_accounting(index) else {}),
                'protocol_attempts': evidence_views.protocol_attempts(store.cache_dir),
                'receipt_effects': evidence_views.receipt_effect_rows(prev_caches),
                'source_support': [dict(node=c['node'], visit=c['visit'], revision=n, **r['machine']['source_support'])
                                   for c in prev_caches for n, r in enumerate(_evidence_records(c))
                                   if r['machine'].get('source_support')],
                'anomaly_groups': evidence_views.anomaly_view(index['anomalies_summary']),
                'artifact_observations': [dict(node=c['node'], visit=c['visit'], revision=n,
                                              declared=r['payload']['evidence']['artifacts'], observed=r['machine'].get('artifacts') or [])
                                          for c in prev_caches for n, r in enumerate(_evidence_records(c))
                                          if r['payload']['evidence']['artifacts'] or r['machine'].get('artifacts')],
                'scope_note': 'Accepted cache records only; not all Provider events or unreported side effects. Empty does not prove none occurred.',
            }
            if entry['name'] in (*ACCOUNTING_NODES, *ANSWER_NODES):
                for row, cached in zip(ia['node_summaries'], main_caches, strict=True):
                    payload = _latest_payload(cached)
                    # alpha.42 E3: no user_messages / steps copies in the terminal reply (they were the largest part and pushed the
                    # reply past the Provider's tool-output cap); the model reuses them from context or reads them via input_refs
                    row.update(user_messages_chars=[len(str(m)) for m in (payload.get('user_messages') or [])],
                               steps_done=len(payload['steps'].get('done') or []), output_is_preview=True,
                               degraded_reason=payload.get('degraded_reason'))
                ia['final_context']['materials_note'] = ('node_summaries carry each main node\'s complete user_summary; user_messages are not '
                                                        'copied here - reuse them from context or read them via input_authority.input_refs '
                                                        '(next_node.py --read-input-ref <ref> --input-field user_messages).')
                ia['final_context']['execution_scope'] = {
                    'program': copy.deepcopy(index['program']),
                    'main_occurrences': [dict(node=r['node'], visit=r['visit'], status=r['status']) for r in ia['node_summaries']],
                    'private_steps': [dict(node=c['node'], parent=c.get('parent'), visit=c['visit'], status=_latest_payload(c)['status'])
                                      for c in prev_caches if c['kind'] == 'sub' and c not in main_caches],
                    'dispatch': copy.deepcopy(_dispatch_group(index)),
                    'report_commit_status': 'COMMITTED' if any(c['name'] in REPORT_NODES for c in index['completed']) else 'PENDING',
                    'public_delivery_status': 'UNOBSERVED',
                    'verification_boundary': 'Accepted commits and file evidence, not proof of semantic correctness. Final delivery is not observed yet; physical Provider calls remain unknown.',
                }
                ia['final_context']['human_decisions'] = [   # review of docs/05SoulRun 87, round 2 (N2): with any refusal
                    dict({k: rec[k] for k in ('question_id','node','visit','question','answer_text','chosen_intent','answered_at',
                                              'replacement_refused') if k in rec},
                         **_unused_replacement(store, index, rec),   # round 3 (D2): or a choice whose replacement never ran
                         **_moved_on(store, index, rec))   # docs/05SoulRun 88 (K1): or a recheck that moved on to another stop
                    for rec in (store.read_json(store.gate_path(h['question_id'])) for h in index['gate']['history']
                                if h.get('resolution_kind') in ('chosen', 'free_text'))]
            ia = dict(execution_facts=evidence_views.execution_facts(ia['final_context'], store.cache_dir,
                      program.dir if program else None, nodes=_node_facts(store, index),   # alpha.79 (doc 163): states and status floor up front
                      snapshot=dict(consumer=dict(index['current']), index_updated_at=index.get('updated_at'),
                                    basis='accepted_records_and_archived_replies_available_before_this_submission')), **ia)
        reply["input_authority"] = ia
        reply["gate"] = {"state": "CLEAR", "required": False, "source": "router_candidates" if entry["name"] == NODE_MATCH else "none",
                         "kind": "choice" if entry["name"] == NODE_MATCH else None, "prompt_text": None, "public_prompt": None, "advisory": False}
        action = steps[0]["text"]
    else:
        view = _view_for(program, entry)
        reply["reserved"] = {"constraints": view["reserved"].get("constraints"), "on_error": view["reserved"].get("on_error"),
                             "retry_policy": view["reserved"].get("retry_policy"), "output_mapping": view["reserved"].get("output_mapping"),
                             "extra": view["extra"]}
        topo = view["topology"]
        frame = _frame_of(index, entry)
        planned = _planned_next(index, entry)
        reply["topology"] = {"next_candidates": topo["next_candidates"], "branches": topo["branches"],
                             "successors": _successor_candidates(view),
                             "planned_next": _bare(planned) if planned else None,
                             "default_successor": _default_successor(program, view, planned, in_frame=frame is not None),
                             "error_target": topo["error_target"], "is_end": topo["is_end"],
                             "end_nodes": _end_names(program, view)}
        if frame:  # a sub-graph node: where it executes and why (doc 05 §4.2)
            parent_entry = _catalog_entry(index, frame["parent"])
            parent_view = _view_for(program, parent_entry) if parent_entry else None
            reply["frame"] = {"parent": frame["parent"], "parent_visit": frame["parent_visit"], "depth": entry["depth"],
                              "doc": frame["doc"], "task": frame["task"], "ns": frame["ns"], "dir": frame["dir"], "order": frame["order"],
                              "parent_label": parent_view["label"] if parent_view else None,
                              "parent_steps": [{"key": s["key"], "text": s["text"]} for s in (parent_view["steps"] if parent_view else [])],
                              "siblings": _frame_siblings(store, index, frame["parent"], frame["parent_visit"]),
                              "note": "This node belongs to the sub-graph opened by the parent module node. Commit it under its qualified id; "
                                      "the parent's own steps are served after the sub-graph reaches its end node. siblings[] carries the "
                                      "bounded previews of committed sub nodes. For complete inputs use input_authority.input_refs or its read-only catalog, not arbitrary cache files."}
        module_result = _module_result(store, index, entry, visit)
        if module_result:  # the module node itself, after its sub-graph closed
            reply["module"] = module_result
            delegated = _module_delegation_steps(program, entry, view)
            for s in steps:
                s["satisfied_by_module"] = s['key'] in delegated
            reply["module"]["note"] = ("The sub-graph already ran and is recorded in the manifest; steps marked satisfied_by_module are "
                                       "satisfied by it (list them in steps.done, do not redo the work). Do the remaining steps on last_node.output.")
        first_assert = steps[0]["assert"] if steps and steps[0]["assert"] else None
        reply["input_authority"] = {
            "prev_node_summary": prev_summary, "user_message": run_input.get("user_message"),
            "assert": {"predecessors_committed": True, "primary_predecessor": topo["primary_predecessor"],
                       "declared_predecessors": first_assert["predecessors"] if first_assert else [], "graph_predecessors": topo["predecessors"]},
            "required_fields": _required_fields_status(first_assert["required"] if first_assert else [], prev_caches, index["context"], _run_inputs(run_input)),
            "context": index["context"], "gate_answer": gate_answer,
        }
        if frame:
            from . import module_inputs
            module_inputs.attach(program,index,frame,reply)
        gs = _gate_summary(view["gate_sources"])
        reply["gate"] = {"state": "CLEAR", "required": gs["required"], "source": gs["source"], "kind": gs["kind"],
                         "prompt_text": gs["prompt_text"], "public_prompt": None, "advisory": gs["advisory"]}
        action = steps[0]["text"] if steps else "(no steps)"
    from . import tool_faults
    reentry_receipt = tool_faults.human_reentry_receipt(store.cache_dir, index)
    if reentry_receipt:
        reply['input_authority']['machine_recovery_answer'] = reentry_receipt
    refs = _input_refs(store, index, prev_caches)
    reply["input_authority"]["input_refs"] = refs[-8:]
    if entry["name"] in ANSWER_NODES:   # alpha.69 (doc 147): what the answer must / may reference, with paste-ready report_parts items
        candidates = _report_candidates(store, index, program)
        candidates["rule"] = ("required items MUST be in semantics.report_parts as listed; optional items by REFERENCE FIRST; "
                              "a ref here is the short id <node>@<visit>, valid even when the node is not among the listed input_refs")
        reply["input_authority"]["report_candidates"] = candidates
        sizes = {(c["node"], c["visit"]): _latest_payload(c) for c in prev_caches}
        for ref in reply["input_authority"]["input_refs"]:
            p = sizes.get((ref["node"], ref["visit"])) or {}
            ref["report_chars"] = {"user_summary": len(p.get("user_summary") or ""),
                                   "user_messages": [len(m) for m in (p.get("user_messages") or []) if isinstance(m, str)]}
    reply["input_authority"]["input_catalog"] = {
        "total": len(refs), "preview_limit": 8, "has_more": len(refs) > 8,
        "read": "next_node.py --cache-dir <same-cache> --read-input-ref <ref> [--input-field output|vars|user_summary|user_messages|source_support] [--input-path a.b[0]] [--offset N] [--limit N]. source_support: effective_counts=unique scoped claims; ambiguous excluded; legacy counts=ID-label observations. Missing is not zero.",
        "list": "next_node.py --cache-dir <same-cache> --list-inputs [--offset N] [--limit N]",
        "rule": "References identify complete committed inputs, previews do not. Read needed truncated inputs; agent callers retain --agent-ticket. Read/list never serves or commits a node."}
    if kind in ('business', 'sub'):
        reply['input_authority']['program_contracts'] = {
            'items': _program_contract_items(store, index, program, entry),
            'read': 'next_node.py --cache-dir <same-cache> --read-program-contract <ref> [--offset N] [--limit N]',
            'rule': 'Apply the entry-program and current-module output/shared rules with the current steps. A directory is not full content. '
                    'Read missing complete rules once per unchanged content in your context; do not re-read already available complete rules. '
                    'No implicit override on conflict: a material authority doubt uses HSAW. Reads retain --agent-ticket for dispatched callers. '
                    'Partial JSON pages must be reassembled in order; only complete=true gives the whole value.'}
    topo_r = reply.get("topology") or {}
    gate_r = reply.get("gate") or {}
    node_facts: dict = {}   # alpha.100 (doc 241 D7): the values the rule sections refer to
    reply["payload_skeleton"], reply["payload_rules"] = _payload_skeleton(
        entry["name"], steps, gate_required=bool(gate_r.get("required")), gate_advisory=bool(gate_r.get("advisory")),
        successors=topo_r.get("successors") or [], default_successor=topo_r.get("default_successor"),
        gate_answered=gate_answer if gate_answer else None, host_fences=(index.get("host") or {}).get("host_fences"), sub_agent=sub_agent,
        facts=node_facts, write_target=index.get('target_aiap_dir'))
    reply["node_facts"] = node_facts
    if entry['name'] in (*ACCOUNTING_NODES, *ANSWER_NODES):
        node_facts['independent_budget'] = dispatch_budget.summary(index)
        from . import dispatch_accounting
        accounting = dispatch_accounting.snapshot(store, index)
        if accounting is not None:
            reply['input_authority']['execution_facts']['dispatch_accounting'] = accounting
        from . import blind_review
        reply['input_authority']['execution_facts']['review_candidate_bindings'] = blind_review.latest_results(store, _report_records(store, index, review_only=True))
    conditions = _conditional_records(store, index)
    if conditions:
        reply['input_authority']['human_instructions'] = conditional_reply.for_node(conditions, _conditional_node_aliases(program, index, entry['name']))
        if reply['input_authority']['human_instructions']:
            reply['payload_skeleton']['human_compliance'] = [dict(question_id=r['question_id'], instruction_id=r['instruction']['id'],
                status=None, rationale='', evidence_refs=[]) for r in reply['input_authority']['human_instructions']]
        reply['conditional_reply'] = {'state': 'INTERPRETED', 'rule': conditional_reply.RULE,
                                      'verification_scope': conditional_reply.SCOPE}
        if entry['name'] in (*ACCOUNTING_NODES, *ANSWER_NODES):
            reply['input_authority']['human_conditions'] = conditions
            reply['input_authority']['human_compliance_records'] = _conditional_compliance_records(prev_caches)
        reply['payload_rules'].append(_contracts.text('conditional-reply.execution'))
    if entry["name"] not in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY):   # alpha.90 (doc 202 B): the item shape beside the rule that names it
        reply["hsaw_item_example"] = _contracts.example("hsaw.doubt_gate")   # alpha.107 (doc 269 T4): a critical item with its gate
        reply["hsaw_taxonomy"] = hsaw_gate.taxonomy()   # alpha.97 (doc 232 C)
    if entry["name"] in ACCOUNTING_NODES:   # alpha.83 (doc 174 A): the accounting starts with every main node the run committed - all turns
        main_nodes = _main_nodes_committed(index)
        if main_nodes:
            reply["payload_skeleton"]["semantics"]["per_node"] = [{"node": n, "material_action": "", "result": ""} for n in main_nodes]
    if index.get("cancelled") and entry["name"] in (*ACCOUNTING_NODES, *ANSWER_NODES):   # alpha.88 (doc 196 F4'): the refusal closes into the report
        reply["payload_rules"].append(_cancelled_rule(index["cancelled"], report=entry["name"] in ACCOUNTING_NODES))
        node_facts["cancelled"] = dict(zip(("where", "dropped"), _cancel_where(index["cancelled"])))   # alpha.100 (doc 241 D7)
        if entry["name"] in ACCOUNTING_NODES:
            reply["payload_skeleton"]["semantics"]["nodes_skipped"] = list(index["cancelled"].get("dropped_nodes") or [])
            reply["payload_skeleton"]["semantics"]["functional_status"] = "PARTIAL"
    if entry["name"] in ANSWER_NODES:   # alpha.80 (doc 168): the required references start in the skeleton - the rules say "start from
        # payload_skeleton, keep every key"; 4 of 22 production runs sent a first final without report_parts (the guard repaired them)
        required_parts = [copy.deepcopy(c["report_part"]) for c in reply["input_authority"]["report_candidates"]["required"]]
        if required_parts:
            reply["payload_skeleton"]["semantics"]["report_parts"] = required_parts
    schema_out = _output_schema_for(_view_for(program, entry), run_input)   # alpha.59 (doc 128 §6)
    if schema_out:
        reply["payload_schema"] = {"output": schema_out}
        reply["payload_rules"].append(OUTPUT_SCHEMA_RULE)
    if kind in ('business', 'sub') and _source_template_needed(program, entry, steps, schema_out, prev_caches):
        reply['source_input_template'] = source_support.input_template()
        reply['source_support_candidates'] = _source_support_candidates(store)   # alpha.97 (doc 232 A)
        if source_support.RULE not in reply['payload_rules']:
            reply['payload_rules'].append(source_support.RULE)
    if kind in ('business', 'sub'):
        reply['delivery_obligations'] = delivery_obligations.obligations(_view_for(program, entry))
        reply['user_message_hints'] = delivery_obligations.user_message_hints(_view_for(program, entry), reply['delivery_obligations'])   # alpha.93
        reply['user_message_shape'] = delivery_obligations.UM_SHAPE   # alpha.95 (doc 223): the item shape at the head, inside the CLI preview of a long reply
        if any(reply['delivery_obligations'].values()):
            reply['payload_rules'].insert(-2, delivery_obligations.RULE)
        from . import module_order
        module_order.attach(store, index, program, entry, visit, reply)
        if (reply.get('module_execution') or {}).get('phase') == 'PRE_WORK' and reply['steps']:
            action = reply['steps'][0]['text']
        if frame:
            module_order.attach_parent(store, index, program, frame, reply)
    if resume_kind in ("same_occurrence", "re_serve") and entry["name"] not in ANSWER_NODES:   # alpha.45: `Engine.final-answer` has no PLAN block to present
        reply["payload_rules"].append(_contracts.text("resume.presentation"))
    if resume_kind in ("same_occurrence", "re_serve"):
        reply["payload_rules"].append(_contracts.text("resume.continuation_evidence"))   # alpha.42 E4: resume only
    if entry["name"] in ANSWER_NODES:   # alpha.45: the answer node has no PLAN block - the answer itself is its public output
        reply["public_plan"], reply["public_plan_ref"] = None, None
        return reply
    executor = render.executor_line(mode, dispatch)
    if kind == "sub":
        reply["public_plan"] = render.sub_plan_line(position, entry["name"], action, _resume_label(reply), executor=executor)
    else:
        notice = None
        if entry['name'] == NODE_SETUP and _no_agent_normal(index):
            notice = next(a['text'] for a in index['anomalies_summary'] if a['code'] == 'HOST_NO_AGENT_TOOL')
        reply["public_plan"] = render.plan_block(position, entry["name"], kind, mode["effective"], action, _resume_label(reply), executor=executor,
                                                 user_language=index.get("user_language"), notice=notice)
    plan_name = f"plan.{position['ordinal']:02d}.{_safe_name(entry['name'])}.v{visit}.txt"   # alpha.84: the file keeps the catalog ordinal
    if write_plan:
        plan_name = store.write_public_snapshot(plan_name, reply["public_plan"]).name
    reply["public_plan_ref"] = _ref(store, plan_name)   # alpha.27 R1: the model presents this line, the host expands it
    from . import blind_review
    from . import independent_inputs
    return independent_inputs.filter_reply(store, index, blind_review.filter_reply(store, index, reply))


# ---------------------------------------------------------------------------
# recovery (R-37)
# ---------------------------------------------------------------------------

def _recover_orphan_cache(store: RunStore, index: dict, run_input: dict, program) -> bool:
    """A node cache exists for the current node but its index transition never landed."""
    if index["run_state"] != "RUNNING":
        return False
    name, visit = index["current"]["name"], index["current"]["visit"]
    entry = _catalog_entry(index, name)
    if not entry:
        return False
    if dispatch_lifecycle.replacement_accounting(index):
        known_gates = {h['question_id'] for h in index['gate']['history']}
        if any(p.stem.removeprefix('_gate.') not in known_gates for p in store.cache_dir.glob('_gate.q*.json')):
            from . import partial_commit
            return partial_commit.recover_unrecorded(store, index)
    path = _cache_path_for(store, index, entry, visit)
    if not store.exists_path(path):
        return False
    cache = store.read_json(path)
    last = cache["continuations"][-1] if cache.get("continuations") else cache
    state = index['nodes'].get(_node_key(name, visit)) or {}
    if state.get('module_prefix') and last['machine'].get('module_prefix') == state['module_prefix'] \
            and state.get('cache_sha256') == sha256_bytes(store.read_bytes(path)):
        return False
    paused = last["machine"].get("paused_gate")
    if paused:
        known = any(h["question_id"] == paused for h in index["gate"]["history"])
        if known:
            return False  # normal same-occurrence flow (gate presented, maybe answered)
        if dispatch_lifecycle.replacement_accounting(index):
            from . import partial_commit
            return partial_commit.recover_unrecorded(store, index)
        rec = store.read_json(store.gate_path(paused))
        if last.get("gate_answer"):
            _mark_gate_consumed(store, last["gate_answer"]["question_id"])
        _apply_pause_to_index(index, entry, visit, rec, path)
        index["anomalies_summary"].append({"node": name, "code": "RECOVERED_ORPHAN_PAUSE", "text": f"gate {paused} re-applied from cache"})
        return True
    if any(c["name"] == name and c["visit"] == visit for c in index["completed"]):
        return False
    if dispatch_lifecycle.replacement_accounting(index):
        from . import partial_commit
        return partial_commit.recover_unrecorded(store, index)
    payload = last["payload"]
    try:
        pre = _prevalidate_advance(store, index, run_input, program, entry, payload)
    except EngineError as exc:
        _terminate(index, kind="fatal", by="engine", reason=f"orphan cache could not be re-applied: {exc.code} {exc.message}")
        return True
    _apply_commit_to_index(store, index, run_input, program, entry, visit, payload, cache, path, pre, recovered=True)
    return True


# ---------------------------------------------------------------------------
# commit (node-commit)
# ---------------------------------------------------------------------------

def _submission_repair_fields(node: str, errors: list[dict]) -> list[dict]:
    """Shape examples from the existing skeleton, never inferred business or gate decisions."""
    allowed = {'node', 'output', 'user_summary', 'user_messages', 'user_message', 'steps', 'evidence', 'anomalies', 'explain'}
    skeleton, _ = _payload_skeleton(node, [])
    result, seen = [], set()
    for error in errors:
        field, code = error.get('field'), error.get('code')
        if field in seen:
            continue
        if code == 'USER_MESSAGE_REQUIRED' and field == 'user_messages':
            example = ['<original user-facing text, verbatim>']
        elif code == 'SCHEMA_INVALID' and field in allowed and field in skeleton:
            example = copy.deepcopy(skeleton[field])
        elif code == 'SCHEMA_INVALID' and isinstance(field, str) and re.fullmatch(r'anomalies\[\d+\]', field):
            example = '<observed failure and recovery>'
        elif code == 'SCHEMA_INVALID' and field == 'evidence.artifacts':
            example = [dict(path='<existing absolute path>', kind='file')]
        elif code == 'SCHEMA_INVALID' and isinstance(field, str) and re.fullmatch(r'evidence\.artifacts\[\d+\]', field):
            example = dict(path='<existing absolute path>', kind='file')
        else:
            continue
        result.append(dict(field=field, example=example, example_only=True))
        seen.add(field)
    return result


def commit(cache_dir: str | Path, node_name: str, payload_text: str, *, agent_ticket: str | None = None, next_plan: bool = False) -> dict:
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        # Problem 85 (docs/05SoulRun 90 §2, ledger decisions 181 and 183): as in _serve; any mismatch is left to guard_submission.
        dispatch_budget.reinstall(store, index)
        run_input = _read_run_input(store)
        # Record 90 round 4 (B1): a node-commit with an agent ticket comes from a sub-agent (the old agent's, say), whose
        # reply never reaches the human: it is served the stop plain and writes no menu, so the stop is not marked served
        # to the main executor (a stop whose menu.<qid>.* file exists has been) and its first serve stays for the main
        # executor's next-node or node-commit (dispatch_budget.served).
        publish = not agent_ticket
        integrity_gate = program_guard.record(store, index)
        if integrity_gate:
            program_guard.pending_payload(store, payload_text, integrity_gate)
            return program_guard.reply(store, index, integrity_gate, publish=publish)
        blocked_dispatch = dispatch_budget.record(store, index)
        from . import dispatch_identity
        fenced = dispatch_identity.fenced_ticket(index, agent_ticket)
        if blocked_dispatch and fenced is None:
            ref = program_guard.pending_payload(store, payload_text, directory='_dispatch_pending')
            shown = (dispatch_budget.served(store, index, blocked_dispatch) if publish else
                     dispatch_budget.reply(store, index, blocked_dispatch, publish=False))
            return dict(shown, pending_payload_refs=[ref])
        kept = None
        try:
            if fenced is not None:
                raise _ticket_error(index, node_name, agent_ticket, fenced)
            program = _load_routed_program(run_input) if index['run_state'] not in TERMINAL_STATES else None
            if program and index['run_state'] == 'RUNNING':
                reason = dispatch_budget.preflight(index, program, _catalog_entry(index, index['current']['name']), store=store)
                if reason in ('ORIGINAL_EXECUTOR_RESUME_UNAVAILABLE', 'DISPATCH_LIVENESS_UNKNOWN'):
                    _, current_dispatch = _self_dispatch(index, _catalog_entry(index, index['current']['name']), index['current']['visit'])
                    if dispatch_identity.authority(store, index, current_dispatch):
                        reason = None
                    elif current_dispatch and current_dispatch.get('scope_root'):
                        kept = program_guard.pending_payload(store, payload_text, directory='_dispatch_pending')
                        return dict(dispatch_identity.open_gate(store, index, publish=publish), pending_payload_refs=[kept])
                if reason:
                    kept = program_guard.pending_payload(store, payload_text, directory='_dispatch_pending')
                    if reason == 'DISPATCH_LIVENESS_UNKNOWN' and dispatch_lifecycle.return_query_due(store, index,
                            _self_dispatch(index, _catalog_entry(index, index['current']['name']), index['current']['visit'])[1]):
                        raise _return_query_pending()
                    return dict(dispatch_budget.pause(store, index, reason, publish=publish), pending_payload_refs=[kept])
            result = _commit_locked(store, index, run_input, program, node_name, payload_text, agent_ticket)
            from . import gate_delivery
            gate_delivery.accepted(store,result)
        except EngineError as exc:
            if exc.code == 'PROGRAM_DRIFT_DETECTED':
                # docs/05SoulRun 90 round 5 (ledger decision 185): with an agent ticket not published, as above
                return program_guard.pause(store, index, exc, payload_text, publish=publish)
            help_text = _HELP.get(exc.code, "See schemas/commit.v1.json and the next-node reply.")
            help_text += (' Do not repeat completed business writes to repair a submission. Reuse the existing artifact; '
                          'update the same file only when its declared operation allows it. Never overwrite append-only history or audit evidence.')
            errors = [exc.as_dict()] + [e for e in exc.errors if (e.get("code"), e.get("field")) != (exc.code, exc.field)]
            if any(re.fullmatch(r"evidence\.sources\[\d+\]\.retrieved_at", str(e.get("field"))) for e in errors):
                help_text += " evidence.sources[].retrieved_at accepts an observed ISO 8601 string with zone or null, not an @ref object. " \
                             "Use the actual observed value from the existing capture, or null if unobserved; never substitute the current time."
            repair_fields = _submission_repair_fields(node_name, errors)
            if repair_fields:
                help_text += (' repair_fields are shape examples only, not defaults or a repaired payload. Fix only named fields; '
                              'retain all actual evidence and original text. Empty examples do not authorize deleting content. '
                              'If a host message was not captured, resubmit the same original user-facing text inline, not a summary.')
            return {"status": "REJECTED", "node": node_name, "run_state": index["run_state"],
                    "errors": errors,
                    **({'repair_fields': repair_fields} if repair_fields else {}),
                    **({'pending_payload_refs': [kept or program_guard.pending_payload(store, payload_text, directory='_dispatch_pending')]}
                       if kept or (agent_ticket and _ticket_known(index, agent_ticket)) else {}),
                    **({'source_input_template': source_support.input_template()} if exc.code == 'SOURCE_SUPPORT_INVALID' else {}),
                    "help": help_text,
                    "sealed_capture_diagnostics": _sealed_diagnostics(store, index, node_name),
                    **_refusal_sections(index, node_name, [exc.code] + [e.get("code") for e in exc.errors],   # alpha.100 (doc 241 S4)
                                        _HELP.get(exc.code, ""), bool(agent_ticket))}
    return _with_next_plan(cache_dir, result, agent_ticket) if next_plan else result   # alpha.28 B3 (node-commit CLI opt-in)


def _sealed_diagnostics(store, index, node):
    from . import sealed_diagnostics
    caches = [c for c in _prev_business_caches(store, index) if c.get('node') == node]
    entry = _catalog_entry(index, (index.get('current') or {}).get('name')) if index.get('catalog') else None
    _, dispatch = _self_dispatch(index, entry, index['current']['visit']) if entry else (None, None)
    if (dispatch or {}).get('review_binding'):
        root = dispatch.get('scope_root')
        caches = [c for c in caches if root and (((c.get('continuations') or [c])[-1].get('machine', {}).get('dispatch') or {}).get('scope_root')) == root]
    return sealed_diagnostics.summary(store, caches)


def _with_next_plan(cache_dir: str | Path, result: dict, agent_ticket: str | None) -> dict:
    """alpha.28 B3 (04 series doc 57 §4): a COMMITTED result that names a next node carries that node's next-node reply
    as `next_plan` (served exactly as next-node would serve it, so a later next-node call is idempotent): one tool round
    trip less per node. Opt-in of the node-commit CLI (the Python API keeps the two-call flow for hosts and tests).
    Dispatched callers (agent tickets), dispatching commits and non-running states are left alone;
    any failure to serve leaves the commit result as it is (the model then calls next-node as before)."""
    scope_continues = bool(result.get('dispatch') and result['dispatch'].get('scope_root') and not result['dispatch'].get('closed'))
    if (agent_ticket and not scope_continues) or result.get("status") != "COMMITTED" or not result.get("next") or (result.get("dispatch") and not scope_continues):
        return result
    from . import write_observation
    with write_observation.suboperation('next_node_after_commit',cache_dir):
        write_observation.bind_request(agent_ticket=agent_ticket, abandon=None, reason=None)
        return _next_after_commit(cache_dir,result,agent_ticket)


def _next_after_commit(cache_dir,result,agent_ticket):
    try:
        served = serve(cache_dir, agent_ticket=agent_ticket, session="continue")
    except Exception as exc:  # the commit stands; a partially served next node is not silently replayed
        from . import tool_faults
        failure = (dict(status='ERROR',errors=[exc.as_dict()],
                        **tool_faults.capture(cache_dir,'next_node_after_commit',exc))
                   if isinstance(exc,EngineError) else tool_faults.unexpected(cache_dir, 'next_node_after_commit', exc))
        result['next_plan_error'] = failure['errors'][0]
        if failure.get('public_block_ref'):
            result['fault_public_block_ref'] = failure['public_block_ref']
        result.update({key: value for key, value in failure.items()
                       if key not in ('status', 'errors', 'public_block', 'public_block_ref')})
        result['next_plan_error_action'] = ('Emit the accepted public_block_ref first, then fault_public_block_ref if present. '
                                            'End the turn for the machine gate; no next-node call or business replay until the actual human answer.')
        return result
    if (served.get("run") or {}).get("state") != "RUNNING" or not served.get("node"):
        return result
    result["next_plan"] = served
    if served.get("contracts_attached"):   # alpha.100 (doc 241 S5): the newly sent sections, named at the top of the commit reply
        result["next_contracts_attached"] = served["contracts_attached"]
    if served.get("user_message_hints"):   # alpha.93 (doc 218): the next node's user-message hints inside the first kilobytes of the reply
        result["next_user_message"] = served["user_message_hints"]
    result["public_plan_next"] = served.get("public_plan")
    result["public_plan_next_ref"] = served.get("public_plan_ref")
    return result


def _repair_invalid_escapes(text: str) -> tuple[str, int]:
    """alpha.58 (doc 123 §6 #1): strict JSON gives `\\` + a non-escape character no meaning, so doubling that backslash cannot change a
    valid payload; it turns the model's Markdown escapes (\\_ \\* \\( ...) into the characters it meant. Returns (text, repairs)."""
    return _BAD_ESCAPE_RE.subn(r"\\\\", text)


def _normalize_intent(value: str, fallback: str) -> str:
    s = _INTENT_BAD_RE.sub("_", value.strip().lower()).strip("_")
    s = re.sub(r"_+", "_", s)
    if not s:
        return fallback
    return s if s[0].isalpha() else "opt_" + s


def _normalize_gate_intents(gate: dict, notes: list | None) -> None:
    """alpha.58 (doc 123 §6 #2; production cache/88, 90): option intents and the recommendation are normalised to ^[a-z][a-z0-9_]*$
    consistently instead of rejecting the whole gate as SCHEMA_INVALID; uniqueness is still checked by _check_gate_shape."""
    mapping, changed = {}, []
    options = gate.get("options")
    if isinstance(options, list):
        for i, o in enumerate(options):
            if isinstance(o, dict) and isinstance(o.get("intent"), str):
                new = _normalize_intent(o["intent"], f"option_{i + 1}")
                mapping[o["intent"]] = new
                if new != o["intent"]:
                    changed.append(f"options[{i}].intent {o['intent']!r} -> {new!r}")
                    o["intent"] = new
    rec = gate.get("recommendation")
    if isinstance(rec, str):
        new = mapping.get(rec) or _normalize_intent(rec, rec)
        if new != rec:
            changed.append(f"recommendation {rec!r} -> {new!r}")
            gate["recommendation"] = new
    if changed and notes is not None:
        notes.append({"code": "GATE_INTENT_NORMALIZED", "text": "; ".join(changed) + " (alpha.58: intents are ^[a-z][a-z0-9_]*$; write them so)"})


_RESTORED_KEYS = (("degraded_reason", None), ("user_messages", []), ("anomalies", []))
_NULL_OPTIONAL_SOURCE_KEYS = ("title", "label", "tool", "source_id")
_NULL_OPTIONAL_CALL_KEYS = ("step", "sys_call")


def _normalize_shape(payload: dict, notes: list | None) -> None:
    """alpha.97 (04 series doc 232 B): omissions that carry no meaning are repaired and recorded, never refused. A skeleton key the payload
    dropped (degraded_reason / user_messages / anomalies; production caches 4 and 13) gets its skeleton default; an optional source or
    tool-call field written as null is removed, and so is a null url beside a path (cache 9). What follows still checks everything: DEGRADED
    without a reason, a declared User Message without messages, a source with neither url nor path."""
    restored = [key for key, _ in _RESTORED_KEYS if key not in payload]
    for key, default in _RESTORED_KEYS:
        payload.setdefault(key, copy.deepcopy(default))
    dropped = []
    evidence = payload.get("evidence")
    if isinstance(evidence, dict):
        for i, src in enumerate(evidence["sources"] if isinstance(evidence.get("sources"), list) else []):
            if isinstance(src, dict):
                for key in _NULL_OPTIONAL_SOURCE_KEYS + (("url",) if src.get("path") else ()):
                    if key in src and src[key] is None:
                        del src[key]
                        dropped.append(f"evidence.sources[{i}].{key}")
        for i, call in enumerate(evidence["tool_calls"] if isinstance(evidence.get("tool_calls"), list) else []):
            if isinstance(call, dict):
                for key in _NULL_OPTIONAL_CALL_KEYS:
                    if key in call and call[key] is None:
                        del call[key]
                        dropped.append(f"evidence.tool_calls[{i}].{key}")
    if notes is not None and restored:
        notes.append({"code": "SKELETON_KEY_RESTORED", "text": f"{restored} missing: set to the skeleton default (alpha.97) - start from "
                                                               "payload_skeleton and keep every key"})
    if notes is not None and dropped:
        notes.append({"code": "OPTIONAL_NULL_DROPPED", "text": f"{dropped}: null removed (alpha.97) - omit an inapplicable optional field"})


def _hsaw_critical_declared(items) -> bool:
    """alpha.106 (doc 265 E4): an hsaw item whose recorded level will be critical - declared critical, a FREEZE_NOW / HARD_FAIL disposition,
    or facts that imply critical (hsaw_gate.implied_level, the rule align_items applies). Conservative: an item it cannot judge counts."""
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            if item.get("severity") == "critical" or item.get("disposition") in ("FREEZE_NOW", "HARD_FAIL") or hsaw_gate.implied_level(item) == "critical":
                return True
        except Exception:  # noqa: BLE001 - malformed facts: no default, the alpha.105 refusal stands
            return True
    return False


def _decode_payload_json(payload_text: str, notes: list | None = None):
    """Share JSON syntax decoding with request identity; no schema or authority defaults."""
    try:
        payload = strict_loads(payload_text)
    except ValueError as exc:
        repaired, count = _repair_invalid_escapes(payload_text)   # alpha.58 (doc 123 §6 #1; production cache/83, 88, 89, 90)
        payload = None
        if count:
            try:
                payload = strict_loads(repaired)
            except ValueError:
                payload = None
        if payload is None:
            raise
        if notes is not None:
            notes.append({"code": "JSON_ESCAPE_REPAIRED", "text": f"{count} invalid backslash escape(s) doubled before parsing (alpha.58): "
                                                                  "in JSON strings write Markdown escapes as plain characters"})
    return payload


def _parse_payload(payload_text: str, notes: list | None = None, defaults: list | None = None, *, raw_gate_intents: list | None = None,
                   na_reasons: list | None = None) -> dict:
    """defaults lists omitted terminal step placeholders; JSON identity precedes schema defaults."""
    try:
        payload = _decode_payload_json(payload_text, notes)
    except ValueError as exc:
        raise EngineError("JSON_INVALID", str(exc), field="$", expected="strict JSON object", example='{"schema_version": 1, ...}') from exc
    if not isinstance(payload, dict):
        raise EngineError("JSON_INVALID", "payload must be a JSON object", field="$", expected="object")
    from . import public_path_text
    public_path_text.validate(payload,notes)
    if isinstance(payload.get("gate"), dict):
        if raw_gate_intents is not None and isinstance(payload['gate'].get('options'), list):
            raw_gate_intents.extend(o.get('intent') if isinstance(o, dict) else None
                                    for o in payload['gate']['options'])
        _normalize_gate_intents(payload["gate"], notes)   # alpha.58 (doc 123 §6 #2)
    _normalize_shape(payload, notes)   # alpha.97 (doc 232 B)
    hsaw_gate.normalize_shape(payload, notes)   # alpha.99 (doc 239 H1 / H2 / H4)
    if payload.get("node") in ANSWER_NODES:   # alpha.99 (doc 240; isolated cache 38): the answer node's L1 fields are machine placeholders (alpha.45)
        filled = [k for k, v in (("output", "final_answer"), ("user_summary", FINAL_NOTE), ("user_messages", []),
                                 ("steps", {"done": [], "remaining": [], "not_applicable": []})) if k not in payload and payload.setdefault(k, v) is not None]
        if filled and notes is not None:
            notes.append({"code": "STEPS_FILLED_AT_ANSWER", "text": f"the answer commit carried no {filled}; placeholders set, the served steps recorded as done (alpha.99)"})
    if "steps" not in payload and payload.get("status") == "PASS" and not isinstance(payload.get("gate"), dict) \
            and not _hsaw_critical_declared(payload.get("hsaw_items")):   # alpha.106 (doc 265 E4)
        payload["steps"] = {"done": [], "remaining": [], "not_applicable": []}   # placeholder: _commit_locked sets done = the served keys
        if defaults is not None:
            defaults.append("steps")
    sources_address = None
    ev = payload.get("evidence")
    if isinstance(ev, dict):   # alpha.58 B6 (doc 124 P2): one address in place of the source list is resolved, then validated like typed sources
        src = ev.get("sources")
        if isinstance(src, dict) and ADDRESS_REF_KEY in src:
            sources_address = src
        elif isinstance(src, list) and len(src) == 1 and isinstance(src[0], dict) and ADDRESS_REF_KEY in src[0]:
            sources_address = src[0]
        if sources_address is not None:
            ev["sources"] = []
    hits = schema_lite.machine_owned_hits(payload, commit_schema())
    if hits:
        raise EngineError("MACHINE_FIELD_REJECTED", f"machine-owned fields present: {hits}", field=hits[0], expected="absent")
    errors = repairs.repair_schema(payload, commit_schema(), schema_lite.validate, notes)   # alpha.99 (doc 239 P7): repaired and recorded first
    if errors:
        first = errors[0]
        head = first["field"].split(".")[0].split("[")[0]
        raise EngineError("SCHEMA_INVALID", first["message"], field=first["field"], expected=first["expected"],
                          example=_example_for(first["field"], head), errors=[dict(e, code="SCHEMA_INVALID") for e in errors[1:]])
    if sources_address is not None:
        payload["evidence"]["sources_address"] = sources_address
    # docs/05SoulRun 87 (runs 6 / 7: four {step, reason} entries reduced to names, the reasons only in dropped_fields): a not_applicable
    # entry is the step key or {step, reason}; the payload keeps the keys every check reads, the reasons go to machine.steps_not_applicable
    rows = payload["steps"]["not_applicable"] if isinstance(payload.get("steps"), dict) else []
    if any(isinstance(row, dict) for row in rows):
        if na_reasons is not None:
            na_reasons.extend({"step": row["step"], "reason": row["reason"]} for row in rows
                              if isinstance(row, dict) and str(row.get("reason") or "").strip())
        payload["steps"]["not_applicable"] = [row["step"] if isinstance(row, dict) else row for row in rows]
    return payload


# --- alpha.93 (doc 217 / 218): User Message - the executor declares, the engine checks ------------------------------------------
USER_MESSAGE_PROSE_MIN = 300   # has false while output carries this much prose: recorded (USER_MESSAGE_NONE_WITH_TEXT_OUTPUT)
_UM_QUOTES = (re.compile(r"'([^'\n]{2,})'"), re.compile("\u300c([^\u300d\n]{2,})\u300d"), re.compile("\u201c([^\u201d\n]{2,})\u201d"),
              re.compile(r'"([^"\n]{2,})"'))


def _norm_ws(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _program_texts(view) -> list:
    out = []

    def walk(value):
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    for step in (view or {}).get("steps") or []:
        walk(step.get("text"))
    walk((view or {}).get("reserved"))
    walk((view or {}).get("extra"))
    return out


def _program_literals(view) -> list:
    """Every quoted text of this node's program ('...', 「...」, “...”, "..."): the texts a literal user_message item may copy."""
    found = []
    for text in _program_texts(view):
        for rx in _UM_QUOTES:
            found.extend(m.group(1) for m in rx.finditer(text))
    return found


def _literal_pattern(literal: str):
    """A program text as a pattern: whitespace runs match whitespace runs, a {placeholder} matches the value filled in.
    docs/05SoulRun 87: the placeholders are found by _PLACEHOLDER_RE in the program text itself and only the parts between them are
    escaped - the rule the commit check uses - so {PASS|FAIL} or {max value} is a placeholder here too (escaping first hid them)."""
    body = ".+?".join(re.escape(part) for part in _PLACEHOLDER_RE.split(_norm_ws(literal)))
    body = body.replace("\\ ", r"\s+").replace(" ", r"\s+")   # re.escape writes a space as backslash-space
    return re.compile(body, re.S)


def _is_prose(text: str) -> bool:
    t = str(text or "").strip()
    if len(t) < 40 or t[:1] in "{[":
        return False
    return sum(1 for c in t if c.isalpha()) / len(t) >= 0.5


_PROSE_SKIPPED_KINDS = ("proc", "input")   # docs/05SoulRun 87: process output and upstream content are not this node's text for the user


def _output_prose_chars(output, user_message=None) -> int:
    """The longest natural-language text in output - inline, or behind an address (its @resolved chars, judged by the preview).
    docs/05SoulRun 87 (run 7: all 8 USER_MESSAGE_NONE_WITH_TEXT_OUTPUT were such values): a proc: or input: address - a captured
    output, content an upstream node already gave - and a string equal to this run's user message are passed over; work: files and
    inline fields still count."""
    best = 0
    words = _norm_ws(user_message) if isinstance(user_message, str) else ""

    def walk(value):
        nonlocal best
        if isinstance(value, str):
            if _is_prose(value) and not (words and _norm_ws(value) == words):
                best = max(best, len(value))
        elif isinstance(value, dict):
            resolved = value.get("@resolved")
            kind = resolved.get("kind") if isinstance(resolved, dict) else str(value.get(ADDRESS_REF_KEY) or "").split(":", 1)[0]
            if kind in _PROSE_SKIPPED_KINDS:
                return
            if isinstance(resolved, dict) and isinstance(resolved.get("chars"), int) and _is_prose(resolved.get("preview")):
                best = max(best, resolved["chars"])
            for k, v in value.items():
                if k != "@resolved":
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(output)
    return best


_MARKUP_PAIRS = (re.compile(r"`([^`\n]+)`"), re.compile(r"\*\*([^*\n]+?)\*\*"))
_CONTROL_ESCAPES = {"\n": "\\n", "\t": "\\t", "\r": "\\r", "\f": "\\f", "\b": "\\b"}


def _markup_free(text: str) -> str:
    """alpha.98 (04 series doc 236, B2 narrow): paired inline-code backticks and ** bold set aside - presentation, not characters the
    user reads. A single * or _ and every other mark stay."""
    for rx in _MARKUP_PAIRS:
        text = rx.sub(r"\1", text)
    return text


def _escape_hint(raw, joined: str) -> str:
    """alpha.98 (04 series doc 236; production cache 4, isolated 43 / 53): the JSON turned a Windows path's backslash sequence into a
    control character - the refusal says so."""
    raw = str(raw or "")
    if not any(ch in raw for ch in _CONTROL_ESCAPES):
        return ""
    restored = _norm_ws("".join(_CONTROL_ESCAPES.get(ch, ch) for ch in raw))
    if restored in joined or _markup_free(restored) in _markup_free(joined):
        return (" - the JSON turned a backslash sequence of a Windows path into a control character (\\n became a line break): write each "
                "backslash as \\\\ or use / (alpha.98)")
    return ""


LITERAL_REF_MIN = 8   # alpha.98: a quote shorter than this (a button word such as 「导出」) never stands for a step's program text


def _step_quotes(view, key) -> list:
    """alpha.98 (04 series doc 236 #5): the quoted program texts of one step, longest first, at least LITERAL_REF_MIN characters"""
    steps = [s for s in (view or {}).get("steps") or [] if s.get("key") == key]
    found = []
    for text in _program_texts({"steps": steps}):
        for rx in _UM_QUOTES:
            found.extend(m.group(1) for m in rx.finditer(text))
    return sorted((q for q in dict.fromkeys(found) if len(_norm_ws(q)) >= LITERAL_REF_MIN), key=len, reverse=True)


def _step_literals(view, key) -> list:
    """the quotes of a step a literal may stand for - never one that asks the user for a reply: that is a gate question, not a User
    Message (alpha.98 fix A, doc 236 §7; isolated cache 64 streamed ExportReport's question after its gate was answered)"""
    return [q for q in _step_quotes(view, key) if not delivery_obligations.is_request(q)]


def _find_literal(quotes, haystack: str):
    """alpha.98: the delivered text of the first program quote whose pattern (placeholders as wildcards) occurs in haystack; a placeholder
    at either end runs to the next whitespace, so the recorded text is the whole value, not one character of it."""
    for quote in quotes:
        body = _literal_pattern(quote).pattern
        if body.endswith(".+?"):
            body = body[:-3] + r"\S+"
        if body.startswith(".+?"):
            body = r"\S+" + body[3:]
        found = re.search(body, haystack, re.S)
        if found:
            return found.group(0)
    return None


_TRAILING_STOP = "。．.！!？?；;"
_PLACEHOLDER_RE = re.compile(r"\{[^{}]{1,40}\}")


def _restore_escapes(raw) -> str:
    """alpha.98 / alpha.99: a declared text whose Windows-path backslash sequences the JSON turned into control characters, written back"""
    return _norm_ws("".join(_CONTROL_ESCAPES.get(ch, ch) for ch in str(raw or "")))


def _na_with_program_text(view, rows) -> list:
    """alpha.106 (doc 265 E4): a not_applicable row that names a step and carries no (or a blank) text is archived with that step's program
    text - its quoted texts (at most three, each cut to 160 characters, joined by " / "), or its own text when it quotes nothing (whitespace
    normalised, the first 300 characters) - and text_by "engine". The payload stays as submitted; only machine.user_message carries it."""
    out = []
    for row in copy.deepcopy(list(rows)):
        if isinstance(row, dict) and row.get("step") and not str(row.get("text") or "").strip():
            quotes = _step_quotes(view, row["step"])[:3]
            if quotes:
                row["text"] = " / ".join(q[:160] for q in quotes)
            else:
                steps = [s for s in (view or {}).get("steps") or [] if s.get("key") == row["step"]]
                row["text"] = _norm_ws(" ".join(_program_texts({"steps": steps})))[:300]
            row["text_by"] = "engine"
        out.append(row)
    return out


def _check_user_message(payload: dict, view: dict, served: list, notes: list, tool_texts=(), partial_steps=(), user_message=None) -> dict:
    """alpha.93: the declaration is required on a completing business / sub commit; it must agree with user_messages, name the node's own
    steps, and every literal item must be a program text that appears verbatim in user_messages. Returns machine.user_message.
    alpha.99 (04 series doc 239 §3.1): what used to be refused is settled by the engine and recorded - a literal with one extra full stop
    (U1), a literal that is not a program text becomes content (U2), a text-less literal of a step that only asks or quotes nothing (U3),
    a Windows path broken by JSON escaping (U4), the step's program text found in the messages although the declared copy differs (U5),
    and a literal the executor did not deliver is delivered by the engine - the program's own text, placeholders as the executor filled
    them (U6). The has decision itself stays required (user r3), and a declaration whose content never arrived is still refused
    (USER_MESSAGE_REQUIRED): only the executor can write content, the engine delivers program texts only."""
    decl = payload.get("user_message")
    msgs = [m for m in payload.get("user_messages") or [] if isinstance(m, str) and m.strip()]
    if not isinstance(decl, dict) or decl.get("has") is None:
        raise EngineError("USER_MESSAGE_DECISION_MISSING", "declare user_message: has true (and deliver it in user_messages) or has false with none_reason",
                          field="user_message", expected="{has, items, not_applicable, none_reason}", example=copy.deepcopy(_EXAMPLES["user_message"]))
    keys = [s["key"] for s in served]
    for where in ("items", "not_applicable"):
        for i, it in enumerate(decl.get(where) or []):
            if where == "not_applicable" and "step" not in it:   # r2 (doc 219): the program's own text names the point as well as a step
                if not str(it.get("text") or "").strip():
                    raise EngineError("USER_MESSAGE_DECISION_MISSING", f"user_message.not_applicable[{i}] names neither a step nor the program's text",
                                      field=f"user_message.not_applicable[{i}]", expected="{step and / or text, reason}",
                                      example=copy.deepcopy(_EXAMPLES["user_message"]))
                continue
            if it.get("step") not in keys:
                raise EngineError("USER_MESSAGE_STEP_UNKNOWN", f"user_message.{where}[{i}].step {it.get('step')!r} is not a step of this node",
                                  field=f"user_message.{where}[{i}].step", expected=keys)
            if where == "items" and it.get("step") not in (payload.get("steps") or {}).get("done", []) and it.get('step') not in partial_steps:
                listed = next((b for b in ("remaining", "not_applicable") if it.get("step") in (payload.get("steps") or {}).get(b, [])), "no bucket")
                raise EngineError("USER_MESSAGE_STEP_NOT_DONE", f"user_message.items[{i}].step {it.get('step')!r} is in steps.{listed}, not steps.done: "
                                  "a text the user gets comes from a step this commit completed",
                                  field=f"user_message.items[{i}].step", expected=list((payload.get("steps") or {}).get("done", [])))
    if not decl["has"] and msgs:
        raise EngineError("USER_MESSAGE_DECISION_INCONSISTENT", "user_message.has is false but user_messages carries text",
                          field="user_message.has", expected=True)
    # r3 (user 2026-09-23 「声明必填，缺理由自动记 n/a」): the has decision stays mandatory; has false without a reason is recorded as n/a
    none_default = not decl["has"] and not str(decl.get("none_reason") or "").strip()
    verified = 0
    markup_ignored, referenced = [], []   # alpha.98 (doc 236): B2 and literals declared by reference
    corrected, dropped_items, delivered, relocated, repaired, not_delivered, punct = [], [], [], [], [], [], []
    items = decl.get("items") or []
    literals = [(i, it) for i, it in enumerate(items) if it.get("kind") == "literal"]
    if decl["has"] and not msgs and any(it.get("kind") != "literal" for it in items):   # content only the executor can write - nothing arrived
        raise EngineError("USER_MESSAGE_REQUIRED", "user_message.has is true but user_messages carries no text", field="user_messages",
                          expected="the texts this node's program gives the user - generated content in full, quoted texts verbatim")
    if literals:
        program_literals = _program_literals(view)
        tools = _norm_ws("\n".join(t for t in tool_texts if isinstance(t, str)))

        def joined_now() -> str:
            return _norm_ws("\n".join(m for m in payload.get("user_messages") or [] if isinstance(m, str) and m.strip()))

        def deliver(text, i, step):
            payload.setdefault("user_messages", [])
            payload["user_messages"] = [m for m in payload["user_messages"] if m != "@host"] + [text]
            delivered.append({"item": i, "step": step, "index": len(payload["user_messages"]) - 1, "chars": len(text)})

        for i, it in literals:
            joined = joined_now()
            text = _norm_ws(it.get("text"))
            if not text:   # alpha.98 (doc 236 #5): a literal item without text is declared by reference - the engine finds its step's program text
                quotes = _step_literals(view, it.get("step"))
                asks = [q for q in _step_quotes(view, it.get("step")) if q not in quotes]
                if not quotes and asks:   # alpha.98 fix A / alpha.99 U3: the step's quoted text is a question to the user - never a User Message
                    dropped_items.append({"item": i, "step": it.get("step"), "reason": "the step's quoted text asks the user (a gate question)"})
                    it["kind"] = "content"
                    it.setdefault("what", "(dropped: a gate question, not a User Message)")
                    continue
                if not quotes:   # alpha.99 U3: nothing to find - a description is content
                    corrected.append({"item": i, "step": it.get("step"), "reason": f"the step quotes no program text of {LITERAL_REF_MIN}+ characters"})
                    it["kind"] = "content"
                    continue
                found = _find_literal(quotes, joined)
                if found is None:
                    found = _find_literal(quotes, _markup_free(joined))
                    if found is not None:
                        markup_ignored.append(i)
                if found is None:   # alpha.99 U6: not delivered - the engine delivers the step's program text when it has no placeholder
                    static = [q for q in quotes if not _PLACEHOLDER_RE.search(q)]
                    if not static:
                        # docs/05SoulRun 87: text was delivered but is not this program text (its placeholders are wildcards, every
                        # other character must match) - the executor is not told it left a placeholder unfilled
                        reason = ("the delivered text does not match the step's program text (its {placeholders} match any value; every "
                                  "other character must be as the program writes it)" if joined else
                                  "the step's program text has placeholders the executor did not fill")
                        not_delivered.append({"item": i, "step": it.get("step"), "reason": reason})
                        continue
                    deliver(static[0], i, it.get("step"))
                    found = static[0]
                referenced.append({"item": i, "step": it.get("step"), "text": found[:500]})
                verified += 1
                continue
            if not any(_literal_pattern(lit).fullmatch(text) for lit in program_literals):
                stripped = text[:-1].rstrip() if text and text[-1] in _TRAILING_STOP else None
                if stripped and any(_literal_pattern(lit).fullmatch(stripped) for lit in program_literals):   # alpha.99 U1 (production cache 19)
                    punct.append({"item": i, "mark": text[-1]})
                    text = stripped
                else:   # alpha.99 U2 (production cache 19, isolated 59 / 60): not a program text - the executor's own text is content
                    source = "a text of this node's own tool output" if text and text in tools else "not a quoted program text of this node"
                    corrected.append({"item": i, "step": it.get("step"), "reason": source})
                    it["kind"] = "content"
                    it.setdefault("what", str(it.get("text"))[:200])
                    continue
            if text not in joined:
                if _markup_free(text) in _markup_free(joined):   # alpha.98 (doc 236, B2 narrow): only paired backticks / bold differ
                    markup_ignored.append(i)
                elif any(ch in str(it.get("text") or "") for ch in _CONTROL_ESCAPES) and (
                        _restore_escapes(it.get("text")) in joined or _markup_free(_restore_escapes(it.get("text"))) in _markup_free(joined)):
                    repaired.append(i)   # alpha.99 U4 (production 4, isolated 43 / 53): the JSON turned a path's backslash into a control character
                else:
                    found = _find_literal(_step_literals(view, it.get("step")), joined) or _find_literal(_step_literals(view, it.get("step")), _markup_free(joined))
                    if found is not None:   # alpha.99 U5: the program's text is in the messages; the declared copy differs
                        relocated.append({"item": i, "declared": str(it.get("text"))[:200], "found": found[:200]})
                    else:   # alpha.99 U6: the engine delivers the declared program text (a JSON-broken path written back first)
                        raw = str(it.get("text"))
                        deliver(_restore_escapes(raw) if any(ch in raw for ch in _CONTROL_ESCAPES) else raw.strip(), i, it.get("step"))
            verified += 1
    msgs = [m for m in payload.get("user_messages") or [] if isinstance(m, str) and m.strip()]
    record = {"has": bool(decl["has"]), "messages": len(msgs), "items": copy.deepcopy(items), "literals_verbatim": verified,
              "not_applicable": _na_with_program_text(view, decl.get("not_applicable") or []),   # alpha.106 (doc 265 E4): the engine records the text
              "none_reason": None if decl["has"] else ("n/a" if none_default else decl.get("none_reason"))}
    if partial_steps:
        record['partial_producer_steps'] = [it['step'] for it in items if it.get('step') in partial_steps]
    if referenced:   # alpha.98 (doc 236 #5): what the engine found for each literal declared by reference
        record["literals_referenced"] = referenced
    if markup_ignored:   # alpha.98 (doc 236, B2): recorded, the delivered text keeps its marks
        record["literals_markup_ignored"] = markup_ignored
        notes.append({"code": "USER_MESSAGE_MARKUP_IGNORED", "text": f"user_message.items{markup_ignored}: verbatim once paired backticks / "
                                                                    "** bold are set aside (alpha.98); the delivered text keeps them"})
    if punct:
        record["literals_punct_ignored"] = punct
        notes.append({"code": "USER_MESSAGE_LITERAL_PUNCT_IGNORED", "text": f"user_message.items{[p['item'] for p in punct]}: the program text plus one closing "
                                                                            f"mark {[p['mark'] for p in punct]}; accepted (alpha.99)"})
    if corrected:
        record["kind_corrected"] = corrected
        notes.append({"code": "USER_MESSAGE_KIND_CORRECTED", "text": "; ".join(f"user_message.items[{c['item']}] literal -> content ({c['reason']})" for c in corrected)
                                                                     + " (alpha.99: a literal is a text the program quotes; everything else is content)"})
    if dropped_items:
        record["items_dropped"] = dropped_items
        notes.append({"code": "USER_MESSAGE_ITEM_DROPPED", "text": "; ".join(f"user_message.items[{d['item']}]: {d['reason']}" for d in dropped_items) + " (alpha.99)"})
    if repaired:
        record["literals_escape_repaired"] = repaired
        notes.append({"code": "USER_MESSAGE_ESCAPE_REPAIRED", "text": f"user_message.items{repaired}: the JSON turned a Windows path's backslash sequence into a "
                                                                      "control character; the text written back is in user_messages (alpha.99) - write \\\\ or /"})
    if relocated:
        record["literals_relocated"] = relocated
        notes.append({"code": "USER_MESSAGE_LITERAL_RELOCATED", "text": "; ".join(f"user_message.items[{r['item']}]: declared {r['declared'][:60]!r}, delivered "
                                                                                    f"{r['found'][:60]!r}" for r in relocated) + " (alpha.99: the delivered program text counts)"})
    if delivered:
        record["engine_delivered"] = delivered
        notes.append({"code": "USER_MESSAGE_ENGINE_DELIVERED", "text": "; ".join(f"user_message.items[{d['item']}] ({d['step']}) -> user_messages[{d['index']}]"
                                                                                  for d in delivered) + " (alpha.99: the program's text the executor did not deliver; "
                                                                                                        "it shows in the node block, the report and the answer, not in the live stream)"})
    if not_delivered:
        record["literals_not_delivered"] = not_delivered
        notes.append({"code": "USER_MESSAGE_LITERAL_NOT_DELIVERED", "text": "; ".join(f"user_message.items[{d['item']}] ({d['step']}): {d['reason']}" for d in not_delivered) + " (alpha.99)"})
    if decl["has"] and not msgs:   # alpha.99: nothing arrived and nothing the engine could deliver - the one case still refused
        raise EngineError("USER_MESSAGE_REQUIRED", "user_message.has is true but user_messages carries no text", field="user_messages",
                          expected="the texts this node's program gives the user - generated content in full, quoted texts verbatim")
    if none_default:
        record["none_reason_defaulted"] = True   # r3: written by the engine, not by the executor
    if not decl["has"]:
        prose = _output_prose_chars(payload.get("output"), user_message)   # docs/05SoulRun 87: the user's own words are no prose of this node
        if prose >= USER_MESSAGE_PROSE_MIN:
            notes.append({"code": "USER_MESSAGE_NONE_WITH_TEXT_OUTPUT",
                          "text": f"user_message.has is false ({record['none_reason']!r}) while output carries {prose} characters of prose - text for the user "
                                  "belongs in user_messages (alpha.93)"})
            record["prose_output_chars"] = prose
    return record


def _commit_locked(store, index, run_input, program, node_name, payload_text, agent_ticket: str | None = None) -> dict:
    state = index["run_state"]
    if state in TERMINAL_STATES:
        raise EngineError("RUN_STATE_FORBIDS_COMMIT", f"run is {state}", field="$", expected="RUNNING")
    if state == "WAITING_USER":
        raise EngineError("RUN_STATE_FORBIDS_COMMIT", f"run is WAITING_USER on gate {index['gate']['question_id']}", field="$", expected="gate answered by host")
    current = index["current"]["name"]
    if _conditional_pending(store, index):
        raise EngineError('HUMAN_INTERPRETATION_REQUIRED', 'Interpret the host-recorded conditional reply before business execution or commit.',
                          field='human_compliance', expected='node_commit.py --interpret-human-reply')
    if node_name != current:
        raise EngineError("NODE_MISMATCH", f"current node is {current!r}", field="node", expected=current, example=current)
    from . import partial_commit
    partial_commit.guard_submission(store, index, _catalog_entry(index, current), index['current']['visit'])
    from . import blind_review
    review_binding = blind_review.active(store, index)
    from . import independent_inputs
    scoped_binding = independent_inputs.active(store, index)
    parse_notes: list = []
    if current in (*ACCOUNTING_NODES, *ANSWER_NODES):
        parse_notes.extend(blind_review.anomalies(blind_review.latest_results(store, _report_records(store, index, review_only=True))))
    defaults: list = []   # alpha.106 (doc 265 E4): skeleton defaults taken - machine.defaults_taken, never an anomaly
    raw_gate_intents = []
    na_reasons: list = []   # docs/05SoulRun 87: steps.not_applicable reasons - machine.steps_not_applicable
    payload = _parse_payload(payload_text, parse_notes, defaults, raw_gate_intents=raw_gate_intents, na_reasons=na_reasons)   # alpha.58: escape repairs / intent normalisation are recorded, never rejected
    from . import gate_delivery
    gate_delivery.require(store.cache_dir,index,node=node_name,payload=payload)
    if agent_ticket and _host_markers(payload):   # alpha.62 (doc 135 G1): a sub-agent's stream is never captured - fail at once, no wait
        kinds = _host_markers(payload)
        raise EngineError("HOST_TEXT_UNAVAILABLE_SUBAGENT", f"a sub-agent commit carries \"@host\" for {kinds}", field=HOST_FIELDS[kinds[0]],
                          expected="the full text inline (the host captures only the main agent's visible stream)")
    if current in ANSWER_NODES:   # alpha.90 (doc 202 C): the answer node's user_summary / user_messages / explain are machine placeholders (alpha.45) - an "@host" there is no text to wait for
        carried = [k for k in ("user_summary", "explain") if payload.get(k) == "@host"] + (["user_messages"] if _has_host_marker(payload.get("user_messages")) else [])
        if carried:
            parse_notes.append({"code": "FINAL_PLACEHOLDER_NORMALIZED", "text": f"{carried} carried \"@host\" at {current}; replaced by the machine placeholders, nothing waited for (alpha.90)"})
        payload = dict(payload, user_summary=FINAL_NOTE, user_messages=[], explain="")
    occurrence_ready = _parse_ts((index["nodes"].get(_node_key(current, index["current"]["visit"])) or {}).get("ready_at"))
    payload = _resolve_host_texts(store, current, payload,   # alpha.30 A5 / alpha.44: the streamed texts replace their "@host" markers
                                  not_before=occurrence_ready.timestamp() if occurrence_ready else None,   # alpha.68: only this occurrence's files
                                  notes=parse_notes, language=index.get("user_language"))   # alpha.99 (doc 239 P6 / G6)
    if payload["node"] != current:
        raise EngineError("NODE_MISMATCH", f"payload.node {payload['node']!r} != current {current!r}", field="node", expected=current)
    if 'report_parts' in (payload.get('semantics') or {}) and (current not in ANSWER_PART_NODES or payload.get('gate')):
        raise EngineError('REPORT_PART_INVALID', 'report_parts is only for the `Engine.final-answer` commit (or a legacy Router.summary)', field='semantics.report_parts')
    if current in ANSWER_NODES and isinstance(payload.get("semantics"), dict) and "report_parts" not in payload["semantics"] \
            and payload["status"] == "PASS" and not isinstance(payload.get("gate"), dict):   # alpha.106 (doc 265 E4): the skeleton's list
        required = [copy.deepcopy(c["report_part"]) for c in _report_candidates(store, index, program)["required"]]
        if required:
            payload["semantics"]["report_parts"] = required
            defaults.append("report_parts")
    if 'answer_details' in (payload.get('semantics') or {}) and (current not in FINAL_NODES or payload.get('gate')):
        raise EngineError('FINAL_DETAILS_INVALID', 'answer_details is only for a final summary/direct reply', field='semantics.answer_details')
    entry = _catalog_entry(index, current)
    visit = index["current"]["visit"]
    key = _node_key(current, visit)
    node_entry = index["nodes"].setdefault(key, RunStore.new_node_entry(visit))
    if node_entry["ready_at"] is None:
        node_entry["ready_at"] = now_iso()
    if (node_entry.get("module") or {}).get("state") == "OPEN":
        raise EngineError("SUBSTEPS_INCOMPLETE", f"sub-graph of {current} is still open", field="node",
                          expected="the sub node named by next-node")

    machine_dispatch = _check_dispatch_for_commit(index, program, entry, visit, payload, agent_ticket, store=store)   # doc 10 §3: executor gate first
    executor_mode = _executor_mode(index, program, entry, visit)
    if machine_dispatch and machine_dispatch['actor'] == 'sub_agent' and not dispatch_scope.enabled(index):
        executor_mode = dict(executor_mode, effective='agent', downgrade=None)
    elif machine_dispatch and machine_dispatch.get('fallback'):
        executor_mode = dict(executor_mode, effective='inline', downgrade='AGENT_FALLBACK_INLINE')
    served = _served_steps(entry, program)
    if "steps" in defaults:   # alpha.106 (doc 265 E4): a PASS commit without a gate that left steps out did every served step
        payload["steps"]["done"] = [s["key"] for s in served]
    view = _view_for(program, entry)
    from . import module_order
    module_phase = module_order.validate(store, index, program, entry, visit, view, payload)
    if current in ANSWER_NODES and not any(payload["steps"].values()):   # alpha.99 (doc 240): an answer without steps did the served ones
        payload["steps"]["done"] = [s["key"] for s in served]
    _check_steps_closed(payload, served, notes=parse_notes)   # alpha.99 (doc 239 P3): a gate's pause may leave steps remaining
    if payload["status"] == "DEGRADED" and not payload.get("degraded_reason"):   # alpha.99 (doc 239 P7): defaulted and recorded, not refused
        payload["degraded_reason"] = DEGRADED_REASON_DEFAULT["en" if str(index.get("user_language") or "zh").lower().startswith("en") else "zh"]
        parse_notes.append({"code": "DEGRADED_REASON_DEFAULTED", "text": "status DEGRADED without degraded_reason: the engine wrote that the reason is in this "
                                                                         "node's Report (alpha.99) - give the reason in degraded_reason"})
    artifacts = _check_artifacts(payload, program, index, store=store, notes=parse_notes)   # alpha.99 (doc 239 P2)
    _check_permissions(payload, served, program)
    _check_process_evidence(store, payload, notes=parse_notes)   # alpha.99 (doc 239 P1)
    payload = _resolve_sources_address(store, index, payload, notes=parse_notes)   # alpha.58 B6: evidence.sources given as one address (alpha.99: or the ledger)
    _check_sources(payload, store, program, parse_notes)   # alpha.59: relative source paths resolved and recorded
    payload = _resolve_address_refs(store, index, payload, sub_agent=bool(agent_ticket), notes=parse_notes)   # alpha.57/63: addresses verified, copies converted
    source_proof = _check_source_claims(store, index, payload, notes=parse_notes)   # alpha.99 (doc 239 §3.4): repaired or demoted, never refused
    hsaw_record = _check_hsaw_items(store, index, current, payload, notes=parse_notes, program=program,   # alpha.87 (doc 193): doubt / problem / bug items
                                    pending_answer=_pending_gate_answer(store, index, current, visit))   # alpha.99 (doc 239 §3.3)
    prior_path = _cache_path_for(store, index, entry, visit)
    prior_cache = store.read_json(prior_path) if store.exists_path(prior_path) else None
    if prior_cache is not None and sha256_bytes(store.read_bytes(prior_path)) != node_entry.get("cache_sha256"):
        raise EngineError("CONTINUATION_EVIDENCE_CHANGED", "prior occurrence evidence differs from the accepted cache digest", field="evidence")
    assertion_failed, assert_anomalies = _check_sys_evidence_and_asserts(payload, served, prior_cache=prior_cache)
    public_text = '\n'.join(str(payload.get(k) or '') for k in ('user_summary', 'explain', 'user_messages', 'semantics'))
    upstream_proofs = _public_source_context(store, index) if 'source_verified' in public_text else []
    assert_anomalies.extend(source_support.public_diagnostics(payload, source_proof, upstream=upstream_proofs, visit=visit,   # alpha.112 (doc 276)
                                                              nodes=[e["name"] for e in index["catalog"]]))
    assert_anomalies.extend(evidence_views.evidence_anomalies(payload))
    assert_anomalies.extend(parse_notes)   # alpha.58 #1 / #2
    issues, strict = _output_schema_issues(view, run_input, payload)   # alpha.59 (doc 128 §6): payload_schema.output
    if issues and strict:
        raise EngineError("OUTPUT_SCHEMA_INVALID", issues[0]["message"], field=issues[0]["field"], expected=issues[0].get("expected"),
                          errors=[dict(e, code="OUTPUT_SCHEMA_INVALID") for e in issues[1:]])
    if issues:
        assert_anomalies.append({"code": "OUTPUT_SCHEMA_MISMATCH",
                                 "text": "; ".join(f"{e['field']}: {e['message']}" for e in issues[:6]) + " (alpha.59: see payload_schema.output; recorded, not rejected)"})
    if _pause_output(payload):
        missing = [k for k in (_output_schema_for(view, run_input) or {}).get('required', []) if k not in payload['output']]
        if missing:
            assert_anomalies.append(dict(code='OUTPUT_FIELDS_PENDING', text=f'Gate pause: terminal output fields not produced yet: {missing}; terminal continuation still requires them.'))
    undeclared = _undeclared_output_keys(view, payload)   # alpha.58 B8 (doc 125 §5): recorded, never rejected, never removed
    if undeclared:
        assert_anomalies.append({"code": "OUTPUT_UNDECLARED_KEYS",
                                 "text": f"output keys the program does not declare: {[k for k, _ in undeclared]} ({sum(n for _, n in undeclared)} chars) - "
                                         "narration belongs in Explain; declared keys and machine facts belong in output (alpha.58)"})
    if 'final_answer' in (payload.get('semantics') or {}) and (current not in ANSWER_NODES or payload.get('gate')):
        raise EngineError('FINAL_ANSWER_INVALID', 'final_answer belongs only to the `Engine.final-answer` commit (alpha.45)', field='semantics.final_answer')
    if current in ACCOUNTING_NODES:   # alpha.45: Engine.execute-report carries the accounting only (the schema no longer requires the keys)
        register_problems = hsaw_gate.verify_register(index)   # alpha.87 (doc 193 §3): tamper evidence ends the run
        if register_problems:
            _terminate(index, kind="fatal", by="engine", reason=f"HSAW register integrity: {register_problems[0]}")
            _write_index(store, index)
            raise EngineError("HSAW_REGISTER_INTEGRITY", f"index.hsaw_register chain broken: {register_problems[:3]}", field="$", expected="an untouched register")
        semantics = payload.get('semantics')
        missing = [k for k in ('intent', 'result_summary', 'functional_status', 'nodes_skipped', 'per_node') if not isinstance(semantics, dict) or k not in semantics]
        if missing:
            raise EngineError('REPORT_SEMANTICS_INVALID', f'Engine.execute-report semantics lack {missing}', field='semantics',
                              expected='{intent, result_summary, functional_status, nodes_skipped, per_node}')
        # alpha.54 (doc 115; production cache/79): the accounting must agree with the statuses the engine holds - PASS is impossible
        # while a business / sub node is DEGRADED or FAILED; a stricter status than the nodes imply stays the model's judgement
        main_nodes = _main_nodes_committed(index)   # alpha.83 (doc 174 A; production cache/43: the report of "this turn" - 4 of 6 main nodes)
        accounted = {p.get('node') for p in semantics.get('per_node') or [] if isinstance(p, dict)} | {str(n) for n in semantics.get('nodes_skipped') or []}
        absent = [n for n in main_nodes if n not in accounted]
        if absent:
            raise EngineError('REPORT_SEMANTICS_INCOMPLETE',
                              f'semantics.per_node accounts for {len(main_nodes) - len(absent)} of the {len(main_nodes)} main nodes this run committed; missing {absent}',
                              field='semantics.per_node', expected=absent,
                              example=[{"node": n, "material_action": "", "result": ""} for n in main_nodes])
        floor = _functional_floor(index)
        degraded_nodes, failed_nodes = floor['degraded_nodes'], floor['failed_nodes']
        if semantics.get('functional_status') == 'PASS' and (degraded_nodes or failed_nodes):
            # alpha.79 (doc 163; production cache/32): only the named field was repaired and the public Report kept "PASS" - the same
            # rejection now names the Report sentences that depend on the status, with the node states
            states = evidence_views.node_state_counts(_report_records(store, index), index)
            raise EngineError('REPORT_SEMANTICS_INCONSISTENT',
                              f'functional_status PASS while DEGRADED nodes {degraded_nodes} / FAILED nodes {failed_nodes} are in this run',
                              field='semantics.functional_status', expected=floor['floor'],
                              example={'repair_group': ['semantics.functional_status', 'semantics.result_summary', 'user_summary', 'explain'],
                                       'dependent_report_statements': evidence_views.report_consistency_errors(payload, dict(node_states=states), status=floor['floor']),
                                       'node_states': states,
                                       'rule': 'Correct dependent status/count statements in the uncommitted candidate too; preserve unrelated facts and prior public evidence.'})
    if current in ANSWER_NODES:   # alpha.45: `Engine.final-answer` carries only the answer; its L1 fields are machine-owned placeholders
        extra = sorted(set(payload.get('semantics') or {}) - {'final_answer', 'report_parts', 'answer_details'})
        if extra:
            raise EngineError('FINAL_SEMANTICS_INVALID', f'final semantics carry unexpected keys {extra}', field='semantics', expected='{final_answer, report_parts?, answer_details?}')
        payload = dict(payload, user_summary=FINAL_NOTE, user_messages=[], explain='')
    answer = _answer_body(payload) if current in ANSWER_NODES and not payload.get('gate') else payload['user_summary']
    claim = _timing_claim(payload["user_summary"], payload.get("output"), *payload.get("user_messages", []), answer)
    if claim:
        raise EngineError("UNTRUSTED_TIMING_CLAIM", f"timing text {claim!r} in user-facing fields", field="user_summary",
                          expected="no self-reported execution timings. The timing fields are " + ", ".join(TIMING_FIELDS) + ". " + TIMING_CLAIM_RULE
                                   + " Name the nodes and what happened; the engine measures time itself and shows it in every node's Audit line "
                                   "and in the run accounting")
    pending_answer = _pending_gate_answer(store, index, current, visit)
    gate_view = (module_order.pre_view(view, program, entry) if module_phase and module_phase['state'] == 'ACCEPTED'
                 else module_order.post_view(store,index,program,entry,visit,view) if view else view)
    gs = _gate_summary(gate_view["gate_sources"]) if gate_view else {"required": False, "advisory": False}
    if entry["name"] == NODE_MATCH and payload.get("route") is None and payload.get("gate") is None:
        raise EngineError("ROUTE_INVALID", "Router.match needs route {package, rationale} or a gate", field="route", expected="object", example=_EXAMPLES["route"])
    hsaw_freeze = hsaw_gate.freeze_items((hsaw_record or {}).get("items"))   # alpha.87 (doc 193): critical freezes here, or ends the run
    hsaw_hard = hsaw_gate.hard_fail_items((hsaw_record or {}).get("items"))
    if hsaw_hard and (payload["status"] != "FAIL" or payload.get("error_type") or "gate" in payload):
        raise EngineError("HSAW_HARD_FAIL_STATUS", "a HARD_FAIL item needs status FAIL, no error_type and no gate: the run terminates here",
                          field="status", expected="FAIL")
    complete = payload["status"] in ("PASS", "DEGRADED") and not payload["steps"]["remaining"] and (
        entry["kind"] not in ("business", "sub") or isinstance(payload.get("user_message"), dict))
    if "gate" in payload and pending_answer and not hsaw_freeze and complete:   # alpha.99 (doc 239 G2; isolated 49 / 64): the answered menu again - dropped
        prior = store.read_json(store.gate_path(pending_answer["question_id"]))
        if _gate_identity(payload["gate"]) == _gate_identity(prior):
            payload.pop("gate")
            assert_anomalies.append({"code": "GATE_REPEAT_DROPPED", "text": f"the commit carried gate {pending_answer['question_id']} again after it was answered; "
                                                                            "the repeated menu was dropped and the commit completes with the human's answer (alpha.99)"})
    if hsaw_freeze and "gate" not in payload:   # alpha.99 (doc 239 H7): a critical finding without a gate - the engine composes the hsaw_doubt gate
        payload["gate"] = hsaw_gate.compose_gate(hsaw_freeze, current, index.get("user_language"))
        assert_anomalies.append({"code": "HSAW_GATE_COMPOSED", "text": f"{len(hsaw_freeze)} FREEZE_NOW item(s) and no gate: the engine composed the hsaw_doubt gate - "
                                                                       "the human decides whether this node continues (alpha.99, first rule)"})
    if "steps" in defaults and isinstance(payload.get("gate"), dict):   # alpha.106 (doc 265 E4): a pause never carries default steps
        raise EngineError("SCHEMA_INVALID", "required field 'steps' is missing", field="steps", expected="present",
                          example=_example_for("steps", "steps"))   # the alpha.105 refusal
    if "gate" in payload:  # a pause is not a final commit; successor and budget are judged on continuation
        if not hsaw_freeze and entry["name"] != NODE_MATCH and gs.get("source", "none") == "none":   # alpha.87: a question of the model's own is an hsaw_doubt gate
            raise EngineError("HSAW_ITEM_REQUIRED", "this node declares no gate: a question of your own needs a FREEZE_NOW hsaw_items entry",
                              field="hsaw_items", expected="one FREEZE_NOW item (doubt / problem / bug)", example=_EXAMPLES["hsaw_item"])
        _normalize_gate_shape(payload["gate"], assert_anomalies)   # alpha.99 (doc 239 G4 / G5)
        if hsaw_freeze:
            existing_intents={o.get('intent') for o in payload['gate']['options']}
            payload["gate"] = hsaw_gate.completed_gate(payload["gate"], hsaw_record["items"], current, index.get("user_language"), assert_anomalies)
            if gs.get('source','none')!='none':
                hsaw_record['finding_only_intents']=sorted(({o.get('intent') for o in payload['gate']['options']}-existing_intents)&set(hsaw_gate.BUG_GATE_INTENTS))
        _check_gate_shape(payload["gate"], view, allow_no_recommendation=bool(hsaw_freeze))
        _conditional_declaration(payload['gate'], view, entry, program)
        if hsaw_freeze:
            try:
                hsaw_gate.check_gate(payload["gate"], hsaw_record["items"])
            except hsaw_gate.HsawError as exc:
                raise EngineError(exc.code, exc.message, field=exc.field, expected=exc.expected)
            payload["gate"]["closing"] = hsaw_gate.closing_with_sentence(payload["gate"]["closing"], index.get("user_language"))
        if pending_answer:
            prior = store.read_json(store.gate_path(pending_answer["question_id"]))
            if _gate_identity(payload["gate"]) == _gate_identity(prior):
                raise EngineError("GATE_ALREADY_ANSWERED", "this menu was already answered", field="gate")
        return _pause_with_gate(store, index, entry, visit, payload, node_entry, gate_view, machine_dispatch, pending_answer, executor_mode,
                                source_proof=source_proof, anomalies=assert_anomalies, hsaw=hsaw_record,
                                route_binding=_router_option_bindings(run_input, payload['gate'], raw_gate_intents)
                                if current == NODE_MATCH and not hsaw_freeze else None)
    if hsaw_freeze:
        raise EngineError("HSAW_GATE_REQUIRED", "a FREEZE_NOW item stops execution here: this commit must carry the hsaw_doubt gate",
                          field="gate", expected="gate with resume_boundary", example=_EXAMPLES["gate"])
    if pending_answer and pending_answer.get('business_authorization') is False:
        raise EngineError('BUSINESS_GATE_DECISION_REQUIRED','The human only disposed of an added finding; the original business choice remains unanswered. Present a new gate from accepted work; never replay completed actions.',field='gate',expected='a real human business decision')
    if gs["required"] and pending_answer is None:
        raise EngineError("GATE_REQUIRED", "this node declares a human gate", field="gate", expected="gate object", example=_EXAMPLES["gate"])
    if gs["advisory"] and pending_answer is None and not payload.get("gate_not_triggered_reason") and (
            payload["status"] not in ("PASS", "DEGRADED") or payload["steps"]["remaining"]):   # unfinished work still needs its gate
        raise EngineError("GATE_REQUIRED", "advisory/conditional gate: submit gate or gate_not_triggered_reason", field="gate_not_triggered_reason", expected="string")
    if gs["advisory"] and pending_answer is None and not payload.get("gate_not_triggered_reason"):   # alpha.99 (doc 239 G1): n/a, like a93 r3
        payload["gate_not_triggered_reason"] = "n/a"
        assert_anomalies.append({"code": "GATE_DECISION_UNSTATED", "text": "this node's conditional / advisory gate was neither opened nor given a reason for not "
                                                                           "triggering; recorded as n/a (alpha.99) - the executor's judgement that its condition did not arise stands"})
    questions = delivery_obligations.public_questions(payload)
    prior_question = store.read_json(store.gate_path(pending_answer['question_id']))['question'] if pending_answer else ''
    if any(q not in prior_question for q in questions):
        new_questions = [q for q in questions if q not in prior_question]
        program_asks = [_norm_ws(q) for q in _program_literals(view) if delivery_obligations.is_request(q)]
        if pending_answer and all(any(_norm_ws(q)[:40] in a for a in program_asks) for q in new_questions):   # alpha.99 (doc 239 U8): recorded
            assert_anomalies.append({"code": "GATE_QUESTION_REPEATED", "text": f"this node's gate {pending_answer['question_id']} was already answered and the "
                                                                               f"program's own question appears again in the delivered text {new_questions[:2]}; "
                                                                               "accepted - the human's answer stands (alpha.99)"})
        else:
            raise EngineError('GATE_REQUIRED', 'a public request for a human reply cannot be completed by the executor',
                              field='gate', expected='real HSAW gate, not a default answer', example=_EXAMPLES['gate'])
    user_message_record = None
    if entry['kind'] in ('business', 'sub') and payload['status'] in ('PASS', 'DEGRADED', 'PARTIAL'):   # alpha.93 (doc 218): the declaration
        _attach_host_message(store, current, payload, occurrence_ready, assert_anomalies)   # alpha.99 (doc 239 U7)
        partial_steps = [module_phase['call_step']] if module_phase and module_phase['state'] == 'ACCEPTED' and module_phase['within_step'] else []
        user_message_record = _check_user_message(payload, gate_view, served, assert_anomalies, tool_texts=_tool_texts(store, payload),partial_steps=partial_steps,
                                                  user_message=run_input.get('user_message'))
    duties = delivery_obligations.obligations(gate_view)
    if payload['status'] in ('PASS', 'DEGRADED') and set(duties['required_steps']) & set(payload['steps']['done']) and not any(m.strip() for m in payload['user_messages']):
        raise EngineError('USER_MESSAGE_REQUIRED', f"public output declared in {duties['required_steps']} is missing",   # alpha.93: formerly NODE_MESSAGE_REQUIRED
                          field='user_messages', expected='nonblank program-required result/receipt')
    report_snapshot = evidence_views.report_snapshot(store.cache_dir, index, now_iso(), records=_report_records(store, index),
                                                     hsaw=_hsaw_report_facts(store, index), cancelled=index.get('cancelled')) if current in ACCOUNTING_NODES else None   # alpha.87 / alpha.88
    if current in ACCOUNTING_NODES:
        conflicts = evidence_views.report_consistency_errors(payload, report_snapshot)
        if conflicts:   # alpha.79 (doc 163): every finding in ONE rejection - commit() folds extra rows of the same code + field
            raise EngineError('REPORT_FACTS_INCONSISTENT', f'{len(conflicts)} Report statement(s) disagree with the accepted node records',
                field='user_summary', expected=conflicts,
                example={'repair_group': ['user_summary', 'explain', 'semantics.result_summary'],
                         'node_states': report_snapshot['node_states'], 'functional_status': (payload.get('semantics') or {}).get('functional_status'),
                         'rule': 'Rewrite each `found` statement so it agrees with node_states / functional_status; keep unrelated content. Earlier ACP text and '
                                 'accepted caches are never edited. Write no rejected/error numbers: the machine table carries them.'})
        payload, aligned = evidence_views.align_report_counts(payload, report_snapshot)   # alpha.79: a rejection would change the count it checks
        assert_anomalies.extend(aligned)
        assert_anomalies.extend(evidence_views.report_fact_findings(payload, index, snapshot=report_snapshot, local_anomalies=assert_anomalies))
    if payload["status"] in ("PARTIAL", "DEGRADED") and payload["steps"]["remaining"] and not module_phase:
        raise EngineError("STEPS_NOT_CLOSED", "unfinished work requires a real gate or an honest failure, not a terminal partial commit",
                          field="steps.remaining", expected=[], example=[])
    _apply_gate_branch(store, index, entry, visit, payload)
    if not module_phase or module_phase['state'] != 'ACCEPTED':
        _check_next_hint(payload, view, _planned_next(index, entry), program, in_frame=_frame_of(index, entry) is not None, notes=assert_anomalies)
    budget = _budget_for(entry["kind"], program)
    active_so_far = _active_elapsed_ms(node_entry, now_iso())
    if active_so_far > budget["active_ms"]:   # doc 06 §2 1c: recorded, never a rejection; the model's status stands
        assert_anomalies.append({"code": "BUDGET_EXCEEDED",
                                 "text": f"active {active_so_far} ms > {budget['source']} budget {budget['active_ms']} ms; status kept as reported ({payload['status']})"})
    pre = _prevalidate_advance(store, index, run_input, program, entry, payload)
    report_parts = _resolve_report_parts(store, payload)
    if report_parts:   # alpha.89 (doc 198): delivered in node order whatever the listing; a different listing is recorded, never rejected
        ordered = [p for _, p in sorted(enumerate(report_parts), key=lambda ip: _part_order_key(index, ip[1]['node'], ip[1]['visit'], ip[1]['field'], ip[1].get('message_index'), fallback=ip[0], revision=ip[1]['revision']))]
        if any(a is not b for a, b in zip(ordered, report_parts)):
            assert_anomalies.append({"code": "REPORT_PARTS_REORDERED",
                                     "text": "report_parts were listed as " + ", ".join(_part_label(p) for p in report_parts)
                                             + " and are delivered in node order: " + ", ".join(_part_label(p) for p in ordered)})
        report_parts = ordered
    if current in ANSWER_NODES:   # alpha.69 (doc 147): the reports the run delivered must be in the answer
        _check_required_references(store, index, program, payload, report_parts)
        lead_note = _check_final_lead(store, payload, report_parts)   # alpha.83 (doc 174 B): refused once, then recorded
        if lead_note:
            assert_anomalies.append(lead_note)
    if executor_mode.get("downgrade"):
        assert_anomalies.append({"code": executor_mode["downgrade"],
                                 "text": f"declared={executor_mode['declared']}, effective={executor_mode['effective']}; execution mode is not evidence of independent review"})

    payload, human_decisions = _fill_human_decisions(store, index, current, visit, payload)   # alpha.58 B9 (doc 125 §9.2 #2)
    conditions = _conditional_records(store, index)
    aliases = _conditional_node_aliases(program, index, current) if program else {current}
    required_conditions = conditional_reply.for_node(conditions, aliases)
    try:
        human_compliance = conditional_reply.compliance(required_conditions, payload.get('human_compliance'),
            ref_ok=lambda ref: _hsaw_ref_exists(store, index, payload, ref))
    except conditional_reply.ReplyError as exc:
        raise EngineError(exc.code, exc.message, field=exc.field) from exc
    shown_conditions = conditions if current in (*ACCOUNTING_NODES, *ANSWER_NODES) else [
        r for r in conditions if r['question_id'] in {i['question_id'] for i in required_conditions}]
    shown_compliance = (_conditional_compliance_records(_prev_business_caches(store, index)) + human_compliance
                        if current in (*ACCOUNTING_NODES, *ANSWER_NODES) else human_compliance)
    execution_summary = payload['user_summary'] if current == NODE_REPORT else None
    if execution_summary is not None and sum(not c.isspace() for c in execution_summary) < 500:
        raise EngineError('EXECUTION_SUMMARY_REQUIRED', 'Execution report summary needs 500 non-whitespace characters; references and machine tables do not count.',field='user_summary')
    if execution_summary is not None and len(execution_summary) > 2000:
        assert_anomalies.append(dict(code='EXECUTION_SUMMARY_LONG',text='Execution report summary exceeds 2000 characters; accepted without functional degradation.'))
    condition_table = conditional_reply.table(shown_conditions, shown_compliance, index.get('user_language'),
        not_reached=_conditional_unreached(store, index) if current in ACCOUNTING_NODES else ())
    if condition_table:
        if current in ANSWER_NODES:
            payload['semantics']['final_answer'] = str(payload['semantics'].get('final_answer') or '') + '\n\n' + condition_table
        else:
            payload['user_summary'] += '\n\n' + condition_table
    payload, report_projection = evidence_views.project_report(payload, index.get('user_language'),
        gate_answer=pending_answer, snapshot=report_snapshot,
        decisions=human_decisions if current in ACCOUNTING_NODES else ())

    # --- writes: cache, then index (one transition) ----------------------------
    now = now_iso()
    cache_path = _cache_path_for(store, index, entry, visit)
    dropped = repairs.dropped_fields(assert_anomalies)   # alpha.99 (doc 239): every value a repair removed, kept
    machine = {"committed_at": now, "ready_at": node_entry["ready_at"], "trace_id": index["trace_id"], "engine_version": ENGINE_VERSION,
               "artifacts": artifacts, "logical_tool_calls": len(payload["evidence"]["tool_calls"]), "assertion_failed": assertion_failed,
               "engine_anomalies": assert_anomalies, "dispatch": machine_dispatch, "execution_mode": executor_mode,
               "revisit": pre.get("revisit")}
    if review_binding:
        _, owner = _self_dispatch(index, entry, visit)
        machine['review_binding'] = copy.deepcopy(owner['review_binding'])
    if scoped_binding:
        _, owner = _self_dispatch(index, entry, visit)
        machine['input_binding'] = copy.deepcopy(owner['input_binding'])
    if module_phase:
        machine['module_prefix'] = module_phase
    if human_compliance:
        machine['human_compliance'] = dict(declarations=human_compliance, verification_scope=conditional_reply.SCOPE,
                                           semantic_correctness='UNVERIFIED', actual_compliance='UNVERIFIED')
    if dropped:
        machine["dropped_fields"] = dropped
    if report_parts is not None:
        machine['report_parts'] = report_parts
    if report_projection:
        machine['report_projection'] = report_projection
    if execution_summary is not None:
        from . import execution_report
        machine['execution_report'] = execution_report.describe(execution_summary, payload['user_summary'],store.cache_dir.name,current,visit,index.get('user_language'))
        try:
            execution_report.materialize(store,machine['execution_report'],payload['user_summary'])
        except (OSError, ValueError) as exc:
            raise EngineError('EXECUTION_REPORT_FILE_INVALID', str(exc), field='user_summary') from exc
    if hsaw_record:
        machine['hsaw'] = hsaw_record['machine']   # alpha.87: the items with their engine-owned identities
    if user_message_record is not None:
        machine['user_message'] = user_message_record   # alpha.93: the executor's declaration as checked
    if any(source_proof[k] for k in ('source_verified', 'derived', 'unverified')):
        machine['source_support'] = source_proof
    if defaults:
        machine['defaults_taken'] = list(defaults)   # alpha.106 (doc 265 E4): steps / report_parts left out, the skeleton's taken
    if na_reasons:
        machine['steps_not_applicable'] = na_reasons   # docs/05SoulRun 87: why each step did not apply, as the executor wrote it
    if human_decisions:
        machine['human_decisions'] = human_decisions   # alpha.58 B9: also here, for nodes whose output is a string
    if current in FINAL_NODES:
        machine['final_answer_basis'] = _final_answer_basis(store, index, entry, visit, payload, machine)
    if entry["kind"] == "sub":
        machine["tree"] = {"parent": entry["parent"], "parent_visit": node_entry.get("parent_visit"), "depth": entry["depth"],
                           "order": node_entry.get("order"), "doc": entry["doc"], "task": entry["task"]}
    from . import partial_commit
    partial_commit.prepare(store, index, entry, visit,
                           dict(payload=payload, machine=machine, gate_answer=pending_answer),
                           hsaw_events=hsaw_record['events'] if hsaw_record else (),
                           shared_events=hsaw_record['events'] if hsaw_record else ())
    if store.exists_path(cache_path):
        store.append_continuation(cache_path, {"payload": payload, "machine": machine, "gate_answer": pending_answer})
    else:
        store.write_json_once(cache_path, {"cache_schema_version": 1, "program": _program_name(index), "node": current, "kind": entry["kind"],
                                           "visit": visit, "ordinal": entry["ordinal"], "payload": payload, "machine": machine, "gate": None, "continuations": []})
    cache = store.read_json(cache_path)
    if pending_answer:
        _mark_gate_consumed(store, pending_answer["question_id"])
    if hsaw_record:   # alpha.87: the run register (chained) and the package ledger, before the transition closes evidence
        hsaw_gate.append_events(index, hsaw_record["events"])
        _hsaw_ledger_append(store, index, hsaw_record["events"])
    result = _apply_commit_to_index(store, index, run_input, program, entry, visit, payload, cache, cache_path, pre, recovered=False)
    _write_index(store, index)
    result.update({"status": "COMMITTED", "node": current, "cache_sha256": index["nodes"][key]["cache_sha256"], "run_state": index["run_state"]})
    return result


def _public_source_context(store, index):
    """Only hashed, accepted latest occurrences may bind a public upstream claim ID."""
    rows = []
    for c in index['completed']:
        entry = _catalog_entry(index, c['name'])
        if not entry or entry['kind'] not in ('business', 'sub'):
            continue
        path = _cache_path_for(store, index, entry, c['visit'])
        raw = store.read_bytes(path)
        if sha256_bytes(raw) != index['nodes'][_node_key(c['name'], c['visit'])]['cache_sha256']:
            raise EngineError('SOURCE_CONTEXT_CHANGED', 'upstream source occurrence digest changed', field='evidence')
        cached = strict_loads(raw.decode('utf-8'))
        record = (cached.get('continuations') or [cached])[-1]
        proof = record['machine'].get('source_support', {})
        if proof.get('verification_scope') == source_support.SCOPE:
            rows.append(dict(node=c['name'], visit=c['visit'], **proof))
    return rows


def _check_steps_closed(payload: dict, served: list[dict], notes: list | None = None) -> None:
    keys = [s["key"] for s in served]
    given = payload["steps"]["done"] + payload["steps"]["remaining"] + payload["steps"]["not_applicable"]
    if sorted(given) != sorted(keys) or len(set(given)) != len(given):
        raise EngineError("STEPS_NOT_CLOSED", f"served steps {keys}, payload covers {given}", field="steps", expected=keys,
                          example={"done": keys, "remaining": [], "not_applicable": []})
    if payload["status"] == "PASS" and payload["steps"]["remaining"]:
        if isinstance(payload.get("gate"), dict):   # alpha.99 (doc 239 P3; isolated cache 57): a pause leaves steps remaining
            if notes is not None:
                notes.append({"code": "STEPS_REMAINING_AT_GATE", "text": f"status PASS with remaining steps {payload['steps']['remaining']} on a commit that carries a "
                                                                         "gate: a pause, accepted (alpha.99)"})
            return
        raise EngineError("STEPS_NOT_CLOSED", "status PASS with remaining steps", field="steps.remaining", expected=[], example=[])


DEGRADED_REASON_DEFAULT = {"zh": "执行者未单独写降级原因；见本节点 Report。", "en": "The executor gave no separate reason; see this node's Report."}
_SOURCE_CANDIDATE_MIN = 2048   # alpha.99 (doc 239 S4): a saved original is a page or a document, not a note
_SOURCE_CANDIDATE_SKIP = re.compile(r'"(?:evidence_span|evidence_locator|support_check|claim_id)"|\bevidence_span\b')
_SCRIPT_SUFFIXES = (".py", ".ps1", ".sh", ".bat", ".cmd", ".js", ".ts")


def _source_candidates(store, payload: dict) -> list[tuple[str, str]]:
    """alpha.99 (doc 239 S4 / S5): the files of this run that may hold a source's original - this payload's artifacts and captures and the
    files under _work/ - never the engine's reply archive, never a script, never a file that carries claim records (a ledger holds the
    executor's own copies of the passages, not the original), never a note under 2 KB."""
    out, seen = [], set()

    def add(address: str, path: Path) -> None:
        try:
            real = path.resolve()
            if real in seen or not path.is_file() or path.suffix.lower() in _SCRIPT_SUFFIXES or re.search(r"search|snippet", path.name, re.I):
                return
            size = path.stat().st_size
            if size < _SOURCE_CANDIDATE_MIN or size > PROC_MAX_BYTES:
                return
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return
        if _SOURCE_CANDIDATE_SKIP.search(text) or '"snippet"' in text:   # a claim ledger or a search dump holds copies, not the original
            return
        seen.add(real)
        out.append((address, text))

    for n, art in enumerate(payload["evidence"]["artifacts"]):
        if isinstance(art, dict) and art.get("path"):
            add(f"artifact:{n}", Path(art["path"]))
    for call in payload["evidence"]["tool_calls"]:
        if isinstance(call, dict) and call.get("stdout_path"):
            add(f"proc:{call['stdout_path']}", store.cache_dir / call["stdout_path"])
    work = store.cache_dir / "_work"
    if work.is_dir():
        for p in sorted(work.rglob("*")):
            rel = p.relative_to(work).as_posix()
            if rel.split("/", 1)[0] not in _ENGINE_WORK_DIRS:
                add(f"work:{rel}", p)
    return out


def _tool_texts(store, payload: dict) -> list[str]:
    """alpha.99 (doc 239 U2): the captured stdout of this payload's tool calls, to name where a text labelled literal came from"""
    out = []
    for call in payload["evidence"]["tool_calls"]:
        rel = call.get("stdout_path") if isinstance(call, dict) else None
        if rel:
            try:
                path = store.cache_dir / rel
                if path.is_file() and path.stat().st_size <= PROC_MAX_BYTES:
                    raw = path.read_bytes().decode("utf-8", errors="replace")
                    out.append(raw)
                    try:
                        parsed = strict_loads(raw)
                    except ValueError:
                        continue
                    stack = [parsed]
                    while stack:
                        v = stack.pop()
                        if isinstance(v, str):
                            out.append(v)
                        elif isinstance(v, dict):
                            stack.extend(v.values())
                        elif isinstance(v, list):
                            stack.extend(v)
            except OSError:
                continue
    return out


def _attach_host_message(store, node: str, payload: dict, ready, notes: list) -> None:
    """alpha.99 (doc 239 U7; production 4 / 6, isolated 49): user_message.has true and no message - this occurrence's streamed User Message
    is attached when the host has it (waiting the usual host-text budget)"""
    decl = payload.get("user_message")
    if not (isinstance(decl, dict) and decl.get("has") and not any(isinstance(m, str) and m.strip() for m in payload.get("user_messages") or [])):
        return
    try:
        text = _read_host_text(store, "message", node, time.monotonic() + HOST_REPORT_WAIT_S, ready.timestamp() if ready else None)
    except EngineError:
        return
    payload["user_messages"] = [text]
    notes.append({"code": "HOST_MESSAGE_ATTACHED", "text": f"user_message.has is true and user_messages was empty; this occurrence's streamed User Message "
                                                          f"({host_text_name('message', node)}, {len(text)} chars) was attached (alpha.99)"})


def _host_fences(store, index: dict) -> list[str]:
    """alpha.99 (doc 239 P5): this occurrence's streamed User Message fences as the host kept them (<file>.fences.json, alpha.95)"""
    node = index["current"]["name"]
    path = store.cache_dir / (host_text_name("message", node) + ".fences.json")
    ready = _parse_ts((index["nodes"].get(_node_key(node, index["current"]["visit"])) or {}).get("ready_at"))
    try:
        if not path.is_file() or (ready is not None and path.stat().st_mtime < ready.timestamp() - HOST_TEXT_FRESH_SLACK_S):
            return []
        fences = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f for f in fences if isinstance(f, str) and f.strip()] if isinstance(fences, list) else []


def _resolve_artifact_path(raw: str, store, program, target_dir) -> Path | None:
    """alpha.99 (doc 239 P2; isolated cache 47: `_work/FetchData.stockanalysis.quote.md`): a relative artifact path, resolved against the cache
    directory, its _work/, the program directory and the target directory, in that order"""
    rel = str(raw).replace("\\", "/")
    bases = [b for b in ((store.cache_dir if store is not None else None), (store.cache_dir / "_work" if store is not None else None),
                         getattr(program, "dir", None), target_dir) if b]
    for base in bases:
        for cand in (Path(base) / rel, (Path(base) / rel.split("_work/", 1)[1]) if "_work/" in rel else None):
            if cand is not None and cand.exists():
                return cand.resolve()
    return None


def _check_artifacts(payload: dict, program, index: dict, store=None, notes: list | None = None) -> list[dict]:
    out = []
    target_dir = index.get("target_aiap_dir") or payload.get("target_aiap_dir")
    if program is not None:
        for target in (index.get('target_aiap_dir'), payload.get('target_aiap_dir')):
            if target:
                program_guard.check_write_target(target, program.dir, purpose='program')
    for i, art in enumerate(payload["evidence"]["artifacts"]):
        if any(ord(c) < 32 or ord(c) == 127 for c in art['path']):
            raise EngineError('INVALID_WRITE_PATH', f"Corrupted artifact path: {art['path']!r}", field=f'evidence.artifacts[{i}].path')
        path = Path(art["path"])
        if not path.exists():   # alpha.99 (doc 239 P2): a relative path is resolved; a file that is nowhere is recorded, not refused
            found = None if path.is_absolute() else _resolve_artifact_path(art["path"], store, program, target_dir)
            if found is None:
                if notes is not None:
                    notes.append({"code": "ARTIFACT_NOT_FOUND", "text": f"evidence.artifacts[{i}].path {art['path']!r} does not exist; kept, not hashed (alpha.99)"})
                out.append({"path": str(path), "sha256": None})
                continue
            if notes is not None:
                notes.append({"code": "ARTIFACT_PATH_RESOLVED", "text": f"evidence.artifacts[{i}].path {art['path']!r} -> {found.as_posix()} (alpha.99: give absolute paths)"})
            art["path"] = str(found)
            path = found
        resolved = path.resolve()
        if program is not None and not (path.is_dir() and not art.get('mutation') and not art.get('artifact_mutation')):
            program_guard.check_write_target(path.absolute(), program.dir, purpose='artifact',
                                             cache_dir=store.cache_dir if store else None, field=f'evidence.artifacts[{i}].path')
        sha = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if art.get("sha256") and sha and art["sha256"] != sha and notes is not None:   # alpha.99: the engine's own hash is kept, the difference recorded
            notes.append({"code": "PROCESS_SELF_REPORT_CORRECTED", "text": f"evidence.artifacts[{i}].sha256 given {str(art['sha256'])[:16]}… differs from the "
                                                                           "file; the engine's hash is kept (alpha.99)"})
        if sha:   # alpha.57 B1 (doc 121 §6 / §8.5): the receipt is engine-derived - the model need not retype sha256 / bytes from the writer's stdout
            art["sha256"] = sha
            art["bytes"] = path.stat().st_size
            art["verified_by"] = "engine"
        receipt = {"path": str(path.absolute()), "sha256": sha}
        if path.is_dir():
            from . import blind_review
            receipt['directory_manifest'] = blind_review.directory_manifest(path)
        out.append(receipt)
    return out


def _check_permissions(payload: dict, served: list[dict], program) -> None:
    denied = sorted({s["key"] for s in served if s.get("permission") == "denied"} & set(payload["steps"]["done"]))
    if denied:
        raise EngineError("PERMISSION_VIOLATION", f"steps {denied} are outside declared permissions", field="steps.done",
                          expected="denied steps in not_applicable with a DEGRADED reason")
    for i, call in enumerate(payload["evidence"]["tool_calls"]):
        if _tool_permission(program, call["tool"], call.get("sys_call")) == "denied":
            raise EngineError("PERMISSION_VIOLATION", f"tool call {call['tool']!r} is outside declared permissions",
                              field=f"evidence.tool_calls[{i}].tool", expected="an allowed tool")


def _output_text(payload: dict) -> str:
    out = payload.get("output")
    return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)


_STDOUT_PATH_RE = re.compile(r"^_proc/[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
_SOURCE_URL_RE = re.compile(r"^https?://[^\s/?#]+[^\s]*$", re.I)
PROC_MAX_BYTES = 8 * 1024 * 1024
LEDGER_GENESIS = "GENESIS"


SOURCE_EVIDENCE_ROUND = True   # alpha.99 (doc 240 decision point): False = never refuse, demote only (fewer verified claims)
SOURCE_ROUND_MIN, SOURCE_ROUND_SHARE = 3, 0.1   # the round is given when at least 3 claims and 10% of the labelled ones cannot be supported
SOURCE_ROUND_FILE = "source_evidence_round.json"


def _source_evidence_round(store, index: dict, proof: dict) -> None:
    """alpha.99 (doc 239 §3.4, revised in doc 240): the replay of the 35 source refusals since alpha.93 showed that the refusal is the lever
    that makes an executor save and point at its originals - first attempts supported 254 claims, the records after the refusals 705. So a
    commit whose own source_verified claims fail systematically (>= SOURCE_ROUND_MIN and >= SOURCE_ROUND_SHARE of them) gets ONE feedback
    round per node occurrence, with every claim and its reason; the next commit of that occurrence is accepted and whatever is still
    unsupported is counted unverified. Fewer failures are demoted at once. The round is marked in _work/source_evidence_round.json."""
    if not SOURCE_EVIDENCE_ROUND:
        return
    failing = [d for d in proof.get("demoted") or [] if d.get("reason") != "demoted where it was first checked"]
    ids = sorted({str(d.get("claim_id")) for d in failing})
    labelled = proof.get("labelled") or 0
    if len(ids) < SOURCE_ROUND_MIN or len(ids) < SOURCE_ROUND_SHARE * labelled:
        return
    key = f"{index['current']['name']}@{index['current']['visit']}"
    path = store.cache_dir / "_work" / SOURCE_ROUND_FILE
    try:
        given = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        given = {}
    if key in given:
        return
    given[key] = {"at": now_iso(), "claims": len(ids), "labelled": labelled}
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, dumps(given).encode("utf-8"))
    by_reason: dict = {}
    for d in failing:
        by_reason.setdefault(d.get("reason"), []).append(d)
    issues = [dict(code="SOURCE_SUPPORT_INVALID", field=d["field"], message=f"{d.get('claim_id')}: {d.get('reason')}") for d in failing[:32]]
    raise EngineError("SOURCE_SUPPORT_INVALID",
                      f"{len(ids)} of the {labelled} claims this commit labels source_verified cannot be supported by captured content - "
                      + "; ".join(f"{len(v)}x {k}" for k, v in by_reason.items())
                      + ". This is the one evidence round of this node (alpha.99): save the originals and point content_ref at them, declare the "
                        "sources a claim names, copy the passage that holds the value (or give evidence_locator) - or label a claim unverified. "
                        "The next commit of this node is accepted; whatever is still unsupported is then counted unverified.",
                      field="output", expected="captured originals holding each passage, or honest unverified labels",
                      errors=issues[1:] if issues else [])


class _LazyIds:
    """alpha.99 (doc 239 S2): the claim_ids upstream nodes checked, read only when a claim without a support check needs them"""

    def __init__(self, fn):
        self.fn, self.ids = fn, None

    def __contains__(self, item) -> bool:
        if self.ids is None:
            self.ids = self.fn()
        return item in self.ids


def _check_source_claims(store, index, payload, notes: list | None = None):
    ctx = _address_ctx(payload)
    def binding(observed, record):
        proof = record['machine'].get('source_support') or {}
        checked = observed['field'] == 'output' and proof.get('verification_scope') == source_support.SCOPE
        scope = f"{observed['node']}@{observed['visit']}"
        classes = proof.get('claim_classifications') if checked else None
        if checked and isinstance(proof.get('effective_classifications'), dict):
            classes = {label: [cid[len(scope) + 1:] for cid in ids if cid.startswith(scope + '/')]
                       for label, ids in proof['effective_classifications'].items()}
        return dict(scope=scope, checked=checked, classes=classes,
                    demoted=[d.get('claim_id') for d in proof.get('demoted') or []] if checked else [])

    def materialize(value, scope, depth=0, origin_binding=None):
        if depth > 16:
            raise source_support.SupportError('output', 'overdeep inherited source reference')
        if isinstance(value, dict):
            if ADDRESS_REF_KEY in value:
                observed, selected = _resolve_address_target(store, index, scope, value[ADDRESS_REF_KEY], 'output', _address_ctx(scope))
                expected = (value.get(ADDRESS_REF_RESOLVED) or {}).get('sha256')
                if expected and observed['sha256'] != expected:
                    raise source_support.SupportError('output', 'inherited source capture changed since commit')
                if observed['kind'] == 'input':
                    raw = store.read_bytes(store.cache_dir / observed['cache'])
                    if sha256_bytes(raw) != observed['sha256']:
                        raise source_support.SupportError('output', 'nested source occurrence cache digest mismatch')
                    origin = strict_loads(raw.decode('utf-8'))
                    scope = _payload_at_revision(origin, observed['revision'])
                    record = (origin['continuations'][observed['revision'] - 1] if observed['revision'] else origin)
                    origin_binding = binding(observed, record)
                return materialize(selected, scope, depth + 1, origin_binding)
            expanded = {k: materialize(v, scope, depth + 1, origin_binding) for k, v in value.items()}
            if origin_binding is not None and 'verification' in value and ('claim_id' in value or 'id' in value):
                return source_support.InheritedClaim(expanded, **origin_binding)
            return expanded
        if isinstance(value, list):
            return [materialize(v, scope, depth + 1, origin_binding) for v in value]
        return value
    def resolve(address, field):
        try:
            observed, selected = _resolve_address_target(store, index, payload, address, field, ctx)
            if observed['kind'] == 'input':
                raw = store.read_bytes(store.cache_dir / observed['cache'])
                if sha256_bytes(raw) != observed['sha256']:
                    raise source_support.SupportError(field, 'source occurrence cache digest mismatch')
                origin = strict_loads(raw.decode('utf-8'))
                record = (origin['continuations'][observed['revision'] - 1] if observed['revision'] else origin)
                selected = materialize(selected, record['payload'], origin_binding=binding(observed, record))
                if observed['field'] == 'output' and record['machine'].get('source_support', {}).get('verification_scope') == source_support.SCOPE:
                    observed['prior_source_support'] = True
                    observed['prior_demoted'] = [d.get('claim_id') for d in record['machine']['source_support'].get('demoted') or []]   # alpha.99
                    observed['prior_claim_classifications'] = record['machine']['source_support'].get('claim_classifications')
            return observed, selected
        except (EngineError, OSError) as exc:
            raise source_support.SupportError(field, str(exc)) from exc
    def raw_text(address, observed):   # alpha.99 (doc 239 S5): the capture's bytes as text, from the record resolve() already made
        kind = (observed or {}).get('kind')
        path = store.cache_dir / observed['path'] if kind in ('proc', 'work') else Path(observed['path']) if kind == 'artifact' else None
        try:
            return path.read_bytes().decode('utf-8', errors='replace') if path is not None and path.is_file() and path.stat().st_size <= PROC_MAX_BYTES else None
        except OSError:
            return None
    upstream = _LazyIds(lambda: {cid for row in _public_source_context(store, index)
                                for cid in source_support.effective_view(row).get('claim_ids') or []})
    try:
        proof = source_support.validate(payload.get('output'), payload['evidence']['sources'], resolve, raw_text=raw_text,
                                        candidates=lambda: _source_candidates(store, payload), upstream_ids=upstream, notes=notes,
                                        claim_scope=f"{payload['node']}@{index['current']['visit']}")
        _source_evidence_round(store, index, proof)   # alpha.99 (doc 239 §3.4 revised): at most one feedback round per occurrence
        return proof
    except source_support.SupportError as exc:
        raise EngineError('SOURCE_SUPPORT_INVALID', str(exc), field=exc.field,
                          expected='captured original plus located supporting passage, or an honest unverified claim',
                          errors=getattr(exc, 'issues', [])) from exc


def _check_sources(payload: dict, store: RunStore | None = None, program=None, notes: list | None = None) -> None:
    """alpha.22 (doc 44 E3, v6 source_evidence_audit lite): a source is a page the reader can open. alpha.59 (doc 127 / 128 L3;
    production cache/88, 92): a relative path is resolved against the cache directory, then the program directory, and recorded."""
    sources = payload["evidence"].get("sources") or []
    for i, src in enumerate(sources):
        if 'path' in src and (not isinstance(src['path'], str) or
                              any(ord(c) < 32 or ord(c) == 127 for c in src['path'])):
            raise EngineError('INVALID_SOURCE_PATH', 'source path contains control characters or is not text; use forward slashes in Windows paths',
                              field=f'evidence.sources[{i}].path', expected='D:/workspace/source.json')
    for i, src in enumerate(sources):
        if any(k in src for k in ('recorded_at', 'retrieval_time_basis')):
            raise EngineError('SOURCE_TIME_AUTHORITY_INVALID', 'source clock provenance is engine-owned', field=f'evidence.sources[{i}]')
        if 'path' in src:
            path = Path(src['path'])
            if not path.is_absolute():
                for where, base in (("the cache directory", store.cache_dir if store is not None else None),
                                    ("the program directory", getattr(program, "dir", None))):
                    if base is not None and (Path(base) / path).is_file():
                        resolved = (Path(base) / path).resolve()
                        if notes is not None:
                            notes.append({"code": "SOURCE_PATH_RESOLVED", "text": f"evidence.sources[{i}].path {src['path']!r} resolved against {where} -> "
                                                                                   f"{resolved.as_posix()} (alpha.59: give absolute paths)"})
                        src['path'] = str(resolved)
                        path = resolved
                        break
            owned = [k for k in ('bytes', 'verification_scope') if k in src]
            for key in owned:   # alpha.99 (doc 239 S11): engine-owned values the executor wrote are replaced by the engine's
                src.pop(key)
            if owned and notes is not None:
                notes.append({"code": "PROCESS_SELF_REPORT_CORRECTED", "text": f"evidence.sources[{i}] carried engine-owned {owned}; the engine's values are kept (alpha.99)"})
            try:
                if not path.is_absolute() or not path.is_file() or path.stat().st_size > PROC_MAX_BYTES:
                    raise ValueError('not an absolute regular file of at most 8 MiB')
                raw = path.read_bytes()
            except (OSError, ValueError) as exc:   # alpha.99 (doc 239 S11; production 13, isolated 33 / 43: a directory)
                src.pop('sha256', None)
                if notes is not None:
                    notes.append({"code": "SOURCE_PATH_NOT_FILE", "text": f"evidence.sources[{i}].path {src['path']!r}: {exc}; kept as a locator, not hashed - a claim "
                                                                           "cannot be verified against it (alpha.99)"})
                continue
            digest = sha256_bytes(raw)
            if src.get('sha256') and src['sha256'] != digest and notes is not None:
                notes.append({"code": "PROCESS_SELF_REPORT_CORRECTED", "text": f"evidence.sources[{i}].sha256 differs from the file; the engine's hash is kept (alpha.99)"})
            src.update(sha256=digest, bytes=len(raw), verification_scope='local_file_bytes_only')
            continue
        url = src.get("url")
        if not isinstance(url, str) or not _SOURCE_URL_RE.fullmatch(url.strip()):
            raise EngineError("SOURCE_URL_INVALID", f"sources[{i}].url {str(url)[:60]!r} is not an absolute http(s) URL",
                              field=f"evidence.sources[{i}].url", expected="https://host/path")
        src.update(recorded_at=now_iso(), retrieval_time_basis=(
            'model_reported_unverified' if src.get('retrieved_at') else 'unobserved'))


def _canonical_digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ledger_errors(events) -> list[str]:
    """v6.25.0 engine_contracts._chain_errors: sequence, prev_hash and entry_hash of every event must hold."""
    if events is None:
        return []
    if not isinstance(events, list):
        return ["ledger must be an array"]
    errors: list[str] = []
    previous = LEDGER_GENESIS
    for expected, event in enumerate(events, start=1):
        label = f"events[{expected - 1}]"
        if not isinstance(event, dict):
            errors.append(f"{label} must be an object")
            continue
        if event.get("sequence") != expected:
            errors.append(f"{label} sequence mismatch")
        if event.get("prev_hash") != previous:
            errors.append(f"{label} prev_hash mismatch")
        actual = _canonical_digest({k: v for k, v in event.items() if k != "entry_hash"})
        if event.get("entry_hash") != actual:
            errors.append(f"{label} entry_hash mismatch")
        previous = str(event.get("entry_hash") or "")
    return errors


def _read_ledger(store) -> list:
    try:
        data = json.loads(store.evidence_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, RecursionError):   # record 90 round 4 (B6): JSON nested past the recursion limit is corrupt
        return [{"corrupt": True}]
    return data if isinstance(data, list) else [{"corrupt": True}]


def _ledger_append(store, index: dict, event: dict) -> dict:
    """Append one hash-chained event to _evidence.json (doc 44 E2). A broken prior chain is recorded in the event and as
    an EVIDENCE_LEDGER_BROKEN anomaly; it never blocks the transition (tamper evidence, not tamper prevention)."""
    events = _read_ledger(store)
    ident = {k: event.get(k) for k in ("kind", "node", "visit", "revision", "question_id", "final_answer_sha256")}
    for existing in events:
        if isinstance(existing, dict) and all(existing.get(k) == v for k, v in ident.items()):
            return existing   # idempotent: an orphan-cache recovery re-applies a commit whose event already landed
    errors = ledger_errors(events)
    if errors:
        event["prior_chain_errors"] = errors[:8]
        index["anomalies_summary"].append({"node": event.get("node") or NODE_SUMMARY, "code": "EVIDENCE_LEDGER_BROKEN",
                                           "text": f"_evidence.json chain broken before event {len(events) + 1}: {errors[0]}"})
    event["sequence"] = len(events) + 1
    event["prev_hash"] = str(events[-1].get("entry_hash") or "") if events and isinstance(events[-1], dict) else LEDGER_GENESIS
    event["entry_hash"] = _canonical_digest(event)
    events.append(event)
    atomic_write_bytes(store.evidence_path, dumps(events).encode("utf-8"))
    return event


def verify_evidence_ledger(cache_dir: str | Path) -> dict:
    """Read-only: {ok, events, errors} for the run's hash-chained evidence ledger."""
    store = RunStore(cache_dir)
    events = _read_ledger(store)
    errors = ledger_errors(events)
    return {"ok": not errors, "events": events, "errors": errors}


def _ledger_tool_calls(payload: dict) -> list[dict]:
    out = []
    for call in payload["evidence"].get("tool_calls") or []:
        process = _is_process_call(call)
        out.append({"tool": call.get("tool"), "step": call.get("step"), "sys_call": call.get("sys_call"), "process": process,
                    "verified_by": call.get("verified_by") if process else None, "stdout_path": call.get("stdout_snapshot") or call.get("stdout_path"),
                    "stdout_sha256": call.get("stdout_sha256"), "stdout_bytes": call.get("stdout_bytes"), "exit_code": call.get("exit_code")})
    return out


def _ledger_sources(payload: dict) -> list[dict]:
    return [{k: s.get(k) for k in ('url', 'path', 'label', 'tool', 'retrieved_at', 'recorded_at', 'retrieval_time_basis', 'source_id', 'title', 'sha256', 'bytes', 'verification_scope') if k in s}   # alpha.64: + label, tool
            for s in payload["evidence"].get("sources") or []]


def _ledger_commit_event(index: dict, entry: dict, visit: int, revision: int, payload: dict, machine: dict, *, kind: str, question_id: str | None = None) -> dict:
    node_entry = index["nodes"].get(_node_key(entry["name"], visit)) or {}
    event = {"kind": kind, "at": machine.get("committed_at") or now_iso(), "trace_id": index["trace_id"], "engine_version": ENGINE_VERSION,
             "node": entry["name"], "visit": visit, "revision": revision, "status": payload.get("status"),
             "cache_sha256": node_entry.get("cache_sha256"), "tool_calls": _ledger_tool_calls(payload),
             "artifacts": [{"path": a.get("path"), "sha256": a.get("sha256")} for a in (machine.get("artifacts") or [])],
             "sources": _ledger_sources(payload),
             "anomalies": len(payload.get("anomalies") or []) + len(machine.get("engine_anomalies") or [])}
    if question_id:
        event["question_id"] = question_id
    if entry["name"] == NODE_MATCH and kind == "commit":
        event["route"] = {"package": index["route"].get("package"), "catalog_sha256": index["route"].get("catalog_sha256"),
                          "governance": index["program"].get("governance")}
    return event


def _program_governance(program_dir: Path) -> dict:
    """alpha.22 (doc 44 E4, doc 35 T22): canonical v1.0 governance hash of the routed program (sorted *.aisop.json,
    JCS-style json.dumps, 0x1E-joined, sha256) against the hash the program declares (agent_card.json, else AIAP.md).
    Registration only: a mismatch is an advisory anomaly, never a rejection."""
    out = {"algorithm": "canonical_v1.0", "computed": None, "declared": None, "match": None}
    try:
        names = sorted(p.name for p in Path(program_dir).iterdir() if p.is_file() and p.name.endswith(".aisop.json"))
        chunks = []
        for name in names:
            data = json.loads((Path(program_dir) / name).read_text(encoding="utf-8-sig"))
            chunks.append(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        if chunks:
            out["computed"] = hashlib.sha256(b"\x1e".join(chunks)).hexdigest()
    except (OSError, ValueError):
        out["computed"] = None
    declared = None
    card = Path(program_dir) / "agent_card.json"
    if card.is_file():
        try:
            value = json.loads(card.read_text(encoding="utf-8-sig")).get("governance_hash")
            declared = value if isinstance(value, str) and value else None
        except (OSError, ValueError):
            declared = None
    if declared is None:
        md = Path(program_dir) / "AIAP.md"
        if md.is_file():
            try:
                m = re.search(r'^governance_hash:\s*"?([0-9a-fA-F]{16,64})"?\s*$', md.read_text(encoding="utf-8-sig"), re.M)
                declared = m.group(1).lower() if m else None
            except OSError:
                declared = None
    out["declared"] = declared
    if out["computed"] and declared:
        out["match"] = out["computed"] == declared
    return out


def _evidence_records(cache: dict):
    yield cache
    yield from cache.get("continuations") or []


def _project_evidence(records) -> dict:
    """Pure projection of accepted references, not an execution receipt or a disk revalidation."""
    groups, path_versions, path_scopes = {}, {}, {}
    process, artifacts, sources = [], [], []
    counts = dict(basis="evidence_reference_counts_v1", declared_entries=0, process_references=0,
                  verified_references=0, unique_outputs=0, unique_verified=0, repeated_references=0,
                  unknown_identity_references=0, conflicting_paths=0, cross_scope_reuses=0,
                  physical_business_calls=None)
    for name, visit, cache in records:
        scope = ((cache.get("machine") or {}).get("trace_id"), name, visit)
        for revision, record in enumerate(_evidence_records(cache)):
            payload, machine = record.get("payload") or {}, record.get("machine") or {}
            evidence = payload.get("evidence") or {}
            calls = evidence.get("tool_calls") or []
            counts["declared_entries"] += len(calls)
            for number, call in enumerate(calls):
                if not _is_process_call(call):
                    continue
                counts["process_references"] += 1
                verified = call.get("verified_by") == "engine"
                counts["verified_references"] += int(verified)
                raw_path, digest = call.get("stdout_snapshot") or call.get("stdout_path"), call.get("stdout_sha256")
                known = verified and isinstance(raw_path, str) and bool(raw_path) and bool(_SHA256_RE.fullmatch(digest or ""))
                # normcase follows the running platform; no cross-platform lowercasing or file IO.
                path = os.path.normcase(os.path.normpath(raw_path)) if known else None
                working_path = os.path.normcase(os.path.normpath(call.get('stdout_path') or raw_path)) if known else None
                version = (digest, call.get("stdout_bytes"), call.get("exit_code"))
                key = (scope, working_path, version) if known else (scope, revision, number)
                reference = {"revision": revision, "index": number}
                if key in groups:
                    groups[key]["references"].append(reference)
                    counts["repeated_references"] += 1
                    continue
                item = {"node": name, "visit": visit, "tool": call.get("tool"), "stdout_path": call.get('stdout_path'),
                        "stdout_snapshot": call.get('stdout_snapshot'),
                        "stdout_sha256": digest, "stdout_bytes": call.get("stdout_bytes"), "exit_code": call.get("exit_code"),
                        "verified_by": call.get("verified_by"), "references": [reference], "conflict": False,
                        "cross_scope_reuse": False, "identity_known": known}
                groups[key] = item
                process.append(item)
                if known:
                    if not call.get('stdout_snapshot'):
                        path_versions.setdefault((scope, path), []).append(item)
                    path_scopes.setdefault((scope[0], working_path), {}).setdefault(scope, []).append(item)
                    counts["unique_outputs"] += 1
                    counts["unique_verified"] += 1
                else:
                    counts["unknown_identity_references"] += 1
            for a in machine.get("artifacts") or []:
                artifacts.append({"node": name, "path": a.get("path"), "sha256": a.get("sha256")})
            for s in evidence.get("sources") or []:
                sources.append({"node": name, "url": s.get("url"), "path": s.get('path'), "sha256": s.get('sha256'),
                                "retrieved_at": s.get("retrieved_at"), "title": s.get("title"),
                                "recorded_at": s.get('recorded_at'), 'retrieval_time_basis': s.get('retrieval_time_basis'),
                                "ref": s.get("source_id") or f"S{len(sources) + 1}"})
    for versions in path_versions.values():
        if len(versions) > 1:
            counts["conflicting_paths"] += 1
            for item in versions:
                item["conflict"] = True
    for scopes in path_scopes.values():
        if len(scopes) > 1:
            counts["cross_scope_reuses"] += 1
            for items in scopes.values():
                for item in items:
                    item["cross_scope_reuse"] = True
    return {"counts": counts, "process": process, "artifacts": artifacts, "sources": sources}


def _node_evidence(cache: dict) -> dict:
    return _project_evidence([(cache.get("node"), cache.get("visit", 1), cache)])


def _count_verified(cache: dict) -> int:
    return _node_evidence(cache)["counts"]["verified_references"]


def _count_tool_calls(cache: dict) -> int:
    """alpha.22 (doc 43 §4.4): a node's logical tool calls across its first commit and every continuation."""
    return _node_evidence(cache)["counts"]["declared_entries"]


def _evidence_summary(store, index: dict) -> dict:
    """Walk every committed node cache (top-level and sub frames) and collect process outputs, artifacts and sources."""
    records = []
    for key in index["nodes"]:
        name, _, v = key.partition("@")
        entry = _catalog_entry(index, name)
        if not entry:
            continue
        try:
            cache = store.read_json(_cache_path_for(store, index, entry, int(v[1:]) if v else 1))
        except (RunStoreError, OSError, ValueError):
            continue
        records.append((name, int(v[1:]) if v else 1, cache))
    summary = _project_evidence(records)
    # docs/05SoulRun 87: the all-node-revisions anomaly scope of the same caches, as the execution report counts it
    summary["revision_anomalies"] = evidence_views.revision_anomaly_rows(cache for _, _, cache in records)
    return summary


def _evidence_block_text(store) -> str | None:
    try:
        return (store.public_dir / "evidence.txt").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def _close_evidence(store, index: dict, now: str, ev: dict | None = None, *, preserved_sha256=None) -> None:
    """alpha.22 E7: the final ledger event, the evidence_* accounting counters and the public evidence block.
    Idempotent (an orphan-cache recovery may re-apply the final commit): the final event dedupes on final_answer_sha256."""
    ev = ev if ev is not None else _evidence_summary(store, index)
    degraded = [k.partition("@")[0] for k, v in index["nodes"].items() if v.get("status") == "DEGRADED"]
    final_event = _ledger_append(store, index, {"kind": "final", "at": now, "trace_id": index["trace_id"], "engine_version": ENGINE_VERSION,
                                                "final_answer_sha256": index.get("final_answer_sha256"), "run_state": index["run_state"]})
    events = _read_ledger(store)
    index["accounting"]["evidence_events"] = len(events)
    index["accounting"]["evidence_ledger_sha256"] = final_event["entry_hash"]
    # Review of docs/05SoulRun 87 (C4): counted again after the commit and final ledger events, which add an
    # EVIDENCE_LEDGER_BROKEN record each on a broken chain - the same run index the evidence block counts below.
    index["accounting"]["anomalies_by_code"] = evidence_views.code_counts(index["anomalies_summary"])
    if preserved_sha256:
        if sha256_bytes(store.read_bytes(store.public_dir/'evidence.txt')) != preserved_sha256:
            raise RunStoreError('FINAL_EVIDENCE_CHANGED', 'Preserved evidence block changed during recovery')
        return
    summary = {"nodes_committed": index["accounting"]["nodes_committed"], "node_tracks": _track_counts(index), "process_calls": ev["counts"]["unique_outputs"],
               "process_verified": ev["counts"]["unique_verified"], "evidence_counts": ev["counts"], "artifacts": len(ev["artifacts"]),
               "sources": len(ev["sources"]), "events": len(events), "ledger_sha256": final_event["entry_hash"],
               "anomalies": len(index["anomalies_summary"]), "anomaly_groups": evidence_views.anomaly_view(index['anomalies_summary'])}
    # docs/05SoulRun 87: both anomaly scopes by name, each with its per-code counts; never merged by text, never summed
    summary['anomaly_codes'] = evidence_views.code_counts(index['anomalies_summary'])
    if ev.get('revision_anomalies') is not None:
        summary['revision_anomalies'] = evidence_views.anomaly_view(ev['revision_anomalies'])
        summary['revision_anomaly_codes'] = evidence_views.code_counts(ev['revision_anomalies'])
    summary['protocol_attempts'] = evidence_views.protocol_summary(evidence_views.protocol_attempts(store.cache_dir))
    summary['human_decisions'] = evidence_views.human_decision_summary(_resolved_decision_rows(store, index))
    summary['hsaw'] = _hsaw_report_facts(store, index)   # alpha.87 (doc 193 §6)
    summary['cancelled'] = index.get('cancelled')   # alpha.88 (doc 196 F4')
    summary['independent_budget'] = dispatch_budget.summary(index)
    gov = dict(index["program"].get("governance") or {}, package=index["route"].get("package"))
    block = render.evidence_block(summary=summary, process=ev["process"], artifacts=ev["artifacts"], sources=ev["sources"], governance=gov,
                                  degraded=degraded, user_language=index.get("user_language"))
    store.write_public("evidence.txt", block)


_PROCESS_TOOL_RE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:python_tool_run|python[0-9.]*|bash|sh|zsh|shell|powershell|pwsh|cmd|subprocess|terminal|exec|run_command|execute_command)(?:$|[^a-z0-9])|\.py(?:$|[^a-z0-9])")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROCESS_EXCERPT_MAX = 400


_PROTOCOL_TOOL_RE = re.compile(r"(?i)(?:^|[^a-z0-9_])(?:next_node|node_commit|gate_answer|prepare_cache)\.py(?:$|[^a-z0-9])")


def _is_process_call(call: dict) -> bool:
    """alpha.21 (doc 41 §7.5): a tool_calls entry that ran a process, by its sys_call (sys.run*) or by its tool name.
    The engine's own protocol scripts (next_node / node_commit / gate_answer / prepare_cache) are never process evidence:
    their reads are served by the engine and their commits are the record itself."""
    if str(call.get("sys_call") or "").startswith("sys.run"):
        return True
    tool = str(call.get("tool") or "")
    if _PROTOCOL_TOOL_RE.search(tool):
        return False
    return bool(_PROCESS_TOOL_RE.search(tool))


def _check_process_evidence(store, payload: dict, notes: list | None = None) -> None:
    """alpha.22 (doc 43 §6.1 / doc 44 E1): a process run leaves its stdout in <cache>/_proc/ and the ENGINE hashes it.
    The model names stdout_path (and exit_code, or a .exit file); stdout_sha256 / stdout_bytes / stdout_excerpt are
    engine-derived and verified_by is set to "engine". alpha.99 (04 series doc 239 P1): a process call without a usable capture is
    recorded (PROCESS_CAPTURE_MISSING - its stdout_path is dropped, so nothing can address it), an exit code nobody knows is recorded
    (PROCESS_EXIT_UNKNOWN), and a self-report that contradicts the file is replaced by the file's value (PROCESS_SELF_REPORT_CORRECTED) -
    never refused; the engine never took the self-report as evidence (production cache/16)."""
    proc_dir = store.proc_dir.resolve()
    missing, unknown, corrected = [], [], []
    for i, call in enumerate(payload["evidence"]["tool_calls"]):
        if 'stdout_snapshot' in call:
            raise EngineError('EVIDENCE_SNAPSHOT_INVALID', 'stdout_snapshot is machine-owned',
                              field=f'evidence.tool_calls[{i}].stdout_snapshot')
        if not _is_process_call(call):
            continue
        field = f"evidence.tool_calls[{i}]"
        rel = call.get("stdout_path")
        path = (store.cache_dir / rel).resolve() if isinstance(rel, str) and _STDOUT_PATH_RE.fullmatch(rel) else None
        if path is None or path.parent != proc_dir or not path.is_file() or path.stat().st_size > PROC_MAX_BYTES:
            missing.append(f"{field} {call.get('tool')!r}" + (f" ({rel})" if rel else ""))
            for key in ("stdout_path", "stdout_sha256", "stdout_bytes", "stdout_excerpt", "verified_by"):
                call.pop(key, None)
            code = call.get("exit_code")
            if code is not None and (not isinstance(code, int) or isinstance(code, bool)):
                call.pop("exit_code")
            continue
        data = path.read_bytes()
        sha = sha256_bytes(data)
        if call.get("stdout_sha256") is not None and call["stdout_sha256"] != sha:
            corrected.append(f"{field}.stdout_sha256")
        exit_path = path.with_suffix(".exit")
        file_exit = None
        if exit_path.is_file():
            try:
                file_exit = int(exit_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                file_exit = None
        code = call.get("exit_code")
        if code is not None and (not isinstance(code, int) or isinstance(code, bool)):
            corrected.append(f"{field}.exit_code {code!r}")
            code = None
        if file_exit is not None and code is not None and code != file_exit:
            corrected.append(f"{field}.exit_code {code} -> {file_exit}")
            code = file_exit
        if code is None and file_exit is None:
            unknown.append(f"{field} {call.get('tool')!r}")
            call.pop("exit_code", None)
        else:
            call["exit_code"] = code if code is not None else file_exit
        call["stdout_sha256"] = sha
        call["stdout_bytes"] = len(data)
        call["stdout_excerpt"] = data[: PROCESS_EXCERPT_MAX * 4].decode("utf-8", errors="replace")[:PROCESS_EXCERPT_MAX]
        call["verified_by"] = "engine"
        call['stdout_snapshot'] = seal_process_output(store.cache_dir, data)
    if notes is not None:
        if missing:
            notes.append({"code": "PROCESS_CAPTURE_MISSING", "text": f"{missing}: a process ran without a stdout file under _proc/ - recorded, not evidence "
                                                                     "(alpha.99); redirect stdout to _proc/<node>.<n>.out"})
        if unknown:
            notes.append({"code": "PROCESS_EXIT_UNKNOWN", "text": f"{unknown}: exit code neither given nor in a .exit file - recorded (alpha.99)"})
        if corrected:
            notes.append({"code": "PROCESS_SELF_REPORT_CORRECTED", "text": f"{corrected}: the file's value is kept (alpha.99)"})

_ADDRESS_TARGET_RE = re.compile(r"^(proc|input|artifact|host|work|evidence):([^#]+?)(?:#(.+))?$")   # alpha.63: + work:<file under _work/>; alpha.64: + evidence:sources
_WORK_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")   # alpha.63: top-level keys an auto-converted address may select with #key
_HOST_TARGET_RE = re.compile(r"^(report|explain|message\[([0-9]+)\])$")
_INPUT_OCCURRENCE_RE = re.compile(r"^(.+)@([0-9]+)$")
_JSON_PATH_STEP_RE = re.compile(r"\[[0-9]+\]|[^.\[\]]+")
_ADDRESS_FIELDS = ("output", "vars", "user_summary", "user_messages")


def _address_markers(value, at: str, found: list, parent=None, key=None) -> None:
    """Every {"@ref": ...} object inside `value`, depth first, as (path, marker, parent, key); a marker's own keys are not descended."""
    if isinstance(value, dict):
        if ADDRESS_REF_KEY in value:
            found.append((at, value, parent, key))
            return
        for k, v in value.items():
            _address_markers(v, f"{at}.{k}", found, value, k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _address_markers(v, f"{at}[{i}]", found, value, i)


def _json_path_select(value, steps, at: str):
    """`#a.b[2].c` on a parsed JSON value (steps: the path string or its step list); a step that does not resolve is REF_TARGET_INVALID."""
    if isinstance(steps, str):
        steps = _JSON_PATH_STEP_RE.findall(steps)
    for step in steps:
        if step.startswith("["):
            i = int(step[1:-1])
            if not isinstance(value, list) or i >= len(value):
                raise EngineError("REF_TARGET_INVALID", f"#{'.'.join(steps)}: index {i} is outside the referenced list", field=at, expected="an index inside the referenced list")
            value = value[i]
        elif not isinstance(value, dict) or step not in value:
            raise EngineError("REF_TARGET_INVALID", f"#{'.'.join(steps)}: key {step!r} is not in the referenced JSON", field=at,
                              expected=(sorted(str(k)[:60] for k in value)[:30] if isinstance(value, dict)   # alpha.68: name the keys that do exist
                                        else "a key of the referenced object - the value at this step is not an object"))
        else:
            value = value[step]
    return value


def _address_summary(value, is_json: bool) -> dict:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return {"json": is_json, "chars": len(text), "preview": text[:ADDRESS_REF_PREVIEW]}


def _decode_capture(data: bytes, want_json: bool, at: str, what: str):
    """The referenced bytes as JSON when they parse, else as text (a #path needs JSON). Returns (value, is_json)."""
    text = data.decode("utf-8", errors="replace")
    try:
        return strict_loads(text), True
    except ValueError:
        if want_json:
            raise EngineError("REF_TARGET_INVALID", f"{what} is not JSON, so a #path cannot be selected in it", field=at, expected="a JSON file, or an address without #path") from None
        return text, False


def _payload_at_revision(cache: dict, revision: int) -> dict:
    return (cache["continuations"][revision - 1] if revision else cache)["payload"]


def _resolve_address_target(store: RunStore, index: dict, payload: dict, target, at: str, ctx: dict) -> tuple[dict, object]:
    """One address -> (its engine record, the content it names). ctx caches this payload's captures / artifacts / prior caches."""
    m = _ADDRESS_TARGET_RE.match(target) if isinstance(target, str) else None
    if not m:
        raise EngineError("REF_TARGET_INVALID", f"{target!r} is not proc:<stdout_path>[#path], input:<node>@<visit>[#field.path], artifact:<n>[#path], "
                          "host:report | host:message[<n>] | host:explain, work:<file>[#path] or evidence:sources", field=at,
                          expected="proc:_proc/<node>.<n>.out[#path] | input:<node>@<visit>[#output.path] | artifact:<n>[#path] | host:report | host:message[0] | host:explain | work:<file> | evidence:sources")
    kind, where, sub = m.group(1), m.group(2), m.group(3)
    if kind == "proc":
        if where not in ctx["captures"]:
            raise EngineError("REF_TARGET_INVALID", f"{where} is not a stdout_path of this payload's tool_calls", field=at, expected=ctx["captures"])
        call = next(c for c in payload['evidence']['tool_calls'] if c.get('stdout_path') == where)
        capture = call.get('stdout_snapshot') or where
        path = (store.cache_dir / capture).resolve()
        if path.parent != store.proc_dir.resolve():
            raise EngineError('REF_TARGET_INVALID', 'capture escapes _proc', field=at)
        data = path.read_bytes()
        if call.get('stdout_snapshot') and sha256_bytes(data) != call.get('stdout_sha256'):
            raise EngineError('REF_TARGET_INVALID', 'sealed stdout changed after validation', field=at)
        value, is_json = _decode_capture(data, sub is not None, at, where)
        selected = _json_path_select(value, sub, at) if sub else value
        resolved = {"kind": "proc", "path": capture, "sha256": sha256_bytes(data), "bytes": len(data), **_address_summary(selected, is_json)}
    elif kind == "input":
        from . import blind_review
        review = blind_review.active(store, index)
        om = _INPUT_OCCURRENCE_RE.match(where)
        if ctx.get("prev") is None:
            ctx["prev"] = _prev_business_caches(store, index)
        cache = next((c for c in ctx["prev"] if om and c["node"] == om.group(1) and c["visit"] == int(om.group(2))), None)
        if cache is None:
            raise EngineError("REF_TARGET_INVALID", f"{where} is not a committed business occurrence of this run", field=at,
                              expected=[f"{c['node']}@{c['visit']}" for c in ctx["prev"]])
        if review and not blind_review.owns(cache, review):
            raise EngineError('REF_TARGET_INVALID', 'Blind review cannot dereference Writer inputs.', field=at)
        from . import independent_inputs
        scoped = independent_inputs.active(store, index)
        selected = (sub or '').partition('.')
        if scoped and not independent_inputs.allows(scoped, cache, selected[0], selected[2]):
            raise EngineError('REF_TARGET_INVALID', 'Input address exceeds the declared field projection.', field=at)
        record = (cache.get('continuations') or [cache])[-1]
        review_status = None
        machine = record.get('machine') or {}
        if machine.get('review_binding'):
            review_status = blind_review.observe(store, machine['review_binding'],
                (machine.get('dispatch') or {}).get('scope_root') or dict(node=cache['node'], visit=cache['visit']))
        steps = _JSON_PATH_STEP_RE.findall(sub or "output")
        if not steps or steps[0] not in _ADDRESS_FIELDS:
            raise EngineError("REF_TARGET_INVALID", f"#{sub}: field must be output|vars|user_summary|user_messages", field=at,
                              expected="#output[.path] | #vars[.path] | #user_summary | #user_messages[n]")
        src = _latest_payload(cache)
        selected = _json_path_select(src.get(steps[0]), steps[1:], at)
        cache_path = _cache_path_for(store, index, _catalog_entry(index, cache["node"]), cache["visit"])
        resolved = {"kind": "input", "node": cache["node"], "visit": cache["visit"], "revision": len(cache.get("continuations") or []),
                    "field": steps[0], "cache": cache_path.resolve().relative_to(store.cache_dir.resolve()).as_posix(),
                    "sha256": index["nodes"][_node_key(cache["node"], cache["visit"])]["cache_sha256"],
                    **_address_summary(selected, not isinstance(selected, str)),
                    **(dict(review_binding_status=review_status) if review_status else {})}
    elif kind == "artifact":
        artifacts = ctx["artifacts"]
        try:
            n = int(where)
            art = artifacts[n]
        except (ValueError, IndexError):
            raise EngineError("REF_TARGET_INVALID", f"artifact:{where} is not an index of this payload's evidence.artifacts ({len(artifacts)} items)", field=at,
                              expected=f"artifact:0..{len(artifacts) - 1}" if artifacts else "an evidence.artifacts entry to address") from None
        path = Path(art["path"])   # existence was checked by _check_artifacts
        if not path.is_file():
            raise EngineError("REF_TARGET_INVALID", f"artifact:{n} ({art['path']}) is not a file", field=at, expected="a file artifact")
        if path.stat().st_size > PROC_MAX_BYTES:
            raise EngineError("REF_TARGET_INVALID", f"artifact:{n} is larger than {PROC_MAX_BYTES} bytes", field=at, expected="a smaller file, or inline a summary")
        data = path.read_bytes()
        value, is_json = _decode_capture(data, sub is not None, at, art["path"])
        selected = _json_path_select(value, sub, at) if sub else value
        resolved = {"kind": "artifact", "index": n, "path": str(path), "sha256": sha256_bytes(data), "bytes": len(data), **_address_summary(selected, is_json)}
    elif kind == "evidence":   # alpha.64 (doc 140 §2 #2): the run's evidence ledger - every source recorded so far, this payload's included
        if where != "sources" or sub is not None:
            raise EngineError("REF_TARGET_INVALID", f"evidence:{where}{'#' + sub if sub else ''}: the only evidence address is evidence:sources, without a #path",
                              field=at, expected="evidence:sources")
        select = ctx.pop("select", None)
        entries = _ledger_source_entries(store, payload, dedupe=select is None)
        if select is not None:   # an auto-converted projection names exactly the entries it matched
            by_where = {_canon_json(e["where"]): e for e in entries}
            picked = [by_where.get(_canon_json(w)) for w in select]
            if any(p is None for p in picked):
                raise EngineError("REF_TARGET_INVALID", "evidence:sources: the selection names entries that are not in this run's ledger", field=at,
                                  expected="ledger coordinates issued by the engine")
            entries = picked
        if not entries:
            raise EngineError("REF_TARGET_INVALID", "evidence:sources: this run has recorded no sources yet", field=at,
                              expected="an evidence.sources entry in this or an earlier commit of the run")
        selected = [e["source"] for e in entries]
        resolved = {"kind": "evidence", "path": "_evidence.json", "selection": [e["where"] for e in entries], "count": len(entries),
                    "sha256": sha256_bytes(_canon_json(selected).encode("utf-8")), **_address_summary(selected, True)}
    elif kind == "work":   # alpha.63 (doc 137 §6.4): a value the model wrote under _work/ because it existed nowhere else
        rel = where.strip().replace("\\", "/")
        if rel.startswith("_work/"):
            rel = rel[len("_work/"):]
        work_root = (store.cache_dir / "_work").resolve()
        path = (work_root / rel).resolve() if rel else work_root
        if not rel or ".." in rel.split("/") or not path.is_relative_to(work_root) or not path.is_file():
            raise EngineError("REF_TARGET_INVALID", f"work:{where} is not a file under _work/ of this run's cache", field=at,
                              expected="work:<file you wrote under <cache_dir>/_work/>")
        if path.stat().st_size > PROC_MAX_BYTES:
            raise EngineError("REF_TARGET_INVALID", f"work:{rel} is larger than {PROC_MAX_BYTES} bytes", field=at, expected="a smaller file, or inline a summary")
        data = path.read_bytes()
        value, is_json = _decode_capture(data, sub is not None, at, f"_work/{rel}")
        selected = _json_path_select(value, sub, at) if sub else value
        resolved = {"kind": "work", "path": f"_work/{rel}", "sha256": sha256_bytes(data), "bytes": len(data), **_address_summary(selected, is_json)}
    else:   # alpha.58 B7 (doc 125 §4): this node's own streamed text, already resolved into the payload; no preview - it is in the same cache
        if ctx.get("sub_agent"):   # alpha.62 (doc 135 G1)
            raise EngineError("REF_TARGET_INVALID", f"host:{where}: host: addresses are unavailable to a sub-agent (its stream is not captured); inline the text",
                              field=at, expected="proc: | input: | artifact: | work: | evidence: or the inline value")
        hm = _HOST_TARGET_RE.match(where)
        if not hm or sub is not None:
            raise EngineError("REF_TARGET_INVALID", f"host:{where}{'#' + sub if sub else ''}: use host:report, host:message[<n>] or host:explain, without a #path",
                              field=at, expected="host:report | host:message[0] | host:explain")
        if where == "report":
            field, text = "user_summary", payload.get("user_summary")
        elif where == "explain":
            field, text = "explain", payload.get("explain")
        else:
            n = int(hm.group(2))
            msgs = payload.get("user_messages") or []
            fences = ctx.get("host_fences") or []
            if n >= len(msgs) and n < len(fences):   # alpha.99 (doc 239 P5; production 10 / 11 / 13): the n-th streamed fence
                field, text = f"user_messages[0] fence {n}", fences[n]
                ctx.setdefault("repairs", []).append(f"host:message[{n}] -> streamed fence {n} of {len(fences)}")
            elif n >= len(msgs) and msgs:   # alpha.99: no such fence - the whole streamed User Message
                field, text = f"user_messages[{len(msgs) - 1}]", msgs[-1]
                ctx.setdefault("repairs", []).append(f"host:message[{n}] -> the whole User Message ({len(msgs)} message(s), {len(fences)} fence(s))")
            elif n >= len(msgs):
                raise EngineError("REF_TARGET_INVALID", f"host:message[{n}]: this payload has {len(msgs)} user_messages", field=at,
                                  expected=f"host:message[0..{len(msgs) - 1}]" if msgs else
                                  f"this occurrence's User Message captured in {host_text_name('message', payload['node'])} before commit: "
                                  f"stream :::message {payload['node']} then close it with :::, or put the complete original text inline in user_messages; "
                                  "do not replace it with the Report or repeat a completed business action")
            else:
                field, text = f"user_messages[{n}]", msgs[n]
        if not isinstance(text, str) or not text.strip() or text.strip() == "@host":
            raise EngineError("REF_TARGET_INVALID", f"host:{where}: this node's {field} is empty", field=at, expected="the streamed text in that field")
        selected = text
        resolved = {"kind": "host", "field": field, "sha256": sha256_bytes(text.encode("utf-8")), "chars": len(text)}
    resolved["by"] = "engine"
    resolved["resolved_at"] = ctx["resolved_at"]
    return resolved, selected


def _address_ctx(payload: dict) -> dict:
    return {"captures": sorted({c.get("stdout_path") for c in payload["evidence"]["tool_calls"] if isinstance(c, dict) and c.get("stdout_path")}),
            "artifacts": payload["evidence"]["artifacts"], "prev": None, "resolved_at": now_iso()}


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _canon_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _value_size(value) -> int:
    return len(value) if isinstance(value, str) else len(json.dumps(value, ensure_ascii=False))


def _ledger_source_entries(store: RunStore, payload: dict | None, *, dedupe: bool = True) -> list[dict]:
    """alpha.64 (doc 140 §2 #2): every source this run has recorded - the ledger's events in order, then this payload's own
    evidence.sources (its event is appended after the commit) - as {"where": {"seq", "i"} | {"own": True, "i"}, "source": <ledger
    projection>}. dedupe keeps one entry per url / path, the latest wins."""
    rows: list[dict] = []
    for event in _read_ledger(store):
        if not isinstance(event, dict) or not isinstance(event.get("sequence"), int):
            continue
        for i, s in enumerate(event.get("sources") or []):
            if isinstance(s, dict) and (s.get("url") or s.get("path")):
                rows.append({"where": {"seq": event["sequence"], "i": i}, "source": s})
    for i, s in enumerate(_ledger_sources(payload) if payload else []):
        if s.get("url") or s.get("path"):
            rows.append({"where": {"own": True, "i": i}, "source": s})
    if not dedupe:
        return rows
    latest: dict[str, dict] = {}
    for row in rows:
        latest[str(row["source"].get("url") or row["source"].get("path"))] = row
    return list(latest.values())


def _evidence_projection(entries: list[dict], items: list) -> list | None:
    """alpha.64: `items` is a field-projection of recorded sources when every item is an object with a url / path whose every key
    and value are those of some ledger entry (the latest such entry wins); returns the matched coordinates in item order, else None."""
    selection = []
    for item in items:
        if not isinstance(item, dict) or not (item.get("url") or item.get("path")):
            return None
        match = next((e for e in reversed(entries) if all(k in e["source"] and e["source"][k] == v for k, v in item.items())), None)
        if match is None:
            return None
        selection.append(match["where"])
    return selection


def _evidence_selection(store: RunStore, payload: dict | None, resolved: dict, at: str) -> list:
    """alpha.64 read side: the entries an evidence:sources address selected, rebuilt from the ledger (and this record's own
    evidence.sources) and verified as a whole against the sha256 recorded at commit."""
    events = _read_ledger(store)
    own = _ledger_sources(payload) if payload else None
    out = []
    for where in resolved.get("selection") or []:
        if isinstance(where, dict) and where.get("own"):
            if own is None or not isinstance(where.get("i"), int) or not 0 <= where["i"] < len(own):
                raise EngineError("REF_TARGET_INVALID", "evidence:sources: this record's own sources are not readable", field=at, expected=resolved.get("sha256"))
            out.append(own[where["i"]])
            continue
        seq, i = (where.get("seq"), where.get("i")) if isinstance(where, dict) else (None, None)
        event = events[seq - 1] if isinstance(seq, int) and 0 < seq <= len(events) else None
        sources = event.get("sources") if isinstance(event, dict) and event.get("sequence") == seq else None
        if not isinstance(sources, list) or not isinstance(i, int) or not 0 <= i < len(sources):
            raise EngineError("REF_TARGET_INVALID", f"evidence:sources: ledger entry {where} is missing", field=at, expected=resolved.get("sha256"))
        out.append(sources[i])
    if sha256_bytes(_canon_json(out).encode("utf-8")) != resolved.get("sha256"):
        raise EngineError("REF_TARGET_INVALID", "evidence:sources: the ledger changed since the commit that addressed it", field=at, expected=resolved.get("sha256"))
    return out


def _compact_resolution(marker: dict, resolved: dict, selected) -> dict:
    """alpha.64 (doc 140 §2 #1): a resolved value under ADDRESS_INLINE_LIMIT characters rides beside its address as @value and its
    @resolved keeps kind / identity / sha256 / by / resolved_at (no preview, size or shape) - readers take the value without
    dereferencing. host: targets already live in the same payload; larger values keep the preview and are dereferenced on read."""
    chars = resolved.get("chars")
    if resolved.get("kind") == "host" or not isinstance(chars, int) or chars >= ADDRESS_INLINE_LIMIT:
        return resolved
    marker[ADDRESS_REF_VALUE] = selected
    if chars < ADDRESS_TINY_LIMIT and resolved.get("kind") != "input":   # selected input reads still need their source/revision identity
        return {k: v for k, v in resolved.items() if k in ('kind', 'review_binding_status')}
    return {k: v for k, v in resolved.items() if k not in ("preview", "chars", "json", "bytes")}


def _auto_address_candidates(store: RunStore, payload: dict, sub_agent: bool) -> list[tuple[str, str, str]]:
    """alpha.63 L2: every text and JSON value an output value may be a verbatim copy of, as (address, form, canonical): this node's
    streamed texts (never for a sub-agent - host: is unavailable there), each captured stdout (whole text, whole JSON, each top-level
    key that is a structure) and each artifact file (the same three shapes)."""
    cands: list[tuple[str, str, str]] = []
    if not sub_agent:
        if isinstance(payload.get("user_summary"), str):
            cands.append(("host:report", "text", _normalized_text(payload["user_summary"])))
        for n, message in enumerate(payload.get("user_messages") or []):
            if isinstance(message, str):
                cands.append((f"host:message[{n}]", "text", _normalized_text(message)))
        if isinstance(payload.get("explain"), str):
            cands.append(("host:explain", "text", _normalized_text(payload["explain"])))

    def add_file(address: str, path: Path) -> None:
        try:
            if not path.is_file() or path.stat().st_size > PROC_MAX_BYTES:
                return
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return
        cands.append((address, "text", _normalized_text(text)))
        try:
            parsed = strict_loads(text)
        except ValueError:
            return
        cands.append((address, "json", _canon_json(parsed)))
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                if isinstance(v, (dict, list)) and _WORK_KEY_RE.match(str(k)):
                    cands.append((f"{address}#{k}", "json", _canon_json(v)))

    for call in payload["evidence"]["tool_calls"]:
        stdout_path = call.get("stdout_path") if isinstance(call, dict) else None
        if stdout_path:
            add_file(f"proc:{stdout_path}", store.cache_dir / (call.get('stdout_snapshot') or stdout_path))
    for n, art in enumerate(payload["evidence"]["artifacts"]):
        if isinstance(art, dict) and art.get("path"):
            add_file(f"artifact:{n}", Path(art["path"]))
    return cands


def _auto_address_output(store: RunStore, payload: dict, notes: list | None, sub_agent: bool) -> dict:
    """alpha.63 L2 (doc 137 §3): an output value of ADDRESS_AUTO_MIN+ characters that is a verbatim copy of an existing text
    (whitespace-normalised) or of an existing JSON value becomes that address - the outermost matching value, never inside an address;
    recorded as ADDRESS_AUTO_CONVERTED. Verbatim keys (the user's words, human_decisions, user_*) are never touched."""
    output = payload.get("output")
    if not isinstance(output, dict) or not output:
        return payload
    cands: list | None = None
    ev_entries: list | None = None   # alpha.64: the run's recorded sources, lazily
    converted: list[tuple[str, str, int]] = []
    out = json.loads(json.dumps(payload, ensure_ascii=False))

    def visit(container, key, value, path: str) -> None:
        nonlocal cands, ev_entries
        if isinstance(value, dict) and ADDRESS_REF_KEY in value:
            return
        size = _value_size(value)
        if size < ADDRESS_AUTO_MIN:
            return
        nested = []
        _address_markers(value, path, nested)
        if nested:
            # A raw capture cannot carry the Engine companions for its child references.
            # Keep the container so the normal resolver validates and seals each child.
            if isinstance(value, dict):
                for k, v in list(value.items()):
                    visit(value, k, v, f"{path}.{k}")
            elif isinstance(value, list):
                for i, v in enumerate(list(value)):
                    visit(value, i, v, f"{path}[{i}]")
            return
        if cands is None:
            cands = _auto_address_candidates(store, payload, sub_agent)
        if isinstance(value, str):
            norm = _normalized_text(value)
            for address, form, canonical in cands:
                if form == "text" and canonical == norm:
                    container[key] = {ADDRESS_REF_KEY: address}
                    converted.append((path, address, size))
                    return
            return
        if isinstance(value, list) and value and all(isinstance(x, dict) and ADDRESS_REF_KEY not in x for x in value):   # alpha.64 (doc 140 §2 #2)
            if ev_entries is None:
                ev_entries = _ledger_source_entries(store, payload, dedupe=False)
            selection = _evidence_projection(ev_entries, value)
            if selection is not None:
                container[key] = {ADDRESS_REF_KEY: "evidence:sources", ADDRESS_REF_SELECT: selection}
                converted.append((path, "evidence:sources", size))
                return
        canon = _canon_json(value)
        for address, form, canonical in cands:
            if form == "json" and canonical == canon:
                container[key] = {ADDRESS_REF_KEY: address}
                converted.append((path, address, size))
                return
        if isinstance(value, dict):
            for k, v in list(value.items()):
                visit(value, k, v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(list(value)):
                visit(value, i, v, f"{path}[{i}]")

    for k, v in list(out["output"].items()):
        if k in _OUTPUT_VERBATIM_KEYS or str(k).startswith("user_"):
            continue
        visit(out["output"], k, v, f"output.{k}")
    if not converted:
        return payload
    if notes is not None:
        notes.append({"code": "ADDRESS_AUTO_CONVERTED",
                      "text": "; ".join(f"{p} ({n} chars) -> {a}" for p, a, n in converted)
                              + " (alpha.63: a verbatim copy of an existing text or value is stored as its address; readers dereference it)"})
    return out


def _note_inline_over_limit(payload: dict, notes: list | None) -> None:
    """alpha.64 (doc 140 §2 #3): a large top-level output value that exists in no file is recorded as a hint - strings from
    ADDRESS_INLINE_LIMIT, objects and lists from ADDRESS_INLINE_LIMIT_STRUCTURED characters - never rejected. Addresses, the user's
    words and user_* keys are not measured."""
    output = payload.get("output")
    if notes is None or not isinstance(output, dict):
        return
    over = []
    for k, v in output.items():
        if (isinstance(v, dict) and ADDRESS_REF_KEY in v) or k in _OUTPUT_VERBATIM_KEYS or str(k).startswith("user_"):
            continue
        size = _value_size(v)
        if size >= (ADDRESS_INLINE_LIMIT if isinstance(v, str) else ADDRESS_INLINE_LIMIT_STRUCTURED):
            over.append((k, size))
    if over:
        notes.append({"code": "OUTPUT_VALUE_INLINE_OVER_LIMIT",
                      "text": "large inline output values with no file yet: " + ", ".join(f"{k} ({n})" for k, n in over)
                              + f" (alpha.64: strings of {ADDRESS_INLINE_LIMIT}+ / structures of {ADDRESS_INLINE_LIMIT_STRUCTURED}+ characters - writing such "
                                "a value under _work/ and addressing it as work:<file> is encouraged, and a value that already exists in a file is its "
                                "address; a hint, never a rejection)"})


def _resolve_address_refs(store: RunStore, index: dict, payload: dict, *, sub_agent: bool = False, notes: list | None = None) -> dict:
    """alpha.57 (doc 121 §8.5 / doc 122) + alpha.58 host: (doc 125 §4): an address {"@ref": "proc:…" | "input:…" | "artifact:…" | "host:…"}
    inside output names content that already exists - this payload's captured stdout, a committed occurrence of this run, a file this
    payload lists as an artifact, or this node's own streamed text. The engine verifies the target, records kind / sha256 / size (and a
    300-character preview, none for host:) under "@resolved" and stores the address, never a copy; read_input hands readers the content.
    output itself is never an address (its keys are the package contract), and an address changes only the payload: whatever a program
    step requires on disk is produced by the program as declared (doc 121 §9)."""
    output = payload.get("output")
    if isinstance(output, dict) and ADDRESS_REF_KEY in output:
        raise EngineError("REF_TARGET_INVALID", "output itself is never an address; keep its keys and address single values", field="output",
                          expected="an object whose values may be addresses")
    submitted: list = []
    _address_markers(output, "output", submitted)
    for _at, marker, _parent, _key in submitted:
        for extra in (ADDRESS_REF_VALUE, ADDRESS_REF_SELECT):
            marker.pop(extra, None)   # alpha.64: the engine is the only author of @value and @select
    payload = _auto_address_output(store, payload, notes, sub_agent)   # alpha.63 L2: verbatim copies become addresses first
    output = payload.get("output")
    found: list = []
    _address_markers(output, "output", found)
    if not found:
        _note_inline_over_limit(payload, notes)
        return payload
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    found = []
    _address_markers(out["output"], "output", found)
    ctx = _address_ctx(payload)
    ctx["sub_agent"] = sub_agent   # alpha.62: host: addresses are unavailable to a sub-agent (doc 135 G1)
    ctx["host_fences"] = _host_fences(store, index) if not sub_agent else []   # alpha.99 (doc 239 P5)
    failures = []
    for at, marker, _parent, _key in found:
        ctx["select"] = marker.pop(ADDRESS_REF_SELECT, None)   # alpha.64: an auto-converted evidence:sources names the entries it matched
        try:
            resolved, selected = _resolve_address_target(store, index, payload, marker.get(ADDRESS_REF_KEY), at, ctx)
        except EngineError as exc:
            if exc.code != "REF_TARGET_INVALID":
                raise
            failures.append(exc)
            continue
        marker[ADDRESS_REF_RESOLVED] = _compact_resolution(marker, resolved, selected)   # a submitted @resolved is overwritten: the engine is its only author
        if notes is not None and resolved.get('review_binding_status'):
            from . import blind_review
            notes.extend(blind_review.anomalies([resolved['review_binding_status']]))
        if " fence " in str(resolved.get("field") or ""):   # alpha.99 (doc 239 P5): a fence is no payload field - its text rides with the address
            marker[ADDRESS_REF_VALUE] = selected
    if failures:
        first = failures[0]
        first.errors.extend(error.as_dict() for error in failures[1:])
        raise first
    if ctx.get("repairs") and notes is not None:
        notes.append({"code": "HOST_FENCE_RESOLVED", "text": "; ".join(ctx["repairs"]) + " (alpha.99: host:message[n] counts this node's streamed fences)"})
    _note_inline_over_limit(out, notes)
    return out


_ENGINE_SOURCE_KEYS = ("recorded_at", "retrieval_time_basis", "bytes", "verification_scope")


def _resolve_sources_address(store: RunStore, index: dict, payload: dict, notes: list | None = None) -> dict:
    """alpha.58 B6 (doc 124 P2): evidence.sources given as one address (artifact:<n>[#path] | proc:<stdout_path>[#path]) to the source list
    a script persisted. The engine selects the list, validates it like typed sources (schema here, URL shape in _check_sources), stores the
    list - renderers, the ledger and the counts read it - and keeps the address beside it as evidence.sources_address."""
    ev = payload.get("evidence") or {}
    marker = ev.get("sources_address")
    if not isinstance(marker, dict):
        return payload
    at = "evidence.sources"
    target = marker.get(ADDRESS_REF_KEY)
    if target == "evidence:sources":   # alpha.99 (doc 239 S13; production 17, isolated 64): the run's evidence ledger is the list meant
        selected = [{k: v for k, v in e["source"].items() if k not in _ENGINE_SOURCE_KEYS} for e in _ledger_source_entries(store, None)]
        out = json.loads(json.dumps(payload, ensure_ascii=False))
        out["evidence"]["sources"] = selected
        out["evidence"]["sources_address"] = dict(marker, **{ADDRESS_REF_RESOLVED: {"kind": "evidence", "count": len(selected), "by": "engine"}})
        if notes is not None:
            notes.append({"code": "SOURCES_FROM_LEDGER", "text": f"evidence.sources was the address evidence:sources: the {len(selected)} source(s) this run recorded "
                                                                 "before this commit were taken (alpha.99) - add this node's own sources inline"})
        return out
    if not isinstance(target, str) or not target.startswith(("artifact:", "proc:")):
        raise EngineError("REF_TARGET_INVALID", f"evidence.sources address must be artifact:<n>[#path] or proc:<stdout_path>[#path], not {target!r}",
                          field=at, expected="artifact:<n>#sources")
    resolved, selected = _resolve_address_target(store, index, payload, target, at, _address_ctx(payload))
    if not isinstance(selected, list) or not all(isinstance(s, dict) for s in selected):
        raise EngineError("REF_TARGET_INVALID", f"{target} selects {type(selected).__name__}, not a list of source objects", field=at,
                          expected="a JSON list of {url, retrieved_at} / {path} objects")
    schema = commit_schema()
    errors = schema_lite.validate(selected, schema["$defs"]["evidence"]["properties"]["sources"], schema, at)
    if errors:
        first = errors[0]
        raise EngineError("REF_TARGET_INVALID", f"{target}: {first['message']} at {first['field']}", field=first["field"], expected=first.get("expected"))
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    out["evidence"]["sources"] = selected
    out["evidence"]["sources_address"] = dict(marker, **{ADDRESS_REF_RESOLVED: resolved})
    return out


def _deref_address_refs(store: RunStore, value, payload: dict | None = None):
    """alpha.57 read side: every resolved address inside an output read is replaced by the content it names. A capture that changed since
    the commit is refused (REF_TARGET_INVALID); an artifact that changed or vanished on disk stays an address carrying "@deref_error";
    a host: address reads the same payload's streamed text (alpha.58)."""
    found: list = []
    _address_markers(value, "output", found)
    if not found:
        return value
    out = json.loads(json.dumps(value, ensure_ascii=False))
    found = []
    _address_markers(out, "output", found)
    for at, marker, parent, key in found:
        resolved = marker.get(ADDRESS_REF_RESOLVED)
        m = _ADDRESS_TARGET_RE.match(marker.get(ADDRESS_REF_KEY)) if isinstance(marker.get(ADDRESS_REF_KEY), str) else None
        if parent is None or not isinstance(resolved, dict) or not m:
            continue   # never written by the engine: stays as it is
        if ADDRESS_REF_VALUE in marker:   # alpha.64: a small value rides with its address - no file is read
            parent[key] = marker[ADDRESS_REF_VALUE]
            continue
        kind, sub = m.group(1), m.group(3)
        if kind == "proc":
            path = (store.cache_dir / resolved["path"]).resolve()
            data = path.read_bytes() if path.is_relative_to(store.cache_dir.resolve()) and path.is_file() else None
            if data is None or sha256_bytes(data) != resolved["sha256"]:
                raise EngineError("REF_TARGET_INVALID", f"{resolved['path']} changed or vanished since the commit that addressed it", field=at, expected=resolved["sha256"])
            content, _ = _decode_capture(data, sub is not None, at, resolved["path"])
            parent[key] = _json_path_select(content, sub, at) if sub else content
        elif kind == "input":
            path = (store.cache_dir / resolved["cache"]).resolve()
            if not path.is_relative_to(store.cache_dir.resolve()) or not path.is_file():
                raise EngineError("REF_TARGET_INVALID", f"{resolved['cache']} vanished since the commit that addressed it", field=at, expected="the occurrence cache")
            src = _payload_at_revision(strict_loads(path.read_text(encoding="utf-8")), resolved["revision"])
            steps = _JSON_PATH_STEP_RE.findall(sub or "output")
            parent[key] = _json_path_select(src.get(steps[0]), steps[1:], at)
        elif kind == "work":   # alpha.63: like proc - the file must be unchanged since the commit
            path = (store.cache_dir / resolved["path"]).resolve()
            data = path.read_bytes() if path.is_relative_to(store.cache_dir.resolve()) and path.is_file() else None
            if data is None or sha256_bytes(data) != resolved["sha256"]:
                raise EngineError("REF_TARGET_INVALID", f"{resolved['path']} changed or vanished since the commit that addressed it", field=at, expected=resolved["sha256"])
            content, _ = _decode_capture(data, sub is not None, at, resolved["path"])
            parent[key] = _json_path_select(content, sub, at) if sub else content
        elif kind == "evidence":   # alpha.64: the selected ledger entries, rebuilt and verified as a whole
            parent[key] = _evidence_selection(store, payload, resolved, at)
        elif kind == "host":
            field = str(resolved.get("field") or "")
            index_match = re.match(r"user_messages\[(\d+)\]$", field)   # alpha.99: a fence reference carries its text as @value
            if index_match and payload is not None:
                msgs = payload.get("user_messages") or []
                n = int(index_match.group(1))
                parent[key] = msgs[n] if n < len(msgs) else dict(marker, **{"@deref_error": "the streamed message is not in this payload"})
            else:
                parent[key] = (payload or {}).get(field, dict(marker, **{"@deref_error": "the streamed text is not in this payload"}))
        else:
            path = Path(resolved["path"])
            data = path.read_bytes() if path.is_file() else None
            if data is None or sha256_bytes(data) != resolved["sha256"]:
                parent[key] = dict(marker, **{"@deref_error": "the artifact changed or vanished since the commit that addressed it; its sha256 at commit was " + resolved["sha256"]})
                continue
            content, _ = _decode_capture(data, sub is not None, at, resolved["path"])
            parent[key] = _json_path_select(content, sub, at) if sub else content
    return out


_SKETCH_TYPE_RE = re.compile(r"^\s*(string|number|integer|boolean|object|array|null|address)(\[\d*\])?(\s*\|\s*(string|number|integer|boolean|object|array|null|address)(\[\d*\])?)*")   # alpha.63: + address
_ADDRESS_VALUE_SCHEMA = {"type": "object", "required": [ADDRESS_REF_KEY], "properties": {ADDRESS_REF_KEY: {"type": "string"}}}


def _sketch_types(text: str) -> list[str]:
    """'string|null' -> ['string', 'null']; 'string[]' / 'array[6]' -> ['array']; free text -> []."""
    m = _SKETCH_TYPE_RE.match(text or "")
    if not m:
        return []
    out = []
    for tok in re.split(r"\s*\|\s*", m.group(0).strip()):
        base = re.sub(r"\[\d*\]$", "", tok)
        out.append("array" if base != tok else base)
    return list(dict.fromkeys(out))


def _output_schema_for(view, run_input) -> dict | None:
    """alpha.59 (doc 128 §6): the program's output declaration - a sketch such as {'hexagram_interpretation': 'string',
    'line_by_line_reading': 'string|null', 'five_hexagram_analysis': 'object'} - compiled into a JSON Schema fragment for this node:
    typed properties, required = the declared keys not typed with null, no undeclared keys, every declared value may instead be an
    address {"@ref": ...}, raw_user_message pinned to the run's user message, human_decisions allowed (engine-filled). Served as
    payload_schema.output; the commit is validated against it (recorded, or rejected under output_strict)."""
    declared = ((view or {}).get("extra") or {}).get("output") if view else None
    if not isinstance(declared, dict) or not declared:
        return None
    props, required = {}, []
    message = (run_input or {}).get("user_message") if isinstance(run_input, dict) else None
    for key, sketch in declared.items():
        if isinstance(sketch, str):
            types = _sketch_types(sketch)
            typed = {"type": types if len(types) > 1 else types[0]} if types else {"description": sketch[:160]}
        else:
            types = ["object"] if isinstance(sketch, dict) else ["array"] if isinstance(sketch, list) else []
            typed = {"type": types[0]} if types else {}
        if key == "raw_user_message" and isinstance(message, str) and message:
            props[key] = {"const": message}
        elif "address" in types:   # alpha.63 L3 (doc 137 §3): the package declares the key as a body - only an address is accepted
            others = [t for t in types if t not in ("address", "null")]
            branches = ([{"type": others if len(others) > 1 else others[0]}] if others else []) + [_ADDRESS_VALUE_SCHEMA] \
                + ([{"type": "null"}] if "null" in types else [])
            props[key] = {"anyOf": branches} if len(branches) > 1 else dict(_ADDRESS_VALUE_SCHEMA)
        elif typed:
            props[key] = {"anyOf": [typed, _ADDRESS_VALUE_SCHEMA]}
        else:
            props[key] = {}
        if "null" not in types:
            required.append(key)
    props.setdefault("human_decisions", {"type": "array"})
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def _pause_output(payload):
    return payload.get('status') == 'PARTIAL' and isinstance(payload.get('gate'), dict) and bool(payload['gate']) and isinstance(payload.get('output'), dict)


def _output_schema_issues(view, run_input, payload: dict) -> tuple[list[dict], bool]:
    """alpha.59: (schema errors other than undeclared keys - those are OUTPUT_UNDECLARED_KEYS -, strict?) for an object output."""
    schema = _output_schema_for(view, run_input)
    output = payload.get("output")
    if not schema or not isinstance(output, dict):
        return [], False
    if _pause_output(payload) or (payload.get('module_control') or {}).get('action') == 'enter':
        schema = dict(schema, required=[])
    issues = [e for e in schema_lite.validate(output, schema, None, "output") if not e["message"].startswith("unexpected field")]
    return issues, bool(((view or {}).get("extra") or {}).get("output_strict"))


def _undeclared_output_keys(view, payload: dict) -> list[tuple[str, int]]:
    """alpha.58 B8 (doc 125 §2 / §5): output keys a package that declares its output does not name - the model's own narration. Recorded
    as OUTPUT_UNDECLARED_KEYS, never rejected, never removed; the user's own words and engine-filled keys are never counted."""
    declared = ((view or {}).get("extra") or {}).get("output") if view else None
    output = payload.get("output")
    if not isinstance(declared, dict) or not declared or not isinstance(output, dict):
        return []
    return [(k, len(json.dumps(v, ensure_ascii=False))) for k, v in output.items()
            if k not in declared and k not in _OUTPUT_VERBATIM_KEYS and not k.startswith("user_")]


def _human_decisions(store: RunStore, index: dict, node: str, visit: int) -> list[dict]:
    """Answered gates for this occurrence; Engine.execute-report covers the whole run in gate order."""
    out = []
    seen = set()
    kinds = ("chosen", "free_text", "cancel") if node in ACCOUNTING_NODES else ("chosen", "free_text")   # alpha.79 (doc 161 §6.1): a routed refusal is a decision of the run
    for h in index["gate"]["history"]:
        if (node not in ACCOUNTING_NODES and h.get("node") != node) or h.get("resolution_kind") not in kinds or h['question_id'] in seen:
            continue
        rec = store.read_json(store.gate_path(h["question_id"]))
        if node not in ACCOUNTING_NODES and rec.get("visit") != visit:
            continue
        seen.add(h['question_id'])
        out.append({"question_id": rec.get("question_id"), "node": rec.get('node'), "visit": rec.get('visit'), "source": rec.get("source"), "question": rec.get("question"),
                    "options": [{"kind": o.get("kind"), "label": o.get("label"), "intent": o.get("intent"),
                                 **({'next_hint': o['next_hint']} if 'next_hint' in o else {})} for o in rec.get("options") or []],
                    "recommendation": rec.get("recommendation"), "answer_text": rec.get("answer_text"), "resolution_kind": rec.get("resolution_kind"),
                    **({'answer_text_original': rec['answer_text_original']} if 'answer_text_original' in rec else {}),
                    **({'invalid_answers': copy.deepcopy(rec['invalid_answers'])} if rec.get('invalid_answers') else {}),   # alpha.79: listed apart from the accepted reply
                    **({'cancel_outcome': rec['cancel_outcome']} if rec.get('cancel_outcome') else {}),   # alpha.88 (doc 196 F4')
                    # round 2 of the review of docs/05SoulRun 87 (N2): a stop retired by a stale replacement choice replaced nothing
                    **({'replacement_refused': copy.deepcopy(rec['replacement_refused'])} if rec.get('replacement_refused') else {}),
                    **_unused_replacement(store, index, rec),   # round 3 (D2): an accepted choice whose replacement never ran
                    **_moved_on(store, index, rec),   # docs/05SoulRun 88 (K1): a recheck that moved on to another stop
                    "consumed_by_commit": rec.get('consumed_by_commit', False),
                    "chosen_intent": rec.get("chosen_intent"), "chosen_label": rec.get("chosen_label"), "answered_by": rec.get("answered_by"),
                    "presented_at": rec.get("presented_at"), "answered_at": rec.get("answered_at"), "by": "engine"})
    return out


def _unused_replacement(store: RunStore, index: dict, rec: dict) -> dict:
    """Round 3 of the review of docs/05SoulRun 87 (D2): {'replacement_not_used': why} for an engine stop whose accepted
    replacement choice replaced nothing, derived from the dispatch records (never written to the gate record); else {}."""
    unused = dispatch_lifecycle.unused_replacement(store, index, rec) if rec.get('source') == 'hsaw_doubt' else None
    return {'replacement_not_used': unused} if unused else {}


def _moved_on(store: RunStore, index: dict, rec: dict) -> dict:
    """docs/05SoulRun 88 (K1): {'recheck_moved_on': {question_id, code}} for a liveness stop that the human's Recheck
    conditions retired because another condition held the part - the stop the human was asked at next - derived from that
    stop's supersedes link (dispatch_budget.recheck_moved_on), never written to the gate record; else {}."""
    moved = dispatch_budget.recheck_moved_on(store, index, rec)
    return {'recheck_moved_on': moved} if moved else {}


def _resolved_decision_rows(store: RunStore, index: dict) -> list[dict]:
    """The gate history rows of resolved choices and free text. Round 2 of the review of docs/05SoulRun 87 (N2): an engine
    stop retired by a stale replacement choice carries the refusal from its gate record, so no count reads it as a
    replacement the human authorized; round 3 (D2): nor an accepted choice whose replacement never ran."""
    rows = []
    for h in index['gate']['history']:
        if h.get('resolution_kind') not in ('chosen', 'free_text'):
            continue
        rec = store.read_json(store.gate_path(h['question_id'])) if h.get('source') == 'hsaw_doubt' else {}
        extra = dict(_unused_replacement(store, index, rec), **_moved_on(store, index, rec),
                     **({'replacement_refused': copy.deepcopy(rec['replacement_refused'])} if rec.get('replacement_refused') else {}))
        rows.append(dict(h, **extra) if extra else h)
    return rows


def _fill_human_decisions(store: RunStore, index: dict, node: str, visit: int, payload: dict) -> tuple[dict, list[dict]]:
    """alpha.58 B9: the engine writes output.human_decisions[] (object outputs); the model's own list is replaced, only its "effect"
    sentences per question_id are kept. String outputs keep the record in machine.human_decisions."""
    decisions = _human_decisions(store, index, node, visit)
    if not decisions:
        return payload, []
    output = payload.get("output")
    given = output.get("human_decisions") if isinstance(output, dict) else None
    effects = {d.get("question_id"): d.get("effect") for d in given if isinstance(d, dict) and isinstance(d.get("effect"), str) and d.get("effect").strip()} \
        if isinstance(given, list) else {}
    for d in decisions:
        if effects.get(d["question_id"]):
            d["effect"] = effects[d["question_id"]]
    if isinstance(output, dict):
        return dict(payload, output=dict(output, human_decisions=decisions)), decisions
    return payload, decisions


def _check_sys_evidence_and_asserts(payload: dict, served: list[dict], *, prior_cache: dict | None = None) -> tuple[bool, list[dict]]:
    """R-23 / I-08. Returns (assertion_failed, anomalies).

    The engine re-evaluates the PROGRAM's assertion expression (from the step text) against the
    model's context_snapshot; the model's own `expression` field is informational only, so a
    substituted trivially-true expression cannot pass. Expressions outside AISOP §6.11 (function
    calls, `in`, `or`) cannot be evaluated by the executor: they are recorded as
    ASSERT_EXPRESSION_UNSUPPORTED and the declared result is accepted (YELLOW, doc 02 I-08).
    """
    done = set(payload["steps"]["done"])
    calls = payload["evidence"]["tool_calls"]
    results = {r["step"]: r for r in payload["evidence"].get("sys_assert_results", [])}
    failed = False
    anomalies: list[dict] = []
    history = list(_evidence_records(prior_cache)) if prior_cache else []
    for s in served:
        sysc = s.get("sys")
        if not sysc or s["key"] not in done:
            continue
        if sysc["name"] == "sys.assert":
            r = results.get(s["key"])
            if r is None:
                r = next((r for record in reversed(history)
                          if s["key"] in (record.get("payload", {}).get("steps", {}).get("done") or [])
                          for r in record.get("payload", {}).get("evidence", {}).get("sys_assert_results", [])
                          if r.get("step") == s["key"]), None)
            if r is None:
                raise EngineError("ASSERTION_RESULT_MISMATCH", f"no sys_assert_results entry for {s['key']}", field="evidence.sys_assert_results",
                                  expected=f"entry with step={s['key']!r}, context_snapshot holding the variables the program's expression names")
            program_expr = aisop_parse.first_string_arg(sysc["args"]) or ""
            try:
                engine_result = bool(aisop_parse.eval_expression(program_expr, r["context_snapshot"]))
            except aisop_parse.ExpressionError as exc:
                msg = str(exc)
                if msg.startswith("Undefined variable"):
                    raise EngineError("ASSERTION_RESULT_MISMATCH", f"{s['key']}: {msg} (program expression {program_expr!r})", field="evidence.sys_assert_results",
                                      expected="context_snapshot with every variable the program's expression names")
                anomalies.append({"code": "ASSERT_EXPRESSION_UNSUPPORTED", "text": f"{s['key']}: program expression {program_expr!r} is outside AISOP §6.11 ({msg}); declared result {r['result']} accepted unverified"})
                failed = failed or not bool(r["result"])
                continue
            if engine_result != bool(r["result"]):
                raise EngineError("ASSERTION_RESULT_MISMATCH", f"{s['key']}: model says {r['result']}, engine says {engine_result} for {program_expr!r}",
                                  field="evidence.sys_assert_results", expected=engine_result)
            failed = failed or not engine_result
            continue
        if sysc["forced_blocking"]:
            continue
        prior_calls = [c for record in history
                       if s["key"] in (record.get("payload", {}).get("steps", {}).get("done") or [])
                       for c in record.get("payload", {}).get("evidence", {}).get("tool_calls", [])]
        if not any(c.get("step") == s["key"] or str(c.get("sys_call") or "").startswith(sysc["name"]) for c in calls + prior_calls):
            raise EngineError("EVIDENCE_MISSING_FOR_SYS_STEP", f"done step {s['key']} ({sysc['name']}) has no tool_calls entry", field="evidence.tool_calls", expected=f"entry with step={s['key']!r}")
    return failed, anomalies


def _successor_candidates(view: dict | None) -> list[str]:
    if not view:
        return []
    topo = view["topology"]
    return list(dict.fromkeys(topo["next_candidates"] + list(topo["branches"].values())))


def _planned_next(index: dict, entry: dict) -> dict | None:
    """The next catalog entry of the same frame (same depth and parent), skipping nested sub-graph entries;
    None when the frame has nothing planned after this node (sub-graphs are planned one node at a time)."""
    depth, parent = entry["depth"], entry.get("parent")
    for e in index["catalog"][entry["ordinal"] + 1:]:
        if e["depth"] < depth:
            return None
        if e["depth"] == depth and e.get("parent") == parent:
            return e
    return None


def _graph_types(program, view: dict) -> dict:
    return program.docs[view["file"]].tasks.get(view["task"], {}).get("node_types", {})


def _end_candidates(program, view: dict | None) -> list[str]:
    if not view or program is None:
        return []
    types = _graph_types(program, view)
    return [c for c in _successor_candidates(view) if types.get(c) == "end"]


def _end_names(program, view: dict | None) -> list[str]:
    if not view or program is None:
        return []
    return [n for n, t in _graph_types(program, view).items() if t == "end"]


def _default_successor(program, view: dict | None, planned: dict | None, in_frame: bool = False) -> str | None:
    """I-02 defaults: the planned successor when it is a candidate; the end node when nothing (or only the
    engine summary) is planned after this node and an end node is a candidate; the only candidate otherwise."""
    cands = _successor_candidates(view)
    if planned and _bare(planned) in cands:
        return _bare(planned)
    ends = _end_candidates(program, view)
    if ends and (planned is None or planned["kind"] == "engine"):
        return ends[0]
    return cands[0] if len(cands) == 1 else None


def _check_next_hint(payload: dict, view: dict | None, planned: dict | None, program=None, in_frame: bool = False, notes: list | None = None) -> None:
    """I-02: next_hint may override within the candidates; it is required only when no default exists. alpha.68 (doc 145 E3): with
    exactly one candidate a wrong hint cannot change anything - it is corrected and recorded (NEXT_HINT_CORRECTED), never rejected."""
    if not view:
        return
    cands = _successor_candidates(view)
    hint = payload.get("next_hint")
    if hint is not None and hint not in cands and len(cands) == 1:
        if notes is not None:
            notes.append({"code": "NEXT_HINT_CORRECTED", "text": f"next_hint {hint!r} is not a successor of this node; the only candidate {cands[0]!r} was taken (alpha.68)"})
        payload["next_hint"] = hint = cands[0]
    if hint is not None and hint not in cands and re.split(r"[./]", str(hint))[-1] in cands:   # alpha.99 (doc 239 P4): a qualified name
        if notes is not None:
            notes.append({"code": "NEXT_HINT_CORRECTED", "text": f"next_hint {hint!r} names the successor {re.split(r'[./]', str(hint))[-1]!r} (alpha.99)"})
        payload["next_hint"] = hint = re.split(r"[./]", str(hint))[-1]
    if hint is not None and hint not in cands:
        raise EngineError("NEXT_HINT_INVALID", f"{hint!r} not in {cands}", field="next_hint", expected=cands or None, example=cands[0] if cands else None)
    if hint is None and len(cands) > 1 and _default_successor(program, view, planned, in_frame) is None and payload["status"] != "FAIL":
        # alpha.99 (doc 239 P4; production 9, isolated 35 / 45 / 59): the successor this commit's own output names first
        output = payload.get("output")
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        spots = sorted((m.start(), c) for c in cands for m in [re.search(r"(?<![A-Za-z0-9_])" + re.escape(c) + r"(?![A-Za-z0-9_])", text or "")] if m)
        if spots:
            payload["next_hint"] = spots[0][1]
            if notes is not None:
                notes.append({"code": "NEXT_HINT_INFERRED", "text": f"no next_hint among {len(cands)} successors: {spots[0][1]!r}, the first one this commit's output "
                                                                    "names, was taken (alpha.99) - set next_hint"})
            return
        raise EngineError("NEXT_HINT_INVALID", f"candidates {cands}, no planned successor among them", field="next_hint", expected=cands, example=cands[0])


def _gate_identity(gate: dict) -> tuple:
    normalize = lambda value: " ".join(str(value).split()).casefold()
    return (normalize(gate["question"]), tuple((o["kind"], normalize(o["intent"]), normalize(o["label"])) for o in gate["options"]))


_SKIP_LABEL_RE = re.compile(r"不导出|不生成|不保存|不写入|不发送|不执行|不做|跳过|略过|暂不|\bskip|\bwithout\b|\bomit|\bdo not\b|\bdon'?t\b|\bnot? (?:the )?export|\bno_export\b", re.I)
_CANCEL_LABEL_RE = re.compile(r"取消|放弃|终止|中止|\bcancel|\babort|\bterminate|\bquit\b", re.I)


def _skip_labelled_as_cancel(option: dict) -> bool:
    """alpha.88 (doc 195 §2; production cache/55: 「不导出，结束本轮」 modelled as kind cancel, the human chose it, the run was abandoned):
    a cancel option whose label reads as declining one step and carries no cancel word. Words only, never semantics; a label with a
    cancel word ("取消导出") is left to the model."""
    label = str(option.get("label") or "")
    return bool(_SKIP_LABEL_RE.search(label)) and not _CANCEL_LABEL_RE.search(label)


def _normalize_gate_shape(gate: dict, notes: list | None) -> None:
    """alpha.99 (04 series doc 239 G4 / G5): what _check_gate_shape used to refuse and the engine can settle - a cancel option whose intent is
    not cancel (a real cancellation gets intent cancel; a declined step labelled as one becomes kind execute and keeps its intent), aliases
    repeated inside an option or shared by two options (kept once / dropped from both). Recorded."""
    changed = []
    options = [o for o in gate.get("options") or [] if isinstance(o, dict)]
    for i, o in enumerate(options):
        if o.get("kind") == "cancel" and (o.get("intent") != "cancel" or _skip_labelled_as_cancel(o)):
            if _skip_labelled_as_cancel(o):   # production cache/55, isolated 59: 「不导出，结束本轮」 is declining a step, not the gate
                o["kind"] = "execute"
                if o.get("intent") == "cancel":
                    o["intent"] = "skip"
                    if gate.get("recommendation") == "cancel":
                        gate["recommendation"] = "skip"
                changed.append(f"options[{i}] {o.get('label')!r}: kind cancel -> execute")
            else:   # isolated 33: 「取消本轮运行」 with intent cancel_run
                if gate.get("recommendation") == o.get("intent"):
                    gate["recommendation"] = "cancel"
                changed.append(f"options[{i}].intent {o.get('intent')!r} -> 'cancel'")
                o["intent"] = "cancel"
    owners = {}
    for i, o in enumerate(options):
        seen = []
        for a in o.get("aliases") or []:
            if isinstance(a, str) and a.lower() not in [s.lower() for s in seen]:
                seen.append(a)
        if len(seen) != len(o.get("aliases") or []):
            changed.append(f"options[{i}].aliases repeated inside the option")
            o["aliases"] = seen
        for a in seen:
            owners.setdefault(a.lower(), set()).add(i)
    shared = {a for a, who in owners.items() if len(who) > 1}
    if shared:
        for o in options:
            if o.get("aliases"):
                o["aliases"] = [a for a in o["aliases"] if a.lower() not in shared]
        changed.append(f"aliases shared by two options dropped: {sorted(shared)}")
    if changed and notes is not None:
        notes.append({"code": "GATE_OPTION_KIND_CORRECTED" if any("kind" in c or "intent" in c for c in changed) else "GATE_ALIASES_DEDUPED",
                      "text": "; ".join(changed) + " (alpha.99)"})


def _check_gate_shape(gate: dict, view: dict | None = None, allow_no_recommendation: bool = False) -> None:
    for i, option in enumerate(gate['options']):
        field = f'gate.options[{i}]'
        if any(a.strip().lower() in {'all', 'everything', '全部', '全接受', '全部接受'}
               and a.strip().lower() not in {option['label'].strip().lower(), option['intent'].lower()}
               for a in option.get('aliases', [])):
            raise EngineError('GATE_SHAPE_INVALID', 'Collection aliases cannot grant an option extra permissions. '
                              'Remove the shorthand and request its exact label or number.', field=field + '.aliases')
        if (option['kind'] == 'cancel') != (option['intent'] == 'cancel'):
            raise EngineError('GATE_CANCEL_INTENT_INVALID',
                              'Cancel requires intent=cancel. Keep an optional skip intent (e.g. skip_export) and use kind=execute; '
                              'do not rename a skip to cancel. Only a genuine refusal of the whole gate is cancel.',
                              field=field, expected='execute + business intent, or cancel + cancel')
        if option['kind'] == 'cancel' and _skip_labelled_as_cancel(option):   # alpha.88 (doc 195 §2; production cache/55)
            raise EngineError('GATE_CANCEL_INTENT_INVALID',
                              f'option {option.get("label")!r} reads as declining one step, not as refusing the whole gate: make it kind=execute '
                              'with an intent naming the skip path (e.g. skip_export); a cancel option is labelled as a cancellation (取消 / cancel) '
                              'and stops the business work (alpha.88).',
                              field=field + '.kind', expected='execute + skip intent')
        if 'next_hint' in option and (option['kind'] != 'execute' or not view or option['next_hint'] not in _successor_candidates(view)):
            raise EngineError('GATE_BRANCH_INVALID', 'Only execute options may bind a declared graph successor.',
                              field=field + '.next_hint', expected=_successor_candidates(view) if view else [])
    intents = [o["intent"] for o in gate["options"]]
    labels = [o["label"] for o in gate["options"]]
    if len(set(intents)) != len(intents) or len(set(labels)) != len(labels):
        raise EngineError("GATE_SHAPE_INVALID", "duplicate option intents or labels", field="gate.options", expected="unique intents and labels")
    if not any(o["kind"] == "execute" for o in gate["options"]):
        raise EngineError("GATE_SHAPE_INVALID", "at least one execute option", field="gate.options", expected="kind execute present")
    rec = gate.get("recommendation")   # alpha.28 GA: required — a recommendation with its reason, never a choice (Axiom 0)
    if not rec or (rec not in intents and not (allow_no_recommendation and rec == hsaw_gate.NO_RECOMMENDATION)):   # alpha.87: an hsaw_doubt gate may say "none"
        raise EngineError("GATE_SHAPE_INVALID", f"recommendation {rec!r} must name an option intent", field="gate.recommendation", expected=intents)
    for key in ("advice", "explanation"):
        if not str(gate.get(key) or "").strip():
            raise EngineError("GATE_SHAPE_INVALID", f"gate.{key} is required (advice: why you recommend that option; explanation: what this decision is about and how the options differ)",
                              field=f"gate.{key}", expected="non-empty text in the user's language")
    aliases = [a.lower() for o in gate["options"] for a in o.get("aliases", [])]
    if len(set(aliases)) != len(aliases):
        raise EngineError("GATE_SHAPE_INVALID", "duplicate aliases across options", field="gate.options", expected="unique aliases")


def _hsaw_ref_exists(store, index, payload, ref: str) -> bool:
    """alpha.87 (doc 193 §2): an hsaw item's evidence_refs are addresses of this run; syntax + existence, no semantics."""
    kind, _, rest = str(ref).partition(":")
    target = rest.split("#", 1)[0]
    if kind == "proc":
        return target.startswith("_proc/") and store.exists_path(store.cache_dir / target)
    if kind == "work":
        return bool(target) and store.exists_path(store.cache_dir / "_work" / target)
    if kind == "artifact":
        return target.isdigit() and int(target) < len((payload.get("evidence") or {}).get("artifacts") or [])
    if kind == "input":
        node, _, visit = target.partition("@")
        return bool((index["nodes"].get(_node_key(node, int(visit) if visit.isdigit() else 1)) or {}).get("committed_at"))
    if kind == "evidence":
        return target == "sources"
    if kind == "host":
        return bool(re.fullmatch(r"report|explain|message\[\d+\]", target))
    if kind == "file":   # alpha.99 (doc 239 H3): an existing absolute file, hashed by the engine in the note it writes
        return Path(rest).is_absolute() and Path(rest).is_file()
    if kind == "note":   # alpha.99: the executor's own words, kept as such
        return bool(rest.strip())
    return False


def _hsaw_file_ref(program_dir, ref) -> list[str]:
    """alpha.99 (doc 239 H3; isolated 40 / 47 / 49 / 54 / 56 / 59 / 60): an evidence reference that is not an address of this run - an existing
    absolute file -> file:<path>; a sentence that starts with a program file name -> file:<that file> + note:<the rest>; else note:<text>"""
    text = str(ref).strip()
    p = Path(text)
    if p.is_absolute() and p.is_file():
        return [f"file:{p.resolve().as_posix()}"]
    m = re.match(r"^([\w./\\-]+?\.(?:aisop\.json|json|md|py|txt|ya?ml))(?![\w.])", text)
    if m and program_dir:
        cand = Path(program_dir) / m.group(1)
        if cand.is_file():
            rest = text[m.end():].strip(" :：;；,，-—")
            return [f"file:{cand.resolve().as_posix()}"] + ([f"note:{rest}"] if rest else [])
    return [f"note:{text}"]


def _answered_hsaw_fingerprints(store, index: dict, pending_answer: dict | None) -> set:
    """alpha.99 (doc 239 H9): the fingerprints of the items an answered hsaw_doubt gate of this occurrence carried"""
    if not pending_answer:
        return set()
    try:
        record = store.read_json(store.gate_path(pending_answer["question_id"]))
    except (OSError, ValueError, KeyError):
        return set()
    ids = set((record.get('hsaw') or {}).get('item_ids') or [])
    if not ids:
        return set()
    problems = hsaw_gate.verify_register(index)
    answers = [row for row in index.get('hsaw_register') or []
               if row.get('kind') == 'gate_answered' and row.get('question_id') == pending_answer['question_id']]
    if (problems or not answers or record.get('answer_text') != answers[-1].get('answer')
            or not isinstance(record.get('answer_text_original'), str)
            or record['answer_text_original'].strip() != record.get('answer_text')):
        raise EngineError('HSAW_DECISION_EVIDENCE_INVALID', 'Answered finding suppression requires intact decision evidence', field='hsaw_items')
    return {ev.get("fingerprint") for ev in index.get("hsaw_register") or [] if ev.get("kind") == "discovered" and ev.get("id") in ids}


def _hsaw_package(index: dict) -> str:
    return str((index.get("route") or {}).get("package") or _program_name(index) or "unknown")


def _check_hsaw_items(store, index, current: str, payload: dict, notes: list | None = None, program=None, pending_answer=None) -> dict | None:
    """alpha.87 (doc 193): validate hsaw_items[] (structure and self-consistency only) and mint their engine-owned identities.
    Returns {"items": validated, "machine": {"items": [...with id / fingerprint]}, "events": [discovered events]} or None.
    alpha.99 (doc 239 §3.3): an empty list at the report / answer node is ignored, items a human already answered at this occurrence are
    not frozen again, evidence references become addresses, and a level below what the item's facts require is raised (never lowered)."""
    items = payload.get("hsaw_items")
    if items is None:
        return None
    if current in (*ACCOUNTING_NODES, *ANSWER_NODES, LEGACY_SUMMARY):
        if items == []:   # alpha.99 (doc 239 H5; isolated cache 41): an empty list says nothing
            payload.pop("hsaw_items")
            if notes is not None:
                notes.append({"code": "HSAW_ITEMS_EMPTY_IGNORED", "text": f"an empty hsaw_items at {current} was ignored (alpha.99)"})
            return None
        raise EngineError("HSAW_ITEM_INVALID", "hsaw_items are not accepted at the execution report / answer node", field="hsaw_items", expected="absent")
    answered = _answered_hsaw_fingerprints(store, index, pending_answer) if isinstance(items, list) and "gate" not in payload else set()
    if answered:   # alpha.99 (doc 239 H9): the human answered these at this occurrence - recorded there, not frozen again
        package = _hsaw_package(index)
        known = {row.get('id'): row.get('fingerprint') for row in index.get('hsaw_register') or [] if row.get('kind') == 'discovered'}
        keep = [it for it in items if not (isinstance(it, dict) and
                (known.get(it.get('same_as')) or hsaw_gate.fingerprint(package, current, it)) in answered)]
        if len(keep) != len(items) and notes is not None:
            notes.append({"code": "HSAW_ITEM_ALREADY_ANSWERED", "text": f"{len(items) - len(keep)} hsaw item(s) a human already answered at this occurrence were "
                                                                        "not recorded again (alpha.99)"})
        items = payload["hsaw_items"] = keep
        if not items:
            return None
    if isinstance(items, list):
        defaults = ["host:report"] if str(payload.get("user_summary") or "").strip() else ["host:explain"] if str(payload.get("explain") or "").strip() else [
            "note:" + ("未给出证据" if not str(index.get("user_language") or "zh").lower().startswith("en") else "no evidence given")]
        hsaw_gate.normalize_refs(items, lambda ref: _hsaw_ref_exists(store, index, payload, ref), lambda ref: _hsaw_file_ref(getattr(program, "dir", None), ref),
                                 defaults, notes)
        hsaw_gate.align_items(items, notes, index.get("user_language"))
    try:
        validated = hsaw_gate.validate_items(items, ref_ok=lambda ref: _hsaw_ref_exists(store, index, payload, ref))
    except hsaw_gate.HsawError as exc:
        raise EngineError(exc.code, exc.message, field=exc.field, expected=exc.expected, example=_EXAMPLES["hsaw_item"])
    if not validated:
        return None
    def prior_item(name, visit, item_id):
        entry = _catalog_entry(index, name)
        path = _cache_path_for(store, index, entry, visit)
        accepted = index['nodes'].get(_node_key(name, visit)) or {}
        if sha256_bytes(store.read_bytes(path)) != accepted.get('cache_sha256'):
            raise hsaw_gate.HsawError('HSAW_DECISION_EVIDENCE_INVALID', f'{name}: accepted cache digest differs')
        for revision in _evidence_records(store.read_json(path)):
            for previous in ((revision.get('machine') or {}).get('hsaw') or {}).get('items') or []:
                if previous.get('id') == item_id:
                    return previous
        return None

    try:
        readjudication = hsaw_readjudication.review(validated, index, lambda q: store.read_json(store.gate_path(q)), prior_item)
    except (hsaw_gate.HsawError, RunStoreError, OSError, KeyError, TypeError) as exc:
        raise EngineError(getattr(exc, 'code', 'HSAW_DECISION_EVIDENCE_INVALID'), str(exc), field='hsaw_items') from exc
    if readjudication:
        proposed_hard = copy.deepcopy(hsaw_gate.hard_fail_items(validated))
        # All proposed hard failures remain in evidence; none may terminate past the new human gate.
        for it in validated:
            if it['disposition'] == 'HARD_FAIL':
                it['disposition'] = 'FREEZE_NOW'
        payload['status'] = 'PARTIAL'
        payload.pop('error_type', None)
        payload['gate'] = hsaw_readjudication.gate(validated, current, index.get('user_language'), readjudication)
        if notes is not None:
            notes.append(dict(code='HSAW_HARD_FAIL_READJUDICATION', text='A related prior decision requires a new human gate; no repair or continuation was authorized.'))
    package = _hsaw_package(index)
    record = hsaw_gate.prepare(package, current, index["current"]["visit"], validated, now_iso(), hsaw_gate.ledger_rows(store.cache_dir.parent, package))
    if readjudication:
        record['machine']['readjudication'] = readjudication
        record['machine']['hard_fail_proposals'] = proposed_hard
    record["items"] = validated
    return record


def _hsaw_ledger_append(store, index: dict, events: list) -> None:
    """The package's cross-run ledger under <cache root>/_hsaw/ (never inside the business package); best effort, recorded when it fails."""
    try:
        hsaw_gate.ledger_append(store.cache_dir.parent, _hsaw_package(index), f"{store.cache_dir.name}:{index['trace_id']}", events,
                               verified_append=dispatch_lifecycle.replacement_accounting(index))
    except OSError as exc:
        index["anomalies_summary"].append({"node": index["current"]["name"], "code": "HSAW_LEDGER_UNAVAILABLE", "text": f"package ledger not written: {exc}"})


def _hsaw_report_facts(store, index: dict) -> dict:
    facts = hsaw_gate.summary(index)
    status = hsaw_gate.ledger_status(store.cache_dir.parent, _hsaw_package(index))
    facts.update(open=status["open"], ledger_rows=status["rows"], ledger_problems=status["problems"], rows=hsaw_gate.table_rows(index),
                 register_problems=hsaw_gate.verify_register(index))
    return facts


def _record_gate_target(record: dict) -> str | None:
    if record.get('resolution_kind') != 'chosen' and not (record.get('resolution_kind') == 'free_text' and conditional_reply.accepted(record)):
        return None
    selected = [o for o in record['options'] if o['intent'] == record.get('chosen_intent') and o['kind'] == 'execute']
    return selected[0].get('next_hint') if len(selected) == 1 else None


def _apply_gate_branch(store, index, entry, visit, payload):
    if payload['status'] == 'FAIL':
        return  # Real execution failures retain the program's error route.
    for history in reversed(index['gate']['history']):
        if history['node'] != entry['name'] or history.get('resolution_kind') not in ('chosen', 'free_text'):
            continue
        record = store.read_json(store.gate_path(history['question_id']))
        target = _record_gate_target(record) if record.get('visit') == visit else None
        if target:
            if payload.get('next_hint') not in (None, target):
                raise EngineError('GATE_BRANCH_CONFLICT', 'Continuation cannot override the human-selected graph branch.',
                                  field='next_hint', expected=target, example=target)
            payload['next_hint'] = target
            return


def _router_option_bindings(run_input, gate, raw_intents):
    """Bind original program IDs before intent normalization loses Unicode or punctuation."""
    names = [s['package'] for s in run_input['snapshot']]
    bindings = {}
    for i, option in enumerate(gate['options']):
        if option['kind'] != 'execute':
            continue
        raw = raw_intents[i] if i < len(raw_intents) else None
        matches = [n for n in names if n == raw]
        if not matches:
            matches = [n for n in names if _normalize_intent(n, f'option_{i + 1}') == option['intent']]
        if len(matches) != 1:
            raise EngineError('ROUTE_INVALID', 'A program-choice option must identify exactly one registry program.',
                              field=f'gate.options[{i}].intent', expected=names)
        bindings[option['intent']] = matches[0]
    return bindings


def _human_selected_route(store, index, run_input):
    """Use the latest real program choice; later HSAW dispositions do not replace it."""
    history = index['gate']['history']
    if (index['gate'].get('source') == 'router_candidates' and index['gate'].get('question_id')
            and not any(h['question_id'] == index['gate']['question_id'] for h in history)):
        raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'The Router gate has no matching question history.')
    for h in reversed(history):
        if h['node'] != NODE_MATCH or h['source'] != 'router_candidates' or h['resolution_kind'] == 'invalid_retry':
            continue
        try:
            rec = store.read_json(store.gate_path(h['question_id']))
            events = store.read_json(store.evidence_path)
        except (RunStoreError, OSError) as exc:
            raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'The accepted Router choice evidence is unavailable.') from exc
        keys = ('question_id', 'node', 'source', 'resolution_kind', 'answered_at')
        if (not isinstance(rec, dict) or any(rec.get(k) != h.get(k) for k in keys)
                or rec.get('visit') != index['current']['visit'] or rec.get('resolution_kind') != 'chosen'
                or not rec.get('answered_at')):
            raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'The Router choice disagrees with this node occurrence.')
        selected = [o for o in rec.get('options', [])
                    if o.get('kind') == 'execute' and o.get('intent') == rec.get('chosen_intent')]
        bindings = rec.get('route_binding')
        answers = [e for e in events if e.get('kind') == 'gate_answer' and e.get('question_id') == h['question_id']
                   and e.get('answered_at') == rec['answered_at']]
        if (len(selected) != 1 or not isinstance(bindings, dict) or len(answers) != 1
                or any(answers[0].get(k) != rec.get(k) for k in ('node', 'visit', 'resolution_kind', 'chosen_intent', 'answered_by'))):
            raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'The Router choice has no unique accepted option and event binding.')
        target = bindings.get(rec['chosen_intent'])
        if (set(bindings) != {o['intent'] for o in rec['options'] if o['kind'] == 'execute'}
                or target not in [s['package'] for s in run_input['snapshot']]):
            raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'The Router choice has no current registry program binding.')
        return target
    return None


def _prevalidate_advance(store, index, run_input, program, entry, payload) -> dict:
    """Everything the cursor advance needs, validated before any file is written."""
    pre: dict = {}
    if (payload.get('module_control') or {}).get('action') == 'enter':
        return dict(module_prefix=True)
    if entry["name"] == NODE_MATCH:
        route = payload.get("route")
        package = route["package"] if route else None
        chosen = _human_selected_route(store, index, run_input)
        if chosen is not None and package != chosen:
            raise EngineError('ROUTE_CHOICE_CONFLICT', 'The route cannot override the human-selected program.',
                              field='route.package', expected=chosen, example=chosen)
        if package == NO_MATCH:
            pre["no_match"] = True
            return pre
        snap = next((s for s in run_input["snapshot"] if s["package"] == package), None)
        if snap is None:
            raise EngineError("ROUTE_INVALID", f"{package!r} not in registry snapshot", field="route.package", expected=index["route"]["snapshot"] + [NO_MATCH])
        routed = _load_bound_program(run_input, snap)
        pre.update({"snap": snap, "program": routed, "analysis": program_loader.analyze(routed)})
    elif entry["name"] == NODE_SETUP:
        path = payload.get("outer_nodes_in_path")
        if not path:
            raise EngineError("PATH_INVALID", "outer_nodes_in_path is required at Router.cache-setup", field="outer_nodes_in_path", expected="non-empty list", example=_EXAMPLES["outer_nodes_in_path"])
        try:
            pre["catalog"] = program_loader.compile_outer_path(program, path, report_node=_report_node(index))
        except program_loader.ProgramError as exc:
            raise EngineError(exc.code, exc.detail, field="outer_nodes_in_path", expected="a main-graph walk", example=_EXAMPLES["outer_nodes_in_path"])
        fatal = []
        for name in path:
            v = program_loader.node_view(program, name)
            if v["unsupported_reserved"]:
                fatal.append({"code": "UNSUPPORTED_RESERVED_KEY", "severity": "FATAL", "detail": f"node {name} uses {v['unsupported_reserved']}"})
        pre["fatal"] = fatal
    elif entry["kind"] in ("business", "sub"):
        view = _view_for(program, entry)
        frame = _frame_of(index, entry)
        chosen = ((None if hsaw_gate.hard_fail_items(payload.get("hsaw_items")) else _error_handler(view, payload, index, entry)) if payload["status"] == "FAIL" else   # alpha.87
                  payload.get("next_hint") or _default_successor(program, view, _planned_next(index, entry), in_frame=frame is not None))
        if chosen and chosen in _graph_for(program, entry)["nodes"]:
            target = _sibling_entry(entry, chosen, entry["ordinal"] + 1)["name"]
            visits = [c["visit"] for c in index["completed"] if c["name"] == target and
                      (not frame or index["nodes"][_node_key(target, c["visit"])].get("parent_visit") == frame["parent_visit"])]
            if target == entry["name"]:
                visits.append(index["current"]["visit"])
            if visits:
                gate_ref = index["gate"]["question_id"] if index["gate"]["node"] == entry["name"] and index["gate"]["answered_at"] else None
                pre["revisit"] = {"source": entry["name"], "source_visit": index["current"]["visit"],
                                  "target": target, "target_visit": max(visits) + 1,
                                  "parent": frame["parent"] if frame else None, "parent_visit": frame["parent_visit"] if frame else None,
                                  "reason": "error_route" if payload["status"] == "FAIL" else "graph_backedge",
                                  "source_gate_ref": gate_ref, "policy": "OBSERVE_ONLY_NOT_AUTHORIZATION"}
    return pre


def _pause_block(store: RunStore, index: dict, entry: dict, visit: int, payload: dict, node_entry: dict, machine_dispatch: dict | None,
                 qid: str, now: str) -> str:
    """alpha.25 (doc 47 item 1; v6 node_engine step3_5 "landed-evidence MID-STATE node-info"): the ⏸ WAITING_USER node
    info rendered from the paused payload and written to _public/pause.NN.<Node>.<qid>.v<visit>.txt. The model presents
    it before the menu, so the findings a gate rests on are public even when the gate question is short."""
    position = _track_position(index, entry, visit)
    executor = render.executor_note(machine_dispatch, node_entry.get("dispatch") if entry["kind"] != "sub" else None)
    steps_done = len(payload["steps"]["done"])
    steps_total = steps_done + len(payload["steps"]["remaining"]) + len(payload["steps"]["not_applicable"])
    cache = store.read_json(_cache_path_for(store, index, entry, visit))
    counts = _node_evidence(cache)["counts"]
    run_input = _read_run_input(store)
    block = render.node_block(position=position, node=entry["name"], kind=entry["kind"], status="WAITING_USER",
                              cache_sha256=index["nodes"][_node_key(entry["name"], visit)]["cache_sha256"], committed_at=now,
                              elapsed_ms=_ms_between(node_entry["ready_at"], now), logical_tool_calls=counts["declared_entries"],
                              user_summary=payload["user_summary"], user_messages=payload.get("user_messages", []), artifacts=[],
                              anomalies=evidence_views.node_anomalies(payload, (cache.get('continuations') or [cache])[-1]['machine'])
                                        + hsaw_gate.anomaly_lines((cache.get('continuations') or [cache])[-1]['machine']),   # alpha.87
                              next_node=None, next_kind=None, executor=executor,
                              explain=payload.get("explain"), steps_done=steps_done, steps_total=steps_total,
                              process_verified=counts["verified_references"], evidence_counts=counts, gate_question_id=qid,
                              user_message=run_input.get("user_message") if entry["kind"] != "engine" or entry["name"] == NODE_MATCH else None,
                              user_language=index.get("user_language"),   # alpha.29
                              waiting_gate=qid)
    stem = _safe_name(entry['name'])
    store.write_public(f"pause.{position['ordinal']:02d}.{stem}.{qid}.v{visit}.txt", block)
    return block


def _pause_with_gate(store, index, entry, visit, payload, node_entry, view, machine_dispatch: dict | None = None, pending_answer: dict | None = None, executor_mode: dict | None = None, *, source_proof=None, anomalies=None, hsaw: dict | None = None, route_binding: dict | None = None) -> dict:
    from . import public_path_text
    public_path_text.validate(payload,anomalies)
    now = now_iso()
    qid = f"q{len(index['gate']['history']) + 1:03d}-{secrets.token_hex(4)}"
    gs = _gate_summary(view["gate_sources"]) if view else {"source": "router_candidates", "kind": "choice", "prompt_text": None}
    if gs["source"] == "none":   # the model asks the user on a node that declares no gate source (doc 12 §7.4): allowed, labelled
        gs = {"source": "model_request", "kind": "choice", "prompt_text": None}
    hsaw_freeze = hsaw_gate.freeze_items(hsaw["items"]) if hsaw else []   # alpha.87 (doc 193 §4): the sovereignty doubt gate
    if hsaw_freeze:
        gs = {"source": hsaw_gate.GATE_SOURCE, "kind": "choice", "prompt_text": None}
    hsaw_events = list(hsaw["events"]) if hsaw else []
    if hsaw_freeze:
        hsaw_events.append(hsaw_gate.gate_opened_event(entry["name"], visit, qid, [it["id"] for it in hsaw["machine"]["items"] if it["disposition"] == "FREEZE_NOW"], now))
    record = {"question_id": qid, "node": entry["name"], "visit": visit, "source": gs["source"], "kind": gs["kind"],
              "prompt_text": gs.get("prompt_text"), "question": payload["gate"]["question"], "options": payload["gate"]["options"],
              "closing": payload["gate"]["closing"], "recommendation": payload["gate"].get("recommendation"),
              "advice": payload["gate"].get("advice"), "explanation": payload["gate"].get("explanation"),   # alpha.28 GA
              "presented_at": now, "delivered_at": None, "answered_at": None, "answer_text": None,
              "resolution_kind": None, "chosen_intent": None, "chosen_label": None, "consumed_by_commit": False}
    if route_binding is not None:
        record['route_binding'] = route_binding
    if payload['gate'].get('conditional_reply'):
        decl = conditional_reply.declaration(payload['gate']['conditional_reply'], view,
                business=entry['kind'] in ('business', 'sub'), source=gs['source'])
        if decl:
            record['conditional_reply'] = copy.deepcopy(decl)
    if hsaw_freeze:   # alpha.87: the gate record names its items and the resume boundary
        record["hsaw"] = {"category": hsaw_freeze[0]["category"], "item_ids": [it["id"] for it in hsaw["machine"]["items"] if it["disposition"] == "FREEZE_NOW"]}
        if hsaw.get('finding_only_intents'):record['hsaw']['finding_only_intents']=hsaw['finding_only_intents']
        record["resume_boundary"] = payload["gate"].get("resume_boundary")
    cache_path = _cache_path_for(store, index, entry, visit)
    # R-37: prove the index transition is schema-valid BEFORE any file is written (a rejected pause must leave no trace)
    projection = copy.deepcopy(index)
    _apply_pause_to_index(projection, entry, visit, record, cache_path, cache_sha256="0" * 64)
    hsaw_gate.append_events(projection, hsaw_events)
    problems = store.validate_index(project_host_fields(projection))
    if problems:
        raise EngineError("INDEX_PROJECTION_INVALID", f"gate pause would leave the index invalid: {problems[0]['field']} {problems[0]['message']}",
                          field="gate", expected="a gate the index can record")
    payload, report_projection = evidence_views.project_report(payload, index.get('user_language'), gate_answer=pending_answer)
    machine = {"committed_at": now, "ready_at": node_entry["ready_at"], "trace_id": index["trace_id"], "engine_version": ENGINE_VERSION,
               "artifacts": [], "logical_tool_calls": len(payload["evidence"]["tool_calls"]), "assertion_failed": False, "paused_gate": qid,
               "dispatch": machine_dispatch, "execution_mode": executor_mode,
               "engine_anomalies": anomalies if anomalies is not None else evidence_views.evidence_anomalies(payload)}
    _, review_owner = _self_dispatch(index, entry, visit)
    if review_owner and review_owner.get('review_binding'):
        machine['review_binding'] = copy.deepcopy(review_owner['review_binding'])
    if review_owner and review_owner.get('input_binding'):
        machine['input_binding'] = copy.deepcopy(review_owner['input_binding'])
    dropped = repairs.dropped_fields(machine["engine_anomalies"])   # alpha.99 (doc 239)
    if dropped:
        machine["dropped_fields"] = dropped
    if source_proof and any(source_proof[k] for k in ('source_verified', 'derived', 'unverified')):
        machine['source_support'] = source_proof
    if report_projection:
        machine['report_projection'] = report_projection
    if hsaw:
        machine['hsaw'] = hsaw['machine']   # alpha.87
    from . import partial_commit
    partial_commit.prepare(store, index, entry, visit,
        dict(payload=payload, machine=machine, gate_answer=pending_answer), pause_record=record,
        hsaw_events=hsaw_events, shared_events=hsaw['events'] if hsaw else ())
    store.write_json_once(store.gate_path(qid), record)
    if store.exists_path(cache_path):
        store.append_continuation(cache_path, {"payload": payload, "machine": machine, "gate_answer": pending_answer})
    else:
        store.write_json_once(cache_path, {"cache_schema_version": 1, "program": _program_name(index), "node": entry["name"], "kind": entry["kind"],
                                           "visit": visit, "ordinal": entry["ordinal"], "payload": payload, "machine": machine, "gate": qid, "continuations": []})
    if pending_answer:
        _mark_gate_consumed(store, pending_answer["question_id"])
    return _finish_pause(store, index, entry, visit, payload, cache_path, machine, record,
                         hsaw_events=hsaw_events, shared_events=hsaw['events'] if hsaw else [])


def _finish_pause(store, index, entry, visit, payload, cache_path, machine, record, *, hsaw_events=(), shared_events=()):
    """Finish the original persisted pause, also used after verified partial writes.
    docs/05SoulRun 90 round 7 (ledger decision 187 (a)): a sub-agent's pause - its commit carries an agent ticket, so the
    machine's dispatch actor is 'sub_agent', in partial_commit's re-application of it too - writes everything the pause
    writes (index, ledger, ticket, ⏸ node info, the scope's ordered public_refs and the reply, the menu's reference among
    them) except the menu file, the mark of a gate shown (_unshown_stop): a gate only a sub-agent was given has not been
    shown. The menu is written, with the same name and bytes, at the main executor's waiting serve (_show_unshown_gate:
    ledger decisions 189 and 193 - the main executor calls next-node before presenting the returned gate, in every host);
    until then a message to the gate is no answer (answer_gate, _not_shown)."""
    qid, now = record['question_id'], record['presented_at']
    machine_dispatch = machine.get('dispatch')
    node_entry = index['nodes'][_node_key(entry['name'], visit)]
    _apply_pause_to_index(index, entry, visit, record, cache_path)
    if hsaw_events:   # alpha.87
        hsaw_gate.append_events(index, hsaw_events)
        _hsaw_ledger_append(store, index, shared_events)
    _ledger_append(store, index, _ledger_commit_event(index, entry, visit, len(store.read_json(cache_path).get("continuations") or []), payload, machine,
                                                     kind="pause", question_id=qid))
    dispatch_result = _apply_dispatch_commit(store, index, entry, visit, machine_dispatch, paused=True,
        at=machine['committed_at'] if dispatch_lifecycle.replacement_accounting(index) else None)
    _write_index(store, index)
    # docs/05SoulRun 90 round 5 (problem 95, ledger decision 185): the menu is the mark of a gate shown (_unshown_stop), so it
    # is written after the ⏸ node info: a process that dies before it leaves a gate not yet shown, which takes no answer and
    # which the main executor's next-node publishes (_show_unshown_gate) - never a menu without its node info
    wait_block = _pause_block(store, index, entry, visit, payload, node_entry, machine_dispatch, qid, now)   # alpha.25
    prompt = render.menu_block(record, user_language=index.get("user_language"))   # alpha.24: robot envelope
    menu = f"menu.{qid}.txt"
    if (machine_dispatch or {}).get('actor') == 'sub_agent':   # round 7 (decision 187 (a)); decision 189: published at the
        # main executor's next-node before it presents the returned gate; a host return is not presentation
        menu_ref = _menu_ref(store, menu, prompt)
    else:
        store.write_public(menu, prompt)
        menu_ref = _ref(store, menu)
    _, scope = _self_dispatch(index, entry, visit)
    if scope and scope.get('scope_root'):
        dispatch_scope.append_ref(scope, _pause_ref(store, qid))
        dispatch_scope.append_ref(scope, menu_ref)
        dispatch_result.update(dispatch_scope.view(scope))
        _write_index(store, index)
    return {"status": "WAITING_USER", "node": entry["name"], "run_state": "WAITING_USER",
            "gate": {"question_id": qid, "public_prompt": prompt, "public_prompt_ref": menu_ref},   # alpha.27 R1
            "public_block": wait_block, "public_block_ref": _pause_ref(store, qid), "public_plan_next": None, "errors": [], "next": None,
            "dispatch": dispatch_result}


def _apply_pause_to_index(index: dict, entry: dict, visit: int, record: dict, cache_path: Path, cache_sha256: str | None = None) -> None:
    qid = record["question_id"]
    index["gate"].update({"state": "WAITING_USER", "question_id": qid, "node": entry["name"], "source": record["source"], "kind": record["kind"],
                          "presented_at": record["presented_at"], "delivered_at": record.get("delivered_at"), "answered_at": None})
    index["gate"]["history"].append({"question_id": qid, "node": entry["name"], "source": record["source"], "prompt_text": record.get("prompt_text"),
                                     "presented_at": record["presented_at"], "answered_at": None, "resolution_kind": None,
                                     "answer_ref": f"_gate.{qid}.json"})
    index["tickets"].append({"question_id": qid, "state": "READY", "minted_at": record["presented_at"]})
    index["run_state"] = "WAITING_USER"
    key = _node_key(entry["name"], visit)
    index["nodes"].setdefault(key, RunStore.new_node_entry(visit))
    index["nodes"][key]["status"] = "WAITING_USER"
    if cache_sha256 is None:
        raw = RunStore.read_bytes(cache_path)
        cache_sha256 = sha256_bytes(raw)
        index["nodes"][key]["logical_tool_calls"] = _count_tool_calls(strict_loads(raw.decode("utf-8")))
    index["nodes"][key]["cache_sha256"] = cache_sha256


def _mark_gate_consumed(store: RunStore, question_id: str) -> None:
    path = store.gate_path(question_id)
    rec = store.read_json(path)
    rec["consumed_by_commit"] = True
    _write_json(path, rec)


def _apply_commit_to_index(store, index, run_input, program, entry, visit, payload, cache, cache_path, pre, recovered: bool, *, frame_closed_at=None, preserved_evidence_sha256=None) -> dict:
    """Index transition for a committed node (also used by orphan-cache recovery). Never raises EngineError."""
    key = _node_key(entry["name"], visit)
    node_entry = index["nodes"].setdefault(key, RunStore.new_node_entry(visit))
    machine = (cache["continuations"][-1] if cache.get("continuations") else cache)["machine"]
    if pre.get('module_prefix'):
        from . import module_order
        return module_order.apply_prefix(store, index, entry, visit, payload, cache, cache_path, machine)
    report_display = payload['user_summary']
    if machine.get('execution_report'):
        from . import execution_report
        execution_report.materialize(store,machine['execution_report'],payload['user_summary'])
        report_display = machine['execution_report']['display']
    committed_at = machine["committed_at"]
    node_entry["committed_at"] = committed_at
    node_entry["ready_at"] = node_entry["ready_at"] or machine.get("ready_at") or committed_at
    node_entry["elapsed_ms"] = _ms_between(node_entry["ready_at"], committed_at)
    node_entry["human_wait_ms"] = node_entry["human_wait_ms"] or 0
    node_entry["active_elapsed_ms"] = _active_elapsed_ms(node_entry, committed_at)
    node_entry["artifacts"] = machine.get("artifacts", [])
    node_entry["sources_count"] = len(payload["evidence"]["sources"])
    counts = _node_evidence(cache)["counts"]
    node_entry["logical_tool_calls"] = counts["declared_entries"]
    node_entry["cache_sha256"] = sha256_bytes(RunStore.read_bytes(cache_path))
    status = "FAIL" if machine.get("assertion_failed") else payload["status"]
    node_entry["status"] = {"PASS": "COMMITTED", "PARTIAL": "COMMITTED", "DEGRADED": "DEGRADED", "FAIL": "FAILED"}[status]
    index["completed"].append({"name": entry["name"], "visit": visit})
    frame = _frame_of(index, entry)
    if frame:  # sub node: fix its commit order inside the frame
        if node_entry.get("order") is None:
            node_entry["order"] = frame["order"]
        frame["order"] += 1
    for a in payload.get("anomalies", []):
        index["anomalies_summary"].append({"node": entry["name"], "code": "MODEL_ANOMALY", "text": a})
    for a in machine.get("engine_anomalies", []):
        index["anomalies_summary"].append({"node": entry["name"], "code": a["code"], "text": a["text"]})
    if recovered:
        index["anomalies_summary"].append({"node": entry["name"], "code": "RECOVERED_ORPHAN_CACHE", "text": "cache existed without index transition; re-applied"})
    revisit = machine.get("revisit")
    if revisit:
        event = dict(revisit, committed_at=committed_at)
        events = index.setdefault("revisit_events", [])
        if event not in events:
            events.append(event)
        index["anomalies_summary"].append({"node": entry["name"], "code": "REVISIT_OBSERVED",
                                          "text": f"{revisit['target']} visit {revisit['target_visit']}; no repair authorization inferred from this observation"})
    view = _view_for(program, entry)
    if view and view["reserved"].get("output_mapping"):
        index["context"][str(view["reserved"]["output_mapping"])] = payload["output"]
    if view:
        first_assert = view["steps"][0]["assert"] if view["steps"] and view["steps"][0]["assert"] else None
        if first_assert and first_assert["required"]:
            rf = _required_fields_status(first_assert["required"], _prev_business_caches(store, index, exclude=(entry["name"], visit)), index["context"],
                                         _run_inputs(run_input))
            if rf["missing"]:
                index["anomalies_summary"].append({"node": entry["name"], "code": "REQUIRED_FIELD_MISSING", "text": f"missing {rf['missing']} (MF28b YELLOW; declared by the package - align Required with a producer's output_mapping or output keys)"})
    if payload.get("target_aiap_dir"):
        index["target_aiap_dir"] = payload["target_aiap_dir"]
    result = {"public_block": None, "public_plan_next": None, "gate": None, "errors": [], "next": None,
              "dispatch": _apply_dispatch_commit(store, index, entry, visit, machine.get("dispatch"), paused=False,
                  at=committed_at if dispatch_lifecycle.replacement_accounting(index) else None)}   # before frames move
    executor = render.executor_note(machine.get("dispatch"), node_entry.get("dispatch") if entry["kind"] != "sub" else None)
    final_evidence = None
    if entry["name"] == NODE_MATCH:
        _advance_after_match(store, index, run_input, pre)
    elif entry["name"] == NODE_SETUP:
        _advance_after_setup(index, pre)
    elif entry["name"] in FINAL_NODES:
        final_evidence = _finalize(store, index, payload, program, committed_at=committed_at,
                                   report_parts=machine.get('report_parts'), final_basis=machine.get('final_answer_basis'))
    elif entry["name"] in ACCOUNTING_NODES:   # alpha.45: the execution report is committed; the answer node `Engine.final-answer` follows
        index["semantics"] = copy.deepcopy(payload.get("semantics"))
        _set_current(index, _planned_next(index, entry)["name"])
    else:
        _advance_after_business(store, index, program, entry, view, payload, status, frame_closed_at=frame_closed_at)
    _ledger_append(store, index, _ledger_commit_event(index, entry, visit, len(cache.get("continuations") or []), payload, machine, kind="commit"))   # alpha.22 E2
    if index["run_state"] in TERMINAL_STATES and index.get("accounting"):   # finalized in this transition: close the ledger, write the evidence block (E7)
        _close_evidence(store, index, committed_at, final_evidence, preserved_sha256=preserved_evidence_sha256)
    if frame and frame in index["call_stack"]:  # frame still open: refresh its manifest (close wrote the final one)
        _update_manifest(store, index, frame)
    if index["run_state"] == "RUNNING":
        nxt = _catalog_entry(index, index["current"]["name"])
        result["next"] = {"node": nxt["name"], "kind": nxt["kind"]}
    position = _track_position(index, entry, visit)
    next_node = result["next"]["node"] if result["next"] else None
    if entry["kind"] == "sub" and node_entry["status"] not in ("DEGRADED", "FAILED"):
        block = render.sub_receipt(position=position, node_id=entry["name"], order=node_entry.get("order") or 0, status=node_entry["status"],
                                   cache_sha256=node_entry["cache_sha256"], logical_tool_calls=node_entry["logical_tool_calls"],
                                   user_summary=payload["user_summary"], next_node=next_node, executor=executor, evidence_counts=counts,
                                   user_messages=payload.get("user_messages", []))   # alpha.94 (doc 220): the receipt shows the User Message
    else:
        steps_done = len(payload["steps"]["done"])
        steps_total = steps_done + len(payload["steps"]["remaining"]) + len(payload["steps"]["not_applicable"])
        block = render.node_block(position=position, node=entry["name"], kind=entry["kind"], status=node_entry["status"],
                                  cache_sha256=node_entry["cache_sha256"], committed_at=committed_at, elapsed_ms=node_entry["elapsed_ms"],
                                  logical_tool_calls=node_entry["logical_tool_calls"], user_summary=report_display,
                                  user_messages=payload.get("user_messages", []), artifacts=node_entry["artifacts"],
                                  anomalies=evidence_views.node_anomalies(payload, machine, list(_evidence_records(cache))[:-1]) + hsaw_gate.anomaly_lines(machine), next_node=next_node,
                                  next_kind=result["next"]["kind"] if result["next"] else None, module=node_entry.get("module"),
                                  executor=executor, explain=payload.get("explain"), steps_done=steps_done, steps_total=steps_total,
                                  process_verified=counts["verified_references"], evidence_counts=counts, gate_question_id=cache.get("gate"),
                                  user_message=run_input.get("user_message") if entry["kind"] != "engine" or entry["name"] == NODE_MATCH else None,   # alpha.23 R3
                                  user_language=index.get("user_language"))   # alpha.29: footer-aligned closing line
    if entry["name"] in ANSWER_NODES:   # alpha.45: no node block - the answer is the public output of this node
        result["public_block"], result["public_block_ref"] = None, None
    else:
        result["public_block"] = block
        block_name = f"node.{entry['ordinal'] + 1:02d}.{_safe_name(entry['name'])}.v{visit}.txt"
        store.write_public(block_name, block)
        result["public_block_ref"] = _ref(store, block_name)   # alpha.27 R1
        _, scope = _self_dispatch(index, entry, visit)
        if scope and scope.get('scope_root'):
            dispatch_scope.append_ref(scope, result['public_block_ref'])
            if result.get('dispatch'):
                result['dispatch'].update(dispatch_scope.view(scope, include_refs=result['dispatch']['closed']))
    if index["run_state"] == "COMPLETED":
        result["final_answer"] = _final_answer_text(store)
        result["final_answer_block"] = _final_block_text(store)   # alpha.23 R4: human_output_v5 envelope
        result["final_answer_ref"] = _ref(store, "final_answer.txt")   # alpha.27 R1
        result["evidence_block"] = _evidence_block_text(store)   # alpha.22 E7
        result["evidence_ref"] = _ref(store, "evidence.txt")
    elif index["run_state"] in ("FAILED", "ABANDONED"):
        result["error_report"] = _error_report(store, index)
        result["error_report_ref"] = _ref(store, "ended.txt")
    if index["run_state"] in TERMINAL_STATES:
        result.update(_terminal_delivery(store, index, result["public_block_ref"]))
    return result


def _advance_after_match(store, index, run_input, pre) -> None:
    now = now_iso()
    if pre.get("no_match"):
        index["route"].update({"package": NO_MATCH, "decided_at": now})
        index["catalog"] = index["catalog"][:1] + [program_loader.engine_entry(NODE_DIRECT, 1)]
        _set_current(index, NODE_DIRECT)
        return
    snap, program, analysis = pre["snap"], pre["program"], pre["analysis"]
    # Choose once, after package selection and before preflight; reloads consume this machine-owned choice.
    no_agent = program.loading_mode == 'node' and not _host_has_agent_tool(index)
    if no_agent:
        program.runtime_loading_mode = 'normal'
        rows, _ = dispatch_budget.requirements(program)
        zh = str(index.get('user_language')).startswith('zh')
        text = ('程序声明 node；宿主无 Agent 工具，本场使用 normal，由主代理 inline 执行全部节点；真实人类门仍停机等待答复。'
                if zh else 'Declared node; no host Agent tool: this run uses normal, all nodes execute main inline; real human gates still stop for a reply.')
        if rows:
            text += (' 独立执行未达成，相关工作由主代理完成，不声称独立盲评或新代理上下文。' if zh else
                     ' Independent execution not achieved; main performs the work without independent blind review or fresh-agent claims.')
        index['anomalies_summary'].append(dict(node=NODE_MATCH, code='HOST_NO_AGENT_TOOL', text=text))
    index["program"].update({"name": program.name, "entry_path": str(Path(snap["dir"]) / snap["entry_file"]), "entry_file": snap["entry_file"],
                             "trust_level": program.trust_level, "loading_mode": program.loading_mode,
                             "execution_loading_mode": program.execution_loading_mode,
                             "permissions_digest": program.permissions_digest(),
                             "checks": [{"code": f["code"], "severity": f["severity"], "detail": f["detail"]} for f in analysis["findings"]],
                             "skipped_files": analysis["skipped_files"]})
    index["program"]["governance"] = _program_governance(Path(snap["dir"]))   # alpha.22 E4: register, never reject
    if index["program"]["governance"].get("match") is False:
        index["anomalies_summary"].append({"node": NODE_MATCH, "code": "GOVERNANCE_HASH_MISMATCH",
                                           "text": f"{snap['package']}: computed canonical hash {index['program']['governance']['computed'][:16]}… != declared "
                                                   f"{index['program']['governance']['declared'][:16]}… (advisory; the program ran unchanged)"})
    index["route"].update({"package": snap["package"], "decided_at": now})
    run_input["routed"] = {"dir": snap["dir"], "entry_file": snap["entry_file"],
                           "execution_loading_mode": program.execution_loading_mode}
    _write_run_input(store, run_input)
    if analysis["fatal_count"]:
        _terminate(index, kind="fatal", by="engine", reason="program load checks failed (PROGRAM_INVALID)")
        return
    index["budget"] = _budget_for("business", program)
    index["catalog"] = index["catalog"][:1] + [program_loader.engine_entry(NODE_SETUP, 1)]
    _set_current(index, NODE_SETUP)


def _advance_after_setup(index, pre) -> None:
    if pre.get("fatal"):
        index["program"]["checks"].extend(pre["fatal"])
        _terminate(index, kind="fatal", by="engine", reason="; ".join(f"{f['code']}: {f['detail']}" for f in pre["fatal"]))
        return
    index["catalog"] = pre["catalog"]
    for c in pre["catalog"]:
        if c["kind"] == "business":
            index["nodes"].setdefault(c["name"], RunStore.new_node_entry(1))
    _dispatch_group(index)["policy"] = _dispatch_policy(index)   # doc 10 §2: decided once per run from program.loading_mode
    _set_current(index, pre["catalog"][2]["name"])


def _advance_after_business(store, index, program, entry, view, payload, status, *, frame_closed_at=None) -> None:
    """Cursor advance after a business or sub node commit; identical rules at every depth (doc 05 §4.2)."""
    graph = _graph_for(program, entry)
    frame = _frame_of(index, entry)
    ordinal = entry["ordinal"]
    coords = {"parent": frame["parent"], "parent_visit": frame["parent_visit"], "depth": entry["depth"], "order": frame["order"]} if frame else {}
    if status == "FAIL":
        hard = hsaw_gate.hard_fail_items(payload.get("hsaw_items"))
        if hard:   # alpha.87 (doc 193): a HARD_FAIL item ends the run; the program's error route is not taken
            if frame:
                _close_frame(store, index, frame, status="FAIL", reason=f"HSAW HARD_FAIL at {entry['name']}", closed_at=frame_closed_at)
            _terminate(index, kind="fatal", by="engine", reason=f"HSAW HARD_FAIL at {entry['name']}: " + "; ".join(str(it.get("title") or "") for it in hard))
            return
        handler = _error_handler(view, payload, index, entry)
        if handler and handler in graph["nodes"] and graph["node_types"].get(handler) != "end":
            new = _sibling_entry(entry, handler, ordinal + 1)
            _splice(index, ordinal, [new], drop_planned=True)
            index["anomalies_summary"].append({"node": entry["name"], "code": "ERROR_ROUTED", "text": f"-> {handler} ({payload.get('error_type') or 'default'})"})
            _set_current(index, new["name"], **coords)
            return
        if frame:  # unhandled failure inside a sub-graph: the module node decides (its Error clause / error edge)
            _close_frame(store, index, frame, status="FAIL",
                         reason=f"{entry['name']} FAILED without a handler in the sub-graph ({payload.get('error_type') or 'unspecified'})", closed_at=frame_closed_at)
            return
        _terminate(index, kind="assertion" if payload.get("error_type") == "assertion_error" else "fatal", by="engine",
                   reason=f"node {entry['name']} FAILED without error handler ({payload.get('error_type') or 'unspecified'})")
        return
    planned = _planned_next(index, entry)
    chosen = payload.get("next_hint") or _default_successor(program, view, planned, in_frame=frame is not None)
    is_end = chosen is None or graph["node_types"].get(chosen) == "end"
    if frame:
        if is_end:
            _close_frame(store, index, frame, status=None, reason=None, closed_at=frame_closed_at)
            return
        if planned and _bare(planned) == chosen:
            _set_current(index, planned["name"], **coords)
            return
        new = _sibling_entry(entry, chosen, ordinal + 1)
        _splice(index, ordinal, [new], drop_planned=True)
        _set_current(index, new["name"], **coords)
        return
    if chosen is None or (planned and planned["name"] == chosen):
        if planned is None:
            _splice(index, ordinal, [], drop_planned=True)
    elif is_end:
        _splice(index, ordinal, [], drop_planned=True)
    else:
        if planned and planned["kind"] == "business":
            index["anomalies_summary"].append({"node": entry["name"], "code": "PATH_REPLANNED", "text": f"planned {planned['name']} -> chosen {chosen}"})
        _splice(index, ordinal, [program_loader.business_entry(chosen, ordinal + 1)], drop_planned=True)
        if chosen==entry['name']:
            _set_current(index,chosen,**coords)
            return
    _set_current(index, _planned_next(index, entry)["name"])


def _error_handler(view: dict | None, payload: dict, index=None, entry=None) -> str | None:
    if not view:
        return None
    on_error = view["reserved"].get("on_error") if isinstance(view["reserved"].get("on_error"), dict) else {}
    from . import bounded_retry
    policy = view['reserved'].get('retry_policy')
    if isinstance(policy, dict) and policy.get('mode') == bounded_retry.MODE:
        return on_error.get(payload.get('error_type')) if bounded_retry.allowed(view['reserved'], payload, index, entry) else None
    etype = payload.get("error_type")
    if etype and etype in on_error:
        return on_error[etype]
    if "default" in on_error:
        return on_error["default"]
    return view["topology"].get("error_target")


def _splice(index: dict, ordinal: int, entries: list[dict], *, drop_planned: bool = False) -> None:
    """Insert catalog entries after the node at `ordinal` and the nested sub-graph entries that follow it.

    drop_planned: also drop what was planned after it in the SAME frame (deeper-or-equal depth, up to the
    next outer-frame entry or the engine summary) — a re-plan. Entries of outer frames and the engine
    summary are always kept; at depth 0 the summary is re-appended if it went missing. Ordinals renumbered.
    """
    from . import catalog_history
    catalog_history.remember(index)
    cat = index["catalog"]
    depth = cat[ordinal]["depth"]
    tail = ordinal
    while tail + 1 < len(cat) and cat[tail + 1]["depth"] > depth:
        tail += 1
    rest = cat[tail + 1:]
    if drop_planned:
        i = 0
        while i < len(rest) and rest[i]["kind"] != "engine" and rest[i]["depth"] >= depth:
            i += 1
        for dropped in rest[:i]:   # a re-plan: planned-only node records leave the index with their catalog entries
            key = _node_key(dropped["name"], 1)
            if key not in {e["name"] for e in entries} and index["nodes"].get(key, {}).get("status") == "PLANNED":
                del index["nodes"][key]
        rest = rest[i:]
    if depth == 0 and not any(e["name"] in REPORT_NODES for e in rest):
        rest = rest + [program_loader.engine_entry(_report_node(index), 0)]
    if depth == 0 and _report_node(index) in ACCOUNTING_NODES and not any(e["name"] in ANSWER_NODES for e in rest):   # alpha.45: the answer node follows the report
        rest = rest + [program_loader.engine_entry(LEGACY_FINAL if _report_node(index) == LEGACY_REPORT else NODE_FINAL, 0)]
    names={e['name'] for e in entries}
    prefix=catalog_history.without_previous_subtrees(cat[:tail+1],names)
    rest=catalog_history.without_previous_subtrees(rest,names)
    index["catalog"] = prefix + entries + rest
    for i, e in enumerate(index["catalog"]):
        e["ordinal"] = i


def _set_current(index: dict, name: str, *, parent: str | None = None, parent_visit: int | None = None,
                 depth: int = 0, order: int | None = None) -> None:
    if not any(e['name']==name for e in index['catalog']):
        raise EngineError('CURRENT_PLAN_ENTRY_MISSING','History is not a scheduling authority; stop before replaying an archived node.')
    visits = [c["visit"] for c in index["completed"] if c["name"] == name]
    visit = max(visits) + 1 if visits else 1
    index["current"] = {"name": name, "visit": visit}
    index["nodes"].setdefault(_node_key(name, visit), RunStore.new_node_entry(visit, parent=parent, parent_visit=parent_visit, depth=depth, order=order))


def _terminate(index: dict, *, kind: str, by: str, reason: str, rejection_report: dict | None = None, resume_prohibited: bool = True) -> None:
    index["run_state"] = "FAILED" if kind in ("fatal", "assertion", "timeout") else ("ABANDONED" if kind in ("rejection", "human_termination") else "COMPLETED")   # alpha.88: "cancelled" (a gate refusal closed by the report and the answer) is COMPLETED
    index["run_termination"] = {"kind": kind, "by": by, "at": now_iso(), "reason": reason,
                                "rejection_report": rejection_report, "resume_prohibited": resume_prohibited}


def _final_answer_basis(store, index, entry, visit, payload, machine):
    """Bind final provenance before writing the commit; replay uses this immutable snapshot."""
    mains, sources, evidence, exceptions, artifacts, decisions = [], [], [], [], [], []
    try:
        public_keys = {(c['node'], c['visit']) for c in _public_reference_caches(store, index)}
    except EngineError as exc:
        raise EngineError('FINAL_SOURCE_CHANGED', exc.message) from exc
    for key, state in index['nodes'].items():
        if not state.get('cache_sha256'):
            continue
        name, _, suffix = key.partition('@')
        node = _catalog_entry(index, name)
        if not node:
            raise EngineError('FINAL_SOURCE_CHANGED', 'cached occurrence is absent from the catalog')
        source_visit = int(suffix[1:]) if suffix else 1
        path = _cache_path_for(store, index, node, source_visit)
        if name == NODE_MATCH and not store.exists_path(path):
            path = store.node_cache_path('engine', name, source_visit)
        try:
            raw = store.read_bytes(path)
        except OSError as exc:
            raise EngineError('FINAL_SOURCE_CHANGED', f'accepted source is unavailable: {name}') from exc
        if sha256_bytes(raw) != state['cache_sha256']:
            raise EngineError('FINAL_SOURCE_CHANGED', f'accepted source cache changed: {name}', field='semantics.answer_details')
        data = strict_loads(raw.decode('utf-8'))
        source_ref = path.relative_to(store.cache_dir).as_posix()
        source = dict(source_ref=source_ref, source_sha256=state['cache_sha256'])
        sources.append(name)
        if dispatch_scope.is_main(index, node) and (name, source_visit) in public_keys:
            mains.append(dict(node=name, visit=source_visit, **source))
        for revision, record in enumerate(_evidence_records(data)):
            prefix = '#/payload' if revision == 0 else f'#/continuations/{revision - 1}/payload'
            _collect_final_records(record['payload'], record['machine'], dict(source, source_ref=source_ref + prefix),
                                   evidence, exceptions, artifacts)
    # Use executed order, including distinct visits, not dictionary insertion order or planned nodes.
    order = {(row['name'], row['visit']): i for i, row in enumerate(index['completed'])}
    mains.sort(key=lambda row: order.get((row['node'], row['visit']), len(order)))
    current_ref = _cache_path_for(store, index, entry, visit).relative_to(store.cache_dir).as_posix()
    prior = store.read_json(store.cache_dir / current_ref) if store.exists_path(store.cache_dir / current_ref) else None
    pointer = f"#/continuations/{len(prior.get('continuations') or [])}/payload" if prior else '#/payload'
    _collect_final_records(payload, machine, dict(source_ref=current_ref + pointer, source_sha256=None),
                           evidence, exceptions, artifacts)
    for event in index['anomalies_summary']:
        exceptions.append(dict(source_ref='_index.json#/anomalies_summary', source_sha256=None,
                                kind='run_observation', record=copy.deepcopy(event)))
    from . import tool_faults
    exceptions.extend(dict(source_ref=row['source_ref'],source_sha256=row['source_sha256'],
                           kind='machine_recovery',record=row) for row in tool_faults.report_diagnostics(store.cache_dir))
    if dispatch_lifecycle.replacement_accounting(index):
        exceptions.append(dict(source_ref='engine:recovery_diagnostic_summary', source_sha256=None,
                               kind='recovery_counts', record=recovery_diagnostic_summary(store.cache_dir, index)))
    attempts = evidence_views.protocol_attempts(store.cache_dir)
    for row in attempts['records']:
        exceptions.append(dict(source_ref=row['file'], source_sha256=row['sha256'],
                               kind='protocol_commit_failure', record=row))
    for row in attempts['unreadable']:
        exceptions.append(dict(source_ref='_work/replies/' + row['file'], source_sha256=None,
                               kind='protocol_receipt_unreadable', record=row))
    for event in index['gate']['history']:
        if event.get('resolution_kind') not in ('chosen', 'free_text'):
            continue
        path = store.gate_path(event['question_id'])
        raw = store.read_bytes(path)
        rec = strict_loads(raw.decode('utf-8'))
        fields = ('question_id', 'node', 'visit', 'question', 'answer_text', 'chosen', 'chosen_intent', 'answered_at', 'by',
                  'replacement_refused')   # review of docs/05SoulRun 87, round 2 (N2): a retired stop replaced nothing
        # A summary gate is consumed after its commit lands; its mutable file cannot carry a final raw-byte claim yet.
        mutable = rec.get('node') == entry['name'] and rec.get('visit') == visit
        decisions.append(dict(source_ref=path.relative_to(store.cache_dir).as_posix(), source_sha256=None if mutable else sha256_bytes(raw),
                              kind='human_gate_answer', record=dict({key: rec[key] for key in fields if key in rec},
                                                                    # round 3 (D2): derived from the dispatch records, not the file
                                                                    **_unused_replacement(store, index, rec),
                                                                    **_moved_on(store, index, rec))))   # docs/05SoulRun 88 (K1)
    basis = dict(main_nodes=mains,
                 evidence=final_answer.records(evidence, ['accepted_node_payloads.evidence'], ['external_sources_not_revalidated']),
                 exceptions=final_answer.records(exceptions, ['node_revisions', 'index.anomalies_summary', 'archived_commit_replies'], ['provider_events']),
                 artifacts_changes=final_answer.records(artifacts, ['declared_artifacts_and_engine_file_observations'], ['unreported_side_effects']),
                 human_decisions=final_answer.records(decisions, ['resolved_gate_history'], ['off_channel_authorization']))
    try:
        details = (payload.get('semantics') or {}).get('answer_details')
        answer = _compose_answer(payload, machine.get('report_parts'))   # alpha.42 E1: validate the delivered composition
        business = _compose_answer(payload, [p for p in machine.get('report_parts') or [] if p.get('node') not in ACCOUNTING_NODES])   # alpha.85: excerpts cover the business answer, not the appended execution report
        final_answer.validate_details(details, business, mains, sources)
        final_answer.assemble(answer, index.get('user_language') or 'zh', basis, details)   # alpha.60 (doc 130 §4 d; cache/96): a run whose message had no detectable language ("1") assembled with None and rejected its own artifact
    except ValueError as exc:
        raise EngineError('FINAL_DETAILS_INVALID', str(exc), field='semantics.answer_details') from exc
    return basis


def _collect_final_records(payload, machine, source, evidence, exceptions, artifacts):
    payload_ref = source['source_ref']
    machine_ref = payload_ref.removesuffix('/payload') + '/machine'
    if machine.get('source_support'):
        evidence.append(dict(source, source_ref=machine_ref + '/source_support', kind='captured_source_support',
                             record=copy.deepcopy(machine['source_support'])))
    for kind, items in (payload.get('evidence') or {}).items():
        if kind == 'artifacts':
            continue
        for n, item in enumerate(items):
            evidence.append(dict(source, source_ref=f'{payload_ref}/evidence/{kind}/{n}', kind=kind, record=copy.deepcopy(item)))
    for origin, items in ((payload_ref + '/anomalies', payload.get('anomalies') or []),
                          (machine_ref + '/engine_anomalies', machine.get('engine_anomalies') or [])):
        for n, item in enumerate(items):
            exceptions.append(dict(source, source_ref=f'{origin}/{n}', kind='recorded_exception', record=copy.deepcopy(item)))
    if payload.get('degraded_reason'):
        exceptions.append(dict(source, source_ref=payload_ref + '/degraded_reason', kind='degraded_reason', record=payload['degraded_reason']))
    declared = (payload.get('evidence') or {}).get('artifacts', [])
    observed = machine.get('artifacts') or []
    if declared or observed:
        artifacts.append(dict(source, source_ref=payload_ref + '/evidence/artifacts', kind='artifact_observation',
                              record=dict(declared=copy.deepcopy(declared), observed=copy.deepcopy(observed),
                                          observation_ref=machine_ref + '/artifacts')))


NO_MATCH_NOTICE = {   # docs/05SoulRun 90 (problem 55; decisions 143, 182, 186): the first line of a no_match run's direct answer
    "zh": "指定或扫描到的程序（{names}）里没有匹配这个请求的，下面直接回答。",
    "en": "None of the designated or scanned programs ({names}) matches this request; it is answered directly below.",
}
NO_MATCH_NOTICE_NAMES = 8


def _no_match_notice(index: dict) -> str:
    """The candidates this run had (route.snapshot: the designated programs, or the ones scanned), named up to
    NO_MATCH_NOTICE_NAMES; the machine puts it ahead of the direct answer - no gate, no other change. Decisions 182, 186:
    Chinese only when user_language starts with 'zh' (any case: 'zh', 'zh-CN', 'ZH-tw'); English for every other value -
    'en', 'ja', 'ko', 'fr', ... and an unset one (None or empty). render.detect_language counts only CJK and Latin letters,
    so a first message with neither (Russian, Arabic, Greek, Thai, Hindi or Hebrew alone, or only digits, symbols or emoji)
    records no language and gets English. Only this line: hsaw_gate._lang keeps its own rule elsewhere (problem 96)."""
    lang = "zh" if str(index.get("user_language") or "").lower().startswith("zh") else "en"
    names = [str(n) for n in (index.get("route") or {}).get("snapshot") or []]
    shown, rest = names[:NO_MATCH_NOTICE_NAMES], len(names) - NO_MATCH_NOTICE_NAMES
    if lang == "zh":
        listed = "、".join(shown) + (f" 等共 {len(names)} 个" if rest > 0 else "")
    else:
        listed = ", ".join(shown) + (f" and {rest} more" if rest > 0 else "")
    return NO_MATCH_NOTICE[lang].format(names=listed)


def _finalize(store, index, payload, program=None, *, committed_at=None, report_parts=None, final_basis=None) -> dict:
    now = committed_at or now_iso()
    nodes = index["nodes"]
    timeout_ms = _program_timeout_ms(program)
    wall = _ms_between(index["started_at"], now) or 0
    human_wait_total = sum(v["human_wait_ms"] or 0 for v in nodes.values())
    active_wall = max(0, wall - human_wait_total)   # alpha.22 (doc 43 §4.3): the human's deliberation is not the program's time
    if timeout_ms and active_wall > timeout_ms:
        index["anomalies_summary"].append({"node": NODE_SUMMARY, "code": "RUN_TIMEOUT_ADVISORY",
                                           "text": f"active wall {active_wall} ms (wall {wall} ms minus human wait {human_wait_total} ms) > program runtime.timeout_seconds {timeout_ms // 1000} s (AIAP §19; advisory)"})
    business_keys = [k for k in nodes if (_catalog_entry(index, k.split("@")[0]) or {}).get("kind") in ("business", "sub")]
    degraded = [k for k in business_keys if nodes[k]["status"] == "DEGRADED"]
    failed = [k for k in business_keys if nodes[k]["status"] == "FAILED"]
    from . import catalog_history
    definitions=catalog_history.definitions(index)
    sub_entries = [c for c in definitions if c["kind"] in ('business', 'sub') and not dispatch_scope.is_main(index, c)]
    sub_names = {c["name"] for c in sub_entries}
    index["accounting"] = {
        "engine_version": ENGINE_VERSION, "run_started_at": index["started_at"], "run_ended_at": now,
        "wall_ms": _ms_between(index["started_at"], now), "nodes_total": len(definitions),
        "nodes_committed": len(index["completed"]), "nodes_degraded": len(degraded), "nodes_failed": len(failed),
        "logical_tool_calls_total": sum(v["logical_tool_calls"] for v in nodes.values()),
        "sources_total": sum(v["sources_count"] for v in nodes.values()),
        "artifacts_total": sum(len(v["artifacts"]) for v in nodes.values()),
        "gates_presented": len([h for h in index["gate"]["history"] if h["resolution_kind"] != "invalid_retry"]),
        "human_wait_ms_total": sum(v["human_wait_ms"] or 0 for v in nodes.values()),
        "active_elapsed_ms_total": sum(v["active_elapsed_ms"] or 0 for v in nodes.values()),
        "sub_nodes_total": len(sub_entries),
        "max_depth": max([0] + [c["depth"] for c in definitions]),
        # docs/05SoulRun 87: the sub_nodes_total basis (is_main), not "a '/' in the name" - a main-file module's nodes are main
        "sub_anomalies_total": sum(1 for a in index["anomalies_summary"] if a["node"] in sub_names),
        "anomalies_by_code": evidence_views.code_counts(index["anomalies_summary"]),   # docs/05SoulRun 87: run index scope
        # doc 10 §4: executor accounting (agent_nodes = outer occurrences that were dispatched or declared agent)
        "dispatch_policy": _dispatch_group(index).get("policy"),
        "agent_nodes": sum(1 for v in nodes.values() if (v.get("dispatch") or {}).get("mode") == "agent"),
        "tickets_issued": _dispatch_group(index)["tickets_issued"],
        "spawns_claimed": _dispatch_group(index)["spawns_claimed"],
        "agent_fallbacks": _dispatch_group(index)["fallbacks"],
        "spawn_hard_limit": SPAWN_HARD_LIMIT,
        "ordinary_spawns_claimed": dispatch_budget.usage(index, 'ordinary'),
        "independent_spawns_claimed": dispatch_budget.usage(index, 'independent'),
        "independent_hard_limit": dispatch_budget.limit(index, 'independent'),
        "independent_base_limit": dispatch_budget.summary(index)['base_limit'],
        "independent_budget_added": dispatch_budget.summary(index)['added'],
    }
    ev = _evidence_summary(store, index)   # alpha.22 E7: evidence counters + the public evidence block
    if dispatch_budget.resume_accounting(index) and _dispatch_group(index).get('ordinary_resumes_claimed'):
        index['accounting']['ordinary_resumes_claimed'] = _dispatch_group(index)['ordinary_resumes_claimed']
    index["accounting"].update({
        "evidence_process_calls": ev["counts"]["process_references"],
        "evidence_process_verified": ev["counts"]["verified_references"],
        "evidence_counting_basis": ev["counts"]["basis"],
        "evidence_unique_outputs": ev["counts"]["unique_outputs"],
        "evidence_unique_verified": ev["counts"]["unique_verified"],
        "evidence_repeated_references": ev["counts"]["repeated_references"],
        "evidence_unknown_identity_references": ev["counts"]["unknown_identity_references"],
        "evidence_conflicting_paths": ev["counts"]["conflicting_paths"],
        "evidence_cross_scope_reuses": ev["counts"]["cross_scope_reuses"],
        "physical_business_tool_calls": None,
        "evidence_artifacts": len(ev["artifacts"]), "evidence_sources": len(ev["sources"]),
        "evidence_governance_match": (index["program"].get("governance") or {}).get("match"),
        "evidence_events": 0, "evidence_ledger_sha256": None,
    })
    semantics = payload.get("semantics")
    if payload['node'] not in ANSWER_NODES:   # alpha.45: at `Engine.final-answer` the accounting stored by Engine.execute-report's commit stays as it is
        index["semantics"] = ({k: v for k, v in semantics.items() if k != 'final_answer'}
                              if payload['node'] in ACCOUNTING_NODES and semantics else semantics)
    text = _compose_answer(payload, report_parts)   # alpha.42 E1: lead + referenced reports verbatim
    if payload['node'] == NODE_DIRECT and index['route'].get('package') == NO_MATCH:   # docs/05SoulRun 90 (problem 55, decision 143)
        text = _no_match_notice(index) + "\n\n" + text
    if degraded and payload['node'] not in (*ACCOUNTING_NODES, *ANSWER_NODES):
        lines = []
        for k in degraded:
            name, _, v = k.partition("@")
            path = _cache_path_for(store, index, _catalog_entry(index, name), int(v[1:]) if v else 1)
            reason = None
            try:
                reason = _latest_payload(store.read_json(path)).get("degraded_reason")
            except RunStoreError:
                pass
            lines.append(f"DEGRADED: {name} — {reason or 'degraded without a recorded reason'}")
        text = text.rstrip("\n") + "\n\n" + "\n".join(lines)
    if final_basis is not None:
        artifact = final_answer.assemble(text, index.get('user_language') or 'zh', final_basis,   # alpha.60: same fallback as the basis check
                                         (payload.get('semantics') or {}).get('answer_details'))
        store.ensure_final_artifact(artifact)
    index["final_answer_sha256"] = store.ensure_final_answer(text)
    semantics = payload.get('semantics') or {}
    index["final_answer_metrics"] = {"chars": len(text), "lead_chars": len(_answer_body(payload)), "report_parts": len(semantics.get('report_parts') or []),
                                     "coverage": len((semantics.get('answer_details') or {}).get('coverage') or [])}   # alpha.47 (doc 93): observability, never a gate
    cancelled = index.get("cancelled")   # alpha.88 (doc 196 F4'): the run the human cancelled at a gate still closes with its report and answer
    _terminate(index, kind="cancelled" if cancelled else ("degraded" if degraded else "success"), by="engine",
               reason=f"final answer written after the human cancelled at gate {cancelled['question_id']} ({cancelled['node']})" if cancelled else "final answer written",
               resume_prohibited=True)
    index["run_termination"]["at"] = now
    store.write_public_snapshot("final_answer.txt", render.final_block(text, index.get("user_language")))
    return ev


# ---------------------------------------------------------------------------
# gate-answer (host only)
# ---------------------------------------------------------------------------

_UNSHOWN_STOP_HINT = ('Not taken as an answer: the human has not been shown this question yet (it was never served to the main '
                      'executor and never delivered); nothing was answered or authorized. The main agent\'s next-node serves it: '
                      'present that menu and wait for the human\'s answer.')


def _unshown_stop(store, index, rec) -> bool:
    """docs/05SoulRun 90 rounds 4 and 5 (problems 90 and 95, ledger decisions 184 and 185): True while the open gate `rec` -
    an engine stop (a dispatch stop, dispatch_budget.pause; the program-integrity stop, program_guard.pause) or a business gate
    (_pause_with_gate) - has not reached the human: never served to the main executor and never marked delivered. Served to
    the main executor: its _public/menu.<qid>.* exists. Where that is written:
    - an engine stop: only by a serve to the main executor - dispatch_budget.reply and program_guard.reply with publish, from
      next-node, node-commit and the interpretation command with no agent ticket. Unpublished: a serve to a sub-agent (an
      agent ticket's next-node or node-commit, record 90 round 4 B1 and round 5), and every stop opened or installed inside
      gate-answer, whose reply through prepare reaches no model - _show_integrity_stop, the drift paths below, and
      dispatch_budget._ask_again's stop asked again (round 5 B5);
    - a business gate: by _finish_pause at the main executor's own pause (node-commit with no agent ticket, or partial_commit's
      re-application of it, whichever call recovers it). At a sub-agent's pause (an agent ticket: the machine's dispatch actor
      'sub_agent', its partial_commit re-application included) _finish_pause writes everything but the menu - record 90
      round 7, ledger decision 187 (a): a gate only a sub-agent was given has not been shown. In node loading mode, the only
      mode that dispatches, its menu's reference is among the ordered public_refs the sub-agent returns. Ledger decision 189
      (record 90, the contract resume.dispatch_segments): the main executor calls next-node once before presenting any of
      them, and that waiting serve writes the menu, under the name that reference gives (_show_unshown_gate, which also
      publishes a pause that died before its menu) - SoulRun decides it in every host. Decision 193 removes the earlier
      host-return publication: a return records lifecycle facts only, not presentation. A sub-agent's business pause is
      shown at the main executor's next-node. The engine before these rounds wrote the menu on every serve.
    Marked delivered: mark_delivered (gate_answer.py --mark-delivered, the after-turn
    observer) in the record or the index. Such a gate is left by an unpublished serve, or by the process dying after the
    gate's index write and before its menu - pause()'s reply, problem 85's re-install (next-node's, or answer_gate's below),
    _finish_pause. A message to it is no answer (answer_gate, _not_shown); the main executor's next-node shows it. The
    moment between the main serve writing a menu and the main executor presenting it is not covered: a death there
    counts as shown. A host return before that main serve does not enter this window."""
    qid = rec['question_id']
    return not (rec.get('delivered_at') or index['gate'].get('delivered_at') or any(store.public_dir.glob(f'menu.{qid}.*')))


def _not_shown(rec) -> dict:
    """answer_gate's reply to a message at a gate `rec` not yet shown (_unshown_stop): nothing written, answered or authorized;
    the main agent's next-node serves the gate - an engine stop's first serve, a business gate published then (problem 95)."""
    return dict(status='WAITING_USER', question_id=rec['question_id'], run_state='WAITING_USER', answer_valid=False,
                conditions_satisfied=False, answer_hint=_UNSHOWN_STOP_HINT, next=None)


def _restore_pause_block(store, index, gate) -> None:
    """Rebuild only the accepted pause body, never publish a superseded menu."""
    qid = gate['question_id']
    if _pause_ref(store, qid) is None:
        entry, visit = _catalog_entry(index, gate['node']), gate['visit']
        cache = store.read_json(_cache_path_for(store, index, entry, visit)) if entry else {}
        last = (cache.get('continuations') or [cache])[-1] if cache else {}
        if (last.get('machine') or {}).get('paused_gate') == qid:
            _pause_block(store, index, entry, visit, last['payload'], index['nodes'][_node_key(entry['name'], visit)],
                         last['machine'].get('dispatch'), qid, gate['presented_at'])


def _show_unshown_gate(store, index, gate) -> None:
    """docs/05SoulRun 90 round 5 (problem 95, ledger decision 185): the business gate `gate` the run waits at, never shown
    (_unshown_stop), published at the main executor's serve as _finish_pause publishes it - its ⏸ node info when that is
    missing too, rebuilt from the paused commit in the node cache (_pause_block, at the instant the gate was presented), then
    its menu. The index and every record are left as they are. Also a sub-agent's pause, which writes no menu, here -
    the main executor's next-node before it presents the returned gate (decisions 189 and 193); a host return cannot
    publish it. Its reference is already among the
    scope's ordered public_refs, under the name this write gives it (_menu_ref)."""
    qid = gate['question_id']
    _restore_pause_block(store, index, gate)
    store.write_public(f"menu.{qid}.txt", render.menu_block(gate, user_language=index.get("user_language")))


def _show_integrity_stop(store, index, rec, question_id, answer_text, by) -> dict:
    """docs/05SoulRun 90 round 4 (problems 90 and 91, ledger decision 184): the program-integrity stop `rec` the human has not
    been shown takes no answer. Where it paused a business gate and the message is the human's answer to that gate (it names
    that gate), the message is kept as the stop's deferred_business_answer, exactly as answer_gate's drift path keeps it for
    the stop it opens there - once. Over an engine stop nothing is kept: an authorisation is never deferred past a program
    change (problem 92). The reply is the stop's own (pause()'s), unpublished (record 90 round 5, ledger decision 185):
    through prepare it reaches no model, so the stop stays not shown and the main executor's next-node gives it its first
    published serve; the human answers it on a later turn."""
    prior = rec.get('previous_gate') or {}
    if rec.get('previous_run_state') == 'WAITING_USER' and prior.get('question_id') == question_id \
            and 'deferred_business_answer' not in rec:
        try:
            paused = store.read_json(store.gate_path(question_id))
        except (OSError, ValueError, RunStoreError):
            paused = None
        if isinstance(paused, dict) and not (paused.get('program_drift') or paused.get('dispatch_block')):
            rec['deferred_business_answer'] = dict(question_id=question_id, text_original=answer_text, by=by, at=now_iso())
            _write_json(store.gate_path(rec['question_id']), rec)
    return program_guard.reply(store, index, rec, publish=False)


def answer_gate(cache_dir: str | Path, question_id: str, answer_text: str, *, by: str = "host") -> dict:
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        # docs/05SoulRun 90 round 4 (problem 91, ledger decision 184): an engine stop cut off before its index write is installed
        # first, as next-node and node-commit install it (dispatch_budget.reinstall); it is then a stop not yet shown (below)
        dispatch_budget.reinstall(store, index)
        run_input = _read_run_input(store)
        integrity_gate = program_guard.record(store, index)
        if integrity_gate:
            if _unshown_stop(store, index, integrity_gate):    # problems 90 and 91: shown first, never answered unseen
                return _show_integrity_stop(store, index, integrity_gate, question_id, answer_text, by)
            return program_guard.answer(store, index, integrity_gate, question_id, answer_text, by)
        from . import dispatch_identity
        identity_gate = dispatch_identity.record(store, index)
        if not identity_gate and index['run_state'] in ('RUNNING', 'WAITING_USER'):
            pending = next((r for r in reversed(index['gate']['history'])
                            if r['question_id'] == question_id and not r.get('answered_at')), None)
            if pending:
                candidate = store.read_json(store.gate_path(question_id))
                if candidate.get('identity_handoff') and store.exists_path(
                        dispatch_identity._authorization_path(store, question_id)):
                    identity_gate = candidate
        if identity_gate:
            if question_id != identity_gate['question_id']:
                return dict(status='WAITING_USER', question_id=identity_gate['question_id'], answer_valid=False,
                            run_state='WAITING_USER', reason='GATE_MISMATCH')
            if _unshown_stop(store, index, identity_gate):
                return _not_shown(identity_gate)
            option = _match_option(identity_gate['options'], (answer_text or '').strip())
            if option and option['intent'] == 'identity_stop' and not store.exists_path(
                    dispatch_identity._authorization_path(store, identity_gate['question_id'])):
                return dispatch_identity.answer(store, index, identity_gate, answer_text, by)
            try:
                _load_routed_program(run_input)
            except EngineError as exc:
                if exc.code != 'PROGRAM_DRIFT_DETECTED':
                    raise
                return program_guard.pause(store, store.read_index(), exc, publish=False)
            return dispatch_identity.answer(store, index, identity_gate, answer_text, by)
        blocked_dispatch = dispatch_budget.record(store, index)
        if blocked_dispatch:
            if _unshown_stop(store, index, blocked_dispatch):
                # problem 90: nothing is written, so the main agent's next-node gives the stop its first serve - pause()'s
                # reply (dispatch_budget.served) - and the human answers it on a later turn
                return _not_shown(blocked_dispatch)
            try:
                return dispatch_budget.answer(store, index, blocked_dispatch, question_id, answer_text, by)
            except EngineError as exc:
                # problem 92 (ledger decision 184): the program changed - the integrity stop opens over the dispatch stop, as
                # over a business gate below; the dispatch answer is neither applied nor kept, and once the integrity stop
                # is resolved the dispatch stop is served again and answered afresh. Round 5 (ledger decision 185): opened
                # inside gate-answer, unpublished - the main executor's next-node gives it its first published serve
                if exc.code != 'PROGRAM_DRIFT_DETECTED':
                    raise
                return program_guard.pause(store, store.read_index(), exc, publish=False)
        if index['run_state'] == 'WAITING_USER' and index['gate'].get('state') == 'WAITING_USER' \
                and index['gate'].get('question_id') == question_id:
            # docs/05SoulRun 90 round 5 (problem 95, ledger decision 185): the business gate the message answers was never
            # shown - nothing is written, answered or kept; the main agent's next-node publishes it (_show_unshown_gate)
            rec = store.read_json(store.gate_path(question_id))
            if _unshown_stop(store, index, rec):
                return _not_shown(rec)
        previous = store.gate_path(question_id)
        if re.fullmatch(r'q\d+-[0-9a-f]+', question_id) and previous.exists():
            rec = store.read_json(previous)
            if (rec.get('program_drift') or rec.get('dispatch_block')) and rec.get('answered_at'):
                return dict(status='ALREADY_ANSWERED', question_id=question_id, run_state=index['run_state'])
        try:
            program = _load_routed_program(run_input) if index['run_state'] not in TERMINAL_STATES else None
            return _answer_locked(store, index, program, question_id, answer_text, by)
        except EngineError as exc:
            if exc.code == 'PROGRAM_DRIFT_DETECTED':
                # round 5 (ledger decision 185): opened inside gate-answer, unpublished, as above
                result = program_guard.pause(store, index, exc, publish=False)
                rec = program_guard.record(store, index)
                rec['deferred_business_answer'] = dict(question_id=question_id, text_original=answer_text, by=by, at=now_iso())
                _write_json(store.gate_path(rec['question_id']), rec)
                return result
            return {"status": "REJECTED", "question_id": question_id, "run_state": index["run_state"], "errors": [exc.as_dict()],
                    "help": _HELP.get(exc.code, "")}


def mark_delivered(cache_dir: str | Path, question_id: str) -> dict:
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        if index["gate"]["question_id"] != question_id:
            raise EngineError("GATE_MISMATCH", f"active gate is {index['gate']['question_id']!r}")
        rec_path = store.gate_path(question_id)
        rec = store.read_json(rec_path)
        indexed, recorded = index['gate']['delivered_at'], rec.get('delivered_at')
        if indexed and recorded and indexed != recorded:
            raise EngineError('DELIVERY_EVIDENCE_CONFLICT', 'index and gate record disagree')
        delivered = recorded or indexed
        if delivered and indexed == recorded:
            return {"status": "DELIVERED", "question_id": question_id, "delivered_at": delivered}
        if index['run_state'] != 'WAITING_USER' or index['gate']['state'] != 'WAITING_USER' \
                or rec.get('answered_at') or index['gate'].get('answered_at'):
            raise EngineError('RUN_STATE_FORBIDS_COMMIT', 'delivery may only be recorded while waiting for this answer')
        # Recover a record-first partial write without inventing a later delivery time.
        delivered = delivered or now_iso()
        if recorded != delivered:
            rec['delivered_at'] = delivered
            _write_json(rec_path, rec)
        if indexed != delivered:
            index['gate']['delivered_at'] = delivered
            _write_index(store, index)
        return {"status": "DELIVERED", "question_id": question_id, "delivered_at": delivered}


def _match_option(options: list[dict], text: str, *, engine_aliases: bool = False) -> dict | None:
    t = text.strip()
    low = t.lower()
    if re.fullmatch(r"\d+", t):
        i = int(t)
        return options[i - 1] if 1 <= i <= len(options) else None
    for opt in options:
        if low == opt["label"].strip().lower() or low == opt["intent"].lower():
            return opt
    if engine_aliases:
        for opt in options:
            if low in [a.lower() for a in opt.get("aliases", [])]:
                return opt
    return None


def check_write_target(cache_dir, target, *, purpose='artifact'):
    store = RunStore(cache_dir)
    with store.lock():
        index = store.read_index()
        program_guard.assert_run_version(index)
        program = _load_routed_program(_read_run_input(store))
        if program is None:
            raise EngineError('PROGRAM_INVALID', 'Select the executing program before declaring a write target.')
        return program_guard.check_write_target(target, program.dir, purpose=purpose, cache_dir=store.cache_dir)


def _cancel_where(cancelled: dict) -> tuple[str, list]:
    """alpha.88 / alpha.100: where the human cancelled and the planned nodes that did not run (the rule text and node_facts.cancelled)."""
    label = cancelled.get("chosen_label") or cancelled.get("answer_text") or "cancel"
    return f"gate {cancelled['question_id']} on {cancelled['node']} ({label!r})", list(cancelled.get("dropped_nodes") or [])


def _cancelled_rule(cancelled: dict, *, report: bool) -> str:
    """alpha.88 (doc 196 F4'): what Engine.execute-report / Engine.final-answer are told after the human cancelled at a gate."""
    where, dropped = _cancel_where(cancelled)
    if report:
        return (_contracts.text("execute-report.cancelled", where=where, dropped_count=len(dropped), dropped=dropped))
    return (_contracts.text("final-answer.cancelled", where=where, dropped=dropped))


def _cancel_to_report(store, index: dict, entry: dict, key: str, question_id: str, option: dict | None, text: str, now: str) -> list[str]:
    """alpha.88 (doc 196 F4', user ruling 2026-09-22): a cancel answered on a business / sub node without a confirm_rejected route no longer
    abandons the run. The gated node is FAILED (its action did not happen), every open sub-graph frame is closed FAIL, every planned
    business / sub node after the cancel point is dropped and the cursor moves to Engine.execute-report: the report and the answer are
    still written and the run ends COMPLETED with run_termination.kind "cancelled". Returns the names of the dropped nodes."""
    node, visit = entry["name"], index["current"]["visit"]
    keep, dropped = [], []
    for e in index["catalog"]:
        state = index["nodes"].get(_node_key(e["name"], 1)) or {}
        if e["ordinal"] <= entry["ordinal"] or e["kind"] == "engine" or state.get("cache_sha256") or state.get("committed_at"):
            keep.append(e)
            continue
        dropped.append(e["name"])
        if state.get("status") in (None, "PLANNED"):
            index["nodes"].pop(_node_key(e["name"], 1), None)
    index["catalog"] = keep
    report = _report_node(index)
    if not any(e["name"] in REPORT_NODES for e in index["catalog"]):
        index["catalog"].append(program_loader.engine_entry(report, 0))
    if report in ACCOUNTING_NODES and not any(e["name"] in ANSWER_NODES for e in index["catalog"]):
        index["catalog"].append(program_loader.engine_entry(LEGACY_FINAL if report == LEGACY_REPORT else NODE_FINAL, 0))
    for i, e in enumerate(index["catalog"]):
        e["ordinal"] = i
    reason = f"cancelled by the human at gate {question_id} ({node})"
    close_dispatch_tickets(store, index, reason)
    frames_closed = []
    while index["call_stack"]:
        frame = index["call_stack"][-1]
        pkey = _node_key(frame["parent"], frame["parent_visit"])
        _close_frame(store, index, frame, status="FAIL", reason=reason)
        index["nodes"][pkey]["status"] = "FAILED"
        frames_closed.append(frame["parent"])
    index["nodes"][key]["status"] = "FAILED"
    index["completed"].append({"name": node, "visit": visit})
    index["cancelled"] = {"node": node, "visit": visit, "question_id": question_id, "chosen_label": option["label"] if option else None,
                          "answer_text": text, "at": now, "dropped_nodes": dropped, "frames_closed": frames_closed}
    index["anomalies_summary"].append({"node": node, "code": "CONFIRM_REJECTED_TO_REPORT", "text": f"-> {report}; {len(dropped)} planned node(s) dropped"})
    _set_current(index, report)
    index["run_state"] = "RUNNING"
    return dropped


def close_dispatch_tickets(store, index, reason):
    """Cancellation revokes write authority; it does not attest to Agent exit."""
    for ne in index['nodes'].values():
        d = ne.get('dispatch')
        if d and (d.get('state') in {'ISSUED','CLAIMED'} or (d.get('state') == 'ABANDONED' and not d.get('closed_reason'))):
            _record_ticket_state(store, d, 'ABANDONED', closed_reason=reason, closed_at=now_iso())
        elif d and d.get('state') == 'ABANDONED':
            # A prior identity fence closed the index; reconcile its ticket projection too.
            _record_ticket_state(store, d, 'ABANDONED', preserve_equal=True)


def _answer_locked(store, index, program, question_id, answer_text, by, *, _choice=None, _recorded=None, _delivery=None) -> dict:
    if index["run_state"] != "WAITING_USER":
        raise EngineError("RUN_STATE_FORBIDS_COMMIT", f"run is {index['run_state']}, no gate is waiting", field="$")
    if index["gate"]["question_id"] != question_id:
        raise EngineError("GATE_MISMATCH", f"active gate is {index['gate']['question_id']!r}", field="question_id", expected=index["gate"]["question_id"])
    ticket = next((t for t in index["tickets"] if t["question_id"] == question_id), None)
    if not ticket or ticket["state"] != "READY":
        raise EngineError("TICKET_NOT_READY", f"ticket state {ticket['state'] if ticket else 'missing'}", field="question_id")
    rec_path = store.gate_path(question_id)
    rec = store.read_json(rec_path)
    now = _delivery['answered_at'] if _delivery else now_iso()
    restoring_conditional = rec.get('resolution_kind') == 'free_text' and conditional_reply.pending(rec) and rec.get('answered_at')
    if _recorded is not None:
        if rec != _recorded or not rec.get('answered_at') or rec.get('answer_text_original') != answer_text or rec.get('answered_by') != by:
            raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'Only the unchanged already-recorded human reply may be recovered.')
        now = rec['answered_at']
    if restoring_conditional:
        answer_text, by, now = rec['answer_text_original'], rec['answered_by'], rec['answered_at']
    text = (answer_text or "").strip()
    low = text.lower()
    history = next(h for h in reversed(index["gate"]["history"]) if h["question_id"] == question_id and h["resolution_kind"] != "invalid_retry")
    node, visit = rec["node"], rec["visit"]
    key = _node_key(node, visit)
    entry = _catalog_entry(index, node)

    def persist(resolution: str, chosen: dict | None):
        delivered = rec.get("delivered_at") or index["gate"]["delivered_at"]
        if _delivery and not (restoring_conditional or _recorded is not None):
            delivered = _delivery['delivered_at']
            rec['delivered_via_question_id'] = _delivery['question_id']
        wait = _ms_between(delivered, now) if delivered else None
        rec.update({"answered_at": now, "answer_text": text, "answer_text_original": answer_text or '', "resolution_kind": resolution,
                    "chosen_intent": chosen["intent"] if chosen else None, "chosen_label": chosen["label"] if chosen else None,
                    "delivered_at": delivered, "answered_by": by, "human_wait_ms": wait,
                    "human_wait_basis": "DELIVERED_TO_ANSWERED" if delivered else "UNKNOWN_DELIVERY"})
        _write_json(rec_path, rec)
        history.update({"answered_at": now, "resolution_kind": resolution})
        index["gate"]["answered_at"] = now
        index["gate"]["delivered_at"] = delivered
        index["nodes"][key]["human_wait_ms"] = (index["nodes"][key]["human_wait_ms"] or 0) + (wait or 0)
        if delivered is None:
            index["anomalies_summary"].append({"node": node, "code": "HUMAN_WAIT_UNKNOWN",
                                              "text": f"gate {question_id}: no delivered timestamp; no wait deducted from active elapsed"})
        event = {"kind": "gate_answer", "at": now, "trace_id": index["trace_id"], "engine_version": ENGINE_VERSION,
                                      "question_id": question_id, "node": node, "visit": visit, "resolution_kind": resolution,
                                      "chosen_intent": chosen["intent"] if chosen else None, "delivered_at": delivered, "answered_at": now,
                                      "human_wait_ms": wait, "answered_by": by}
        if resolution == 'free_text':
            event['answer_sha256'] = conditional_reply.digest(answer_text)
        if not (restoring_conditional or _recorded is not None) or not any(e.get('kind') == 'gate_answer' and e.get('question_id') == question_id
                and e.get('answered_at') == now and e.get('resolution_kind') == resolution for e in store.read_json(store.evidence_path)):
            _ledger_append(store, index, event)
        if rec.get("source") == hsaw_gate.GATE_SOURCE:   # alpha.87: the human's answer joins the run register
            hsaw_gate.append_events(index, [hsaw_gate.gate_answered_event(rec, question_id, resolution, chosen, text, now)])

    option = _match_option(rec["options"], text) if _choice is None else _choice
    if _choice is not None and sum(o == _choice for o in rec['options']) != 1:
        raise EngineError('HUMAN_REPLY_BINDING_INVALID', 'The joint choice must bind one original business option.')
    conditional = bool(rec.get('conditional_reply') and entry and entry['kind'] in ('business', 'sub'))
    previous_answer = conditional_reply.latest(rec) if conditional else None
    if previous_answer and previous_answer['answered_by'] != by:
        raise EngineError('HUMAN_REPLY_CHANNEL_MISMATCH', 'Clarification must come from the same host channel as the original reply.')
    known_alias = any(text.lower() == a.lower() for o in rec['options'] for a in o.get('aliases', []))
    is_cancel = (option is not None and option["kind"] == "cancel") or (option is None and low in CANCEL_WORDS)
    is_terminate = (option is not None and option['kind'] == 'terminate') or (option is None and low in TERMINATE_WORDS)
    if is_terminate:
        close_dispatch_tickets(store, index, f'human_terminate:{question_id}')
        persist("terminate", option)
        ticket["state"] = "RETIRED"
        index["nodes"][key]["status"] = "FAILED"
        index["gate"]["state"] = "CLEAR"
        _terminate(index, kind="human_termination", by="human", reason=f"user terminated at gate {question_id}")
        _write_index(store, index)
        return {"status": "TERMINATED", "question_id": question_id, "run_state": index["run_state"], "error_report": _error_report(store, index),
                "error_report_ref": _ref(store, "ended.txt"), "terminal_delivery_refs": [_ref(store, "ended.txt")]}
    if is_cancel:
        close_dispatch_tickets(store, index, f'human_cancel:{question_id}')
        persist("cancel", option)
        ticket["state"] = "RETIRED"
        index["gate"]["state"] = "CLEAR"
        view = _view_for(program, entry) if entry else None
        # AISOP error routing for confirm_rejected: on_error[confirm_rejected] -> on_error.default -> the -.-> error edge
        handler = _error_handler(view, {"error_type": "confirm_rejected"}) if view else None
        graph = _graph_for(program, entry) if (program and entry and entry["kind"] in ("business", "sub")) else None
        if handler and graph and handler in graph["nodes"] and graph["node_types"].get(handler) != "end":
            index["nodes"][key]["status"] = "FAILED"
            index["completed"].append({"name": node, "visit": visit})
            frame = _frame_of(index, entry)
            if frame:
                frame["order"] += 1
            new = _sibling_entry(entry, handler, entry["ordinal"] + 1)
            _splice(index, entry["ordinal"], [new], drop_planned=True)
            coords = {"parent": frame["parent"], "parent_visit": frame["parent_visit"], "depth": entry["depth"], "order": frame["order"]} if frame else {}
            _set_current(index, new["name"], **coords)
            index["run_state"] = "RUNNING"
            index["anomalies_summary"].append({"node": node, "code": "CONFIRM_REJECTED_ROUTED", "text": f"-> {handler}"})
            if frame:
                _update_manifest(store, index, frame)
            _write_index(store, index)
            return {"status": "ROUTED", "question_id": question_id, "run_state": "RUNNING", "next": {"node": new["name"], "kind": new["kind"]}}
        if program and entry and entry["kind"] in ("business", "sub"):   # alpha.88 (doc 196 F4'): no declared route - the refusal closes the business work; the report and the answer still follow
            rec["cancel_outcome"] = "report"
            _write_json(rec_path, rec)
            dropped = _cancel_to_report(store, index, entry, key, question_id, option, text, now)
            _write_index(store, index)
            return {"status": "ROUTED", "question_id": question_id, "run_state": "RUNNING", "cancelled": True, "dropped_nodes": dropped,
                    "next": {"node": index["current"]["name"], "kind": "engine"}}
        index["nodes"][key]["status"] = "FAILED"   # Router.match: no program was chosen, nothing to report on - the run ends here (doc 196 D3)
        _terminate(index, kind="rejection", by="human", reason=f"confirm rejected at gate {question_id}",
                   rejection_report={"confirm_text": rec.get("prompt_text") or rec["question"], "user_response": text})
        _write_index(store, index)
        return {"status": "REJECTED_BY_USER", "question_id": question_id, "run_state": index["run_state"], "error_report": _error_report(store, index),
                "error_report_ref": _ref(store, "ended.txt"), "terminal_delivery_refs": [_ref(store, "ended.txt")]}
    if option is None and conditional and text and not known_alias and not re.fullmatch(r'[+-]?\d+', text):
        if not restoring_conditional:
            conditional_reply.receive(rec, answer_text, by, now)
        persist('free_text', None)
        _write_json(rec_path, rec)
        ticket['state'] = 'CONSUMED'
        index['nodes'][key]['status'] = 'ACTIVE'
        index['gate']['state'] = 'CLEAR'
        index['run_state'] = 'RUNNING'
        _write_index(store, index)
        return dict(status='ANSWERED', question_id=question_id, run_state='RUNNING',
                    interpretation_required=True, authorization='ORIGINAL_RECORDED_NOT_INTERPRETED',
                    recovered_existing_original=bool(restoring_conditional), answer_sha256=conditional_reply.latest(rec)['sha256'],
                    next=dict(node=node, kind=entry['kind']))
    if option is None:
        index["gate"]["history"].append({"question_id": question_id, "node": node, "source": rec["source"], "prompt_text": rec.get("prompt_text"),
                                         "presented_at": rec["presented_at"], "answered_at": now, "resolution_kind": "invalid_retry",
                                         "answer_ref": f"_gate.{question_id}.json"})
        rec.setdefault("invalid_answers", []).append({"at": now, "text": text, "text_original": answer_text or ''})   # alpha.79: the reply as the host passed it
        _write_json(rec_path, rec)
        _write_index(store, index)
        prompt = render.menu_block(rec, hint=f"未识别的回复 {text!r}；请回复编号 1-{len(rec['options'])}、选项名或 intent。", user_language=index.get("user_language"))
        return {"status": "WAITING_USER", "question_id": question_id, "run_state": "WAITING_USER", "reason": "INVALID_ANSWER", "public_prompt": prompt}
    persist("chosen", option)
    ticket["state"] = "CONSUMED"
    index["nodes"][key]["status"] = "ACTIVE"
    index["gate"]["state"] = "CLEAR"
    index["run_state"] = "RUNNING"
    _write_index(store, index)
    return {"status": "ANSWERED", "question_id": question_id, "run_state": "RUNNING",
            "chosen": {"intent": option["intent"], "label": option["label"]},
            "next": {"node": node, "kind": entry["kind"] if entry else None}}
