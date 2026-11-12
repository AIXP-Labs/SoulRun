# Changelog

All notable user-facing changes to SoulRun are documented in this file.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

SoulRun follows Semantic Versioning; its engine carries a version of its own (`soulrun.ENGINE_VERSION`), which
changes only when the engine does. The version promises SoulRun's own surface; what the engine makes (`ctx.data`,
the modules `host.engine()` reaches, the inside of the dicts the host doors return, the engine's error codes, the
files inside a run) changes with the engine version and is outside it ([GOVERNANCE.md](GOVERNANCE.md#versioning)).

## [1.0.1] - Unreleased

- Preserve the existing private `0o700` run-folder creation policy. The Windows restricted-token default-folder
  limitation remains unresolved; no inherited-ACL fallback, added principals or existing-permission changes.
- Correct the Windows creation comment and qualify the existing doctor parent-write probe: it does not verify
  access or privacy of a directory that has not been created. Keep statuses, JSON fields, exit codes and probe
  behavior unchanged; add no directory-creation simulation or ACL analyzer.
- Align English/Chinese permission and privacy guidance, best-effort `.gitignore` wording and the conditional
  pre-created-directory workaround. Pre-creation is not a privacy guarantee and must not bypass the host sandbox.
- Add the Python 3.15 classifier and point project support metadata to Discussions. Runtime dependencies remain
  empty and the canonical engine stays 1.0.0 with its existing resource manifest. Historical 1.0.0 evidence is
  preserved, not relabeled as acceptance of this unreleased candidate.
- Add a bilingual [local qualification summary](README.md#soulrun-101-local-qualification)
  ([中文](README_CN.md#soulrun-101-本地验收范围)), separating recorded 1.0.1 candidate tests, original skips,
  conditional Ubuntu Engine inheritance and untested host paths from older 1.0.0 evidence and hosted CI.
  This prose-only refresh changes no executable source, dependency, permission or canonical resource.
- A prior frozen 1.0.1 wheel was verified in one local user-site CLI/SDK update; that does not update production
  or put this new summary into that installed package. Final artifacts need verification against final inputs.
  Keep this entry Unreleased until a maintainer actually authorizes publication; no release date is asserted.
- Tighten release privacy checks: an e-mail-shaped address no longer bypasses detection through a file-like
  suffix. Ignore and reject local `.ssh`/`.aws` authentication directories while preserving neutral public
  examples; cover both rejection and exact-ignore boundaries with synthetic regressions. No runtime, engine,
  dependency constraint, permission or execution-authority change.
- Correct both dependency inventories and contribution stage lines for the unreleased 1.0.1 candidate;
  keep older dated evidence separate from current local checks and the exact release commit's hosted CI.
- B方案：不实施A′，S1默认目录问题显名保留；说明、诊断文字与元数据窄修外，仅收紧发行工具的隐私准入和ignore边界，不改运行逻辑。
  补齐中英验收范围，保留原skip、继承及未验边界；
  旧冻结制品的本机用户安装已核，不代表生产更新、平台发布或旧包包含本次新文字。正式发布前核最终输入与新制品，不改写1.0.0历史。

## [1.0.0]

The first release. Engine `1.0.0`. The dated sections below record the changes made under this version number on
the way to the release. An engine build is named by its digest (`soulrun --engine-info`), not by its version number:
where a section says the engine digest changed, an unfinished run begun before that change is a run of another build
(`ENGINE_BUILD_MISMATCH`).

### November 11 Python 3.15 CI and README History Trim

- Add Python 3.15 to the existing Windows/Ubuntu source-test matrix, retaining 3.11–3.14 and both
  Python 3.12 package jobs. Keep pinned actions, read-only permissions and every existing check.
  The extended 12-job configuration is not itself a hosted-CI pass.
- Remove historical runtime-head and earlier-build tables from both READMEs; preserve their prose,
  measurements and qualifiers in the verification archive, relocating relative links only.
  Keep the current baseline and qualification boundaries visible in both languages.
- Update current matrix references without rewriting dated evidence. Version, dependencies,
  runtime files, execution policy and production installations remain unchanged.
- 双平台增补3.15；双语README历史表迁入验证文档。新增远端作业待运行，不沿用旧结果判通过。

### November 11 Release Archive Checks and Qualification Inventory

- Reject duplicate/unsafe archive members and link/special types before selecting their contents;
  inspect each accepted ZIP member by its own ZipInfo. Keep ordinary files and valid source directories.
- Refuse local authentication, configuration, log, environment and generated material by path,
  including opaque data that matches no known credential pattern. Keep neutral source/templates
  visible and continue scanning their contents for privacy violations.
- Add explicit normal/corrupt archive counterexamples and update English/Chinese verification
  material with the dated local tests, QA-only inheritance and user-install/production distinction.
  Preserve old evidence and artifact identities; new release-tool inputs require separate checks.
- Version remains 1.0.0. No runtime dependency, public execution code, contract, error code,
  human authorization, record, business package or production installation changes.
- 仅发行工具与发布材料窄修；原失败和旧制品保留，不等于已推送或发布。

### November 11 Caller Guide and Documentation Consistency Review

- Correct the introductory README examples: show `ctx.doubt` directly to the human rather than forwarding
  that question to the model. Align English/Chinese examples, navigation, privacy and release-status wording.
- Correct the standalone caller guide to match existing gate-publication and explicit handover rules:
  a diagnostic return report neither publishes a menu nor authenticates the original child. Cancel and
  terminate do not grant new-agent authority. Ignore rules are not access control or a no-disclosure guarantee.
- Make the AIAP Usage prose host-neutral and remove the obsolete installed-engine development-test command.
  Preserve its parsed governance fields and all executable sources. Record the new source digest and keep
  prior test/artifact qualifications dated; do not relabel them as fresh tests of this revision.
- Clarify PowerShell syntax, interpreter selection, independently maintained Engine tests and shipped guide
  versus maintainer guide. No dependency, execution policy, error code or production installation changes.
- 中英文同改，版本仍1.0.0；这是说明与示例修正，不是新授权规则或部署。旧文档、回执和制品保留。

### November 11 AIAP Governance Document History Trim

- At the user's request, remove predecessor version entries and superseded development commentary from
  the bundled `AIAP.md`. Preserve all governance fields, current recovery rules, version policy and AIAP seal.
  Keep the complete original in a separate local backup; historical source records are not rewritten.
- Recompute the file manifest because the Markdown bytes changed, not because execution code changed.
  The version remains 1.0.0; governance program hashes, contracts and executable files are unchanged.
  Earlier test/artifact evidence remains bound to its earlier digest. No installed CLI/SDK or production update
  is implied by this source-only change.
- 按用户要求精简治理文件历史说明，保留现行规则与原文备份；摘要更新不授权续跑旧记录，不改执行代码、已安装包或生产。

### November 11 Documentation and Repository Hygiene Review

- Align the English and Chinese README on the 97-resource runtime head, dated test results, inherited
  real-model cases and remaining qualifications; retain earlier results as history. Reporting events alone
  do not prove original-child identity, and cancel/terminate never grant new-agent authorization.
- Clarify privacy boundaries: run data is not encrypted, ignore rules do not untrack files or erase history,
  and hosts/providers/program tools have separate logging and network policies. Add narrow ignore rules for
  local environment variants, authentication profiles, keys, private logs and release-tool output, with
  positive/negative tests preserving public examples.
- Keep dependency constraints unchanged; distinguish declared compatibility floors, recorded tools and CI
  configuration. Make CI's Twine metadata check strict. No SDK/runtime Python or canonical engine bytes change.
- 本次对齐中英文说明、隐私与依赖边界，版本保持 1.0.0。旧制品保留；文档改动后的新源码须另建包核验，
  不把旧模型、Linux、远端 CI 或旧制品结果冒充本修订的新验收，不执行安装、部署或发布。

### November 9 Development: only executing choices authorize handover

- Combined readjudication menus preserve both termination and cancellation kinds and labels. Only an executing
  business choice carries new-agent consent; termination preserves evidence without issuing a new execution right.
- Authorization readers and ticket validation reject all non-executing choices using existing errors. The existing
  internal termination record and response formats are unchanged; model-submitted gate permissions are not widened.

### November 9 Development: cancellation is not handover consent

- A combined business/handover menu retains an original cancel option's kind and label. Cancellation does not
  authorize another agent; it preserves accepted work and follows the existing report/answer closeout. Declining
  an optional action such as an export remains a continuing business choice, not whole-run cancellation.
- The existing handover-authorization response flag is false for cancellation and stopping. Recovery checks the
  same option kinds as the menu writer; authorization and ticket checks reject cancellation as continuation consent.
- No new contract, persisted field, error code, budget, host or business-specific behavior is introduced. Historical
  questions are not rewritten. This isolated development candidate is not a production deployment qualification.

### November 9 Development: historical execution-record compatibility scope

- v6-era execution records are outside the SoulRun 1.0.0 compatibility guarantee. Regression targets
  tied to deleted historical fixtures are retired explicitly, not counted as successful executions.
- Retained historical samples check their stated properties only. Current program execution, human
  authorization and recovery without repeating accepted work are unchanged. No runtime, contract,
  error code, permission or business/host adaptation changes are introduced by this scope clarification.

### November 9 Development: policy and external comparison maintenance

- Clarify the public executor/host boundary, release evidence and explicit operational authorization.
- Keep the English and Chinese contribution/security guidance aligned on package privacy review and incident
  handling; local deletion does not revoke a credential or erase remote copies.
- Refresh neutral external comparison inputs with the existing recorder. No execution code, contract, error
  code, permission or host/business adaptation changes; historical evidence and missing-fixture qualifications
  remain separate from current synthetic or platform-specific checks.

### November 5 Development: default-untrusted identity handover (record 92, decisions 196/197)

- A valid human handover resolves the old identity hold, not the current host's missing Agent capability.
  The existing capability gate is checked before a new handover ticket is issued, including on recheck;
  restoring the tool does not answer that gate. No public interface, record, error code or budget changes.
- Advisory confirmation examples in constraints and extra text are scanned as original strings, including nested
  JSON text, so valid double quotes are not lost to serialization escapes. Step-leading confirmation calls remain
  mandatory; prose examples remain advisory and grant no execution or replacement authority. No contract, error,
  record, trust source or budget changes. This correction is isolated and not deployed.
- Direct gate answers reconcile a durably recorded handover choice before interpreting a later reply, using the same
  existing binding checks and completion path as recovery. The optional reply hint identifies the original choice;
  the later text does not replace it or authorize a second action. Unshown and mismatched questions remain rejected.
- Re-presenting an unchanged identity menu keeps its existing entry bytes and modification time, while still
  verifying/preserving the immutable menu snapshot. Changed content keeps the existing publication path.
- Host reports remain diagnostic observations; no host source currently authenticates original-child identity.
  `resume_executor` and `host.parent_policy_ref` return `None`. No credential layer or trust switch is enabled.
- A first unshown business gate explicitly combines its choice with authorization for one new agent. Pause/inspect
  leaves the business question unanswered. Old wording, later loss, a return without a business question or unclear
  authorization requires a separate human decision; business refusal retains its original route/report behavior.
- The old execution right is fenced before presentation. Checkpoint-bound human authorization is rechecked before
  ticket issuance, claim and commit. Interrupted records are recovered without replaying accepted business work.
  Fencing does not attest physical exit; unknown external effects must be checked before continuing.
- Identity handovers at distinct accepted checkpoints are accounted separately; repeated same-progress failures
  retain the existing two-replacement bound. Joint delivery timing retains its actual question provenance.
- Fenced late submissions retain their payload and return the existing stale-ticket rejection before any legacy
  dispatch-stop preflight, without replacing the current question or its recorded human answer.
- Handover explanations retain the existing bounded tool-request summary (names and targets, not contents).
  Reports remain diagnostic only: a recorded result is not proof of identity, a completed write or physical exit.
- The early stale-ticket check leaves unrelated dispatch-stop exceptions at their original boundary; a failed
  diagnostic renderer is not reclassified as a business-submission rejection.
- An answer to a shown identity question detects program drift through the existing integrity stop. No handover
  choice is deferred across that stop; an unseen question still takes no answer or replacement authorization.
- Recovery preflight uses the same explicit identity handover for main and child entries. Child entries leave the
  question unpublished until the main executor serves it. Unticketed submissions cannot displace an already
  accepted handover; rejected payloads are retained without forwarding them to the new executor.
- Read-only re-entry recognizes an interrupted identity fence/menu without adding another transport wait or
  abandonment. Installation and observation share the same validation; a touched, answered or shown orphan is
  refused instead of being installed as a fresh unanswered question. Recognition grants no execution right.
- These rules supersede historical original-child continuation claims below. Version remains `1.0.0`; this is an
  isolated development candidate, not a deployment, protected-host qualification or completed real-model acceptance.

### November 4 Development: gate presentation (record 92, decision 193)

- **A returned child does not mean the human saw its gate.** Recording a child return no longer writes its business
  menu. The main conversation must take `next-node` before presenting the returned references, in every host.
  An answer before that step is held even when the host already reported the return. The separate proof of accepted
  plan/node/pause blocks remains available without publishing the one strictly bound, still-unpublished menu.
- **Returned blocks reach the command line in their original order.** The main conversation's waiting reply includes
  the current dispatch's existing public-reference list, so plans and accepted receipts precede its pause and menu.
  CLI printing keeps its cap, deferred blocks and explicit expansion, and does not add human text to a child's command.
  Returned references are checked against this run's public files; explicit historical expansion is unchanged.
  A completed child's existing `previous_dispatch_publication` list is printed before the next main plan as well,
  without re-executing its accepted node or treating a single historical fallback reference as a new list.
- This supersedes the early-publication descriptions in the historical November 2 entries below. Version remains
  `1.0.0`; the engine digest changes. Original-child identification without trusted host events remains unresolved.
  This development entry is not a production deployment or a completed full-qualification claim.
- **An interrupted recorded integrity answer is not a fresh choice.** Its view identifies the earlier recorded
  answer and the unfinished recovery, labels the original question/options read-only, and omits the new-choice reply
  grammar. Repeated views or identical preserved submissions do not apply or rewrite that answer; the next human
  reply still completes the original recorded decision under the existing rule, not the new text.

### November 2 Fixes
SoulRun stays V1.0.0 and the engine `1.0.0`; the engine digest changes again, so runs begun by an earlier `1.0.0` build are runs of
another build.
- **A folder SoulRun takes for the first time always gets its `.gitignore`.** In an existing folder - empty, or holding
  only an engine's runs - the `.gitignore` of `*` is now written before SoulRun takes its prepare lock there. A first
  call that ended under that lock - in a question (`NAMED_RUN_MISMATCH`, `DESIGNATED_RUN_UNFINISHED`,
  `ENGINE_BUILD_MISMATCH`), the notice that an old run was ended (`ENGINE_BUILD_RUN_ENDED`) or a machine turn's
  `ENGINE_BUILD_MISMATCH` error - left `.soulrun/` and no `.gitignore`, then or later. A folder that already has a
  `.gitignore` keeps it, a folder SoulRun refuses still gets nothing written into it, and the questions are unchanged.
- **`soulrun --doctor` says which runs need a `python`.** With no `python` on `PATH`, `python for the model` is still
  a `FAIL` in every program form. Its text no longer says that every run would stop at its first step, which is not
  so for the slim form's main conversation (it names the interpreter running SoulRun by its full path); it names
  what runs with that `python`: every engine tool in the entry-path form, a sub-agent's engine tools in every form,
  and a program's own tools written as `python ...` in every form. The documents that said only the entry-path
  form needs a `python` are corrected the same way.
- **`soulrun --doctor` follows the program-form switches.** `--slim-program`, `--no-slim-program` and
  `--inline-program` were accepted with `--doctor` and ignored: `program form` reported the environment's form.
  They are now read as a run reads them - each before its environment variable - so `program form` names the form
  that run gets and the switch that decided it, argument or variable (it says "the default" only when no switch was
  given: a slim form asked for by `--slim-program` or `SOULRUN_SLIM_PROGRAM` is no longer called the default), and is
  a `FAIL` where that run would stop (`PROGRAM_FORMS_CONFLICT`, a value that is not a switch).
- **A confirmation after an interruption and a cancel get no entry block in the entry-path form either.** Both run
  nothing (`ctx.kind` is `text_only`), yet in the entry-path and second-stage forms they still carried the
  `[EXECUTE ENGINE ENTRY]` block and the "read the entry first" assertion, against their note's "run nothing". They
  now get the context, the note and the text-only assertion, as in the slim form; the fixed wording is unchanged.
- **A code comment on the default conversation is corrected**: with no `session_id` there is one conversation per agent
  folder, as the documents say. No behaviour change.
- **The SoulACP example no longer tells the engine its model can start sub-agents.** It reports none of the sub-agent
  events a host must report through `soulrun.host`'s sub-agent doors, so it now declares `host_tools={"agent": False}`
  whatever the provider (it declared `True` for `--provider claude`), and the engine runs every node in the main
  conversation; `one_turn` no longer takes `can_spawn_agents`.
- **Engine: a message not from the human never answers a gate.** While a run waits at a gate, a message a host
  marks as not the human's (`human_turn=False`) is kept and the gate stays open (`entry_mode` `gate_hold`, and the
  context says so). SoulRun still refuses such a turn first (`HUMAN_REPLY_REQUIRED`). With
  `SOULBOT_RESUME_INTERRUPTED_RUNS` off, the engine holds such a message the same way at a run whose engine stop was
  cut off before its index write (below), and SoulRun now refuses it there too, before the engine is called and with
  nothing written, as at the run waiting at that stop. Before, SoulRun read that run as still running and handed the
  turn to the model as a program turn, whose next-node showed the stop from a turn that was not the human's. So it
  is, with the switch off, while a run still marked running cannot be read: the run lock a killed process left is
  still in place (the engine reclaims it as stale after two minutes; a lock a live process holds leaves the turn to
  the engine as before), or the run's records cannot be read or hold a gate record its index does not know that the
  engine cannot classify. SoulRun then refuses the turn, and the engine's own entry holds it with no question named,
  instead of reading the run as running, where a cancel word ends it. The engine function this check calls is in
  SoulRun's interface check (`soulrun --doctor`, `tools/upgrade_engine.py`). A hold the engine still returns to such
  a turn - a gate reached between SoulRun's check and the engine's, say - is refused as well, the message kept by the
  engine as at any held gate. A message that starts with the host's recovery marker (`[EXECUTE ENGINE RECOVERY]`) and
  whose `cache_dir:` line names a numbered run of that conversation in the same run folder still goes to the engine,
  in either switch position and with `human_turn=False`: the host's own re-entry re-enters that run, and its next
  step shows the stop. The run waiting at that stop never gets such a message. A marker naming another
  conversation's run, or no numbered run in that folder, is ordinary words and refused as above; text another agent
  writes in that form, naming the run's own folder, re-enters the run all the same.
- **Engine: re-entry text works only in its run's own conversation.** A recovery marker naming another
  conversation's run is ordinary words; that run is neither re-entered nor changed.
- **Engine: no program, no run folder left behind.** With no program to choose from, prepare reports
  `PROGRAM_INVALID` and takes back the run folder it had just reserved, so no empty folder counts among the kept runs.
  A folder holding anything that call did not make, and other init failures, keep their folder and record as before.
- **Engine: after a Stop, the next step names the engine's own tool.** `stop-decision` `continue` now names the
  bundled engine's `next_node.py`, not a path beside the runs.
- **Engine: a direct answer says that no program matched.** When Router.match finds no matching program, the
  direct answer starts with a line naming the designated or scanned programs - in Chinese only when the engine reads
  the user's first message as Chinese, in English for everyone else: Japanese and Korean as the engine reads them
  included, and a user whose language the engine cannot tell, whose first message holds neither a CJK character nor a
  Latin letter (Russian, Arabic or Thai alone, say, or only digits, symbols or emoji). The engine reads a Japanese
  message with fewer kana than kanji (`東京の天気`, `株価分析をお願い`) as Chinese, and so a Korean one with fewer
  hangul than hanja; a Chinese message with more than twice as many Latin letters as CJK characters (links, paths and
  identifiers aside) reads as English. No gate is added. Only this line follows that rule; the engine's other texts
  keep their own.
- **Engine: naming a timing field is not a timing claim; a digit tied to one is.** `UNTRUSTED_TIMING_CLAIM` refuses a
  digit (0-9, ０-９) tied to `started_at`, `ended_at`, `elapsed_ms`, `active_elapsed_ms`, `human_wait_ms` or
  `committed_at`: later in its clause, or inside a bracket opened there; below a heading, a label (`elapsed_ms:`) or a
  caption naming it - a caption is any other line naming it that is no table row and ends no sentence, such as
  `elapsed_ms per node`; an HTML `<caption>` counts too, and so does a table row whose one non-empty cell names the
  field where it is the row just above the `|---|` row or the first or last row of its table - in the list, block,
  code fence, bracket, table, `key: value` lines or `name number` rows that follow (other bullets, a value in
  brackets, dot leaders and a note after the unit included), one line or a one-line structure such as `Unit: ms`
  allowed in between, and in the next line itself when it starts with a digit (`1200` below `elapsed_ms (ms)`); in
  JSON, YAML or TOML text, beside a line whose value is the field; in a table column it heads (Markdown, `|`, HTML
  with a cell's own attributes, CSV or TSV, quoted cells and `;` included); in a structured output, under a key naming
  it, beside a value that is the field or a one-line caption (each such value's own digits aside, also where two stand
  side by side), in its column of a table given as lists (a header of strings or of dicts, rows as lists, dicts or
  strings, under separate keys too), or inside a key; and in the texts a node shows, read together as one text in the
  order it shows them - its messages, then its summary, then a text output and, at the answer node, the answer - each
  once (a structured output is read on its own). A caption that reads as a sentence - four words or more before the
  field, three Chinese characters counting as two, and the field not inside a bracket opened before it, such as
  `The program asks each node to report started_at` or `程序要求自报started_at` - is read the same way, one line in between
  included, except that a next line starting with a digit is not carried over: it counts only when it is a value
  (`1200`, `1200 ms`, `1200 ms for Start`), so `1. Router.match chose mini` or `2 nodes were sent back`, and then one
  more line that does not continue that list, may follow it. A `name number` row is a name, a number and at most one
  more word, or a number with a time unit right after it and anything after that (`Start 1200 毫秒用于读取请求`); a line that
  ends a sentence with one word after the number is prose (`路由重试了 2 次。`, `Router.match retried 2 times.`), while
  `Start 1200.`, `Start took 1200 ms.` and `路由 1200 毫秒。` stay rows. Line breaks may be `\n`, `\r\n` or `\r`, and the
  digits of an HTML attribute value count; those of a tag's name or an entity (`<h2>`, `&#58;`) do not. A field merely
  named is accepted - also in a complete sentence over a list, one that ends in an ellipsis or has an emoji or symbol,
  a Markdown hard break or a code span after its full stop included, and in a sentence wholly in bold
  (`**Never write started_at.**`) - and so are a digit before the field (except beside a line whose value is the
  field), a longer name (`started_at_1`, `max_elapsed_ms`), a field left empty in a structured output
  (`"started_at": null`) or in a table row between other rows (`| started_at | |`), Chinese prose with a spaced number
  followed by five Chinese characters or more (`共 2 个节点被退回`) or by one word on a line that ends a sentence
  (`路由给出 3 个候选。`), and spelled-out numbers, which are self-reports all the same. `took`, `elapsed`, `耗时` or `用时`
  followed by a number is refused only where the same text or output also holds an ISO date-time. The refusal's
  `expected` states every rule - about 11.5 KB in each refusal - and its help points there; the check takes time and
  memory linear in the text. Cost: below such a heading, label or caption, an explanation keeps digits out of the
  lists, tables, `name: number` lines and `name number` rows that follow, also one line further down, and out of the
  start of the next line - below a caption that reads as a sentence, out of a next line that is a value - and a
  caption meant as a sentence with fewer than four words before the field ends with a full stop. A few prose lines are
  still refused there: a number glued to the Chinese after it (`路由重试了 2次。`), a Chinese sentence that reads as a
  two-word name before its closing number (`路由选了 Opus 5.5。`) and a line a comma turns into a CSV header
  (`Of these, 2 failed.`). This closes the work on the check: rare forms it still accepts are known limits - a table
  header in a sibling branch (Frictionless's `schema.fields` beside `data`), an axis or encoding naming the field away
  from its values (Plotly's `layout.yaxis.title`, Vega-Lite's `encoding.y.field`, Highcharts' `yAxis.title.text`),
  rows keyed by column number, a caption value of more than one line, a second caption-like value holding the values
  (`'Start 1200 ms (see started_at)'` beside `'elapsed_ms per node'`), two structures between a caption and its table
  (`Values:`, then `- in ms`), a `#` comment that itself ends a sentence (`elapsed_ms  # the unit is ms.` over
  `1200`), `approx. 1200` below a caption that reads as a sentence, a section row inside a table
  (`| **elapsed_ms** | |` between rows), and `name number` rows written without spaces (`路由1200毫秒`), after an emoji or
  dash bullet (`✅`, `—`, `–`), after `(a)`, `#1` or a `-` with no blank, with a name of four words
  (`Read the user request 1200 ms`) or with one plain word after the value on a line that ends a sentence
  (`Start 1200 ok.`).
- **Engine: an unreadable reset time zone is recorded.** The reset time is still computed in local time, and the
  run now records `SUPPLY_RESET_ZONE_UNREADABLE`, which its report shows.
- **Engine: a file being replaced is read again.** On Windows a read refused while another process replaces the
  file is tried again after the pauses a write waits for the same refusal (2.75 seconds in all); a refusal that lasts,
  and a folder, which Windows refuses for good, are raised as before. The refusal is known by its error number - a
  `PermissionError` with errno 13 and no Windows error number, as builtin `open()` reports it - as well as by winerror
  5, 32 or 33. Overlapping prepares no longer fail on a file being replaced or leave a run folder without a record,
  and prepares that meet on the same run number take the next free one. SoulRun's own prepares hold a system lock; a
  host that calls the engine's prepare directly and unsynchronised can still see one fail once the agent folder keeps
  `CACHE_NUM` runs that cannot be evicted (unfinished ones): a prepare can then remove the run folder another has just
  made and take its number, and the other prepare fails - with an operating-system error raised out of prepare when
  its folder is removed under it (`FileNotFoundError`, say), or with its error recorded in that run.
- **Engine: a lock being released no longer fails a call on Windows.** Creating a lock file while its holder deletes
  it is refused for a moment there; the run, lifecycle, registry and HSAW locks now wait that refusal out instead of
  failing the call. A refusal that lasts 2.75 seconds - a folder that cannot be written, say - is raised as the same
  `PermissionError`; through `soulrun.run`, which tries the preparation four times, the call fails after about 12 to
  14 seconds.
- **Engine: a path too long says so.** On Windows without long paths, the unexpected-exception message names the
  path, its length and the 260-character limit. Status, code and exit are unchanged.
- **Engine: an engine stop cut off before the run's index is installed, not left behind.** The engine writes one of
  its own stops - a dispatch stop it opens itself, the stop asked again after a stale replacement choice or a recheck
  that moved on, the program-integrity stop - before the run's index; a run that stopped in between used to stop at
  every later step with `ENGINE_ORPHAN_WRITE_SET_UNPROVEN`. Now the next next-node, node-commit or interpretation
  command (`node_commit --interpret-human-reply`) installs that same stop as the engine would have, and so does the
  human's next message for a program-integrity stop cut off while the run waited at a gate; the engine's
  program-integrity pause also installs one it finds cut off instead of opening a second stop with the same number.
  The stop keeps its number, its link to the stop before it and its unchanged record, still needs the human's answer,
  and every answer leads where it would have without the crash; its first serve to the main conversation is the reply
  the engine gave when it opened the stop, except that for a stop asked again the line on the answer at the stop
  before is rebuilt from the records (below). A bookkeeping value the cut-off call had changed only in memory may lag:
  a part's preparation count, the refreshed independent limit (a cancel reply's budget summary shows it) or a part's
  progress time. Only a stop the engine wrote itself, never delivered and never answered, that matches the run is
  installed: its node and visit, the gate before it, the next number, the only such record, the types and option frame
  the engine writes (numbers compared by type, so `true` or `1.0` never passes for `1`), a dispatch stop's code with
  the facts the engine writes for that code (the replacement basis that code offers, the liveness stop's fixed
  explanation, a lapsed choice, a budget code's figures), the run values it copied (the node's status; for the
  integrity stop also the run state, the ticket it paused, the payload it kept and the program it loads at that node -
  the routed program, or at Router.match the registry snapshot entry the kept payload's route names), an instant in
  order, for a stop asked again a link to the answered stop it retired whose answer was not carried out (a replacement
  choice refused, a recorded replacement the October 29 recovery could not carry out because its ticket is no longer
  the part's, a recheck that moved on), on the stop opened for that answer (no return query offered for the part
  since, where the retired stop's replacement basis records one), for a budget stop the exact extension the run gives
  (from the record's own figures while the program's files differ), a lapsed choice it discloses still lapsed, and
  that it can be shown; never a program-integrity stop over one the run already waits at. Not checked: the wording of
  the stop and of its options other than the extension, the error details it copied, the replacement basis's values,
  which are compared with the run's when the replacement is chosen (a mismatch replaces nothing), the code of a stop
  that carries none of those facts, and, where the retired stop records no return query, whether a linked stop is the
  one opened for that answer; a rewrite of these can change what the stop says or where a recheck leads, or withhold a
  replacement, never authorise one. Anything else, a malformed record included, is left as before:
  `ENGINE_ORPHAN_WRITE_SET_UNPROVEN`, or the step's own stop first. After a cut-off program-integrity stop, an
  Agent-tool start or a failed delivery of the ticket it paused binds nothing and an SDK task start of that ticket is
  bound, as on the run waiting at that stop, and a recorded return of that ticket still lets the stop be installed.
  The engine-faults contract states the exception.
- **Engine: a gate the human has not been shown takes no answer.** An engine stop counts as shown once the main
  conversation has been served it - only that serve writes its menu - or its delivery is recorded; a business gate,
  once its menu is written - when the main conversation's own step pauses there; for a sub-agent's pause, when the
  main conversation's next step serves the gate (or earlier, when a host records that sub-agent's return) - or its
  delivery is recorded. A message before that is not taken: nothing is answered or authorised, prepare gives
  `resume_invalid_answer`, and the main conversation's next step shows the gate as first written - an engine stop with
  the reply the engine gave when it opened it (a stop asked again with its line on the answer before rebuilt from the
  records, below), a business gate with its node block and then its menu, which the engine now always writes in that
  order. Before, a run that stopped between a gate's index write and its menu took the human's next message as the
  answer: '2' at a liveness stop authorised a replacement and a new agent started. The rule also holds on runs that
  never stopped. A sub-agent's next-node or node-commit that opens or meets an engine stop, and a stop the engine
  opens or asks again while it takes the human's answer (a stop asked again, the program-integrity stop), return that
  stop without writing or naming its menu (`public_prompt_ref` is null; the text is in the reply). So a human who
  answers before the main conversation's next step - a stop relayed from a sub-agent's text, or a turn that ended
  before its next-node - answers once more. What the first showing of a stop asked again says is the next item's;
  after an answer the October 29 recovery completed, the lead saying the new reply was not taken reaches only the
  gate-answer reply. A sub-agent's node-commit that pauses at a business gate writes the index, the gate's node block
  and, among the references the sub-agent returns for the main conversation to present, the reference its menu will
  have, but not the menu. SoulRun itself decides when that gate is shown, in any host: the contract
  `resume.dispatch_segments` (the one contract change of this round, approved by the owner) and the main program now
  have the main conversation call next-node once (no ticket) before it presents anything of a gate a sub-agent
  returned at; that next step writes the menu, under that name and with the same text, and serves the gate, and the
  main conversation then presents the returned references, every one of which resolves, and any served gate
  reference not among them. So SoulRun's own command line run with `--host-tool agent=true` (as the SoulSkill bridge
  runs it, seeing no tool calls), SoulBot and an SDK host show such a gate in the same turn, and the human answers
  once. A host that reports the return (`host.observe_agent_return`; an SDK's task event for a resumed sub-agent,
  `observe_agent_task_event`) has the menu written at the return already, before the return is sealed - an extra
  signal only: the main conversation's next step then serves the same gate and writes nothing. A return recorded
  twice, late, unverified or for another ticket writes nothing. Should the turn end after the sub-agent returned and
  before that next step (and before any host record), the human's next message is not taken and the next step shows
  the gate. Once a host has recorded the return the gate counts as shown, as a gate does once its menu is written. At
  a program-integrity stop not yet shown, over a business gate, a message naming that gate is kept in the stop's
  record only, and the business gate asks again after the recheck. A gate already shown is answered as before.
- **Engine: a stop asked again after an answer says what was done, never 「答复有效」 / "Valid reply".** The records
  cannot tell an answer the engine used from one the October 29 recovery completed with the human's newer reply set
  aside, so the line a stop asked again opens with states facts only, in the menu and in the host hint, for both.
  After an answer that closes an engine stop and asks again, the main conversation's first serve of the stop asked
  again opens with a line on that answer: after a replacement choice refused as stale (a late start included)
  「这个换人选项依据的记录已经变了，没有换人。下面按现在的记录重新问你。」 / "The records this replacement was offered on
  have changed, so nothing was replaced. Here is the question again on the current records."; after a recheck that
  moved on to another condition 「复核已执行：这一段现在被另一个条件拦着（…），这道题已关闭，没有换人，也没有派出任何代理。下面按现在的记录重新问你。」
  / "Recheck executed: another condition now holds this part (…), so this stop is closed; nothing was replaced and no
  agent was started. …"; the host hint names the answer and the stop before it and what was done ("The recheck
  answered at the stop before (q…) was executed: that stop is closed, nothing was replaced and no agent was started;
  this stop asks again."). The gate-answer call's own reply to that answer says the same; after a recovery it opens
  instead with the recovery's line that the newer reply was not taken. A stop asked again at once after a reply given
  there says 「复核已执行；当时条件未满足，请再答一次。」 / "Recheck executed; conditions were not met then. Please answer
  again." (a recheck held) or 「这个换人选项依据的记录已经变了，没有换人；请再答一次。」 (a replacement choice whose records
  had changed), with the host hint "Recheck executed; conditions were not met then." or "The replacement choice was
  not carried out: …", on every serve of that stop; the forms after a later host record say 「复核已执行；当时条件未满足。」
  / "Recheck executed; at that time a condition was unmet." Where only that recovery leaves the records - a recorded replacement it could not carry out because its
  ticket is no longer the part's, or a recheck that moved back to the stop's own condition - the line names the
  recorded answer and what became of it, says that the reply received after it was not used, and calls no reply
  valid (「你先前在上一道题选的「…」没能执行：它授权替换的那张票已经不是这一段现在的票，所以没有换人。之后收到的那条回复没有采用。」,
  「之前记下的答复已处理，复核已执行：按现在的记录，这一段又回到这道题自己的条件（…）……之后收到的那条回复没有采用。」 /
  "Your earlier answer at the stop before (…) could not be carried out: … The reply received after it was not used.",
  "Your earlier recorded answer was handled; recheck executed: on the current records this part is back at this
  stop's own condition (…) … The reply received after it was not used."), and its host hint says the same. No record,
  `answer_valid`, `answer_disposition` or option outcome depends on these lines, and every later serve of a stop
  asked again at another stop is plain. After a human Stop, a
  cancel-like word the waiting stop does not take (`放弃`, say) whose answer call completes a recorded answer and asks
  again at a stop not yet shown now opens the Stop question, as on the run that never stopped, and its first option
  goes back to the stop asked again; it used to say 「答复有效，复核已执行；条件未满足，继续等待。」 beside the menu of the
  stop that answer closed; where such a word leaves the run waiting at the stop it was given at, the note beside that
  stop's menu now says 「复核已执行；当时条件未满足，请再答一次。」. The model's gloss of `resume_waiting_conditions`
  calls no reply valid.
- **Engine: the program-integrity stop cut off at a waiting gate is installed when the human's message comes first.**
  That message used to answer the gate under it, after which every step stopped with
  `ENGINE_ORPHAN_WRITE_SET_UNPROVEN`, or it opened a second stop with the same number. Now gate-answer installs the
  stop as next-node would; the stop is not yet shown, so the message is not taken (above) and the next step shows it.
  A message not from the human there is held under that stop's question (`gate_hold`), as at the run waiting at it.
  After a human Stop, the next message to such a run is routed at that stop, never shown, as on the run waiting at
  it: a cancel word asks first, an option, its number or a continue word shows the stop, and other words go to the
  executor's judgement as for a question not delivered.
- **Engine: an answer at the program-integrity stop cut off after its record is completed as recorded.** If the run
  stops after the human's answer at that stop is written but before the run's index is, the next reply completes the
  recorded answer as it was decided, whatever that reply says: a recorded cancel ends the run, a recorded recheck
  returns it to where the stop paused it. The stop's record is not written again, the ledger keeps one `gate_answer`,
  and the reply's answer hint says the recorded answer was completed and, unless the new reply named the same
  choice, that the new reply was not taken. Before, the next reply decided the answer afresh and rewrote the record,
  so a recorded cancel could become a recheck and a recorded recheck an end.
- **Engine: choosing an option at an engine stop after the program's files changed opens the program-integrity
  stop** instead of failing the turn with `PROGRAM_DRIFT_DETECTED`. The choice is neither carried out nor kept; once
  the files are restored and rechecked, the engine stop is the run's gate again and is answered afresh. A cancel there
  still ends the run.
- **Engine: a program change while the run waits at an engine dispatch stop no longer gives up that stop's ticket.**
  The program-integrity stop leaves the ticket as it is. It refuses every serve and commit with any ticket, so no
  agent can be served or commit for it - a node-commit's payload is kept, not accepted, and after the recheck it is
  named neither to a later serve nor in the recheck's reply, as on a run whose files never changed - though the host
  may still record the ticket's start or return, and an old agent may still be running. Once the files are restored
  and rechecked, the dispatch stop is answered as on a run whose files never changed, and a replacement agent the
  human then chooses is not handed the replaced agent's output. Before, that ticket was given up: once the files were
  restored, the replacement was refused and only a recheck or cancel remained. Over a running part or a business gate
  the ticket is still paused, and taken up again after the recheck; over a waiting business gate a node-commit's
  payload is kept likewise and named to no one after the recheck, as the run whose files never changed refuses that
  commit.
- **Engine: with `SOULBOT_RESUME_INTERRUPTED_RUNS` off, a run whose engine stop was cut off gets no restart
  question.** `open_restart_question` returns `SKIPPED` for it and writes nothing: the run that never stopped would be
  waiting at that stop. The human's next message, whatever it says, re-enters the run and the next step shows the
  stop; a message not from the human is refused by SoulRun as at a waiting gate (`HUMAN_REPLY_REQUIRED`; the engine's
  own entry holds it, `gate_hold`). After a human Stop, the next message to such a run is routed as at that stop never
  shown, as on the run waiting there: a cancel word asks first, an option, its number or a continue word shows the
  stop, other words go to the executor's judgement as for a question not delivered, and the Stop question's first
  option goes back to that stop. Before, it was routed as a running run, where a cancel word ends it. A host's
  recovery re-entry, the re-entry after an interrupted turn and the human-Stop judge path recognise such a run without
  installing its stop, and record no transport wait and no ticket interruption, as for the run waiting at that stop.
  Until the run lock a killed process left behind is reclaimed (after two minutes), a host's restart scan and a human
  message after a Stop can meet that lock: the call fails (`LOCK_TIMEOUT`), or the run is read as one genuinely
  interrupted - the restart question opens, and after a human Stop a cancel word ends the run. With the switch on, a
  message to such a run without a human Stop is routed as before: it is re-entered, and a cancel word ends it; after a
  human Stop it is routed as above, in either switch position.
- **SoulRun: the named-program question calls a run cut off at its engine stop "waiting for your answer"**
  (「在等你回答」), as it calls the run waiting at that stop, not "still in progress" (「还在进行」). Wording only: the
  question's `run_state` still gives the index's `RUNNING`.

### October 29 Improvements From the Creator Acceptance
SoulRun stays V1.0.0 and the engine `1.0.0`; the engine digest changes again, so runs begun by an earlier `1.0.0` build are runs of
another build. A reply printed over the cap now has another form: replace the engine with no run in flight.
- **Engine: a long reply puts what the executor needs first and can be read page by page.** The program's identity,
  the node's constraints (`reserved`), its steps and skeleton, the module result and the sub-graph (`frame`) now come
  before the rule texts, `input_authority` and the source candidates; newly sent contract sections are still named
  first, and nothing is folded that was not folded before. A reply still over the print cap is printed indented, one
  value per line, so the file a model command line keeps it in can be read page by page. Which replies are over the cap,
  and what is folded, is unchanged.
- **Engine: the main agent's reply to a dispatch it starts is the dispatch view** - the node's identity and mode, the
  dispatch block, the gate and run, the plan and previous-publication references, its own entry contracts and the
  dispatch rule addressed to it - instead of the whole node package; the sub-agent that claims the ticket still gets the
  whole package, and the main session's contract record lists only what it was given.
- **Engine: the human-chosen replacement also covers a child that paused at a gate first.** A child that opened a gate
  inside its part and then came back with an error is offered the same one new child, which resumes the answered gate;
  every replacement ticket carries the answered gate it resumes.
- **Engine: replacements are counted as replacements.** A human-chosen replacement uses no dispatch attempt: it is
  bounded by the part's replacement count (two) and never turns into inline work - with no replacement left, the engine
  stops and asks. When the part already holds its task charge, the replacement's claim takes no new task quota and is
  counted as a replacement; a part whose ticket was never claimed (never seen starting, or its Agent call failed before
  claiming) is charged once by the replacement's claim, and with no quota left that claim is refused, never inline.
  The execution report shows replacement claims.
- **Engine: after a host restart or recovery re-entry, the human may replace a child whose state is unknown - with the
  risks stated.** Offered only when the re-entry recorded the interruption, no return was recorded and the one bounded
  return query was already offered where the host has one; until that query is offered, a call from the interrupted
  resumed child (or any commit) is refused with `DISPATCH_RETURN_QUERY_PENDING` - nothing committed, the run not paused,
  the payload kept - so the query and the replacement after it are still offered. The stop says the old agent may still
  be running, that its ticket is retired the moment the human chooses (any later commit from it is
  `DISPATCH_TICKET_STALE`), that files it wrote outside the engine may repeat or conflict, and lists the tool requests
  the host recorded since its last accepted commit, or its claim (names and paths only; a re-read of its plan hides
  none). The choice is bound to the ticket and the interruption evidence; a choice made on changed records replaces
  nothing. Such a choice retires the stop and the human is asked again on the current records when the old agent came
  back with an error - at the resume-unavailable stop with its one replacement while one is left, wherever the part
  sits - and otherwise while a recheck of that stop still cannot pass, at the stop of whatever condition blocks (after
  the bounded return query where that is now needed); after a normal return on which a recheck can pass, the same stop
  stays. From the moment the old agent's return is recorded, every serve of that stop says so in its menu, says nothing
  was replaced, and says what Recheck conditions and, where the stop offers it, the replacement now lead to, from the
  engine's own decision for each: Recheck conditions continues with that return, leads to the stop that follows (the
  resume-unavailable stop with one new agent, the stop where only cancel remains once the part's second attempt is
  used - by its one same-agent continuation, or by a new agent that took the part after it (by the engine's handoff or
  the human's choice) - or another stop that states its cause), or - where the liveness condition itself
  still holds, or asking again would show this stop's own condition - does not pass there and leaves the run paused on
  that stop; the replacement keeps the stop, or retires it and asks again at the stop it names, and where it can no
  longer lead to a new agent the menu says the earlier recommendation no longer applies. The error message, and after a
  valid reply the answer hint, tell the host the same about Recheck conditions and the replacement. No served text
  names an option its stop does not offer. If an accepted choice is not carried out because the host recorded the old
  agent's return, its start or a new interruption before the new agent was issued, nothing is replaced and every stop
  the engine opens for that part says so; the lapsed-choice stop (`DISPATCH_REPLACEMENT_LAPSED`) itself opens only
  where a recheck would resume the old agent or let the engine take its next step, and anywhere else the stop of the
  condition that holds the part (an error return, the continuation bound) opens and says it. The human settles such a
  choice by choosing Recheck conditions at a stop that said so - no later stop repeats it, and the engine takes the
  step the current records give, resuming the old agent once where it can - or by a later replacement choice that is
  accepted, which supersedes it. The execution report, the evidence block and the final answer's records show a
  refused choice as refused and an unused one - lapsed or superseded - as not used, never as a used authorization.
  Without an answer nothing runs.
- **Engine: each dispatch stop states its own cause** - a child that cannot be resumed, a repeated unfinished return, an
  unknown liveness, a missing Agent capability, the part's attempt bound (`ORIGINAL_EXECUTOR_CONTINUATION_EXHAUSTED`,
  and `INDEPENDENT_ATTEMPTS_EXHAUSTED` at an independent root's bound, say how the part's second attempt was used and
  which agent returned unfinished, naming and counting no more than the records establish - where no continuation is
  known to have reached the original agent, only that the agent now holding the part returned unfinished - and
  no longer say "independent execution is unavailable ... configure the program or capability"; other
  attempts-exhausted stops keep their wording) - with what is kept and what each option does in every pool: a recheck
  that cannot resume the child leaves the run paused for the human's answer - on that stop, on a new one of the same
  kind, or, from a liveness stop after a recorded return, at the stop that follows, which its menu names - and the
  liveness stop says that without a recorded return (or, for an unclaimed continuation, a record that its message was
  never delivered) a recheck does not pass; the anomaly names the real cause instead of "independent execution cannot
  fall back inline".
- **Engine: a recheck moves on by the current records.** When the recheck on a liveness stop is held by another
  condition - the missing Agent capability in any pool; at an independent root, once the old agent's return is
  recorded, also an error return, a return without an identity, or the part's attempt bound - the stop no longer stays
  with "conditions remain unmet": it is retired with that answer and the human is asked again at that condition's stop,
  which names the retired one (`supersedes`, reason `DISPATCH_RECHECK_MOVED_ON`); nothing is issued without an answer
  there. A recheck still held by the liveness condition itself keeps the stop, a recheck that passes is unchanged, and
  a recheck at a stop that said an earlier replacement choice was not carried out still settles that choice. Every
  serve says beforehand where Recheck conditions leads; at the part's attempt bound it says what the records establish
  of how the part's second attempt was used and which agent has returned (where no continuation is known to have
  reached the original agent, only that the agent now holding the part has returned), and that only cancel remains
  there. The stop that waits for the Agent capability
  (`SUBTREE_AGENT_CAPABILITY_UNAVAILABLE`) does the same once the host declares the tool again at a re-entry and another
  condition holds the part: its recheck moves on to that condition's stop (the resume-unavailable stop, a stop where
  only Recheck conditions and cancel remain, or the budget stop with its extension). Where nothing else holds the part,
  its serves say the host now declares the tool, the condition the stop waited for is met, and Recheck conditions goes
  on with the current records (the engine may then start the part's agent, resume its original sub-agent or stop at
  another condition); the recheck passes as before. While the tool is lost nothing changes. The execution report's
  reply tables and machine rows, the evidence block, the final answer's records and the report node's facts show a
  retired stop as the human's recheck that moved on (`recheck_moved_on`: the stop the human was asked at next, and its
  condition), never as refused, not used or a consumed authorization.
- **Engine: an answer cut off by a stopped run is completed as it was decided.** If the run stops after the human's
  answer at an engine stop is written but before the run's index is, the stop waits with that answer recorded and every
  serve says so: the recorded choice, that it is not finished, and that the next reply first completes it whatever that
  reply says (a new choice is not taken; cancel stays available at a stop that follows). For a replacement choice the
  first attempt refused as stale, or one whose ticket the part no longer runs, it says instead that nothing will be
  replaced and that the next reply closes the stop and asks again. It no longer offers "reply stop to end this run",
  and the error message and answer hint tell the host the same. The next reply then completes the recorded answer as
  the first attempt decided it, never deciding it again on the current records: a carried replacement with its
  recorded authorization (what the host recorded meanwhile, such as the old agent's return, is then handled as after an
  uncrashed choice), a recheck that passed, a budget extension, a recheck that moved on (the human is asked at the stop
  of what holds the part now), a refused replacement choice (closed, nothing replaced, the human asked again) or a
  cancel. It adds no second recheck attempt; its reply says what became of the recorded answer and whether the new
  reply was set aside, and that reply's host hint never calls the set-aside reply valid (the stop it asks again is
  first shown as the November 2 Fixes say). A recorded replacement whose ticket the
  part no longer runs is not carried out: no new agent is issued, the stop is retired and the human is asked again; its
  authorization is still entered in the ledger (`executor_replacement_authorized`, written by the recovery if the run
  stopped before it), but nothing is replaced. If the run stops after the index but before the stop that follows is
  written, the reports still show the retired stop as moved on - to the stop the main agent's next-node then opened for
  it, or with the condition the recheck recorded and no stop. The machine fields of a stop in that state
  (`answer_valid`, `answer_disposition`) are unchanged.
- **Engine: a liveness stop says what was recorded after it opened.** When the host records the old ticket's start
  after a stop that offered the replacement as never seen starting, every serve says so - the option note and the
  explanation saying it was never seen starting no longer apply - and what choosing the replacement now does: where it
  leads to the stop with one new agent, this stop closes and the human is asked again there; otherwise the earlier
  recommendation is said to no longer apply. When the host records that an unclaimed continuation's message was never
  delivered, every serve says what Recheck conditions now does, from the engine's own decision; where it applies, that
  includes the engine's continuation rule then giving the part one new agent. The error message, and after a valid
  reply the answer hint, say the same. Where the replacement leads to the stop with one new agent, the menu adds that
  the advice's authorization takes effect only when chosen again there. The resume-unavailable advice for a child that
  returned without an identity says its return is recorded and final.
- **Engine: two small fixes.** `soulrun.host.resolve_tool_parent` raises `DISPATCH_RESOURCE_CONTEXT_INVALID` (as
  SoulRun's error) for a ticket no dispatch owns, instead of a plain `AttributeError`. Acceptance receipts are read,
  written and listed through the engine's long-path helper, and every regular-file (link or junction) check goes
  through it, so a run directory about 160 characters deep no longer fails to seal a receipt with "file not found".
  This is not general long-path support: a run directory of about 170 characters or more still fails on other run
  files.
- **Engine: an unclaimed continuation that may never reach its child says how to give it up**: the reply names
  `next-node --dispatch-abandon <ticket> --reason <reason>` for a SendMessage that failed or was never sent; the engine
  still replaces nothing on its own.
- **Engine: the source candidate list shows the run's saved files** - `_work` top level first, then deeper folders,
  newest first within each level, still capped at 80 (`more` says when more exist).
- **Engine: "has false with text output" counts only this node's own text**: `proc:` and `input:` values and a string
  equal to the user's message are passed over; `work:` files and inline fields still count.
- **Engine: one placeholder rule for program texts.** `{A|B}` and `{two words}` are placeholders in every check; a
  delivered text that does not match is recorded as not matching, not as a placeholder left unfilled.
- **Engine: dual counts written as the contract asks bind.** The node path without module prefixes (unique only) is
  accepted and a leading list marker is ignored; a count that does not bind says which name or counts did not match.
- **Engine: `steps.not_applicable` takes `{step, reason}`** besides the step key; the reason is kept in
  `machine.steps_not_applicable`.
- **Engine: a non-zero exit names the call's purpose** in `PROCESS_EXIT_NONZERO`; the judgement is unchanged.
- **Engine: `node_commit --payload-stdin` no longer waits forever.** With nothing for 10 seconds, or empty input, it stops
  with `PAYLOAD_STDIN_EMPTY` (`PAYLOAD_STDIN_INCOMPLETE` after a partial payload), exit code 2, and the run unchanged.
- **Engine: one command validates an unchanged run index once.** Every read still reads and parses the file; the full
  schema check runs once per exact bytes in a process, and changed bytes are checked in full again.
- **Engine: anomaly accounting uses the sub-node basis and counts by code** (`accounting.anomalies_by_code`, a count,
  never a severity), and the evidence block names both anomaly scopes - the run index and all node revisions - each
  with its per-code counts and where its records are; the scopes are never summed or merged by text.
- **Engine: acceptance receipts moved out of `_work/replies/`** to `_work/_receipts/`; receipts in the old place are
  still read.
- **Hosts report sub-agents through named doors.** `soulrun.host` gains `dispatches_nodes`, `observe_agent_start`,
  `observe_agent_return`, `observe_agent_task_event`, `observe_resume_failure`, `resumed_agent_start`,
  `parent_policy_ref`, `observe_tool_request`, `observe_tool_result` and `resolve_tool_parent`, each passing straight
  through to the engine function it names; those functions are in the interface check, and the README and GUIDE say
  what a qualified host must report.
- **The checks before a run is prepared look up the conversation's latest run once**: a continued turn reads that
  run's index three times instead of seven (twice before the engine prepares the turn, once after), and a new
  conversation scans the kept runs once instead of three times. No behaviour change.
- **The doctor's path-length check follows the node names that write in a run**: it works the deepest file out from the
  installed programs' node names and the engine's own nodes that write a block in every run (with short program names,
  the engine's `Engine.execute-report` block, 130 characters at a three-digit run number), as the engine names them,
  counts run numbers with at least three digits, names the node, and assumes 150 characters when it can read no
  program's node name (it assumed 140). A deepest path of exactly 260 characters now counts as too long, as on Windows,
  which allows at most 259 (it was passed), and the run folder's length is counted in UTF-16 units, as Windows counts
  it: a character outside the Basic Multilingual Plane (a CJK Extension B character, an emoji) counts two.
- **SoulRun's records say which turn they are about.** `ctx.turn_id` is documented as the engine's (the run's number,
  the same on every turn); `.soulrun/turns/<run>.json` keeps the latest turn's `turn_id`, `host_turn_id`, its number
  within the run and the run's `trace_id`: a run number the engine gives again starts again at turn 1, and the engine's
  rebootstrap of a turn keeps its number only with the same `host_turn_id`. The record of what a slim turn was given
  keeps the turn's facts when a part is added.
- **The slim entry says how to read an output the command line saved to a file**: whole, by its path, page by page -
  never searched instead.

### October 28 Fixes From the SoulBot Review
SoulRun stays V1.0.0 and the engine `1.0.0`; the engine digest changes, so runs begun by the earlier `1.0.0` build are runs of
another build.
- **Engine: a rejected reply that could not be printed no longer stops the run.** When printing the reply to a node
  submission fails after the engine rejected it and changed nothing (a sub-agent whose pipe closed), the engine proves
  the run unchanged, notes `REJECTED_REPLY_NOT_DELIVERED` and lets the executor submit again; an accepted submission
  whose reply was lost still stops for a human.
- **Engine: every host-authorised end writes the accepted-facts notice** (`_public/ended.txt`, and
  `_terminal_facts.json` for a human end), as the gate and commit paths do; an existing notice is never rewritten.
- **Engine: 1.x versions keep the inherited feature set** (`runtime_identity.revision_match`), and run numbers follow
  their own run root only (the predecessor folder name is no longer consulted). One documentation example no longer
  names a machine path.
- **A run of another engine build is asked about, not a failed turn.** `ENGINE_BUILD_MISMATCH` on a human turn is now
  a question (`ctx.doubt`): end that run, work in another conversation, or leave it. A reply of one cancel word ends it
  through the engine's `terminate_run` (only a run of the same engine version; none of its steps is run). A machine
  turn is still refused with the error.
- **A reply the command line cannot print is noted, not a traceback.** Exit code 74, one line on standard error, and a
  note in `<soulrun_cache_dir>/.soulrun/undelivered/<run>.jsonl` (removed with the run).
- **SoulBot's agent template is now a SoulRun entry.** The wording comparisons recognise it and stay on the recorded
  samples; `tools/upgrade_engine.py` says so instead of failing. [The SoulBot guide](docs/guide/02-soulbot-integration.md)
  now describes the wiring as SoulBot has it and the rules a host must keep.
- **Engine: a child that returned with an error can be replaced - only by the human's choice.** When a dispatched
  child's Agent call comes back with an error before its part is done (a usage limit cut its model off, say), the
  engine still cannot resume it and still stops for the human; that stop now also offers one new child, bound to that
  exact return. The new child starts at the first unfinished node; accepted nodes are not redone. Nothing is replaced
  without that choice, and a child that can be resumed is still resumed.
- **A question to the human at Router.match is not a stalled slim turn.** When two programs fit and the model asks
  which one, the run waits at Router.match with nothing committed; the turn that answers (or one that does not) no
  longer marks the run `STALLED_AT_ROUTER_MATCH`, so the run and the conversation keep the slim form. A model that
  then leaves Router.match without a commit is still caught.

### October 28 Source-Form Release Checks
- Add read-only `sync_engine.py --check-release` admission: verify the record, exact payload and privacy before applying canonical identity/license/contracts or the unchanged legacy history check.
- Refuse unknown, drifted or contradictory source declarations without a fallback. Keep canonical runtime bytes and existing legacy rules unchanged.
- The CI workflow runs the new check; the release, contribution and dependency documents (English and Chinese) describe it.

### October 27 Release Preparation
- The English and Chinese documents keep this build's verified results apart from an earlier build's Python matrix.
- The [release notes](docs/release-1.0.0.md) record the engine's identity, the results verified for the release and what it does not claim, Creator and Codex backend qualification included.
- The package payload and the 96 engine runtime files are unchanged by this preparation.

### October 27 Maintenance
- Bind accepted Router program choices to registry program identities before intent normalization; reject another candidate or `no_match` instead of silently overriding the human.
- Preserve choice evidence and existing HSAW disposition, cancellation, business-branch and recovery guards. Missing or conflicting choice evidence is not authorization.
- Keep business-gate report statistics explicitly scoped; host fault-recovery authorization remains separately recorded, not invented as a business answer.
- Identify same-version artifacts by SHA-256; an unchanged version label does not carry Creator, Codex or platform qualification over.

### Canonical Runtime Sync
- Copy 96 canonical runtime files without rewriting executable text or historical feature selectors; retain LICENSE and NOTICE.
- Validate upgrade interfaces, slim arrangement and fixed wording before replacing runtime files; keep legacy tooling explicitly separate.
- Use current menu-SHA references, bind unfinished runs to the exact engine digest, and reject nonhuman answers to open business gates.
- Regenerate the slim program and host wording. Keep model/backend and business-program qualification distinct; no Creator-specific adaptation.
- Add an exact, read-only generated-program policy projection for hosts preserving native child sessions. Forward original runtime bytes separately; keep all resume authority checks.

### Added
- **The one call.** `import soulrun; ctx = soulrun(user_message=...)` starts a run or continues the one
  the message belongs to; with no message and no `cmd` it hands back the guide and creates nothing.
  The package itself is callable; `soulrun.run` is the same function.
- **`Ctx`.** `kind` (`program`, `text_only`, `guide`; a confirmation after an interruption and a cancel are
  `text_only` too: in every program form they get the context, the note and a text-only assertion, never an entry
  block), `text`, `blocks`, `cache_dir`, `entry_mode`,
  `turn_id`, `session_id`, `places`, `doubt`, `program` (the filled-in program in the slim and second-stage forms,
  else `None`), `program_form` (which form the text was given in), `system_prompt` (the opening instruction that
  goes with that form), `slim_fallback` (why a turn that would be slim is not), and the engine's own answer in `data`.
- **Program and data are separate.** The engine is read from the installed package; runs go to
  `soulrun_cache_dir` (argument, then `SOULRUN_CACHE_DIR`, then `<agent_dir>/.soulrun_cache`); a named
  one is that folder itself. A value that is set but unusable is an error, never a silent fallback. A
  folder that holds an engine program is refused (`SOULRUN_CACHE_DIR_HOLDS_AN_ENGINE`), so two engines
  never share one set of runs; so is an existing folder that already holds other files
  (`SOULRUN_CACHE_DIR_NOT_EMPTY`). A run folder carries a `.gitignore` of `*` from its first run - written when SoulRun creates the folder
  or takes one for the first time that has none, then left to the owner: run data holds the user's own words and is never committed by
  accident. On Linux and macOS a run folder SoulRun creates is readable by its owner only.
- **Choosing the candidates.** `aiap_dir` / `aisp_dir` (folders of programs) and `aiap=` / `aisp=`
  (one designated program, by path or by name). A designated program is used as designated; one that
  cannot be found opens a question for the human and nothing is run. While the conversation has an unfinished
  run not created for the designated program, the human is asked first (`DESIGNATED_RUN_UNFINISHED`): the engine
  would otherwise continue that run and the named program would quietly not run. A program folder with its registry
  script (`aiap_list.py`, `aisp_list.py`) is used only through its agent folder, where the engine runs the script
  (`REGISTRY_FOLDER_ALONE` otherwise), so a folder gives the same candidates however it is named; one folder given
  for both kinds counts once; a default run folder that is a link (a junction, a symbolic link) does not make
  the engine look for programs beside the link's target.
- **Conversations.** `session_id` says which conversation a message belongs to (default: one per agent
  folder); `cache_dir` says which run it is for and is checked before use. Re-entry text
  (`host.resume_prompt`) is checked the same way: it re-enters a run only in that run's own conversation.
- **Questions before a run exists.** A designated program that is not found, or a `cache_dir` that does
  not match, comes back as `text_only` with `ctx.doubt`: what was looked for, what exists, a non-binding
  suggestion, and options that each carry what to do next (`call` with arguments, `ask`, `cancel`).
- **No words.** No program named (or only the big folders): the guide. One program named (`aiap=` or
  `aisp=`): it is run with an empty message, and a program that needs words asks the human. Both an AIAP
  program and an AISP skill named: the human is asked which one first (`WHICH_DESIGNATED_PROGRAM`, in
  Chinese and English).
- **A note per run.** `.soulrun_cache/.soulrun/runs/<N>.json` records which folders a run was created with
  and whether each came from an argument, an environment variable or the default. SoulRun's notes are never
  written inside a run's own folder (only the command line's message file is moved there, see Command line), and
  they are dropped once the engine has removed the run. Notes and saved turns
  are written whole (a temporary file put in place), never half.
- **`cmd`.** `soulrun(cmd="next-node" | "node-commit" | "stop-decision" | "gate-answer", ...)` runs one
  engine command; it cannot be combined with `user_message`. SoulRun's own arguments are not passed to a command
  (`ARGUMENT_NOT_FOR_CMD`); an engine option whose name SoulRun uses itself goes in `args=[...]`. A reply that is not
  JSON is `CMD_OUTPUT_NOT_JSON` from `CmdResult.json()`, a command past its `timeout` is `CMD_TIMEOUT`, and a
  human's `answer=` reaches `gate-answer` in a file only the user can read, never on a command line.
- **Command line.** `soulrun`, `python -m soulrun`: the same call, the user's words from a file or
  standard input (UTF-8, or UTF-16 with its byte-order mark; anything else is `MESSAGE_NOT_UTF8`), `--json`,
  `--cmd` (also `--cmd=NAME`; no abbreviated options), `--program` (the business program a run is bound to, as
  JSON: the overview - the size and fingerprint of a field worth fetching, the name of a small one -, `--node`,
  `--field` with `--offset`/`--limit`, `--doc`; a field that is not a string is written the way the engine writes
  it, so its size, fingerprint and pages are those of the engine's `program_contracts` and
  `--read-program-contract`), `--report` (the complete execution report behind an `engine-report:` link),
  `--engine-node` (a part of the slim engine program on request; `ENGINE_NODE_UNKNOWN` for a name that is not
  handed out), `--expand` (the text of a public block, as a host shows it; `EXPAND_REF_UNKNOWN`),
  `--keep-message-file` (by default the message file is moved into its run's folder, `_soulrun/message.<n>.txt`,
  once the turn has its run; a file written into a new run folder no longer keeps it from being used; a file that is
  missing gets `MESSAGE_FILE_UNREADABLE` saying where an earlier turn put it),
  `--slim-program`/`--no-slim-program`,
  `--engine-info`, `--version`. Output is UTF-8 with LF line
  ends on every platform and stays under the command-line cap in every program form: over-long data lines are
  shortened with the file that holds the full text. With `--json` every error is one JSON object.
- **Checked calls.** The types of the arguments, the two switches (`True` / `False`, or 1/true/yes/on and
  0/false/no/off in the environment, where an empty value counts as not set), and that there is a program to choose from are checked before anything is
  created; a question for the human creates no run folder and names no absolute path. Errors the engine raises
  come out as `SoulRunError` with the engine's code; every `SoulRunError` can be pickled. With no `session_id`, a
  conversation is one per agent folder. A run folder taken for the first time may hold only runs and system files.
  A busy run folder holds up no call for another one. After a Stop, a new task keeps the programs the run was
  named for.
- **`soulrun.host`.** Named doors onto the engine for hosts: `expand_refs` (the reply as the human reads it:
  the engine's `⟦engine:…⟧` references replaced by its public blocks), `after_turn` (after every turn: a shown
  question's menu marked delivered, what was said, that it was stored), `observe`, `finalize`, `stop`,
  `open_question`, `mark_question_delivered`, `interrupted_runs`, `mark_interrupted`, `open_restart_question`,
  `resume_prompt`, `resume_interrupted_enabled`, `runner_recovery` with a typed `RecoveryRequest`, `latest_run`,
  `cache_root`, `soulrun_cache_dir` (the agent's runs), `program_root` (the engine's tools), `system_prompt(form)`
  (a form's opening instruction), `program_view` (what `soulrun --program` prints), `execution_report` (the
  complete execution report behind its link, checked as SoulBot's web page checks it), and `engine(name)`
  for any engine module - a name that is not one is refused before anything is imported (`ENGINE_MODULE_UNKNOWN`),
  and a module of one of the engine's names from elsewhere in the process is refused, never used
  (`ENGINE_NAME_CLASH`). `import soulrun` is enough to reach `soulrun.host`. The two examples run the same loop: a
  doubt goes to the human, everything else to the model; the reply is shown expanded; `after_turn` follows every
  turn; the user's words come from a file or standard input.
- **The engine** in `soulrun/soulrun_aiap`: the runtime files only, with `engine_manifest.json` (version and
  SHA-256 of every file); `tools/sync_engine.py --check` and `soulrun --verify-engine` check it (the manifest's own
  digest too), `soulrun --engine-info` shows the digest worked out from the files themselves, and the engine's own
  AIAP conformance check passes.
- **`tools/clean_engine.py`** turns an older development engine tree into SoulRun's engine (the legacy path; a
  canonical engine is copied byte for byte instead, see Canonical Runtime Sync): runtime files only (a list of what is
  kept, not of what is dropped: hidden folders, caches, logs, `node_modules`, `.env`, tests and release notes never
  come in), SoulRun's name and the version given, development notes taken out of comments, docstrings and texts,
  machine-specific example paths made neutral (drive letters with either slash, `/home/…`, `/Users/…`, network
  shares), and the engine's own integrity records (contract manifest, governance hash) recomputed. Python files
  must keep their exact structure, a text that holds JSON must keep its shape, and a string written in pieces is
  cleaned as one sentence (on Python 3.11 and 3.12 alike); `--check` reports anything left and refuses a folder
  that is not an engine. Notes found by rules added later in a cleaned engine are listed by file hash in
  `KNOWN_LEFTOVERS`; a changed file is checked in full.
- **`tools/upgrade_engine.py`**: a newer engine in one step - a canonical engine staged byte for byte with its
  identity, version, license and contracts checked (an older development tree only with `--legacy-clean`, cleaned on
  the way in and refused when anything is left to clean), the replaced engine kept under `.engine_backups/` (local
  only), the new one copied in with its manifest, `engine_node.aisop.json` rebuilt, the fixed wording checked against SoulBot's `agent.py` when
  found; `--engine-version` names the new engine's version (a release version only; changed files under the same
  version are refused unless `--same-version`; a lower version is noted), `--dry-run` shows the plan, `--restore`
  goes back to a kept engine (an archive that is damaged, fails the check of its source form, names a file outside
  the engine, does not match the manifest kept with it or does not take the current SoulRun's calls is refused before
  anything changes; the kept manifest is put back as it
  was). The new engine is copied beside the bundled one and swapped in whole; after it is in, SoulRun's calls are
  tried on it and a named program is run, with the way back printed when they fail. With `--legacy-clean` every
  changed text is listed in `.engine_backups/cleaned-texts-<version>-<time>.txt`; a backup of an engine that had
  drifted from its manifest says so in its name, bringing the bundled engine in again still runs every check, and the
  engine version is written with it where DEPENDENCIES and GUIDE name it.
- **`soulrun --doctor`**: checks that leave nothing behind, that everything is in place for a run -
  versions, engine files, the slim program, the `python` a model's shell finds (for the entry-path form's engine tools,
  a sub-agent's and a program's own `python` tools), the agent folder and its
  programs, the engine interface (the functions, constants and parameters SoulRun calls, read from the engine),
  `soulrun_cache_dir` (writability tried with one file removed at once), a missing `.gitignore`,
  runs that never finished, time-zone data in this Python and the model's, and on Windows whether a run's
  deepest files would pass the 260-character limit, the program form a run gets (a warning when the slim program
  cannot be built and every run would fall back), and the engine's own
  environment settings, read the way the engine reads them (`CACHE_NUM` decides how many runs are kept); `--json` for one
  object. It uses the same folders and named programs as a run with the same arguments, wants `python` itself
  (not only `python3`), never runs a `python` found in the current folder, and reports a broken setup as FAIL
  lines instead of breaking; it names the agent folder's registry scripts (run at every run, never by the doctor)
  and, on Linux and macOS, a run folder other users can open, and a wrong run folder does not hide the programs
  check.
- **Processes at the same time.** Preparing a run holds an operating-system lock on
  `.soulrun_cache/.soulrun/prepare.lock` as well as the in-process lock, so `soulrun` command lines started
  together never take the same run number; an index another process is replacing,
  refused for a moment on Windows, is read again; a file system without locks is reported at once
  (`PREPARE_LOCK_UNSUPPORTED`). A byte-order mark at the start
  of the user's words is dropped. `soulrun.host` doors do not create the run folder, and a copy with a
  damaged engine still imports, so `--doctor` and `--verify-engine` report it instead of failing to start.
- **Development extras** (`.[dev]`) include `tzdata`, so a Windows development environment reads named zones as
  a run does (no test needs it), `pytest-timeout` (a test that hangs fails after 5 minutes) and `mypy`. SoulRun still has
  no run-time dependency.
- **Packages.** A wheel and a source archive build with hatchling. `tools/check_dist.py` checks that
  the wheel carries exactly the engine files the manifest installs, that there is no runtime
  dependency, that no cache, run data, kept engine, repository folder or `.env` file is inside, and that no file
  or archive header holds a home-folder path, an unexpected e-mail address or a user name; a path that is not a
  package, or nothing checked at all, is a problem, not an OK; so is a long description with a relative link.
  The wheel may hold only SoulRun's own files and the source archive only what pyproject.toml's sdist list includes,
  plus the `PKG-INFO`, `pyproject.toml` and `.gitignore` the build backend adds;
  credentials are looked for in every file, with the rules `tools/privacy_rules.py` shares with the documentation
  check. `SOULRUN_TEST_INSTALLED=1` runs the tests against an installed wheel instead of the source tree. Nothing in
  this repository uploads a package.
- **Typed.** `py.typed`, `run()` overloaded (a `Ctx`, or a `CmdResult` with `cmd=`), path arguments typed,
  `Ctx.kind` a literal; `tests/test_typing.py` type-checks a host written as the README writes one (mypy, in the
  dev extra). A type checker cannot see that the module itself is callable: such hosts use `from soulrun import run`.
- **The long description a package index shows** is README.md with every relative link and anchor written
  against the repository (`tools/pypi_readme.py`, a hatchling metadata hook built into the build backend; README.md
  itself is unchanged): on an index the README stands alone.
- **`tools/port_agent_text.py`** lifts the fixed wording and the opening instruction (`_SYSTEM_PROMPT`) from
  SoulBot's agent template so the entry-path form's text is what SoulBot's agent template gave before SoulBot ran
  on SoulRun, except on a confirmation after an interruption and a cancel: they run nothing, and get the template's
  text-only assertion and no entry block; a value written with a conversion or a format (`{x!r}`, `{x:>10}`) is
  refused, and a misspelt option is an error, never a rewrite.
- **`engine_node.aisop.json`** and `tools/build_engine_node.py`: the engine program arranged by engine
  node, every text copied verbatim from the engine, with `soulrun_delivery` saying which part goes with which
  engine node and why the rest is never handed out (plus the sub-agent program as `sub_agent_` nodes, a
  reference for a planned engine change); `--check` fails when the engine's program files change, or when a part
  refers to a text the model has not been given by then.
- **The slim form is the default; the model in the main conversation reads nothing itself and is given only what
  each step needs.** A turn
  starts with the group `entry` of the slim engine program (identity, `output_mode`, `hsaw_first_law`,
  `system_prompt`, the node execution and payload transport contracts, `Start`; `params` and `bootstrap_recovery`
  when it re-enters a run) in place of the path to
  `main.aisop.json`. Every other part follows the engine reply that first needs it, once per turn: SoulRun's
  command line prints the reply whole and first, then `[SOULRUN ENGINE NODE: <groups>]` and the part
  (recorded in `.soulrun/delivered/<run>.json`; nothing is added for a sub-agent's command), or, when the part would
  take the output past the engine's print cap, one line naming it and the `--engine-node` command that prints it. The entry block
  has the model run every engine tool as `"<python>" "<soulrun>/_launch.py" --cmd <name>` (this
  interpreter and this package by full path, whatever the shell's own `python` is) and get the business program
  from `--program` (a contract the engine's reply names, the engine's own `--read-program-contract`), never opening
  a program file, and `ctx.system_prompt` is its opening instruction. A turn with a
  note about an interruption keeps the slim form, the note followed first (a Stop's judgement begins with
  `stop_decision`; any text the note says to print comes before the first tool; the tools a note or an engine reply
  names go through SoulRun too); a turn that runs nothing gets no entry block. A turn falls back to the entry-path
  form, saying why in `ctx.slim_fallback`, when the slim program cannot be built, or when the run or the conversation's previous run went wrong in the slim
  form (still at Router.match with nothing committed after the model had its turn, or failed at an engine node):
  such a problem is kept in the run's note and the rest of that conversation stays in the entry-path form. A slim
  turn too long for a command line is printed in the entry-path form.
- **No host program on a command line.** A turn printed there tells the model it shows the human the blocks itself
  (`[SOULRUN SCREEN]`, an assertion line), and every engine command then prints, after the reply, the text of the
  blocks it names for the human (`[SOULRUN FOR THE HUMAN]`), once per turn; blocks past the print cap follow a later
  reply with room. The engine command's output is to be read whole (the entry block says so). `--json` and the
  Python call, for host programs, are unchanged.
- **The entry-path form** (`slim_program=False`, `SOULRUN_SLIM_PROGRAM=false`, `--no-slim-program`): SoulBot's
  text and opening instruction, word for word; the model reads `main.aisop.json` itself. A turn that runs nothing (a
  confirmation after an interruption, a cancel) gets the text-only assertion and no entry block here too.
- **Experimental second-stage form** (`inline_program`, off by default; it turns the slim form off): the main
  program with the user's words filled in, and the engine's output cap applied to what a command line prints.

### Documentation
- The documentation follows SoulBot's architecture: README / README_CN (what SoulRun is, Axiom 0 in
  SoulRun, quick start, architecture, usage, host doors, testing with a dated baseline, known limits,
  and the ecosystem footer), GUIDE (Chinese usage guide), INSTALL (Chinese install, build and publish
  guide), DEPENDENCIES / DEPENDENCIES_CN, SECURITY (English and Chinese), CONTRIBUTING / CONTRIBUTING_CN,
  GOVERNANCE, CODE_OF_CONDUCT, and a documentation map in `docs/README.md`.
- The design notes and the SoulBot integration guide moved to `docs/guide/01-design.md` and
  `docs/guide/02-soulbot-integration.md`.
- `tools/check_docs.py` checks links, anchors, fenced blocks, fenced Python, local paths, credential shapes,
  the shared footers and the version they name, and that no document names an old development version;
  `python tools/check_docs.py --set-version X.Y.Z` sets SoulRun's version in the package and in the documents'
  version lines (footers, the contribution guides' stage lines, the guides' head lines); the engine version the
  documents' engine-version lines name (DEPENDENCIES, GUIDE) is checked against the engine manifest. Setting a
  version changes the version only and keeps each file's line endings, so a Windows checkout's CRLF survives an
  engine upgrade and its `--restore`.
  Anchors follow GitHub's rule (symbols in a heading drop out), Setext headings count, a link in inline code or
  an HTML comment is not checked, and a link starting with `/` is read from the repository's root.
  The tests compare the footers, policy sections and license with SoulBot's, the fixed wording and SoulBot's send
  layer as well: with SoulBot itself when it is beside this repository, else with `tests/soulbot_samples.json`,
  recorded from it by `tools/record_soulbot_samples.py` - so CI compares too.
- CI pins its actions to commit SHAs (as SoulBot does), runs Python 3.11–3.14 and the documentation check,
  lists why any test was skipped (`-rs`), and writes no version range of its own: the release tools come from
  pyproject.toml through `tools/extra_requirements.py`, the test tools as the `dev` extra (of the source tree, and
  of the built wheel in the package job). Dependabot
  watches the Python extras and the actions.

### Known limits
See the README. The engine is not edited by hand here; changes reach it through `tools/upgrade_engine.py`.
Every 1.x engine keeps the feature set the engine inherited, including its guard against continuing a run another
engine version started; SoulRun also binds an unfinished run to the exact engine digest it began with.
