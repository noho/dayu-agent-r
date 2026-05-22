# Phase 12 Aggregate Deepreview — DS Adversarial Review

**Date:** 2026-05-21
**Reviewer:** AgentDS (aggregate review worker)
**Gate:** Phase 12 aggregate deepreview / phase acceptance validation
**Verdict:** PASS

## Scope

Full Phase 12 accepted work on branch `docs/phase12-design-discussion`. Key commits:

- `1aae08d` feat(runtime): add Phase 12 tools discovery slice
- `b4b3831` feat(runtime): add tools discovery provenance digest
- `3c7631d` feat(runtime): add config loader typed views
- `914ad1e` feat(runtime): add scene prepare assembly
- `6327a42` fix(runtime): preserve scene temperature profile
- `2912271` feat(config): migrate legacy scene assets
- `ba58d8a` test(runtime): close Phase 12 boundary coverage
- `917cda2` test(contracts): sync source ref exports
- `11cc003` docs: record Phase 12 aggregate fix gate

## Primary Questions — Answers

### Q1: Does the implementation satisfy design.md Phase 12 boundaries without modifying Host public interface?

**Yes.** `dayu/host/__init__.py` has zero diff from `main`. `open_host(options)`, `OpenHostOptions`, `HostToolingOptions` fields, `SubmitFollowupRequest` fields, and Host handle methods are all untouched.

The only change to `dayu/host/tooling.py` is canonical ownership migration: `ToolBundleSourceKind` and `ToolBundleSourceRef` class definitions moved to `dayu/contracts/tool_source.py`; `dayu/host/tooling.py` now imports them from `dayu.contracts`. `dayu/host/__init__.py` already re-exported these types and continues to export the same canonical types — this is the design-prescribed ownership down-move (design.md §18.1, plan §2, slice 1 §3), not a wrapper/facade pattern. No new, deleted, renamed, or reshaped Host public fields.

### Q2: Does dayu.runtime remain layer-neutral?

**Yes.** AST-based import boundary tests (`tests/runtime/test_import_boundary.py`, `tests/contracts/test_import_boundary.py`) confirm:

- `dayu.runtime.tools_discovery` — only imports from `dayu.contracts` and stdlib (`hashlib`, `importlib`, `json`, `collections.abc`, `dataclasses`, `types`, `typing`)
- `dayu.runtime.config_loader` — only imports from `dayu.contracts` and stdlib (`json`, `collections.abc`, `dataclasses`, `enum`, `pathlib`, `typing`)
- `dayu.runtime.scene_prepare` — only imports from `dayu.contracts` and stdlib (`hashlib`, `json`, `re`, `collections.abc`, `dataclasses`, `enum`, `pathlib`, `typing`)
- `dayu/contracts/tool_source.py` — only stdlib (`dataclasses`, `enum`)

No imports from `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins`, or any business tool package. No imports from `aiohttp`, `requests`, or `httpx`.

### Q3: Are ToolsDiscovery, ScenePrepare, and ConfigLoader responsibilities separated correctly?

**Yes.** The three components form an assembly pipeline with no cross-coupling:

- `ToolsDiscovery` (`dayu/runtime/tools_discovery.py`) — resolves provider callables from explicit import paths or package entry points; invokes providers; validates provider identity, empty output, and reserved tool names; computes SHA-256 content digest over declarations (not callables); aggregates into `ToolBundle`. Does NOT import config files, scene manifests, or prompt fragments.
- `ConfigLoader` (`dayu/runtime/config_loader.py`) — reads four typed config files (`models.json`, `execution_profiles.json`, `host_runtime.json`, `tool_discovery.json`); applies workspace overlay per file type (map fields merged by id, workspace record replaces package default); resolves single-inheritance `extends`; validates cross-file references. Does NOT resolve provider callables, read scene manifests, interpret prompt fragments, resolve env vars, or construct Host.
- `ScenePrepare` (`dayu/runtime/scene_prepare.py`) — reads scene manifest JSON from caller-supplied root; resolves single-inheritance extends chain; loads directly-referenced prompt fragment files; validates path containment (no escape); renders `{{slot_name}}` placeholders with typed string context slot values; computes scene assembly digest. Does NOT read `ConfigLoader` output, discover tools, or import config models. Receives `SceneToolCatalog` (name+tags only) from Service.

Each module's `__all__` exports only its own types; no module imports another runtime assembly module.

### Q4: Are config/prompt assets and README docs consistent with current code?

**Yes.** Legacy files confirmed deleted:

- `dayu/config/llm_models.json` — REMOVED
- `dayu/config/run.json` — REMOVED
- `legacy_config_file_names()` returns `frozenset({"llm_models.json", "run.json"})` for diagnostic use only; no code reads these paths

New config files present and loadable (verified via `ConfigLoader().load()`):

- `models.json` — 2 model configs
- `execution_profiles.json` — 1 profile, 2 runner options profiles, 1 agent policy profile
- `host_runtime.json` — 1 Host runtime profile
- `tool_discovery.json` — 1 provider spec

Scene manifests (14 manifests in `dayu/config/prompts/manifests/`) use `schema_version: 1`, follow the new schema with required fields (`scene`, `version`, `description`, `capability_tags`, `extends`, `model`, `runtime`, `conversation`, `tool_selection`, `defaults`, `fragments`, `context_slots`). Prompt fragments live in `dayu/config/prompts/base/` (4 files) and `dayu/config/prompts/scenes/` (11 files). Task prompts, contract files, and workflow artifacts are not migrated.

README updates verified:
- `dayu/README.md` — added `tools_discovery`, `config_loader`, `scene_prepare` to runtime capabilities list; updated `dayu.contracts` description to mention tool source refs; updated extension entry points. No process state, future plans, or discussion records.
- `dayu/config/README.md` — rewritten for new four-file config schema; old `llm_models.json`/`run.json` documentation removed; legacy removal noted; overlay rules documented.

### Q5: Are tests and pyright coverage sufficient?

**Yes.** All validation passes:

| Check | Result |
|---|---|
| `pytest tests/runtime -q` | 174 passed |
| `pytest tests/contracts tests/engine/test_config_models.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | 69 passed |
| Total | **243 passed** |
| `pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host tests/engine/test_config_models.py` | **0 errors, 0 warnings, 0 informations** |
| Runtime coverage | **92%** (target: >= 80%) |

Per-module coverage:

| Module | Coverage |
|---|---|
| `dayu/runtime/tools_discovery.py` | 94% |
| `dayu/runtime/config_loader.py` | 94% |
| `dayu/runtime/scene_prepare.py` | 91% |

Test coverage spans: provider resolution (import path, entry point), digest stability, reserved tool name validation, duplicate detection, disabled provider, empty provider with/without allow_empty; config loading (four file types), workspace overlay, extends single inheritance, cycle detection, missing field detection, cross-file reference validation; scene manifest parsing, single inheritance, fragment loading, context slot rendering, tool selection (all/none/select modes), path containment, legacy asset migration.

## Findings

### Blocking (0)

None.

### High (0)

None.

### Medium (1)

**P12-AGG-M1 — `_canonical_json_digest` / `_normalize_json_value` duplication between `tools_discovery.py` and `scene_prepare.py`**

- `tools_discovery.py:531-551` and `scene_prepare.py:1189-1205` implement identical JSON canonicalization → SHA-256 digest logic.
- `tools_discovery.py:554-573` and `scene_prepare.py:1218-1237` implement identical `_normalize_json_value` (minor: `tools_discovery.py` uses `dict` iteration with `Mapping` check, `scene_prepare.py` uses `sorted(keys())`).
- **Risk:** Future digest algorithm changes must be applied in two places; drift between the two could produce inconsistent digests. Currently both produce compatible output, so no correctness bug.
- **Recommendation:** Extract shared `_canonical_json_digest` and `_normalize_json_value` into a new `dayu/runtime/_digest.py` private module, used by both `tools_discovery` and `scene_prepare`. Not blocking for draft PR; can be done as a follow-up cleanup slice.

### Low (2)

**P12-AGG-L1 — `scene_prepare.py` `_normalize_json_value` sorts keys at line 1232, `tools_discovery.py` version does not sort (line 568-571)**

- `scene_prepare.py` sorts `value.keys()` before iterating; `tools_discovery.py` iterates `value.items()` without sorting.
- Both callers (`_canonical_json_digest`) already pass through `json.dumps(..., sort_keys=True)`, so the final output is identical. The in-function sorting in `scene_prepare.py` is redundant but harmless.
- **Risk:** None — `json.dumps(sort_keys=True)` is the canonical sort step. The extra sort only affects intermediate dict construction order, not final JSON output.

**P12-AGG-L2 — `config_loader.py` `_TOOL_DISCOVERY_SOURCE_KINDS` explicitly excludes `SERVICE_COMPOSITION`**

- `config_loader.py:37-43` defines `_TOOL_DISCOVERY_SOURCE_KINDS` as `{EXPLICIT_PROVIDER, CONFIG_BINDING, PACKAGE_ENTRYPOINT}`, excluding `SERVICE_COMPOSITION`.
- `_parse_tool_bundle_source_kind` at line 1639-1656 rejects `SERVICE_COMPOSITION` for tool discovery providers — this is intentional: `SERVICE_COMPOSITION` is for Service-managed tool assembly, not for declarative config-based discovery.
- **Risk:** If future Service workflow needs to reference `SERVICE_COMPOSITION` tools in `tool_discovery.json`, the validation will reject it. This is correct for Phase 12 scope; the design explicitly states Service composition is a Service responsibility.
- **Status:** Design-consistent, not a bug. Flagged for awareness.

## Stop Conditions Audit

All plan §9 stop conditions checked; none triggered:

- [x] No Host public command/handle/options/request field changes
- [x] No Engine execution path or Runner protocol state machine changes
- [x] No `dayu.fins.storage` access
- [x] No workflow/Skill semantics, step graph, checkpoint/resume, retry/replay, failure classification
- [x] No new per-run override fields beyond `system_prompt`, `tool_names`, `runner_spec`, `runner_options`, `agent_policy`
- [x] `dayu.runtime` does not import Host/Engine/Service/UI/Fins/business tools
- [x] Legacy asset migration did not require task prompts, contract files, or workflow artifacts

## Validation Run (Independent Re-execution)

```text
$ source .venv/bin/activate && pytest tests/runtime -q
174 passed in 3.94s

$ source .venv/bin/activate && pytest tests/contracts tests/engine/test_config_models.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q
69 passed in 0.83s

$ source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host tests/engine/test_config_models.py
0 errors, 0 warnings, 0 informations

$ source .venv/bin/activate && pytest tests/runtime --cov=dayu.runtime --cov-report=term
TOTAL 2071 170 92%
```

All results match controller-reported validation.

## Residual Risks

1. **Service/composition root integration untested.** Phase 12 delivers the three runtime assembly components but does not include a real Service that wires `ToolsDiscovery` → `ScenePrepare` → `ConfigLoader` → `open_host()`. The plan explicitly defers Service workflow to future phases. The typed outputs (dataclass instances with frozen/slots) are well-formed and importable, but end-to-end assembly correctness can only be verified when a real Service wire-up exists.

2. **`SERVICE_COMPOSITION` not exercised in discovery.** The `ToolBundleSourceKind.SERVICE_COMPOSITION` enum value is defined in contracts but has no consumer in Phase 12 code. Its semantics will be defined when Service workflow is implemented.

3. **Workspace config overlay with real paths.** `ConfigLoader` tests use test fixture directories; real workspace overlay with user-provided paths has not been integration-tested. The overlay logic is covered by unit tests with controlled file contents.

4. **Prompt fragment rendering with non-ASCII context slot values.** The `{{slot_name}}` regex replacement is deterministic and covered by tests, but the full Unicode/CJK surface in prompt fragments (Chinese financial report text) is tested only through migrated scene asset fixtures, not through exhaustive fuzzing.

## Conclusion

Phase 12 implementation satisfies all design.md Phase 12 boundaries. Host public interface is unmodified. `dayu.runtime` remains layer-neutral. `ToolsDiscovery`, `ScenePrepare`, and `ConfigLoader` are correctly separated with no cross-coupling. Config assets, prompt assets, and README docs are consistent with current code. All 243 tests pass; pyright reports 0 errors; runtime coverage is 92%.

**Verdict: PASS.** Ready for ready-to-open-draft-PR gate.
