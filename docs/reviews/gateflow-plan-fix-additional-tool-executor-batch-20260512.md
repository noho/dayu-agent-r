# Gateflow Additional Plan-Fix Artifact: ToolExecutor Batch Handshake

- **Gate**: plan-fix
- **Target plan**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- **Review inputs**:
  - `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512-ds.md`
  - `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512-mimo.md`
- **Date**: 2026-05-12

## Scope

本次只修订计划与 review artifact，不实现生产代码或测试代码。目标是把 Controller 已裁决的 DS / Mimo findings 反映到 handoff-ready、code-generation-ready 的计划中。

## First-Principles Check

动机成立：ToolExecutor batch handshake 是公共契约与 Engine 状态机迁移，不是局部命名修复。Slice 1 过粗的风险真实存在，但严格拆成 contracts-only 与 engine-only 独立交付 slice 会在“禁止旧 single request/context 兼容 wrapper / facade / re-export”的约束下制造 pyright-red 或诱导兼容层。因此修订采用 bounded vertical checkpoint：保留单个可交付 Slice 1，同时增加 dependency batches、中间检查、行为测试和 stop conditions。

## Direct Evidence Checked

已按 Controller 要求检查 Host / Service 影响范围：

```bash
rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host dayu/service
```

当前结果：`dayu/host` 与 `dayu/service` 目录不存在，命令因目录不存在返回错误。因此计划不扩展 Host 代码实现，只要求 implementation planning / final validation 重新运行该命令、记录 stderr / exit code，并在无 Host implementation 时更新 `docs/host/tracking.md` 的 batch executor / orphan cleanup 跟踪说明。

## Plan Changes

### DS Findings

- **DS-01 accepted（as plan-risk）**：计划 §9 已解释为什么不拆成 contracts-only / engine-only 交付 slice，并新增 Batch 1A-1D、每批 pyright/pytest 检查、completion report 记录要求，以及三条 stop condition：非测试生产 pyright 错误超过 20 个、错误扩散到计划外模块、无法在不恢复旧 single request/context 兼容前提下归零。
- **DS-02 accepted**：计划新增 §5.9，并更新 §9 Slice 1 Step 26，明确内部 accepted record union 包含 `ToolCancelledOutcome`，count helpers、`_all_records_failed`、projection/injection 语义，以及 all-cancelled / all-failed / mixed failed+cancelled 测试。
- **DS-03 accepted**：计划 §5.2、§5.7、§9 Validation、§10 与 §13 已加入 `correlation_id` 从 per-call 到 per-batch 的 public break、grep 验证和 completion report 要求。
- **DS-04 accepted**：计划新增 §5.8，并更新 §9 Slice 1 Step 11，显式列出 `dayu/contracts/__init__.py`、`dayu/engine/contracts/__init__.py`、`dayu/engine/__init__.py` 中新增/移除的 batch、record 与 cancelled symbols。
- **DS-05 accepted-with-clarification**：计划 §5.6 明确 Engine 本 work unit 不提供公共 reconstruction helper，只暴露 stable snapshot/record data shapes；调用方自行构造消息，测试只验证 shape 足够重建。
- **DS-06 accepted**：计划 §9 Slice 3 与 §11 要求更新 `docs/engine/design.md` 状态机，说明 `SUSPENDED` 来源是 batch outcome 含至少一个 awaiting record，terminal 同时携带 `accepted_records` 与 `awaiting_records`。

### Mimo Findings

- **F01 accepted（as plan-risk）**：与 DS-01 同源处理。计划拒绝为了拆片引入 public/internal compatibility shim，改为 bounded、ordered、auditable 的 vertical Slice 1。
- **F02 partially-accepted**：计划 §8 Host / Service Discovery、§9 Validation、§10 与 §13 要求运行指定 `rg`；当前无 Host / Service 代码时不做 Host implementation，只更新 tracking；若实现时发现 pyright 必需的当前代码，则仅做最小迁移。
- **F03 accepted**：计划 §9 Slice 1 Step 28 与 Expected assertions 增加 batch happy-path 行为测试：多工具只调用一次 executor、每个工具产出 accepted/awaiting record、no-awaiting batch done counts。
- **F04 accepted**：计划 §5.6 重写 `tool_records.py` 动机为降低耦合、保持 shared snapshot/record types 独立于 event data/run outcome modules，不再声称当前存在 mutual imports。
- **F05 accepted**：计划 §4 Non-Goals 与 §6.1 将 Engine 只调用一次 `ToolExecutor.execute`、不拆分/并发/审批/限流提升为硬架构约束。
- **F06 accepted**：计划 §5.7 与 §13 加入 `ToolCallsBatchDoneData.cancelled_count` 公共契约变化与 completion report 要求。

## Review Artifact Changes

- DS review artifact 已将全部待裁决状态改为显式 Controller decision，并为每个 finding 增加 plan-fix status 指向修订后的计划段落。
- Mimo review artifact 已将全部待裁决状态改为显式 Controller decision，并为每个 finding 增加 plan-fix status 指向修订后的计划段落。
- 两份 review artifact 均明确：这些状态只表示 plan-fix 已完成，不表示生产代码、测试或文档实现已完成。

## Remaining Blockers

当前未发现需要 Controller 再裁决的计划 blocker。剩余风险是 implementation-time 风险：Slice 1 迁移仍然很大，必须严格执行 §9 的 dependency batches、stop conditions、Host / Service discovery 和 pyright/pytest 验证。
