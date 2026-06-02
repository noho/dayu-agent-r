# WU-TOOL-02 Slice 2 Implementation Report

## Changed Files

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `docs/reviews/wu-tool-02-slice2-implementation-report-20260602.md`

## Implemented Plan Items

- 将 `ToolFactAcceptCandidate` 从旧 flat 顶层字段迁移为 Slice 1 子结构组合根：`identity`、`call`、`result`、`governance`、`idempotency`、`diagnostics`。
- 更新组合根中文 docstring，并将 fact-kind 跨结构校验迁移到组合根 validator。
- 迁移 `_tool_fact_accept_candidate()` 与 `_tool_fact_reuse_accept_candidate()`，由 producer 直接构造 typed 子结构。
- 迁移默认 accept barrier consumer 的 logging、幂等 scope、precondition context、payload descriptor check、event plan、EventLog payload、accepted evidence envelope、accepted ack、reject helper 读取路径。
- 更新 allowed tests 中的 candidate 构造 helper 与断言，移除旧超宽 flat constructor 用法。
- 保持 `_tool_awaiting_accept_candidate()` 与 `ToolAwaitingAcceptCandidate` 未修改。

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
```

结果：通过，`53 passed in 0.37s`。

```bash
source .venv/bin/activate && pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
```

结果：通过，`0 errors, 0 warnings, 0 informations`。

## Docs Decision

本 slice 明确禁止修改 README、配置、schema、plan、总控文档；本次仅写入 implementation report artifact。Host public API、EventLog durable payload 与用户使用方式未变，因此未更新 README。

## Semantic Confirmation

- Awaiting accept candidate 与 awaiting accept path 未修改。
- `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` payload key 未修改。
- accepted evidence envelope 字段与选择逻辑未修改，仅迁移 candidate 读取路径。
- duplicate governance attempt-local 语义未修改；测试中与 duplicate 无关的场景通过差异化参数避免误入 duplicate policy。
- memory、compaction、tool trace production consumer 未修改。
- wait、truncation、fetch_more、accept retry 行为未做 production 语义变更。

## Residual Risks / Uncovered Areas

- 本 slice 只运行 handoff 指定 focused tests 与指定 pyright 范围，未运行全仓测试。
- 其它未授权测试文件若仍直接构造或读取旧 flat candidate，需要在后续 slice 按各自 ownership 迁移。
- 未修改 duplicate governance、diagnostics、memory、compaction 独立测试文件；这些文件不在当前 allowed files。

## Stop Status

Slice 2 implementation complete. 未 commit、未 push、未创建 PR、未进入 review gate。
