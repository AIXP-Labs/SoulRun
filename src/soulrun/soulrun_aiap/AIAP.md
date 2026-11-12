---

# AIAP Governance Contract
# Governance Fields (6 required)
protocol: "AIAP V1.0.0"
authority: aiap.dev
seed: aisop.dev
executor: soulrun.dev
axiom_0: Human_Sovereignty_and_Wellbeing
governance_mode: NORMAL
governance_hash: "fe447f5dc20483e7"
# Project Fields (8 required)
name: soulrun_aiap
version: "1.0.0"
pattern: A
flow_format: "mermaid"
summary: "AISOP program executor (v7 core): single node protocol next-node / node-commit, Python-held run state, Python-rendered public blocks, machine-detected human gates, audited resume. Runs AIAP and AISP programs without modifying them."
tools:
  - name: file_system
    required: true
    annotations:
      read_only: false
      destructive: false
      idempotent: false
      open_world: false
modules:
  - id: soulrun_aiap.main
    file: main.aisop.json
    nodes: 6
    critical: true
    idempotent: false
    side_effects: [file_write]
    description: "Entry, Router.match, Router.cache-setup, node loop, Engine.execute-report, `Engine.final-answer`, error report."
  - id: soulrun_aiap.agent
    file: agent_engine.aisop.json
    nodes: 6
    critical: true
    idempotent: false
    side_effects: [file_write]
    description: "Sub-agent entry: claim the root ticket, execute its reached subtree inline with the shared node kernel, commit each node and return ordered public references; never spawns or answers human gates."
license: Apache-2.0
copyright: "Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev"

# Optional Fields

description: "v7 core rewrite of the soulrun_aiap. The engine prompt is one AISOP file; runtime authority is the Python code in python_tools/ (next_node, node_commit, gate_answer, render) which owns state, cache files and rendering. See the 04 series documents 01 (development plan) and 02 (protocol conformance mapping) for design and conformance."
tags: [execution-engine, executor, node-protocol, decision-gate, resume]
author: SoulRun.dev
tool_dirs: []
capabilities:
  offered: [aisop_execution, node_protocol, machine_owned_state, python_rendering, human_gate_detection, sys_call_permission_precheck, audited_resume, crash_recovery, conformance_check]
  required: [file_system]
trust_level: 3
permissions:
  file_system:
    scope: "./.execution_cache/ + target workspace"
    operations: ["read", "write"]
  shell:
    allowed: false
  network:
    allowed: false
runtime:
  timeout_seconds: 300
  max_retries: 3
  token_budget: 256000
  idempotent: false
  side_effects: [file_write]
status: draft
discovery_keywords: [engine, executor, router, execute, node, commit, gate, resume]
min_protocol_version: "AIAP V1.0.0"
identity:
  program_id: dev.soulrun.soulrun_aiap
  publisher: "AIXP Labs AIXP.dev | SoulRun.dev"
  verified_on: "2026-09-05"
---

## Governance Declaration

soulrun_aiap V1.0.0 is an AIAP V1.0.0 program (Pattern A) aligned with Axiom 0.
It is the executor (`executor: soulrun.dev`) for AIAP and AISP programs: it serves each
program node to the model with its steps, input authority, permission pre-check and gate
detection, and it holds all run state itself. Human gates declared by a program
(`sys.io.confirm` / `sys.io.input` / `sys.io.select`, `user_gate`) are detected by the
engine and answered only through the host's `gate-answer` entry; the model never decides
for the user. The engine never modifies its own governance files or those of the programs it
runs (NO_SELF_MODIFY); writes are limited to the run cache directory and, for generator
programs, their declared `target_aiap_dir`.

## Executor Runtime Notice

`python_tools/` contains the executor runtime (next_node, node_commit, gate_answer, render,
lib). It is not a Pattern G `tool_dirs` package: the code is not offered to business programs
as tools, it is invoked by the host (`agent.py`) and by the model as the engine's own
protocol. Therefore `tool_dirs: []` and `pattern: A`. `tools/aiap_conformance_check.py` is a
read-only conformance checker for this directory and for target programs.

## Feature Overview

| Component | Responsibility |
|-----------|---------------|
| main.aisop.json | Engine prompt: entry, Router.match, Router.cache-setup, node loop, Engine.execute-report, `Engine.final-answer`, error report |
| python_tools/next_node.py | Returns the current node: steps (classified), reserved keys, topology, input authority, gate, budget, resume kind |
| python_tools/node_commit.py | Validates the model's payload (schemas/commit.v1.json), writes the node cache and the index under a file lock, mints gates, derives public blocks |
| python_tools/gate_answer.py | Host-only entry for human answers: alias/number/free-text parsing, cancel and terminate, audit |
| python_tools/lib/render.py | Derives PLAN, node-info, menu and final-answer blocks from cache files |
| schemas/ | commit.v1.json (payload), index.v1.json (run index), final_answer.v1.json (assembled final artifact) |
| tools/aiap_conformance_check.py | C-01…C-11 self checks; program load checks and doc 02 §2.2 scans |

## Usage

Entry file: `main.aisop.json`. Use the SoulRun CLI or SDK to prepare a turn and obtain
its program form and run binding; any compatible host can supply model access.
The host uses the returned instruction and context, not a framework-specific environment switch.
The child actor uses `agent_engine.aisop.json` under the existing dispatch contract.
Tools: file_system only. No shell, no network from the engine itself; business programs use
the host's tools under their own declared permissions, which the engine pre-checks.
Conformance: `python tools/aiap_conformance_check.py` (self) and
`python tools/aiap_conformance_check.py <program_dir> --mode program`.

Development tests are outside the installed engine. Follow the source repository's
CONTRIBUTING guide for development dependencies and test commands; development environments
and test suites are not shipped in the engine. The independent JSON Schema validator
is test-only; runtime remains standard-library-only.

## Current Recovery Policy (SoulRun V1.0.0 candidate)

`SOULBOT_RESUME_INTERRUPTED_RUNS` defaults to false. Only explicit true/1/yes/on enables automatic interrupted-run re-entry; false/0/no/off, absence, empty/invalid settings and policy-read failure never grant automatic authority. Existing user environment files are not rewritten.

Original CLI transition intents are persisted before cache/index writes. A complete, unchanged orphan proof can forward only its original Engine bookkeeping: false asks a machine recovery question, explicit true permits one automatic attempt and a host notice. An unsuccessful attempt requires a new actual human decision; damaged or incomplete proofs stay paused. The switch never answers business HSAW gates, repeats business computation, issues a child, overrides a human Stop or migrates an old run. Accepted-reply recovery keeps its separately authorized bounds.

Attempt receipts and present acceptance are separate facts. Reports disclose both; a queued callback notice is not delivery, and its exact committed host event is observed later. Main and child still use the same inline Engine transition. No ACP Part is edited.

## SoulRun Version Policy

The product name is `soulrun_aiap`, homepage https://soulrun.dev. Public version remains **V1.0.0** (`1.0.0` in machine fields) before initial release. Candidate manifests identify tested bytes without changing the public version.

[Apache License 2.0](https://github.com/AIXP-Labs/SoulRun/blob/main/LICENSE) - Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev

Align Axiom 0: Human Sovereignty and Wellbeing. Version: AIAP V1.0.0. www.aiap.dev
