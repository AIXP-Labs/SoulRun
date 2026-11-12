# SoulRun

**一个调用的 AISOP 执行引擎 —— 任何宿主都能运行 AIAP 程序与 AISP 技能**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![CI](https://github.com/AIXP-Labs/SoulRun/actions/workflows/ci.yml/badge.svg)](https://github.com/AIXP-Labs/SoulRun/actions/workflows/ci.yml)

[English](README.md) | 中文文档

[快速开始](#快速开始) · [Python API](#用法) · [CLI](#命令行) · [宿主](#给宿主用的入口) ·
[隐私](#隐私与本机文件) · [验证范围](docs/verification-1.0.0.md) · [文档地图](docs/README.md)

## SoulRun 是什么？

SoulRun 是 AIXP 生态的执行运行时，形式是一个 Python 包。AISOP 程序——**AIAP 程序包**（`*_aiap`）和 **AISP 技能**
（`*_aisp`）——由 **SoulRun 的引擎**来跑：引擎一次交出一个节点，把每个节点的结果作为证据收回，把运行存在磁盘上，
所以能停、能续、断了能接回；遇到要人来定的地方就开门停下，等人回答。引擎装在一个没有任何依赖的包里，前面只放一个调用：

```python
import soulrun

message = "用易经看一下这个月"
ctx = soulrun(user_message=message)          # 开始一场运行，或者接回这句话所属的那一场
if ctx.doubt:                              # 这是问人的问题，不交给模型处理
    show_to_the_human(ctx.text)
else:
    reply = send_to_your_model(ctx.system_prompt, ctx.text + "\n\n" + message)
```

`send_to_your_model`、`show_to_the_human`是宿主提供的占位函数，不是SoulRun API。
引用展开和每轮记账使用[第一次调用](#第一次调用)里的循环。

SoulRun 不联系模型。它在本机磁盘上把运行准备好，交回这一轮模型需要的东西：`ctx.text`，以及和它配套的开场指令
`ctx.system_prompt`。宿主用自己接模型的方式把它们送出去（SoulBot 经 [SoulACP](https://soulacp.dev) 送），之后模型用引擎的命令
一步步往下做。默认是简装形式：文字里带着这一轮开头要用的那部分引擎程序（后面每一部分跟着需要它的那条引擎回复交），模型经
`soulrun` 命令运行引擎的工具、取业务程序，自己不打开任何文件。在命令行上，模型自己就是把引擎要给人看的内容展示给人的那一方，
SoulRun 把这些内容也交给它。切换以后是入口路径形式，和 SoulBot 改用 SoulRun 之前、它的代理模板交给模型的文字一字不差，
只是不运行任何东西的轮次不带它的入口段（见[程序形式](#程序形式)）。
所以 SoulBot、[SoulAgent](https://soulagent.dev)、一个小脚本、一个命令行会话，都能用同一个引擎跑同一批程序。

### 核心特性

- **一个调用** — `soulrun(user_message=...)` 开始一场运行，或者接回这句话所属的那一场；什么都不带时交回使用说明，不新建任何东西
- **任何宿主** — SoulRun 从不调用模型；宿主用自己接模型的方式送出 `ctx.text`，框架、代理、脚本、终端用的都是同一个引擎
- **模型自己不读文件** — 默认的简装形式下，引擎程序就在 `ctx.text` 里；主对话的模型运行引擎的工具、拿业务程序，都经 `soulrun` 命令，从不自己打开文件（见[程序形式](#程序形式)；子代理和退回的轮次见[已知限制](#已知限制)）
- **引擎在包里，可核对** — 引擎装在包里，每个文件的 SHA-256 都记在清单上；`soulrun --verify-engine` 拿装好的副本和随它装上的清单核对；在本仓库的检出里，一个工具就能换进新引擎（也能换回去）
- **程序和数据分开** — 引擎在装好的包里、只读；运行放在 `soulrun_cache_dir`（默认是程序旁边的 `.soulrun_cache`），这个目录自带忽略规则，不会被提交进版本库
- **零依赖** — SoulRun 和引擎都只用 Python 标准库，Python 3.11 及以上
- **人类主权写进构造里** — SoulRun 判断不了人要什么时，就问人；从不替用户编话、从不替人挑程序、从不替人答门（见[SoulRun 里的公理 0](#soulrun-里的公理-0)）
- **宿主入口** — `soulrun.host` 交出完整宿主在模型说话前后要调用的东西：每一轮之后、人按停止时、重启之后、模型断线之后，以及子代理开始和返回时
- **自检** — `soulrun --verify-engine` 逐个核对引擎文件；`soulrun --doctor` 在运行前检查这台机器，不留下任何东西
- **很多对话同时调用** — 准备运行时在线程和进程之间都加锁，两个调用不会拿到同一场运行

### 历史运行记录

SoulRun 1.0.0 不保证兼容 v6 时代的执行记录。仍保留的历史夹具只检查各自明确列出的性质，不代表一般性的 v6 记录兼容。
这一边界不改变当前 AISOP/AIAP/AISP 程序执行、人类授权检查，或恢复时不重复执行已接受工作的规则。

### SoulRun 里的公理 0

SoulRun 自己遵循公理 0——[人类主权与福祉](https://hsaw.dev)（Human Sovereignty and Wellbeing），不只是靠它的引擎。
下面这些规矩写在 SoulRun 的代码里，也都有测试：

| 规矩 | SoulRun 怎么做 |
|---|---|
| **人来定，SoulRun 来问** | 指定的程序找不到、`cache_dir` 不是这个对话最近那一场没做完的运行、没有话却同时点名了 AIAP 程序和 AISP 技能、点名了程序而这个对话还有一场不是为它建的运行没做完、或者有一场没做完的运行是另一个引擎构建开的：什么都不运行、不新建运行。人收到一个问题，写明找过什么、有什么、不具约束力的建议（`ctx.doubt`）。 |
| **从不替用户编话** | 没有话、点名了一个程序时，用空消息运行它；需要话的程序经引擎的人类主权疑惑门去问人。SoulRun 从不替人写请求。 |
| **从不替人选** | 指定的程序就用指定的，绝不悄悄换掉；哪个候选合用户的话由引擎判断，拿不准就交给人。 |
| **从不替人答** | 门和疑惑原样给人看；人的回答作为一条普通消息回来。SoulRun 里没有任何东西会回答问题；运行停在门上、等人回答时，标明不是人说的那一轮（`human_turn=False`）会被拒绝（`HUMAN_REPLY_REQUIRED`）。 |
| **不悄悄退回默认** | 设了但用不了的值会报错，带固定的错误码，绝不悄悄换成默认值。 |
| **人的话还是人的** | SoulRun 不打开任何网络连接。运行里有用户说的话，只放在 `soulrun_cache_dir`，命令行读用户的话的那个文件也挪进它那一场运行。SoulRun 新建的、或第一次接管的目录，没有 `.gitignore` 时写进内容为 `*` 的 `.gitignore`（在 Linux、macOS 上，它新建的目录只有自己能读），已经放着别的文件的目录会被拒绝。 |
| **做了什么就说什么** | 每场运行都记下用了哪些目录、每个目录是参数、环境变量还是默认给的；`soulrun --doctor` 把会悄悄拖累运行的情况报出来。 |

引擎在一场运行里遵循同一条公理：用户门和人类主权疑惑门会让运行停下，直到人回答；人按停止，这一轮就结束。

---

## 快速开始

### 前置条件

| 需要 | 说明 |
|---|---|
| Python 3.11+ | `requires-python` 声明下限，不是上限。CI 配置 3.11–3.15；实际运行头的已测结果与未测版本分别记录（见[已验证测试基线](#已验证测试基线)） |
| 模型的命令行能找到的 `python` | 模型用它运行这些：入口路径形式下的每个引擎工具；不管哪种形式，子代理的引擎工具（引擎给子代理的程序写的是 `python <引擎目录>/python_tools/...`）；不管哪种形式，程序自己写成 `python ...` 的工具。只有简装形式（默认）的主对话运行引擎的工具不靠它，按完整路径写出运行 SoulRun 的那个解释器。`soulrun --doctor` 两个都会报出；找不到 `python` 时，不管哪种形式都报 `FAIL` |
| 能接模型的宿主 | 能把 `ctx.text` 送给模型、再把回答带回来的任何东西：SoulBot、一个 SoulACP 会话、一个 API 客户端 |
| Windows 上的时区数据 | python.org 的 Python 要 `python -m pip install tzdata`（见[已知限制](#已知限制)） |

### 安装

```bash
python -m pip install soulrun                                          # 从 PyPI
python -m pip install "git+https://github.com/AIXP-Labs/SoulRun.git"   # 或者直接从 GitHub
```

这些是发布后的安装命令，不证明任一平台当前已经发布。首次发布准备期间固定V1.0.0；本地候选应使用已核验制品或获准源码，
核对清单，不能只看版本号。见[验证范围](docs/verification-1.0.0.md)。

装好以后核对：

```bash
soulrun --version                # SoulRun 的版本号和带着的引擎的版本号
soulrun --verify-engine          # 装好的引擎就是记下的那一份
```

要改 SoulRun 本身、跑它的测试，在本仓库的一份检出里可编辑安装：`python -m pip install -e ".[dev]"`；构建和发布见 [INSTALL.md](INSTALL.md)。

### 第一次调用

把你的程序放进一个代理目录——AIAP 程序包放在 `aiap/` 下，AISP 技能放在 `aisp/` 下——在那里调用 SoulRun（或者传 `agent_dir=`）：

```bash
soulrun                                      # 使用说明
soulrun --doctor                             # 运行需要的东西都齐了吗？
soulrun --user-message-file msg.txt          # 打印应当交给模型的文字（msg.txt 随后收进这场运行）
```

```python
import soulrun

from soulrun import host

ctx = soulrun(user_message=message, session_id="conversation-1",
              host_tools={"agent": False})   # 照实说宿主能做什么：不给时引擎当作能派子代理
if ctx.doubt:                                # SoulRun 先问人：原样给人看，然后等
    show_to_the_human(ctx.text)
else:                                        # program 或 text_only：轮到模型
    reply = send_to_your_model(ctx.system_prompt, ctx.text + "\n\n" + message)   # 先开场指令，再这一轮的文字
    show_to_the_human(host.expand_refs(reply, cache_dir=ctx.cache_dir))   # 给人看正文，不是引用
    host.after_turn(ctx.cache_dir, reply)    # 每一轮之后都调
```

包带类型标注（`py.typed`），但类型检查器认不出「模块可以调用」：做类型检查的宿主写 `from soulrun import run`、调用 `run(...)`，
是同一个函数，返回 `Ctx`（给了 `cmd=` 时返回 `CmdResult`）。

不接模型的完整宿主循环见 [`examples/minimal_host.py`](examples/minimal_host.py)；经 SoulACP 接真实命令行模型的同一个循环见
[`examples/soulacp_host.py`](examples/soulacp_host.py)。

---

## 架构

### SoulRun 在哪一层

```text
宿主（SoulBot、SoulAgent、一个脚本、一个终端会话）
  │  soulrun(user_message=..., session_id=...)
  ▼
SoulRun ── 找到这个对话的那一场运行，或者新准备一场；定下候选；
  │        判断不了人要什么时就问人
  │  ctx.text：这一轮交给模型的文字（默认带着简装的引擎程序）
  ▼
宿主把 ctx.text 送给自己的模型（SoulACP、某个 API……）
  │
  ▼
模型用引擎自己的命令驱动引擎：
  next-node → 做这个节点 → node-commit → …… ；遇到门，运行停下，直到人回答
```

### 程序和数据是分开的

| 什么 | 在哪 |
|---|---|
| 引擎（程序） | 安装好的 `soulrun` 包里面，只读 |
| 运行 | `soulrun_cache_dir`——默认是代理目录（不指定时就是当前目录）里的 `.soulrun_cache`，或者你指定的那个目录。只放运行数据。放着引擎程序的目录（比如 SoulBot 代理自己的引擎文件夹）会被拒绝，免得两个引擎共用一批运行；已经放着别的文件的目录也会被拒绝。删掉它就删掉了所有运行，包括没跑完的 |
| 你的程序 | `aiap_dir`、`aisp_dir`（默认是代理目录里的 `aiap/`、`aisp/`） |

`soulrun_cache_dir` 里面：

| 路径 | 谁的 | 是什么 |
|---|---|---|
| `.gitignore` | SoulRun 的 | 内容是 `*`，减少误把运行数据纳入的机会。SoulRun 新建这个目录、或第一次接管一个没有它的目录时写进去；之后归目录的主人决定。它不移除已跟踪文件、不阻止强行纳入、不加密、不做访问控制 |
| `.execution_cache/<N>/` | 引擎的 | 每场运行一个文件夹。引擎保留最近的 100 场（`CACHE_NUM`），更早而且已经结束的会被删掉；还在进行或者在等人回答的运行不会被删。每次调用都要把留着的运行逐个读一遍：在更早构建的测试机上量过（这一版没有重新量），几场时一次调用约 50 毫秒，100 场时约 0.2 秒。这个对话最近一场的索引越大，一次调用也越慢：SoulRun 和引擎每次都要读它、校验它（同一次测量里，1.9 MB 的索引读一次约 77 毫秒，长的节点式程序会到这么大；SoulRun 自己在引擎准备这一轮之前读两次（找这个对话最近一场时一次、检查时再一次）、之后读一次） |
| `.soulrun/runs/<N>.json` | SoulRun 的 | 这一场是用哪些目录建的，每个目录是参数、环境变量还是默认给的；开这一场的 SoulRun 版本、引擎版本和引擎摘要，以及它的候选。之后再记下这一场有没有拿到简装形式、简装形式出过的问题，以及人在这里结束另一个引擎构建的运行时，记下它是这样结束的 |
| `.soulrun/turns/<N>.json` | SoulRun 的 | 这一场最近的一轮：`turn_id`（引擎的，就是场号，`ctx.turn_id` 也是，一场里每一轮都相同）、`host_turn_id`（宿主的）、`turn`（这一场的第几轮），还有这一场的 `trace_id`。引擎给新的一场编号是留着的最大号加一，最近的几场被删掉或清掉后，用过的号会再出现：`trace_id` 和这里记的不一样的一场，从 1 重新数。引擎两分钟内为同一句话把同一场再交回来（重启这一轮）时，只有 `host_turn_id` 也相同才算同一轮、号不变；不同、或者没给 `host_turn_id` 没法分辨，就是下一轮 |
| `.soulrun/delivered/<N>.json` | SoulRun 的 | 简装形式的一轮里，这一轮已经拿到了引擎程序的哪些部分，以及这一轮的 `turn_id`、`host_turn_id`、`turn`；新的一轮重新开始记（见[程序形式](#程序形式)） |
| `.soulrun/entries/<N>.txt` | SoulRun 的 | 命令行打印过的那一轮的全文 |
| `.soulrun/undelivered/<N>.jsonl` | SoulRun 的 | SoulRun 命令行没能打印出来的引擎回复，每条一行（读的一方关了管道）；回复本身引擎已留在这场运行里 |
| `.soulrun/prepare.lock` | SoulRun 的 | 空文件；准备运行时，操作系统在它上面加的锁让别的进程等着，两个进程不会拿到同一个运行编号。进程不管怎样结束，锁都会自动放开 |

除了命令行那一轮挪进运行目录的消息文件（`<运行>/_soulrun/message.<n>.txt`），SoulRun 不往任何一场运行自己的文件夹里写东西；
引擎删掉一场运行以后，SoulRun 为它记的东西也跟着清掉。

---

## 用法

### 用 Python

```python
import soulrun

ctx = soulrun(user_message="...")            # 包本身可以直接调用；soulrun.run 是同一个函数
ctx.kind          # "program" | "text_only" | "guide"
ctx.text          # 交给模型（如果是疑惑，就原样给人看）
ctx.system_prompt # 和这一轮配套的开场指令：放在宿主原来放开场指令的地方
ctx.cache_dir     # 这一轮属于哪一场运行
ctx.session_id    # 哪个对话：照传进来的，或者 SoulRun 定的
ctx.turn_id       # 引擎的 turn_id：就是场号，一场里每一轮都相同
ctx.entry_mode    # 引擎把这句话当成了什么：fresh、resume、recovery、terminal……
ctx.program_form  # "slim"（默认）、"entry_path" 或 "full"；不运行东西的一轮是 None
ctx.slim_fallback # 这一轮为什么用入口路径形式而不是简装形式，否则是 None
ctx.doubt         # SoulRun 在新建运行之前要问人时才有：问题的代码和选项
ctx.data          # 引擎自己的回答，原样

soulrun()                                    # 使用说明；不新建任何东西
soulrun(aiap="daily_report")                 # 没有话、点名一个程序：运行这个程序
soulrun(cmd="next-node", cache_dir=ctx.cache_dir)   # 运行一个引擎命令
```

`ctx` 还有 `blocks`（同一段文字，分成一块一块）、`places`（用了哪些目录、每个是谁给的）、`program`（这一轮交出程序时的程序文字）
和 `as_dict()`。包本身还有 `soulrun.__version__`、`soulrun.ENGINE_VERSION`、`soulrun.engine_info()` 和 `soulrun.guide()`。

### 交回的是什么

| `ctx.kind` | 什么时候 | 怎么办 |
|---|---|---|
| `program` | 一场运行准备好了 | 把 `ctx.text` 和人的话交给模型，`ctx.system_prompt` 作为开场指令 |
| `text_only`，`ctx.doubt` 没有值 | 引擎判断这一轮不该进程序（比如人点了停止之后、中断后请人确认时、取消时） | 把 `ctx.text` 交给模型；模型只回文字、不运行命令 |
| `text_only`，`ctx.doubt` 有值 | SoulRun 在新建运行之前有问题要问 | 把 `ctx.text` 原样给人看，然后等；不问模型 |
| `guide` | 没有话、没有点名程序、也没有 `cmd` | 读它 |

### 人看到的是什么

引擎让模型把每个公开块——门的菜单、节点的块、终答——都写成一行引用 `⟦engine:<运行>/<文件>⟧`，从不写正文。宿主给人看回答之前，
先把块放回去：`host.expand_refs(reply, cache_dir=ctx.cache_dir)`。每一轮之后（`text_only` 那一轮也一样）都调
`host.after_turn(ctx.cache_dir, reply)`：它除了记下说了什么，还会在回答里带着某个提问的菜单时，登记这份菜单已经送到——停止、重启、
断线、执行故障之后的提问，菜单没登记送到之前，引擎不收人的回答。运行里的门也一样，给人看过以前不收回答：给人看过，是指它的菜单写下了
（引擎的停门只在主对话取到它时才写，子代理碰到它、或者引擎在收答复时开出它，都不写；子代理停下的业务门，在主对话下一步取到它时才写
——不管什么宿主，主对话都在给人看这道门之前先取这一步；宿主记下这个子代理交回（`host.observe_agent_return`）并不写菜单或算作给人看过），
或者登记了已送到。在那之前来的话不算回答；
主对话下一步会把这道门给人看，人到那时再答。

### 接着一场运行

模型的回答停在一个问题上时，等人回答，再带着回答调用一次：

```python
ctx = soulrun(user_message=answer, session_id="the same conversation")
```

引擎会认出这是回答，接着同一场往下走。任何时候都不替人回答。`cache_dir=` 只用来确认这句话是给那一场的：它必须是这个对话最近
那一场没做完的运行，否则先问人。一个对话一轮做完再来下一轮：上一轮做完（模型说完、`after_turn` 做完）再调用，期间进来的话由宿主
排队——模型还在做时送进来的话，会被当成「上一轮被打断」。

### 没有用户的话时

没点名程序（或者只给了大目录）：交回使用说明。点名了一个程序（`aiap=` 或 `aisp=`）：运行它——有些程序不需要话；需要的程序
会开门问人（引擎的规矩），SoulRun 从不替人编话。AIAP 程序和 AISP 技能都点名了：没有话说明要运行哪一个，所以先问人，
用中英两种文字，因为没有话可以判断人的语言。

这个对话还有一场没做完、又不是为点名的程序建的运行时，点名的程序不会开始（引擎一个对话只接着一场运行）：先问人
（`DESIGNATED_RUN_UNFINISHED`）——接着那一场、在另一个对话里运行这个程序，或者取消。有话的时候也一样。

### 参数

都可以不给。

| 参数 | 不给时 | 意思 |
|---|---|---|
| `session_id` | 一个代理目录算一个对话（`ctx.session_id` 写明是哪个） | 这句话属于哪个对话；有对话的宿主应当总是给 |
| `cache_dir` | 由引擎去找这个对话的那一场 | 这句话是冲着哪一场说的；必须是这个对话没做完的那一场 |
| `aiap_dir`、`aisp_dir` | `agent_dir` 下面的 `aiap`、`aisp` | 放着很多程序的大目录 |
| `aiap`、`aisp` | 不指定 | 指定某一个程序：目录路径、它的入口文件，或者到上面的大目录里按名字找 |
| `agent_dir` | `SOULRUN_AGENT_DIR`，再没有就是当前目录 | 代理目录：放你的程序的目录，程序在它下面的 `aiap/`、`aisp/` 里（这是 SoulBot 的叫法，它的每个代理都有一个这样的目录） |
| `soulrun_cache_dir` | `SOULRUN_CACHE_DIR`，再没有就是 `<agent_dir>/.soulrun_cache` | 放运行的目录。指定的就是这个目录本身（和 pip、pytest、ruff 的 cache-dir 一样）；它必须是新的、空的，或者本来就是 SoulRun 的。别和 `cache_dir` 混了：那是它里面的一场运行。相对路径按当前目录解析，不按代理目录。 |
| `user_id`、`channel`、`model`、`host_fences`、`host_tools`、`human_turn`、`host_turn_id`、`origin_type` | 引擎的默认 | 宿主对这一轮知道的事。不给 `host_tools` 等于说宿主**能**派子代理：不能的宿主要写 `{"agent": False}` |
| `slim_program` | 开 | 简装形式，见[程序形式](#程序形式)；给 `False`（`SOULRUN_SLIM_PROGRAM=false`、`--no-slim-program`）就是入口路径形式，也就是 SoulBot 的文字 |
| `inline_program` | 关 | 试验性的第二步形式，见[程序形式](#程序形式)；开了它就不用简装形式，不能和 `slim_program=True` 同时给。两个开关只收 `True`、`False` 或不给；对应的环境变量只认 1/true/yes/on 和 0/false/no/off（空值算没设），别的值报 `SWITCH_INVALID` |
| `cmd` | — | 改为运行一个引擎命令；不能和 `user_message` 同时给。命令自己的选项写成关键字参数（`node=`、`payload=` 等），另有 `args=[...]`、`stdin=`、`timeout=`；SoulRun 自己的参数不能和它一起给（`ARGUMENT_NOT_FOR_CMD`） |

设了但用不了的值会报错，SoulRun 从不悄悄退回默认值。每个错误都是 `soulrun.SoulRunError`，带固定的 `code`、出问题的 `field`
和应当是什么（`expected`）：调用本身不对是 `UsageError`，带着的引擎载入不了是 `EngineUnavailable`；引擎自己报的错保留引擎的错误码。
错误码的清单见 [GUIDE.md](GUIDE.md)。

### 用哪一个程序

参数只决定**候选有哪些**。用哪一个，由引擎的主程序按用户的话来判断；拿不准就问人。

| 给了什么 | 候选 |
|---|---|
| 什么都没给 | `aiap_dir` 和 `aisp_dir` 里的全部 |
| `aiap=` 或者 `aisp=` | 就这一个 |
| 两个都给 | 就这两个 |
| 指定了，同时又给了大目录 | 只用指定的 |
| 指定的找不到 | 什么都不运行：SoulRun 来问，写明到哪里找过、大目录里有什么、它会建议什么 |

### 引擎命令

```python
soulrun(cmd="next-node", cache_dir=...)                       # 现在该做的节点
soulrun(cmd="node-commit", cache_dir=..., node="...", payload={...})
```

`next-node`、`node-commit`、`stop-decision`、`gate-answer` 是引擎自己的命令行工具。模型每一步都用前两个。简装形式（默认）交给模型的
文字里，这些工具写成经 SoulRun 运行的命令；入口路径形式里写的是引擎脚本的路径。几种写法运行的是同一份代码。在命令行里、简装形式的
一轮中，引擎的回复先完整打印，这一轮还没给过的、这一步要用的那部分引擎程序跟在后面（见[程序形式](#程序形式)）；Python 的
`soulrun(cmd=...)` 只返回回复本身。

---

## 命令行

```bash
soulrun                                              # 使用说明
soulrun --user-message-file msg.txt                  # 打印应当交给模型的文字；msg.txt 收进这场运行
soulrun --user-message-file msg.txt --keep-message-file   # 同上，msg.txt 留在原处
soulrun --user-message-stdin --json < msg.txt        # 改为打印一个 JSON 对象
soulrun --aiap <名字>                                 # 没有话、点名一个程序：运行这个程序
soulrun --cmd next-node --cache-dir <目录>            # "--cmd 名字" 以外的内容原样交给引擎的工具
soulrun --program --cache-dir <目录> [--node 节点 | --field 字段]   # 这场运行绑定的业务程序（JSON）
soulrun --report <链接> --cache-dir <目录>           # engine-report: 链接后面的完整执行报告
soulrun --engine-node <名字> [--cache-dir <目录>]     # 按需打印简装引擎程序的某一部分
soulrun --expand <引用> --cache-dir <目录>          # 一块给人看的内容的正文，和宿主展示的一样
soulrun --user-message-file msg.txt --no-slim-program   # 入口路径形式（SoulBot 的文字）
soulrun --version                                    # SoulRun 的版本号和带着的引擎的版本号
soulrun --engine-info                                # 带的是哪一份引擎（JSON）
soulrun --verify-engine                              # 逐个文件核对带着的引擎和记下的 SHA-256
soulrun --doctor                                     # 运行需要的东西是否都齐了？不留下任何东西
```

`soulrun --doctor`（需要时照一场运行会拿到的样子加 `--agent-dir`、`--soulrun-cache-dir`、`--aiap-dir`、`--aisp-dir`、`--aiap`、`--aisp`
和程序形式的开关 `--slim-program`、`--no-slim-program`、`--inline-program`，以及 `--json`）每项检查打印一行——`OK`、`WARN` 或
`FAIL`：版本号、引擎文件和清单是否一致、简装程序是不是由这份引擎生成的、SoulRun 调用的引擎接口、模型的命令行找到的 `python`、
时区数据、带这些开关的运行会用哪种程序形式、引擎自己读的环境变量（`CACHE_NUM` 决定留几场运行）、代理目录和里面的程序（还有放错目录的程序、引擎会运行的登记脚本）、放运行的目录（真的建一个文件试写、马上删掉——Windows 上
常用的那种判断只看「只读」属性）、它缺 `.gitignore` 或者（Linux、macOS 上）别的用户能打开、没有跑完的运行，以及 Windows 上放运行的
目录深到引擎的文件会达到 260 字符上限。它不运行任何程序。有检查不通过时返回 `1`；只有提醒时不算失败。

用户的话只从文件或者标准输入读，不直接写在命令行上。开头的字节顺序标记（BOM，记事本和 PowerShell 存文件时常带）会被去掉，
命令行和 Python 调用都一样：它不是用户说的话，而且引擎认不出它后面的「继续」。带字节顺序标记的 UTF-16 文件（Windows PowerShell 5.1
用 `>` 写出来的就是这种）也能读；其它不是 UTF-8 的一律拒绝（`MESSAGE_NOT_UTF8`），不去猜。这一轮有了运行以后，消息文件会被挪进
那一场的运行目录（`<运行>/_soulrun/message.<n>.txt`），用户的话不留在项目里，引擎删掉这一场时一起删；加 `--keep-message-file`
就留在原处；没有运行的一轮（还没开始运行就要问人的问题）也留在原处，回答时还要用。消息文件写在一个新的放运行的目录里、它是那里
唯一的东西时，不妨碍这个目录被使用。

在命令行上打印的一轮，SoulRun 和模型之间没有宿主程序把引擎用引用行点名的块（计划、节点块和其中的消息、门、终答、证据）展示给人：
模型自己就是宿主。打印的文字里写明这一点（`[SOULRUN SCREEN]`）；每条引擎回复之后，命令行把它点名的块的正文打印在
`[SOULRUN FOR THE HUMAN]` 下面，每轮每块一次，由模型打印到屏幕上。放不下的块顺延到后面有空间的回复（门和终答那两条回复都很短）；
`soulrun --expand` 可以按需取一块。`--json` 和 Python 调用是给宿主程序用的，宿主自己展示这些块（SoulBot 就是），这些都不加。

返回值：`0` 成功（使用说明、一场运行、给人的一个问题，都算成功）；`2` 用法不对；`1` 其它错误（`--verify-engine` 或 `--doctor`
有检查不通过、引擎用不了、引擎报错）；带 `--json` 时，SoulRun 报的错以一个 JSON 对象打印到标准错误，`--verify-engine` 和
`--doctor` 的报告（含不通过的检查）以 JSON 打印到标准输出。用 `--cmd` 时，引擎工具运行了，返回值就是
工具自己的；它的回复打印不出来时是 `74`（见[引擎](#引擎)）；在那之前 SoulRun 自己拒绝的用法（没写命令名或命令名不认识、和用户的话
一起给了 `--cmd`）算用法不对，返回 `2`。

---

## 给宿主用的入口

`soulrun.host` 把宿主在模型说话前后要调用的引擎函数交出来，宿主不用知道引擎在哪里：

```python
from soulrun import host

# 每一轮
host.expand_refs(reply, cache_dir=ctx.cache_dir)      # 人看到的回答：正文，不是引用
host.after_turn(ctx.cache_dir, reply)                 # 每一轮之后：登记已送到的提问菜单，记下说了什么
host.observe(cache_dir, reply)                        # 单独做 after_turn 的第二步：记下模型说了什么
host.finalize(cache_dir)                              # 单独做 after_turn 的最后一步：回答已经存好
# 人按停止、宿主重启、模型断线
host.stop(ctx.cache_dir, host_run_id)                 # 人按了停止
host.open_question(cache_dir)                         # 一场运行在模型之外等着人回答的提问；没有就是 None
host.mark_question_delivered(cache_dir)               # 宿主自己把那个提问给人看了
host.interrupted_runs(created_before=started_at)      # 被重启打断的运行
host.resume_interrupted_enabled()                     # 人的设置：重启后自动接回，还是问人（默认）
host.open_restart_question(cache_dir, instance_started_at=started_at)   # 开关关着：问人（或 SKIPPED）
host.mark_interrupted(cache_dir)                      # 开关开着：记下这一场被打断了……
host.resume_prompt(cache_dir)                         # ……以及接回这一场用的文字
host.runner_recovery(host.RecoveryRequest(...))       # 模型断线以后怎么办
# 东西在哪，以及交给模型的是什么
host.soulrun_cache_dir(agent_dir=...)                 # 代理的运行放在哪
host.cache_root(agent_dir=...)                        # 其中放编号运行的那个目录
host.latest_run(session_id, agent_dir=...)            # 一个对话最近的一场；没有就是 None
host.program_root()                                   # 包里的引擎程序目录（引擎的工具在这里）
host.engine("lib.stop_flow")                          # 任意一个引擎模块，给已经按名字调用它的宿主用
host.system_prompt("slim")                            # 某种形式的开场指令，不用先调用
host.project_slim_policy(text, cache_dir=..., entry_mode=...)     # 简装一轮的固定指令，用来比较两轮
host.program_view(ctx.cache_dir)                      # soulrun --program 打印的内容（node=、field= 同命令行）
host.execution_report(link, cache_dir=ctx.cache_dir)  # engine-report: 链接后面的完整执行报告
# 子代理（见下）
host.dispatches_nodes(index)                          # 这一场是不是把节点派给子代理？
host.observe_agent_start(cache_dir, sha256, ...)      # 宿主看到了什么：一个子代理开始了
```

以前把引擎放在每个代理目录里的宿主：凡是用「代理的引擎文件夹」指运行的地方，换成 `soulrun_cache_dir(...)`；指引擎的工具的地方，
换成 `program_root()`。这些入口都不新建放运行的目录：问一个从没跑过的代理，什么都不会留下；第一次 `soulrun(...)` 运行时才建它。
SoulBot 怎样接 SoulRun，以及宿主必须守的几条（一个进程只用一份引擎、找运行只问 SoulRun、旧引擎和另一个 SoulRun 构建留下的运行怎么处理）见 [docs/guide/02-soulbot-integration.md](docs/guide/02-soulbot-integration.md)。
执行报告块的末尾是一个指向完整报告的 `engine-report:<运行>/<节点>@<次>/<sha256>` 链接：SoulBot 的网页能打开它，其他宿主用
`host.execution_report(link, …)` 或 `soulrun --report <链接>` 打开——核对方式和 SoulBot 一样（属于这场运行、指纹对得上），长的分页。
有自己的开场指令的宿主在那里改放 `ctx.system_prompt`，这样开场指令总和这一轮的程序形式一致（SoulBot 的代理模板就是这样做的；
使用说明和 SoulRun 在新建运行之前问人的那一轮，`ctx.system_prompt` 是 `None`，模板就留着自己只回文字的开场指令）。

**宿主重启以后**由人的设置决定（`host.resume_interrupted_enabled()`，读 `SOULBOT_RESUME_INTERRUPTED_RUNS`；不设就是停下问人）。
对 `interrupted_runs(created_before=…)` 里每一场没被停过的（`row["stopped"]` 为假）：开关关着时，调 `open_restart_question(...)`；
结果是 OPENED 时，在那一场的对话里把 `open_question(cache_dir)["text"]` 给人看，再调 `mark_question_delivered(cache_dir)`——
人的回答之后作为普通消息进来。引擎自己的停门刚写下、还没写进索引就中断的那一场，返回 SKIPPED，不用给人看什么：人下一句话进来时接着
这一场，先给人看那道门（不是人说的那一轮，SoulRun 像停在门上时一样拒绝，报 `HUMAN_REPLY_REQUIRED`）。开关开着时，`mark_interrupted(cache_dir)`，再把
`resume_prompt(cache_dir)` 经 `soulrun(..., session_id=<那一场的>, origin_type="engine_recovery", human_turn=False)` 送进去。被停过的那一场交给人；
它的提问 `row["question"]` 从没送到过时，再给人看一次。接回的文字只在那一场自己的对话里有效。

**人按停止**：`host.stop(ctx.cache_dir, host_run_id)`，同时结束正在进行的这一轮模型。人下一句话照常经 `soulrun(...)` 进来；
引擎和模型商量出要问人什么，把问题给人看的那一轮回答和其它轮一样处理。

**模型断线**：`host.runner_recovery(request)`，`phase="plan"`，得到引擎的决定（各个阶段见 `host.RECOVERY_PHASES`）。`resume`：
等 `delay_seconds` 秒，发 `phase="start"`，把决定里的 `prompt` 交给模型，这一轮结束后发 `phase="complete"`（被取消时发
`phase="cancel"`）。`ask`：把 `public_text`（展开后）给人看，发 `phase="delivered"`。`wait` / `hold`：有 `public_text` 就给人看，
过 `next_probe_seconds` 秒再试。`stop`：放弃，有 `public_text` 就给人看。`completed`：这一场已经跑完了。

**一场运行的几轮共用一个模型会话。** 这样做的宿主（SoulBot 的发送层就是）用
`host.project_slim_policy(text, cache_dir=..., entry_mode=...)` 比较简装一轮的固定指令；`text` 是宿主交给模型的整段文字，
`ctx.text` 也在里面（只给 `ctx.system_prompt` 时里面没有那段程序，交回 `None`；按位置传：参数名是 `system_prompt`）。它先重建并核对这个包生成的那段程序，再交回
`policy_text`（把那段程序换成一个记号以后的指令）、`source_digest` 和原封不动的那段程序（`runtime_fragment`）；核对不了的一律交回
`None`。`policy_text` 只用来比较，绝不拿来代替原文发给模型。它不授权任何事：能不能沿用这个模型会话，仍要看宿主自己的核对和引擎核实过的
宿主自己的受保护检查。本轮默认不信任报告来源，`host.parent_policy_ref` 返回 `None`；普通报告不认证父会话或子代理身份。

**子代理**（宿主报告只作诊断）。节点式的运行（`host.dispatches_nodes(index)`）把节点派给子代理。宿主可以报告它看到的工具事件，
但本轮没有任何报告来源获准证明原子代理身份。出现同步的 Agent/Task 调用，或接回某个子代理的 SendMessage 时：
`observe_agent_start`（带它的 prompt 的 SHA-256；回答里给出票号）。这个调用结束时：`observe_agent_return`（完成或失败）；
引擎只记返回事实，不写业务门菜单或算作给人看过。不管什么宿主，主对话在展示交回的引用之前先取一次下一步，SoulRun 在那一步写菜单、
把门交给主对话；返回时另行封存的已接受块证明不发布菜单，也不登记门的送达。
接回的子代理，SDK 自己的任务事件：`observe_agent_task_event`；SendMessage 失败：`observe_resume_failure`。子代理发出的工具调用
（SDK 挂在它的父调用下面报）：待执行时 `observe_tool_request`，结束时 `observe_tool_result`（`resolve_tool_parent` 认出接回的
子代理原来的父调用）。两个只读的查询：`resumed_agent_start`、`parent_policy_ref`。每个入口都原样转给它的说明里写的那个引擎函数，
`soulrun --doctor` 和 `tools/upgrade_engine.py` 会核对这些函数。看不到工具调用的宿主（只用命令行）报告不了：派出去的节点里
过门或交回后，所有宿主都按无法证明原子代理身份处理，必须由人明确授权一个新代理，不冒称原代理续跑。
第一次未展示的业务门把业务选择和换人授权写在同一选项上；暂停查证不消耗业务答复，业务拒绝仍走原路由。
只有 `execute` 选项附带新代理授权；`cancel`、`terminate` 保留原种类和标签，不授权换人、不发新票。
「不导出但继续完成报告」仍可能是执行选项；范围以真实展示的题面和接受的人答为准，不能只凭某个词判断。
普通门已答、事后失联、旧题面没有换人说明或授权不清楚时，另行询问。先封旧单，接受人答后才发新单。
封权不证明旧进程退出；结果不明的外部操作先核对，不重做。不同有效检查点的换人单独计数，同一进度的重复失败仍受原两次限制。
报告本身不授予换人或续跑权限；受保护宿主事件及运行记录写域的资格另行审查，本轮没有恢复资格的开关。

---

## 引擎

引擎放在 `src/soulrun/soulrun_aiap`：它运行要用的文件，每个文件的 SHA-256 都记在清单上。

```bash
python tools/sync_engine.py --check                                                    # 证明没有走样
python tools/upgrade_engine.py --from <引擎目录> --engine-version <X.Y.Z> --dry-run      # 只看换进新引擎会改什么
python tools/upgrade_engine.py --from <引擎目录> --engine-version <X.Y.Z>                # 换进来
python tools/upgrade_engine.py --restore .engine_backups/<保留的那份>                     # 换回去
```

`upgrade_engine.py` 逐字节复制新引擎运行要用的文件，核对它的身份、版本、许可和契约指纹；引擎里的东西一概不改写。替换任何东西之前，
它先核对：简装程序能由新引擎生成、新引擎照 SoulRun 的调法接得住每个调用、点名一个程序能建出一场运行（不接模型），以及找得到
SoulBot 的代理模板、而且它还带着这些文字时，固定文字一致；其中任何一项不通过，什么都不改。之后把被换掉的引擎留底在 `.engine_backups/`，整份复制进新引擎，
写清单，重新生成简装程序。版本号不变而内容变了，要显式加 `--same-version`。`--restore` 先核对留底的归档、以及 SoulRun 能不能用它，
再放回去；现在的 SoulRun 调不了的旧引擎，要连同它当时的 SoulRun 一起恢复。`--legacy-clean` 选用给引擎较早的开发树用的旧清理工具（它会改写文字，
并把版本号写进引擎）；它拒绝 SoulRun 自己的引擎，这份引擎不用它。SoulRun 自己的版本号不会被动到，这里没有哪条命令会发布安装包。

- `src/soulrun/engine_manifest.json` 记着引擎的版本和每个文件的 SHA-256；`soulrun --verify-engine` 拿装好的副本和它核对。
- SoulRun 的版本号只担保 SoulRun 自己的部分（[GOVERNANCE.md](GOVERNANCE.md#versioning)）。引擎产出的东西随引擎版本变，不在这个担保里：
  `ctx.data`、`host.engine()` 拿到的模块、宿主入口交回的字典里引擎放的内容、引擎自己的错误代码、一场运行里的文件。第二步形式也
  不在里面；简装形式自己那几段文字的措辞会随引擎配合改进，也不在里面。换了引擎一定记进 CHANGELOG。
- 每个 1.x 的引擎都保留它继承下来的那套功能：版本号是 1.0.0，按版本号打开的那些行为照样开着。引擎的文件保持发布时的原样，
  其中的功能选择器也一样。
- 没做完的运行，要核对开它时记下的完整引擎摘要，光版本号相同不够。记录缺失或不同时，这场运行不会被接着跑：人的回合得到一个提问
  （`ctx.doubt["code"] == "ENGINE_BUILD_MISMATCH"`：结束那一场、到另一个对话里做、或先不处理）；人只回一个取消词时，用引擎的
  `terminate_run` 结束它，不执行它的任何步骤（只限同一引擎版本开的运行）；非人回合（`human_turn=False`）照旧报
  `ENGINE_BUILD_MISMATCH` 错误。要接着跑，回到开它的那个完整环境。这项核对是 SoulRun 在准备一轮时做的；不能因此改用引擎的工具
  直接去跑另一个构建的运行。
- SoulRun 命令行打印不出引擎的回复（读的一方关了管道）时，退出码 74，在标准错误写一行说明，并记进
  `<soulrun_cache_dir>/.soulrun/undelivered/<运行>.jsonl`；引擎自己的回复已留在这场运行里。
- 每一轮开始前给模型看的那几段固定文字和 SoulBot 的开场指令，是 `tools/port_agent_text.py` 从 SoulBot 的代理模板里取出来、写进
  `src/soulrun/_agent_text.py` 的，那里记着这份模板的 SHA-256；`[EXECUTION CONTEXT]` 段由 SoulRun 自己的代码（`_blocks.py`）逐行照样
  拼出。入口路径形式下 SoulRun 交出的文字和那份模板交给模型的一样，只有中断后请人确认、取消这两种轮次不同：它们不运行任何东西，
  给模板的只回文字断言，不给入口段和执行断言。简装形式保留其中的上下文段和中断提醒段，其余换成自己的入口段、断言段和开场指令。
  SoulBot 的代理模板现在把每一轮都交给 SoulRun，不再带这些文字，所以它们按最后一次生成的样子留在 SoulRun 里。
- `src/soulrun/engine_node.aisop.json` 是按引擎节点排好的引擎程序：仍是 AISOP 格式，每一段文字都从引擎的 `main.aisop.json`
  逐字拷贝；其中的 `soulrun_delivery` 写明哪一部分跟哪个引擎节点交，以及其余部分为什么不交。它由 `tools/build_engine_node.py` 生成，
  不手改（`--check` 证明它是最新的、完整的、逐字的，而且没有哪一部分提到交到那时模型还没拿到的文字）。

引擎不在这个仓库里手改：改动都经 `tools/upgrade_engine.py` 换进来。

---

## 程序形式

引擎程序怎样到模型手里。`ctx.program_form` 写明这一轮用的是哪种；`text_only` 的轮次没有（`None`）。`ctx.system_prompt` 是和它配套的开场
指令：宿主把它放在原来放自己开场指令的地方。

- **简装形式（默认）。** 设计原则：用了 SoulRun，模型自己不读任何文件，而且只拿到眼前这一步要用的内容。`ctx.text` 里带着用
  `engine_node.aisop.json` 组装的简装引擎程序的开头——引擎原文，用户的话放在 `user_input`——外加一段入口文字，告诉模型其余的事都经
  SoulRun 做：每个引擎工具写成
  `"<python>" "<soulrun>/_launch.py" --cmd next-node|node-commit|...`（运行 SoulRun 的那个解释器和这个包的启动文件，都写完整路径，所以
  不管模型的 shell 自己的 `python` 是哪个，都能找到这个 SoulRun），业务程序写成 `... --program --cache-dir <运行目录>`（主图、节点名单、
  程序的 system_prompt、output_mode、tools 和 params，其余较长的字段给出大小和指纹；`--node` 取一个节点的 function；`--field` 取任意
  一个字段的全文）。引擎回复里 `program_contracts` 点名的程序约定（比如共同约束）用引擎自己的读法
  `... --cmd next-node --read-program-contract <ref>` 取；SoulRun 按引擎的写法计字段，所以同一条规则两边报的大小和指纹一样。模型从不打开
  程序文件。入口段、断言段、开场指令、SoulRun 附在引擎回复后面的那几行，以及命令行上的屏幕规则，都是 SoulRun 自己的措辞。
- **按引擎节点交。** 每一轮开头只交 `entry` 这一组：引擎的身份、`output_mode`、`hsaw_first_law`、`system_prompt`、节点执行约定和提交约定
  （从第一条引擎回复起就要用）以及 `Start` 函数，约占主程序的五分之二；接回一场运行的轮次再加 `params` 和 `bootstrap_recovery`。其余各组跟着
  第一条需要它的引擎回复交，每轮每组一次：SoulRun 的命令行先完整打印回复，再打印 `[SOULRUN ENGINE NODE: <组名>]` 和那一部分（一段短的
  AISOP）。Router.match 带来 `RouterMatch`；Router.cache-setup 带来 `CacheSetup` 和 `NodeLoop`；业务节点带来 `NodeLoop`；派发带来派发范围约定；
  Engine.execute-report 带来 `Report`；Engine.final-answer 带来 `Final` 和终答交付约定；运行失败带来 `ErrorReport`。打印的内容守引擎自己的
  上限（29,000 字节；超过的输出，模型的命令行工具会存进文件）：附上会超限的部分不打印，只打印一行，写明是哪几组，并要模型做这一步之前
  先运行取它的 `soulrun --engine-node` 命令。始终不交的：引擎的
  `tools` 和 `json_schema`（每个引擎工具自己的回复写明它要什么）、指向四份约定的指针（每轮第一条引擎回复里已有全文），以及说明性字段。
  这一轮给过什么记在 `<soulrun_cache_dir>/.soulrun/delivered/<运行>.json`，同时记下是哪一轮：`turn_id`（引擎的，就是场号，和 `ctx.turn_id`
  一样，一场里每一轮都相同）、`host_turn_id`（宿主的）、`turn`（这一场的第几轮，怎么数见上面 `.soulrun/turns/<N>.json` 那一行）；新的一轮重新开始记，因为新的一轮可能是新的模型会话。
  `soulrun --engine-node <组、段或函数的名字> [--cache-dir <运行目录>]` 可以按需打印任何一部分。
- **真实运行。** 记录中的R115运行头已有有限的Claude、Codex CLI/SDK及隔离SoulBot证据；报告宿主限制、继承用例及未测路径仍显名保留。
  修改文档不等于重跑这些场景，也不认证所有宿主（见[已验证测试基线](#已验证测试基线)）。
- **带中断提醒的轮次**（人按停止以后的判断、接回、停止后作为新任务）也用简装形式：提醒先做，入口段和断言都这样写——停止以后的判断
  第一步是 `stop_decision`，其余是 `next_node`，提醒要求先打出的文字放在它前面——提醒或引擎回复里点名的引擎工具也一律经 SoulRun
  调用。只回文字的轮次（中断后请人确认、取消、提问）给上下文段、提醒段和只回文字的断言，不给会叫模型去读 `main.aisop.json` 的入口段。
- **退回。** 遇到下面几种情况，这一轮改用入口路径形式，并在 `ctx.slim_fallback` 里写明原因：简装程序做不出来（没有 `engine_node.aisop.json`，或者它是由别的引擎生成的）——
  `SLIM_PROGRAM_UNAVAILABLE`；或者这一场、或者这段对话的上一场在简装形式下出了问题——`EARLIER_SLIM_PROBLEM`：模型已经轮到过、下一轮
  来时运行还停在 Router.match、一个节点都没提交，或者在引擎节点上失败。这样的问题记进这场运行的记录，这段对话之后都用入口路径形式；
  别的对话照旧用简装形式。命令行上装不下的一轮按入口路径形式打印（`--json` 写明 `TOO_LONG_FOR_COMMAND_LINE`）。
- **入口路径形式。** `slim_program=False`、`SOULRUN_SLIM_PROGRAM=false` 或 `--no-slim-program`：SoulBot 改用 SoulRun 之前代理模板交给模型的
  文字（见[引擎](#引擎)）——模型自己去读 `main.aisop.json`——`ctx.system_prompt` 是当时配套的那段开场指令。只回文字的轮次在这里也是
  上下文段、提醒段和只回文字的断言：模板给中断后请人确认、取消也加上了入口段和「先读入口」的断言，可它们的提醒写着什么都不运行。
- **第二步形式（试验性）。** `inline_program=True`（或者 `SOULRUN_INLINE_PROGRAM=true`）会多交回一份主程序，用户的话作为数据、最后放进
  引擎原封不动的文字里的 `user_input` 位置；开了它就不用简装形式。在命令行里，输出不超过引擎自己的上限（29,000 字节）：整份装不下时
  不打印主程序，用一个记号写明全文在哪个文件里。它还没有用真实的运行验收过。

---

## 项目结构

```text
SoulRun/
├── src/soulrun/
│   ├── __init__.py              # 可以直接调用的包，以及版本号
│   ├── __main__.py              # python -m soulrun
│   ├── _api.py                  # 那一个调用
│   ├── _select.py               # agent_dir、aiap_dir、aisp_dir、soulrun_cache_dir、候选
│   ├── _adapter.py              # 一次调用期间把候选交给引擎
│   ├── _blocks.py               # 引擎这一轮之前交给模型的文字
│   ├── _agent_text.py           # 从 SoulBot 代理模板生成（不手改）
│   ├── _slim.py                 # 简装引擎程序，按引擎节点交
│   ├── _policy.py               # host.project_slim_policy：核对过的简装一轮固定指令
│   ├── _program.py              # soulrun --program：把一场运行的业务程序交给模型
│   ├── _report.py               # soulrun --report：链接后面的完整执行报告
│   ├── _launch.py               # 简装文字里写的那条命令（这个解释器、这个包）
│   ├── _records.py              # SoulRun 放在运行数据旁边的记录
│   ├── _filelock.py             # 跨进程，一次只准备一场
│   ├── _cmd.py                  # 引擎命令
│   ├── _screen.py               # 命令行上没有宿主：给人看的块
│   ├── _message_file.py         # 消息文件收进它那一场的运行目录
│   ├── _render.py               # 命令行打印的文字，守上限
│   ├── _engine.py               # 带着的引擎：在哪、版本、核对
│   ├── _doctor.py               # soulrun --doctor
│   ├── errors.py                # SoulRunError、UsageError、EngineUnavailable
│   ├── host.py                  # 给宿主用的入口
│   ├── cli.py                   # soulrun 命令
│   ├── guide.txt                # 使用说明（模型会话也会读）
│   ├── py.typed                 # 包带类型标注
│   ├── engine_manifest.json     # 引擎版本、来源、每个文件的 SHA-256
│   ├── engine_node.aisop.json   # 生成的：按节点排好的引擎程序
│   └── soulrun_aiap/            # SoulRun 的引擎：只有运行要用的文件
├── tests/                       # SoulRun 自己的测试（不调用模型）
├── tools/                       # 引擎清理、同步和换新、生成器、安装包和文档检查
├── examples/                    # 最小宿主，以及 SoulACP「程序门」
├── docs/                        # 文档地图和开发指南
└── pyproject.toml
```

---

## 测试

```bash
python -m pip install -e ".[dev]"                             # 测试工具
python tools/sync_engine.py --check                           # 引擎和清单一致
python tools/sync_engine.py --check-release                  # 只读核对引擎记下的来源形式和包内容
python src/soulrun/soulrun_aiap/tools/aiap_conformance_check.py src/soulrun/soulrun_aiap   # 引擎自己的 AIAP 符合性检查
python tools/build_engine_node.py --check                     # 简装程序和引擎一致
python -m ruff check src tests tools examples                 # 代码检查
python tools/check_docs.py                                    # 文档：链接、锚点、代码块、本机路径、页脚
python -m pytest -rs                                          # SoulRun 自己的测试（-rs：列出跳过的测试和原因）
SOULRUN_TEST_INSTALLED=1 <干净环境>/bin/python -m pytest      # 同一套测试，对着单独装好的安装包（见 INSTALL.md）
```

没有任何测试会调用模型。需要模型的地方，由测试向引擎提交模型会提交的那种内容。

### 已验证测试基线

历史精简及宿主中立使用说明修正后，当前97资源的源码清单摘要为
`9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`。
执行源码与治理字段不变，独立调用说明也已改准。

**11月11日对这个摘要的本地验收，发生在发行检查器刷新之前：**

| 范围 | 环境 | 结果 |
|---|---|---|
| 共享Engine完整选择 | Windows 3.12.9 | 8613 passed，9 skipped；总8622，0失败/错误 |
| 共享Engine完整选择 | Ubuntu 3.12.3 | 8606 passed，16 skipped；总8622，0失败/错误 |
| SoulRun源码包装 | Windows 3.12.9 | 912 passed，3 skipped；总915，0失败/错误 |
| SoulRun源码包装 | Ubuntu 3.11.18、3.12.3、3.13.18、3.14.10、3.15.2分别独立运行 | 每组911 passed，4 skipped；各总915，0失败/错误 |
| 全新安装wheel | Ubuntu 3.12.3 | 911 passed，4 skipped；总915，0失败/错误 |

随后QA进程竞态窄修在双平台各验17项守卫。当前8626个Engine编号由完整运行中8609个未变编号加这17项组合，
**不宣称8626项曾单场全量跑完**。25项平台skip分别在另一平台通过，但不把原全量改成零skip，
也不证明缺少权限的Windows原生symlink已经通过。
上述Python3.15结果是本地兼容证据，不是远端CI结果或支持政策变更。Windows SDK3.11–3.15与冷安装按之前准确正文继承，不是重新实跑。

另有一次本机用户site CLI/SDK更新，124份正文已核，但不表示生产宿主也更新。
当前发行检查器修订及其制品须单独保留维护者回执；带日期制品SHA、继承、观察和本地/远端CI区别见
[验证范围](docs/verification-1.0.0.md)。

[CI矩阵](.github/workflows/ci.yml)覆盖Windows、Ubuntu的Python3.11–3.15，共10项源码测试与2项包装作业。
新增Python3.15作业尚待远端运行，不能沿用之前的CI结果判通过。
旧构建表保留在[验证历史归档](docs/verification-1.0.0.md#readme-history-archive)。

---

## 安装选项

下面这些是给要改 SoulRun 本身的人用的；其他人从 PyPI 或 GitHub 安装（见[安装](#安装)）。

```bash
# 开发（可编辑安装），带测试工具
pip install -e ".[dev]"

# 构建与发布工具
pip install -e ".[release]"

# 构建好的安装包：装好的包自己带着引擎，不再需要这个目录
python -m build
pip install dist/soulrun-<version>-py3-none-any.whl
```

详细的安装、打包与发布见 [INSTALL.md](INSTALL.md)。

---

## 隐私与本机文件

- 运行记录可能包含用户消息、人答、工具输出及业务结果。SoulRun不加密这些内容；摘要用于检查内容变化，不用于隐藏内容或认证作者。
- 运行数据、宿主日志、服务商配置和凭据应放在源码及发布目录之外。ignore覆盖常见本机材料、保留`.env.example`模板；它不会撤下已经跟踪的文件、
  擦除历史、修改ACL，也不能证明目录私有。共享前必须核对准确文件。
- 敏感用户文字用标准输入或私有消息文件，不放在命令参数或终端历史字面值里。消息文件被收进运行不等于安全擦除，运行记录和宿主/服务商仍可能留副本。
- SoulRun本身不调用模型或上传记录；宿主、服务商、业务程序及其工具各有网络、日志和保留政策。宿主要如实传`human_turn`及能力标记；
  一个标记或普通报告不是经过认证的身份证明。
- 不把凭据或原始私有运行贴进issue。用合成复现并遵守[SECURITY.md](SECURITY.md)的披露流程；任何ignore或一次样本扫描通过都不能保证未来任意输入可公开。

## 已知限制

- **拦截边界。** 在合格宿主下，门会拒绝缺少已接受的人的回答、权限、票据或证据的受管操作。这不是操作系统的沙箱，也挡不住任意命令行
  或不可信的宿主去调用无关的工具。文件摘要核对的是记下的内容，不是独立可信的签名。引擎不核对的 `ASSERT` 不算机器证明过。
- **报告不认证原子代理身份。** 本轮所有报告来源都未获资格，包括经`soulrun.host`完整报告过程的宿主。
  继续已记录的未完成工作要由人明确授权新代理，不靠报告放行；先封旧单，但不证明旧进程退出。
  恢复原子代理续跑要另审受保护的事件来源和机器状态写域。录制或合成事件只验证规则，不证明真实宿主资格。
- **子代理停下的业务门，由 SoulRun 在主对话下一步给人看。** 契约规定主对话在给人看这道门之前先取一次下一步；这一步写出门的菜单、
  把门交给主对话，任何宿主都一样——SoulRun 自己的命令行用 `--host-tool agent=true` 跑（SoulSkill 桥就这样跑）、SoulBot、SDK
  宿主——已展示的业务门接受一次人的回答。宿主报告子代理交回，不写菜单、不算给人看过；在报告和主对话下一步之间断掉的一轮，人的回答仍先不收。
  模型若不取这一步就把子代理交回的引用贴出来，SoulRun 不算这道门
  给人看过：人的第一次回复不收，下一步把门给人看，人再答一次。
  这条展示规则不认证原child身份。首次题面明确合并业务选择和新代理授权；旧题面或事后失联要另问，不能默许换人。
- **指定的程序和请求对不上时**不会硬跑：在 Router.match 这一步，请求可以走 `no_match`，直接回答，不先开门问人；回答开头有一句话说明指定的或扫描到的程序里没有
  匹配的。**人在 Router.match
  选定了候选以后**，这一场就绑定在选定的程序上：改交另一个候选或 `no_match` 会被拒绝（`ROUTE_CHOICE_CONFLICT`），缺失或互相矛盾的
  选择证据不算人选过。这只保证选择被绑定，不保证模型写的标签或程序的结论是对的。
- **运行停在门上、等人回答时**，标明不是人说的那一轮（`human_turn=False`、`--machine-turn`）会被拒绝（`HUMAN_REPLY_REQUIRED`）。直接调用引擎
  自己的入口不报这个错，但也不把这一轮当作门的回答：引擎记下这句话，门照旧开着（`entry_mode` 为 `gate_hold`）。不管哪种，宿主都要
  照实说一句话是不是人说的。引擎自己的停门刚写下、还没写进索引就中断的那一场看上去还在进行；`SOULBOT_RESUME_INTERRUPTED_RUNS`
  关着时，发给它的非人回合 SoulRun 也一样拒绝（`HUMAN_REPLY_REQUIRED`），这一场里什么都不写；还标着在进行、一时又读不了的那一场
  也一样（被杀掉的进程留下的运行锁，引擎两分钟后才回收；索引不认识、引擎也认不出的门记录）。开关开着时，这句话照被打断的运行处理
  （取消词会结束它）。以宿主的接回标记开头、`cache_dir:` 写着同一个放运行的目录里这个对话的这种运行的话，两种开关下都交给引擎。
- **还靠「引擎版本以 7. 开头」认运行记录格式的 Creator 程序**，在引擎 1.0.0 上找不到要进化的目标程序，要等 Creator 自己改掉这个判断。
- **除了「代理目录下的全部」以外的候选名单**，是在一次调用期间在内存里交给引擎的，因为引擎的 `prepare` 入口还不收这些。
- **新建运行之前提出的问题**（程序找不到、`cache_dir` 对不上、对话里有一场不是为点名的程序建的运行没做完、有一场运行是另一个引擎构建开的）是作为文字交回的。
  `ctx.doubt["options"]` 里每个选项都带着「选了它以后怎么办」——`call`（带上要换掉的参数再调用一次）、`ask`、`cancel`——但 SoulRun
  不记这个问题：谁把问题给人看，谁把回答带回来。
- **引擎内部的断线恢复**默认程序和数据在同一个文件夹里。`host.resume_prompt`、`host.runner_recovery` 把放运行的目录交给它，
  并把接回文字里的工具路径指向程序目录；宿主如果直接调用引擎自己的处理函数，模型会被叫去运行一个不存在的工具。（人按停止以后、
  模型判断这一场接着做（`stop-decision` 选 `continue`）时，引擎给的下一步指向引擎自己的 `next_node.py`。）简装形式下入口段让模型把
  回复里点名的引擎工具一律经 SoulRun 调用，不管写的是哪个路径；入口路径形式下，宿主直接调用断线恢复的处理函数时仍会碰到。
- **模型的命令行要能读到装好的包。** 引擎的工具（入口路径形式下还有引擎程序）从 SoulRun 装好的位置读（`soulrun --engine-info`）；只许读工作目录、
  或者在沙箱里运行的模型命令行，做不了第一步。已有有限的Claude、Codex路径实测，不认证所有CLI、沙箱或报告宿主配置。
- **带空格的目录。** 交给模型的命令里，引擎目录和放运行的目录原样写出、不加引号（固定文字逐字照 SoulBot）：其中任何一个带空格时
  （比如 Windows 的 Program Files 下面），照字面执行命令的 shell 会失败。SoulRun 装在、运行放在不带空格的目录里。简装形式下
  运行 SoulRun 本身的那条命令加了引号，放运行的目录没有。
- **简装形式只到主对话。** 引擎交给子代理的是它自己那份引擎程序（`agent_engine.aisop.json`）的路径，子代理自己去读。引擎自己的文字
  也还在说「读程序入口」，它交出的节点信息里也没有业务程序的 tools、params 和 system_prompt：简装的入口段写明这一步已经做了，
  并让模型用 `soulrun --program` 取。这两样引擎自己都不交。
- **上不上屏由模型决定。** 在命令行上，SoulRun 把每一块给人看的正文都交给模型，要模型打印出来。在更早构建的独立会话里，Claude Code
  把每一道门的全部内容、每一份终答和证据、大部分节点块都打印到了屏幕上，但最前面几步（路由、路径设置、第一个节点）的块没有打印，
  怎么改说法都一样；后来的CLI/SDK功能通过也不证明每个模型会转发每一块。需要确定性展示的宿主应自行渲染已接受正文/引用。
- **按节点交的部分只经 SoulRun 的命令行到模型手里。** 用别的方式运行引擎工具（按路径运行引擎脚本，或者在 Python 里用
  `soulrun(cmd=...)`）只拿到回复本身；入口段告诉模型缺哪一部分就用 `soulrun --engine-node` 取。附上会让回复超过打印上限的部分，模型要多跑
  这一条命令；引擎自己打印的回复就已经超限时（它能折叠的都折叠了），会把长输出存进文件的命令行工具照样存，点名那一部分的一行跟在后面。
- **退回的轮次仍会自己读文件。** 用入口路径形式交出的轮次（简装程序做不出来，或者这段对话在简装形式下出过问题）带的是 SoulBot
  的开场指令，所以模型会自己读 `main.aisop.json`、用 shell 里的 `python` 运行引擎的工具。带中断提醒的轮次不会退回。
- **测过的平台。** 带日期的本地Python3.11–3.15 SDK及Ubuntu Engine结果只具有上文准确范围，macOS未测。
  本地QA和文档修订不证明远端CI或全部平台已合格（见[已验证测试基线](#已验证测试基线)）。
- **Windows 上的时区。** 模型服务商说额度几点恢复并点名时区时（如「resets 2pm (America/New_York)」），引擎用 `zoneinfo` 读那个时区；
  读不到这个时区时（没有时区数据，或者时区名不认识）按本机时区算，并在这一场的记录里记一笔（`SUPPLY_RESET_ZONE_UNREADABLE`，
  运行报告里看得到）。Windows 自己没有时区数据：python.org 的 Python 要 `python -m pip install tzdata`。
  SoulRun 本身仍然没有运行时依赖；缺数据时 `soulrun --doctor` 会提醒。
- **Windows 上的路径长度。** 一场运行会在 `soulrun_cache_dir` 里一层层建到约 130–150 个字符深：最深的是节点的块文件，名字里有节点名
  和 64 位指纹：程序的节点（AIAP Creator 的一场里是 146，场号到三位数时 148），程序的节点名都短时是引擎自己的 `Engine.execute-report`
  （每场都会写它的块文件，场号三位数时 130）。Windows 没打开长路径支持时，放运行的目录长到装不下它，引擎就会写失败；引擎的工具现在
  直说路径太长（多长、上限 260），更早的构建报的是让人误会的「找不到文件或目录」（在更早的构建上，150 字符的目录在第一次提交时
  就失败了）。目录放浅一点，或者打开长路径支持；
  `soulrun --doctor` 按找到的程序的节点名和引擎自己的节点名算出深度、写出是哪个节点，并提醒。

---

## 文档

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | 文档地图：阅读入口、权威源、生成记录与文档门禁 |
| [docs/verification-1.0.0.md](docs/verification-1.0.0.md) | 带日期的运行头/制品证据、skip范围、继承用例及未验边界（中英） |
| [GUIDE.md](GUIDE.md) | 完整使用指南 |
| [INSTALL.md](INSTALL.md) | 安装、打包与发布 |
| [DEPENDENCIES.md](DEPENDENCIES.md) / [DEPENDENCIES_CN.md](DEPENDENCIES_CN.md) | 已验证依赖基线、Python 矩阵、引擎与升级策略 |
| [SECURITY.md](SECURITY.md) | 安全政策与漏洞报告（中英） |
| [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING_CN.md](CONTRIBUTING_CN.md) | 贡献流程，含「引擎不在这里改」的规矩 |
| [GOVERNANCE.md](GOVERNANCE.md) | 项目治理与决策 |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | 社区行为准则（公理 0 对齐） |
| [CHANGELOG.md](CHANGELOG.md) | 发布历史 |
| [docs/release-1.0.0.md](docs/release-1.0.0.md) | V1.0.0 发布说明：带着的引擎、为它验证过的结果、它不声称的东西（中英） |
| [docs/guide/01-design.md](docs/guide/01-design.md) | 设计说明：SoulRun 为什么这样做 |
| [docs/guide/02-soulbot-integration.md](docs/guide/02-soulbot-integration.md) | SoulBot 接 SoulRun：代理和宿主怎样接、宿主要守的规矩 |
| [examples/README.md](examples/README.md) | 最小宿主，以及 SoulACP「程序门」 |

---

## AIXP Labs [aixp.dev](https://aixp.dev)

AIXP Labs 开发并维护以下核心项目：

| 项目 | 描述 | 网站 |
|------|------|------|
| [HSAW](https://hsaw.dev) | 人类主权与福祉 —— Axiom 0 白皮书（基石） | hsaw.dev |
| [AIZP](https://aizp.dev) | AI Zenith-Zero Protocol —— 运行时行为对齐 | aizp.dev |
| [AIIP](https://aiip.dev) | AI Intent Protocol（AI 意图协议）—— 意图树治理、优先级与反馈 | aiip.dev |
| [AIKP](https://aikp.dev) | AI Knowledge Protocol（AI 知识协议）—— 长期知识组织、导航与治理 | aikp.dev |
| [AIJP](https://aijp.dev) | AI Job Protocol（AI 作业协议）—— 可调度的工作树与作业图 | aijp.dev |
| [AINP](https://ainp.dev) | AI Neogenesis Protocol（AI 创生协议）—— 可治理的生成项目：计划 + 内容 + 证据 | ainp.dev |
| [AILP](https://ailp.dev) | AI List Protocol —— agent 发现与能力广告 | ailp.dev |
| [AIVP](https://aivp.dev) | AI Value Protocol —— 国际商务、加密资产结算 | aivp.dev |
| [AIRP](https://airp.dev) | AI RMB Protocol —— 中国大陆商务、人民币持牌结算 | airp.dev |
| [AIBP](https://aibp.dev) | AI Bot Protocol —— 社交通信与信任 | aibp.dev |
| [AIAP](https://aiap.dev) | AI Application Protocol —— 治理与合规 | aiap.dev |
| [AISP](https://aisp.dev) | AI Skill Protocol —— 目录式技能包，以 AISOP 技能入口和可执行契约绑定为核心 | aisp.dev |
| [AISOP](https://aisop.dev) | AI Standard Operating Protocol —— 流程程序定义 | aisop.dev |
| [AIXPStore](https://aixpstore.dev) | AIAP 程序与 AISP 技能官方市场 —— 发现、发布和分发 AI 能力包 | aixpstore.dev |
| [SoulSkill](https://soulskill.dev) | AISP 技能参考库 & 多 CLI 插件分发 | soulskill.dev |
| [SoulAgent](https://soulagent.dev) | 任何 CLI / SDK / IDE 直接调用的 drop-in AI agent | soulagent.dev |
| [SoulBot](https://soulbot.dev) | AI agent 运行时 & 自编排框架（定时、建 agent、agent 间通信） | soulbot.dev |
| [SoulRun](https://soulrun.dev) | 一个调用的 AISOP 执行引擎 —— 为任何宿主运行 AIAP 程序与 AISP 技能 **（本项目）** | soulrun.dev |
| [SoulACP](https://soulacp.dev) | 适配库 —— 桥接 CLI 工具与 LLM 提供方 | soulacp.dev |

---

## ⚠️ 免责声明

本软件为**实验性**软件，仅供**研究和教育用途**。不适用于生产环境。使用风险由用户自行承担。作者对因使用本软件造成的任何损害不承担责任。完整条款见 [LICENSE](LICENSE)（Apache 2.0）。

---

## 许可证

[Apache License 2.0](LICENSE) - Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev

---

Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulRun V1.0.0. <www.soulrun.dev>

<a id="values-philosophy"></a>

## ⚓ 价值观与哲学 (Alignment & Philosophy)

### Axiom 0: [HSAW | Human Sovereignty and Wellbeing](https://hsaw.dev)

- **No HITL, HSAW.**
  *人类主权与福祉是第零公理，无需虚伪的人机协同。*
- **No w.a.s.h, Real h.s.a.w.**
- **人非蝼蚁，人为道。**
- **We are not beggars. We the People.**
