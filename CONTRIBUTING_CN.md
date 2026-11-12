# 贡献 SoulRun

感谢您有兴趣为 SoulRun 做出贡献！

> ⚠️ **当前阶段的贡献政策**
>
> 我们欢迎通过 **GitHub Issues 进行讨论**。
>
> **当前不接受外部 Pull Request。** 如果您有任何建议 — bug 报告、功能想法、新的宿主示例或改进 — 请通过 Issue 描述。如果我们认为有价值，由维护者实现并在 commit/release notes 中署名感谢您。
>
> 此政策未来会重新审视。

> **阶段状态（V1.0.1）**
>
> SoulRun 当前版本：V1.0.1，尚未发布的维护候选；带着的引擎仍为1.0.0。下方流程描述的是**目标**开发模型。初期决策由 AIXP Labs 核心维护者做出；社区讨论窗口将随贡献者基数增长而扩大。

## 如何贡献

### 报告 Issue

- 使用 [GitHub Issues](https://github.com/AIXP-Labs/SoulRun/issues) 报告 bug、提议功能或建议新示例
- 安全漏洞按 [SECURITY.md](SECURITY.md) 写的方式私下报告，不要发在公开的 issue 里
- 附 `soulrun --version` 的输出（SoulRun 和引擎的版本）、OS、宿主和模型 CLI 工具的版本
- 运行起不来时附 `soulrun --doctor --json` 的输出；贴出来之前检查里面有没有私人的目录名
- 提供最小复现步骤
- AISOP / AIAP / AISP 相关问题请引用相关的 `.aisop.json` 文件
- 不要附 `soulrun_cache_dir` 里的运行数据：里面是用户自己说的话

### 讨论驱动开发

1. 通过 issue 提出讨论
2. 维护者评估价值、可行性和公理 0 合规性
3. 讨论达成共识后，由维护者实现变更
4. 贡献者在 commit / release notes 中获得署名

### 提议新的宿主示例

提议新示例时，请在 issue 中包含：

- **使用场景** — 宿主在 SoulRun 前后做什么
- **宿主类型** — 脚本 / 框架 / 代理 / IDE / 终端会话
- **接模型的方式** — SoulACP、某个 API 客户端，或宿主接模型的其它方式
- **宿主入口** — 需要 `soulrun.host` 里的哪些（重启、断线、停止……）
- **为什么**该示例对社区广泛有用

维护者将评估并实现（如批准）。

## 贡献原则

### 引擎

**引擎不在这个仓库里手改。** 新的引擎从它的规范来源（canonical）用 `tools/upgrade_engine.py` 换进来：先核对来源的身份、版本、
许可和契约摘要，再把它的运行文件逐字节放进 `src/soulrun/soulrun_aiap/`（它的测试和发布说明不带进来）：

```bash
python tools/upgrade_engine.py --from <引擎目录> --engine-version <X.Y.Z> --dry-run   # 先看
python tools/upgrade_engine.py --from <引擎目录> --engine-version <X.Y.Z>
```

规范来源的 `--engine-version` 必须就是来源自己带的版本（不会改写版本号）；内容变了、版本却和已带的相同，会被拒绝，除非加
`--same-version`。动手之前，工具先用新引擎生成 `engine_node.aisop.json`、检查新引擎接得住 SoulRun 的每一种调用（不用模型，
指定一个程序跑一场），并且在找得到 SoulBot 的代理模板（在本仓库旁边，或用 `--agent-py` 指定）、而且它还带着这些文字时，
拿它核对固定文字；有任何问题就停下，什么都不改。然后把被换掉的引擎保存在 `.engine_backups/`（`--restore` 可以换回）、
换进新引擎、写它的清单、重建 `engine_node.aisop.json`、在 DEPENDENCIES（中英两份）和 GUIDE 写引擎版本的地方写上新版本，
最后列出还要手动做的：跑测试、构建并检查安装包、文档检查、在 CHANGELOG 记一笔、重新给 README 的测试基线标日期。

规范来源的指令和历史文字不清洗、不改版本、不重新盖章。只有显式加 `--legacy-clean` 才走旧开发树的转换
（`tools/clean_engine.py`），这个清洗器拒绝规范来源的身份。它改过的、模型或人会读到的文字都会列出来（写在
`.engine_backups/` 下的一个文件里；`--dry-run` 时直接打印）：提交之前逐条审阅。不能为了让发布检查通过而添加哈希豁免。

`tools/sync_engine.py --check-release` 核对已记录的来源形式、文件清单与总摘要、只含运行文件以及隐私。
规范来源还须通过身份/版本、许可和契约检查；legacy-clean 来源仍须通过原来的历史检查。来源未知、互相矛盾或已漂移都直接失败，
不自动降级。AIAP 符合性、生成程序和安装包检查仍须通过，见[来源分支发布检查](docs/release-1.0.0.md#来源分支发布检查)。
引擎故障在它的来源修好再换进来，不在这里打补丁。三个生成的文件也不手改：

- `src/soulrun/_agent_text.py` 是 `tools/port_agent_text.py` 生成的，这个工具从还带着这些文字的 SoulBot `agent.py` 里取。
  SoulBot 现在的代理模板把每一轮都交给 SoulRun，自己不再带这些文字：`tools/upgrade_engine.py`、
  `tools/record_soulbot_samples.py` 和测试都认得这种模板，这个模块保持最后一次从 SoulBot 自己的文字生成的样子。
- `src/soulrun/engine_node.aisop.json` 由 `tools/build_engine_node.py` 从引擎生成（`--check` 证明它是最新的）。
  `tools/upgrade_engine.py` 会重建它；新引擎多出归类里还没放的部分时，它会停下：在 `tools/build_engine_node.py` 里放好，
  重新运行这个工具，并复查它报出的归类。
- `tests/soulbot_samples.json` 记着比对里 SoulBot 那一边（各种情况下它的固定文字、它发送层读这些块的函数、它的宿主按名字载入的
  引擎模块、它的页脚、政策文档的章节和许可证），所以没有 SoulBot 的机器（比如 CI）上测试也照样比对。SoulBot 在本仓库旁边时，
  测试直接用 SoulBot 本身，样本落后于它就不过：这时运行 `python tools/record_soulbot_samples.py`。SoulBot 的代理模板是 SoulRun
  入口时，固定文字那几部分保持最后一次记下的样子，只有其余部分和 SoulBot 本身比对。

名字以 `test_engine_today_` 开头的测试，记的是引擎**现在**的行为和 SoulRun 的设计不一样的地方。引擎改了以后，这种测试会
故意不过：把设计说明和测试一起改。

### 质量标准

- 行为变更必须包含定向回归测试；共享契约和用户工作流需要扩大覆盖范围
- 只用标准库：SoulRun 没有运行时依赖，以后也不能有
- SoulRun 抛出的错误都带一个稳定的代码；知道的时候，还带是哪一项不对、应当是什么
- 代码风格：`ruff`（配置见 `pyproject.toml`）
- 新增或修改的 Python API 必须使用 Python 3.11+ 类型注解
- 行长：选用的 Ruff 规则不检查行长；跟周围的代码保持一致
- 公开函数和类必须有 docstring
- 禁止 wildcard imports
- 没有任何测试会调用模型：需要模型的地方，由测试向引擎提交模型会提交的那种内容；测试都在 pytest 的临时目录里进行，
  不往仓库里写任何东西

维护者执行的检查和 `.github/workflows/ci.yml` 里 `test` 任务相同（Ubuntu 和 Windows，Python 3.11 到 3.15）：

```bash
python -m pip install -e ".[dev]"
python -m pip check
python tools/sync_engine.py --check
python tools/sync_engine.py --check-release
python src/soulrun/soulrun_aiap/tools/aiap_conformance_check.py src/soulrun/soulrun_aiap
python tools/build_engine_node.py --check
python -m ruff check src tests tools examples
python tools/check_docs.py
python -m pytest -rs
```

SoulRun 自己代码的覆盖率（配置在 `pyproject.toml`：`src/soulrun`，不含引擎）：`python -m coverage run -m pytest`，
再 `python -m coverage report`。这样量不到 `tools/` 下的工具：配置只包含 `src/soulrun`，而且有几组工具的测试是把仓库复制到
临时目录、在另一个进程里运行工具。

安装包相关的变更还必须执行（同一个工作流的 `package` 任务在 Ubuntu 和 Windows、Python 3.12 上做这些检查）：

```bash
python -m pip install -e ".[release]"
python -m build
python tools/check_dist.py
python -m twine check --strict dist/*
python -m venv <干净环境>                                                       # 一个干净的环境
<干净环境>/bin/python -m pip install "dist/soulrun-<version>-py3-none-any.whl[dev]"   # 安装包和它的测试工具
<干净环境>/bin/soulrun --version
<干净环境>/bin/soulrun --verify-engine
SOULRUN_TEST_INSTALLED=1 <干净环境>/bin/python -m pytest -rs                    # Windows 上把 bin/ 换成 Scripts/
```

下面任何一种情况，`tools/check_dist.py` 都会报错：wheel 里带了 SoulRun 自己的文件和引擎文件以外的东西，或者带的引擎文件
不正好是清单里「随包安装」的那一批（每个都对得上记下的 SHA-256）；出现了运行时依赖；安装包里有缓存、运行数据或存放密钥的
文件；某个文件里有凭据、个人目录的路径、不在少数允许名单上的邮箱，或者压缩包头里记了用户名。构建不等于发布：上传安装包由维护者亲手做；
这个仓库里没有任何脚本或工作流会去上传。

### 隐私

这个仓库里的文件不指向任何人，也不指向某一台机器上的位置：没有用户名、没有个人目录、没有带盘符的路径、没有个人邮箱。
SoulRun 自己的文件有一项测试在查，文档由 `tools/check_docs.py` 查，安装包由 `tools/check_dist.py` 查。想让安装包检查顺带查
额外的非秘密标识、不把它们写进源码，可在运行时传进去：

```bash
SOULRUN_PRIVACY_WORDS="<词>,<词>" python tools/check_dist.py
```

命令历史和进程环境可能保留值，示例里绝不放真实令牌。ignore 不移除已跟踪文件，也不替代内容审查。
原始会话、本机服务商配置、私钥、日志和构建输出不放进公开输入；公开报告使用合成例子。

### 打包与隐私审查

在隔离 checkout 构建 wheel 和源码包，并用 `tools/check_dist.py` 核查两者成员名及文件字节。合成归档测试是实际构建的补充，
不能代替真实构建。保留合法源码和资源，不得为掩盖泄露而一概排除 JSON 或数据文件。没有版本控制元数据时，显式构建排除规则也须有效；
公开示例只使用占位符。忽略规则不能清理已跟踪文件或历史修订。疑似泄露按 [SECURITY.md](SECURITY.md) 处理：发行方撤销或轮换与删除、
隔离本机文件是不同操作。记录精确构建输入、制品摘要、失败、跳过及资格边界；构建和检查通过不等于获得发布或部署授权。

### 文档变更

- 在仓库根目录运行 `python tools/check_docs.py`。
- 命令必须与 `.github/workflows/ci.yml` 和 `pyproject.toml` 对齐。
- 同时更新受维护的中英文对照文件。
- 保持统一的页脚：README 一对以 AIXP Labs 项目表、免责声明、许可证一行和公理 0 一节结尾；政策类文档以公理 0 那一行结尾，
  并保留 SoulBot 的章节标题（SoulRun 换了说法或用不上的少数几节除外）。`python tools/check_docs.py --set-version X.Y.Z`
  一步改好包里的版本和文档里标 SoulRun 版本的那几行（页脚、上面的阶段行、GUIDE 和 INSTALL 开头）；引擎版本由
  `tools/upgrade_engine.py` 写进 DEPENDENCIES（中英两份）和 GUIDE 开头那一行。文档里别处提到的版本号要手动改。
  `tools/check_docs.py` 两种版本行都查，`tests/test_docs.py` 把页脚和政策文档的章节与 SoulBot 的比对。
- 测试数量必须标注日期，并与支持版本政策或行为保证分开表述。
- 不得发布凭据、用户数据、本机绝对路径、运行数据或含隐私内容的截图。

权威源和生成记录边界见[文档地图](docs/README.md)。

### 双语要求

对齐带日期的证据和限制，不只对齐标题。配置 CI 不等于实测结果；版本或运行摘要未变，不代表旧制品已经包含新 README。
记录受影响检查，核验新发布制品前在新目录重建。

仓库测试覆盖SDK、CLI和包装；独立Engine测试另行维护，不随已装引擎发布，记录实际跑了哪一套。
`guide.txt`也是面向调用者的文档，由无参API/CLI格式化交出，不是从`GUIDE.md`生成。
不为润色文字改动可执行契约、许可语义或冻结的治理字段。

README、CONTRIBUTING 与 DEPENDENCIES 维护中英文对照版本；SECURITY、文档地图与发布说明（`docs/release-1.0.0.md`）在同一文件中
包含两种语言；GUIDE 和 INSTALL 用中文写；GOVERNANCE、CODE_OF_CONDUCT、CHANGELOG、示例的 README（`examples/README.md`）和
`docs/guide/` 下的指南用英文写。共享事实发生变化时必须保持两个语言表面一致。
Issue 可使用任一语言。

## 行为准则

参与本项目即表示您同意遵守 [Code of Conduct](CODE_OF_CONDUCT.md)。

## 贡献的许可

提交即同意您的贡献以 [Apache License 2.0](LICENSE) 授权（无论通过 issue 或未来的 PR）。

Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev

---

Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulRun V1.0.1. www.soulrun.dev
