# SoulRun Governance

SoulRun belongs to the SoulBot ecosystem (AISOP / AIAP / AISP / HSAW protocols + the SoulBot reference
runtime) and uses the same domain-separated stewardship. The separation isolates format, governance, and
runtime responsibilities; it does not imply that current maintainer control is decentralized. At this stage,
AIXP Labs core maintainers make repository decisions after public issue discussion where appropriate.

## The Tripartite Chain

The ecosystem separates program format, protocol governance and host execution across the domains below.
**This repository** governs the public executor at soulrun.dev: the AISOP execution engine inside one package,
with one call in front of it. SoulBot is one possible host, not a requirement for executing an AISOP program.
This repository is licensed under Apache 2.0; other protocols, hosts and programs retain the licenses declared
by their own authoritative metadata. This summary does not relicense them.

### 1. The Seed Layer (`aisop.dev`)

The origin of the format.

- **Responsibility**: Defines the underlying `.aisop.json` language specification, Mermaid graph parsing rules, and the System/User execution model.
- **Philosophy**: Neutral, static, foundational. Unconcerned with ethics or application logic.
- **License**: Apache 2.0 — unified across the AIXP protocol family.

### 2. The Authority Layer (`aiap.dev`)

The source of governance and the steward of Axiom 0.

- **Responsibility**: Maintains the AIAP and HSAW specifications, the quality gates, and enforces the Zero-Entropy and L0 isolation rules.
- **Philosophy**: Rigorous, uncompromising. Ensures that all compliant intelligence adheres to "Human Sovereignty and Wellbeing."
- **License**: Apache 2.0 — providing patent protection for the governance layer.

### 3. The Host Runtime Layer (`soulbot.dev`)

The reference host runtime and agent framework.

- **Responsibility**: The host manages model sessions, tools, channels, persistence and the human-facing interface.
  It connects the public executor through its documented host interface. A declaration in a program is not an
  operating-system permission or a provider's approval.
- **Philosophy**: Secure, observable, and explicit about trust boundaries. Native sandboxing, provider approvals
  and isolation of mutually untrusted actors belong to the host, provider and deployment.
- **License**: The SoulBot Host repository declares its own license.

### SoulRun's Public Executor (`soulrun.dev`)

SoulRun maintains a dependency-free public execution engine. It serves AISOP programs node by node, accepts
evidence and stops at human gates. The wrapper selects candidates and run folders and provides the same host
interface to command-line, SDK and other hosts. It never contacts a model or specializes execution for a
particular business package. Engine HSAW decisions, host authorization callbacks and native provider controls
are separate authority boundaries; none substitutes for another. Host observations alone do not authenticate
an original child or prove that its process exited.

## The Engine

The engine in `src/soulrun/soulrun_aiap` is SoulRun's. In this repository:

- The engine carries only the files it runs on, with its license and notice, and a manifest
  (`src/soulrun/engine_manifest.json`) records the SHA-256 of each file and an aggregate digest; a test fails on
  any difference, and `soulrun --verify-engine` checks an installed copy.
- The engine is never edited by hand. Changes are made in the engine's own source and brought in with
  `tools/upgrade_engine.py`, which checks a canonical source's identity, version, license and contract digests and
  copies its runtime files byte for byte, never rewriting a text or a version. Only an explicit `--legacy-clean`
  converts an old development tree (`tools/clean_engine.py`), and that cleaner refuses a canonical source.
- The fixed wording the model reads before an engine turn - the interruption blocks, and the entry-path form's
  entry block, assertions and opening instruction - was lifted from SoulBot's agent template by a tool
  (`tools/port_agent_text.py`) into `src/soulrun/_agent_text.py`; the context block, which is logic rather than
  wording, is re-implemented line for line in `src/soulrun/_blocks.py`. So SoulBot and SoulRun hand a model the same
  text there. SoulBot's current agent template hands every turn to SoulRun and
  carries none of that wording; it is kept in SoulRun as last generated from SoulBot's own text. The slim form's
  own texts - its entry block, assertion and opening instruction, the lines it adds after engine replies and, on a
  command line, the screen block - are SoulRun's.

## Axiom 0 Immutability

**Axiom 0: "Human Sovereignty and Wellbeing" is immutable.**

No release of any AIXP protocol (AISOP, AIAP, AISP, HSAW), the SoulBot reference runtime, or SoulRun may ever modify, weaken, or deprecate the core alignment to Human Sovereignty and Wellbeing. This constraint is absolute and non-negotiable.

For SoulRun this means, in particular: no change may let SoulRun answer a gate or a doubt for the human, invent the user's words, silently replace a program the human designated, or fall back to a default without saying so.

Any change request that is determined to compromise, dilute, or bypass Axiom 0 will be rejected regardless of performance benefits, commercial pressure, or technical convenience.

## Versioning

Changes to SoulRun follow Semantic Versioning (SemVer):

- **Major**: breaking changes to the call (`soulrun(...)` arguments, `Ctx` fields), the host doors (their names and arguments), the command-line options, SoulRun's own error codes, or the layout of `soulrun_cache_dir` (where it is, and where the runs go in it)
- **Minor**: backward-compatible additions
- **Patch**: bug fixes, documentation corrections, non-normative clarifications

The promise covers SoulRun's own surface only. What the engine makes changes with the engine version and is
outside it:

- `ctx.data`, the engine's own answer, handed over as it is
- the engine modules `host.engine()` reaches
- what the engine puts inside the dicts the host doors return
- the engine's own error codes, which a `SoulRunError` carries unchanged
- the files inside a run (`.execution_cache/<N>/`)

The experimental second-stage form (`inline_program`) is outside it too, and so is the wording of the slim form's
own texts, which follows the engine as the two are improved together. A new engine is always recorded in
[CHANGELOG.md](CHANGELOG.md), so a host that reads any of these knows when to check again.

The engine carries its own version (`soulrun.ENGINE_VERSION`), which changes only when the engine does. Every 1.x
engine preserves its inherited feature set; this does not guarantee execution or interpretation of every
historical record format. A version number alone does not identify an engine build: the manifest's digest does
(`soulrun --engine-info` shows it). An unfinished run is continued only by the exact engine build that began it;
a run begun under another build, even one with the same version, is not continued: a human turn is asked about
it, a machine turn is refused (see the README's section on the engine).

`python tools/check_docs.py --set-version X.Y.Z` sets SoulRun's version in the package and in the documents'
version lines (the footers, the contribution guides' stage lines, the opening lines of GUIDE and INSTALL).
`tools/upgrade_engine.py --engine-version` names the version of the engine being brought in (a canonical engine
must already carry it) and writes it in the documents' engine-version lines (DEPENDENCIES, in both languages, and
the opening line of GUIDE). Any other mention of a version in the documents (such as the README's test baseline,
the release notes and the CHANGELOG) is changed by hand. Changes are recorded in
[CHANGELOG.md](CHANGELOG.md).

The Axiom 0 immutability constraint supersedes all versioning rules.

## Protocol Steering

The AIXP protocols (AISOP, AIAP, AISP, HSAW), the SoulBot reference runtime, and SoulRun are maintained by AIXP Labs across the domains:

| Domain | Role | Scope |
|--------|------|-------|
| `aisop.dev` | Format Steward | `.aisop.json` specification, field definitions |
| `aiap.dev` | Governance Steward | Protocol rules, quality standards, security model |
| `soulbot.dev` | Runtime Steward | Reference implementation, agent framework, tool resolution |
| `soulrun.dev` | Engine Steward | The AISOP execution engine, the one call, candidate and run-folder selection, host doors, engine integrity |

### Decision Process

1. **Proposals**: Open a GitHub Issue describing the problem, affected domain,
   compatibility impact, and evidence. Labels are maintainer-managed and not a
   prerequisite for filing.
2. **Discussion**: Maintainers choose a review window proportional to risk.
   There is currently no guaranteed minimum discussion period or SLA.
3. **Review**: Relevant maintainers review Axiom 0 alignment, technical
   soundness, security, evidence quality, and backward compatibility.
4. **Decision**: Current-stage decisions are recorded by AIXP Labs maintainers.
   Cross-domain changes — for example a change that needs the engine to behave
   differently — require review by each affected domain steward.
5. **Documentation**: Normative changes update the documentation, versioning
   rationale, migration notes, and verification evidence. An ADR is required
   only after the repository adopts an ADR process and location.

## Release Evidence and Authorization

Record which component enforced a decision and preserve its actual outcome. A format declaration, permission
field or model statement is not an operating-system restriction, successful execution or provider approval.
Synthetic controls are not real model tests, exact-byte inheritance is not a fresh execution, and an isolated
candidate is not a deployed release. Keep failures, skips, missing historical inputs and untested hosts explicit.

Review source and package changes against their canonical inputs. Preserve immutable protocol snapshots and
historical records; keep sensitive incident evidence private under [SECURITY.md](SECURITY.md). Local cleanup
does not revoke a credential, establish that remote copies disappeared or authorize replay of model/tool work.
Publication, deployment and service actions require the responsible operator's explicit scope; approving a
code change or discussing a contribution is not operational authorization.

During V1.0.0 release preparation the version stays fixed, but changed source, README metadata or package
bytes require their own evidence. Preserve prior artifacts and identify new ones by SHA-256; unchanged runtime
files do not qualify new documentation or imply that an old artifact contains it. See
[Verification Scope](docs/verification-1.0.0.md). No documentation edit authorizes publication or deployment.

## Communication

- **GitHub Issues**: Primary public channel for proposals, questions, and
  compatibility discussion
- **Private security reports**: Use the process in [SECURITY.md](SECURITY.md);
  do not disclose vulnerability details in governance issues
- **Decision records**: Release notes, documentation diffs, and linked issues
  are the current record. ADRs may be introduced later with an explicit policy.

---

Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulRun V1.0.0. www.soulrun.dev
