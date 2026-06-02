# WU-TOOL-02 PR Follow-up RR-TOOL-03 / RR-TOOL-04 Implementation Report

## Changed Files

- `tests/host/test_toolruntime_accept_barrier.py`
- `docs/reviews/wu-tool-02-pr-followup-rr-tool-03-04-implementation-report-20260602.md`

## Tests Added

- 新增 `ToolFactKind.LOST` 显式负例：使用 completed candidate 作为基线，通过 `dataclasses.replace` 改为 `ToolFactKind.LOST`，断言 candidate 构造期以 `unsupported tool_fact_kind` fail-fast。
- 新增 `ToolAcceptIdentity` 直接 validator 负例，覆盖 `session_id`、`run_id`、`attempt_id`、`execution_id` 空字段拒绝。
- 新增 `ToolAcceptCall` 直接 validator 负例，覆盖非法 digest 拒绝。
- 新增 `ToolAcceptResult` 直接 validator 负例，覆盖 `payload_digest` 与 `payload_ref.payload_digest` 不一致拒绝。
- 新增 `ToolAcceptDuplicateGovernance` 直接 validator 负例，覆盖缺 `duplicate_scope`、缺 `duplicate_decision_message`、非法 `reuse_prior_event_refs` 拒绝。
- 新增 `ToolAcceptGovernance` 直接 validator 负例，覆盖非 `ToolPolicyDecision` 拒绝。
- 新增 `ToolAcceptIdempotency` 直接 validator 负例，覆盖非法 `semantic_input_digest` 拒绝。
- 新增 `ToolAcceptDiagnostics` 直接 validator 负例，覆盖非 `ToolTraceDiagnosticRef` 拒绝。

## Validation Commands And Results

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py`
  - 结果：`24 passed in 0.34s`
- `source .venv/bin/activate && pyright tests/host/test_toolruntime_accept_barrier.py dayu/host/tool_runtime.py`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py`
  - 结果：`56 passed in 0.41s`

## README / Doc Sync Decision

本次只补测试覆盖与 review artifact，不修改 production 接口、CLI、配置、schema、架构边界或用户可见行为。按 handoff 限制与 README 触发规则，不更新 README、production 文档或 control doc。

## Residual Risk Closure Evidence

- `RR-TOOL-03`：`ToolFactKind.LOST` 已有显式 negative test，证明当前 LOST 不会被误当作 accepted result/reuse/governed fact，而是在 candidate 构造期 fail-fast。
- `RR-TOOL-04`：accept candidate 各子结构的直接 validator 负例已补齐，覆盖空字段、非法 digest、payload ref digest mismatch、duplicate governance 字段组合、policy 类型、idempotency digest 与 diagnostic ref 类型。
- 未引入跨文件共享 test builder，新增 helper 需求不存在；测试仍沿用本文件局部构造方式。

## Stop Status

已完成 implementation。未修改 production、README、control doc；未 commit、push 或创建 PR。
