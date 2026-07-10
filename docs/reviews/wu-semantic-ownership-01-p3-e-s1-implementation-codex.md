# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Implementation - AgentCodex

## Status

`implementation-pass`

本 artifact 只覆盖 P3-E Slice S1。未实施 S2 / S3，未修改 wait callback endpoint、accepted result projection、Fins direct runtime、Service fins_direct、CLI fins、control doc，未 commit / push。

## Files Changed

- `dayu/contracts/tool_result.py`
- `dayu/host/tool_runtime.py`
- `tests/contracts/test_tool_result_envelope.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/fins/test_fins_storage_provider.py`

未修改 README。

## Owner Boundary And Propagation Audit

- `ToolResultSuccess.ok` / `ToolResultFailure.ok`
  - 事实产生与校验 owner：`dayu.contracts.tool_result`。
  - 持久化 / 投影消费者：ToolRuntime、Engine tool message、Host accepted result payload / trace / memory。
  - 本 slice 在构造边界 fail closed：`ToolResultSuccess.__post_init__` 要求 `ok is True`；`ToolResultFailure.__post_init__` 先要求 `ok is False`，再做原有字段完整性校验。
  - 一致性结论：错误 discriminator 不再能越过 contract 构造边界进入 Host / Engine 分支。

- ToolRuntime synthetic failure hint
  - 事实产生 owner：`dayu.host.tool_runtime`。
  - 诊断 owner：ToolRuntime policy decision、accept result、Tool Trace diagnostic emitter、failure metadata。
  - LLM-facing 投影：Engine 会消费 `ToolResultFailure.hint`；因此治理 reason code、accept rejection reason、diagnostic ref 不应写入 hint。
  - 本 slice 修改 `_truncation_failure(...)`、`_governed_failure_outcome(...)`、`_accept_failure_outcome(...)`、`_awaiting_accept_failure_outcome(...)`，统一让 synthetic governed / truncation / accept / awaiting-accept failure 的 `hint=None`。
  - 一致性结论：治理码仍在 policy decision / diagnostic / message 路径，LLM-facing hint 不再承载 hidden governance protocol。

- Diagnostic propagation
  - ToolRuntime accept retry exhaustion 仍通过 `ToolTraceDiagnosticRecord(reason_code="accept_timeout", ...)` 发出诊断 ref。
  - accept rejected 无 diagnostic refs 时仍补发 `ToolTraceDiagnosticRecord(reason_code="accept_rejected", ...)`，该 reason 只作为 owner diagnostic，不再拼入 hint。
  - accepted governed / failed / cancelled facts 的 `failure_metadata.diagnostic_refs` 路径未改动。

## last_error_code Audit Result

审计范围：`dayu/host/tool_runtime.py` 中所有 `last_error_code` 命中。

- `ToolFactAcceptTimedOut.last_error_code`：保留 contract 字段校验；accept retry 捕获 `HostTransactionRetryExhaustedError` 时写入 `accept_ack_lost`，普通 timed-out result 透传 port 返回的 `last_error_code`。
- `_accept_with_retry(...)`：最终 timeout 继续发出 `accept_timeout` Tool Trace diagnostic，并返回携带 `last_error_code` 与 `diagnostic_refs` 的 `ToolFactAcceptTimedOut`。
- `_accept_failure_outcome(...)`：不再把 `last_error_code` 写入 hint；若存在，写入 self-contained `message`，例如 `last_error_code=ack_lost`。
- `ToolAwaitingAcceptTimedOut.last_error_code`：Host waiting contract 字段未改。
- `_accept_awaiting_with_retry(...)`：最终 timeout 继续发出 `accept_timeout` Tool Trace diagnostic，并返回携带 `last_error_code` 与 `diagnostic_refs` 的 awaiting timeout result。
- `_awaiting_accept_failure_outcome(...)`：不再把 `last_error_code` 或 diagnostic refs 写入 hint；若存在，写入 self-contained `message`，例如 `last_error_code=accept_ack_lost`。
- durable wait / poll 相关 `last_error_code` 命中位于其它 owner 的 wait-state / read-model 测试中，非 S1 ToolResultFailure.hint 路径。

新增 / 调整测试证明：

- `test_accept_timeout_bounded_retry_returns_governed_error` 断言 `hint is None`、`message` 保留 `last_error_code=ack_lost`、Tool Trace diagnostic 仍有 `accept_timeout`。
- `test_awaiting_accept_timeout_returns_governed_error` 断言 awaiting accept timeout 的 `hint is None` 且 `message` 保留 `last_error_code=accept_ack_lost`。
- `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref` 断言 `hint is None`、`message` 保留 `last_error_code=accept_ack_lost`、Tool Trace diagnostic 仍有 `accept_timeout`。

## Hidden Hint Helper / Constants Cleanup Result

已删除：

- `_hint_with_diagnostic_refs(...)`
- `_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`
- `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`
- `_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`

`rg` 结果：

- `_hint_with_diagnostic_refs`：无命中。
- 三个 hidden-hint protocol 常量：无命中。
- `accept_rejected:`：无命中。
- `hidden-hint`：无命中。

剩余 `accept_rejected` 命中分类：

- `tool_accept_rejected` / `tool_awaiting_accept_rejected`：ToolResultFailure.error 机器错误码，非 hint。
- `_TOOL_RUNTIME_ACCEPT_REJECTED_REASON = "accept_rejected"`：Tool Trace diagnostic reason，非 hint；`tests/host/test_toolruntime_diagnostics.py` 仍断言该 owner diagnostic。

## Tests And Validation Outputs

通过：

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py -q
```

结果：`151 passed, 3 warnings in 14.05s`。warnings 来自 edgar 依赖弃用提示。

通过：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 提示有新版本可用。

通过：

```bash
rg -n "last_error_code|_hint_with_diagnostic_refs|_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY|_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR|accept_rejected:|hidden-hint" dayu/host/tool_runtime.py tests/host
```

分类：

- `last_error_code` 命中为 owner contract、accept retry state、日志、message preservation 测试，以及 wait-state / read-model 其它 owner 测试。
- hidden-hint helper / 常量、`accept_rejected:`、`hidden-hint` 均无命中。

通过：

```bash
git diff --check
```

结果：无输出。

附加 coverage 尝试：

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py --cov=dayu.contracts.tool_result --cov=dayu.host.tool_runtime --cov-report=term-missing -q
```

结果：失败。失败原因不是断言变化，而是 pytest-cov 下 process-backed/spawn 测试出现 `multiprocessing` pickling error（`Can't pickle <function rebuild_connection ...>`）和未启动 process join assertion。coverage 已输出的部分为 `dayu/contracts/tool_result.py 100%`、`dayu/host/tool_runtime.py 77%`；因此未能用当前 coverage 命令证明 `tool_runtime.py >= 80%`。不带 coverage 的同一测试集合已通过。

## README Update Decision

- 已按触发规则读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。
- 已读取 `tests/README.md` 当前职责说明。
- 本 slice 改变的是 ToolRuntime synthetic governed / truncation / accept failure 的 hidden hint 投影，以及 contract discriminator invariant；`dayu/host/README.md` 当前只说明 Host / ToolRuntime owner 边界、process-backed 业务 failed envelope hint 映射和取消/超时治理，没有声明治理 reason code 会进入 `ToolResultFailure.hint`。业务-authored process-backed failed envelope hint 映射未改变。
- `tests/README.md` 只记录测试分层和已有覆盖范围；本次未新增测试目录或测试层级。

结论：README no-op。

## Residual Risks / Blockers

- Coverage residual：pytest-cov 与 process-backed spawn 测试组合在当前环境失败，无法完成单文件 coverage gate；需要 controller 或后续环境层面决定是否用分离 coverage 命令、过滤 process-backed cases，或修复 coverage/spawn 交互。
- 本 slice 未运行不在 required list 内的全量 Host / Engine 测试；rg 已确认 hidden-hint 协议残留不存在，pyright 全量通过。
- S2 / S3 的 accepted status projection、wait callback typed provider ref、Fins direct RESULT protocol 仍未实施，按计划留给后续 slice。
