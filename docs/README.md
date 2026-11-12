# SoulRun Documentation Map

This directory indexes the repository documentation and defines which file is
authoritative when several documents describe the same behavior.

## Reader map

| Need | Authoritative document |
|---|---|
| What SoulRun is, how to call it, every argument, known limits | [`README.md`](../README.md) and [`README_CN.md`](../README_CN.md) |
| Install, build, package, or publish (in Chinese) | [`INSTALL.md`](../INSTALL.md) |
| Use SoulRun in depth (in Chinese): parameters, `Ctx`, doubts, error codes, host doors, `--doctor` | [`GUIDE.md`](../GUIDE.md) |
| Dependency versions, Python matrix, the engine, upgrade policy | [`DEPENDENCIES.md`](../DEPENDENCIES.md) and [`DEPENDENCIES_CN.md`](../DEPENDENCIES_CN.md) |
| Security and deployment boundaries (English and Chinese) | [`SECURITY.md`](../SECURITY.md) |
| Contribute, report a problem, or bring a newer engine in | [`CONTRIBUTING.md`](../CONTRIBUTING.md) and [`CONTRIBUTING_CN.md`](../CONTRIBUTING_CN.md) |
| Governance, versioning, and Axiom 0 | [`GOVERNANCE.md`](../GOVERNANCE.md) and [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) |
| Why SoulRun is built the way it is | [`guide/01-design.md`](guide/01-design.md) |
| SoulBot on SoulRun: how its agents and host are wired, and the rules a host keeps | [`guide/02-soulbot-integration.md`](guide/02-soulbot-integration.md) |
| Host examples | [`examples/README.md`](../examples/README.md) |
| Release history | [`CHANGELOG.md`](../CHANGELOG.md) |
| Unreleased 1.0.1: recorded local tests, skips, inheritance and untested scope | [English](../README.md#soulrun-101-local-qualification) and [中文](../README_CN.md#soulrun-101-本地验收范围) |
| V1.0.0 release notes: the engine it carries, the results verified for it, and what it does not claim | [`release-1.0.0.md`](release-1.0.0.md) |
| Dated runtime/artifact evidence, skip accounting, inherited cases and untested paths (English and Chinese) | [`verification-1.0.0.md`](verification-1.0.0.md) |
| What a model session reads | `soulrun()` or the `soulrun` command with no arguments: the guide shipped inside the package |

## Sources of truth

Documentation summarizes executable contracts; it does not replace them.

| Contract | Source of truth |
|---|---|
| Package version | `src/soulrun/__init__.py` |
| Python dependencies, extras, and supported Python range | `pyproject.toml` |
| CI matrices and commands | `.github/workflows/ci.yml` |
| The engine: version and file fingerprints | `src/soulrun/engine_manifest.json` |
| The one call, its arguments, `Ctx`, and doubts | `src/soulrun/_api.py` |
| Folders and candidates | `src/soulrun/_select.py` |
| Engine commands (`cmd=`, `--cmd`) | `src/soulrun/_cmd.py` |
| Host doors | `src/soulrun/host.py` |
| Error classes (`SoulRunError`, `UsageError`, `EngineUnavailable`) | `src/soulrun/errors.py` |
| SoulRun's own records beside the runs (`.soulrun/`) | `src/soulrun/_records.py` |
| Command-line options | `src/soulrun/cli.py` (`soulrun --help`) |
| Machine checks | `src/soulrun/_doctor.py` |
| The guide handed to callers and model sessions | `src/soulrun/guide.txt` |
| The fixed text the model reads | `src/soulrun/_agent_text.py` (the entry-path form's wording - the interruption notes, the entry block, the assertions and the opening instruction - lifted from SoulBot's agent template by `tools/port_agent_text.py`); `src/soulrun/_blocks.py` (the context block, re-implemented line for line from that template's code, and the slim form's own entry block, assertion and opening instruction); the lines after engine replies in `src/soulrun/_slim.py` and `src/soulrun/_screen.py` |
| The slim engine program | `src/soulrun/engine_node.aisop.json` (generated from the engine) |
| The business program handed to the model (`soulrun --program`) | `src/soulrun/_program.py` |
| The complete execution report for hosts (`soulrun --report`) | `src/soulrun/_report.py` |
| What the wheel and the source archive may hold | `tools/check_dist.py` |
| The privacy rules the documentation and package checks share | `tools/privacy_rules.py` |

When prose conflicts with code or configuration, verify the executable contract and correct the prose.
Change runtime behavior only for an independently confirmed and authorized defect, not to satisfy a sentence.
Contract changes need their own review; add regression coverage for executable fixes.

## Copies and generated records

- `src/soulrun/soulrun_aiap/` is SoulRun's engine, brought in only through `tools/upgrade_engine.py`: a canonical
  source is kept byte for byte; only an explicitly selected legacy source passes through `tools/clean_engine.py`.
  The source-aware release check is `tools/sync_engine.py --check-release`; it is not a waiver of the legacy history
  check. The engine is never edited by hand. Its own Markdown (`AIAP.md`, `README.md`) belongs to the engine and is
  outside the documentation gate.
  That exclusion preserves canonical bytes; it does not exempt shipped text from privacy review.
- `src/soulrun/guide.txt` is the standalone guide shipped to callers, not generated from `GUIDE.md`.
  Editing the maintainer guide does not silently update the installed guide.
  Its formatting placeholders and actual no-argument CLI/SDK output must be tested; summaries must match
  current publication/authority rules. A documentation-only review does not authorize changing those rules.
- `src/soulrun/_agent_text.py` was generated from SoulBot's agent template by `tools/port_agent_text.py` and is not
  edited by hand. SoulBot's template now hands every turn to SoulRun and no longer carries that wording, so the
  module stays as last generated and SoulRun is where that wording lives; `tools/record_soulbot_samples.py` keeps
  SoulBot's side of the comparisons in `tests/soulbot_samples.json`.
- `src/soulrun/engine_node.aisop.json` is generated from the engine by `tools/build_engine_node.py`. Change the
  source or the generator, then regenerate; never hand-edit the output.
- SoulRun's version in the documents' version lines (the footers, the contribution guides' stage lines, the opening
  lines of GUIDE and INSTALL) is set together with the package version by
  `python tools/check_docs.py --set-version X.Y.Z`. The engine's version in the documents' engine-version lines
  (DEPENDENCIES in both languages, the opening line of GUIDE) is written by `tools/upgrade_engine.py` and checked
  against the engine manifest. Other mentions of a version, such as those in the release notes and the CHANGELOG,
  are changed by hand.
- Run data (`.soulrun_cache/`, `.execution_cache/`, `.soulrun/`), kept engines
  (`.engine_backups/`) and build output (`dist/`, `build/`) are not public documentation
  and must not be committed. Ignore patterns are not proof that this policy was obeyed.

## Documentation gate

Run from the repository root:

```bash
python tools/check_docs.py
python -m pytest tests/test_docs.py
```

`check_docs.py` scans SoulRun's own Markdown (everything outside the
engine, run data, kept engines, and build output). It validates UTF-8, relative
files, Markdown fragments, balanced fenced blocks, fenced Python syntax,
machine-specific absolute paths, high-risk credential shapes and e-mail addresses other than SoulRun's own and the
example placeholder. Syntax validation does not execute examples, and the gate does not claim that an
external website is available. Run without arguments, it also checks the versions (the version lines above name the
current SoulRun and engine versions; no document names an old development version or the engine's old name) and
the shared footers: the README pair ends with the AIXP Labs project table, the disclaimer, the license line, and the
Axiom 0 block identical to the ecosystem's; the policy documents end with the Axiom 0 line; every footer names the
current package version; no other document carries the Axiom 0 footer line. `tests/test_docs.py`
runs the gate and compares the footers, the policy documents' sections and the license with SoulBot's (with SoulBot
beside this repository, else as recorded in `tests/soulbot_samples.json`).

Before merging documentation changes:

1. Update every maintained English/Chinese pair in the same change.
2. Verify commands against the current CI workflow and `pyproject.toml`.
3. Keep measured test counts dated and separate from guaranteed behavior.
4. Review examples for secrets, personal paths, run data, destructive commands,
   and permissions that exceed the stated trust boundary.
5. Regenerate generated files from their source instead of hand-editing them.
6. Distinguish the current checkout, user-installed CLI/SDK, the host's imported package and release artifacts.
   Record their actual identities instead of assuming that editing a source file updated all four.

---

# SoulRun 文档地图

本目录索引仓库文档，并规定多个文件描述同一行为时应以哪个文件为权威。

## 阅读入口

| 需求 | 权威文档 |
|---|---|
| SoulRun 是什么、怎么调用、每个参数、已知限制 | [`README.md`](../README.md) 与 [`README_CN.md`](../README_CN.md) |
| 安装、构建、打包或发布（中文） | [`INSTALL.md`](../INSTALL.md) |
| 深入使用（中文）：参数、`Ctx`、疑惑、错误代码、宿主入口、`--doctor` | [`GUIDE.md`](../GUIDE.md) |
| 依赖版本、Python 矩阵、引擎、升级策略 | [`DEPENDENCIES.md`](../DEPENDENCIES.md) 与 [`DEPENDENCIES_CN.md`](../DEPENDENCIES_CN.md) |
| 安全与部署边界（中英） | [`SECURITY.md`](../SECURITY.md) |
| 贡献、报告问题、换进新引擎 | [`CONTRIBUTING.md`](../CONTRIBUTING.md) 与 [`CONTRIBUTING_CN.md`](../CONTRIBUTING_CN.md) |
| 治理、版本号与公理 0 | [`GOVERNANCE.md`](../GOVERNANCE.md) 与 [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) |
| SoulRun 为什么这样做 | [`guide/01-design.md`](guide/01-design.md) |
| SoulBot 接 SoulRun：代理和宿主怎样接、宿主要守的规矩 | [`guide/02-soulbot-integration.md`](guide/02-soulbot-integration.md) |
| 宿主示例 | [`examples/README.md`](../examples/README.md) |
| 发布历史 | [`CHANGELOG.md`](../CHANGELOG.md) |
| 未发布1.0.1：已记录的本地测试、跳过、继承与未验范围 | [English](../README.md#soulrun-101-local-qualification)与[中文](../README_CN.md#soulrun-101-本地验收范围) |
| V1.0.0 发布说明：带着的引擎、为它验证过的结果、它不声称的东西 | [`release-1.0.0.md`](release-1.0.0.md) |
| 带日期的运行头/制品证据、skip核算、继承用例和未验路径（中英） | [`verification-1.0.0.md`](verification-1.0.0.md) |
| 模型会话读的东西 | `soulrun()` 或不带参数的 `soulrun` 命令：包里自带的使用说明 |

## 权威源

文档用于解释可执行契约，不能替代契约本身。

| 契约 | 权威源 |
|---|---|
| 包版本 | `src/soulrun/__init__.py` |
| Python 依赖、extra 与 Python 支持区间 | `pyproject.toml` |
| CI 矩阵与命令 | `.github/workflows/ci.yml` |
| 引擎：版本和文件指纹 | `src/soulrun/engine_manifest.json` |
| 那一个调用、它的参数、`Ctx` 与疑惑 | `src/soulrun/_api.py` |
| 目录与候选 | `src/soulrun/_select.py` |
| 引擎命令（`cmd=`、`--cmd`） | `src/soulrun/_cmd.py` |
| 宿主入口 | `src/soulrun/host.py` |
| 错误类（`SoulRunError`、`UsageError`、`EngineUnavailable`） | `src/soulrun/errors.py` |
| SoulRun 在运行旁边记的东西（`.soulrun/`） | `src/soulrun/_records.py` |
| 命令行选项 | `src/soulrun/cli.py`（`soulrun --help`） |
| 机器自检 | `src/soulrun/_doctor.py` |
| 交给调用方和模型会话的使用说明 | `src/soulrun/guide.txt` |
| 模型读到的固定文字 | `src/soulrun/_agent_text.py`（入口路径形式的文字——中断提醒段、入口段、断言段和开场指令——由 `tools/port_agent_text.py` 取自 SoulBot 的代理模板）；`src/soulrun/_blocks.py`（上下文段，照那个模板的代码逐行重写；以及简装形式自己的入口段、断言段和开场指令）；引擎回复后附的那几行在 `src/soulrun/_slim.py`、`src/soulrun/_screen.py` |
| 简装引擎程序 | `src/soulrun/engine_node.aisop.json`（从引擎生成） |
| 交给模型的业务程序（`soulrun --program`） | `src/soulrun/_program.py` |
| 给宿主的完整执行报告（`soulrun --report`） | `src/soulrun/_report.py` |
| wheel 和源码包里允许有什么 | `tools/check_dist.py` |
| 文档检查和安装包检查共用的隐私规则 | `tools/privacy_rules.py` |

文档与代码或配置冲突时，先核实可执行契约、改准文档。只有独立确认且获授权的缺陷才改运行行为，不为了迎合一句话改代码。
契约变化单独审定，可执行修复补回归覆盖。

## 副本与生成记录

- `src/soulrun/soulrun_aiap/` 是 SoulRun 的引擎，只经 `tools/upgrade_engine.py` 换进来：canonical 来源逐字节保留，只有显式选中的
  legacy 来源经 `tools/clean_engine.py` 清洗；按来源分支的发布检查是 `tools/sync_engine.py --check-release`，它不豁免 legacy
  历史检查。引擎从不手改；它自带的 Markdown（`AIAP.md`、`README.md`）属于引擎，不在文档门禁范围内。
  这为了保留规范字节，不豁免随包文字的隐私审查。
- `src/soulrun/guide.txt` 是随包交给调用者的独立使用说明，不是从 `GUIDE.md` 生成。改维护指南不会悄悄更新已装说明。
  它的格式占位符、无参CLI/SDK实际输出也要测试；摘要应符合当前送达/授权规则，文档审查不授权改变那些规则。
- `src/soulrun/_agent_text.py` 当初由 `tools/port_agent_text.py` 从 SoulBot 的代理模板生成，不手改。SoulBot 的模板现在把每一轮
  交给 SoulRun、自己不再带这些文字，所以这个模块保持最后一次生成的样子，这些文字以 SoulRun 这一份为准；SoulBot 那一边用来比对的内容由
  `tools/record_soulbot_samples.py` 记在 `tests/soulbot_samples.json`。
- `src/soulrun/engine_node.aisop.json` 由 `tools/build_engine_node.py` 从引擎生成。改源头或生成器，再重新生成；不手改生成物。
- 文档里标 SoulRun 版本的那几行（页脚、贡献指南的阶段行、GUIDE 和 INSTALL 的开头一行）和包版本一起由
  `python tools/check_docs.py --set-version X.Y.Z` 改；文档里标引擎版本的那几行（中英两份 DEPENDENCIES、GUIDE 的开头一行）由
  `tools/upgrade_engine.py` 写入，并对照引擎清单检查。别处提到的版本（比如发布说明和 CHANGELOG 里的）手工改。
- 运行数据（`.soulrun_cache/`、`.execution_cache/`、`.soulrun/`）、保留的旧引擎（`.engine_backups/`）和构建输出（`dist/`、`build/`）
  不是公开文档，必须不提交；ignore规则存在不证明该政策已被遵守。

## 文档门禁

在仓库根目录运行：

```bash
python tools/check_docs.py
python -m pytest tests/test_docs.py
```

`check_docs.py` 扫描 SoulRun 自己的 Markdown（引擎、运行数据、保留的旧引擎和构建输出之外的全部），检查 UTF-8、相对文件、
Markdown 锚点、代码围栏闭合、Python 围栏语法、本机绝对路径、高风险凭据形态及 SoulRun 自己的地址和示例占位地址以外的电子邮件地址。
语法检查不会执行示例；门禁也不会声称外部网站持续可用。不带参数运行时还查版本号（上面说的那几行标的是当前的 SoulRun 版本和引擎版本；
不出现旧的开发版本号和引擎的旧名字）和统一的页脚：README 一对以 AIXP Labs 项目表、免责声明、许可证一行和与生态一致的公理 0 一节结尾；
政策类文档以公理 0 那一行结尾；每个页脚写的都是当前的包版本；其它文档不带公理 0 那一行页脚。`tests/test_docs.py` 运行这道门禁，并把页脚、政策类文档的章节和许可证
与 SoulBot 的比对（SoulBot 就在本仓库旁边时比它本身，否则比 `tests/soulbot_samples.json` 里的记录）。

合并文档变更前：

1. 在同一变更中更新所有受维护的中英文对照文件。
2. 对照当前 CI workflow 与 `pyproject.toml` 核验命令。
3. 测试数量必须标注核验日期，并与行为保证分开表述。
4. 检查示例中的凭据、个人路径、运行数据、破坏性命令及超出声明范围的权限。
5. 从源头重新生成生成物，不手工修补。
6. 区分当前源码、用户安装的CLI/SDK、宿主实际导入的包和发布制品；记录真实身份，不假定改一处便四处都更新。
