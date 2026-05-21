# Phase 12.1 Plan Review -- MiMo 2026-05-21

## Review Inputs

- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`
- Plan under review: `docs/host/phase12-1-runtime-assembly-correction-plan.md`
- Discussion reference: `docs/host/runtime-assembly-followup-discussion.md`
- Current codebase state: verified via file reads and grep

## Verdict: PASS

Plan is code-generation-ready. No blocking findings. Six non-blocking observations below.

---

## Blocking Findings

None.

---

## Non-Blocking Observations

### O-1. Slice 1 owns the largest file surface (severity: low)

Slice 1 touches 8 source modules and 6 test files. The `ContextBudgetPolicy` ratio-first rewrite requires coordinated changes across `context_policy.py`, `context_budget.py`, `context_governance.py`, `memory.py`, `memory_repair.py`, `durable/memory.py`, `tool_schema.py`, `tool_runtime.py`, and `tool_runtime_schema_projection.py`. This is within a single agent's capacity if the agent is well-briefed, but the risk of partial migration (e.g., updating the dataclass but missing a derivation helper in `context_budget.py`) is non-zero.

Recommendation: Implementation artifact for Slice 1 should list each file's expected diff summary before coding begins.

### O-2. Effective truncate spec helper placement is underdetermined (severity: low)

Plan Slice 1 says the effective truncate spec helper goes at "Host/tool runtime 边界或 runtime assembly helper", while Slice 4 says it's a "runtime-neutral helper" that can go in `dayu.runtime`. These are different locations with different import boundaries. The plan should converge on one placement.

Current codebase fact: `ToolTruncateSpec` lives in `dayu/contracts/tool_schema.py` (importable by both `dayu.runtime` and `dayu.host`). A helper in `dayu.runtime` that only consumes `ToolTruncateSpec` + policy defaults would respect the import boundary. A helper in `dayu.host.tool_runtime` would be closer to the consumer but would create a tighter coupling.

Recommendation: Converge on `dayu.runtime` (or `dayu/contracts`) as the helper location, since it only needs `ToolTruncateSpec` and policy default values, not Host internals. Document this convergence in the Slice 1 implementation artifact.

### O-3. MemoryProjectionPolicy field naming verification (severity: low)

Plan Slice 1 says to change `MemoryProjectionPolicy` from "fixed `stable_layer_size_units` / `history_pool_size_units` / `max_raw_turn_size_units`" to ratio/floor/cap model. Current codebase verification confirms the Host public `MemoryProjectionPolicy` already uses these field names (`stable_layer_size_units`, `history_pool_size_units`, `max_raw_turn_size_units`). The plan's description is accurate.

However, the config layer (`execution_profiles.json` / `config_loader.py`) uses `stable_layer_max_items` / `history_pool_max_items` -- a different naming convention. The plan correctly identifies this mismatch (Slice 2 handles config schema, Slice 1 handles Host contract). No action needed; just noting for implementation agents that the naming gap is intentional across slices.

### O-4. Smoke-private adapter creates intermediate ownership (severity: low)

Plan Slice 4 says: "Phase 12.1 若没有真实 Service package，先作为 smoke 私有 helper 实现". This means `utils/smoke_host_public_multiturn.py` will temporarily own composition logic that should eventually live in a Service package. The plan correctly identifies this and requires smoke diagnostics to output "suggested adapter/helper function names" for future extraction.

Recommendation: Implementation artifact for Slice 4 should explicitly name each smoke-private helper function and its suggested future extraction target (e.g., `service.compose_open_host_options()`), so the ownership handoff is traceable.

### O-5. Old model migration depends on git history commit (severity: low)

Plan Slice 2 references `git show 9952fd4:dayu/config/llm_models.json` as the source for model migration. This is a concrete commit reference. The plan correctly requires migrating all models from this source and converting `runtime_hints.temperature_profiles` to `runtime_hints.runner_option_hints`. The 27-model list in the discussion document (item 15) provides a complete manifest.

Recommendation: Implementation artifact for Slice 2 should include a migration checklist mapping each old model to its new `models.json` entry, and verify the commit is accessible before starting.

### O-6. Phase 12 dirty files audit scope (severity: informational)

Plan Section 3 correctly identifies the dirty worktree state: `README.md`, `docs/host/design.md`, `docs/host/implementation-control.md`, `utils/smoke_host_public_multiturn.py` are modified; `docs/host/runtime-assembly-followup-discussion.md` is untracked. The audit steps are well-defined.

However, the plan does not mention that `docs/host/phase12-1-runtime-assembly-correction-plan.md` itself is currently untracked. This is expected (it's the plan artifact being reviewed), but implementation agents should note it will need to be committed as part of the plan acceptance gate, not as part of any implementation slice.

---

## Open Questions

None. The plan's "Blocking Questions for Controller" section correctly states "无 blocking open questions".

---

## Review Criteria Checklist

| Criterion | Status | Notes |
|-----------|--------|-------|
| Satisfies design/control objectives | PASS | All 23 success signals from Section 1 trace to design.md and implementation-control.md |
| Code-generation-ready | PASS | Each slice has owned files, allowed/forbidden changes, validation commands, stop conditions |
| Slice ownership boundaries | PASS | 6 slices with clear dependency chain; no overlapping file ownership |
| Host public surface protection | PASS | Slice 1 forbidden changes list explicitly protects field names and request/response shapes |
| dayu.runtime import boundary | PASS | Plan repeatedly enforces "不得 import Engine / Host / Service / UI / Fins" |
| No compatibility readers/wrappers | PASS | Section 2 Non-goals explicitly forbids these; Section 3 audit enforces it |
| Dirty files handled safely | PASS | Section 3 provides concrete audit steps with git commands |
| Smoke genuinely Service-like | PASS | Slice 5 requires "缺配置、缺 helper、缺 contract mapping 时输出装配诊断并在调用 Host 前失败" |
| Tests/pyright/README sufficient | PASS | Each slice has explicit validation commands; Slice 6 is dedicated README sync |

---

## Final Recommendation

PASS. Plan is ready for implementation. Non-blocking observations O-1 through O-6 are advisory for implementation agents; none require plan changes before handoff.
