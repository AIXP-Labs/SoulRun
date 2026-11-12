# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it privately through GitHub Security Advisory:

**[Report a vulnerability](https://github.com/AIXP-Labs/SoulRun/security/advisories/new)**

Please do not disclose the issue publicly until a fix is available. A defect inside the engine is fixed in
the engine and brought in with `tools/upgrade_engine.py`; see [GOVERNANCE.md](GOVERNANCE.md).

## Scope

This software is **experimental** and provided **as-is** for research and educational purposes. There is no guaranteed response time, no SLA, and no bug bounty. The authors will review reports on a best-effort basis.

For full terms, see [LICENSE](LICENSE) (Apache 2.0).

## Handling a Suspected Disclosure

1. Stop sharing the affected output. Preserve only the minimum necessary investigation evidence in a private,
   access-restricted location; use synthetic examples in public reports, not user messages or run caches.
2. Revoke or rotate any exposed credential at its issuer. Deleting a file, masking a response or isolating a
   local copy does not revoke that credential.
3. Review the relevant source, historical revisions, packages, logs, backups and provider sessions. Scope any
   cleanup explicitly, preserve unrelated evidence and do not claim that remote copies have disappeared.
4. Record what was inspected, changed and left unresolved. Local cleanup does not prove that a credential was
   unused or that no disclosure occurred elsewhere; follow the private reporting process above.

## Supported Versions

Security fixes target the current `main` branch and latest published release
unless a release note explicitly says otherwise. Older releases do not receive
guaranteed backports. Confirm the installed version and the engine it carries with
`soulrun --version` and verify the engine files with `soulrun --verify-engine`;
review [CHANGELOG.md](CHANGELOG.md) before reporting or deploying a fix.

## Deployment Baseline

- SoulRun opens no network connection and calls no model. What leaves the machine
  is what the host sends: `ctx.text` and the user's words go to the host's model
  provider under that provider's policy. Minimize submitted data and review the
  provider's retention, approval, sandbox, and network settings.
- Run data in `soulrun_cache_dir` holds the conversation: the user's messages, the
  model's reports, gate questions and answers. `.soulrun/entries/<N>.txt` keeps the
  full text of a turn printed by the command line. SoulRun does not encrypt any of
  it. Restrict filesystem access, keep the folder out of shared or synchronized
  locations, and use encrypted storage where the data classification requires it.
- SoulRun attempts to write a `.gitignore` of `*` when it creates a run folder,
  or takes one for the first time that has none; verify it exists, since the write is best effort. After
  that the owner's choice stands. The run folder, named by the caller or the
  default, must be new, empty (a `.gitignore`, an engine's own runs and system files
  aside) or one SoulRun already keeps runs in, and must not hold an engine program;
  any other folder is refused, so run data never lands among other files. On Linux
  and macOS a run folder SoulRun creates is readable by its owner only (700);
  `soulrun --doctor` warns when other users can open it.
- Windows retains the same `0o700` creation policy. Python 3.11.10 / 3.12.4 and later minor series can apply a
  protected DACL that a restricted token cannot use; this limitation is not fixed by the 1.0.1 documentation
  patch. There is no automatic inheritance or ACL widening. A pre-created directory must already be permitted
  by the host and suitable for sensitive data; neither pre-creation nor `.gitignore` proves privacy. A parent
  write probe in `--doctor` does not test a nonexistent child's later access or any other user's permissions.
- `session_id` separates conversations; it is not authentication. Hosts that serve
  mutually untrusted users must give each trust domain its own `soulrun_cache_dir`
  (or agent folder) and enforce access themselves.
- On the command line SoulRun reads the user's words from a file or standard input,
  not from a message argument in the process list. A user's shell command that creates
  that file or supplies input can still retain the words in history; avoid embedding secrets there.
  The same file-based transport holds for a human's answer given through
  `soulrun(cmd="gate-answer", answer=...)`: it reaches the engine tool in a file
  only the user can read, removed when the command is done. The examples read the
  user's words from a file or standard input too. Once a command-line turn has its run, the file holding the
  user's words is moved into that run's folder (`_soulrun/message.<n>.txt`, under the run data's `.gitignore`)
  and goes with the run; `--keep-message-file` leaves it where it was. On a command line SoulRun also prints,
  after engine replies, the text of the blocks meant for the human, for the model to show: the run's own public
  text, which a host program would show the human anyway.
- In an agent folder, `aiap/aiap_list.py` and `aisp/aisp_list.py` (registry scripts)
  are run by the engine at every run, with the interpreter running SoulRun, and
  rewrite the JSON lists beside them: keep only scripts you trust there (`soulrun
  --doctor` names them). A program folder with its registry script is used only
  through its agent folder, so the script cannot be bypassed by naming the folder.
- The bundled engine and every AIAP/AISP program, including their Python tools,
  are executable trust boundaries. The model runs the commands its text names: in
  the slim form (the default) SoulRun's launcher with the interpreter running
  SoulRun, in the entry-path form the engine's scripts with the `python` its shell
  finds, and in either form the program's own tools; in either form, too, a sub-agent
  runs the engine's scripts with the `python` its shell finds. Process-level
  sandboxing and the model program's permission rules are the host's and provider's
  responsibility, not SoulRun's.
- `cmd` runs one of the bundled engine's own tools with the interpreter running
  SoulRun, and nothing else. `soulrun.host.engine(name)` imports an engine module
  into the host process: treat it as trusted in-process code. `soulrun --report`
  (`host.execution_report`) reads only inside that run's own folder (its index, its
  execution-report records and the report file), checks that the report is bound to
  the run and to the link's digest, and refuses symbolic links (`REPORT_PATH_UNSAFE`).
- Besides the program folders and the run folder, the engine reads the files (and
  lists the folders) a node's evidence names as its artifacts or sources, wherever
  the path points, to record their SHA-256 and size and to check what the node
  claims about them; the run records then hold those paths and digests. One
  diagnostic also reads a local file outside the run folder: `next_node.py
  --observe-dispatch-return` (run by a model or a host, never by SoulRun itself)
  may read the Claude Code session record of a dispatched sub-agent under
  `~/.claude/projects` (`.jsonl` only, at most 64 MB) to report what it saw. What
  it reports is diagnostic only and never lets a run continue.
- The engine's tools use plain top-level module names (`lib`, `prepare_cache` ...).
  In a host process those names belong to the engine once SoulRun loads it: a module
  of the same name from elsewhere is refused (`ENGINE_NAME_CLASH`), never used.
- Verify an installed copy with `soulrun --verify-engine`: every bundled engine file
  is compared with the SHA-256 recorded in `engine_manifest.json`, and a changed,
  missing, or extra file is reported, and so is a manifest whose file list no longer
  gives the digest it records. The manifest is installed with the engine, so this
  cannot prove that nobody changed files, list and digest together: against that,
  compare `soulrun --engine-info`'s `installed_digest_now` - worked out from the
  files themselves - with the digest published with the release.
- `tools/check_dist.py` fails a build whose engine folder is not exactly the files
  the manifest installs, that misses one of SoulRun's own required files, that
  carries a cache, run data, a kept engine, a repository folder or a `.env` file,
  declares a runtime dependency, carries any file SoulRun does not ship (the wheel
  holds only `src/soulrun`'s files, the source archive only what pyproject.toml's
  sdist list includes, plus the `PKG-INFO`, `pyproject.toml` and `.gitignore` the
  build backend adds itself), or holds a credential, a home-folder path, an unexpected
  e-mail address, or a user name in an archive header (the rules in
  `tools/privacy_rules.py`, shared with the documentation check).
- `.engine_backups/`, kept by `tools/upgrade_engine.py`, is local only and is never
  packaged.
- SoulRun has no runtime dependency. The `dev` and `release` extras are for tests and
  packaging only; dependency scans of a development environment do not prove that a
  program, a model-generated action, or the host is safe.

## Repository and Tooling Hygiene

- Ignore local environment variants, provider profiles, private keys, raw logs and build outputs. Keep the
  sanitized `.env.example` and legitimate public JSON examples reviewable. Ignore rules do not remove tracked
  files, clean history, encrypt records or provide access control; review actual public inputs and built packages.
- Local `.ssh` and `.aws` authentication directories are ignored and refused in distribution archives even
  when their content looks harmless. Ordinary `examples/ssh`, `examples/aws` and `.ssh.example`/`.aws.example`
  remain reviewable. E-mail-shaped content is not exempt merely because its suffix resembles a file extension;
  only the explicit project/neutral address allow-list applies.
- Do not put credentials in command arguments, issue reports, screenshots or test fixtures. Use synthetic
  values in public regressions and keep raw evidence private. A file being consumed, moved or deleted is not
  evidence of secure erasure. Provider/host logs and program tools have their own retention and network policies.
- `human_turn` and host capability values are assertions a trusted caller must supply truthfully, not
  independently authenticated identities. A report or writable proof file cannot by itself establish the
  original child's identity. Default diagnostic reports must not be treated as execution authorization.
- A scan without matches is bounded evidence for the inspected inputs, not proof about all history, ignored
  directories, remote copies or future files. Record exclusions and artifact SHAs; never publish raw private
  paths or original sessions just to demonstrate a successful privacy check.

---

# 安全政策

## 报告漏洞

如发现安全漏洞，请通过 GitHub Security Advisory 私下报告：

**[报告漏洞](https://github.com/AIXP-Labs/SoulRun/security/advisories/new)**

在修复发布之前请勿公开披露问题。引擎内部的缺陷在引擎里修复，再用 `tools/upgrade_engine.py` 换进来；见
[GOVERNANCE.md](GOVERNANCE.md)。

## 范围

本软件为**实验性**软件，按"现状"提供，仅供研究和教育用途。无响应时限承诺、无 SLA、无 Bug Bounty。作者将尽力审阅报告。

完整条款见 [LICENSE](LICENSE)（Apache 2.0）。

## 疑似泄露的处置

1. 停止共享受影响输出。仅在访问受限的私有位置保留调查所需的最少证据；公开报告使用合成示例，不附用户消息或运行缓存。
2. 到发行方撤销或轮换任何暴露的凭据。删除文件、掩码响应或隔离本机副本不等于撤销凭据。
3. 核查相关源码、历史修订、安装包、日志、备份和服务商会话。清理须明确范围、保全无关证据，不声称远端副本已消失。
4. 记录已检查、已修改和尚未解决的事项。本机清理不能证明凭据未被使用或未在别处泄露；按上文流程私下报告。

## 支持版本

除非发布说明另有声明，安全修复面向当前 `main` 分支和最新正式版本；旧版本不保证回补。报告或部署修复前，
用 `soulrun --version` 确认安装的版本和它带着的引擎，用 `soulrun --verify-engine` 核对引擎文件，并检查
[CHANGELOG.md](CHANGELOG.md)。

## 部署基线

- SoulRun 不打开任何网络连接，也不调用模型。离开这台机器的，是宿主送出去的东西：`ctx.text` 和用户的话按宿主所用模型服务商的
  政策送到服务商那里。应最小化提交的数据，并审查服务商的保留、审批、sandbox 与网络设置。
- `soulrun_cache_dir` 里的运行数据就是对话本身：用户的消息、模型的报告、门的问题和回答。`.soulrun/entries/<N>.txt` 保存命令行
  打印过的那一轮的全文。SoulRun 不加密其中任何内容。应限制文件系统权限，不把这个目录放在共享或同步的位置，并在数据分级要求时
  使用加密存储。
- SoulRun 新建运行目录、或第一次接管一个没有忽略文件的目录时，尝试写入内容为 `*` 的 `.gitignore`；这是尽力而为，须核对它确实存在。
  之后归目录的主人决定。
  放运行的目录（不论是调用方指定的还是默认的）必须是新的、空的（`.gitignore`、引擎自己的运行和系统文件不算），或者 SoulRun 本来就在
  里面放运行的，而且不能放着引擎程序；别的目录一律拒绝，运行数据不会混进别的文件中间。在 Linux、macOS 上，SoulRun 新建的运行目录只有
  自己能读（700）；别的用户能打开时 `soulrun --doctor` 会提醒。
- Windows保持相同的`0o700`创建策略。Python3.11.10 / 3.12.4及以后次版本可能应用受限令牌无法使用的受保护DACL；1.0.1文档补丁
  没有修复这项限制，不自动继承或放宽ACL。预建目录必须本来就被宿主允许且适合敏感数据；预建和`.gitignore`均不证明私有。
  `--doctor`父目录写入探针不验证尚不存在的子目录后续访问能力，也不验证其他用户的权限。
- `session_id` 只用来区分对话，不是身份认证。服务互不信任用户的宿主，必须给每个信任域单独的 `soulrun_cache_dir`（或代理目录），
  并自行做访问控制。
- 在命令行上，SoulRun 从文件或标准输入读用户的话，不把消息放进进程参数；但用户为创建文件或提供输入写的 shell 命令仍可能留下历史，
  不要把秘密嵌进去。经
  `soulrun(cmd="gate-answer", answer=...)` 交的人的回答也一样：放在只有自己能读的文件里交给引擎工具，用完就删。两个示例也从文件或
  标准输入读用户的话。命令行上的一轮有了运行以后，装着用户的话的文件会被挪进那一场的运行目录（`_soulrun/message.<n>.txt`，在运行数据
  的 `.gitignore` 之内），跟着运行一起删；加 `--keep-message-file` 就留在原处。在命令行上，SoulRun 还会在引擎回复后面打印要给人看的块的
  正文，由模型展示给人：这是运行自己的公开内容，有宿主程序时宿主同样会展示给人。
- 代理目录里的 `aiap/aiap_list.py`、`aisp/aisp_list.py`（登记脚本）会被引擎在每场运行里用运行 SoulRun 的解释器执行，并改写旁边的
  JSON 名单：那里只放你信得过的脚本（`soulrun --doctor` 会列出来）。带登记脚本的程序目录只能经它的代理目录用，点名这个目录绕不过脚本。
- 带着的引擎和每个 AIAP/AISP 程序（包括它们的 Python 工具）都是可执行代码信任边界。模型运行交给它的文字里写的命令：简装形式
  （默认）下是用运行 SoulRun 的解释器运行 SoulRun 的启动文件，入口路径形式下是用它的命令行找到的 `python` 运行引擎的脚本，两种
  形式下都会运行程序自己的工具；不管哪种形式，子代理也都用它的命令行找到的 `python` 运行引擎的脚本。进程级沙箱和模型程序的权限规则
  由宿主和服务商负责，不在 SoulRun 的保证范围内。
- `cmd` 只用运行 SoulRun 的解释器运行带着的引擎自己的一个工具，不运行别的。`soulrun.host.engine(name)` 会把一个引擎模块导入
  宿主进程：应把它当作受信任的进程内代码。`soulrun --report`（`host.execution_report`）只读那一场自己的运行目录里的东西（它的
  索引、它的执行报告记录和报告文件），要求报告和这一场、和链接里的摘要都对得上，并拒绝符号链接（`REPORT_PATH_UNSAFE`）。
- 除了程序目录和放运行的目录，引擎还会读节点的证据里点名为产物或来源的文件（是目录时列出其中的文件），不论路径指向哪里，
  用来记下它们的 SHA-256 和大小、核对节点关于它们的说法；运行记录里会留下这些路径和摘要。另有一项诊断会读放运行的目录以外的本机文件：
  `next_node.py --observe-dispatch-return`（由模型或宿主运行，SoulRun 自己从不调用）可能读 `~/.claude/projects` 下某个被派发的
  子代理的 Claude Code 会话记录（只读 `.jsonl`，最多 64 MB），报告它看到了什么。报告的内容只作诊断，从不让运行因此接着走。
- 引擎的工具用很普通的顶层模块名（`lib`、`prepare_cache` 等）。SoulRun 载入引擎以后，宿主进程里这些名字归引擎：别处来的同名模块
  会被拒绝（`ENGINE_NAME_CLASH`），绝不拿来用。
- 用 `soulrun --verify-engine` 核对装好的副本：每个引擎文件都和 `engine_manifest.json` 里记下的 SHA-256 比对，改动、缺少或多出的
  文件都会报出来；清单里的文件列表算不出它记下的总摘要时也会报出来。清单是和引擎一起装上的，所以它证明不了没人同时改了文件、
  列表和总摘要；要防这种情况，拿 `soulrun --engine-info` 的 `installed_digest_now`（从文件本身算出来的）和发布处公布的摘要比对。
- 下面这些情况 `tools/check_dist.py` 会让构建失败：引擎文件夹里的文件不正好是清单要装的那一批；缺了 SoulRun 自己必需的文件；
  带进了缓存、运行数据、留底的引擎、仓库文件夹或 `.env` 文件；声明了运行时依赖；带了 SoulRun 不发的文件（wheel 里只能有
  `src/soulrun` 的文件，源码包里只能有 pyproject.toml 的 sdist 名单里的，加上构建工具自己加的 `PKG-INFO`、`pyproject.toml`、
  `.gitignore`）；有凭据、本机用户目录路径、意外的邮箱地址，或者归档头里带用户名（规则在 `tools/privacy_rules.py`，和文档检查共用）。
- `tools/upgrade_engine.py` 保留的 `.engine_backups/` 只在本机，从不打进安装包。
- SoulRun 没有运行时依赖。`dev` 和 `release` 两组额外依赖只用于测试和打包；对开发环境做依赖扫描，不能证明某个程序、某个模型
  生成的操作或宿主是安全的。

## 仓库与工具卫生

- 忽略本机环境变体、服务商配置、私钥、原始日志和构建输出；保留脱敏 `.env.example` 和合法公开 JSON 示例可审。
  ignore 不移除已跟踪文件、不清历史、不加密、不提供访问控制；仍须审查实际公开输入和构建包。
- 本机`.ssh`和`.aws`认证目录即使内容看似中性，也忽略并拒绝打入发行归档；普通`examples/ssh`、`examples/aws`与`.ssh.example`/`.aws.example`
  仍可审。邮箱形状的内容不能仅凭后缀像文件扩展名就豁免，只保留明确的项目/中性邮箱允许名单。
- 不把凭据放进命令参数、Issue、截图或测试夹具。公开回归用合成值，原证据私有保留。文件被消费、移动或删除不证明安全擦除。
  服务商、宿主日志和业务工具有各自的留存与联网政策。
- `human_turn` 与宿主能力由受信调用者如实声明，不是独立认证的身份。报告或可写证明文件本身不能证明原 child 身份，
  默认诊断报告不能当成执行授权。
- 扫描未命中只说明本次检查过的输入，不证明所有历史、忽略目录、远端副本或未来文件安全。记录排除范围和制品 SHA；
  不为证明扫描通过而公开私人路径或原始会话。

---

Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulRun V1.0.1. www.soulrun.dev
