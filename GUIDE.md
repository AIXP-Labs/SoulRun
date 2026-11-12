# SoulRun 使用指南

> Python 3.11+ | 零依赖 | SoulRun V1.0.1，引擎 1.0.0 | 运行 AIAP 程序与 AISP 技能

当前1.0.1的已验范围、跳过、继承与未验项见[本地验收范围](README_CN.md#soulrun-101-本地验收范围)及[变更记录](CHANGELOG.md#101---unreleased)。
包仍未发布；S1按B保留未修。已有本机用户安装不代表生产升级，旧制品不含本次新文字。[1.0.0发布说明](docs/release-1.0.0.md)
只作未变内核的背景及带日期历史，不是1.0.1的新验收结论。

```bash
python -m pip install soulrun
soulrun
```

---

## 一、简介

SoulRun 是一个 Python 包：里面是 AISOP 执行引擎，前面只放一个调用：

```python
import soulrun

ctx = soulrun(user_message="用易经看一下这个月")
```

- **它做什么**：找到这句话所属的那一场运行，或者新准备一场；定下候选程序；判断不了人要什么时就问人；交回这一轮模型需要的全部文字。
- **它不做什么**：不调用模型、不打开网络连接、不改引擎、不替人回答任何问题。
- **谁来用**：任何能把一段文字送给模型、再把回答带回来的宿主——SoulBot、SoulAgent、一个脚本、一个终端会话。

和 README 的分工：README 讲 SoulRun 是什么、怎么开始；本指南把每个参数、每种返回、每个错误代码、每个宿主入口、每项自检都讲全。

---

## 二、项目结构

| 位置 | 是什么 |
|---|---|
| `src/soulrun/` | SoulRun 本身（`_api.py` 是那一个调用，`host.py` 是宿主入口，`cli.py` 是命令行，`_doctor.py` 是自检，`_program.py` 是 `soulrun --program`，`_report.py` 是 `soulrun --report`，`_launch.py` 是简装文字里写给模型的那条命令，`_slim.py` 按节点交引擎程序，`_screen.py` 是命令行上给人看的块，`_message_file.py` 收消息文件） |
| `src/soulrun/soulrun_aiap/` | SoulRun 的引擎：只有运行要用的文件，不手改 |
| `src/soulrun/engine_manifest.json` | 引擎的版本、每个文件的 SHA-256 和总摘要 |
| `src/soulrun/engine_node.aisop.json` | 生成的：按节点排好的引擎程序，以及哪一部分跟哪个节点交（简装形式用） |
| `src/soulrun/_agent_text.py` | 生成的：从 SoulBot 代理模板取出的固定文字 |
| `src/soulrun/guide.txt` | `soulrun()` 交回的使用说明，模型会话也会读 |
| `tools/` | 引擎清理、同步与换新、两个生成器（简装程序、固定文字）、安装包检查、文档检查、共用的隐私规则、PyPI 上的说明页、SoulBot 样本记录、CI 用的依赖清单 |
| `examples/` | 最小宿主、SoulACP「程序门」 |
| `docs/` | 文档地图、设计说明、SoulBot 接入指引、发布说明（`release-1.0.0.md`） |

---

## 三、安装

Python 3.11 及以上。两种方式任选：

```bash
python -m pip install soulrun                                          # 从 PyPI
python -m pip install "git+https://github.com/AIXP-Labs/SoulRun.git"   # 或者直接从 GitHub
```

装好以后核对：

```bash
soulrun --version                     # SoulRun 的版本号和带着的引擎的版本号
soulrun --verify-engine               # 装好的引擎就是记下的那一份
```

Windows 上用 python.org 的 Python 时再装时区数据：`python -m pip install tzdata`（见第十二节「time zones」）。要改 SoulRun 本身、
跑它的测试，在本仓库的一份检出里可编辑安装：`python -m pip install -e ".[dev]"`。构建安装包、装进干净环境、发布前的门禁，见
[INSTALL.md](INSTALL.md)。

---

## 四、快速开始

### 4.1 代理目录

SoulRun 从一个**代理目录**找程序：AIAP 程序包放在它下面的 `aiap/`，AISP 技能放在 `aisp/`。不指定时，代理目录就是当前目录。

```text
my_agent/
├── aiap/
│   └── soulbot_yijing_divination_aiap/
├── aisp/
└── .soulrun_cache/          # 第一次运行时由 SoulRun 建，放运行
```

### 4.2 一个宿主循环

```python
import soulrun
from soulrun import host

def one_turn(words: str, conversation: str) -> str:
    ctx = soulrun(user_message=words, session_id=conversation, agent_dir="my_agent")
    if ctx.doubt or ctx.kind == "guide":               # SoulRun 先问人（或使用说明）：原样给人看，不问模型
        return ctx.text
    reply = send_to_your_model(ctx.text + "\n\n" + words,   # program：模型驱动引擎；text_only：模型只回文字
                               system=ctx.system_prompt)    # 开场指令：放在宿主原来放自己开场指令的地方
    host.after_turn(ctx.cache_dir, reply)              # 每一轮之后都调，text_only 那一轮也调
    return host.expand_refs(reply, cache_dir=ctx.cache_dir)   # 给人看正文，不是引用
```

四条规矩：

- **给人看什么**：`ctx.doubt` 有值时的 `ctx.text`，以及展开引用以后的模型回答。`ctx.doubt` 没有值的 `text_only` 是给模型的指令
  （比如人按停止以后），交给模型，不给人看。
- **展开引用**：引擎让模型把门的菜单、节点的块、终答都写成一行 `⟦engine:<运行>/<文件>⟧`，从不写正文。给人看之前用
  `host.expand_refs` 换回正文；换不了的引用原样留着。
- **每一轮之后都调 `after_turn`**：它记下模型说了什么，并在回答里带着某个提问的菜单时登记「已送到」。停止、重启、断线、执行故障
  之后的提问，菜单没登记送到之前，引擎不收人的回答。运行里的门也一样：菜单还没写下（引擎的停门只在主对话取到它时才写，子代理碰到它、
  或者引擎在收答复时开出它，都不写；子代理停下的业务门，在主对话下一步取到它时才写——主对话在给人看这道门之前先取这一步，任何宿主
  都一样；宿主记下这个子代理交回（`host.observe_agent_return`）不写菜单、不算给人看过）、也没登记送到时，人的话不算回答，主对话下一步
  先把门给人看。人的话照 SoulBot 的做法另外送给
  模型；只有一条文字通道的宿主，把人的话接在 `ctx.text` 后面（上面和两个示例都是这样）。
- **开场指令用 `ctx.system_prompt`**：它和这一轮的程序形式配套（第十六节），宿主原来自己的开场指令换成它（SoulBot 的代理模板
  就是这样：有它就用它，没有时用自己那条只回文字的开场指令）。只有一条文字通道的宿主把它放在最前面（两个示例都是这样，SoulBot
  对不收开场指令的模型也是这样做的）。

不接模型的完整循环见 [`examples/minimal_host.py`](examples/minimal_host.py)；经 SoulACP 接真实命令行模型的见
[`examples/soulacp_host.py`](examples/soulacp_host.py)。

---

## 五、一个调用：参数与返回

`soulrun(...)` 和 `soulrun.run(...)` 是同一个函数。包带类型标注（`py.typed`）：不给 `cmd` 时返回 `Ctx`，给了返回 `CmdResult`。类型检查器认不出「模块可以调用」，做类型检查的宿主写 `from soulrun import run`。

包里另外给出：`soulrun.__version__`、`soulrun.ENGINE_VERSION`、`soulrun.engine_info()`（和 `soulrun --engine-info` 一样）、`soulrun.guide()`（使用说明的文字，和 `soulrun()` 交回的一样）、`soulrun.COMMANDS`（第十节的四个命令）、`soulrun.KINDS`、`soulrun.DEFAULT_SESSION`，以及错误类 `SoulRunError`、`UsageError`、`EngineUnavailable`（第十三节）；宿主入口在 `soulrun.host`（第十一节）。

### 5.1 参数

全部可以不给。设了但用不了的值会报错，SoulRun 从不悄悄退回默认值。参数的类型一开始就核对：`user_message` 不是文字（比如 bytes）、`session_id` 不是一行非空的文字、`host_tools` 的值不是 `True`／`False`、路径里有 NUL 等，都报 `ARGUMENT_TYPE`，什么都不新建。

| 参数 | 不给时 | 意思 |
|---|---|---|
| `user_message` | 没有话 | 用户这一轮说的话。开头的 BOM 会被去掉；只有空白也算没有话 |
| `session_id` | 一个代理目录算一个对话（第七节） | 这句话属于哪个对话；有对话的宿主应当总是给 |
| `cache_dir` | 由引擎去找这个对话的那一场 | 这句话是冲着哪一场说的；必须是这个对话没做完的那一场，否则 SoulRun 问人（`NAMED_RUN_MISMATCH`） |
| `agent_dir` | `SOULRUN_AGENT_DIR`，再没有就是当前目录 | 代理目录 |
| `aiap_dir`、`aisp_dir` | `agent_dir` 下面的 `aiap`、`aisp` | 放着很多程序的大目录 |
| `aiap`、`aisp` | 不指定 | 指定一个程序：目录路径（或它的入口文件），或者到大目录里按名字找 |
| `soulrun_cache_dir` | `SOULRUN_CACHE_DIR`，再没有就是 `<agent_dir>/.soulrun_cache` | 放运行的目录（第八节） |
| `user_id`、`channel`、`model` | 引擎的默认 | 宿主知道的用户、通道、模型。心跳轮次（`channel="heartbeat"`）不经过引擎，报 `HEARTBEAT_NOT_ENGINE` |
| `host_fences` | 引擎的默认 | 宿主会截取的流式文字种类 |
| `host_tools` | 引擎的默认：能派子代理 | 宿主有或没有的能力，例如 `{"agent": False}` 表示不能派子代理；照实说，不给就是说「能」 |
| `human_turn` | 是人说的 | 这句话不是人说的（比如定时任务）时给 `False`。不是人说的话不能回答等人回答的提问：这个对话最近一场停在门上（运行状态 `WAITING_USER`）时，报 `HUMAN_REPLY_REQUIRED`，那一场原样不动；运行状态是 `RUNNING` 时，停止、断线、重启等之后的提问由引擎把这句话记下、不执行（停在门上时按了停止，运行状态仍是 `WAITING_USER`，照上面报错）；引擎自己的停门刚写下、还没写进索引就中断的那一场，开关关着时也报 `HUMAN_REPLY_REQUIRED`，和停在那道门上一样，那一场原样不动（以宿主的接回标记开头、`cache_dir:` 写着同一个放运行的目录里这个对话的那一场的话照常交给引擎）；还标着 `RUNNING`、一时又读不了的那一场，开关关着时也这样拒绝（被杀掉的进程留下的运行锁，引擎两分钟后才回收；索引不认识、引擎也认不出的门记录） |
| `host_turn_id`、`origin_type` | 引擎的默认 | 宿主这一轮的编号、消息来源类型 |
| `slim_program` | 开（看环境变量，第十四节） | 简装形式（第十六节）；给 `False` 就是入口路径形式，也就是 SoulBot 的文字 |
| `inline_program` | 关（看环境变量，第十四节） | 试验性的第二步形式（第十六节），开了它就不用简装形式；不能和 `slim_program=True` 同时给。两个开关只收 `True`、`False` 或不给，别的值报 `SWITCH_INVALID` |
| `cmd` | — | 改为运行一个引擎命令（第十节）；不能和 `user_message` 同时给 |

### 5.2 返回的 `Ctx`

| 字段 | 意思 |
|---|---|
| `kind` | `"program"`（一场运行准备好了）、`"text_only"`（只回文字）、`"guide"`（使用说明）。中断后请人确认、取消这两种轮次也是 `text_only`：引擎只要一段文字回答；不论哪种程序形式，交给模型的都是上下文段、提醒段和只回文字的断言，不给入口段（第十六节） |
| `text` | 这一轮该交给模型的全部文字；疑惑时是给人的问题 |
| `blocks` | 同一段文字按块拆开，顺序不变 |
| `cache_dir` | 这一轮属于哪一场运行；使用说明和新建运行之前的疑惑没有 |
| `entry_mode` | 引擎把这句话当成了什么：`fresh`、`resume`、`recovery`、`terminal`……；SoulRun 自己的疑惑是 `soulrun_doubt` |
| `turn_id`、`session_id` | 引擎的 `turn_id`：就是这一场的编号（`cache_dir` 的最后一级），一场里每一轮都相同，不是这一轮自己的编号（宿主自己的编号是它传进来的 `host_turn_id`）；所属对话 |
| `program_form` | 这一轮用的程序形式：`slim`（默认）、`entry_path`、`full`；`text_only` 的轮次没有（`None`） |
| `system_prompt` | 和这一轮配套的开场指令：简装形式是 SoulRun 自己的，其余是 SoulBot 的原文。使用说明和新建运行之前的疑惑没有 |
| `slim_fallback` | 本该用简装形式、这一轮却没用时，写明原因（第十六节）；否则没有 |
| `program` | 程序作为文字交给模型时，已经填好用户的话的那份程序 |
| `doubt` | SoulRun 在新建运行之前要问人时有值（5.3） |
| `places` | 这一次用的 `agent_dir`、`aiap_dir`、`aisp_dir`、`soulrun_cache_dir`，以及各自从哪来（`sources`：参数、环境变量还是默认） |
| `data` | 引擎自己的回答，原样。它随引擎版本变，不在 SoulRun 版本号的承诺里（GOVERNANCE「Versioning」） |

`str(ctx)` 就是 `ctx.text`；`ctx.as_dict()` 给出 `kind`、`text`、`cache_dir`、`entry_mode`、`turn_id`、`session_id`，以及有值时的
`program_form`、`system_prompt`、`slim_fallback`、`doubt`：命令行 `--json` 打印的就是它（打印上限和另存的全文见第九节）。

### 5.3 SoulRun 自己的疑惑

下面几种情况，SoulRun 在新建任何运行之前就停下来问人：不运行任何程序、不新建运行，交回 `kind="text_only"`，`ctx.doubt` 有值。

| `ctx.doubt["code"]` | 什么时候 | 问的是什么 |
|---|---|---|
| `DESIGNATED_NOT_FOUND` | 指定的程序找不到 | 到哪里找过（`looked_in`）、大目录里有什么（`present`）、相近的建议（`recommendation`，不具约束力） |
| `WHICH_DESIGNATED_PROGRAM` | 没有话，却同时点名了 AIAP 程序和 AISP 技能 | 运行哪一个；没有话可以判断语言，所以中英两种文字都写 |
| `NAMED_RUN_MISMATCH` | `cache_dir` 不是这个对话没做完的那一场；或者话里的接回文字（`host.resume_prompt` 生成的）点名了别的对话的那一场 | 写明哪里对不上（`problems`）和是哪一种（`named_by`：`cache_dir` 或 `recovery_marker`）；接回文字那一种只能取消 |
| `DESIGNATED_RUN_UNFINISHED` | 点名了程序，而这个对话还有一场没做完、又不是为这个程序建的运行 | 那一场是哪一场、在等什么（`cache_dir`、`run_state`、`run_programs`）；可以把这句话交给那一场（有话时）、在另一个对话里运行点名的程序，或者取消 |
| `ENGINE_BUILD_MISMATCH` | 这个对话没做完的那一场不是现在这一份引擎构建开的：它记下的引擎摘要不同（哪怕版本号相同），或者没有记录（比如别的宿主开始的）。这一轮不交给引擎 | 那一场是哪一场、在等什么、两边的引擎版本和摘要（`cache_dir`、`run_state`、`run_engine_version`、`engine_version`、`recorded_digest`、`engine_digest`）；可以在另一个对话里发新的请求、先不处理；那一场的引擎版本号和现在的相同时（`endable` 为真）还可以回复「取消」结束它 |

不是人说的话（`human_turn=False`）遇到 `ENGINE_BUILD_MISMATCH` 的情况不问人，直接报同名错误。人回复引擎的一个取消词（「取消」「cancel」「stop」等）、
而那一场可以结束（`endable`）时，SoulRun 经引擎的 `terminate_run` 把那一场标成由人结束（不执行它的任何步骤），交回一条没有选项的说明
（`ctx.doubt["code"]` 是 `ENGINE_BUILD_RUN_ENDED`）：这是疑惑唯一会改动已有运行的地方。要接着跑那一场，回到开它的那个环境。

`ctx.doubt["options"]` 里每个选项都写明人选了它以后宿主该怎么做：

| `action` | 怎么做 |
|---|---|
| `call` | 用同一句话再调用一次，按 `arguments` 改参数：有值的换上，值为 `None` 的这次不带；`arguments` 里有 `user_message` 时，它就是这次要送的话（比如「取消」） |
| `ask` | 先要说出 `arguments` 里值为 `None` 的那一项（比如程序名、另一个对话的 `session_id`），说了以后带上它再调用 |
| `cancel` | 什么都不做 |

SoulRun 不记这个问题：谁把问题给人看，谁把人的回答带回来。

问题的文字只写相对代理目录的位置和程序名；本机的绝对路径（里面有系统用户名）、别的对话的编号只放在 `ctx.doubt` 里（`looked_in`、`owner_session_id` 等），给宿主看。疑惑的 `Ctx` 和其它回答一样带着 `places` 和 `session_id`。

---

## 六、选程序

参数只决定**候选有哪些**；用哪一个，由引擎的主程序按用户的话来判断，拿不准就开门问人。

| 给了什么 | 候选 |
|---|---|
| 什么都没给 | `aiap_dir` 和 `aisp_dir` 里的全部 |
| `aiap=` 或 `aisp=` | 就这一个 |
| 两个都给 | 就这两个 |
| 指定了，同时又给了大目录 | 只用指定的 |
| 指定的找不到 | 不运行，问人（`DESIGNATED_NOT_FOUND`） |

指定的程序就用指定的，绝不悄悄换成别的。这次没点名、而这个对话没做完的那一场当初是点名建的：引擎在这一轮里新建运行时（比如人停止以后选「作为新任务」），候选仍是那几个程序，新运行的记录里写着 `kept_from`（从哪一场带过来的）。

**登记脚本。** 代理目录的 `aiap/`、`aisp/` 里可以各放一个登记脚本（`aiap_list.py`、`aisp_list.py`），由它决定哪些程序是启用的。
引擎拿到代理目录时，会**用运行 SoulRun 的那个 Python 在每一场运行里执行它**，并改写旁边的 `aiap_list.json`／`aisp_list.json`；
所以代理目录里只放你信得过的登记脚本（`--doctor` 会列出来）。同一个程序目录不管怎么给都得到一样的候选：带登记脚本的程序目录只能经
它的代理目录用（`agent_dir`），单独当 `aiap_dir`／`aisp_dir` 给出时报 `REGISTRY_FOLDER_ALONE`——单独给出时引擎只会逐个扫描、
跳过登记脚本，被它停用的程序又会成为候选。点名一个程序（`aiap=`）是人自己的选择，不受这一条限制。`aiap_dir` 和 `aisp_dir` 给的是同一个
目录时，里面的程序只算一次。

### 6.1 没有用户的话时

| 情况 | 结果 |
|---|---|
| 没点名程序，或者只给了大目录 | 交回使用说明，不新建任何东西 |
| 点名了一个程序（`aiap=` 或 `aisp=`） | 用空消息运行它。不需要话的程序直接跑；需要话的程序经引擎的人类主权疑惑门问人。SoulRun 从不替人编话 |
| AIAP 程序和 AISP 技能都点名了 | 先问人运行哪一个（`WHICH_DESIGNATED_PROGRAM`） |
| 这个对话有一场没做完的运行，不是为点名的程序建的 | 点名的程序不开始，先问人（`DESIGNATED_RUN_UNFINISHED`，见 5.3）。有话时也一样 |
| 这个对话有一场没做完的运行，就是为点名的程序建的 | 交给引擎接着那一场：停在门上时，这次调用算对门的回答（没有话就是一次无效回答，门再摆一遍；那道门还没给人看过——菜单没写下、也没登记送到——时不算回答，不执行也不授权任何事（这一轮照常记进运行的记录），主对话下一步先给人看）；还在进行时，开关关着先问人要不要接着（`interrupted_confirm`；引擎自己的停门刚写下、还没写进索引就中断的那一场例外：直接接回，先给人看那道门），开关开着直接接回（`recovery`） |

定时任务、「运行这个程序」按钮这类宿主场景就用这种调用；人回答以后，回答作为一条普通消息回来（`user_message=回答`，不再带 `aiap=`）。
定时任务给 `human_turn=False`：这个对话最近一场停在门上（`WAITING_USER`）时，这样的调用报 `HUMAN_REPLY_REQUIRED`，门只由人回答。
引擎自己的停门刚写下、还没写进索引就中断的那一场，开关关着时也一样；还标着 `RUNNING`、一时又读不了的那一场（被杀掉的进程留下的
运行锁还在，或者有认不出的门记录）也一样。

---

## 七、对话与运行

- **对话**由 `session_id` 区分——这是宿主自己的概念，不是模型程序的会话。不给时一个代理目录算一个对话：代理用自己默认的放运行的目录时，对话名是 `default`；放运行的目录指定在别处（几个代理可能共用）时，对话名带上代理目录的指纹（`default-` 加 12 位），在一个项目里说的「继续」「取消」不会作用到另一个项目的运行。`ctx.session_id` 写明这次用的是哪个。
- **运行**是 `soulrun_cache_dir/.execution_cache/<N>/`。一句话进来时，引擎按对话找它没做完的那一场；`cache_dir=` 可以点名某一场，
  SoulRun 先核对它确实属于这个对话、确实没做完。
- **接着一场**：模型的回答停在一个问题上时，等人回答，再带着回答、同一个 `session_id` 调用一次。引擎会认出这是回答，接着同一场
  往下走。`cache_dir=` 只用来确认这句话是给那一场的：它必须是这个对话最近那一场没做完的运行，否则先问人。
- **停止**：人按停止时，宿主调 `host.stop(cache_dir, host_run_id)`，并结束正在进行的这一轮模型。下一句话进来时由引擎先处理停止：
  这一轮可能只回文字、不进程序（`text_only`，交给模型），也可能由模型开出停止的提问，由人决定接着上一场、作为新任务，还是结束
  上一场。提问的菜单经 `after_turn` 登记送到以后，人的回答才被收下。
- **一轮做完再来下一轮**：同一个对话，等上一轮做完（模型说完、`after_turn` 做完）再调下一轮；同时来的话由宿主排队。不排队时，同时来的第二句会被引擎当成「上一轮被打断」，几句里只留最后一句，两个模型会同时驱动同一场。不同的对话可以同时调用（11.3）。
- **换了 SoulRun 以后**：一场运行记着开始它的引擎构建（引擎摘要）。装上的 SoulRun 带的是另一份构建时，哪怕版本号相同，这个对话没做完的那一场也不再接着做：
  人说的下一句话先问人（`ENGINE_BUILD_MISMATCH`，5.3）。所以最好在没有运行等着时升级。

---

## 八、运行放在哪：`soulrun_cache_dir`

| 来源（按顺序） | 值 |
|---|---|
| 参数 `soulrun_cache_dir=`、命令行 `--soulrun-cache-dir` | 就是这个目录本身 |
| 环境变量 `SOULRUN_CACHE_DIR` | 同上 |
| 默认 | `<agent_dir>/.soulrun_cache` |

给的是相对路径时（参数或环境变量都一样），按**当前目录**解析，不按代理目录：同一个 `SOULRUN_CACHE_DIR=runs` 在不同的当前目录下
指的是不同的目录，也就是另一批运行。要固定就给绝对路径。`agent_dir`、`aiap_dir`、`aisp_dir` 的相对路径也一样按当前目录解析。

指定的目录必须是**新的、空的，或者本来就是 SoulRun 的**（里面有 `.soulrun`）。只有 `.gitignore` 或系统自己写的文件（`.DS_Store`、`desktop.ini`、`Thumbs.db`、`ehthumbs.db`、`.gitkeep`）也算空。第一次接管一个已有目录时，除了这些只许有 `.execution_cache`（从别的宿主带过来的运行）：

- 里面放着引擎程序（`python_tools` 或 `main.aisop.json`）→ `SOULRUN_CACHE_DIR_HOLDS_AN_ENGINE`（不管是不是第一次）：免得两个引擎共用一批运行。
- 已经放着别的文件 → `SOULRUN_CACHE_DIR_NOT_EMPTY`，报错里列出挡住的文件名：误把项目目录、留作证据的运行副本指进来时，用户的话会混进别的文件里，最旧的运行还会被轮换删掉。
- 不是目录、或创建/检查时捕获到文件系统异常 → `SOULRUN_CACHE_DIR_INVALID`。后续某个工具写入失败的错误由该操作决定，不保证总是同一码。

SoulRun 新建这个目录、或第一次接管一个目录（里面还没有 `.soulrun`）而它没有 `.gitignore` 时，尝试写进一个忽略整个目录的 `.gitignore`
（两行说明和一行 `*`）：上一次调用建好目录就被打断、或者手工建的空目录，也会尝试补上。写入是尽力而为，须实际核对文件存在，不能用创建返回
成功推断后续可写。之后它就归你：你改掉或删掉 `.gitignore`，SoulRun不再动它。新建时在Linux、macOS上限制为所有者权限700，`--doctor`
发现别的用户可访问时提醒。Windows上保留`0o700`；现代Python可生成受保护DACL，受限令牌可能无法使用。1.0.1不自动继承父ACL，问题尚未修复，
不改已有权限；预建目录也须核对宿主许可及实际隐私边界。详见[Windows运行目录权限](README_CN.md#windows运行目录权限)。
新建运行之前就要问人时（5.3），不新建这个目录；目录已经在时，多出来的最多是准备运行时加锁用的 `.soulrun/prepare.lock`（加锁以后才问的
`NAMED_RUN_MISMATCH`、`DESIGNATED_RUN_UNFINISHED`、`ENGINE_BUILD_MISMATCH`，以及非人回合在这里被拒绝的 `ENGINE_BUILD_MISMATCH` 错误，会留下它），
和第一次接管时写的 `.gitignore`（加锁之前就写好了）。里面的内容见 README_CN 的「程序和数据是分开的」。
删掉它就删掉了所有运行，包括没跑完的。

---

## 九、命令行

本节标为`bash`的输入重定向/环境变量示例不能原样当PowerShell执行；Windows优先用`--user-message-file`保留原始文件字节。
带引号的解释器路径用`&`调用，示例见[INSTALL第3.1节](INSTALL.md#31-powershell与解释器选择)。

```bash
soulrun                                              # 使用说明
soulrun --user-message-file msg.txt                  # 打印应当交给模型的文字（'-' 表示读标准输入）；msg.txt 收进这场运行
soulrun --user-message-file msg.txt --keep-message-file   # 同上，msg.txt 留在原处
soulrun --user-message-stdin --json < msg.txt        # 改为打印一个 JSON 对象
soulrun --cmd next-node --cache-dir <目录>            # 运行一个引擎命令
soulrun --program --cache-dir <目录> [--node 节点 | --field 字段]   # 这场运行绑定的业务程序（JSON）
soulrun --report <链接> --cache-dir <目录>                         # 执行报告链接后面的完整报告（JSON）
soulrun --engine-node <名字> [--cache-dir <目录>]                   # 按需打印简装引擎程序的某一部分
soulrun --expand <引用> --cache-dir <目录>                          # 一块给人看的内容的正文
soulrun --version | --engine-info | --verify-engine | --doctor
```

其余选项和 Python 参数一一对应：`--aiap-dir`、`--aisp-dir`、`--aiap`、`--aisp`、`--agent-dir`、`--soulrun-cache-dir`、`--session-id`、
`--cache-dir`、`--user-id`、`--channel`、`--model`、`--host-fence KIND`（可重复）、`--host-tool NAME=true|false`（可重复）、
`--machine-turn`（等于 `human_turn=False`）、`--host-turn-id`、`--origin-type`、`--slim-program`／`--no-slim-program`、`--inline-program`。

- 用户的话只从文件或标准输入读，不写在命令行上（不会出现在进程列表和 shell 历史里）。
- 这一轮有了运行以后，`--user-message-file` 指的文件被挪进那一场的运行目录：`<运行>/_soulrun/message.<n>.txt`（引擎不读这个子目录，
  删掉这一场时一起删），用户的话不留在项目里。`--keep-message-file` 留在原处；标准输入（`-`）没有文件可挪；没有运行的一轮（使用说明、
  还没开始运行就要问人的问题）也留在原处，因为回答时选项会用同一个文件再调一次。文件所在的文件夹不动（agent 下一轮常往同一处写）。
  文件写在一个新的放运行的目录里、是那里唯一的东西时，先挪开再检查这个目录，不报 `SOULRUN_CACHE_DIR_NOT_EMPTY`。
- `--cmd=名字` 也可以。选项不认缩写：写成 `--cm` 会报错，不会被悄悄当成别的调用。
- 用户的话的文件：UTF-8，或者带 BOM 的 UTF-16（Windows PowerShell 5.1 用 `>`、`Out-File` 写出的就是这种）；别的编码报 `MESSAGE_NOT_UTF8`，不去猜。PowerShell 5.1 的管道会把中文换成 `?`，请写成文件，或用 PowerShell 7。
- 有运行的一轮，打印的整轮文字另存一份在 `soulrun_cache_dir/.soulrun/entries/<N>.txt`（`--json` 的 `full_text_file` 写着它；存不下时照样打印，只是少了这个文件）。
- 打印的文字守 29,000 字节的上限（命令行工具会截掉超出的部分）：超了时，简装形式的一轮改按入口路径形式打印（`--json` 的
  `program_form` 写 `entry_path`、`slim_fallback` 写 `TOO_LONG_FOR_COMMAND_LINE`，`system_prompt` 也换成配套的那一份），第二步形式
  把程序块换成一行说明；还超，就把过长的数据行（比如很长的原话）截短，并写明全文在哪个文件。说明指令的行一行不截。
- `--program`（要带 `--cache-dir`）把这场运行绑定的业务程序以 JSON 打印出来，只读、不改运行：不带别的选项时是概要（主图、主图的
  节点、入口和终点节点、程序里的文件，程序的 `system_prompt`、`output_mode`、`tools`、`params` 全文，AIAP.md 的名字、版本、信任级别、
  权限和运行时；其余字段里 200 字符以上的给出大小和指纹，值得用 `--field` 取，更小的只列名字）；`--node 节点` 是这个节点的 function、它点名的 tools 和工具入口、它引用的共同约束；`--field 字段`
  是任意一个字段的全文，长的用 `--offset`、`--limit` 分页（一页最多 12,000 字符，同时不超过 24,000 字节，所以中文一页约 8,000 字，
  打印出来总在上限以内；接着取用回答里的 `next_offset`）；程序有好几个文件、节点同名时用 `--doc` 指定。不是字符串的字段按引擎
  的写法（紧凑 JSON）计，所以大小和指纹与引擎回复里 `program_contracts` 报的一致，同样的 `--offset`、`--limit` 取到的文字也和
  引擎 `--read-program-contract` 的一样。简装形式的入口段就是这样教模型取程序的；引擎回复里 `program_contracts` 点名的程序约定，
  入口段让模型用引擎自己的 `--read-program-contract` 取。
  `--node`、`--field` 等不跟 `--program` 一起用时报 `PROGRAM_OPTION_ALONE`。
- `--report <链接>` 打印执行报告块末尾那个 `engine-report:` 链接后面的完整执行报告（JSON），和 `host.execution_report` 一样：
  先核对报告属于这场运行（执行报告节点的记录与运行索引一致、记录里写的就是这个指纹）、文件的指纹对得上，再交出；交不出时
  `status` 写明原因（`CACHE_EXPIRED`、`NOT_IN_SESSION`、`REPORT_UNBOUND`、`REPORT_FILE_MISSING`、`REPORT_DIGEST_MISMATCH`、
  `REPORT_UNREADABLE`）。放运行的目录由 `--cache-dir`（这段对话的任意一场）或 `--soulrun-cache-dir`、`--agent-dir` 给出；
  `--session-id` 只认这段对话的运行。长的用 `--offset`、`--limit` 分页（不给 `--limit` 时一页 16,384 字符，最多 32,768 字符，同时不超过
  24,000 字节）。只读。
- `--expand <引用>`（可重复，要带 `--cache-dir`）打印一块给人看的内容的正文：计划、节点块、门的菜单、终答、证据，写法照引擎的引用行
  `⟦engine:<运行>/<文件>⟧`。长的用 `--offset` 分页（一页不超过 24,000 字节）。引用指的不是这批运行里的公开块时报 `EXPAND_REF_UNKNOWN`，
  不带 `--cache-dir` 报 `CACHE_DIR_REQUIRED`。
- 在命令行上打印的一轮（不带 `--json`），SoulRun 和模型之间没有宿主程序，模型自己要把给人看的块打印到屏幕上：打印的文字里多一段
  `[SOULRUN SCREEN]`，断言里多一行 `SCREEN=…`；之后每条引擎命令（`--cmd`，给了这场的 `--cache-dir`）的输出里，按节点交的那部分后面
  再跟上 `[SOULRUN FOR THE HUMAN]` 和这条回复点名的块的正文（每轮每块一次，内容一样的只给一次）。放不下的块顺延到后面有空间的回复，
  并打印一行说明和 `--expand` 的取法。`--json`、Python 调用和 SoulBot 这类宿主程序不加这些：宿主自己展开引用行。
- `--engine-node <名字>`（可重复）打印简装引擎程序的一部分（第十六节）：名字是一组（`entry`、`Router.match`、`business`、
  `dispatch` 等）、主程序 system 里的一段（比如 `node_execution_contract`），或一个函数（比如 `NodeLoop`）。给了一场简装
  运行的 `--cache-dir` 时，记为这一轮已经给过。始终不交的部分（`tools`、`json_schema`、子代理的那份）和不认识的名字报
  `ENGINE_NODE_UNKNOWN`，写明能给哪些组。
- 返回值：`0` 成功（使用说明、一场运行、给人的一个问题都算成功）；`2` 用法不对；`1` 其它错误（包括 `--verify-engine` 查出问题、`--doctor`
  有 `FAIL`）。`--cmd` 时工具运行了的话，退出码是工具自己的（例外见第十节）。`--json` 时错误（包括参数写错）以一个 JSON 对象（`{"error": {...}}`）打印到
  标准错误，`--version`、`--verify-engine`、`--doctor` 也改为打印 JSON；`--engine-info` 总是打印 JSON。

---

## 十、引擎命令

```python
soulrun(cmd="next-node", cache_dir=...)                       # 现在该做的节点
soulrun(cmd="node-commit", cache_dir=..., node="...", payload={...})
```

| 命令 | 谁用 | 做什么 |
|---|---|---|
| `next-node` | 模型，每一步 | 拿到现在该做的节点 |
| `node-commit` | 模型，每一步 | 交回这个节点的结果；引擎核对后放行或者退回并说明原因 |
| `stop-decision` | 模型 | 人按停止以后，模型对停止的判断 |
| `gate-answer` | 宿主 | 宿主一侧记下人对门的回答（人的回答通常作为 `user_message` 回来，用不着它） |

`cmd=` 返回 `CmdResult`；命令行里 `--cmd 名字` 以外的参数（写在它前面后面都一样）原样交给引擎的工具，输出和退出码也是那个工具的。`cmd=` 时 SoulRun 自己的参数（`session_id`、`agent_dir`、`aiap` 等）不会转给引擎，给了就报 `ARGUMENT_NOT_FOR_CMD`：命令自己的选项写成关键字参数（`node=...`），和 SoulRun 参数同名的（比如 `--session-id`）放进 `args=[...]`。入口路径形式交给模型的文字按路径写引擎的脚本；简装形式
让模型写 `"<python>" "<包>/_launch.py" --cmd 名字`，也就是这里的命令行（解释器和启动文件都写完整路径，不靠模型的 shell 自己的
`python`）。几种写法运行的是同一份代码。

- 命令行里、简装形式的一轮中（给了 `--cache-dir`，写成 `--cache-dir 目录` 或 `--cache-dir=目录` 都行，这场运行这一轮是按简装形式交的），
  引擎工具的输出原样先打印，后面再跟上这一步要用、这一轮还没给过的那部分引擎程序：一个空行、`[SOULRUN ENGINE NODE: <组名>]` 一行说明，
  和一段 JSON 代码块（第十六节）；附上会超过打印上限时只有那一行，写明取它的 `--engine-node` 命令。所以要解析输出的程序只取开头的
  那个 JSON（Python 用 `json.JSONDecoder().raw_decode`）。输出不是一条
  为节点服务的引擎回复（参数被工具拒绝、只读的查询）、或者没有要补的部分时，什么都不加；子代理的命令（带 `--agent-ticket`）也什么都
  不加、不记，因为子代理用的是引擎给子代理的那份程序。工具运行了的话，退出码是工具自己的（只有下一条一种例外）；SoulRun 在工具运行
  之前就拒绝的用法（`UNKNOWN_CMD`、`CMD_NAME_MISSING`、`MESSAGE_AND_CMD`）以 `2` 结束。`cmd=` 返回的 `CmdResult`
  （`cmd`、`returncode`、`stdout`、`stderr`、`ok`）只有回复本身。
- 给了 `--cache-dir` 的引擎命令（子代理的命令除外），回复由 SoulRun 转印。读输出的一方已经走了（管道关了）、回复打印不出来时，SoulRun
  在标准错误上打一行 `SOULRUN_REPLY_NOT_PRINTED`、尽量记进 `<soulrun_cache_dir>/.soulrun/undelivered/<运行>.jsonl`，以退出码 `74` 结束，
  不出 traceback；
  引擎自己已经把回复存在那一场的 `_work/replies/` 里。
- `CmdResult.json()` 在引擎工具没有打印 JSON 时（参数被它拒绝、中途出错）报 `CMD_OUTPUT_NOT_JSON`，写明退出码和标准错误的最后一行；
  给了 `timeout=` 而工具没按时结束，工具被停下并报 `CMD_TIMEOUT`。
- `gate-answer` 的 `answer=`（人的回答）不会出现在命令行上：SoulRun 把它写进一个只有自己能读的临时文件、以 `--answer-file` 交给工具，
  用完就删。直接在命令行上用 `--cmd gate-answer` 时，也请用 `--answer-file`。
- 命令行里的 `--json` 只管 SoulRun 自己的错误以 JSON 报出，不转给不认它的工具（只有 `next-node` 认它，它本来就打印 JSON）。

---

## 十一、给宿主用的入口（`soulrun.host`）

| 入口 | 用途 |
|---|---|
| `expand_refs(text, *, cache_dir=None, soulrun_cache_dir=None, agent_dir=None)` | 给人看的回答：把 `⟦engine:…⟧` 引用换回公开块的正文；只读引用点名的那一场 `_public/` 里的公开块，换不了的原样留着 |
| `after_turn(cache_dir, public_text, *, response_persisted=True, **details)` | 每一轮之后（`text_only` 那一轮也是）：回答里带着某个提问的菜单时登记已送到，记下模型说了什么，以及宿主已经存好；`public_text` 是模型原样的回答或展开后的，都认。返回 `question_delivered`、`observed`、`finalized`、`run_state` |
| `observe(cache_dir, public_text, **details)`、`finalize(cache_dir, response_persisted=True)` | `after_turn` 后两步，给要分开调用的宿主（它们不登记菜单送到） |
| `stop(cache_dir, host_run_id, *, session_id=None)` | 人按了停止：记进那一场，模型的下一条引擎命令被拒；正在进行的这一轮模型由宿主自己结束 |
| `open_question(cache_dir)` | 一场运行在模型之外等着人回答的提问（停止、断线、重启、执行故障之后）：`question_id`、`stop_id`、`source`、`text`（给人的菜单）、`reference`、`delivered`；没有就是 `None` |
| `mark_question_delivered(cache_dir, question_id=None)` | 宿主自己把那个提问给人看了（比如重启之后），登记已送到；引擎答 `DELIVERED`、`ALREADY_DELIVERED`、`NOT_GATED`，`question_id` 不是那个提问时答对不上 |
| `interrupted_runs(*, soulrun_cache_dir=None, agent_dir=None, created_before=None)` | 重启之后：还标着在跑（RUNNING）的运行；`created_before` 给这个宿主进程启动的时间（ISO，带 Z），排除它自己开始的运行 |
| `mark_interrupted(cache_dir, reason="host restart")` | 在那一场自己的记录里记下宿主发现它被打断（运行状态不变） |
| `open_restart_question(cache_dir, *, instance_started_at, resume_mode=None)` | 重启之后、开关关着：把这一场标成被打断，并开一个问人的提问，而不是接回（`status` 是 `OPENED`、`ALREADY_OPEN`，或 `SKIPPED` 并写明原因：开关开着时什么都不写；那一场不在跑、索引读不了、不是引擎的运行、是这个进程启动以后才建的，也跳过；引擎自己的停门刚写下、还没写进索引就中断的那一场也跳过，什么都不写——人下一句话进来时接着这一场，先给人看那道门） |
| `resume_prompt(cache_dir, error_code="HOST_RESTART")` | 开关开着时接回一场用的文字（工具路径已指向包里的引擎），那一场不在跑时是 `None`；只在那一场自己的对话里有效 |
| `resume_interrupted_enabled()` | 读 `SOULBOT_RESUME_INTERRUPTED_RUNS`：重启后是自动接回（开），还是停下问人（关，默认） |
| `RecoveryRequest(phase, session_id, error_code, …)` | 模型断线时交给引擎的事实：`phase` 是 `plan`、`start`、`complete`、`cancel`、`delivered` 之一 |
| `runner_recovery(request, *, soulrun_cache_dir=None, agent_dir=None, resume_mode=None)` | 模型断线之后：引擎的决定；`request` 是 `RecoveryRequest`、它的字段组成的字典，或带这些字段的对象；`phase` 不对或缺 `session_id` 报 `RECOVERY_REQUEST_INVALID` |
| `latest_run(session_id, *, soulrun_cache_dir=None, agent_dir=None)` | 这个对话最近的一场 |
| `soulrun_cache_dir(*, soulrun_cache_dir=None, agent_dir=None)` | 代理的运行放在哪 |
| `cache_root(*, soulrun_cache_dir=None, agent_dir=None)` | 其中的 `.execution_cache` |
| `program_root()` | 包里的引擎程序目录（引擎的工具在这里） |
| `system_prompt(form="slim")` | 某种程序形式（`slim`、`entry_path`、`full`）的开场指令，不用先调用；别的值报 `PROGRAM_FORM_UNKNOWN` |
| `project_slim_policy(system_prompt, *, cache_dir, entry_mode)` | 只读：把一段带简装程序的文字里每轮不同的那一块换成一个固定记号，给要比较各轮指令是否相同的宿主用（11.5）。第一个参数名叫 `system_prompt`，要传的却是带着程序块的整段文字、含 `ctx.text`；只传 `ctx.system_prompt` 得到 `None` |
| `program_view(cache_dir, *, node=None, field=None, doc=None, offset=0, limit=None)` | `soulrun --program` 打印的内容，作为字典（第九节） |
| `execution_report(link, *, cache_dir=None, soulrun_cache_dir=None, agent_dir=None, session_id=None, offset=0, limit=None)` | 执行报告链接后面的完整报告，作为字典（第九节）；SoulBot 的网页自己打开这种链接，别的宿主用它 |
| `engine(name)` | 任意一个引擎模块，给已经按名字调用它的宿主用 |
| `dispatches_nodes(index)` | 这一场是不是节点式、把节点派给子代理（`index` 是读到的 `_index.json`）；是的时候下面这些报告才对得上（11.4） |
| `observe_agent_start(cache_dir, bootstrap_sha256, *, session_id, tool_call_id, event_id, at, resume_agent_id=None, policy_ref=None)` | 模型开了一个同步子代理（Agent/Task 调用，或接回 `resume_agent_id` 的 SendMessage）：调用一出现就报，`bootstrap_sha256` 是它的 prompt 的 SHA-256；回答 START_BOUND 时带票号 |
| `observe_agent_return(cache_dir, ticket, *, session_id, tool_call_id, event_id, at, status, agent_id=None, completion_tool_call_id=None, observation=None)` | 这个调用结束了（`status` 是 completed 或 failed，照工具报的） |
| `observe_agent_task_event(cache_dir, *, session_id, agent_id, tool_call_id, event_id, at, event_type, status=None)` | 接回的子代理，SDK 自己的任务事件（task_started、task_notification），只从 SDK 的通道来，不从模型的文字来 |
| `observe_resume_failure(cache_dir, ticket, *, session_id, agent_id, tool_call_id, event_id, at)` | 接回子代理的 SendMessage 失败了：只说消息没送到，不说子代理结束了 |
| `observe_tool_request(...)`、`observe_tool_result(...)`、`resolve_tool_parent(...)` | 子代理发出的工具调用（SDK 挂在父调用下面报）：待执行时、结束时；接回的子代理原来的父调用 |
| `resumed_agent_start(cache_dir, *, session_id, agent_id, bootstrap_sha256)`、`parent_policy_ref(cache_dir, session_id)` | 只读：已报过的接回开始（只从后来的 TaskOutput 看到结束时用）；主会话的策略标记 |

这些入口都不新建放运行的目录：问一个从没跑过的代理，什么都不会留下（目录在第一次运行时才建）。以前把引擎放在每个代理目录里的宿主：凡是用「代理的引擎文件夹」指运行
的地方，换成 `soulrun_cache_dir(...)`；指引擎的工具的地方，换成 `program_root()`。宿主里所有找运行的地方都必须问 SoulRun，
不能写死目录名。SoulBot 现在怎样接 SoulRun、宿主要守哪几条，见 [docs/guide/02-soulbot-integration.md](docs/guide/02-soulbot-integration.md)；
其中一处是开场指令用 `ctx.system_prompt`。

### 11.1 重启之后

由人的设置决定（`resume_interrupted_enabled()`；不设就是停下问人）。对 `interrupted_runs(created_before=…)` 里的每一场：

1. 被停过的（`row["stopped"]` 为真）交给人：它的提问 `row["question"]` 从没送到过时，把 `open_question(cache_dir)["text"]` 在那一场的
   对话里再给人看一次，调 `mark_question_delivered(cache_dir)`。
2. 开关关着：调 `open_restart_question(cache_dir, instance_started_at=…)`；结果是 OPENED 时，把 `open_question(cache_dir)["text"]` 在那一场的
   对话里给人看，再调 `mark_question_delivered(cache_dir)`。人的回答之后作为普通消息经 `soulrun(...)` 进来。结果是 SKIPPED 时没有要给人看的
   （比如引擎自己的停门刚写下、还没写进索引就中断的那一场：人下一句话进来时接着这一场，先给人看那道门）。
3. 开关开着：`mark_interrupted(cache_dir)`，再把 `resume_prompt(cache_dir)` 经
   `soulrun(user_message=…, session_id=<那一场的>, origin_type="engine_recovery", human_turn=False)` 送进去。

接回的文字只在那一场自己的对话里有效：别的对话发同样的文字，SoulRun 先问人（`NAMED_RUN_MISMATCH`），不接回。

### 11.2 模型断线

1. 发 `RecoveryRequest(phase="plan", session_id=…, error_code=…)`，得到引擎的决定（`action`）。
2. `resume`：等 `delay_seconds` 秒，发 `phase="start"`（带上决定里的 `recovery_token`），把决定里的 `prompt` 交给模型；这一轮结束后发
   `phase="complete"`，被取消时发 `phase="cancel"`。
3. `ask`（开关关着）：把 `public_text`（展开引用以后）给人看，再发 `phase="delivered"`；人的回答作为普通消息进来。
4. `wait`、`hold`（开关开着）：有 `public_text` 就给人看，过 `next_probe_seconds` 秒再试（`None` 表示不再试）。
5. `stop`、`completed`：不用再做什么（`stop` 有 `public_text` 时给人看）。

### 11.3 同时调用

很多对话可以同时调用：准备运行时在进程内加锁，并在 `soulrun_cache_dir/.soulrun/prepare.lock` 上加操作系统的文件锁，几个进程也不会
拿到同一个运行编号。等锁超过 120 秒报 `PREPARE_BUSY`。

### 11.4 子代理：诊断报告与人裁交接

节点式的运行把节点派给子代理。宿主可记录它看到的工具事件，但本轮所有报告来源都未获身份资格：报告、调用编号、票号和会话日志
本身均不能证明是原子代理，也不能授予新单。以下入口保留作诊断，不代表已认证：

1. 同步的 Agent/Task 调用、或接回子代理的 SendMessage 一出现：`observe_agent_start`；回答里的票号留着。
2. 这个调用结束：`observe_agent_return`；只从后来的 TaskOutput 看到结束时，先用 `resumed_agent_start` 找回那次开始。引擎记下交回，
   但不写业务门菜单、不算给人看过。返回时的已接受块证明与菜单送达分开；给没给人看过由 SoulRun 自己判定：
   契约规定主对话在给人看这道门之前先取一次下一步，那一步写出菜单并把门交给主对话，任何宿主（包括看不到工具调用、什么都不报的
   宿主）都一样。首次题面可显名合并业务选择与新代理授权，但不保证所有情况只答一次。
3. 接回的子代理，SDK 的任务事件：`observe_agent_task_event`；接回用的 SendMessage 失败：`observe_resume_failure`。
4. 子代理发出的工具调用：待执行时 `observe_tool_request`，结束时 `observe_tool_result`；接回的子代理的调用挂在原来的父调用下，
   用 `resolve_tool_parent` 认出来。只记录，不授予任何权限。

每个报告带 `event_id`（每次不同）和 `at`（ISO 时间）；`session_id` 是发出调用的那个模型会话。每个入口原样转给说明里写的那个引擎函数，
这些函数在 `soulrun --doctor` 的 `engine interface` 和换引擎工具里核对：换进来的引擎改了名，在用到之前就报出来。看不到工具调用的宿主
（只用命令行）可以不报告。所有宿主在身份未证实时都问人是否授权新代理按已记录的未完成工作继续。
第一次未展示的业务门直接列出联合选项；暂停查证不答业务门、不派代理，业务拒绝不改成整场终止。
只有 `execute` 选项附换人授权；`cancel`、`terminate` 保留原种类和原标签，不发新票、不授权新代理。
「不导出但继续完成报告」是否属于执行选择，以当前题面、原选项种类及已接受原答为准，不凭否定词猜测。
普通门已答后失联、旧题面缺少换人说明、交回无业务门或授权不清楚时，另开换人门。
先封住旧派工单，用户答复前不发新单；封权不证明旧进程退出，未知外部结果先核对、不重做。
不同有效检查点的交接从已领取历史单独计数，同一进度的重复失败仍最多两次。报告口及权威状态写域的保护资格另外交审。

### 11.5 比较各轮指令：`project_slim_policy`

简装形式每轮交给模型的程序块（`[LOADED AISOP: engine_node.aisop.json]` 下面那一段）每轮都不一样：里面有用户这一轮的话，接回的轮次还多一组。
宿主要判断前后两轮的指令是否相同时（SoulBot 的发送层就这样比较同一场的两轮），调用
`host.project_slim_policy(text, cache_dir=ctx.cache_dir, entry_mode=ctx.entry_mode)`；`text` 是宿主交给模型的、带着这个程序块的整段文字。

- 它按 `entry_mode` 和程序块里用户的话，用装好的这份 SoulRun 逐字重新组装出这一块，和文字里的那一块比对，并核对引擎文件和清单一致。
- 对得上时返回三项：`policy_text`（整段文字，只把这一块换成一个带 `source_digest` 的固定记号，其余逐字不变）；`source_digest`
  （简装程序文件 `engine_node.aisop.json`、组装它的 `_slim.py`、简装文字所在的 `_blocks.py`、实现这个入口的 `_policy.py`，加上引擎清单的总摘要，合起来的摘要）；
  `runtime_fragment`（原样的那一块）。
- 文字里没有这一块或不止一块、内容被改过、`entry_mode` 不对、引擎文件和清单对不上：都返回 `None`，不做模糊匹配。
- `policy_text` 只拿来比较，不能代替原文交给模型：这一轮仍要把原样的 `runtime_fragment` 照常交给模型。
- 它只读、不授权任何事：能不能沿用一个模型会话、子代理的开始和返回算不算数，仍由宿主和引擎各自核对（11.4）。

---

## 十二、自检：`soulrun --doctor`

```bash
soulrun --doctor [--agent-dir DIR] [--aiap-dir DIR] [--aisp-dir DIR] [--aiap NAME] [--aisp NAME] [--soulrun-cache-dir DIR]
                 [--slim-program | --no-slim-program] [--inline-program] [--json]
```

每项一行，`OK`、`WARN` 或 `FAIL`，按下表的顺序，最后一行是 `all checks passed` 或几项失败；`--json` 时是一个 JSON 对象
（`ok` 和 `checks`，每项 `status`、`name`、`detail`）。有 `FAIL` 时返回 `1`，只有 `WARN` 不算失败。它不留下任何东西，也不运行任何程序自己的脚本。用的目录、点名的程序和程序形式的开关（`--slim-program`、`--no-slim-program`、`--inline-program`），和同样参数的一次运行一样；和 `--version` 等别的模式、或用户的话同时给时报 `MODES_CONFLICT`。每一项各自兜住错误：清单坏了、简装程序缺了、目录读不了，都报成那一项的 `FAIL`，不会整个崩掉；引擎本身读不了时只报这一行。

| 检查 | 看什么 |
|---|---|
| `versions` | SoulRun 和引擎的版本号 |
| `engine files` | 装好的引擎文件和清单是否一致 |
| `slim program` | `engine_node.aisop.json` 是否由这份引擎生成 |
| `engine interface` | SoulRun 调用的引擎函数和常量还在不在、参数还收不收（读引擎本身，不运行它）；换进了不配套的引擎时 `FAIL` |
| `python for the model` | 模型的命令行找到的 `python`：能不能启动、能不能载入引擎的工具。只认 `python`：入口路径形式下的每个引擎工具、不管哪种形式下子代理的引擎工具（`python <引擎目录>/python_tools/...`）、不管哪种形式下程序自己写成 `python ...` 的工具，都用它运行（只有简装形式的主对话写的是运行 SoulRun 的解释器的完整路径，不靠它）。找不到 `python`（只有 `python3` 也算）时，不管哪种形式都 `FAIL`，并写明哪些运行要它；Windows 上找到的 `python` 就在当前目录时不运行它，只提醒 |
| `time zones` | 这个 Python 和模型用的 python 能不能读具名时区；不能时 `WARN`：引擎会把服务商点名时区的额度恢复时间按本机时区算 |
| `program form` | 按程序形式的开关，运行会用哪种程序形式（默认简装，并写出交给模型的那条命令）：和一次运行一样，给了 `--slim-program`、`--no-slim-program`、`--inline-program` 就照它们，没给的看环境变量，并写出是哪个开关定的、从哪来（参数还是环境变量；一个开关都没给时才写 `the default`）；简装程序做不出来时 `WARN`（每场都会退回入口路径形式）；开关值写错、两个冲突时 `FAIL` |
| `engine settings` | 引擎自己读的环境变量（第十四节下表），按引擎的读法报出各自的效果；值引擎用不了、会悄悄退回默认时 `WARN`，引擎因此载入不了时 `FAIL` |
| `agent folder`、`programs` | 代理目录从哪来、里面有几个程序（往子层里也找）；一个程序都没有、或点名的程序找不到时 `FAIL`。放运行的目录有问题时这两项照样检查 |
| `misplaced programs` | 放错文件夹的程序（技能放在 `aiap/` 下等）：在那里不是候选 |
| `registry scripts` | 代理目录里的登记脚本：每场运行都会被执行（用运行 SoulRun 的 Python），只列出、不运行；单独给出带登记脚本的程序目录时 `FAIL`（第六节） |
| `path length` | 只在 Windows：一场运行最深的文件约多长（按 Windows 的算法数字符；按找到的程序和引擎自己的节点里最长的节点名算，写出是哪个节点：程序的节点名都短时是引擎的 `Engine.execute-report`，场号三位数时 130；读不到程序的节点名时按 150 算）；没打开长路径支持而达到 260 字符时提醒，并写出放运行的目录最长可以多长（这个上限含结尾的一个空字符，能用的最长是 259） |
| `soulrun_cache_dir` | 放运行的目录从哪来、能不能写（真的建一个文件试写、马上删掉）、留着几场；写不进、或会被拒绝（第八节）时 `FAIL`，这时没有上面 `path length` 那一行 |
| `version control` | 放运行的目录没有 `.gitignore` 时提醒 |
| `permissions` | 只在 Linux、macOS：放运行的目录别的用户也能打开时提醒（运行数据里有用户的话） |
| `unfinished runs` | 没跑完的运行：还在跑，或被重启打断 |

---

## 十三、错误代码

SoulRun 抛出的错误都是 `soulrun.SoulRunError`（用法错误是它的子类 `UsageError`，引擎不可用是 `EngineUnavailable`），带固定的 `code`、
不对的那一项 `field` 和应当是什么 `expected`。引擎抛的错误也转成 `SoulRunError`：`code` 是引擎自己的代码（比如 `RUN_ENGINE_VERSION_MISMATCH`），原来的错误在 `__cause__`。错误可以在进程之间传递（pickle）。

| 代码 | 意思 |
|---|---|
| `MESSAGE_AND_CMD` | `user_message` 和 `cmd` 同时给了 |
| `UNKNOWN_ARGUMENT` | 不认识的参数 |
| `ARGUMENT_TYPE` | 参数的类型不对（5.1） |
| `SWITCH_INVALID` | 开关的值不是开关值：参数不是 `True`／`False`，或环境变量不是 1/true/yes/on、0/false/no/off |
| `ARGUMENT_NOT_FOR_CMD` | `cmd=` 时给了 SoulRun 自己的参数（第十节） |
| `PROGRAM_FORMS_CONFLICT` | `inline_program` 和 `slim_program=True` 同时给了 |
| `PROGRAM_FORM_UNKNOWN` | `host.system_prompt` 给的形式不认识 |
| `CACHE_DIR_REQUIRED`、`NOT_A_RUN`、`PROGRAM_NOT_ROUTED` | `--program`（`CACHE_DIR_REQUIRED` 也在 `--expand`）：没给 `--cache-dir`；给的不是一场运行的目录；这场运行还没选定程序（Router.match 还没提交） |
| `NODE_UNKNOWN`、`NODE_AMBIGUOUS`、`DOC_UNKNOWN`、`FIELD_UNKNOWN`、`PAGE_INVALID`、`PROGRAM_VIEW_CONFLICT` | `--program`：没有这个节点；好几个文件里都有这个节点（用 `--doc` 指定）；没有这个文件；没有这个字段；`--offset`、`--limit` 不对（`--report`、`--expand` 也报 `PAGE_INVALID`）；`--node` 和 `--field` 同时给了 |
| `PROGRAM_UNREADABLE` | `--program`：程序文件读不了 |
| `PROGRAM_OPTION_ALONE` | 命令行：`--node`、`--field`、`--doc` 没跟 `--program` 一起用；`--limit` 没跟 `--program`、`--report` 一起用；`--offset` 没跟 `--program`、`--report`、`--expand` 一起用 |
| `REPORT_LINK_INVALID`、`REPORT_PATH_UNSAFE` | `--report`／`host.execution_report`：给的不是 `engine-report:<运行>/<节点>@<次>/<sha256>` 链接；运行目录或报告文件不在它该在的地方（符号链接、越出放运行的目录） |
| `HEARTBEAT_NOT_ENGINE` | 心跳轮次不经过引擎，不要为它调用 SoulRun |
| `HUMAN_REPLY_REQUIRED` | `human_turn=False`（命令行 `--machine-turn`），而这个对话最近一场停在门上（运行状态 `WAITING_USER`），或者开关关着时它的引擎停门刚写下、还没写进索引就中断（看上去还是 `RUNNING`），或者开关关着时它还标着 `RUNNING`、一时又读不了（被杀掉的进程留下的运行锁、认不出的门记录）：门只由人回答（5.1） |
| `ENGINE_BUILD_MISMATCH` | `human_turn=False`，而这个对话没做完的那一场不是现在这一份引擎构建开的；人说的话遇到这种情况是问人（5.3） |
| `RECOVERY_REQUEST_INVALID` | `host.runner_recovery`：`phase` 不是五个之一、缺 `session_id`，或给的字典缺必填字段、有不认识的字段（11.2） |
| `DIR_NOT_FOUND` | 给的目录不存在或不是目录（写明是参数、环境变量还是默认给的） |
| `NO_PROGRAM_FOLDER` | 没点名程序，而 `aiap_dir`、`aisp_dir` 里一个程序都没有（往子层里也找过）；什么都不新建 |
| `REGISTRY_FOLDER_ALONE` | 单独给出的程序目录里有登记脚本（`aiap_list.py`、`aisp_list.py`）：登记脚本只在经代理目录时才运行，单独给出时会被跳过、被它停用的程序又成了候选，所以拒绝（第六节）；什么都不新建 |
| `SOULRUN_CACHE_DIR_INVALID` | 放运行的目录不是目录、建不出来或写不进去 |
| `SOULRUN_CACHE_DIR_HOLDS_AN_ENGINE` | 放运行的目录里放着引擎程序 |
| `SOULRUN_CACHE_DIR_NOT_EMPTY` | 指定的放运行的目录已经放着别的文件 |
| `PREPARE_BUSY` | 另一个进程准备运行超过 120 秒 |
| `PREPARE_LOCK_UNSUPPORTED` | 放运行的目录所在的文件系统不支持锁（比如不带锁的网络盘）：立刻报出，不白等 |
| `UNKNOWN_CMD`、`CMD_NAME_MISSING`、`PAYLOAD_AND_STDIN` | 引擎命令用法不对 |
| `CMD_OUTPUT_NOT_JSON`、`CMD_TIMEOUT` | 引擎命令没有打印 JSON（`CmdResult.json()` 时；报出退出码和标准错误的最后一行），或没在 `timeout` 秒内结束 |
| `MESSAGE_FILE_UNREADABLE`、`HOST_TOOL_INVALID` | 命令行：读不了用户的话（文件不在时，报错提醒它可能已被前一轮收进运行目录）、`--host-tool` 格式不对 |
| `MESSAGE_NOT_UTF8` | 命令行：用户的话不是 UTF-8（或带 BOM 的 UTF-16） |
| `ARGUMENT_INVALID`、`MODES_CONFLICT` | 命令行：参数写错；`--doctor`、`--version` 等模式和别的模式或用户的话同时给了 |
| `INTERNAL` | 命令行，只在 `--json` 时：意料之外的错误，也作为一个 JSON 对象报出 |
| `ENGINE_MISSING`、`ENGINE_NAME_CLASH`、`ENGINE_VERSION_UNKNOWN` | 带着的引擎不在；这个进程里已有和引擎同名的模块（`lib`、`prepare_cache` 等，包括引擎间接用到的）；说不出版本 |
| `ENGINE_MODULE_UNKNOWN`、`ENGINE_IMPORT_FAILED` | `host.engine(名字)` 给的不是引擎的模块（不会先导入它）；引擎的模块导入失败 |
| `ENGINE_MANIFEST_INVALID` | 引擎清单文件读不了 |
| `ENGINE_INTERFACE_CHANGED` | 引擎不再接受 SoulRun 的调用方式（换进了不配套的引擎） |
| `SLIM_PROGRAM_STALE`、`SLIM_PROGRAM_PARAMS` | 简装程序不是这份引擎生成的，或引擎的参数变了 |
| `ENGINE_NODE_UNKNOWN` | `--engine-node` 给的名字不是能交的组、段或函数（第九节） |
| `EXPAND_REF_UNKNOWN` | `--expand` 给的不是这批运行里的公开块的引用（第九节） |
| `ENGINE_NO_ANSWER`，以及引擎自己的错误代码 | 引擎没有交回运行；引擎报的错带着它自己的代码 |

疑惑（`DESIGNATED_NOT_FOUND`、`WHICH_DESIGNATED_PROGRAM`、`NAMED_RUN_MISMATCH`、`DESIGNATED_RUN_UNFINISHED`，人说的话遇到的
`ENGINE_BUILD_MISMATCH`，以及说明 `ENGINE_BUILD_RUN_ENDED`）不是错误，见 5.3。

---

## 十四、环境变量

| 变量 | 作用 |
|---|---|
| `SOULRUN_AGENT_DIR` | 代理目录（参数没给时） |
| `SOULRUN_CACHE_DIR` | 放运行的目录（参数没给时） |
| `SOULRUN_SLIM_PROGRAM` | 简装形式，默认开：0、false、no、off 关（改用入口路径形式），1、true、yes、on 开，空值算没设；别的值报 `SWITCH_INVALID` |
| `SOULRUN_INLINE_PROGRAM` | 第二步形式，默认关，取值同上；开了它就不用简装形式 |
| `SOULRUN_PRIVACY_WORDS` | 只给隐私检查（`tools/check_dist.py`，以及用它的 `tools/sync_engine.py --check-release`）：额外非秘密标识，逗号分隔，不写进源码；命令历史和进程环境仍可能保留，不放真实令牌 |
| `SOULRUN_TEST_INSTALLED` | 只给测试：`1`（或 `true`、`yes`）时对着装好的安装包跑 |
| `SOULRUN_TEST_AGENT_PY`、`SOULRUN_TEST_SOULBOT_SRC`、`SOULRUN_TEST_SOULBOT_DOCS` | 只给测试：SoulBot 的代理模板、源码和文档在哪；找不到时 SoulBot 那一边用 `tests/soulbot_samples.json` 里记下的样本 |

下面这几个 SoulRun 不读，引擎在每场运行里自己读；设了就对这个进程里的每一场运行都起作用。`soulrun --doctor` 的 `engine settings` 按引擎的读法报出它们。

| 变量 | 引擎拿它做什么 | 没设、或值用不了时 |
|---|---|---|
| `CACHE_NUM` | 最多留几场运行（至少 1）。新建一场时，超出的最旧的、已经结束的运行**被删掉**（在跑的、等人回答的不删） | 100 |
| `SOULBOT_RESUME_INTERRUPTED_RUNS` | 重启以后没跑完的运行：开（1/true/yes/on）时自己接着跑，关时问人（第十一节） | 关 |
| `SOULBOT_SUPPLY_WAIT_MAX_SECONDS` | 等额度恢复时，自动试探最多等多久（秒，至少 60） | 6 小时 |
| `SOULBOT_HOST_REPORT_WAIT_S` | 等宿主报告它截下的流式文字，最多等几秒 | 5 秒；不是数字时引擎载入不了，任何运行都开不了 |

---

## 十五、引擎与换新

```bash
python tools/sync_engine.py --check                                                    # 引擎和清单一致
python tools/sync_engine.py --check-release                                            # 发布准入，只读：来源形式、运行文件、摘要、隐私
python tools/upgrade_engine.py --from <引擎目录> --engine-version <X.Y.Z> --dry-run      # 只看
python tools/upgrade_engine.py --from <引擎目录> --engine-version <X.Y.Z>                # 换进来
python tools/upgrade_engine.py --from <引擎目录> --engine-version <X.Y.Z> --same-version # 内容变了、版本号有意不变
python tools/upgrade_engine.py --restore .engine_backups/<保留的那份>                     # 换回去
python tools/build_engine_node.py --check                                              # 简装程序和引擎一致
python tools/port_agent_text.py <SoulBot 的 agent.py> --check                           # 只对还带着固定文字的 SoulBot 代理模板：两边一致
python tools/check_docs.py --set-version <X.Y.Z>                                       # SoulRun 自己的版本号：包里和文档里标版本的那几行（页脚、阶段行、指南开头）
```

换新的每一步由 `upgrade_engine.py` 一次做完：取进新引擎、列出变化、预检、备份、换上并写清单、核对 SoulRun 的调用、重新生成简装程序、
核对固定文字（SoulBot 的代理模板还带着它时）、改文档里的引擎版本号，最后列出还要手动跑的命令。引擎不在这里手改，改动在引擎里做好再换进来。

- **取进来**：默认按规范来源处理：运行要用的文件、许可和契约逐字节照搬，并核对引擎的身份、版本、许可和契约；不改任何文字，也不重算引擎
  自己的完整性记录。以点开头的文件和文件夹、缓存，以及引擎自己的测试和发布说明（`tests/`、`RELEASE`、`pytest.ini`）不带进来。只有旧的
  开发树才加 `--legacy-clean`，走旧的清理（只留运行要用的文件、改名字和版本号、去掉开发记号），改过的文字会列出来（正式换时写进
  `.engine_backups/` 里的一份清单，只留在本机）；规范来源不能走旧的清理。
- **版本号**：`--engine-version` 只收发布版本的写法（`1.0.1`、`1.1.0rc1`）；规范来源的还必须和引擎自己写的版本一致，不改写。内容变了而
  版本号没变时拒绝（一场运行记着它开始时的引擎），有意如此时加 `--same-version`；比带着的版本低时提醒一句。文档里写引擎版本的地方
  （`DEPENDENCIES.md`、`DEPENDENCIES_CN.md`、本文开头一行）由它一起改，`tools/check_docs.py` 核对它们和引擎清单一致。
- **预检**：换上去之前，先用新引擎做出简装程序（新引擎多出简装排法还没安排的段落时报失败）、核对 SoulRun 调用的引擎函数都还在、
  不用模型建一场点名程序的运行；找得到 SoulBot 的 `agent.py`、而且它还带着固定文字时，再核对固定文字（SoulBot 的模板已经把每一轮
  交给 SoulRun 时，固定文字就是 SoulRun 自己的，这一项跳过）。有一项不过就什么都不改。
- **换上去**：新引擎先复制到旁边，再整体换进来；复制到一半出错时，原来的引擎原样留着。
- **备份**：换之前把带着的引擎（打包成 `soulrun_aiap.zip`）、它的清单和 `engine_node.aisop.json` 留在 `.engine_backups/<旧版本>-<时间>/`
  （不进安装包，git 也不收）；带着的引擎已经和清单对不上时，留底名字带 `-drifted`，并写一份 `DRIFTED.txt` 说哪里不一样。
- **换回去**：`--restore` 先把留底解到旁边，逐个文件对照留底里的清单：缺的、多的、改过的、名字指到引擎外面的（`../`、绝对路径）都拒绝，
  什么都不改；留底的引擎和现在的 SoulRun 接不上（调用的函数、固定文字）时也拒绝，这时要连同当时的 SoulRun 一起换回去。对得上才换回去
  （换下来的那份也先留底），清单也按留底原样放回。
- **旧引擎的对照样本**：测试里另外冻结了一份规范化以前的引擎组合（`tests/data/precanonical.json`），只给测试 `--legacy-clean` 这类旧工具用；
  它不进 wheel 安装包，也不拿来决定现在的引擎要不要改。
- **核对装好的引擎**：`soulrun --verify-engine` 逐个文件和清单比对，还核对清单里的文件列表算得出它记下的总摘要（同时改了文件和清单里
  那一行也查得出）。清单和引擎装在一起，证明不了没人连总摘要一起改；`soulrun --engine-info` 的 `installed_digest_now` 是从文件本身
  算出来的，拿它和发布时公布的摘要比。

换了引擎（哪怕版本号相同），之前没做完的运行不在新引擎上接着做：SoulRun 核对一场运行开始时记下的引擎摘要，对不上或没有记录时先问人
（`ENGINE_BUILD_MISMATCH`，5.3）。要接着跑旧运行，回到开它的那个完整环境。

这道核对是 SoulRun 在准备一轮时做的：直接调用引擎自己的入口（包括经 `host.engine(...)` 拿到的模块）没有它，所以宿主要经
`soulrun(...)`。「门只由人回答」（`HUMAN_REPLY_REQUIRED`，5.1）也是 SoulRun 先拦；直接调用引擎的入口不报这个错，但引擎也不把
标明不是人说的话当作门的回答（记下这句话，门照旧开着）。宿主要照实说一句话是不是人说的（见 README_CN 的「引擎」和「已知限制」）。

---

## 十六、程序形式

引擎程序怎样到模型手里。设计原则：用了 SoulRun，模型自己不读任何文件，都经 `soulrun` 命令拿，而且只拿眼前这一步要用的内容。

| 形式 | 怎么得到 | 交给模型的是什么 | 开场指令（`ctx.system_prompt`） | 状态 |
|---|---|---|---|---|
| 简装（`slim`） | 默认 | 用 `engine_node.aisop.json` 组装的简装程序：每轮开头只交这一轮开头要用的部分，用户的话已填好，其余部分跟着需要它的引擎回复交；入口段让模型经 SoulRun 运行引擎的工具、取业务程序 | SoulRun 的 | 默认 |
| 入口路径（`entry_path`） | `slim_program=False`、`SOULRUN_SLIM_PROGRAM=false`、`--no-slim-program`；或者退回 | 主程序 `main.aisop.json` 的路径，模型自己读；就是 SoulBot 改用 SoulRun 之前代理模板交给模型的文字，只是不运行任何东西的轮次不带入口段 | SoulBot 的原文 | 可选；退回时用 |
| 第二步（`full`） | `inline_program=True`、`SOULRUN_INLINE_PROGRAM=true`、`--inline-program` | 整份主程序，用户的话作为数据放在 `user_input` | SoulBot 的原文 | 试验性，默认关；没有用真实模型验收过 |

**真实模型验收。** 2026 年 10 月 30 日的构建（这一构建之前的那一个）经 SoulBot、在隔离的验收环境里用 Claude Opus 5.5 跑过：易经一场
从头到终答，通过；股票分析（MSFT，完整）跑完，但那个环境没有行情数据服务，改用网页搜索、数字标为未核实，结果降级；一场中途停止、再说
「继续」的运行接着跑完，通过。该历史构建不是当前运行头。之前已记录的 97 资源运行头的 Claude、Codex CLI/SDK 有限短图、
继承分支及正常网页流程另见[验证范围](docs/verification-1.0.0.md)，不能外推为所有宿主、全部正文转发或 Creator 长流程通过。更早的构建上，
简装形式还跑过：股票过导出门、Creator 过门后五次派发子代理、独立的 Claude Code 会话用最简 SKILL.md 跑 AISP 易经，主对话都没有打开程序文件；
入口路径形式也在更早的构建上用真实模型跑过。这一版验证和没验证的全部范围见[发布说明](docs/release-1.0.0.md)。

**简装形式里模型怎么做事。** 入口段写出一条完整的命令：`"<运行 SoulRun 的解释器>" "<包>/_launch.py"`。引擎的四个工具（`next-node`、
`node-commit`、`stop-decision`、`gate-answer`）都写成这条命令加 `--cmd 名字`，参数、标准输入、输出和退出码都是工具自己的；引擎原文里
写 `python {engine_dir}/python_tools/<工具>.py` 的地方，以及中断提醒、引擎回复里点名这几个工具的地方（不管写的是哪个路径），都照这样运行。业务程序写成这条命令加 `--program --cache-dir <运行目录>`（第九节）；引擎回复里 `program_contracts` 点名的程序约定（比如共同约束），用引擎自己的 `--cmd next-node --read-program-contract <ref>` 取，两条路不混用：
模型从不用文件工具或 shell 读程序文件（`*.aisop.json`、`AIAP.md`、`AISP.md`）。PowerShell 里命令前面加 `&`。

**按引擎节点交。** `engine_node.aisop.json` 的 `soulrun_delivery` 把引擎主程序分成几组，每组写明什么时候交：

| 组 | 内容（全是引擎原文） | 什么时候交 |
|---|---|---|
| `entry` | 引擎的身份、`output_mode`、`hsaw_first_law`、`system_prompt`、节点执行约定、提交约定（从第一条引擎回复起就要用）、`Start` 函数，用户的话在 `user_input` | 每一轮开头，在 `ctx.text` 里 |
| `recovery_entry` | `params`、`bootstrap_recovery` | 接回一场运行的轮次（`entry_mode` 不是 `fresh`），也在开头 |
| `Router.match` | `RouterMatch` | 回复要做 Router.match 时 |
| `Router.cache-setup` | `CacheSetup`、`NodeLoop` | 回复要做 Router.cache-setup 时 |
| `business` | `NodeLoop` | 回复要做业务节点时 |
| `dispatch` | 派发范围约定 | 回复要求派发子代理时 |
| `Engine.execute-report` | `Report` | 回复要做执行报告时 |
| `Engine.final-answer` | `Final`、终答交付约定 | 回复要做终答时 |
| `run_failed` | `ErrorReport`、终答交付约定 | 回复说运行失败或放弃时 |
| `terminal` | 终答交付约定 | 回复里点名终答交付时 |

开头那一组约占主程序的五分之二。每组每轮只交一次：SoulRun 的命令行先完整打印引擎回复，再打印 `[SOULRUN ENGINE NODE: <组名>]` 和那一部分
（一段短的 AISOP，role 分 system 和 user，和主程序一样）。打印的内容守引擎自己的上限 29,000 字节（引擎把每条回复控制在这以内；超过约
30,000 字节，Claude Code 这样的命令行工具会把输出存进文件，模型要另外去读、去解析）：附上会超限的部分不打印，只打印一行，写明是哪几组，并要模型做这一步之前
先运行取它的 `--engine-node` 命令；这几组也不记为已给。节点执行约定和提交约定放在开头，就是因为每轮第一条引擎回复本来就有约 24,000 字节。一轮给过什么记在 `<soulrun_cache_dir>/.soulrun/delivered/<运行>.json`（连同是哪一轮：`turn_id` 即场号、宿主的 `host_turn_id`、这一场的第几轮 `turn`。用过的场号再给新的一场时，SoulRun 按这一场的 `trace_id` 认出来、从 1 重新数；引擎为同一句话重启同一轮时，只有 `host_turn_id` 相同才算同一轮），这场运行被
引擎删掉时一起删；新的一轮重新开始记（新的一轮可能是新的模型会话）；按入口路径形式交的一轮不记，也不补。始终不交的：引擎的 `tools`、
`json_schema`（每个引擎工具自己的回复写明它要什么）、指向四份约定的指针（每轮第一条引擎回复里已有全文）、说明性字段，每一项的理由写在
`soulrun_delivery.not_delivered`。模型缺了哪一部分，可以用 `soulrun --engine-node <名字>` 取（第九节）。生成工具 `--check` 核对每一部分只提到
交到那时已经给过的文字。

**带中断提醒的轮次。** 人按停止以后的判断、接回、停止后作为新任务，这几种轮次带着 SoulBot 的中断提醒，提醒自己写了第一步。它们也用
简装形式：入口段最后一句换成「提醒先做」，断言里 `FIRST_TOOL_ACTION` 照提醒写（停止以后的判断是 `stop_decision`，其余是 `next_node`），
`VISIBLE_TEXT_BEFORE_FIRST_TOOL` 换成「只许打出提醒要求先打的文字」（停止后作为新任务、停止后接着做时，提醒要求先原样打出 public_note）。
提醒本身是 SoulBot 的原文，不改。只回文字的轮次（中断后请人确认、取消、各种提问）给上下文段、提醒段和 SoulBot 的只回文字断言，不给
入口段：SoulBot 自己的规则给确认、取消也加上了入口段和「先读入口」的断言，会叫模型去读 `main.aisop.json`。入口路径形式下这些轮次
也一样，不给入口段。人按停止以后直接说「继续」，10 月 30 日的构建用真实模型跑过（上面的验收）；要模型判断的一句话在更早的构建上跑过（第一个
动作是经 SoulRun 调 `stop-decision`；引擎回复接着点名了一个并不存在的 next-node 工具路径，模型按入口段改经 SoulRun 调 `next-node`）。

**什么时候退回入口路径形式。** 下面几种情况，这一轮改用入口路径形式，`ctx.slim_fallback` 写明原因：

| `slim_fallback` | 什么时候 |
|---|---|
| `SLIM_PROGRAM_UNAVAILABLE: <代码>` | 简装程序做不出来（没有 `engine_node.aisop.json`，或者它不是这份引擎生成的） |
| `EARLIER_SLIM_PROBLEM: STALLED_AT_ROUTER_MATCH` | 这一场用过简装形式，下一轮来时还停在 Router.match、一个节点都没提交，而模型已经轮到过（Router.match 交给过模型，或宿主已经结束过这一场的一轮）；被宿主打断、模型还没动手的不算，模型在 Router.match 问了人（比如两个程序都合适）、这一场在等回答或这一轮带来回答的也不算 |
| `EARLIER_SLIM_PROBLEM: ENGINE_NODE_FAILED in run N` | 同一段对话的上一场（第 N 场）用过简装形式，在引擎自己的节点上失败（Router.match、Router.cache-setup、Engine.execute-report、Engine.final-answer） |
| `EARLIER_SLIM_PROBLEM: INHERITED from run N` | 上一场已经记着简装出过问题 |
| `TOO_LONG_FOR_COMMAND_LINE` | 只在命令行 `--json`：这一轮超过打印上限，按入口路径形式打印（第九节） |

问题记在 SoulRun 放在运行旁边的记录里（`.soulrun/runs/<N>.json` 的 `slim_used`、`slim_problem`），所以这段对话之后的运行都用入口路径形式；
别的对话照旧用简装形式。SoulRun 没建过记录的运行（比如别的工具开始的）什么都不判断。

接回的轮次交的 `params` 保留引擎原文（主程序里唯一说明各个 `entry_mode` 是什么意思的地方），三个值由 `[EXECUTION CONTEXT]` 和入口段给出。
简装形式自己那几段文字（入口段、断言段、开场指令，引擎回复后附的那几行，以及命令行上的屏幕规则）是 SoulRun 的措辞，会随引擎配合改进，不在版本号的承诺里。子代理还是从引擎拿到自己那份引擎
程序的路径、自己去读；引擎的节点信息里也还没有业务程序的 tools、params 和 system_prompt：这两样要由引擎自己交出，需要改引擎
（README_CN 的「已知限制」）。

---

## 十七、测试与 CI

下面是从源码工作的命令，不是本机已装包或远端CI已经更新的证明。`guide.txt`是随包独立文字，不是由本文件生成；
修订它须同时核对无参CLI/SDK的真实输出、现行门规则和隐私边界，不能只改维护指南就认为模型会读到新说明。

```bash
python -m pip install -e ".[dev]"
python tools/sync_engine.py --check
python tools/sync_engine.py --check-release
python src/soulrun/soulrun_aiap/tools/aiap_conformance_check.py src/soulrun/soulrun_aiap
python tools/build_engine_node.py --check
python -m ruff check src tests tools examples
python tools/check_docs.py
python -m pytest -rs
SOULRUN_TEST_INSTALLED=1 <干净环境>/bin/python -m pytest   # 在只装了安装包的干净环境里（INSTALL 第七节）
```

- 没有任何测试会调用模型；需要模型的地方，由测试向引擎提交模型会提交的那种内容。
- 名字以 `test_engine_today_` 开头的测试记的是引擎现在的行为和 SoulRun 的设计不一样的地方，引擎改了会故意不过。
- 要和 SoulBot 比对的测试（固定文字、发送层、宿主载入的模块、页脚和政策文档），SoulBot 在旁边时用 SoulBot 本身，不在时用
  `tests/soulbot_samples.json`；SoulBot 改了，用 `python tools/record_soulbot_samples.py` 重新记下（有 SoulBot 时测试会提醒）。
  跳过还可能来自平台权限、历史制品和旧模板适用性；以实际 `-rs` 和 JUnit 为准，不承诺固定只有三项。每项测试最多跑 5 分钟（`pytest-timeout`）。
- CI（`.github/workflows/ci.yml`）配置为在 Ubuntu 和 Windows 上跑 Python 3.11–3.15，共10项源码测试；另有2项Python3.12包装作业，构建安装包、检查内容、对着装好的安装包跑测试。准确1.0.1发布提交的12项远端结果仍须单独核验，本地结果和旧版CI不能代替。
  实际跑过的测试结果和日期见 README_CN 的「已验证测试基线」和[发布说明](docs/release-1.0.0.md)：只有那里写明的环境算验证过。

---

## 十八、公理 0、安全与隐私

SoulRun 自己遵循公理 0（人类主权与福祉）：判断不了人要什么就问人；从不替用户编话、从不替人挑程序、从不替人答门；不悄悄退回默认；
SoulRun 把人的话写在 `soulrun_cache_dir`，并交还宿主（命令行读的消息文件，这一轮有了运行就挪进那一场的运行目录）；
宿主、服务商、终端与工具也可能留副本，不能理解成全链路只有这一份。做了什么就记下来。逐条说明见 README_CN 的「SoulRun 里的公理 0」。

部署时要注意的事（运行数据不加密、`session_id` 不是身份认证、程序和引擎都是可执行代码、模型的权限规则由宿主负责……）见
[SECURITY.md](SECURITY.md)。

`human_turn` 和宿主能力是调用者必须如实提供的断言，不是密码学身份凭证。ignore 不加密、不移除已跟踪文件，也不限制同用户进程；
不把用户原答、工具原文、认证目录或日志放入公开报告。文件移入缓存或删除也不证明安全擦除。

---

## 十九、常见问题

### Q1：调用一次要多久？

留着的运行越多越慢：引擎每次都要把留着的运行逐个读一遍。这个对话最近一场的索引越大也越慢：SoulRun 和引擎每次调用都要读它、校验它。
在更早构建的一台测试机上量过：几场运行时约 50 毫秒，留着 100 场时约 0.2 秒，1.9 MB 的索引读一次约 77 毫秒；这一版没有重新量。
引擎最多留 100 场（`CACHE_NUM`），更早而且已经结束的会被删掉。

### Q2：为什么我的问题「继续」没有接上？

先看这个对话是不是同一个 `session_id`：引擎按对话找没做完的那一场。再看用户的话的文件开头：记事本和 PowerShell 存文件时常带 BOM，
引擎认不出它后面的「继续」；SoulRun 会去掉开头的 BOM，命令行和 Python 调用都一样。

### Q3：模型说找不到工具，或者第一次提交就「找不到文件或目录」「Path too long」？

先跑 `soulrun --doctor`：`program form` 报这一轮是什么形式、交给模型的是哪条命令（简装形式按完整路径写运行 SoulRun 的解释器），`python for the model` 报模型的命令行找到的是哪个 `python`（入口路径形式下的引擎工具、子代理的引擎工具、程序自己写成 `python ...` 的工具用它）、能不能载入引擎的工具；Windows 上 `path length` 报放运行的
目录是不是太深（在更早的构建上实测过：150 字符的目录第一次提交就失败；这一版没有重新量）。

### Q4：可以把运行放回 SoulBot 代理原来的引擎文件夹吗？

可以指过去，但只能在那个文件夹里只剩运行（`.execution_cache`）以后：还放着引擎程序的目录、还放着别的文件的目录都会被拒绝。一场运行按绝对路径记着自己的目录，所以不要搬动运行；整个目录换位置还没有试过。SoulBot 的引擎上开始、还没做完的运行，在 SoulRun 的引擎上不接着做：它们没有 SoulRun 的记录，那个对话里人说的下一句话先问人
（`ENGINE_BUILD_MISMATCH`，5.3），不是人说的话直接报同名错误。接管之前先让它们做完或结束，或者换一个 `session_id`。

### Q5：SoulRun 会把用户的话发到哪里？

SoulRun 自己不打开网络连接；用户的话写进 `soulrun_cache_dir`，并交还给宿主。送不送给模型、送给哪个服务商，由宿主决定。
宿主、服务商或业务工具的联网和留存须另审，不能由「SoulRun 不联网」推断全链路不外传。
命令行上读用户的话的那个文件，这一轮有了运行就挪进那一场的运行目录（`_soulrun/message.<n>.txt`），跟着运行一起删；要留在原处，加
`--keep-message-file`。

### Q6：我的 msg.txt 不见了？

这一轮有了运行，SoulRun 就把它挪进那一场的运行目录：`<soulrun_cache_dir>/.execution_cache/<N>/_soulrun/message.<n>.txt`，同一场的
下一轮是 `message.2.txt`。再用同一个路径之前，先把用户的话重新写进去；想一直用同一个文件，加 `--keep-message-file`。还没开始运行就
要问人的那一轮（比如找不到指定的程序）不挪，回答时还要用。

### Q7：在 Claude Code 里，前面几步的节点块没有显示出来？

在命令行上，SoulRun 每条引擎回复之后都把要给人看的块（计划、节点块和其中的消息、门、终答、证据）交给模型，要它原样打印。但打不打印
由模型决定。在更早的构建上实测，Claude Code 每一道门的全部内容、每一份终答和证据都完整显示，中后段的节点块大多显示；最前面几步（路由、
路径设置、第一个节点）它常常连着调工具不打印，换说法也一样。要看某一块，可以运行 `soulrun --expand <引用> --cache-dir <运行目录>`；运行目录的
`_public/` 里也存着每一块。
