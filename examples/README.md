# Examples

| File | Shows | Calls a model? |
| --- | --- | --- |
| [minimal_host.py](minimal_host.py) | the whole loop of a host around SoulRun in one page: one call; a question SoulRun asks (`ctx.doubt`) shown to the human without asking a model; otherwise the opening instruction (`ctx.system_prompt`), `ctx.text` and the human's words handed to a model - for `program` and `text_only` turns alike; the reply shown with the engine's references expanded (`host.expand_refs`); the turn recorded (`host.after_turn`) | no — the model is a stand-in |
| [soulacp_host.py](soulacp_host.py) | the "program door": the same loop with a real command-line model program reached through SoulACP; one conversation id is given to both layers (`session_id` for SoulRun, `user_id` for SoulACP) | **yes, when run as a program** — the tests drive it with a stand-in session |

Run them in an agent folder (one that holds `aiap/` or `aisp/`), with the human's words in a file or on standard
input - never on the command line, where the process list and the shell's history would show them:

```bash
python <path to>/minimal_host.py                  # no message: the guide
python <path to>/minimal_host.py message.txt      # one turn; the words from a UTF-8 file
python <path to>/minimal_host.py - < message.txt  # or from standard input
python <path to>/soulacp_host.py --provider claude --model claude-acp/sonnet message.txt
```

When a turn ends at a question for the human, run again with the answer in the file: `minimal_host.py` keeps the
conversation id `example`; `soulacp_host.py` takes the same `--conversation` (default `example`).

- SoulACP is not a dependency of SoulRun. `soulacp_host.py` imports it only when the file is run as a program, and
  running it calls a real model and uses that model's quota.
- Neither example reports sub-agents through the sub-agent doors of `soulrun.host` (see the README's
  [For Hosts](../README.md#for-hosts)), so both tell the engine that their model starts none
  (`host_tools={"agent": False}`), whatever the provider: the engine hands no node to a sub-agent, and a program
  meant for sub-agents runs every managed node in the main conversation. This flag is not a sandbox preventing a
  model CLI's own tools. A host managing sub-agents reports their real events; those reports remain diagnostic
  and do not prove original-child identity or replace explicit human authorization.
- `tests/test_examples.py` runs `minimal_host.py` as a program and drives `soulacp_host.one_turn` with a stand-in
  session, and `soulacp_host`'s program entry with a stand-in for SoulACP; no test calls a model.

How SoulBot's agents and host are wired to SoulRun is described in
[docs/guide/02-soulbot-integration.md](../docs/guide/02-soulbot-integration.md).

The model name above is an example identifier, not evidence of availability or qualification. Use a provider's
actual installed model list, normal authentication and explicitly approved permissions. Do not copy authentication
files into the agent or source tree. Input files, run data and provider logs can contain private text; protect them
and use synthetic material for public examples. Shell commands used to create input can retain their contents in
history even though SoulRun itself reads a file. See [SECURITY.md](../SECURITY.md).

The example commands marked `bash` use Bash input redirection; on PowerShell prefer the message-file argument
rather than `<`, and use `&` before a quoted executable path. See [INSTALL.md](../INSTALL.md#31-powershell与解释器选择).
These example hosts are not a claim that a production framework or every provider has passed real-model acceptance.
