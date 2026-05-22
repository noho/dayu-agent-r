# Phase 12.3 Slice 4 Independent Code Review — AgentDS

Date: 2026-05-22  
Review Agent: AgentDS  
Scope: Slice 4 aggregate sweep — README sync, residual scan, full verification  
Verdict: **BLOCKED** — 1 HIGH finding in README.md

## 1. Verification Summary

| Check | Command | Result |
|---|---|---|
| Old field scan | `rg -n "agent_policy_profiles\|agent_policy_profile_id\|runner_option_hints.*max_tokens\|usage_enabled\|collect_usage\|include_usage\|supports_usage" dayu tests docs README.md` | All hits correctly categorized per plan rules (see §2) |
| JSON smoke | `python -m json.tool dayu/config/models.json` + `execution_profiles.json` | Both pass |
| Focused tests (config/assembly/service) | `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py -q` | 53 passed |
| Focused tests (host ingest/context budget) | `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q` | 62 passed |
| Focused tests (engine config/usage) | `pytest tests/engine/test_config_models.py tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q` | 15 passed |
| Import boundary / weak typing guards | `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py tests/engine/test_import_boundary.py tests/engine/test_weak_typing_guard.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` | 34 passed |
| **Total focused tests** | | **164 passed** |
| Pyright | `python -m pyright dayu/runtime dayu/service dayu/host dayu/engine tests/runtime tests/service tests/host tests/engine` | 0 errors, 0 warnings, 0 informations |
| git diff --check | | clean |

## 2. Old Field Scan Analysis

### 2.1 Production code — CLEAN

- `rg -n '"max_tokens"' dayu/config/` → no hits
- `rg -n 'agent_policy_profiles\|agent_policy_profile_id' dayu/config/ dayu/runtime/ dayu/service/` → no hits
- `rg -n 'usage_enabled\|collect_usage' dayu/config/ dayu/runtime/ dayu/service/ dayu/host/ dayu/engine/` → no hits
- `rg -n 'supports_usage[^_]' dayu/config/ dayu/runtime/ dayu/service/` → no hits
- `rg -n 'include_usage' dayu/config/ dayu/runtime/ dayu/service/ dayu/host/` → no hits

### 2.2 `include_usage` — Engine-gated only

All `include_usage` hits are correctly scoped:

- `dayu/engine/contracts/runner_spec.py:238-239` — `RunnerSpec.supports_stream_usage` docstring explaining gate behavior
- `dayu/engine/runners/openai/payload.py:358` — `{"include_usage": True}` only when `stream=True` AND `supports_stream_usage=True`
- `dayu/engine/runners/openai/_types.py:35` — internal OpenAI typed payload
- `tests/engine/runners/openai/test_stream_usage_capability_gating.py` — gate tests
- `dayu/engine/README.md:135` — Engine usage docs, no Host budget mention

No `include_usage` appears in config schema, runtime, service, or host layers. ✅

### 2.3 `agent_policy_profiles` / `agent_policy_profile_id` in docs

- `tests/runtime/test_config_loader.py:594-725` — negative tests only (expected per plan rules) ✅
- `docs/host/design.md`, `docs/host/phase12-3-*.md`, `docs/reviews/phase12-3-*.md` — design source, plan artifact, review artifacts (expected per plan rules) ✅
- `docs/host/implementation-control.md:1801` — stale reference, see §4 OBS-1
- `docs/host/runtime-assembly-followup-discussion.md` — historical discussion doc ✅

### 2.4 `usage_enabled` / `collect_usage` / `supports_usage`

All hits are in design/plan negative constraints or historical discussion docs. None in production config schema. ✅

## 3. Blocking Findings

### BLOCKER-1 [HIGH] — README.md:1145 misstates max_tokens as part of runner_option_hints

**File**: `README.md:1145`  
**Current text**:
```
temperature、max tokens、top-p 和 stream 属于 `models.json` 中 effective model 的 `runtime_hints.runner_option_hints`。`execution_profiles.json` 只保存默认 `model_id` 与 `runner_option_hint_id`。
```

**Why this is wrong**:

1. `dayu/runtime/config_loader.py:1163` — `_parse_runner_option_hint` exact fields are `frozenset({"temperature", "top_p", "stream"})`. `max_tokens` in a runner option hint is rejected as unknown field.
2. `tests/runtime/test_config_loader.py:575-587` — `test_old_runner_hint_max_tokens_fails_fast` explicitly tests that old `max_tokens` in runner hints fails fast.
3. `tests/runtime/test_config_loader.py:285` — asserts `"max_tokens" not in {field.name for field in fields(RunnerOptionHintConfig)}`.
4. The README's own workspace example at lines 1108-1123 correctly omits `max_tokens` from runner_option_hints.
5. `dayu/config/README.md:67` correctly states runner_option_hints "只包含 temperature、top_p 与 stream".

**Impact**: A user reading this sentence will believe they can configure `max_tokens` in their model's `runner_option_hints`. If they do, ConfigLoader will reject the config with an "unknown field" error. This creates a direct contradiction between the user manual and production behavior.

**Suggested fix**: Change line 1145 to:
```
temperature、top-p 和 stream 属于 `models.json` 中 effective model 的 `runtime_hints.runner_option_hints`；`max_tokens` 只保留给显式 per-run 或 provider adapter override，不在默认模型 hint 中配置。`execution_profiles.json` 只保存默认 `model_id` 与 `runner_option_hint_id`。
```

**Severity**: HIGH — user-facing manual contradicts implementation, causes config load failure.

## 4. Non-Blocking Observations

### OBS-1 [LOW] — docs/host/implementation-control.md:1801 stale agent_policy_profiles reference

**File**: `docs/host/implementation-control.md:1801`  
**Text**: `execution_profiles.json 使用 ... agent_policy_profiles`  
**Issue**: This line was written during Phase 12 design, before P12.3 removed `agent_policy_profiles`. The current production schema no longer has this field.  
**Why non-blocking**: This is a design control document, not a user-facing config or README. Modifying design docs is outside Slice 4 scope per plan artifact (Section 4: Allowed Files). The control doc's Phase 12.3 section at lines 1877-1916 correctly describes the removal. Line 1801 is part of the earlier Phase 12 design recording section.  
**Suggested action**: Note for future control doc cleanup; no action required in this slice.

### OBS-2 [INFO] — tests/README.md coverage description is current

`tests/README.md:81` correctly describes "旧 execution profile 字段与旧 runner hint `max_tokens` fail fast" — using "旧" (old) to mark these as historical negative tests. No update needed. ✅

### OBS-3 [INFO] — host/engine README correctly scoped

- `dayu/host/README.md:250`: usage is "post-call observation, 只用于后续估算校准、diagnostic 和后续治理参考". No Engine usage parsing described as Host responsibility. ✅
- `dayu/engine/README.md:135`: `supports_stream_usage` gate described, no Host budget decision mentioned. ✅

## 5. Implementation Artifact Claims — Cross-Validation

| Artifact Claim | DS Verification |
|---|---|
| "dayu/config/README.md 已更新...只描述新 schema 接受范围与 fail-fast 行为" | ✅ Confirmed. Line 94-95 uses "配置只接受" framing, no old field name listing |
| "根 README smoke 示例使用旧 standard profile id...已改为 standard-256k" | ✅ Confirmed. Line 967 is `--execution-profile-id standard-256k` |
| "根 README workspace model 示例在 runner hint 中写 max_tokens...已删除" | ✅ Confirmed. Lines 1111 and 1116 removed, only temperature/top_p/stream remain |
| "Slice 3 review 提到的 smoke test 旧 standard profile id 残留...Slice 3 fix 已修复" | ✅ Confirmed. No `"standard"` (without suffix) in production config or READMEs |
| "README sync complete" | ❌ Misses BLOCKER-1 — README.md:1145 still says max_tokens "属于" runner_option_hints |
| "56 passed" for config/assembly/service tests | ✅ Confirmed (artifact included `test_smoke_host_public_multiturn_assembly.py`; my 53 + that file = 56) |

## 6. Adversarial Failure Pass

- **ConfigLoader fail-closed**: `_parse_runner_option_hint` uses `_require_exact_fields` with `frozenset({"temperature", "top_p", "stream"})` — any extra field (including `max_tokens`) fails fast. ✅
- **Cross-service `max_tokens` default path**: `dayu/service/host_assembly.py:775` writes `max_tokens=None` as the only default config path result. ✅
- **OpenAI explicit override preserved**: `RunnerCallOptions.max_tokens` field still exists; explicit non-None values still map to provider payload. ✅ (verified by existing explicit override tests passing)
- **Usage observation no state change**: `USAGE_REPORTED` remains `PROJECTION_SIGNAL`, does not alter Run/Attempt status. ✅ (verified by test assertions)
- **No usage config override**: `usage_enabled`/`collect_usage`/`include_usage` absent from all config/runtime/service/host layers. ✅
- **No automatic profile switching**: Service helper uses explicit `default_execution_profile_id` or override, never reads model context window to switch. ✅ (verified by Slice 3 tests)
- **Import boundary**: `dayu.runtime` does not import Engine/Host/Service/UI/Fins. ✅ (verified by import boundary tests)
- **`supports_usage`** (standalone, not `supports_stream_usage`) absent from production config. ✅

## 7. README Trigger Check

Per plan artifact README trigger rules:

| README | Trigger | Updated? | Decision |
|---|---|---|---|
| `dayu/config/README.md` | config schema change | ✅ Updated | Correct: old schema field names removed, new structure described |
| Root `README.md` | project-level usage/CLI/config examples changed | ⚠️ Partial | Smoke profile id + example max_tokens fixed; line 1145 NOT fixed |
| `dayu/host/README.md` | host usage observation changes | Not needed | Current text already describes post-call observation facts |
| `dayu/engine/README.md` | engine usage docs stale? | Not needed | Current text describes `supports_stream_usage` gate, no Host content |
| `tests/README.md` | test coverage description changed | Not needed | Already covers negative tests for old fields |
| `dayu/README.md` | architecture boundaries changed | Not needed | Layering unchanged |

The only missed update is README.md:1145.

## 8. Conclusion

**Verdict: BLOCKED**

The aggregate validation is thorough and the production code/config/test chain is clean. However, README.md:1145 contains a statement that directly contradicts current production behavior — it tells users that `max_tokens` belongs to `runner_option_hints`, but ConfigLoader rejects `max_tokens` in that exact position.

Fix BLOCKER-1 and this slice can go to PASS.

### Residual Risks (post-fix)

| Classification | Item |
|---|---|
| later phase/work unit | Real Service/UI/workflow not yet wired to execution profile selection |
| later phase/work unit | Future output token cap must use provider adapter/public contract, not model hints |
| later phase/work unit | `wechat-*` profiles share `standard-*` baseline (no confirmed business divergence yet) |
| existing issue | Historical design/discussion/review docs contain old field names (not production, not user-facing) |
| requiring user decision | `docs/host/implementation-control.md:1801` stale `agent_policy_profiles` — not in Slice 4 scope; needs separate doc cleanup authorization |
