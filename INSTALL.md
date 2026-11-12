# SoulRun 安装、构建与发布指南

本文档覆盖安装、从源码开发、构建安装包、产物验证以及 PyPI 发布。依赖版本与升级策略见 [DEPENDENCIES_CN.md](DEPENDENCIES_CN.md) 与
[DEPENDENCIES.md](DEPENDENCIES.md)。

> **本指南对应 SoulRun V1.0.0。** 用 SoulRun 的人从 PyPI 或 GitHub 安装（第二节）；要改 SoulRun 本身、构建或发布的人，从本仓库的
> 源码安装（第三节起）。

---

## 一、环境要求

### 1.1 Python

- Python 3.11 或更高版本（`requires-python = ">=3.11"`）
- CI配置3.11、3.12、3.13、3.14、3.15（Windows和Ubuntu），不是`requires-python`的上界或全组合通过证明；新增3.15作业尚待远端执行。
  不同源码摘要、文档修订与已安装包不能只凭同一版本号继承资格；实际环境和日期见[验证范围](docs/verification-1.0.0.md)及
  [依赖运行矩阵](DEPENDENCIES_CN.md#2-运行矩阵)。
- 推荐在虚拟环境中安装

```bash
python --version
python -m venv .venv
```

### 1.2 模型用的 python

简装形式（默认）下，主对话里交给模型的引擎命令按完整路径写出运行 SoulRun 的那个解释器，不靠模型的命令行自己找 `python`。
下面这些用的是**模型的命令行在 `PATH` 上找到的 `python`**，不一定是运行 SoulRun 的那个解释器：入口路径形式下的每个引擎工具；
不管哪种形式，子代理的引擎工具（引擎给子代理的程序写的是 `python <引擎目录>/python_tools/...`）；不管哪种形式，程序自己写成
`python ...` 的工具（程序自己的工具照程序里写的命令运行）。引擎只用标准库，但解释器仍须兼容：采用满足SoulRun最低版本的Python，
并核对业务程序额外要求。装好以后用
`soulrun --doctor` 看它报的 `program form` 和 `python for the model`（找不到 `python` 时，不管哪种形式都报 `FAIL`）。

### 1.3 Windows 上的时区数据

Windows 自己没有时区数据：python.org 的 Python（和用它建的虚拟环境）要装 `tzdata`。`soulrun --doctor` 的 `time zones` 分别查运行
SoulRun 的 Python 和模型用的 `python`，哪个缺就在哪个里装：

```bash
python -m pip install tzdata
```

没装时引擎不会出错，但会把服务商点名时区的额度恢复时间按本机时区算，并在运行里记一笔（`SUPPLY_RESET_ZONE_UNREADABLE`）。SoulRun 本身不依赖它；开发用的 `.[dev]` 带着它。

### 1.4 Windows 上的路径长度

一场运行会在 `soulrun_cache_dir` 里建到约 130–150 个字符深，看程序的节点名有多长。Windows 没打开长路径支持时，一个路径最多 259 个
字符，放运行的目录最好不超过约 100 个字符。`soulrun --doctor` 的 `path length` 会按找到的程序算出一场运行最深的文件路径有多长；
太长、又没打开长路径支持时报 `WARN`，并说出这个目录最多能有多少个字符。

---

## 二、安装、升级与卸载

下面的平台注册安装命令描述发布后的用法，不是当前已发布的证明。首次发布准备固定V1.0.0；本地候选须使用已核验wheel或获准源码，
核对实际解释器、包来源与摘要。不要因官方源没有对应文件就自动改用来历不明的包源。

两种方式任选：

```bash
python -m pip install soulrun                                          # 从 PyPI
python -m pip install "git+https://github.com/AIXP-Labs/SoulRun.git"   # 或者直接从 GitHub（main 上的最新提交）
```

装好以后核对：

```bash
soulrun --version                     # SoulRun 的版本号和带着的引擎的版本号
soulrun --verify-engine               # 每个引擎文件和清单里记下的 SHA-256 一致
soulrun --doctor --agent-dir <代理目录>  # 运行需要的东西都齐了吗？不留下任何东西
python -m soulrun --version           # 不经过命令入口，也能这样运行
```

`--doctor` 查的是一个代理目录（放 `aiap/`、`aisp/` 的那个）：在代理目录里运行，或者设了环境变量 `SOULRUN_AGENT_DIR`，可以不写
`--agent-dir`。每一项报 `OK`、`WARN` 或 `FAIL`；有 `FAIL` 时退出码是 1，只有 `WARN` 时是 0。

升级：

```bash
python -m pip install --upgrade soulrun
```

每场运行记着开它的引擎构建（引擎文件的总摘要）。换了引擎以后，别的构建开的、还没跑完的运行（还在进行或在等人回答；没有记录是
哪个构建开的也一样）不会由新的引擎接着执行，即使版本号相同：那一场结束之前，这个对话里每一条人的消息都不交给引擎，而是问人怎么办——
在另一个对话里发新的请求，或者先不处理。引擎版本号相同时，还可以回复「取消」在这里结束那一场；要接着跑它，或者版本号不同时要结束
它，都得回到开它的那个环境。不是人发的轮次直接报 `ENGINE_BUILD_MISMATCH`。

卸载：

```bash
python -m pip uninstall soulrun
```

卸载只删包本身。**运行数据不在包里**：各代理目录下的 `.soulrun_cache`（或你指定的 `soulrun_cache_dir`）原样留着，要删请手动删；
删掉它就删掉了其中所有运行，包括没跑完的。

---

## 三、从源码安装（开发）

在仓库根目录：

```bash
python -m pip install -e .                    # 可编辑安装，只装 SoulRun（没有任何依赖）
python -m pip install -e ".[dev]"             # 加上测试工具：pytest、pytest-timeout、ruff、coverage、mypy、tzdata
python -m pip install -e ".[dev,release]"     # 再加上构建与发布工具：build、twine
python -m pip install .                       # 从源码装进当前环境（非可编辑）
```

核对方法同第二节。在仓库根目录直接运行 `soulrun --doctor` 时，`programs` 会报 `FAIL`——仓库本身不是代理目录，这是预期的；用
`--agent-dir` 指向一个代理目录再查。

### 3.1 PowerShell与解释器选择

本指南标为`bash`的环境变量前缀、`< 文件`重定向不是PowerShell语法。PowerShell中引用带空格的可执行文件路径时，在引号前加`&`；
优先使用消息文件，避免终端输入管道改变原始换行。命令里的相对路径按当前目录解析。

```powershell
& ".\.venv\Scripts\python.exe" -m pip check
& ".\.venv\Scripts\python.exe" -m soulrun --version
& ".\.venv\Scripts\python.exe" -m soulrun --verify-engine
& ".\.venv\Scripts\python.exe" -m soulrun --user-message-file .\msg.txt --json
```

前三条不调用模型；最后一条会准备本地运行，须在隔离代理目录按实际需要执行，不是发布门自动执行的一步。
SoulRun CLI/SDK、模型CLI内部工具和生产宿主可能使用不同解释器；不要因当前终端能导入就声称生产已更新。

---

## 四、uvx 与 pipx

只想用 `soulrun` 命令、不想装进当前环境时，可以用 pipx 或 uvx 安装或临时运行：

```bash
pipx install soulrun                                       # 从 PyPI
uvx --from soulrun soulrun --doctor --agent-dir <代理目录>   # 临时运行
pipx install .                                             # 从源码目录
uvx --from . soulrun --doctor --agent-dir <代理目录>
```

> 这几条不在 SoulRun 的测试和 CI 里；SoulRun 没有依赖，按 pipx 和 uvx 的常规用法应当可行。实际用到时请先核对。

---

## 五、打包配置与发行边界

构建后端是 `hatchling`（与 SoulBot 相同），配置在 `pyproject.toml`。

| 产物 | 带什么 | 不带什么 |
|---|---|---|
| wheel | `src/soulrun` 整个包：SoulRun 的代码、`guide.txt`、`py.typed`、`engine_manifest.json`、`engine_node.aisop.json`、引擎的程序和工具 | 引擎自己的测试（`soulrun_aiap/tests`）、发布说明（`RELEASE*`）、测试配置（`pytest.ini`），以及 `__pycache__`、`.pytest_cache`、`.execution_cache` |
| sdist | `src`、`tests`、`tools`、`examples`、`docs`、`.github`，顶层的 README、CHANGELOG、贡献、安全、治理、行为准则、依赖、指南、安装、LICENSE、NOTICE、`.gitattributes`，以及构建工具自己加的 `pyproject.toml`、`PKG-INFO`、`.gitignore` | 运行数据、`.engine_backups/`、缓存、构建输出 |

- **没有运行时依赖**：`[project].dependencies` 为空，有测试保证；`tools/check_dist.py` 也查 wheel 的元数据。
- **装进去的引擎文件就是清单里记的那一批**：`tools/check_dist.py` 逐个核对，多一个、少一个或内容不同都报错。
- **版本号**来自 `src/soulrun/__init__.py`，用 `python tools/check_docs.py --set-version X.Y.Z` 改：包里的版本号，和文档页脚、
  贡献指南的阶段行、指南开头写的 SoulRun 版本号一起改。引擎有自己的版本号，写在引擎自己的文件里；换引擎时
  `tools/upgrade_engine.py --engine-version` 给出新引擎的版本：canonical 来源只核对它就是这个版本、不改写；显式用 `--legacy-clean`
  时，由清理工具把这个版本写进换进来的引擎。两种情况下都把文档里写引擎版本号的地方（DEPENDENCIES 中英、GUIDE）改成新的。
- **README.md** 是 PyPI 页面的长说明：构建时 `tools/pypi_readme.py` 把其中的相对链接改成指向 GitHub 仓库的完整地址，README.md
  本身不变。

---

## 六、发布前门禁

在仓库根目录，按顺序全部通过：

```bash
python -m pip install -e ".[dev,release]"
python -m pip check
python tools/sync_engine.py --check
python tools/sync_engine.py --check-release
python src/soulrun/soulrun_aiap/tools/aiap_conformance_check.py src/soulrun/soulrun_aiap
python tools/build_engine_node.py --check
python -m ruff check src tests tools examples
python tools/check_docs.py
python -m pytest -rs
```

还要：

- `tools/sync_engine.py --check-release` 只读、不改任何文件：先核对清单记的来源形式（`canonical` 或 `legacy-clean`）、文件清单、
  逐个文件和总摘要、引擎版本、只含运行要用的文件、没有符号链接，以及隐私；再按来源形式查：`canonical` 核对引擎的身份和版本、
  LICENSE 与 NOTICE、契约清单的摘要；`legacy-clean` 还要通过 `tools/clean_engine.py` 的历史检查。来源形式不明或核对失败一律报错，
  不会改用另一种形式。
- Windows 和 Linux 都跑过（Linux 可以从源码包在 WSL 里跑）。
- README 的「Verified Test Baseline」按这次构建更新，测试数量写明日期、环境和范围；CHANGELOG 记下这一版的变化，发布时在版本标题
  写上发布日期。
- 引擎是要发布的那一份（`soulrun --engine-info` 看版本和指纹）。

---

## 七、构建与产物验证

构建到一个新的空目录（下面用 `release-dist`），不和以前构建留下的文件放在一起：同名的旧文件内容可能不同。下面按名字点这两个
文件（以 1.0.0 为例）：

```bash
python -m build --outdir release-dist
python tools/check_dist.py release-dist/soulrun-1.0.0-py3-none-any.whl release-dist/soulrun-1.0.0.tar.gz
python -m twine check --strict release-dist/soulrun-1.0.0-py3-none-any.whl release-dist/soulrun-1.0.0.tar.gz
```

记下这两个文件的大小和 SHA-256（PowerShell 的 `Get-FileHash -Algorithm SHA256`，或者 `sha256sum`）。之后测试、上传的都是这两个
文件；不要用 `dist/*` 这样的通配。

`tools/check_dist.py` 在下面任何一种情况下报错：wheel 里的引擎文件不是清单里「随包安装」的那一批；缺了 SoulRun 自己必需的文件；
带进了缓存、运行数据、留底的引擎、仓库文件夹或 `.env` 文件；带了 SoulRun 不发的文件；出现运行时依赖；长说明里还有相对链接；
某个文件里有凭据、个人目录的路径、不在名单上的邮箱，或者源码包的压缩包头里记了用户名。想额外查非秘密标识而不写进源码：

```bash
SOULRUN_PRIVACY_WORDS="<词>,<词>" python tools/check_dist.py release-dist/soulrun-1.0.0-py3-none-any.whl release-dist/soulrun-1.0.0.tar.gz
```

命令历史、进程环境可能保留这些值；不要把真实令牌放进示例、命令参数或日志。检查未命中也不证明所有历史或任意未来输入安全。

然后在一个**干净的环境**里只装 wheel，对着装好的副本跑测试：

```bash
python -m venv /tmp/soulrun-check
/tmp/soulrun-check/bin/python -m pip install "release-dist/soulrun-1.0.0-py3-none-any.whl[dev]"   # 这个 wheel 和它的测试工具
/tmp/soulrun-check/bin/soulrun --version
/tmp/soulrun-check/bin/soulrun --verify-engine
SOULRUN_TEST_INSTALLED=1 /tmp/soulrun-check/bin/python -m pytest -rs
```

Windows 上把 `bin/` 换成 `Scripts\`。CI 的 `package` 任务在 Ubuntu 和 Windows 上用 Python 3.12 做同样的构建、检查和装好以后的测试
（构建到空的 `dist/`；CI 同样使用 `twine check --strict`）。README 或其他打包输入改了，即使版本仍为 1.0.0，
也不能用旧制品冒充新内容；保留旧包，在新的空目录重建并逐文件核对。

---

## 八、TestPyPI 验证

正式发布前先传到 TestPyPI，从那里装一次：

```bash
python -m twine upload --repository testpypi release-dist/soulrun-1.0.0-py3-none-any.whl release-dist/soulrun-1.0.0.tar.gz
python -m pip install --index-url https://test.pypi.org/simple/ "soulrun==1.0.0"
soulrun --version
soulrun --verify-engine
```

上传由维护者在自己的终端里亲手做；令牌不写进任何文件、不贴进任何对话。

---

## 九、正式 PyPI 发布

**发布由维护者亲手做，只在维护者明确决定发布时进行。本仓库没有任何脚本或工作流会上传安装包。**

```bash
python -m twine upload release-dist/soulrun-1.0.0-py3-none-any.whl release-dist/soulrun-1.0.0.tar.gz
```

要点：

- 先确认第六、七、八节全部通过。
- 上传前核对 PyPI 上的项目归属和账号权限、这个版本号是否已经存在，以及 GitHub 仓库对外可见、`main` 上就是这一版（第二节从
  GitHub 安装的是 `main` 上的最新提交）。
- 上传后先用明确的版本号装一次核对（`python -m pip install "soulrun==1.0.0"`），再看不写版本号时装到的是哪个版本。以后发预发布版本
  （如 `1.1.0a1`）时，不写版本号的安装不会选它，说明里要写成：

  ```bash
  python -m pip install --pre soulrun
  python -m pip install "soulrun==1.1.0a1"
  ```

- 版本号一旦上传就不能再用同一个文件名重传；要改就提高版本号（`python tools/check_docs.py --set-version X.Y.Z`）。
- 发布后从 PyPI 读回元数据核对（作者、网址、说明），并在一个干净的环境里分别从 PyPI 和 GitHub 装一次、跑 `soulrun --verify-engine`。

---

## 十、Git 与 GitHub 发布纪律

- 推送到 GitHub、打标签、发 Release 都由维护者决定和执行。
- 不提交运行数据（`.soulrun_cache/`、`.execution_cache/`、`.soulrun/`）、`.engine_backups/`、`dist/`、`build/`：仓库的 `.gitignore`
  已经排除它们，也排除 `release-dist/` 和 `release-dist-*/`。忽略规则不会移除已跟踪文件、清除历史、加密或收紧权限；
  提交与打包前仍须核对实际文件和内容，不要上传本机认证目录、私钥、原始会话或日志。
- 公开仓库的提交使用不含个人信息的身份；文件里不出现用户名、个人目录、带盘符的路径、个人邮箱（测试和 `tools/check_docs.py` 在查）。
- 推送以后看一遍 CI 的结果，再更新 README 里关于 CI 的说明。

---

## 十一、安装方式速查

| 方式 | 命令 | 用途 |
|---|---|---|
| PyPI | `python -m pip install soulrun` | 正式安装 |
| GitHub | `python -m pip install "git+https://github.com/AIXP-Labs/SoulRun.git"` | 正式安装（不经 PyPI，装 `main` 上的最新提交） |
| 升级 | `python -m pip install --upgrade soulrun` | 换到 PyPI 上的最新版本 |
| pipx / uvx | `pipx install soulrun`、`uvx --from soulrun soulrun` | 只要命令、不装进当前环境（不在测试里） |
| 源码，可编辑 | `python -m pip install -e .` | 开发 |
| 源码，带测试工具 | `python -m pip install -e ".[dev]"` | 开发、跑测试 |
| 源码，带测试和发布工具 | `python -m pip install -e ".[dev,release]"` | 发布前门禁、构建 |
| 构建好的 wheel | `python -m pip install "release-dist/soulrun-<版本>-py3-none-any.whl[dev]"` | 发布前核对（先构建，见第七节） |

---

## 十二、常见问题

### Q1：装好了，`soulrun --verify-engine` 报文件不一致？

装进去的引擎和清单记的不一样：可能有人改过包里的文件，或者装的不是同一次构建的产物。重新安装；仍不一致就报告（附
`soulrun --engine-info` 的输出）。

### Q2：`python -m pytest` 在新环境里有测试失败？

先看是不是没装 `.[dev]`（`pytest` 等测试工具在里面）。测试不依赖时区数据，也不依赖 `PATH` 上有没有 `python`：`--doctor` 的测试
用的就是正在跑测试的那个解释器。仍然失败时，带着 `python -m pytest -rs` 的输出报告。

### Q3：卸载以后运行还在吗？

在。运行在 `soulrun_cache_dir`，不在包里。重新装回同一个构建以后，没跑完的运行可以接着跑；装的是别的引擎构建时，见第二节「升级」。

### Q4：可以只装 wheel、不要源码吗？

可以。装好的包自己带着引擎，不需要源码目录。源码里多出来的只有测试、工具、示例和文档。
