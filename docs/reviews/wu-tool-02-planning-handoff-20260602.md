# WU-TOOL-02 Planning Handoff

## Assignment

你是 planning agent。请为 `WU-TOOL-02 Accept Candidate Structure Cleanup` 生成 handoff-ready、code-generation-ready plan。

不要修改 source、tests、README、配置或 schema。只写 plan artifact：

`docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`

## Inputs

- Design source: `docs/host/design.md`
- Control source: `docs/host/host-core-followup-implementation-control.md`
- Code inspection artifact: `docs/reviews/wu-tool-02-discussion-code-inspection-20260602.md`
- Current branch: `refactor/wu-tool-02-accept-candidate-cleanup`

## Goal

规划一次内部结构清理：收敛 `ToolFactAcceptCandidate` 的 typed structure、命名、producer 和 consumer，把当前过宽 candidate 拆成职责清晰的组合结构，使普通 result、reuse、governed error 等不同 fact kind 的构造和校验只接触各自需要的子结构。

## Hard Boundaries

- 必须遵守 `docs/host/design.md` 中 ToolRuntime / accept barrier / EventLog / memory / compaction / tool trace 的设计边界。
- 不改变 evidence-backed fact 生成门槛。
- 不改变 duplicate、freshness、side-effect、wait、accepted evidence 或 replay/retry/resume 语义。
- 不引入兼容 wrapper、兼容 re-export、旧字段 facade 或 public API 扩展。
- 不把内部 accept candidate 变成 Host public API。
- 不新增 `Any`、`object`、无类型签名或 magic payload。
- 不把显式字段塞进 extra payload。
- 不做无关重构。

## Required Plan Content

Plan 必须包含：

- 动机与直接代码证据。
- 受影响文件 / 模块和明确 file ownership。
- 新 typed 子结构建议，至少覆盖 identity、tool call、result、governance、accept idempotency、diagnostics；具体命名可按现有代码边界调整。
- 每类 fact kind 的字段归属和校验规则：ordinary result、reuse、plain governed error、duplicate governed error。
- producer 迁移路径：普通工具 outcome candidate、reuse candidate、awaiting candidate 是否在 scope 内，以及为什么。
- consumer 迁移路径：accept barrier validation、EventLog payload、accepted evidence envelope、accepted ack、tool trace diagnostics、memory/compaction 读取路径、测试 helper。
- 小 slices，确保每个 slice 可独立 review 和验证。
- 每个 slice 的 allowed files/modules、non-goals、具体实现步骤、测试命令和预期断言。
- README/doc sync 决策：触发 `dayu/host/README.md` 和 `tests/README.md` 时只更新稳定说明，不写过程状态。
- Final review gate 决策：本 work unit 全部实现、常规 slice review 与 aggregate deepreview 通过后，controller 会追加派发 AgentMiMo 与 AgentDS 做并行全仓 review；plan 需要把该 gate 作为 ready-to-open-draft-PR 前置条件。
- stop conditions：发现需要改变 public contract、durable schema、EventLog 语义或 ToolRuntime 行为时停止并交回 controller。

## Suggested Evidence To Inspect

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_diagnostics.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/compact_material.py`
- `dayu/host/memory.py`
- `dayu/host/tool_trace.py`

## Completion Signal

Plan artifact 存在且足够 implementation agent 直接执行，不需要重新设计结构边界、字段归属、file ownership 或测试矩阵。若存在 blocking question，写入 plan 的 `Blocking Questions For Controller` 并停止。
