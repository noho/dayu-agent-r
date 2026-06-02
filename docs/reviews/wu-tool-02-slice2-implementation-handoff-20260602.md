# WU-TOOL-02 Slice 2 Implementation Handoff

## Assignment

你是 implementation agent。当前 gate: implementation。当前 slice: Slice 2 `组合根、producer、accept barrier consumer 与核心 tests 一次性迁移`。

必须严格按 approved plan 执行：

- Plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Slice 1 accepted commit: `d2916aa`

## Allowed Files

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- completion artifact: `docs/reviews/wu-tool-02-slice2-implementation-report-20260602.md`

不得修改其它 production files、tests、README、配置、schema、plan 或总控文档。不得 commit、push、PR、进入 review gate。

## Objective

把 `ToolFactAcceptCandidate` 从旧 flat 顶层字段迁移为 Slice 1 子结构组合根，并在同一 slice 内原子迁移 producer、accept barrier consumer 和核心测试，确保 slice 结束时 pyright 与 focused tests 通过。

## Required Work

- 将 `ToolFactAcceptCandidate` 顶层改为组合结构，并更新中文 docstring。
- 接入 Slice 1 validation helper；子结构校验内部 invariant，组合根 / fact-kind validator 负责 ordinary result、reuse、plain governed error、duplicate governed error 和 unsupported `LOST`。
- 迁移 `_tool_fact_accept_candidate()` 与 `_tool_fact_reuse_accept_candidate()`。
- 迁移 accept barrier consumer，包括 logging、idempotency scope、accept context、payload descriptor check、event plan、EventLog payload、accepted evidence envelope、accepted ack、reject/timeout helper 等当前读取旧顶层字段的路径。
- 保持 `_tool_awaiting_accept_candidate()` 和 `ToolAwaitingAcceptCandidate` 语义不变。
- 更新 allowed tests 中的 candidate construction helper 和 candidate field assertions，避免继续手写超宽 flat constructor。
- 不保留旧顶层字段 property / facade / re-export。

## Non-goals

- 不改变 dispatch、timeout、cancellation、truncation、fetch_more、accept retry 行为。
- 不修改 awaiting accept candidate。
- 不修改 tool trace / memory / compaction production consumer。
- 不改变 EventLog payload key、accepted evidence envelope、duplicate governance attempt-local 语义或 payload durability 语义。
- 不新增 `Any`、`object`、无类型签名或 extra payload。

## Validation

必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
```

## Completion Report

写入 `docs/reviews/wu-tool-02-slice2-implementation-report-20260602.md`，包含：

- changed files
- implemented plan items
- validation commands and results
- docs decision
- residual risks / uncovered areas
- explicit confirmation that awaiting / EventLog payload / memory / compaction / tool trace semantics were not changed
- stop status
