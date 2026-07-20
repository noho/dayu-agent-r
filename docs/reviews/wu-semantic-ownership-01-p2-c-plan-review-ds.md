# WU-SEMANTIC-OWNERSHIP-01 P2-C Plan Review — AgentDS

## Review Scope

- **Work Unit**: `WU-SEMANTIC-OWNERSHIP-01 P2-C`
- **Gate**: plan review
- **Plan artifact**: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-controller-validation.md`
- **Design truth**: `docs/host/design.md`, `docs/engine/design.md`
- **Control truth**: `docs/host/issues-implementation-control.md`

## Review Methodology

Direct evidence from source files verified against plan claims; adversarial failure scenarios constructed for each finding; owner boundary propagation audited per AGENTS.md semantic ownership rules; LLM-facing text constraints checked against CLAUDE.md Section "LLM-facing 文本约束".

---

## Findings

### F-1: Code-generation-ready ambiguity — `AgentPolicyDefaults` rename decision deferred to implementation discretion

**Severity**: MEDIUM

**Direct Evidence**:
- Plan Decision 3 (line 103-106): "若实现发现 `code_default` 已被 execution profile 同值填充且语义混乱，优先将参数命名和 docstring 改为 `base_policy` / `fallback_policy` 一类不会暗示 Engine 默认的名称；不做 wrapper 兼容旧名。"
- Source: `dayu/runtime/assembly.py:39` defines `_SOURCE_CODE_DEFAULT: Final[str] = "code_default"`; `dayu/runtime/assembly.py:160-180` defines `AgentPolicyDefaults` dataclass with `fallback_prompt` and `continuation_prompt` fields that currently hold the same prompt text values as the execution profiles.
- Source: `dayu/runtime/assembly.py:466-598` `merge_agent_policy_config(...)` uses `code_default: AgentPolicyDefaults` as the fallback parameter when execution_profile, scene_override, and run_override all lack a field.

**Failure Scenario**:
If the implementation agent defers the rename decision because "it's not strictly required for the P2-C contract fix" (a plausible reading of the conditional "若实现发现...且语义混乱"), the `code_default` parameter name in `merge_agent_policy_config()` continues to semantically suggest that Engine has a code-level default — exactly the dual-source problem P2-C is fixing. Meanwhile, the actual text values in `AgentPolicyDefaults` would have been updated to match execution profiles, creating a third implicit source that test-only or direct callers could misuse.

**Impact**:
- Residual semantic confusion: `code_default` implies Engine owns a default, undermining the owner boundary P2-C establishes.
- Risk: future contributor reads `code_default` and adds a new prompt default back to Engine, re-creating the dual-source.
- Risk: implementation agent may copy config text into `AgentPolicyDefaults` without removing the Engine defaults first, creating a more confusing triple-source (Engine old default, config text, runtime code_default).

**Recommended Fix**:
Remove the conditional. Make the rename from `code_default` → `base_policy` (or `assembly_fallback`) a hard requirement in this plan, with explicit before/after naming specified. The `_SOURCE_CODE_DEFAULT` source tag should be renamed to `_SOURCE_ASSEMBLY_BASE` or `_SOURCE_RUNTIME_BASE` to make clear it's an assembly-layer fallback, not an Engine-owned default. The `AgentPolicyDefaults` dataclass docstring should state it is "runtime assembly merge fallback values, not Engine contract defaults."

---

### F-2: Missing `utils/` coverage in validation scan command

**Severity**: LOW

**Direct Evidence**:
- Plan line 147: `rg -n "AgentPolicy\\(" dayu/ tests/ --glob '*.py'` excludes `utils/`.
- Source: `utils/smoke_host_public_awaiting_entrypoint.py:975` constructs `AgentPolicy(...)` with explicit prompts — safe.
- Source: `utils/smoke_async_agent_providers.py:297` constructs `AgentPolicy(...)` — needs verification.
- `utils/` is explicitly mentioned in CLAUDE.md under "目录约束" as containing "分析辅助代码" and is not under `dayu/` or `tests/`.

**Failure Scenario**:
A smoke/utility script under `utils/` that constructs `AgentPolicy(...)` without explicit `fallback_prompt` / `continuation_prompt` would fail at import/construction time with a `TypeError` after P2-C implementation, breaking CI smoke or developer workflows that aren't covered by the main test suite.

**Impact**:
Low probability (smoke scripts already pass explicit prompts), but the scan gap means the plan doesn't commit to verifying this at acceptance time.

**Recommended Fix**:
Extend the post-scan acceptance command to: `rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'`. Or add a separate explicit check for `utils/` AgentPolicy constructions.

---

### F-3: Test fixture `public_smoke_support.py` construction point relies on Engine defaults for ordinary run baseline

**Severity**: HIGH

**Direct Evidence**:
- Source: `tests/host/public_smoke_support.py:908-913`:
  ```python
  agent_policy=AgentPolicy(
      max_iterations=2 if allow_tool_calls else 1,
      continuation_max_attempts=0,
      allow_tool_calls=allow_tool_calls,
      tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
  ),
  ```
- This is the only production-significant test fixture that constructs `AgentPolicy` without `fallback_prompt=` or `continuation_prompt=` for the **ordinary run baseline** in `open_host(...)`.
- Plan line 87-88 identifies "Engine tests" as containing omitted-prompt constructions but does not explicitly call out this Host-level public smoke support fixture.

**Failure Scenario**:
After P2-C implementation, `public_smoke_support.py:908` triggers `TypeError` at `open_host(...)` construction time. Public smoke tests (e.g., `test_public_lifecycle_smoke.py`, `test_public_open_host_multiturn_smoke.py`, etc.) that depend on `public_smoke_support` will fail before reaching their test logic. This is a fixture-level failure, not a test-logic failure, so the fix is mechanical but must not be missed.

**Impact**:
- Host public smoke suite breaks on construction, blocking CI.
- If the implementation agent fixes this by creating a module-level default helper in `public_smoke_support.py`, it may inadvertently create a new implicit default source that other test files import, re-creating the dual-source problem at the test layer.

**Recommended Fix**:
Plan Section "Affected Files / Modules" → Tests should explicitly list `tests/host/public_smoke_support.py` as a migration target. Plan Decision 7 should add a guardrail: test fixture helpers must be explicit per-construction, not module-level defaults imported across test files. The `_agent_policy(...)` test helper mentioned in Decision 7 should have its scope bounded: "Engine tests 可建一个局部 fixture helper `_agent_policy(...)`" should also cover the Host public smoke fixture migration.

---

### F-4: Execution profile default fallback prompt text differs from Engine default — plan correctly identifies but doesn't require config text audit

**Severity**: INFO

**Direct Evidence**:
- Engine `_DEFAULT_FALLBACK_PROMPT` (agent_policy.py:29-31): "请基于目前已经获得的上下文直接给出最终回答，不要再调用工具。"
- Config default (quoted in plan line 46, from config/README.md:127): "请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。"
- The config version adds "信息不足时必须说明不确定性，不得编造" — an important behavioral constraint that the Engine default omits.
- Plan Non-goal (line 22): "不改变默认 ordinary fallback / continuation prompt 的实际文本，除非 implementation 发现配置真源已不一致并需要只同步文档。"

**Analysis**:
The plan correctly scopes text differences as a documentation/config sync concern, not a P2-C implementation concern. The config text IS the source of truth; Engine's old text is being deleted, not migrated. No action needed. This is recorded for traceability — the config variant is the better prompt (includes anti-hallucination guidance), and the Engine variant is the one being removed.

**Impact**: None. The plan correctly doesn't require changing config text.

**Recommended Fix**: None required. The plan non-goal is adequate.

---

### F-5: `test_contract_fields_are_explicit` migration specification is insufficiently concrete

**Severity**: MEDIUM

**Direct Evidence**:
- Plan line 123: "更新 `test_contract_fields_are_explicit`：不再断言默认 prompt 存在，改为断言缺少 prompt 触发 `TypeError`，显式 prompt 构造后字段保留且空白 prompt 仍 `ValueError`。"
- Source: `tests/engine/test_agent_phase3_tool_call.py:796-809` currently:
  ```python
  def test_contract_fields_are_explicit() -> None:
      policy = AgentPolicy(
          max_iterations=_MINIMAL_MAX_ITERATIONS,
          continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
          allow_tool_calls=True,
          tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
      )
      assert policy.fallback_mode is AgentFallbackMode.FORCE_ANSWER
      assert policy.max_consecutive_failed_tool_batches == 2
      assert policy.fallback_prompt
      assert policy.continuation_prompt
  ```
- This test currently asserts the very dual-source behavior P2-C eliminates.

**Failure Scenario**:
The plan says "改为断言缺少 prompt 触发 `TypeError`" but doesn't specify:
- Whether `test_contract_fields_are_explicit` should be renamed (it tests the opposite of what its name suggests — it currently tests that defaults exist, not that fields are explicit).
- Whether the new test should be a single test or split into separate `TypeError` (missing prompt) and `ValueError` (blank prompt) tests.
- What the `fallback_mode` and `max_consecutive_failed_tool_batches` default assertions become — they are not LLM-facing text and are retained per plan Decision 1.

**Impact**:
Implementation agent may produce a mechanically correct but semantically confused test: "contract fields are explicit" re-tests non-text defaults (which are out of scope) while the actual P2-C semantic (prompt fields are required) is diluted.

**Recommended Fix**:
Specify:
1. Rename test to `test_agent_policy_prompt_fields_are_required` or split into two tests.
2. New test 1: `test_agent_policy_rejects_missing_prompt_fields` — omit `fallback_prompt` → `TypeError`; omit `continuation_prompt` → `TypeError`.
3. New test 2: `test_agent_policy_accepts_explicit_prompt_fields` — explicit prompts → construction succeeds, fields preserved.
4. Existing `test_agent_policy_rejects_invalid_values` already covers blank prompt `ValueError`; no change needed there beyond making prompt fields explicit in remaining negative test constructions.
5. Non-text defaults (`fallback_mode`, `max_consecutive_failed_tool_batches`) default assertions move to a separate test or are inlined in `test_agent_policy_accepts_explicit_prompt_fields`.

---

### F-6: Plan validation command excludes `test_agent_phase2.py` from focused checks

**Severity**: LOW

**Direct Evidence**:
- Plan line 145: `pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_agent_run.py`
- Plan line 87 lists `tests/engine/test_agent_phase2.py` as an affected test file but doesn't include it in the focused check command.
- Source: `tests/engine/test_agent_phase2.py:422` and `:1431` both construct `AgentPolicy(...)`.

**Impact**:
Focused check misses `test_agent_phase2.py` fallback/continuation tests; only caught by the broader `pytest tests/engine` command.

**Recommended Fix**:
Add `tests/engine/test_agent_phase2.py` to line 145's focused check command.

---

## Owner Boundary Audit

Performed propagation audit for the fallback/continuation prompt semantic across all plan-identified paths:

| Path | Plan Analysis | Verification |
|------|--------------|-------------|
| Ordinary: `execution_profiles.json` → `ConfigLoader.AgentPolicyConfig` → `merge_agent_policy_config(...)` → `_agent_policy_from_merged(...)` → `OrdinaryRunExecutionBaseline` → `AgentRunRequest.agent_policy` → Engine fallback/continuation user message | ✓ Correct. All production AgentPolicy constructions in this path already pass explicit `fallback_prompt=` and `continuation_prompt=` from merged config. | Verified: `host_assembly.py:1699-1707`, `host_assembly.py:1663-1688` |
| Compactor: scene `conversation_compaction` → `_compactor_agent_policy_from_scene_inputs(...)` → `CompactorRunnerBaseline` → Engine | ✓ Correct. Requires all fields non-None before constructing AgentPolicy; misses trigger `ValueError` before reaching Engine. | Verified: `host_assembly.py:1000-1027` |
| Durable restore: `agent_policy_from_json(...)` → `AgentPolicy(...)` | ✓ Correct. Uses `required_json_text` for both prompt fields; JSON without these fields fails before reaching AgentPolicy constructor. | Verified: `_execution_config_projection.py:399-427` |
| Direct Engine usage (tests, utils) | Plan identifies 51 test construction points needing migration. | Verified by scan: multiple test files omit prompt fields; `public_smoke_support.py:908` is the highest-risk case. |
| Service `ServiceRunOverrides` continuation_prompt gap | Plan correctly notes `continuation_prompt` is not in per-run overrides. Ordinary baseline provides it. Not a P2-C scope issue. | Verified: `host_assembly.py:1682` passes `baseline.continuation_prompt` unconditionally. |

Owner boundary conclusion: **Correct**. The plan establishes a single source of truth per path: config → typed policy → Engine consumption. Engine never generates prompt text.

---

## LLM-Facing Text Constraint Check

- Plan correctly identifies that `fallback_prompt` and `continuation_prompt` are LLM-facing text (CLAUDE.md "LLM-facing 文本约束" applies).
- Plan Decision 1 removes Engine's production of LLM-facing text defaults, satisfying the constraint that "LLM-facing 文本从 config / scene 真源一路派生，不由 Engine contract 自行补写."
- Plan Decision 2 explicitly rejects replacing Engine defaults with config text, preventing a second Engine-owned text source.
- No new LLM-facing text is introduced by this plan. Config text is unchanged. Compactor text is unchanged.

✓ Compliant.

---

## Slice Decision Assessment

Plan (line 170-178) proposes a single implementation slice.

**Assessment**: The plan's reasoning is sound per the control doc's slice principles:
- This is a single semantic closure: `AgentPolicy` prompt fields become required → all construction points must pass explicit prompts.
- Partial implementation (e.g., remove Engine defaults first, migrate tests later) would leave pyright/pytest in failing intermediate state.
- No durable schema, Host public API, provider behavior, or cross-owner state machine changes.
- 55 construction points are mechanically similar; splitting by module would increase gate cost without reducing risk.
- Control doc line 138-140: "对代码量较小、语义上属于同一个 contract cleanup / config cleanup / schema cleanup 的 work unit... 应优先合并为少量可验证闭环 slices."

**Residual concern**: Single implementation agent must handle ~55 construction points plus Engine contract change plus README updates. This is within a single agent's context window but near the upper bound. Mitigation: the plan's `rg` scan + pyright + pytest post-validation is a strong guardrail.

✓ Single slice is acceptable.

---

## README / Docs Trigger Check

Plan identifies:
- `dayu/engine/README.md` — **must update** (Engine contract behavior changes)
- `dayu/config/README.md` — check only (already states config owns defaults)
- `tests/README.md` — check only (if new shared test fixtures added)
- Design docs — no update needed (already support the boundary)

Matches CLAUDE.md README update triggers:
- `dayu/engine/` modification → `dayu/engine/README.md` ✓
- `dayu/config/` modification → check `dayu/config/README.md` ✓ (only if implementation changes config)
- `tests/` modification → check `tests/README.md` ✓

---

## Pyright / Type Safety Check

Plan Decision 1: Remove `_DEFAULT_FALLBACK_PROMPT` and `_DEFAULT_CONTINUATION_PROMPT`; make `fallback_prompt: str` and `continuation_prompt: str` required (no default).

**Impact**: All 55 construction points must pass positional/keyword `fallback_prompt=` and `continuation_prompt=`. Any omitted call becomes a `TypeError` at import/construction time — caught by both pyright (static) and pytest (runtime).

✓ Pyright is well-covered as a guardrail.

---

## Compatibility / Wrapper Risk Check

Plan Decision 3: "不做 wrapper 兼容旧名"  
Plan Decision 2: "不把 Engine 默认替换为 config 文本"  
Plan Non-goal line 24-27: No compatibility alias, default wrapper, test-only default helper, or re-export.

**Risk**: Plan Decision 7 allows "Engine tests 建一个局部 fixture helper" — this is a necessary test migration aid, but the scope boundary is fuzzy. If the helper is module-level in `tests/engine/` and imported by other test files, it becomes a de facto shared default source.

**Recommended addition**: In Decision 7, add: "Test fixture helper must be function-local (defined inside the test function) or file-local (module-level but `_`-prefixed and not imported by other test modules). It must not reside in `conftest.py`."

---

## Conclusion

**Pass-with-risks**

The plan correctly identifies the dual-source root cause (MiMo 05), chooses the right fix (remove Engine defaults, don't replace with config text), establishes correct owner boundaries, and provides adequate validation commands and post-scan acceptance criteria.

**Accepted risks** (no plan change required):
- 55 construction points is a large mechanical migration; pyright + pytest + `rg` post-scan are sufficient guardrails.
- Single-slice approach is justified; intermediate state would be worse than large single change.

**Risks requiring plan fix before implementation**:
- **F-1 (MEDIUM)**: `code_default` / `AgentPolicyDefaults` rename should be a hard requirement, not conditional on implementation agent's discovery.
- **F-3 (HIGH)**: `tests/host/public_smoke_support.py:908` not explicitly listed as a migration target; risk of CI break on construction.
- **F-5 (MEDIUM)**: `test_contract_fields_are_explicit` migration spec insufficiently concrete; rename and split guidance needed.

**Risks that can be handled during implementation**:
- **F-2 (LOW)**: Add `utils/` to post-scan command.
- **F-6 (LOW)**: Add `test_agent_phase2.py` to focused check command.

---

## Artifact Path

`docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-ds.md`

---

## Findings Summary

| ID | Severity | Category | Summary |
|----|----------|----------|---------|
| F-1 | MEDIUM | Spec ambiguity | `code_default` → `base_policy` rename is conditional; should be a hard requirement |
| F-2 | LOW | Validation gap | Post-scan `rg` command excludes `utils/` directory |
| F-3 | HIGH | Missing target | `tests/host/public_smoke_support.py` not explicitly listed as migration target |
| F-4 | INFO | Documentation | Config fallback prompt text differs from Engine default; correctly out of scope |
| F-5 | MEDIUM | Test spec | `test_contract_fields_are_explicit` migration guidance insufficiently concrete |
| F-6 | LOW | Validation gap | Focused check command missing `test_agent_phase2.py` |

## Open Questions / Residual Risks

1. **Residual Risk — `AgentPolicyDefaults` semantic**: After this WU, `AgentPolicyDefaults` in `dayu.runtime.assembly` will hold prompt text used as merge fallback in `merge_agent_policy_config()`. If the rename (F-1) is deferred, future readers may still interpret it as Engine-owned defaults. The control doc should track this as a deferred cleanup if not done in P2-C.

2. **Residual Risk — Test fixture scope creep**: If implementation agent creates a test-level `_agent_policy(...)` helper that becomes widely imported, it effectively re-creates a default source. The review gate must check for this specifically.

3. **Open Question — `continuation_prompt` language mismatch**: Engine default is in English ("Your previous response was truncated..."), config versions may differ. The plan non-goal says "不改变默认 ordinary fallback / continuation prompt 的实际文本" — verify during implementation that all paths (ordinary, compactor, per-run override) project consistent-language continuation prompts. This is not a P2-C scope issue but should be noted for future prompt consistency audit.
