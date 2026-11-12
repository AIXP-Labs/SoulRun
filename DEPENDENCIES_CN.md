# SoulRun 依赖政策与已验证基线

依赖声明及部分上游元数据最近审查：2026-11-11。

`pyproject.toml` 是依赖约束的权威来源。本文清单记录：运行时的承诺（没有依赖）、开发与发布工具、引擎、引擎的文字要求机器上
有什么、CI 的固定版本，以及复现检查所需的命令。

英文版见 [DEPENDENCIES.md](DEPENDENCIES.md)。

## 1. 版本政策

- SoulRun **没有运行时依赖**。`[project].dependencies` 为空，有一项测试保证它一直为空，`tools/check_dist.py` 也会让声明了运行时
  依赖的 wheel 不通过。引擎只用 Python 标准库，兼容的 Python 解释器无需额外运行库即可运行其工具。
- 开发与发布工具是可选的额外依赖（`dev`、`release`），采用「声明的兼容下限 + 下一个破坏性大版本上界」（Ruff 还在 0.x，上界是下一个
  小版本）。声明下限不证明所有允许的组合都测过。`tzdata` 只装时区数据、按日期编版本号，只设下限。
- 所有版本范围只写在 `pyproject.toml`，Dependabot 只在这一处更新 Python 依赖的版本范围（它还会更新工作流里 Actions 的固定版本，
  见第 6 节）。CI 经 `tools/extra_requirements.py` 从这里装发布工具；测试工具作为 `dev` 额外依赖装：测试任务装源码树的，package
  任务装构建出来的 wheel 的。工作流和 INSTALL.md、贡献指南、本文档里的安装命令都不自己写版本范围，有一项测试在查。
- 引擎按内容固定，而不是按包版本：`src/soulrun/engine_manifest.json` 记着它的版本和每个文件的 SHA-256。
- GitHub Actions 固定到不可变的 commit SHA，注释里保留发布标签便于审计。已独立核对上游标签与提交；别的项目 CI 不能证明 SoulRun 合格。
- 依赖表记录的是声明的兼容下限，不是锁文件。需要确切证据时，用 `python -m pip list --format=freeze` 记录具体环境。

## 2. 运行矩阵

| 范围 | 支持区间 | 本机实际核验过的版本 |
|---|---|---|
| SoulRun 的 Python | `requires-python = ">=3.11"` 声明最低版本，不是上界 | 11月11日本地SDK源码检查：Windows3.12.9，Ubuntu3.11.18/3.12.3/3.13.18/3.14.10/3.15.2；准确头与继承见下文，更早证据单独保留 |
| CI 矩阵 | 测试：Ubuntu 和 Windows × 3.11、3.12、3.13、3.14、3.15；构建安装包并对装好的 wheel 跑测试：Ubuntu 和 Windows × 3.12 | [`.github/workflows/ci.yml`](.github/workflows/ci.yml)配置12项；新增两项3.15作业尚待远端执行。前一版10项结果按日期记在[验证范围](docs/verification-1.0.0.md) |
| 模型的命令行找到的 `python`（入口路径形式下的每个引擎工具；不管哪种形式，子代理的引擎工具和程序自己写成 `python ...` 的工具） | 兼容的 Python；满足 SoulRun 声明的最低版本及业务程序额外要求 | 由 `soulrun --doctor` 报出；找不到时，不管哪种形式都报 `FAIL`；找到解释器不等于业务程序已合格 |

11月11日对摘要`9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`，
Ubuntu SDK3.11.18/3.12.3/3.13.18/3.14.10/3.15.2分别独立实跑，每组911通过/4跳过/总915；
Windows3.12.9为912通过/3跳过/总915。Windows3.11–3.15 SDK和冷安装按准确不变正文继承。
这些Python3.15本地结果不是远端CI证据或支持政策变更，macOS仍未测。
准确Engine计数、QA守卫组合与后续发行工具修订见[验证范围](docs/verification-1.0.0.md)，不表示后来的每次源码改动都新测通过。
引擎Markdown与独立调用说明也是随包输入。同版本文档修订不能自动继承旧安装包、模型运行或其他平台的资格。

## 3. SoulRun 的 Python 依赖

### 运行时

没有。安装 SoulRun 只装 SoulRun 和它清单里列出的引擎文件，别的都不装。

### 开发与发布

| 额外依赖组 | 包 | 约束 | 已记录工具版本（2026-11-11 审查） |
|---|---|---|---|
| `dev` | coverage[toml] | `>=7.15.2,<8` | 7.17.2（Windows QA） |
| `dev` | mypy | `>=1.19.1,<2` | 1.20.2（Windows QA） |
| `dev` | pytest | `>=9.1.1,<10` | 9.2.0（Windows QA） |
| `dev` | pytest-timeout | `>=2.4.0,<3` | 2.4.0 |
| `dev` | ruff | `>=0.16.0,<0.17` | 0.16.10 |
| `dev` | tzdata | `>=2024.1` | 2026.6（Windows QA） |
| `release` | build | `>=1.5.0,<2` | 1.5.0（上一冻结制品的构建环境） |
| `release` | twine | `>=7.0.0,<8` | 7.0.0（隔离严格核验环境） |

- **tzdata** 在系统没有时区数据时（Windows）给 `zoneinfo` 提供数据，让开发环境像运行时一样读得到具名时区。没有一项测试需要它：
  没有它时引擎退回本机时区，`soulrun --doctor` 会提醒。
- **twine 7.0.0** 严格检查了上一冻结 wheel 和源码包，不是后来文档修订的新制品。
- 构建后端是 `hatchling>=1.31.0,<2`；已记录构建环境用的是 1.32.4。
- 上表来自不同环境，不是一份实测锁。2026-10-14 的干净 Python 3.11.17 环境曾解析到 coverage 7.16.2、pytest 9.1.1、
  pytest-timeout 2.4.0、Ruff 0.16.10、tzdata 2026.5、build 1.6.1、Twine 7.0.0；mypy 1.19.1 在另一 Python 3.12 环境。
  历史观察保留，不表示本轮重验。

安装并核验完整的开发环境：

```bash
python -m pip install -e ".[dev,release]"
python -m pip check
```

## 4. 引擎

| 项 | 值 |
|---|---|
| 引擎 | SoulRun 引擎 `1.0.0`（`soulrun.ENGINE_VERSION`） |
| 位置 | `src/soulrun/soulrun_aiap/`：只有运行要用的文件，全部随包安装 |
| 记录 | `src/soulrun/engine_manifest.json`：版本、来源形式（`canonical` 或 `legacy-clean`）、每个文件的 SHA-256 和整份列表的总摘要 |
| 指纹 | `soulrun --engine-info`：清单记下的 `installed_digest`，和从文件本身算出来的 `installed_digest_now` |
| 引擎的运行时依赖 | 没有（只用标准库） |
| 检查 | `tools/sync_engine.py --check`（文件和清单一致）、`tools/sync_engine.py --check-release`（只读的发布检查：来源形式、运行文件和摘要一个不差、版本、隐私）、引擎自带的 AIAP 合规检查（引擎里的 `tools/aiap_conformance_check.py`） |

`soulrun --verify-engine` 核对装好的副本。新引擎只用 `tools/upgrade_engine.py` 换进来：canonical 引擎先核对身份、版本、许可和契约，
再逐字节拷进来；旧的开发目录只有显式加 `--legacy-clean` 时才经过清理工具（`tools/clean_engine.py`），它的历史检查照样严格。被换掉的
那份留在 `.engine_backups/`（从不打进安装包），`--restore` 可以把留着的一份换回来。

## 5. 引擎的文字要求机器上有什么

这些不是 SoulRun 的 Python 依赖，但一场运行需要它们：

| 需要 | 为什么 | 检查 |
|---|---|---|
| 模型的 `PATH` 上有 `python` | 入口路径形式下模型用它运行每个引擎工具；不管哪种形式，子代理用它运行引擎的工具，程序自己写成 `python ...` 的工具也用它；只有简装形式（默认）的主对话改为按完整路径写出运行 SoulRun 的解释器 | `soulrun --doctor`（`python for the model`、`program form`；找不到 `python` 时，不管哪种形式都报 `FAIL`） |
| Windows 上，运行 SoulRun 的 Python 和模型用的 `python` 都有时区数据 | 引擎要读服务商点名的额度恢复时区 | `soulrun --doctor`（`time zones`） |
| Windows 上打开长路径，或者 `soulrun_cache_dir` 放得浅 | 一场运行的文件会嵌到约 130–150 个字符深（看程序节点名长短） | `soulrun --doctor`（`path length`） |
| 能接模型的宿主 | SoulRun 从不调用模型 | — |

## 6. GitHub Actions

| Action | 发布版本 | 不可变 SHA |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-python | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |

Dependabot 每周检查 Python 额外依赖和 GitHub Actions。更新仍须跑完整的 CI 矩阵；自动提议不等于兼容性证明。Dependabot 不碰
引擎。

2026-11-11 只读核查确认两份 pin 与上游标签一致。向 [OSV 批量 API](https://google.github.io/osv.dev/post-v1-querybatch/)
查询了 15 组指定直接工具/版本，未返回漏洞编号。这不是完整的传递依赖环境审计、不保证没有漏洞，也不证明所有允许的未来版本可用。
本轮没有为了更新日期而改动约束。

## 7. 必须执行的核验

和 CI（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)）的步骤相同：

```bash
# Python —— CI 的测试任务（Ubuntu 和 Windows，Python 3.11 到 3.15）
python -m pip install -e ".[dev]"
python -m pip check
python tools/sync_engine.py --check
python tools/sync_engine.py --check-release
python src/soulrun/soulrun_aiap/tools/aiap_conformance_check.py src/soulrun/soulrun_aiap
python tools/build_engine_node.py --check
python -m ruff check src tests tools examples
python tools/check_docs.py
python -m pytest -rs

# 安装包 —— CI 的 package 任务（Ubuntu 和 Windows，Python 3.12），在还没有 dist/ 的检出目录里
python -m pip install -e ".[release]"     # CI 经 tools/extra_requirements.py 装同一组额外依赖
python -m build
python tools/check_dist.py                # 检查 dist/ 里每个 soulrun-* 文件
python -m twine check --strict dist/*
python -m venv <干净环境>
<干净环境>/bin/python -m pip install "dist/soulrun-<version>-py3-none-any.whl[dev]"
<干净环境>/bin/soulrun --version
<干净环境>/bin/soulrun --verify-engine
SOULRUN_TEST_INSTALLED=1 <干净环境>/bin/python -m pytest -rs
```

Windows 上把 `bin/` 换成 `Scripts\`。正式发布时构建到一个新的空目录，按名字检查那两个文件（`twine check --strict`），记下它们的
大小和 SHA-256，只上传这两个文件，不用通配符：见 [INSTALL.md](INSTALL.md) 第七至九节。上传到 TestPyPI 和 PyPI 由维护者亲手做。

## 8. 升级检查清单

1. 对照权威的包注册表和上游发布页核实直接依赖的版本。
2. 在 `pyproject.toml` 里更新约束；绝不增加运行时依赖。
3. 每次大版本升级都要读破坏性变更说明。
4. 跑 Windows 和 Linux 的测试、所有支持的 Python 版本、文档校验，以及安装包冒烟测试（对着装好的 wheel 跑测试）。
5. 换新引擎：先 `python tools/upgrade_engine.py --from <引擎目录> --engine-version X.Y.Z --dry-run`，再升级，再跑 SoulRun 的测试和安装包构建；在
   [CHANGELOG.md](CHANGELOG.md) 里记下引擎的变化，并给 README 的已验证测试基线换上新日期。
6. 在同一变更中更新本文档和 `DEPENDENCIES.md`。
