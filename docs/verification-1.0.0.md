# SoulRun V1.0.0 Verification Scope / 验证范围

## English

### CI Matrix Extension: Python 3.15

The workflow now configures Windows and Ubuntu × Python 3.11–3.15: 10 source-test jobs plus
2 package jobs on Python 3.12. The added 3.15 jobs await hosted execution; configuration is not a pass.
The preceding commit, `e4f852f`, passed [CI run 1](https://github.com/AIXP-Labs/SoulRun/actions/runs/43109708518)
with 10 jobs (source 3.11–3.14 and the two package jobs). That result is not a qualification of this revision.
The dated local and inherited results below retain their original scope. Minimum Python, dependencies,
execution policy and package version remain unchanged. Archive tables moved out of the README are
preserved in the [README history archive](#readme-history-archive).

### November 11 Completed Local Qualification

Digest `9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`,
97 runtime resources and 124 installed payload files. These completed measurements followed the
history/guide corrections and preceded the current release-check hardening. They are dated evidence,
not a fresh qualification of every later tool/test/documentation edit.

| Scope | Actual result |
|---|---|
| Windows 3.12.9 Engine full selection | 8613 passed, 9 skipped, 8622 collected; 0 failed/errors, clean exit |
| Ubuntu 3.12.3 Engine full selection | 8606 passed, 16 skipped, 8622 collected; 0 failed/errors, clean exit |
| Windows 3.12.9 SDK source suite | 912 passed, 3 skipped, 915 collected; 0 failed/errors |
| Ubuntu SDK source suite, each of 3.11.18/3.12.3/3.13.18/3.14.10/3.15.2 | 911 passed, 4 skipped, 915 collected in each separate run; 0 failed/errors |
| Fresh Ubuntu 3.12.3 wheel installation | 911 passed, 4 skipped, 915 collected; 0 failed/errors |
| Subsequent QA-only guard repair, Windows and Ubuntu separately | 17 passed, 0 skipped/failed/errors on each platform |

The last row replaces 13 QA guard cases from the full selections; 8609 unaffected IDs and their inputs
were unchanged. The latest 8626-ID scope is a **composed qualification, not one full run of 8626**.
Windows SDK 3.11–3.15 and Windows cold-install evidence is inherited from the exact unchanged payload.
Neither inheritance nor a local Python 3.15.2 pass changes the configured CI matrix or public support policy.

All 25 Engine platform skips passed by the same ID on the opposite platform. Native Windows symlink
privileges still limited eight Windows cases; do not relabel them as Windows passes. SDK skips across
source/installed/platform runs deduplicate to six IDs: five have a pass in another applicable setup;
the old SoulBot fixed-wording comparison is inapplicable to its SoulRun entry. Retired v6 targets remain retired.

Five Python lines each completed seven local CI-equivalent gates (35 jobs), with zero failures. The existing
conformance C-06/C-09 warnings remain. Hosted CI, macOS, browser child-handover/Telegram, the Codex
reporting-host restricted case and Creator long flows were not qualified by those checks.

A user-site CLI/SDK install subsequently verified all 124 payload files, both shared-user-site interpreter
entries, the console command and integrity/negative controls. No production host was updated. Another
environment with the same version string is not necessarily the same payload; unfinished runs remain
bound to their original digest. The installed payload and source archive passed strict privacy/metadata checks,
sdist rebuilding and cold validation. The original artifact identities before this release-check refresh are:

| Dated, pre-refresh artifact | SHA-256 |
|---|---|
| Windows wheel | `4c1ac1bcd7f3c0cb9ecc556b50f75da7dd5b2fbbb5be3d4821c78af8afd0f00b` |
| Linux wheel | `dcac289dab173146c08f31a2db04b4c731b1c1fe2981cd14491a9ce736bcf87a` |
| Source archive | `c2eb1baec5861ee8c075b7d02cf9e9e1ca2ab1a53236af9fcbf56aeeb9b9f352` |

The wheel members have identical contents; archive platform metadata differs, so the wheel hashes differ.
These files do not acquire later release-tool or README changes. A new release candidate is frozen separately,
with its own tests and artifact hashes in maintainer receipts; do not embed its own future archive hash back
into the README being packaged. No upload, production update or new model qualification follows automatically.

### Runtime Head and Dated Evidence

The current source manifest after the user-authorized AIAP history trim and host-neutral usage correction is
`9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b` (97 resources).
Only that engine Markdown resource changed; the standalone caller guide was corrected separately.
Executable sources and governance fields remain unchanged.
The following measurements identify the earlier manifest explicitly; they are not fresh qualification of
the trimmed head. Old runs and installed packages are not rewritten or migrated by a source edit.

Earlier qualified runtime head, reviewed on 2026-11-11, version `1.0.0`: 97 engine resources,
manifest digest `9aaa6035d21381fe531cc480d137df1fcd25d7f24c9a395c72d107280d0f9e65`.
These results belong to that runtime head **before the documentation and repository-hygiene
revision below**. They are not newly measured results for every changed public input or a new package.

| Recorded environment | Passed | Failed / errors | Skipped | Collected |
|---|---:|---:|---:|---:|
| Windows, Python 3.12.9, shared Engine suite | 8565 | 0 / 0 | 9 | 8574 |
| Windows, Python 3.12.9, SoulRun package suite | 866 | 0 / 0 | 3 | 869 |
| Ubuntu, Python 3.12.3, Engine suite | 8546 | 0 / 0 | 16 | 8562 |
| Ubuntu, Python 3.12.3, SoulRun package suite | 866 | 0 / 0 | 3 | 869 |

The Windows shared suite has 12 additional test IDs for the relocated test infrastructure; it is not
the Ubuntu suite with a different pass count. A skipped Ubuntu doctor test separately passed in a
short temporary directory; it remains a skip in the full run. Of the 12 Windows skips, 10 have
separate Linux passes; the old root-level distribution fixture and legacy host-template test remain
inapplicable. Complementary evidence does not turn either full run into a zero-skip run.
Thirteen retired historical replay targets are retired, not passed. No v6 record-compatibility
promise is restored by these results.

Python `>=3.11` is a declared minimum. CI configures Windows and Ubuntu with Python 3.11 to 3.14;
configuration is not a hosted-CI result. Other Python versions have earlier-head evidence only;
macOS and the relocated Linux QA environment have no new qualification here.

The intervening history-trim source `49a47db1ac45afa0f3c4f7c470fa19354df6092474de799150c92e86078159c0`
had separate Windows package results of 908 passed / 3 skipped / 911 collected, plus 37 targeted Engine
parser/conformance passes, with zero failures/errors. That was not an Engine full-suite rerun, a Linux run,
a model run or an installed-package update. Keep it separate from both the table and the current documentation head.

### Limited Real-Model Evidence

| Path | Actual scope | Not established |
|---|---|---|
| Codex CLI | Real CLI handover on the 97-resource head | Every CLI configuration, every output block being forwarded by the model |
| Codex SDK | Continue inherited from the earlier SDK run after exact behavior comparison; cancel inherited from the corrected cancel run | A fresh model run for each inherited case |
| Codex reporting host | Dispatch input was encrypted by the platform; qualification stopped | Qualified reporting-host dispatch or original-child identity |
| Claude reporting host, CLI and SDK | Three real short flows on this runtime head using SoulACP 0.2.6; reporting host used an isolated SoulBot release161 synthetic `/run` path | Production web handover, all providers, arbitrary long flows |
| Isolated SoulBot release175 web, Claude and Codex | Separate normal I Ching flows, streamed final text checked | Browser handover: neither flow exercised a child business gate; Telegram |

The Codex short flows used SoulACP 0.2.5 and are not relabeled as 0.2.6 runs. Model identity was
checked against actual session records, not just configuration. Creator long-flow qualification
is deferred, independently of the public executor. Provider authentication, retry transport and
framework rendering failures are recorded at their own layer, not repaired with program-specific
Engine branches.

Reporting events are diagnostic by default, **not proof of original-child identity**. When identity
cannot be established, only an explicit `execute` choice authorizes a new agent to continue recorded
work. Cancel and terminate do not grant that authorization. Fencing an old ticket does not prove
the old process exited. A successful short flow does not remove these boundaries.

### Open Observations

- Two projections of the same accepted answer can be summarized as two answers by a model.
- An anomaly recorded before a node pauses can be absent from the final run-wide anomaly summary.
- A crash window can leave the terminal handover receipt pending; negative checks show no new
  execution authority is granted, and safe ending remains available.
- A cancelled node can be recorded as `FAILED`; this is not permission to repeat it.
- Model output has exposed an internal English instruction; a child also once misused an engine
  node argument. These are observations, not corrected runtime behavior in this review.
- Generic recovery rules and connection-layer authentication must be distinguished; a wait
  timestamp alone is not an independent execution-duration measurement.

The framework's non-streaming `/run` capture observation is limited to that path: compliant
output-before-`@host` submission can be rejected once, and other `@host` text can be degraded when
capture is unavailable. Streamed web final-text transfer passed in the two normal flows above;
Telegram remains untested. These are framework observations, not new SoulRun special cases.

### Artifacts and This Documentation Revision

The prior frozen wheel and source archive passed strict package/privacy checks, source-archive
cold rebuilding and Twine 7 strict validation:

| Historical artifact | SHA-256 |
|---|---|
| `soulrun-1.0.0-py3-none-any.whl` | `0621c9ca684b7a42fd258206967188763fb0f8038fa6d5c8732eb40d0e1e65e0` |
| `soulrun-1.0.0.tar.gz` | `6d4c9ef0996428c7c79335cb22f2210cc586e6e6d3fa4894a2fd0486cb4d4022` |

They are retained historical artifacts. Editing README, release prose, ignore rules, tests or CI
changes the public source input; unchanged runtime files do not make an old wheel contain new
README metadata. Build into a new directory and verify new artifacts before releasing this revision.
This documentation review does not install, deploy, upload, run models, rerun Linux or claim hosted CI.
New local documentation/hygiene test results are recorded separately; they do not replace the table above.

## 中文

### CI矩阵增补：Python3.15

工作流现配置Windows、Ubuntu × Python3.11–3.15：10项源码测试，加Python3.12的2项包装作业。
新增3.15作业尚待远端执行，配置不等于通过。前一提交`e4f852f`的
[CI第1场](https://github.com/AIXP-Labs/SoulRun/actions/runs/43109708518)是10项通过
（源码3.11–3.14和2项包装），不能替本次修订判通过。
下列带日期的本地/继承结果保持原范围；最低Python、依赖、执行策略和版本均未改。
从README移出的旧表保存在[README历史归档](#readme-history-archive)。

### 11月11日已完成的本地验收

摘要`9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`，
97份运行资源、124份安装正文。以下实测发生在历史/guide修正之后、本次发行检查器加固之前；
是带日期的证据，不表示后来的每次工具、测试或文档修订都新测过。

| 范围 | 实际结果 |
|---|---|
| Windows3.12.9 Engine完整选择 | 8613通过、9跳过、收集8622；0失败/错误，正常退出 |
| Ubuntu3.12.3 Engine完整选择 | 8606通过、16跳过、收集8622；0失败/错误，正常退出 |
| Windows3.12.9 SDK源码 | 912通过、3跳过、收集915；0失败/错误 |
| Ubuntu SDK源码3.11.18/3.12.3/3.13.18/3.14.10/3.15.2分别独立运行 | 每组911通过、4跳过、收集915；0失败/错误 |
| Ubuntu3.12.3全新wheel安装 | 911通过、4跳过、收集915；0失败/错误 |
| 随后QA守卫窄修，Windows/Ubuntu分别 | 各17通过，0跳过/失败/错误 |

最后一行替代完整选择中的13项QA守卫；其余8609个编号及输入严格未变。
最新8626编号是**组合资格，不是8626项单场全量**。Windows SDK3.11–3.15和Windows冷安装按准确不变正文继承。
继承及Python3.15.2本地通过均不改变CI矩阵或公开支持政策。

25项Engine平台skip均在另一平台按原ID通过；8项Windows原生symlink仍缺权限，不能改记成Windows通过。
SDK的源码/安装/平台skip去重为6个编号，5个在其他适用场景通过，旧SoulBot固定文案比较对其SoulRun入口不适用。
已退休v6目标仍是退休，不补成通过。

5条Python线各完成7道本地CI等价门，共35个作业，均无失败；原C-06/C-09合规WARN保留。
这些检查不新增远端CI、macOS、浏览器child换人/Telegram、Codex报告宿主受限格或Creator长流程资格。

随后本机用户site CLI/SDK更新核了124正文、两个共用用户site解释器入口、启动器及完整性/负向控制；
未更新生产宿主。同版本字符串不等于同一正文，旧未完成运行仍绑定原摘要。
原安装正文和源码包通过严格隐私/元数据、sdist重建及冷验。本次发行门刷新之前的原制品为：

| 带日期、刷新前制品 | SHA-256 |
|---|---|
| Windows wheel | `4c1ac1bcd7f3c0cb9ecc556b50f75da7dd5b2fbbb5be3d4821c78af8afd0f00b` |
| Linux wheel | `dcac289dab173146c08f31a2db04b4c731b1c1fe2981cd14491a9ce736bcf87a` |
| 源码包 | `c2eb1baec5861ee8c075b7d02cf9e9e1ca2ab1a53236af9fcbf56aeeb9b9f352` |

两wheel成员正文相同，平台归档元数据不同，所以整包SHA不同。旧文件不会自动带上后来的发行工具/README变化。
新候选须另行冻结，维护者回执保存其测试和制品SHA，不把未来包自身SHA回填进正在打包的README形成循环。
这不自动授权上传、更新生产或增加模型资格。

### 运行头与带日期的证据

经用户授权精简AIAP历史并改准宿主中立使用说明后，当前源码清单摘要为
`9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`，仍97资源。
引擎仅这份Markdown资源改变，独立调用说明另行改准，执行源码及治理字段未变。下列实测明确属于之前的摘要，不是当前文档头的新验收。
修改源码不会改写、迁移旧运行或已安装包。

之前已合格的运行头，2026-11-11 核查：版本 `1.0.0`，97 份引擎资源，清单摘要为
`9aaa6035d21381fe531cc480d137df1fcd25d7f24c9a395c72d107280d0f9e65`。
下表是这份运行头在**本次文档与仓库卫生修订之前**的实际结果；不是本轮对所有新公开输入或新安装包重测的结果。

| 已记录环境 | 通过 | 失败 / 错误 | 跳过 | 收集 |
|---|---:|---:|---:|---:|
| Windows，Python 3.12.9，共享 Engine 全量 | 8565 | 0 / 0 | 9 | 8574 |
| Windows，Python 3.12.9，SoulRun 包装全量 | 866 | 0 / 0 | 3 | 869 |
| Ubuntu，Python 3.12.3，Engine 全量 | 8546 | 0 / 0 | 16 | 8562 |
| Ubuntu，Python 3.12.3，SoulRun 包装全量 | 866 | 0 / 0 | 3 | 869 |

Windows 共享测试多出的 12 个编号用于迁移后的测试基础设施，不是给 Ubuntu 那套测试换一个通过数。
Ubuntu 一项 doctor 跳过在短临时路径单独通过，但原全量仍记跳过。Windows 合计 12 项跳过中，10 项另有 Linux 通过证据；
旧根目录制品夹具、旧宿主模板两项不适用。补充证据不能把任一全量改成零跳过。13 项历史回放已退休，不是通过，也不恢复 v6 老记录兼容承诺。

Python `>=3.11` 是声明的最低版本。CI 配置 Windows、Ubuntu 的 Python 3.11 至 3.14，不等于远端 CI 已通过。
其余 Python 版本只有更早运行头的证据；本页不增加 macOS 或迁移后 Linux QA 环境的资格。

中间的历史精简源码`49a47db1ac45afa0f3c4f7c470fa19354df6092474de799150c92e86078159c0`另有Windows包装908通过、3跳过、收集911项，
以及Engine解析/合规定向37通过，均无失败或错误。这不是Engine全量重跑、Linux、模型或已装包更新；不和上表、当前文档头混算。

### 有限真实模型证据

| 路径 | 实际范围 | 没有证明的内容 |
|---|---|---|
| Codex CLI | 97 资源运行头的真实 CLI 换人接续 | 所有 CLI 配置、模型转发每一块正文 |
| Codex SDK | 继续分支经逐项行为对照继承早期 SDK 场；取消分支继承修正后的取消场 | 每项继承结果都重新调用过模型 |
| Codex 会报告宿主 | 平台加密派发正文，资格验收停止 | 会报告宿主派发合格、原 child 身份可证 |
| Claude 会报告宿主、CLI、SDK | 本运行头三场真实短图，使用 SoulACP 0.2.6；会报告宿主为隔离 SoulBot release161 的合成 `/run` 路径 | 生产网页换人、所有服务商、任意长流程 |
| 隔离 SoulBot release175 网页，Claude 与 Codex | 分开跑的正常易经流程，核对流式终答 | 两场均无子代理业务门，不能证明浏览器换人；Telegram 未验 |

Codex 短图用的是 SoulACP 0.2.5，不能重标为 0.2.6。型号以真实会话记录核实，不只看配置。
Creator 长流程延期，和公共执行器资格分开。服务商认证、重试传输、框架渲染失败各归其层，不为它们在 Engine 加业务特判。

宿主报告默认只作诊断，**不是原 child 身份证明**。身份无法核实时，只有明确的 `execute` 选项授权新代理按已记录工作接续；
cancel、terminate 不授权换人。封住旧票不证明旧进程退出。短图通过不消除这些边界。

### 尚存观察

- 同一已接受答复的两份投影，可能被模型总结成两次回答。
- 节点停门前记录的异常，可能未进入最终全场异常汇总。
- 崩溃窗口可能使终态换人回执待补记；负向检查证明没有因此新增执行权，安全结束仍可用。
- 取消节点可能记成 `FAILED`，不代表可以重做。
- 模型曾暴露英文内部指令，child 也曾误用引擎节点参数。本轮只记观察，不冒称已修复运行行为。
- 通用恢复规则须与连接层认证分开；等待时间戳本身不是独立的执行耗时证据。

框架的非流式 `/run` 采集观察只限该路径：按规矩先输出、再 `@host` 提交可能拒收一次；采集不可用时其他 `@host` 文字也可能降级。
上面两场正常网页流式终答转交已通过，Telegram 仍未测。这些是框架观察，不是新的 SoulRun 特判。

### 制品与本次文档修订

上一冻结 wheel 与源码包已通过严格包装、隐私、源码包冷重建和 Twine 7 严格检查：

| 历史制品 | SHA-256 |
|---|---|
| `soulrun-1.0.0-py3-none-any.whl` | `0621c9ca684b7a42fd258206967188763fb0f8038fa6d5c8732eb40d0e1e65e0` |
| `soulrun-1.0.0.tar.gz` | `6d4c9ef0996428c7c79335cb22f2210cc586e6e6d3fa4894a2fd0486cb4d4022` |

它们作为历史制品保留。修改 README、发布说明、ignore、测试或 CI，会改变公开源码输入；运行文件不变不等于旧 wheel 已含新 README 元数据。
发布本修订前须在新目录重新构建、核验，不能覆盖旧制品。本次文档审查不安装、不部署、不上传、不调模型、不重跑 Linux，也不宣称远端 CI 全绿。
新的本地文档、卫生测试结果单独记录，不替换上表。

## README History Archive

These English and Chinese sections were moved out of the README during the Python 3.15 CI update.
Only relative link targets were relocated. Historical “current”, “this build” and CI 3.11–3.14 wording
refers to the previous README snapshot, not the extended matrix above. The measurements, qualifiers
and old artifact identities have not been upgraded to fresh results.

以下中英文区块从README移出，除相对链接按新目录调整外保持原文。区块中的“当前”“这一构建”及
CI3.11–3.14指原README快照，不是上方新增矩阵；原测量、限定和制品身份不改成新通过。

### Archived English README

#### Historical Runtime-Head Table

The table below identifies the earlier manifest, not a fresh run of the current documentation or future packages.

Runtime-head evidence reviewed November 11, 2026: SoulRun V1.0.0, engine 1.0.0, **97 runtime files**, digest
`9aaa6035d21381fe531cc480d137df1fcd25d7f24c9a395c72d107280d0f9e65`.
The version number alone does not identify the build. These measurements belong to the recorded head and inputs,
before this documentation review; they are not fresh test results for every later documentation or package change.

| Scope | Environment | Result |
|---|---|---|
| Engine tests in the shared QA workspace | Windows, Python 3.12.9; November 10–11 | 8565 passed, 9 skipped; 8574 total, 0 failed/errors |
| SoulRun's own tests, from source | Windows, Python 3.12.9; November 10–11 | 866 passed, 3 skipped; 869 total, 0 failed/errors |
| Same runtime-head engine tests | Ubuntu, Python 3.12.3; November 10 | 8546 passed, 16 skipped; 8562 total, 0 failed/errors |
| Same runtime-head SoulRun tests | Ubuntu, Python 3.12.3; November 10 | 866 passed, 3 skipped; 869 total, 0 failed/errors; one path-limited original ID separately passed in a short folder |

The 12 Windows skips are unchanged: 10 have same-head Linux pass evidence, one concerns old artifacts in the
checkout's `dist/`, and one is a legacy host-wording comparison that does not apply. Do not add complementary
platform results into a single zero-skip run. The old 13 retired targets are not counted as passes.

The prior artifact pair also passed strict package/privacy checks, a source-archive-to-wheel-to-clean-runtime chain
and Twine 7.0.0 `check --strict`. That pair predates this documentation change: preserve its identity; build and check
new artifacts before claiming that they contain updated prose. Limited real-host evidence, inherited results,
remaining observations and untested paths are listed in [Verification Scope](verification-1.0.0.md).

The [CI workflow](../.github/workflows/ci.yml) still configures Windows and Ubuntu with Python 3.11–3.14;
a configured matrix is not a hosted CI result. The new local checks do not qualify macOS, reporting-host
identity, browser handover gates, Creator long workflows or Telegram, and do not erase historical failures.

**Earlier builds.** These results belong to builds with an earlier engine digest (the October 30 build's was
`4b7cd1fc2269bf464b3c8ed13d36c85dbca3196ea44835bc5c373f49b86a7b2b`); they were not repeated on this build.

| Build | Scope | Environment | Result |
|---|---|---|---:|
| November 4, 2026; earlier 96-file engine digest `f1884f3ff58d61dd63a477ae9fb3d4b367895e513bbae159885f176770e24680` | SoulRun's own tests, from source | Windows, Python 3.12.9 | 701 passed, 5 skipped |
| November 4, 2026; same earlier head | Engine's own suite | Windows, Python 3.12.9 | 7186 passed, 14 skipped |
| October 30, 2026 | SoulRun's own tests, from source | Windows, Python 3.12.9 | 656 passed, 3 skipped |
| October 30, 2026 | The engine's own test suite, against that engine | — | 4120 passed, 12 skipped, 0 failed |
| October 30, 2026 | SoulBot's complete test suite, with that build installed | Windows, Python 3.12.9, a separate test environment | 3325 passed, 18 skipped, 29 deselected, 1 xfailed |
| October 30, 2026 | The wheel: `python tools/check_dist.py`, then `twine check --strict` (twine 7.0.0) | — | both passed: 129 files, the 96 engine files match the manifest, privacy checked |
| October 30, 2026 | Real model: Claude Opus 5.5 through SoulBot | a separate test environment | an I Ching reading: completed, PASS; a stock analysis (MSFT, full): completed, DEGRADED - that environment has no market-data MCP servers, so the analysis fell back to web search and marked its figures unverified; a run stopped mid-way and continued with "继续": completed, PASS |
| October 16, 2026 | SoulRun tests, from source | Windows, clean virtual environment, Python 3.11.17 | 546 passed, 2 skipped |
| October 16, 2026 | SoulRun tests, from source | Windows, Python 3.13.5 and 3.14.6 | 547 passed, 1 skipped each |
| October 16, 2026 | SoulRun tests and every check, from the source archive | WSL2 Ubuntu 24.04, Python 3.12.3 | 548 passed |

Earlier builds were also run with a real model through SoulBot's host (Claude Code): I Ching readings from start to
final answer, a repeated question through the repeated-reading gate included; the stock analysis through its export
gate; the AIAP Creator through its first gate and five dispatches of nodes to sub-agents, then a human Stop and the
Stop gate; after a Stop, a plain "continue" and a message the model has to judge; and, in a Claude Code session of
its own with a minimal SKILL.md, the AISP I Ching skill. In those slim-form runs the main conversation opened no
program file. On an earlier engine: choosing between two candidates by the human's words, a gate answered on the web
page, re-entry after a host restart and after a broken model connection, a streamed report taken up by the engine,
and a named program run with no user words
(the program asked the human through an HSAW doubt gate instead of making a question up).

### 原中文README归档

#### 历史运行头表

下表明确属于之前的摘要，不是当前文档或未来安装包的新实跑结果。

2026年11月11日核对的运行头证据：SoulRun V1.0.0，引擎1.0.0，**97份运行文件**，摘要
`9aaa6035d21381fe531cc480d137df1fcd25d7f24c9a395c72d107280d0f9e65`。
单凭版本号不能识别构建。以下实测属于记录中的运行头和输入，早于本轮文档审查；不是每次后续文档或安装包变化都重新跑过的结果。

| 范围 | 环境 | 结果 |
|---|---|---|
| 共享QA工作区的引擎测试 | Windows，Python 3.12.9；11月10–11日 | 8565 passed，9 skipped；总8574，0失败/错误 |
| SoulRun自己的源码测试 | Windows，Python 3.12.9；11月10–11日 | 866 passed，3 skipped；总869，0失败/错误 |
| 同一运行头的引擎测试 | Ubuntu，Python 3.12.3；11月10日 | 8546 passed，16 skipped；总8562，0失败/错误 |
| 同一运行头的SoulRun测试 | Ubuntu，Python 3.12.3；11月10日 | 866 passed，3 skipped；总869，0失败/错误；另有1个受路径限制的原ID在短目录单独通过 |

Windows的12个skip没有变：其中10项有同头Linux通过证据，1项针对检出目录dist中的旧制品，1项是旧宿主固定文案比较不适用。
不能把平台互补拼成一次零skip全量；已退休的13个旧目标也不算通过。

此前冻结的制品对还通过了严格包内/隐私检查、源码包到wheel再到干净运行环境的链，以及Twine7.0.0的`check --strict`。
那两份制品早于本轮文档修改：保留其身份；要声称安装包带着新文字，必须先重新构建并核验。
有限真实宿主、继承结果、开放观察及未验范围见[验证范围](verification-1.0.0.md)。

[CI工作流](../.github/workflows/ci.yml)仍配置Windows、Ubuntu及Python3.11–3.14，不等于远端CI已通过。
新本地检查不增加macOS、报告宿主身份、浏览器换人门、Creator长流程或Telegram资格，也不抹去历史失败。

**更早的构建。** 下面这些结果属于引擎摘要更早的构建（10 月 30 日那个构建的摘要是
`4b7cd1fc2269bf464b3c8ed13d36c85dbca3196ea44835bc5c373f49b86a7b2b`），没有在这一构建上重做。

| 构建 | 范围 | 环境 | 结果 |
|---|---|---|---:|
| 2026年11月4日；旧96文件引擎摘要`f1884f3ff58d61dd63a477ae9fb3d4b367895e513bbae159885f176770e24680` | SoulRun自己的源码测试 | Windows，Python3.12.9 | 701 passed，5 skipped |
| 2026年11月4日；同一旧运行头 | 引擎自己的测试 | Windows，Python3.12.9 | 7186 passed，14 skipped |
| 2026 年 10 月 30 日 | SoulRun 自己的测试，对着源码 | Windows，Python 3.12.9 | 656 passed，3 skipped |
| 2026 年 10 月 30 日 | 引擎自己的测试套件，对着那份引擎 | — | 4120 passed，12 skipped，0 failed |
| 2026 年 10 月 30 日 | SoulBot 的全部测试，装上那个构建 | Windows，Python 3.12.9，单独的测试环境 | 3325 passed，18 skipped，29 deselected，1 xfailed |
| 2026 年 10 月 30 日 | 安装包：`python tools/check_dist.py`，再 `twine check --strict`（twine 7.0.0） | — | 都通过：129 个文件，96 个引擎文件和清单一致，隐私检查通过 |
| 2026 年 10 月 30 日 | 真实模型：Claude Opus 5.5，经 SoulBot | 单独的测试环境 | 易经一卦：跑完，PASS；股票分析（MSFT，full）：跑完，DEGRADED——那个环境没有行情数据的 MCP 服务，分析改用网页搜索，数字标为未核实；一场中途停下、再说「继续」接着跑的运行：跑完，PASS |
| 2026 年 10 月 16 日 | SoulRun 测试，对着源码 | Windows，干净的虚拟环境，Python 3.11.17 | 546 passed，2 skipped |
| 2026 年 10 月 16 日 | SoulRun 测试，对着源码 | Windows，Python 3.13.5 和 3.14.6 | 各 547 passed，1 skipped |
| 2026 年 10 月 16 日 | 从源码包开始的 SoulRun 测试和全部检查 | WSL2 Ubuntu 24.04，Python 3.12.3 | 548 passed |

更早的构建也经 SoulBot 宿主（Claude Code）用真实模型跑过：易经从头跑到终答，包括同一个问题再问一次、过重复起卦门；股票分析过了
导出门；AIAP Creator 过了第一道门、五次把节点派给子代理，然后人按停止、答停止门；人按停止以后直接说「继续」和说一句需要判断的话；
另外在一个独立的 Claude Code 会话里，用最简的 SKILL.md 跑 AISP 易经技能。这些简装形式的运行里，主对话没有打开任何程序文件。在更早的
引擎上：两个候选里按人的话选，在网页上回答门，宿主重启后接回、模型断线后接回，模型流式输出的报告被引擎收下，没有用户的话时点名运行一个程序
（程序开人类主权疑惑门问人，没有自己编问题）。
