# Phase 12.1 Plan Review — DS 2026-05-21

## Review Inputs

- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`
- Plan under review: `docs/host/phase12-1-runtime-assembly-correction-plan.md`
- Discussion reference: `docs/host/runtime-assembly-followup-discussion.md`
- Prior review: `docs/reviews/phase12-1-plan-review-mimo-20260521.md` (PASS, 6 non-blocking observations)
- Current codebase state: verified via read of `dayu/host/context_policy.py:44` (ContextBudgetPolicy), `dayu/host/memory.py:592` (MemoryProjectionPolicy), `dayu/contracts/tool_schema.py:99` (ToolTruncateSpec), `dayu/runtime/__init__.py`, `dayu/runtime/*.py` glob, `tests/runtime/test_import_boundary.py` / `tests/runtime/test_weak_typing_guard.py` existence, `dayu/contracts/__init__.py` import boundary.
- Phase 12 status: all 6 slices accepted and aggregate deepreview PASS; PR 67 merged to main. Phase 12.1 is a follow-up correction, not greenfield.

## Verdict: PASS

The plan is code-generation-ready. No blocking findings. Six non-blocking observations below, of which O-1 and O-2 deserve explicit implementation-agent attention.

---

## Blocking Findings

None.

---

## Non-Blocking Observations

### O-1. Slice 1 owned file count vs. single-agent execution risk (severity: medium)

Slice 1 owns 10 files across source and tests:

```
dayu/host/context_policy.py
dayu/host/context_budget.py
dayu/host/context_governance.py
dayu/host/memory.py
dayu/host/memory_repair.py
dayu/host/durable/memory.py
dayu/contracts/tool_schema.py
dayu/host/tool_runtime.py
dayu/host/tool_runtime_schema_projection.py
tests/host/test_context_policy.py
tests/host/test_context_budget.py
tests/host/test_memory_projection.py
tests/host/test_toolruntime_truncation_fetch_more.py
tests/host/test_phase6_toolruntime_integration.py
tests/host/test_public_open_host_options.py
```

The `ContextBudgetPolicy` ratio-first rewrite removes `reserved_output_tokens`, `safety_margin_ratio`, `hard_threshold_tokens`, `minimum_protection_tokens` and adds `soft_threshold_context_ratio`, `hard_threshold_context_ratio`. Verified from current code: `context_policy.py:44` still has the old field set. The internal derivation in `context_budget.py` and `context_governance.py` uses `input_budget_tokens = context_window_size - reserved_output_tokens` and `computed_hard_threshold_tokens = input_budget_tokens - minimum_protection_tokens`. These consumers must all switch to `context_window_size * ratio` derivation simultaneously.

The `MemoryProjectionPolicy` rewrite from fixed `stable_layer_size_units` / `history_pool_size_units` / `max_raw_turn_size_units` to ratio/floor/cap model touches `memory.py`, `memory_repair.py`, and `durable/memory.py`. Verified from current code: `memory.py:592` still has fixed size_units fields.

Risk: A partial migration where the dataclass is updated but a consumer in `context_budget.py`, `context_governance.py`, or `memory_repair.py` still references old field names will be caught by pyright (strict typing). The explicit validation commands in the plan are sufficient. The risk is implementation discipline, not plan adequacy.

Recommendation: Slice 1 implementation agent should pre-compute and record the list of all call sites that reference each removed field name before making any changes. This cross-reference belongs in the implementation artifact.

### O-2. ToolTruncateSpec effective helper placement is dual-located (severity: medium)

Plan shows two different placements for the effective truncate spec default-fill logic:

- **Slice 1** (Allowed changes): "增加 effective truncate spec helper，输入 declaration spec + policy default limit/ttl，输出 Host ToolRuntime 消费的 complete typed spec；该 helper 放在 Host/tool runtime 边界或 runtime assembly helper，不能让 Engine 参与。"
- **Slice 4** (Placement decisions): Lists "tool truncation policy default lookup" under "Runtime-neutral helper" that "可放 `dayu.runtime`，但不得引用 Host / Engine classes."

These are different locations with different coupling profiles:
- **In Host/tool runtime**: helper is close to consumer, but couples truncation defaults to Host package.
- **In dayu.runtime**: helper is reusable and respects import boundary (only needs `ToolTruncateSpec` from `dayu.contracts` and policy default values as plain dict/typed config), but is further from the consumer.

Current codebase fact: `ToolTruncateSpec` lives in `dayu/contracts/tool_schema.py`, which is importable by both `dayu.runtime` and `dayu.host`. The helper only needs `ToolTruncateSpec` + `default_limits: Mapping` + `default_ttl: int | None` → `ToolTruncateSpec`. It does not need Host internals, tool runtime accept barrier, or Engine.

Recommendation: Converge on `dayu.runtime` (or a new `dayu/contracts/tool_truncate_defaults.py`) as the definitive location. The helper signature is:
```python
def effective_truncate_spec(
    declaration: ToolTruncateSpec,
    /,
    *,
    default_limits: Mapping[str, Mapping[str, int]],
    default_cursor_ttl_seconds: int | None,
) -> ToolTruncateSpec
```
This is self-contained enough to live in layer-neutral space. Update Slice 1's description to converge with Slice 4.

### O-3. MemoryProjectionPolicy ratio field names not enumerated (severity: low)

Plan Slice 1 says to change `MemoryProjectionPolicy` to include "stable layer ratio/floor/cap、history pool ratio/floor/cap、raw turn ratio/floor/cap" but does not enumerate the concrete field names. The design doc (§25 Memory Projection, referenced from §3 of design.md) and the discussion document (item 9) describe the intent. However, without field names in the plan, two implementation agents could pick different names (e.g., `stable_layer_ratio` vs. `stable_layer_size_ratio`).

The implementation agent can derive field names from the design doc. This is not blocking because:
- The design doc is the truth source for field naming.
- The implementation artifact will record the chosen names.
- Code review will catch naming mismatches with design intent.

Recommendation: Slice 1 implementation artifact should list the concrete field names chosen from the design doc, confirming they match the `context_window_size * ratio` / floor / cap semantics described in discussion item 9.

### O-4. Smoke-private helper functions need named extraction targets (severity: low)

Plan Slice 4 says service/composition helpers "先作为 smoke-local private helper 实现并在 smoke 输出 suggested adapter/helper function names." Slice 5 echoes this with "diagnostics must clearly suggest subsequent extraction targets." This is architecturally correct — the service layer doesn't exist yet, so placement is deferred.

However, the plan does not provide a concrete list of expected helper function signatures. Without pre-agreed function names, the smoke diagnostics may output names that don't match future Service API conventions.

Recommendation: Slice 4 implementation artifact should pre-declare the smoke-private helper names and their suggested future extraction targets. At minimum:
- `_compose_open_host_options(...)` → suggested `service.compose_open_host_options(...)`
- `_compose_submit_followup_request(...)` → suggested `service.compose_submit_followup_request(...)`
- `_provider_extension_from_config(...)` → suggested `engine.provider_extension_from_config(...)`

### O-5. Old model migration commit reference not verified in this review (severity: low)

Plan Slice 2 references `git show 9952fd4:dayu/config/llm_models.json` as the migration source. This commit exists in the old `dayu-agent` repo, not necessarily in the current `dayu-agent-r` repo. If the commit is inaccessible at implementation time, the implementation agent would need to locate the source through an alternative path (the 27-model list in the discussion document item 15 serves as a fallback manifest).

This is not blocking because:
- The discussion document provides a complete 27-model list as a fallback reference.
- Plan Section 7 residual risks already notes "Provider model catalog 时效性: owner 为后续 execution profile / model catalog maintenance."
- If the commit is inaccessible, the implementation agent can flag it and proceed with the manifest list.

Recommendation: Slice 2 implementation agent should verify commit accessibility as the first step and record the result in the implementation artifact.

### O-6. ConfigLoader aggregate validation for `extends` single-inheritance not explicitly tested (severity: informational)

Plan Slice 2 allows `extends` with single inheritance only. The design doc (§3) says "需要复用配置时使用显式 `extends`，且只允许单继承；继承解析后必须得到完整 typed record." The plan's allowed changes say "`extends` 只引用同 catalog map key" but doesn't explicitly state that multi-inheritance or circular inheritance must fail fast.

This is implied by the design doc constraint and the slice's "fail fast on invalid config" principle. The implementation agent should add a validation test for:
- Self-reference `extends` → fail
- Multi-level chain A→B→C → pass (single inheritance, chained)
- Missing `extends` target → fail
- Circular A→B, B→A → fail

Recommendation: Slice 2 validation commands should include an explicit `extends` validation test case in `tests/runtime/test_config_loader.py`. The plan's existing "single `extends`" mention in the control doc verification requirements covers this implicitly.

---

## Open Questions

None. The plan's "Blocking Questions for Controller" section correctly reports no blocking open questions.

---

## Review Criteria Checklist

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Satisfies design/control objectives | PASS | 23 success signals trace to design.md §§3, 10.1, 11, 18.1, 24, 25 and implementation-control.md Phase 12.1 scope/deliverables/verification |
| Code-generation-ready | PASS | Each slice has owned files, allowed/forbidden changes, dependencies, explicit validation commands, stop conditions |
| Slice ownership boundaries concrete and non-overlapping | PASS (with O-2 note) | 6 slices form clean dependency chain; only ToolTruncateSpec effective helper placement is dual-located (O-2) |
| Host public surface protected | PASS | All slices' forbidden changes explicitly protect `OpenHostOptions` field names, request/response dataclass field names, `dayu.host` public exports, Host command path, Host handle methods |
| Policy dataclass / ToolTruncateSpec changes are only accepted contract changes | PASS | Slice 1 allowed/forbidden changes demarcate exactly what changes and what stays |
| dayu.runtime free from Host/Engine/Service/UI/Fins imports | PASS | Plan repeatedly enforces this; location resolver only needs `Path`; ConfigLoader/ScenePrepare don't import Host/Engine; provider extension helper placed in `dayu.engine` |
| No compatibility readers/wrappers/tests for old schema | PASS | Section 2 Non-goals explicitly forbids; each slice reiterates in forbidden changes; Section 3 audit classifies pre-existing dirty hunks |
| Dirty README.md and smoke handled safely | PASS | Section 3 provides 5-step audit procedure with git commands and three-category classification |
| Smoke genuinely Service-like, no script defaults hiding gaps | PASS | Slice 5 requires dedicated ordinary scene, no business defaults, fail-fast on missing config/contract mapping, assembly diagnostics output |
| Tests/pyright/README/aggregate review sufficient | PASS | Each slice has explicit validation commands; Slice 6 dedicated to README sync + boundary hardening; Section 6 Review Plan covers plan review → slice code review → aggregate deepreview with at least 2 agents each |

---

## Final Recommendation

**PASS.** The plan is code-generation-ready for implementation agents without re-design. Non-blocking observations O-1 (Slice 1 file surface breadth) and O-2 (ToolTruncateSpec helper dual placement) are the two items that implementation agents should address in their artifacts; neither requires plan changes before handoff. The plan correctly inherits design truth from `docs/host/design.md` and control parameters from `docs/host/implementation-control.md`.
