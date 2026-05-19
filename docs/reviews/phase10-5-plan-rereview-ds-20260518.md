# Phase 10.5 Plan Re-Review — fix verification

**Reviewer**: AgentDS (P10.5 plan re-review specialist)
**Date**: 2026-05-18
**Gate**: P10.5 plan re-review
**Review type**: adversarial fix-verification review — did plan fix resolve all controller-accepted findings without introducing new issues?

**Reviewed artifact**: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
**Fix report**: `docs/reviews/phase10-5-plan-fix-codex-20260518.md`
**Controller adjudication**: `docs/reviews/phase10-5-plan-review-controller-adjudication-20260518.md`
**Source reviews**: `docs/reviews/phase10-5-plan-review-mimo-20260518.md`, `docs/reviews/phase10-5-plan-review-ds-20260518.md`
**Design truth**: `docs/host/design.md`
**Control truth**: `docs/host/implementation-control.md`

---

## Review Question

Did the plan fix resolve all controller-accepted findings (A1-A5) without introducing new public API, scope creep, state machine / schema / persistence changes, or conflicts with design.md / implementation-control.md? Is the plan still handoff-ready / code-generation-ready?

---

## Verdict

**PASS — blocking count = 0.**

All five controller-accepted findings (A1-A5) are fixed with explicit plan text at verified locations. No new public API, scope creep, state machine change, schema change, persistence change, or conflict with design.md / implementation-control.md was introduced. The plan remains handoff-ready and code-generation-ready.

---

## A1-A5 Per-item Fix Status

### A1. Slice dependency and Slice 2 request-shape boundary — **FIXED**

**Controller requirement**: clarify Slice 1 -> Slice 2 -> {Slice 3, Slice 4} -> Slice 5 -> Slice 6; Slice 2 may validate with current request shape; Slice 3 migrates SubmitFollowupRequest; Slice 2 must not pre-implement steer/retry/replay.

**Evidence**:
- Plan line 283-285: Explicit dependency chain `Slice 1 -> Slice 2 -> {Slice 3, Slice 4} -> Slice 5 -> Slice 6`.
- Plan line 287-288: "Slice 2 stop condition 可以使用当时代码库已有的 request shape 验证 `submit_followup(queue)` runtime wakeup，不要求提前迁移 `SubmitFollowupRequest` typed fields。"
- Plan line 288-289: "Slice 3 再迁移 ordinary prompt request contract 到 `SubmitFollowupRequest` typed fields".
- Plan line 290-291: "Slice 2 不得为了预留 wakeup 而提前实现 steer、retry 或 replay 语义。"

**Verification**: The fix removes ambiguity about whether Slice 2 needs Slice 3's request shape. The dependency chain is explicit and the non-goal boundary prevents Slice 2 from pre-implementing Slice 5 work. **Pass.**

---

### A2. Public handle session/read wrappers ownership — **FIXED**

**Controller requirement**: `ensure_session` / `create_session` / `get_session` / `get_run` must be explicitly owned by Slice 2 public async handle delegation.

**Evidence**:
- Plan line 351-352: "Public async handle delegation ownership is Slice 2: `ensure_session`、`create_session`、`get_session`、`get_run` must be exposed as async wrapper / delegation methods on the public handle, with handle-open validation and no Service access to the internal command handle."
- Plan line 352-353: "Public handle wrapper / delegation for later public commands belongs to this same facade: `submit_followup`、`resolve_wait`、`retry_run`、`replay_run`、`cancel_run`、`cancel_session_runs`、`close_session` may delegate to internal command primitives, while Slice 3 / Slice 5 own the command semantics they introduce or complete."

**Verification**: Session/read methods are now explicitly assigned to Slice 2. The delegation pattern is clear: Slice 2 owns the facade and delegation wiring; Slice 3/5 own the command semantics. **Pass.**

---

### A3. HostEventStream disposition — **FIXED**

**Controller requirement**: plan must explicitly direct Slice 4 to handle existing `HostEventStream`.

**Evidence**:
- Plan line 444: "If existing `HostEventStream` is present in `dayu.host` public exports, remove it from the Service-facing namespace. If retained at all, it may only be an internal type alias / Protocol equivalent to `AsyncIterator[HostEvent]`; it must not be a Service-facing context manager, subscription handle, or second public stream contract."
- This is in Slice 4 "Exact allowed changes" section, directly actionable by implementation agent.

**Verification**: The disposition is explicit and matches design.md (HostEventStream as internal/type alias only). The instruction is placed in Slice 4 where it belongs. **Pass.**

---

### A4. Compactor baseline None semantics and field mapping — **FIXED**

**Controller requirement**: fail-closed semantics for `compactor_baseline=None`; Slice 2 explicit field mapping from `OpenHostOptions.compactor_baseline` to internal compactor fields; S4 compact owner to include Slice 2 wiring.

**Evidence**:
- Plan line 238-239 (fail-closed): "`compactor_baseline=None` 语义固定为 fail-closed：Host 没有可用 compaction 能力，不得隐式创建 fake compactor、不得静默忽略 context budget policy、不得把 ordinary Run override 当 compactor 配置使用。若当前 Run 在预算压力下需要 compaction 才能继续，必须以 typed budget / compaction-unavailable failure 结束该 Run 或拒绝该执行路径；短上下文本身未触发预算压力时可以正常运行。"
- Plan line 356 (Slice 2 field mapping): "Map `OpenHostOptions.compactor_baseline` to internal compactor fields: `context_compactor`、`compactor_runner_spec`、`compactor_runner_options`、`compactor_policy_ref`、`compact_artifact_root` and compact artifact directory creation policy. If `compactor_baseline is None`, propagate the fail-closed 'no compaction capability' state; do not install fake defaults."
- Plan line 274 (S4 coverage table row owner): "Slice 1 + Slice 2 + Slice 6"

**Verification**: All three sub-requirements are addressed. The fail-closed semantics are consistent with design.md §11 (compactor baseline is independent construction-time baseline — if none is provided, no compaction capability exists). The field mapping is concrete enough for implementation. S4 owner now correctly references Slice 2 wiring. **Pass.**

---

### A5. HostToolingOptions shape note — **FIXED**

**Controller requirement**: clarify that existing `HostToolingOptions` shape is reused; if ToolRuntime policy typed fields are missing, Slice 1 adds typed fields; must not use extra payload / service locator.

**Evidence**:
- Plan line 146-147: "`HostToolingOptions` 复用当前代码库已有 typed shape，作为 construction-time 全量业务工具与 ToolRuntime governance 配置入口。若现有类型尚未显式承载 ToolRuntime policy 所需 typed fields，Slice 1 负责在该 typed shape 上补齐字段；不得改用 `extra payload`、service locator、profile lookup 或无结构 `dict` 传递 policy。"
- Plan line 260 (readiness closure table, DS C2): "复用 `HostToolingOptions` typed shape；若缺少 ToolRuntime policy typed fields，由 Slice 1 补齐，禁止 extra payload / service locator。"
- Plan line 308 (Slice 1 exact changes): "Ensure `HostToolingOptions` remains the typed construction-time tooling policy shape; if existing fields do not cover ToolRuntime policy, add explicit typed fields there instead of `extra payload` / service locator."

**Verification**: The approach is explicit across three locations. Implementation agent knows: reuse the existing type, add typed fields if missing, don't use unstructured fallbacks. **Pass.**

---

## New Issues Check

### New public API?

No. The fixes are clarifications of existing plan content — they don't add new public methods, types, or contracts beyond what the original plan already described. A3 actually constrains public surface by directing removal of `HostEventStream` from public exports.

### Scope creep?

No. All clarifications are within P10.5's existing scope boundary (plan lines 38-47). No new phase responsibilities were imported from Phase 11-15.

### State machine / schema / persistence changes?

No. The fixes don't alter Run / Attempt / EventLog state machines, don't introduce new durable schema fields or tables, and don't change persistence semantics. A4's fail-closed semantics describe behavior (what happens when compaction is unavailable), not a new state transition.

### Conflicts with design.md?

No. Verified against `docs/host/design.md`:

| Design requirement | Fix impact | Status |
|---|---|---|
| HostEventStream as internal/type alias (§11) | A3 enforces this | Consistent |
| Compactor baseline independent of ordinary Run override (§11) | A4 respects this; fail-closed is natural consequence | Consistent |
| `open_host(options)` typed construction (§11) | No fix changes this | Consistent |
| `ensure_session`/`create_session`/`get_session` in minimum interface (§11) | A2 assigns them to Slice 2, within plan scope | Consistent |
| HostToolingOptions carries ToolBundle + ToolRuntime policy (§11) | A5 clarifies typed field approach | Consistent |

### Conflicts with implementation-control.md?

No. Verified against `docs/host/implementation-control.md` Phase 10.5:

| Control requirement | Fix impact | Status |
|---|---|---|
| Slice sequencing and stop conditions | A1 makes them explicit | Consistent |
| Public handle methods ownership | A2 assigns ownership | Consistent |
| HostEventStream disposition | A3 provides explicit directive | Consistent |
| Compactor opener contract | A4 defines fail-closed and field mapping | Consistent |
| Construction-time options typed shape | A5 clarifies HostToolingOptions approach | Consistent |
| Exit conditions (lines 1271-1278) | No fix changes exit criteria | Consistent |

---

## Handoff-readiness Assessment

The plan after fix meets all handoff-readiness criteria:

- **Slice dependency unambiguous**: A1 provides explicit sequencing and cross-slice boundaries.
- **All public handle methods owned**: A2 assigns session/read wrappers to Slice 2.
- **Existing code disposition explicit**: A3 tells Slice 4 exactly what to do with `HostEventStream`.
- **Compactor semantics complete**: A4 defines the None case and precise field mapping.
- **Tooling options approach clear**: A5 tells Slice 1 exactly how to handle `HostToolingOptions`.

The six slices remain well-scoped with clear objectives, allowed files, exact changes, non-goals, tests, validation commands, and measurable stop conditions. The unified coverage table covers all S1-S5 paths with per-row owner, test name, public-path assertions, skip conditions, and follow-up owners.

No new Blocking Questions For Controller were introduced.

---

## Residual Risks

The fix introduces no new risks. Existing residual risks from the plan and source reviews remain unchanged:

| # | Risk | Severity | Owner |
|---|---|---|---|
| R1 | S3 real-runner matrix all-skip (no provider available) | Medium | Slice 6 + Controller |
| R2 | S4 real compactor adapter unavailable | Medium | Slice 6 + Controller |
| R3 | Implementation agent may pre-implement Slice 5 in Slice 2 despite A1 boundary | Low | Implementation discipline; A1 stop condition constrains this |
| R4 | `HostClosedError` inheritance choice (standalone vs. lifecycle base class) | Low | Slice 1; plan allows either, public contract unaffected |
| R5 | Phase 11 Recovery may need P10.5-frozen interface changes | Low | Phase 11; mitigated by implementation-control.md precondition |

---

## Artifact Path

`docs/reviews/phase10-5-plan-rereview-ds-20260518.md`
