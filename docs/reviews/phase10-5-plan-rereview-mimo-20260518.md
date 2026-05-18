# Phase 10.5 Plan Re-Review — Fix Verification

**Reviewer**: MiMo
**Date**: 2026-05-18
**Gate**: P10.5 plan re-review
**Review type**: fix verification — 确认 controller accepted findings A1-A5 是否全部修复，修复是否引入新问题
**Reviewed artifact**: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
**Fix report**: `docs/reviews/phase10-5-plan-fix-codex-20260518.md`
**Controller adjudication**: `docs/reviews/phase10-5-plan-review-controller-adjudication-20260518.md`
**Source reviews**: `docs/reviews/phase10-5-plan-review-mimo-20260518.md`, `docs/reviews/phase10-5-plan-review-ds-20260518.md`
**Design truth**: `docs/host/design.md`
**Control truth**: `docs/host/implementation-control.md`

---

## Verdict

**PASS.** A1-A5 全部修复，无阻塞，无新 findings。Plan 可进入 accepted plan commit / implementation gate。

- **Blocking count**: 0
- **New findings**: 0
- **Residual risks**: 与原 plan 一致，无新增

---

## A1-A5 Per-Item Status

### A1. Slice dependency and Slice 2 request-shape boundary

**来源**: DS N1, DS C3, MiMo F7
**Status**: **Fixed**

**验证**:
- Plan line 281-284: 明确固定 `Slice 1 -> Slice 2 -> {Slice 3, Slice 4} -> Slice 5 -> Slice 6` sequencing。
- Plan line 288: "Slice 2 stop condition 可以使用当时代码库已有的 request shape 验证 `submit_followup(queue)` runtime wakeup，不要求提前迁移 `SubmitFollowupRequest` typed fields。"
- Plan line 291: "Slice 2 不得为了预留 wakeup 而提前实现 steer、retry 或 replay 语义。"
- Slice 2 non-goals (line 363): "Do not implement steer / retry / replay semantics or their special wakeup paths in this slice; Slice 2 proves only queue request wakeup using the current request shape."

**结论**: Slice 2 的 request-shape 边界和 forward-reference 约束均已显式说明。Implementation agent 无需自行判断 sequencing。

---

### A2. Public handle session/read wrappers ownership

**来源**: DS N2
**Status**: **Fixed**

**验证**:
- Plan line 351: "Public async handle delegation ownership is Slice 2: `ensure_session`、`create_session`、`get_session`、`get_run` must be exposed as async wrapper / delegation methods on the public handle, with handle-open validation and no Service access to the internal command handle."
- Plan line 352: "Public handle wrapper / delegation for later public commands belongs to this same facade: `submit_followup`、`resolve_wait`、`retry_run`、`replay_run`、`cancel_run`、`cancel_session_runs`、`close_session` may delegate to internal command primitives, while Slice 3 / Slice 5 own the command semantics they introduce or complete."

**结论**: `ensure_session` / `create_session` / `get_session` / `get_run` 的 public async handle delegation 显式归属 Slice 2。后续 command wrappers 也明确了 facade ownership 与 command semantics ownership 的分离。

---

### A3. HostEventStream disposition

**来源**: DS N3, MiMo F5
**Status**: **Fixed**

**验证**:
- Plan line 444: "If existing `HostEventStream` is present in `dayu.host` public exports, remove it from the Service-facing namespace. If retained at all, it may only be an internal type alias / Protocol equivalent to `AsyncIterator[HostEvent]`; it must not be a Service-facing context manager, subscription handle, or second public stream contract."
- 此行在 Slice 4 "Exact allowed changes" 中，明确给出了 implementation agent 的行动指令。

**结论**: 与 plan Public Contract Change List (line 90) 和 Readiness Review Closure (line 256) 一致。Slice 4 有显式处置指令。

---

### A4. Compactor baseline None semantics and field mapping

**来源**: DS N4, DS N5, DS C1, MiMo F3
**Status**: **Fixed**

**验证**:
- Plan line 238: "`compactor_baseline=None` 语义固定为 fail-closed：Host 没有可用 compaction 能力，不得隐式创建 fake compactor、不得静默忽略 context budget policy、不得把 ordinary Run override 当 compactor 配置使用。若当前 Run 在预算压力下需要 compaction 才能继续，必须以 typed budget / compaction-unavailable failure 结束该 Run 或拒绝该执行路径；短上下文本身未触发预算压力时可以正常运行。"
- Plan line 356: "Map `OpenHostOptions.compactor_baseline` to internal compactor fields: `context_compactor`、`compactor_runner_spec`、`compactor_runner_options`、`compactor_policy_ref`、`compact_artifact_root` and compact artifact directory creation policy. If `compactor_baseline is None`, propagate the fail-closed 'no compaction capability' state; do not install fake defaults."
- Coverage table line 274: S4 compact owner 已更新为 "Slice 1 + Slice 2 + Slice 6"，新增 "Slice 2 opener-to-internal compactor wiring 被覆盖" 断言。

**结论**: `compactor_baseline=None` 的 fail-closed 语义、Slice 2 映射职责、S4 owner 包含 Slice 2 wiring 均已显式说明。DS C1 (coverage table owner) 也一并修复。

---

### A5. HostToolingOptions shape note

**来源**: DS C2
**Status**: **Fixed**

**验证**:
- Plan line 146: "`HostToolingOptions` 复用当前代码库已有 typed shape，作为 construction-time 全量业务工具与 ToolRuntime governance 配置入口。若现有类型尚未显式承载 ToolRuntime policy 所需 typed fields，Slice 1 负责在该 typed shape 上补齐字段；不得改用 `extra payload`、service locator、profile lookup 或无结构 `dict` 传递 policy。"
- Slice 1 exact allowed changes (line 308): "Ensure `HostToolingOptions` remains the typed construction-time tooling policy shape; if existing fields do not cover ToolRuntime policy, add explicit typed fields there instead of `extra payload` / service locator."
- Readiness Review Closure (line 260): "复用 `HostToolingOptions` typed shape；若缺少 ToolRuntime policy typed fields，由 Slice 1 补齐，禁止 extra payload / service locator。"

**结论**: `HostToolingOptions` 复用策略、缺失字段补齐责任、禁止项均已显式说明。

---

## Scope Creep / New Issues Check

### 新增 public API

未发现。Fix 只在现有 plan 结构中增加澄清和 ownership 说明，未新增 Service-facing public API。

### Scope creep

未发现。Fix 严格限于 controller adjudication accepted A1-A5 范围。无新增 slice、无新增 non-goals、无新增 coverage table 行。

### 状态机 / schema / 持久化变更

未发现。`compactor_baseline=None` 的 fail-closed 语义是对已有 typed field 的行为澄清，不是状态机或 schema 变更。

### 与 design.md 冲突

未发现：
- Slice sequencing `1 -> 2 -> {3,4} -> 5 -> 6` 与 implementation-control.md 建议的 slice 切分逻辑一致，只是更细粒度。
- Public handle delegation 与 design.md §11 最小接口集一致。
- HostEventStream 内部化与 design.md §11 "HostEventView 是内部 diagnostic DTO" 一致。
- Compactor fail-closed 与 design.md §11 "compactor baseline independent" 一致。
- HostToolingOptions 复用与 design.md §11 construction-time options 设计一致。

### 与 implementation-control.md 冲突

未发现。所有 fix 均在 implementation-control.md Phase 10.5 已确认的约束范围内。

---

## Handoff-Readiness / Code-Generation-Readiness 确认

| 维度 | 状态 |
| --- | --- |
| Public API 无需重新设计 | ✓ 所有 public contract 已明确 |
| 状态机无需重新设计 | ✓ 状态迁移在各 slice 中明确 |
| Schema 无需重新设计 | ✓ 非 schema 变更 phase |
| File ownership 无需重新设计 | ✓ 每 slice allowed files 明确 |
| Test boundary 无需重新设计 | ✓ 每 slice tests/validation commands 明确 |
| Smoke success signal 无需重新设计 | ✓ coverage table 11 行完整 |
| Slice dependency 无需重新设计 | ✓ A1 修复后 sequencing 明确 |
| Public handle delegation 无需重新设计 | ✓ A2 修复后 ownership 明确 |

---

## Residual Risks

与原 plan 一致，无新增：

| # | Risk | Severity | Owner |
| --- | --- | --- | --- |
| R1 | Real runner matrix 全部 provider 不可用导致零 coverage | 中 | Slice 6 + Controller |
| R2 | Real compactor adapter 不可用 | 中 | Slice 6 + Controller |
| R3 | Phase 11 Recovery 可能需要微调 P10.5 frozen interfaces | 低 | Phase 11 |
| R4 | `OpenHostOptions` 字段数较多，Service 构造可能冗长 | 低 | Slice 1 |

---

## Artifact Path

`docs/reviews/phase10-5-plan-rereview-mimo-20260518.md`
