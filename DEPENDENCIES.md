# SoulRun Dependency Policy and Verified Baseline

Dependency declarations and selected upstream metadata reviewed: 2026-11-11.

`pyproject.toml` is authoritative for dependency constraints. This inventory records the
runtime promise (no dependencies), the development and release tools, the engine, what the
engine's text expects to find on a machine, the CI pins, and the commands required to reproduce checks.

For the Chinese version, see [DEPENDENCIES_CN.md](DEPENDENCIES_CN.md).

## 1. Version Policy

- SoulRun has **no runtime dependency**. `[project].dependencies` is empty, a test keeps it empty, and
  `tools/check_dist.py` fails a wheel that declares one. The engine uses the Python standard library only, so
  compatible Python interpreters can run its tools without extra runtime libraries.
- Development and release tools are optional extras (`dev`, `release`). They declare a compatibility floor plus the
  next breaking-major upper bound (for Ruff, still at 0.x, the next minor release). A declared floor is not
  evidence that every allowed combination was tested. `tzdata` holds only time-zone data and is versioned by
  date: it has a minimum only.
- Every version range lives in `pyproject.toml`, the one place Dependabot updates Python version ranges (it also
  updates the Actions pins in the workflow; see section 6). CI installs the release tools from it through
  `tools/extra_requirements.py`, and the test tools as the `dev` extra: the source tree's in the test job, the
  built wheel's in the package job. Neither the workflow nor an install command in INSTALL.md, the contribution
  guides or this document writes a range of its own; a test checks this.
- The engine is pinned by content, not by a package version: `src/soulrun/engine_manifest.json` records its
  version and the SHA-256 of every file.
- GitHub Actions are pinned to immutable commit SHAs; the release tags are retained in comments for
  auditability. Their upstream tags and commits were checked independently; another project's CI does not qualify SoulRun.
- Dependency tables record declared compatibility floors, not a lock. Capture a concrete environment with
  `python -m pip list --format=freeze` when exact evidence is required.

## 2. Runtime Matrix

| Surface | Supported range | Versions verified locally |
|---|---|---|
| SoulRun Python | `requires-python = ">=3.11"` declares a minimum, not an upper bound | November 11 local SDK source checks on Windows 3.12.9 and Ubuntu 3.11.18/3.12.3/3.13.18/3.14.10/3.15.2; exact head and inheritance below. Older-head evidence is retained separately |
| CI matrix | tests: Ubuntu and Windows × 3.11, 3.12, 3.13, 3.14, 3.15; package build and tests of the installed wheel: Ubuntu and Windows × 3.12 | 12 configured jobs in [`.github/workflows/ci.yml`](.github/workflows/ci.yml); the two added 3.15 jobs await hosted execution. The preceding 10-job result is dated in [Verification Scope](docs/verification-1.0.0.md) |
| The `python` a model's shell finds (every engine tool in the entry-path form; a sub-agent's engine tools and a program's own `python ...` tools in every form) | a compatible Python; use an interpreter meeting SoulRun's declared minimum, and any program-specific requirements | reported by `soulrun --doctor`: none found is a `FAIL` in every form; discovery alone does not qualify a business program |

The November 11 checks on digest `9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`
ran each Ubuntu SDK line separately (911 passed / 4 skipped / 915 total) and Windows 3.12.9
(912 passed / 3 skipped / 915 total). Windows 3.11–3.15 SDK and cold-install evidence is inherited from
the exact unchanged payload. These local Python 3.15 results are not hosted-CI evidence or a support-policy change.
macOS was not tested. Exact Engine counts, QA-only composition and later release-tool revisions are in
[Verification Scope](docs/verification-1.0.0.md), not a new pass for every later source edit.
The engine Markdown and standalone caller guide are shipped inputs too. A same-version documentation
revision does not automatically inherit an installed artifact's, a model run's or another platform's qualification.

## 3. SoulRun Python Dependencies

### Core runtime

None. Installing SoulRun installs SoulRun and the engine files listed in its manifest, nothing else.

### Development and release groups

| Extra | Package | Constraint | Recorded tool version (2026-11-11 review) |
|---|---|---|---|
| `dev` | coverage[toml] | `>=7.15.2,<8` | 7.17.2 (Windows QA) |
| `dev` | mypy | `>=1.19.1,<2` | 1.20.2 (Windows QA) |
| `dev` | pytest | `>=9.1.1,<10` | 9.2.0 (Windows QA) |
| `dev` | pytest-timeout | `>=2.4.0,<3` | 2.4.0 |
| `dev` | ruff | `>=0.16.0,<0.17` | 0.16.10 |
| `dev` | tzdata | `>=2024.1` | 2026.6 (Windows QA) |
| `release` | build | `>=1.5.0,<2` | 1.5.0 (prior frozen-artifact build environment) |
| `release` | twine | `>=7.0.0,<8` | 7.0.0 (isolated strict-validation environment) |

- **tzdata** gives `zoneinfo` its data where the system has none (Windows), so a development environment reads
  named zones as a run does. No test needs it: without it the engine falls back to local time and
  `soulrun --doctor` warns.
- **twine 7.0.0** strictly checked the prior frozen wheel and source archive, not artifacts for later prose changes.
- The build backend is `hatchling>=1.31.0,<2`; the recorded build environment used 1.32.4.
- These are separate recorded environments, not one tested lock. The 2026-10-14 clean Python 3.11.17
  environment previously resolved coverage 7.16.2, pytest 9.1.1, pytest-timeout 2.4.0, Ruff 0.16.10,
  tzdata 2026.5, build 1.6.1 and Twine 7.0.0; mypy 1.19.1 was in a separate Python 3.12 environment.
  Those historical observations are retained, not reverified by this review.

Install and validate the full development environment with:

```bash
python -m pip install -e ".[dev,release]"
python -m pip check
```

## 4. The Engine

| Item | Value |
|---|---|
| Engine | SoulRun engine `1.0.0` (`soulrun.ENGINE_VERSION`) |
| Location | `src/soulrun/soulrun_aiap/`: the runtime files only, every one installed with the package |
| Record | `src/soulrun/engine_manifest.json`: version, source form (`canonical` or `legacy-clean`), the SHA-256 of every file and the digest of the whole list |
| Fingerprint | `soulrun --engine-info`: `installed_digest` as the manifest records it, and `installed_digest_now` worked out from the files themselves |
| Engine runtime dependencies | none (standard library only) |
| Checks | `tools/sync_engine.py --check` (files against the manifest), `tools/sync_engine.py --check-release` (read-only release check: source form, exact runtime files and digests, version, privacy), the engine's own AIAP conformance check (`tools/aiap_conformance_check.py` inside the engine) |

`soulrun --verify-engine` checks an installed copy. A newer engine is brought in only with
`tools/upgrade_engine.py`: a canonical engine is copied byte for byte after its identity, version, license and
contracts are checked; an older development tree goes through the cleaner (`tools/clean_engine.py`) only when
`--legacy-clean` is given, and its history check stays strict. The engine it replaces is kept under
`.engine_backups/` (never packaged), and `--restore` puts a kept one back.

## 5. What the Engine's Text Expects on a Machine

These are not Python dependencies of SoulRun, but a run needs them:

| Need | Why | Check |
|---|---|---|
| A `python` on the model's `PATH` | the model runs every engine tool with it in the entry-path form, a sub-agent's engine tools in every form, and a program's own tools written as `python ...` in every form; only the main conversation of the slim form (the default) names the interpreter running SoulRun by its full path instead | `soulrun --doctor` (`python for the model`, `program form`; no `python` is a `FAIL` in every form) |
| Time-zone data on Windows, in the Python running SoulRun and in the model's `python` | the engine reads a provider's named reset zone | `soulrun --doctor` (`time zones`) |
| Long paths, or a short `soulrun_cache_dir`, on Windows | a run nests files about 130–150 characters deep, by the programs' node names | `soulrun --doctor` (`path length`) |
| A host with model access | SoulRun never calls a model | — |

## 6. GitHub Actions

| Action | Release | Immutable SHA |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-python | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |

Dependabot checks the Python extras and GitHub Actions weekly. Updates still require the full CI matrix; an
automated proposal is not proof of compatibility. Dependabot does not touch the engine.

The 2026-11-11 read-only review matched both pins to their upstream tags. Fifteen selected direct-tool
version queries to the [OSV batch API](https://google.github.io/osv.dev/post-v1-querybatch/) returned no
advisory IDs. This is not a full transitive-environment audit, a guarantee of no vulnerabilities, or
evidence that every allowed future version works. No constraints were changed merely to refresh dates.

## 7. Required Verification

The same steps as CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

```bash
# Python - CI's test job (Ubuntu and Windows, Python 3.11 to 3.15)
python -m pip install -e ".[dev]"
python -m pip check
python tools/sync_engine.py --check
python tools/sync_engine.py --check-release
python src/soulrun/soulrun_aiap/tools/aiap_conformance_check.py src/soulrun/soulrun_aiap
python tools/build_engine_node.py --check
python -m ruff check src tests tools examples
python tools/check_docs.py
python -m pytest -rs

# Package - CI's package job (Ubuntu and Windows, Python 3.12), in a checkout with no earlier dist/
python -m pip install -e ".[release]"     # CI installs the same extra through tools/extra_requirements.py
python -m build
python tools/check_dist.py                # every soulrun-* file in dist/
python -m twine check --strict dist/*
python -m venv <clean env>
<clean env>/bin/python -m pip install "dist/soulrun-<version>-py3-none-any.whl[dev]"
<clean env>/bin/soulrun --version
<clean env>/bin/soulrun --verify-engine
SOULRUN_TEST_INSTALLED=1 <clean env>/bin/python -m pytest -rs
```

On Windows, use `Scripts\` in place of `bin/`. A release is built into a new, empty folder, its two files
checked by name (with `twine check --strict`), their sizes and SHA-256 recorded, and only those two files
uploaded, never a wildcard: see [INSTALL.md](INSTALL.md), sections 7 to 9. Uploads to TestPyPI and PyPI are
made by a maintainer, by hand.

## 8. Upgrade Checklist

1. Verify direct releases against the authoritative package registry and upstream release pages.
2. Update constraints in `pyproject.toml`; never add a runtime dependency.
3. Read breaking-change notes for every major upgrade.
4. Run Windows and Linux tests, all supported Python lines, documentation validation, and the package
   smoke test (tests against the installed wheel).
5. For a newer engine: `python tools/upgrade_engine.py --from <engine tree> --engine-version X.Y.Z --dry-run`
   first, then the upgrade, then SoulRun's tests and a package build; note the engine change in
   [CHANGELOG.md](CHANGELOG.md) and date the README's Verified Test Baseline anew.
6. Update this document and `DEPENDENCIES_CN.md` in the same change.
