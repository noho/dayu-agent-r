# WU-TOOL-02 Slice 1 Implementation Handoff

## Assignment

你是 implementation agent。当前 gate: implementation。当前 slice: Slice 1 `新增子结构与局部 validation helper`。

必须严格按 approved plan 执行：

- Plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Controller adjudication: `docs/reviews/wu-tool-02-plan-review-controller-adjudication-20260602.md`
- Plan re-reviews:
  - `docs/reviews/wu-tool-02-plan-re-review-mimo-20260602.md`
  - `docs/reviews/wu-tool-02-plan-re-review-ds-20260602.md`

## Allowed Files

- `dayu/host/tool_runtime.py`
- completion artifact: `docs/reviews/wu-tool-02-slice1-implementation-report-20260602.md`

不得修改其它 source、tests、README、配置、schema 或总控文档。不得 commit、push、PR、进入 review gate。

## Objective

在 `dayu/host/tool_runtime.py` 中新增后续迁移需要的 Host 内部 typed 子结构和局部 validation helper，但不要改变现有 `ToolFactAcceptCandidate` 顶层字段、producer、accept barrier consumer、EventLog payload、ToolRuntime 行为或 tests。

## Required Work

- 新增 Host 内部 frozen slots dataclass，命名可按 approved plan 微调，但职责必须覆盖：
  - identity: session/run/attempt/execution
  - call: iteration/tool call/tool identity/digests
  - result: outcome/payload/truncation/raw outcome
  - duplicate governance
  - governance policy
  - accept idempotency
  - diagnostics；若只含单字段，可按 plan 裁量保留为组合根直接字段，但本 slice 若新增 dataclass 也可接受
- 每个新增类必须有完整中文 docstring，至少包含参数、返回值、异常。
- 新增 validation helper 只校验本结构内部 invariant；跨子结构 / fact-kind 约束留给后续 Slice 2。
- 不新增 `Any`、`object`、无类型签名、兼容 facade、旧字段 property 或 public export。
- `ToolFactKind.LOST` 当前仍 unsupported，不要新增生产构造语义。

## Non-goals

- 不改变 `ToolFactAcceptCandidate` 当前顶层字段。
- 不迁移 `_tool_fact_accept_candidate()` 或 `_tool_fact_reuse_accept_candidate()`。
- 不迁移 `_accept_idempotency_scope()`、`_tool_result_payload()`、ack、EventLog payload helper 或 tests。
- 不修改 EventLog payload key、accepted evidence envelope、duplicate governance、wait、memory、compaction 或 tool trace 行为。

## Validation

必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py
```

## Completion Report

写入 `docs/reviews/wu-tool-02-slice1-implementation-report-20260602.md`，包含：

- changed files
- implemented plan items
- validation commands and results
- docs decision
- residual risks / uncovered areas
- explicit confirmation that no producer/consumer/test migration was performed
- stop status
