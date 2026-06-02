# WU-TOOL-02 PR Follow-up RR-TOOL-03 / RR-TOOL-04 Implementation Handoff

## Assignment

你是 implementation agent。当前 gate: draft PR follow-up fix。用户要求把 `RR-TOOL-03` 与 `RR-TOOL-04` 现在关闭，不再 defer。

## Motivation Judgment

动机成立：

- `RR-TOOL-03` 是明确的 regression protection gap：`ToolFactKind.LOST` 当前应在 `ToolFactAcceptCandidate` 中 fail-fast，但缺少显式测试。
- `RR-TOOL-04` 中“子结构直接单元测试”是可验证的小缺口，当前可以补齐。
- `RR-TOOL-04` 中“测试 helper 进一步收敛”不得扩大成跨测试文件共享 builder。跨文件共享 candidate factory 会增加测试耦合；当前最佳实践是继续使用 `tests/host/test_toolruntime_accept_barrier.py` 内已有局部 helper，只补直接 validator coverage。

## Allowed Files

- `tests/host/test_toolruntime_accept_barrier.py`
- completion artifact: `docs/reviews/wu-tool-02-pr-followup-rr-tool-03-04-implementation-report-20260602.md`

不得修改 production files、README、设计文档、总控文档、plan、其它 tests、配置、schema 或 PR metadata。不得 commit、push、PR。

## Required Work

1. 在 `tests/host/test_toolruntime_accept_barrier.py` 中补 `ToolFactKind.LOST` explicit negative test。
   - 使用现有 `_completed_candidate(...)` 或同文件局部 helper 构造候选。
   - 用 `dataclasses.replace` 修改 `tool_fact_kind=ToolFactKind.LOST`。
   - 断言构造 `ToolFactAcceptCandidate` 时 fail-fast，错误消息应能证明是 unsupported fact kind。

2. 在同一测试文件中补 accept candidate 子结构直接 validator tests。
   - 覆盖 `ToolAcceptIdentity` 空字段拒绝。
   - 覆盖 `ToolAcceptCall` digest 非法拒绝。
   - 覆盖 `ToolAcceptResult` payload digest 与 payload ref digest 不一致拒绝。
   - 覆盖 `ToolAcceptDuplicateGovernance` 缺 scope/message 或非法 prior ref 拒绝。
   - 覆盖 `ToolAcceptGovernance` 非 `ToolPolicyDecision` 拒绝。
   - 覆盖 `ToolAcceptIdempotency` semantic digest 非法拒绝。
   - 覆盖 `ToolAcceptDiagnostics` 非 diagnostic ref 拒绝。
   - 如果 pyright 对“故意传错类型”的测试不允许直接构造，请优先使用 `typing.cast` 到目标类型或局部 helper 表达 negative case；不要引入 `Any`、`object` 或无类型签名。

3. 不修改生产代码。
4. 不抽取跨文件共享 test builder；如需要 helper，只能在当前文件内使用模块级私有 helper，且必须有中文 docstring。

## Validation

必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py
source .venv/bin/activate && pyright tests/host/test_toolruntime_accept_barrier.py dayu/host/tool_runtime.py
```

建议再运行：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py
```

## Completion Report

写入 `docs/reviews/wu-tool-02-pr-followup-rr-tool-03-04-implementation-report-20260602.md`，包含：

- changed files
- tests added
- validation commands and results
- README/doc sync decision
- residual risk closure evidence
- stop status
