# WU-SEMANTIC-OWNERSHIP-01 / R04-S1 Controller validation

## 1. Gate identity and verdict

- Umbrella WU: existing `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Remediation sub-WU: R04 `awaiting provider resolution composition`.
- Accepted plan: `983070dd1d56490d23529970960349a3df3e9787`.
- Implementation base and current HEAD: `a4ffd7641c8f114e987972d77572c2c2b4a8202f`; HEAD did not move.
- Implementation handoff: `docs/reviews/wu-semantic-ownership-01-r04-s1-implementation-codex.md`.
- Controller verdict: **FAIL / FIX_REQUIRED_BEFORE_DUAL_CODE_REVIEW**.

The implementation correctly places provider mode, runtime policy, Host execution, and Service composition at their adjudicated owner boundaries. Independent test, coverage, type, source, security, README, and real public smoke gates all pass. One owner-propagation correctness finding remains: the newly introduced typed Fins awaiting metadata can be silently dropped by existing derived `ServiceDiscoveredTools` construction. Code review is not authorized until this finding is fixed and Controller re-validation passes.

## 2. Owner and design validation

Controller read the full accepted plan, implementation artifact, production diff, tests, README diff, and relevant design truth. The following contracts are correct and remain accepted:

1. Fins owns the unique strict `AwaitingResolutionMode` enum/parser; the three direct providers and Service provider-assembly boundary reuse that parser without a second raw-mode normalizer.
2. `host_runtime.json` owns the complete required twelve-field deployment snapshot; ConfigLoader performs only layer-neutral exact-shape typed parsing and has no reverse dependency.
3. Host policy values, `WaitPoller`, and `WaitPollerSupervisor` have no deployment defaults, no no-argument policy construction, and no `None` fallback.
4. Service maps typed provider modes to binding policy, partitions activation and poll registries, projects the runtime snapshot one-to-one, rejects callback before Host open, and no longer derives poller authority from scene or entrypoint type.
5. No Host public API/open_host, Engine, callback transport, R05 state machine, Issue 175, unified authorization, permission schema, or other deferred owner was implemented.

## 3. Accepted Controller finding

### R04-S1-CV-F01 — typed awaiting metadata has a silent empty-default escape path

**Severity:** high correctness / semantic ownership.

**Direct evidence:** `ServiceDiscoveredTools` adds `_fins_awaiting_providers` with default `()`. The only production discovery constructor supplies the correct typed collection, but four existing consumers derive a new discovery result by manually copying the previously public fields:

- `tests/tools/test_combined_tools_acceptance.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

Because the new field has a default, those copies remain type-correct and silently replace the owner-produced collection with an empty tuple. Controller reproduced the mismatch from packaged config:

```text
discovered_typed_metadata 3
rebuilt_typed_metadata 0
active_fins_configs 4
```

The rebuilt object still carries the effective provider configs, Fins runtime, tool bundle, source refs, and provider reports. However, `_compose_options(...)` deliberately consumes only the typed collection. It therefore omits Fins wait binding, activation, poll registry, and poller policy even while the bundle can still expose awaiting tools. This is not a harmless fixture difference: it creates two inconsistent projections of the same discovery fact and can leave an accepted awaiting tool without its recovery composition.

**Root cause:** the new owner-produced projection was modeled as an optional/defaulted compatibility field rather than a required construction invariant. The default hides missing propagation from pyright and tests.

**Required owner fix:**

1. Make the Fins awaiting runtime/typed metadata state explicit and required in `ServiceDiscoveredTools`; do not retain an empty default that can mean either “no provider” or “caller forgot the fact”.
2. Derived discovery results must preserve the owner-produced state with `dataclasses.replace(...)` or an equally direct owner-preserving typed operation. They must not access private metadata types, reparse `effective_provider_configs`, or reconstruct mode/workspace/provider facts downstream.
3. Add an owner-level regression proving that replacing a discovered tool bundle preserves the same Host wait binding/registry/policy composition. Do not merely assert a private field or a fixture value.
4. Full pyright must make any future manual constructor omission fail at development time.

**Exact correction scope authorized by Controller:** this remains the same R04 unique atomic S1 and is not a new WU or slice. The accepted production allowlist remains unchanged. The following previously hidden consumers are added only for this correction:

- `tests/tools/test_combined_tools_acceptance.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

`tests/service/test_host_assembly.py`, the implementation artifact, a dedicated fix artifact, and responsibility-owned README text may be updated as needed. No other allowlist expansion is authorized.

## 4. Independent validation evidence

### 4.1 Affected tests and coverage

Controller reran the accepted-plan seventeen-target coverage session:

```text
508 passed, 3 warnings in 22.37s
```

Coverage JSON: `workspace/tmp/r04-controller-validation-coverage.json`. Every modified production Python file remains above the required threshold:

| file | coverage |
|---|---:|
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.54% |
| `dayu/fins/tools/download_provider.py` | 100% |
| `dayu/fins/tools/preprocess_provider.py` | 100% |
| `dayu/fins/tools/upload_provider.py` | 100% |
| `dayu/host/wait_adapter.py` | 90.41% |
| `dayu/runtime/config_loader.py` | 96.31% |
| `dayu/service/entrypoint_runtime.py` | 88.27% |
| `dayu/service/fins_wait_adapter.py` | 94.57% |
| `dayu/service/host_assembly.py` | 95.03% |

The three warnings are the existing edgar deprecation warnings and are not product failures.

### 4.2 Type, lint, whitespace, source, and scope gates

- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`.
- Ruff `F401,F841` over all changed Python/test/smoke files: pass.
- Tracked `git diff --check`: pass; the untracked handoff artifact has no whitespace error under an independent no-index check.
- Old scene helper, old entrypoint helper, no-argument Host policy, and ten Host deployment-default constants: zero production matches.
- Prompt assets and `execution_profiles.json` contain neither wait poller policy nor awaiting resolution mode.
- Anchored `dayu.runtime` reverse-import scan: zero matches.
- Added-line deferred-scope scan for authorization, permission, process isolation, observation-timeout, and lost-outcome implementation: zero matches.
- All 27 tracked paths plus the implementation artifact are within the then-authorized S1 allowlist.

### 4.3 Independent packaged public smoke

Controller ran:

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r04-controller-validation-smoke
```

Result: pass. It independently reproduced the three typed modes, complete twelve-field snapshot, prompt/interactive equality, manual/no-provider/provider-disabled/runtime-disabled no-poller cases, callback pre-open failure, and production public Host `not_ready=1 -> ready=1 -> SUCCEEDED` recovery.

This smoke validates the normal discovery path. It does not negate F01 because it does not derive a new `ServiceDiscoveredTools` object through the four hidden consumers.

## 5. README and residual boundary

The five README changes are within their documented reader/ownership boundaries and accurately describe the intended final contract. Root README and `dayu/README.md` correctly remain unchanged. F01 must be fixed before these texts can be treated as fully true for all current consumers.

Callback transport, external-network smoke, Host restart recovery, and R05 observation timeout/LOST semantics remain explicitly owned by their existing destinations. They are not current blockers and do not authorize scope expansion.

## 6. Next gate

Next gate is **AgentCodex R04-S1 Controller-validation fix**, followed by Controller re-validation. Only after re-validation passes may AgentMiMo and AgentDS receive the complete R04-S1 code-review gate. No implementation commit, R04 aggregate gate, R05 work, push, or PR is authorized.
