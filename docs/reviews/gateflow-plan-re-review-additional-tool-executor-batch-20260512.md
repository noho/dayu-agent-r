# Gateflow Additional Plan Re-review: ToolExecutor Batch Handshake

- **Gate**: plan re-review
- **Target plan**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- **Additional plan-fix**: `docs/reviews/gateflow-plan-fix-additional-tool-executor-batch-20260512.md`
- **Review inputs**:
  - `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512-ds.md`
  - `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512-mimo.md`
  - `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512.md`
  - `docs/reviews/gateflow-plan-fix-tool-executor-batch-20260512.md`
  - `docs/reviews/gateflow-plan-re-review-tool-executor-batch-20260512.md`
- **Date**: 2026-05-12
- **Reviewer conclusion**: pass

## Scope

本次复核只检查追加 plan-fix 是否充分处理 DS-01..06 与 Mimo F01..F06，以及 revised plan 是否因此仍然 handoff-ready / code-generation-ready。未修改生产代码、测试代码或原计划，只新增本 re-review artifact。

## Method

- 逐条对照 DS / Mimo review artifact 中的 Controller decision、plan-fix status 与 revised plan 实际文本。
- 重点挑战 Slice 1 保留 vertical checkpoint 的裁决是否有边界、顺序、审计点和 stop condition。
- 按 AGENTS.md 分层约束、无兼容 wrapper/facade/re-export、无 `Any` / `object`、Host 不越界实现等约束寻找新的 blocker。
- 读取当前仓库目录，确认 `dayu/host` 与 `dayu/service` 当前不存在，Host / Service discovery 的计划假设与代码事实一致。

## DS Findings Re-review

| Finding | Controller decision | Additional fix status | Revised plan evidence | Re-review |
|---|---|---|---|---|
| DS-01 Slice 1 过粗 | `accepted` | 作为 plan-risk 处理 | §9 明确保留 vertical checkpoint 的理由，禁止为了拆片引入旧 single request/context 兼容 wrapper、facade 或 re-export；§9 增加 Batch 1A-1D、每批检查、completion report 记录要求和 stop conditions。 | fixed |
| DS-02 `_ToolOutcomeRecord` 迁移 | `accepted` | 已补充内部 accepted record 语义 | §5.9 固定内部 accepted record outcome union 为 completed / failed / cancelled，要求 failed 与 cancelled 分开计数，`_all_records_failed` 只认 all-failed；§9 Step 26 和 §10 覆盖对应实现与测试。 | fixed |
| DS-03 `correlation_id` per-batch break | `accepted` | 已补充破坏面与验证 | §5.2 明确 `correlation_id` 改为 batch-level 且不含 `tool_call_id`；§5.7、§9 Validation、§10、§13 要求公开破坏说明、grep 和 completion report。 | fixed |
| DS-04 package exports | `accepted` | 已列明导出面 | §5.8 和 §9 Step 11 显式列出 `dayu/contracts/__init__.py`、`dayu/engine/contracts/__init__.py`、`dayu/engine/__init__.py` 的新增 / 移除符号，并要求 package export tests。 | fixed |
| DS-05 reconstruction helper | `accepted-with-clarification` | 已明确不提供公共 helper | §5.6 明确 Engine 不提供 public reconstruction helper，只暴露 stable snapshot / record shapes；§9 Slice 3 和 §10 要求测试 shape 足够重建。 | fixed |
| DS-06 design doc `SUSPENDED` 语义 | `accepted` | 已补充 docs scope | §9 Slice 3 Step 8、§11 要求更新 `docs/engine/design.md`，把 `SUSPENDED` 来源改为 batch outcome 含至少一个 awaiting record，并说明 terminal 同时携带 accepted / awaiting records。 | fixed |

## Mimo Findings Re-review

| Finding | Controller decision | Additional fix status | Revised plan evidence | Re-review |
|---|---|---|---|---|
| F01 Slice 1 过粗 | `accepted` | 与 DS-01 同源处理 | §9 解释不拆成 contracts-only / engine-only 的原因，并用 dependency batches、局部检查和 stop conditions 收敛。 | fixed |
| F02 Host 侧迁移路径未覆盖 | `partially-accepted` | 已补 Host / Service discovery | §8、§9 Validation、§10、§13 要求运行 `rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host dayu/service` 并记录结果；当前仓库确无 `dayu/host` / `dayu/service` 目录，因此不扩展 Host code implementation，只更新 `docs/host/tracking.md`。 | fixed for accepted scope |
| F03 Slice 1 缺 batch 行为测试 | `accepted` | 已补基本行为断言 | §9 Step 28 和 Expected assertions 要求多工具 batch 只调用一次 executor、每个工具产生 accepted 或 awaiting record、no-awaiting batch done counts 正确。 | fixed |
| F04 `tool_records.py` 动机不精确 | `accepted` | 已改动机表述 | §5.6 改为“降低耦合并让 batch snapshot / record 类型独立于 event data 与 run outcome 模块”，不再声称修复既有 mutual import。 | fixed |
| F05 Engine batch 内策略边界 | `accepted` | 已提升为硬架构约束 | §4 和 §6.1 明确 Engine 只调用一次 `ToolExecutor.execute`，不拆分、不并发、不审批、不限流，内部策略归 Host / ToolRuntime / batch executor。 | fixed |
| F06 `cancelled_count` 公共变化 | `accepted` | 已纳入破坏面 | §5.7 明确 `ToolCallsBatchDoneData` 新增 `cancelled_count: int`；§13 要求 completion report 公共破坏清单包含该字段。 | fixed |

## Vertical Checkpoint Challenge

Slice 1 仍然很大，但 revised plan 对“不拆片”的理由是成立的：本 work unit 明确禁止旧 single request/context 兼容 wrapper、facade、re-export，若把 contracts-only 作为可交付 slice，会在 Engine 仍引用旧形状时制造 pyright-red checkpoint，或诱导临时兼容层。

Bounded / ordered / auditable 复核结果：

- **Bounded**: §8 和 §9 列出 contracts、Engine contracts、Engine runtime、tests、docs 与 `rg` discovered files；Host / Service 只做 discovery 和 tracking，不扩展 Host 实现设计。
- **Ordered**: §9 将 Slice 1 拆成 Batch 1A additive contract shapes、1B public signature/export switch、1C Engine event/outcome and agent vertical migration、1D cleanup；最终交付仍以 Slice 1 pyright-green 为边界。
- **Auditable**: §9 要求每个 dependency batch 后运行检查并在 completion report 记录；§9 Validation、§10 final matrix 和 §13 completion report 给出可复核命令与断言。
- **No compatibility seam**: §4、§5.5、§5.7、§9 明确禁止旧 single request/context wrapper、facade、re-export 或字段别名；`FunctionToolExecutor` 被限定为新的 batch callable helper，不是旧接口适配层。
- **Stop conditions**: §9 明确若无法在不恢复旧兼容层前提下 pyright-green、非测试生产 pyright 错误超过 20、错误扩散到 §8 之外、或需要恢复旧兼容，即停止回 Controller。

注意：Batch 1B 之后的 pyright 可能只是审计信号，而非独立可交付 green checkpoint；计划文本已说明 dependency batch 不是可交付 slice，最终只有 Slice 1 完成后允许交付。因此这不是 blocker，但实现报告必须记录每批检查结果，避免把中间红态误认为可提交状态。

## Architecture / Scope / Constraint Review

- **Host 越界**: 未发现。计划把 batch 内审批、并发、限流、tool-level cancellation 归 Host / ToolRuntime，但当前仓库没有 Host / Service 目录；计划只要求 discovery、必要最小迁移和 `docs/host/tracking.md`，没有要求 Engine 实现 Host 治理。
- **分层边界**: 未发现违反。计划修改集中在 `dayu/contracts` 与 `dayu/engine`，并明确不把 Host / Service / UI / Fins 依赖引入 Engine 或 `dayu.runtime`。
- **无兼容代码**: 未发现计划引入兼容 wrapper/facade/re-export。计划反复要求移除旧 request/context 导出和旧 flat event fields，不保留字段别名。
- **无 `Any` / `object` 风险**: Revised plan 的新增公开 shape 均为具体 dataclass 与 union，没有要求使用 `Any` / `object` / extra payload。
- **Scope creep**: 未发现。Host / orphan cleanup 被保留为 residual tracking；Engine reconstruction helper 明确不做；外部长事务恢复、轮询、后台 job 生命周期治理均为 non-goals。
- **测试与文档**: §9、§10、§11 覆盖受影响测试、pyright、package exports、Engine docs、design doc 与 Host tracking；README 触发规则没有机械扩大。

## Findings

无新的 blocker finding。

## Open Questions

无 blocking open question。

## Residual Risks

- Slice 1 仍是大 vertical migration，review 和调试成本高。当前计划用 dependency batches、检查记录和 stop conditions 缓解，实施时必须严格按 §9 执行。
- Host / ToolRuntime orphan cleanup 仍是后续治理风险；当前 work unit 只更新 tracking，不实现 Host 生命周期治理。
- 下游调用方旧导入、旧 flat event/outcome 字段会被 intentional public break 破坏；计划已要求 docs 和 completion report 明示。

## Final Conclusion

pass。追加 plan-fix 与 DS-01..06、Mimo F01..F06 的 controller decisions 和 plan-fix status 一致，且关键修复已实际 reflected in revised plan。未发现新的 blocker、scope creep、Host 实现越界、兼容层计划、分层违规或 `Any` / `object` 签名风险。
