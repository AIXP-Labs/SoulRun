# SoulRun V1.0.0 Release Notes

SoulRun V1.0.0 is the fixed version during preparation for SoulRun's first release: the AISOP execution engine as one call, running AIAP programs and
AISP skills for any host. This file is maintained in English and Chinese below. It summarizes the release; the
[README](../README.md), its [known limits](../README.md#known-limits), the [security policy](../SECURITY.md) and the
[CHANGELOG](../CHANGELOG.md) give the details.

This document describes the candidate, not proof of a GitHub/PyPI publication or an updated local installation.
Verify the actual package source and manifest before use.

**CI update:** Windows and Ubuntu now each configure Python 3.11–3.15 source tests, plus one
Python 3.12 package job each (12 jobs total). The added 3.15 jobs await hosted execution; the preceding
10-job pass belongs to its recorded commit. See [Verification Scope](verification-1.0.0.md) for that
result and the dated local evidence. README historical tables were moved there, not erased.

**CI增补：** Windows、Ubuntu各配置Python3.11–3.15源码测试，再各加1项Python3.12包装，共12项。
新增3.15作业尚待远端执行，前一版10项通过只属于对应提交；准确结果和本地历史见[验证范围](verification-1.0.0.md)。
README旧表移到验证文档，不删除原证据。

## Install

```bash
python -m pip install soulrun                                          # from PyPI
python -m pip install "git+https://github.com/AIXP-Labs/SoulRun.git"   # or straight from GitHub
soulrun --version                                                      # soulrun 1.0.0 (engine 1.0.0)
soulrun --verify-engine                                                # the installed engine is the recorded one
```

Python 3.11 or later; no run-time dependency. Installing from a checkout of this repository is for people who
change SoulRun itself: see [INSTALL.md](../INSTALL.md).

## What V1.0.0 contains

- **One call.** `soulrun(user_message=...)` in Python, or the `soulrun` command, starts a run or continues the one the
  message belongs to; `cmd=` runs one engine command; with nothing given it hands back the guide and creates nothing.
- **The bundled engine.** It runs AIAP programs and AISP skills from the installed package, read-only; runs are kept
  apart from it, in `soulrun_cache_dir` (by default `<agent folder>/.soulrun_cache`, which ignores itself in version
  control).
- **The slim form by default.** In the main conversation the model reads no program file itself: the engine program
  is handed out by engine node, each part with the engine reply whose step needs it, and the business program through
  `soulrun --program`. The entry-path form (`slim_program=False`) hands the model SoulBot's text word for word; a
  turn that runs nothing gets no entry block in it either.
- **SoulRun asks instead of guessing.** A designated program not found, a run that does not belong to the
  conversation, two designated programs with no words, an unfinished run not made for the named program, and an
  unfinished run begun by another engine build or with no record of its build are questions for the human
  (`ctx.doubt`); no run is created.
- **Doors for hosts** (`soulrun.host`): references expanded for the human, the after-turn records, Stop, restart and
  broken-connection handling, and diagnostic reports of the sub-agents a host sees; reporting alone proves no identity.
- **`soulrun --doctor`** checks a machine before a run and leaves nothing behind.

SoulRun opens no network connection and never talks to a model; a host does.

## The engine

| Item | Value |
|---|---|
| Version | `1.0.0` (`soulrun.ENGINE_VERSION`) |
| Source form | `canonical`: every runtime file kept byte for byte |
| Files | 97 runtime files, each recorded in `src/soulrun/engine_manifest.json` |
| Digest | `9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b` (`soulrun --engine-info`) |

Every 1.x engine keeps the feature set the engine inherited. The digest, not the version number, names an engine
build, and a run is bound to the exact engine digest it began with: an unfinished run begun by any other build - even
one with the same version number - or with no record of the build that began it is not continued. On a human
turn SoulRun asks whether to end it (a reply of one cancel word, for a run of the same engine version), to work in
another conversation, or to leave it; a machine turn is refused (`ENGINE_BUILD_MISMATCH`). Upgrade SoulRun when no
run is waiting.

## Verified for this build

November 11 local results for the current `9e618...` manifest are recorded separately from the older
table below: Windows Engine 8613 passed / 9 skipped / 8622 collected; Ubuntu Engine 8606 / 16 / 8622;
Windows SDK source 912 / 3 / 915; Ubuntu SDK source on each of Python 3.11–3.15, and its fresh installed
3.12 wheel, 911 / 4 / 915. All have zero failures/errors. The subsequent QA guard repair passed 17 tests
on each platform; 8626 current IDs are composed from the unchanged full selection plus that targeted
repair, **not one 8626-test full run**. Windows SDK matrix/cold-install evidence is exact-payload inheritance.
The dated Python 3.15 measurements are local compatibility checks, not hosted-CI evidence or a support-policy change. User-site CLI/SDK installation
was verified; production was not updated. Release-check/tool/documentation revisions need separate
fresh receipts and artifacts; no hosted CI, upload or new model/long-flow qualification is implied.

The following older results and artifact history are retained, not relabeled as current runs.

The tested manifest `9aaa6035d21381fe531cc480d137df1fcd25d7f24c9a395c72d107280d0f9e65`
predates the AIAP history/usage revisions and standalone caller-guide correction. Executable files and
governance fields did not change; guide text changes still require their own checks and do not create model qualification.
The preceding manifest's recorded Windows results are Engine
8565 passed / 9 skipped and package 866 passed / 3 skipped; Ubuntu results are Engine
8546 passed / 16 skipped and package 866 passed / 3 skipped. All have zero failures/errors.
These precede this documentation revision. Exact collected counts, nonidentical suite inventories,
skip handling, real-model runs, inherited cases and remaining observations are in
[Verification Scope](verification-1.0.0.md). That page is also the qualification boundary for this release preparation.

New prose does not appear automatically in prior artifacts. No release or upload is performed by this review;
new artifacts must be built and checked before publishing the revised source.

### Historical results

Results of November 4, 2026, on an earlier 96-file build with digest
`f1884f3ff58d61dd63a477ae9fb3d4b367895e513bbae159885f176770e24680`:

| Scope | Environment | Result |
|---|---|---|
| SoulRun's test suite, from source | Windows, Python 3.12.9 | 701 passed, 5 skipped |
| The canonical engine's own test suite (kept outside this repository) | run against this engine, Windows, Python 3.12.9 | 7186 passed, 14 skipped |

Results of October 30, 2026, on the build this one follows (engine digest
`4b7cd1fc2269bf464b3c8ed13d36c85dbca3196ea44835bc5c373f49b86a7b2b`), not repeated on this build:

| Scope | Environment | Result |
|---|---|---|
| SoulRun's test suite, from source | Windows, Python 3.12.9 | 656 passed, 3 skipped |
| The canonical engine's own test suite (kept outside this repository) | run against that engine | 4120 passed, 12 skipped, 0 failed |
| SoulBot's complete test suite with that build installed (an isolated copy) | Windows, Python 3.12.9 | 3325 passed, 18 skipped, 29 deselected, 1 xfailed |
| The wheel | `tools/check_dist.py`; `twine check --strict` (twine 7.0.0) | both passed: 129 files, 96 engine files matching the manifest, privacy checked |
| Real-model smoke runs through SoulBot | Claude Opus 5.5, an isolated acceptance environment | an I Ching reading: COMPLETED, PASS; a stock analysis (MSFT, full): COMPLETED, DEGRADED - that environment has no market-data MCP servers, so the program fell back to web search and marked its figures unverified; a run stopped mid-way and continued with "继续": COMPLETED, PASS |

Counts describe separate runs and are not added together. No test calls a model; the smoke runs did.

**Remaining qualifications:** no new hosted-CI or macOS result; the local Python 3.11–3.15 checks have only
the dated scope above. The Codex reporting-host path remains unqualified, Creator long flows are deferred, and
the web normal-flow passes do not qualify browser child handover or Telegram. A configured CI matrix is
not a result, and an earlier build's result is not automatically this revision's result.

## Boundaries

- **Not a sandbox.** In a qualified host, gates reject managed operations that lack the required human answer,
  authority, ticket or evidence. SoulRun is not an OS sandbox, does not prove arbitrary `ASSERT` expressions, and
  does not establish that a model's analysis is correct. File digests detect changed content; they are not an
  independent signature.
- **Reports do not prove original-child identity.** All host reports are diagnostic by default. Where identity
  cannot be established, the presented business gate can combine an explicit business `execute` choice with
  permission for a new agent to continue recorded work. Cancel and terminate keep their kind and label and grant
  no replacement authority or new ticket. Pause does not consume the business gate. Loss after an ordinary
  answer, missing handover wording or unclear permission requires a separate question. Fencing the old ticket
  does not prove its process exited; unknown external side effects must be checked before repeating work.
- **A business gate a sub-agent pauses at is shown by SoulRun at the main conversation's next step**, which the
  contract has the main conversation call before it presents that gate, in any host - SoulRun's own command line (it
  sees no tool calls) included. A return report does not publish the menu or count it as shown; a reply before the
  main step is held. This fixes presentation, not original-child continuation on hosts lacking trustworthy tool events.
- **The slim form reaches the main conversation only.** The engine still hands a sub-agent the path of its own engine
  program (`agent_engine.aisop.json`), and the sub-agent reads it. A turn that falls back to the entry-path form
  (`ctx.slim_fallback` says why) has the model read `main.aisop.json` itself.
- **Other backends are qualified on their own.** The smoke runs above (on the October 30 build) used Claude Opus 5.5
  through SoulBot. They do not qualify another backend, such as SoulBot's Codex backend: its sub-agent dispatch,
  approvals, continuation and fault recovery need evidence of their own.
- **Business programs are qualified on their own.** The Creator programs' version detection and target migration are their
  own work; the engine carries no Creator-specific code (see the README's known limits).
- **Records are not rewritten.** A run whose records are missing or contradictory is refused, never rewritten or
  re-signed, and a lost executor's state is never guessed.
- **Direct CLI output is not guaranteed model forwarding.** SoulRun can print every block, with paging when
  needed; a model may omit it when relaying tool output. Use direct full output or deterministic host rendering
  when the human must see all text. Run data and tool output can contain private information; ignore rules
  do not encrypt it or remove previously tracked files. See [SECURITY.md](../SECURITY.md).

## Source-form release checks

For maintainers. The read-only command `python tools/sync_engine.py --check-release` verifies the manifest's
explicit source form, its file map (nonempty, no name twice), the exact runtime file inventory, per-file and
aggregate digests, the version and privacy. Links and reparse points, unsafe paths, files that are not shipped and
unknown forms are refused. It writes no manifest and adds no known-leftovers exemption. Digest records are not
independent signatures.

- `canonical`: every accepted source byte is kept, historical lineage included; the canonical identity,
  license/attribution and the complete contract map and digests are verified. A failed canonical check never falls
  back to legacy.
- `legacy-clean`: the original `clean_engine.py --check` history check and its exact-hash policy still apply. A
  canonical program identity cannot claim this form. Legacy conversion is only the explicit upgrade path
  (`tools/upgrade_engine.py --legacy-clean`), never a way to modify canonical files or force them through the check.

On a canonical tree the legacy history command can still report historical matches; that is why the release check
goes by source form. It does not replace the privacy, integrity or authorization requirements: AIAP conformance,
the slim-program check, distribution privacy, license and metadata checks remain required.

License: [Apache License 2.0](../LICENSE) - Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev.

---

# SoulRun V1.0.0 发布说明

SoulRun V1.0.0 是首次发布准备期间的固定版本：把 AISOP 执行引擎变成一个调用，为任何宿主运行 AIAP 程序与 AISP 技能。本文件与上文英文
成对维护，只是发布概要；细节见 [README](../README_CN.md) 和其中的[已知限制](../README_CN.md#已知限制)、[安全政策](../SECURITY.md)
与 [CHANGELOG](../CHANGELOG.md)。

本文描述候选，不证明GitHub/PyPI已经发布或本机安装已更新。使用前核对实际包来源和清单。

## 安装

```bash
python -m pip install soulrun                                          # 从 PyPI
python -m pip install "git+https://github.com/AIXP-Labs/SoulRun.git"   # 或者直接从 GitHub
soulrun --version                                                      # soulrun 1.0.0 (engine 1.0.0)
soulrun --verify-engine                                                # 装好的引擎就是清单里记下的那一份
```

需要 Python 3.11 或更高版本；没有运行时依赖。从本仓库的源码安装是给要改 SoulRun 本身的人的，见 [INSTALL.md](../INSTALL.md)。

## V1.0.0 里有什么

- **一个调用。** Python 里的 `soulrun(user_message=...)` 或 `soulrun` 命令：开始一场运行，或接着这句话所属的那一场；`cmd=`
  执行一条引擎命令；什么都不给时交回使用说明，什么也不创建。
- **带着的引擎。** 从装好的包里只读地运行 AIAP 程序与 AISP 技能；运行另放在 `soulrun_cache_dir`（默认 `<代理目录>/.soulrun_cache`，
  它自己把自己排除在版本控制之外）。
- **默认简装形式。** 在主对话里，模型自己不读任何程序文件：引擎程序按引擎节点交出，每一部分跟着需要它的那条引擎回复给；业务程序经
  `soulrun --program` 给。入口路径形式（`slim_program=False`）交给模型的是 SoulBot 的原文；不运行任何东西的轮次在这种形式下也不带入口段。
- **拿不准就问，不猜。** 指定的程序找不到、点名的运行不属于这个对话、指定了两个程序却没有话、没做完的运行不是为点名的程序开的、
  没做完的运行是另一个引擎构建开的或者没有记下是哪个构建开的，都作为问题交给人（`ctx.doubt`），不创建运行。
- **给宿主的入口**（`soulrun.host`）：把引用展开给人看、每轮之后的记录、Stop、重启和断线的处理，以及子代理诊断报告入口；报告本身不证明身份。
- **`soulrun --doctor`** 在运行前检查本机，不留下任何东西。

SoulRun 不联网，也从不和模型对话；和模型对话的是宿主。

## 引擎

| 项 | 值 |
|---|---|
| 版本 | `1.0.0`（`soulrun.ENGINE_VERSION`） |
| 来源形式 | `canonical`：每个运行文件逐字节保留 |
| 文件 | 97 个运行文件，每个都记在 `src/soulrun/engine_manifest.json` |
| 摘要 | `9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`（`soulrun --engine-info`） |

所有 1.x 引擎都保留引擎继承下来的那一套功能。标明一个引擎构建的是摘要，不是版本号；一场运行绑定它开始时的完整引擎摘要：别的构建开的
（即使版本号相同）、或者没有记下是哪个构建开的、没做完的运行，不会被接着跑。人的一轮会被问：结束它（回复一个取消词；限同一引擎版本开的运行）、换一个对话做，还是先放着；机器的一轮直接拒绝（`ENGINE_BUILD_MISMATCH`）。
所以请在没有运行在等的时候升级 SoulRun。

## 这个构建验证过的结果

11月11日当前`9e618...`摘要的本地结果与下方旧表分开：Windows Engine8613通过/9跳过/收集8622，
Ubuntu Engine8606/16/8622；Windows SDK源码912/3/915；Ubuntu SDK源码Python3.11–3.15每组以及
全新3.12安装wheel均911/4/915，全部0失败/错误。随后QA守卫窄修双平台各17项通过；
当前8626编号由未变的完整选择加定向守卫组成，**不是8626项单场全量**。Windows SDK矩阵/冷安装按准确正文继承。
上述Python3.15测量仅属本地兼容，不是远端CI证据或支持政策变更；用户site CLI/SDK已核，生产未更新。
发行工具/文档修订须有独立新回执和制品，不意味着远端CI、上传、新模型或长流程资格。

下面保留旧结果和制品历史，不重标为当前实跑。

已测摘要`9aaa6035d21381fe531cc480d137df1fcd25d7f24c9a395c72d107280d0f9e65`早于AIAP历史/使用说明修订及独立调用说明修正。
执行文件和治理字段未改；说明文字变化仍须单独检查，不增加模型资格。
之前摘要的已记录 Windows 结果：Engine 8565 通过 / 9 跳过，包装 866 通过 / 3 跳过；
Ubuntu：Engine 8546 通过 / 16 跳过，包装 866 通过 / 3 跳过，均无失败或错误。
这些发生在本次文档修订之前。准确收集数、两套不完全相同的测试清单、skip、真实模型、继承用例和剩余观察见
[验证范围](verification-1.0.0.md)，该页也是本次发布准备的资格边界。

新文档不会自动进入旧制品。本轮不发布、不上传；发布修订后的源码前，须重新构建并检查新制品。

### 历史结果

2026 年 11 月 4 日，更早的 96 文件构建，摘要
`f1884f3ff58d61dd63a477ae9fb3d4b367895e513bbae159885f176770e24680`：

| 范围 | 环境 | 结果 |
|---|---|---|
| SoulRun 自己的测试，从源码 | Windows，Python 3.12.9 | 701 通过，5 跳过 |
| 规范引擎自己的测试（放在本仓库之外） | 对这份引擎运行，Windows，Python 3.12.9 | 7186 通过，14 跳过 |

2026 年 10 月 30 日，在这个构建之前的那个构建（引擎摘要
`4b7cd1fc2269bf464b3c8ed13d36c85dbca3196ea44835bc5c373f49b86a7b2b`）上，没有在这个构建上重做：

| 范围 | 环境 | 结果 |
|---|---|---|
| SoulRun 自己的测试，从源码 | Windows，Python 3.12.9 | 656 通过，3 跳过 |
| 规范引擎自己的测试（放在本仓库之外） | 对那份引擎运行 | 4120 通过，12 跳过，0 失败 |
| 装上那个构建后 SoulBot 的全部测试（隔离副本） | Windows，Python 3.12.9 | 3325 通过，18 跳过，29 未选，1 预期失败 |
| wheel | `tools/check_dist.py`；`twine check --strict`（twine 7.0.0） | 都通过：129 个文件，96 个引擎文件与清单一致，隐私已查 |
| 经 SoulBot 的真实模型冒烟 | Claude Opus 5.5，隔离验收环境 | 易经：COMPLETED，PASS；股票分析（MSFT，full）：COMPLETED，DEGRADED——那个环境没有行情数据的 MCP 服务，程序改用网页搜索，并把数字标为未核实；中途停下、用「继续」接着跑的一场：COMPLETED，PASS |

各行是分开的运行，不相加。测试不调用模型；冒烟调用了。

**剩余资格：** 没有新的远端 CI 或 macOS 结果；本地Python3.11–3.15仅具有上方带日期的范围。
Codex 会报告宿主仍未合格，Creator 长流程延期，正常网页流程通过不代表浏览器 child 换人或 Telegram 通过。
配置 CI 矩阵不等于运行结果，更早构建的结果不能自动算作本修订的结果。

## 边界

- **不是沙箱。** 在合格宿主里，缺少所需的人的回答、授权、票据或证据的受管操作会被门拒绝。SoulRun 不是操作系统沙箱，不能证明任意
  `ASSERT` 表达式，也不保证模型的分析正确。文件摘要能发现内容变了，但不是独立签名。
- **报告不证明原 child 身份。** 所有宿主报告默认只作诊断。身份无法核实时，业务门可把明确的业务 `execute` 选择与新代理接续授权合并；
  cancel、terminate 保留原种类和原标签，不授权换人、不发新票；暂停不消耗业务门。普通答复后才失联、旧题没有换人文字或授权不清楚时须另问。
  封住旧票不证明进程退出，外部操作结果不明时先核对，不直接重做。
- **子代理停下的业务门，由 SoulRun 在主对话下一步给人看。** 契约规定主对话在给人看这道门之前先取这一步，任何宿主都一样（看不到
  工具调用的 SoulRun 自己的命令行也一样）。宿主报告子代理交回，不发布菜单、不算给人看过；主对话取下一步前的回答先不收。
  这解决的是展示，不代表缺少可信工具事件的宿主上的原child续跑已解决。
- **简装形式只到主对话。** 引擎交给子代理的仍是它自己那份引擎程序（`agent_engine.aisop.json`）的路径，子代理自己去读。退回入口
  路径形式的一轮（原因写在 `ctx.slim_fallback`），模型会自己读 `main.aisop.json`。
- **其它后端的资格单独认定。** 上面的冒烟（在 10 月 30 日那个构建上）用的是经 SoulBot 的 Claude Opus 5.5，不能替别的后端（比如 SoulBot 的 Codex 后端）作证：
  那样的后端，子代理派发、审批、续跑和故障恢复都要有自己的验证。
- **业务程序的资格单独认定。** Creator 程序的版本识别和目标迁移是它们自己的事；引擎里没有为 Creator 写的特判（见 README 已知限制）。
- **不改写记录。** 记录缺失或互相矛盾的运行会被拒绝，从不改写、从不补签，也从不猜测丢失的执行者的状态。
- **CLI 直接输出不等于模型一定转发。** SoulRun 能直接输出全部块，必要时分页；模型转述工具输出仍可能遗漏。
  必须让人看全时使用 CLI 直接全文输出或宿主确定性渲染。运行数据、工具输出可能含隐私；ignore 不加密，也不移除已跟踪文件。见[安全政策](../SECURITY.md)。

## 来源分支发布检查

给维护者。只读命令 `python tools/sync_engine.py --check-release` 核对清单显式写明的来源形式、文件清单（非空、没有重名）、精确的运行文件、
逐个文件与总的摘要、版本和隐私。链接/重解析点、不安全路径、不应分发的文件和未知来源一律拒绝；不写清单，也不新增 known-leftovers
豁免。摘要记录不是独立签名。

- `canonical`：保留全部已接受的来源字节，包括历史谱系；核对规范身份、许可/署名、完整的契约清单和摘要。canonical 检查失败绝不自动转 legacy。
- `legacy-clean`：仍执行原来的 `clean_engine.py --check` 历史检查及其精确哈希政策；canonical 程序身份不能声称是这种形式。旧开发树的转换
  只走显式的升级通道（`tools/upgrade_engine.py --legacy-clean`），不能用来改写 canonical 文件或硬让它们过检查。

在 canonical 树上，legacy 历史检查命令仍可能报出历史匹配，所以发布检查按来源形式分支。它不替代隐私、完整性或授权要求：AIAP 符合性、
简装程序检查、分发隐私、许可和元数据检查仍然必需。

许可：[Apache License 2.0](../LICENSE) - Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev。
