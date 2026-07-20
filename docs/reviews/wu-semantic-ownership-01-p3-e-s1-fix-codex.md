# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Fix - AgentCodex

## Status

`ready-for-controller-validation`

本 artifact 覆盖 P3-E S1 code review fix gate。只处理 controller adjudication 接受的四个 finding；未实施 S2 / S3，未修改 wait callback endpoint、accepted result projection、Fins direct runtime、Service fins_direct、CLI fins，未 commit / push。

## Accepted Findings Fix Result

### P3-E-S1-CR-F01 - stale `tests/tools/` cancellation hint assertions

处理结果：已修复。

- `tests/tools/test_doc_tools_provider.py`
  - `test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept`
  - `test_doc_toolruntime_cancel_terminates_real_doc_target_blocked_on_fifo`
- `tests/tools/web/test_web_tools_provider.py`
  - `test_web_toolruntime_cancel_real_process_target_has_no_late_accept`

变更：ToolRuntime synthetic cancellation failure 的 `hint == "tool_runtime_cancelled"` 断言改为 `hint is None`。保留 `accept_port.candidates[0].governance.policy_decision.reason_code == "tool_runtime_cancelled"`，证明治理 reason 仍留在 ToolRuntime-owned policy diagnostic path。

### P3-E-S1-CR-F02 - dead truncation `reason_code` contract

处理结果：已修复。

- 删除 `_truncation_failure(reason_code, message)` 的 `reason_code` 形参。
- 更新所有 `_truncation_failure(...)` 调用点，只传入 owner-authored failure `message`。
- 删除不再有生产语义的 `_TRUNCATION_*_REASON` 常量。
- 保持 `ToolResultFailure.error == "truncation_error"` 不变；当前代码没有直接证据显示下游 owner 需要更细的结构化 truncation error code。场景差异由 ToolRuntime owner-authored `message` 保留。

### P3-E-S1-CR-F03 - strengthen truncation failure tests

处理结果：已修复。

`tests/host/test_toolruntime_truncation_fetch_more.py` 新增 `_assert_truncation_failure(...)`，统一断言：

- `error == "truncation_error"`
- `message == <场景特定说明>`
- `hint is None`

覆盖场景：

- cursor missing: `truncation cursor is missing or no longer available`
- token mismatch: `truncation scope token does not match cursor`
- cursor already used: `truncation cursor has already been used`
- invalid request: `limit must be positive when provided`
- TTL expiry: `truncation cursor expired`
- scope mismatch: `truncation cursor does not belong to this run scope`
- digest mismatch: `truncation remainder digest mismatch`
- unsupported/unreplaceable target: `tool result target cannot be replaced safely`

unsupported target 通过测试专用 `_VanishingPathMapping` 覆盖：第一次路径读取成功，使截断创建 cursor；第二次替换读取失败，触发 ToolRuntime 防御分支。

### P3-E-S1-CR-F04 - accept rejected reason proof

处理结果：已修复。

`tests/host/test_toolruntime_executor.py::test_accept_rejected_does_not_expose_raw_fake_result` 现在断言：

- `error == "tool_accept_rejected"`
- `hint is None`
- owner-authored reject message 仍包含 `idempotency_conflict`
- raw fake result `must-not-leak` 不进入 message

该测试证明移除 `accept_rejected:*` hidden hint protocol 后，accept rejection reason 仍通过 accept barrier owner-authored message 可见。

## Owner Boundary / Propagation Audit

- ToolRuntime 是 synthetic governed / cancellation / truncation / accept failure projection 的语义 owner。修复继续落在 ToolRuntime helper 与 ToolRuntime integration tests，没有在 Engine、UI、Service 或下游展示层加特例。
- Truncation failure 事实路径：
  - 产生：`TruncationManager` / `FetchMoreToolCallable`
  - 校验：ToolRuntime cursor scope、token、TTL、single-use、remainder digest 与 request 参数校验
  - 投影：`_truncation_failure(message)` 构造 `ToolFailedOutcome(ToolResultFailure(error="truncation_error", message=<场景说明>, hint=None))`
  - LLM-facing：Engine 只会看到 error/message，不再看到 retired reason-code hint；测试锁定每个场景的 message 未坍缩。
- Cancellation failure 事实路径：
  - 产生：ToolRuntime cancellation / timeout bounded execution path
  - 诊断 owner：`ToolPolicyDecision.reason_code`
  - 投影：`_governed_failure_outcome(...)` 仍返回 `hint=None`
  - 集成测试：Doc/Web provider 通过真实 ToolRuntime path 断言 hint 已移除，同时 policy reason 保留。
- Accept rejected 事实路径：
  - 产生：Host accept barrier 返回 `ToolFactRejectedAck`
  - 诊断 owner：`ToolFactRejectedAck.message` / Tool Trace diagnostic reason
  - 投影：`_accept_failure_outcome(...)` 只使用 owner-authored message，不再构造 `accept_rejected:*` hint
  - 测试：idempotency conflict 在 message 中保留，raw fake result 不泄漏。

## Validation

通过：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_executor.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py -q
```

结果：`159 passed, 1 skipped in 13.47s`。

通过：

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py -q
```

结果：`233 passed, 1 skipped, 3 warnings in 19.70s`。warnings 为现有 edgar 依赖弃用提示。

通过：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 提示存在新版本。

通过：

```bash
rg -n "_truncation_failure|_TRUNCATION_.*REASON|_hint_with_diagnostic_refs|_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY|_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR|accept_rejected:|hidden-hint" dayu/host/tool_runtime.py tests/host tests/tools
```

分类：

- `_truncation_failure` 命中为当前 helper、生产调用点和测试 helper，均只接收/断言 message，不再包含 reason_code 形参。
- `_TRUNCATION_.*REASON` 无命中。
- `_hint_with_diagnostic_refs`、三枚 hidden-hint protocol 常量、`accept_rejected:`、`hidden-hint` 均无命中。

通过：

```bash
git diff --check
```

结果：无输出。

通过 coverage workaround：

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py --cov=dayu.contracts.tool_result --cov=dayu.host.tool_runtime --cov-report=term-missing -q -k 'not process_backed and not process_capsule and not process_backed_capsule'
```

结果：`137 passed, 17 deselected in 1.71s`；coverage：`dayu/contracts/tool_result.py 100%`，`dayu/host/tool_runtime.py 85%`，总计 86%。

## README Decision

已检查 README 触发规则与现有 README 职责：

- `dayu/host/README.md` 当前说明 ToolRuntime owner、accept barrier、truncation / fetch_more、process-backed business-authored hint；本修复不改变这些开发者稳定契约，只清理 retired hidden hint 协议和测试断言。
- `tests/README.md` 当前记录测试分层与覆盖范围；本修复未新增测试目录、未改变测试层级，只增强既有测试断言。

结论：README no-op。

## Residual Risk

- 本 fix gate 未运行全量仓库测试；已运行 controller 指定 S1+tools 覆盖、pyright、source scan、diff check 和 coverage workaround。
- S2 / S3 仍未实施，按 P3-E 后续 slice 继续。
- 工作树中存在与本轮无关的未跟踪 docs 文件，以及既有 `docs/host/issues-implementation-control.md` 修改；本轮未 touch / stage / 删除这些无关文件。

## Decision

`ready-for-controller-validation`
