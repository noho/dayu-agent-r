# WU-OBS-SIGNALS-01 / OBS-SIG-02 Code Review

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-02 / P02 Tool Duration Signal`
- Reviewer: AgentMiMo
- Implementation artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-implementation-codex.md`
- Review artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-code-review-mimo.md`

## Findings

### F1. [MINOR] cancelled/failed outcome 的 tool_timing 内容未被测试断言

**直接证据：**

- `tests/host/test_toolruntime_accept_barrier.py:845-891` 的 `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` 使用 `_fact_kind_candidate` 构造 cancelled/failed 候选，`_fact_kind_candidate` 已在 tool_timing 字段传入 `_missing_tool_timing()`（行 1396-1397）。
- 该测试在行 881-885 断言了 `tool_fact_kind` 和 `policy_decision`，但未断言 payload 中 `tool_timing` 的内容。
- `test_toolruntime_executor.py:1338-1348` 同样在 `_accepted_ack_for_call` 中填入了 `missing_tool_timing`，但只在特定测试路径中验证。

**影响：** 当前 cancelled/failed 路径的 `tool_timing` 内容由 `_tool_fact_accept_candidate` 统一生成（行 5520），如果未来该路径的 timing 生成逻辑回归，现有测试不会捕获。

**建议：** 在 `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` 中追加对 `payloads[0]["tool_timing"]` 和 `payloads[1]["tool_timing"]` 的断言，至少验证 `status` 和 `schema_version`。

**风险：** 低。当前实现路径是统一的，回归概率小；但按 AGENTS.md "测试必须跟着实现边界迁移" 约束，应补齐。

### F2. [INFO] `_tool_result_meta` 对 `ToolAwaitingOutcome` 的防御性 TypeError

**直接证据：**

- `dayu/host/tool_runtime.py:5908-5925` 的 `_tool_result_meta` 对 `ToolAwaitingOutcome` 抛出 `TypeError`。
- 调用方 `_tool_fact_accept_candidate`（行 5520）仅在 completed/failed/cancelled 分支调用该函数，awaiting 路径已被上游过滤。

**影响：** 无。这是符合 AGENTS.md "设计下层组件接口时，必须假设上层组件不存在" 约束的合理防御性设计。

**建议：** 保留现状。该防御使 `_tool_result_meta` 作为独立 helper 仍然安全。

### F3. [INFO] `_tool_timing_from_meta` 的负 duration 检查相对于 `ToolResultMeta.__post_init__` 冗余

**直接证据：**

- `dayu/contracts/tool_result.py:56-59` 的 `ToolResultMeta.__post_init__` 已验证 `finished_at >= started_at`。
- `dayu/host/tool_runtime.py:5942-5943` 再次检查 `duration_ms < 0`。

**影响：** 无。符合 AGENTS.md "设计下层组件接口时，必须假设上层组件不存在" 约束。如果 `ToolResultMeta` 来自非标准构造路径（例如旧数据反序列化），该检查提供额外安全网。

**建议：** 保留现状。

### F4. [INFO] `_required_int` 对 bool 的防御性拒绝

**直接证据：**

- `dayu/host/tool_trace.py:1534-1553` 的 `_required_int` 使用 `isinstance(value, bool) or not isinstance(value, int)` 模式。

**影响：** 无。Python `bool` 是 `int` 子类，该模式是正确防御 JSON 反序列化中 `true`/`false` 被误读为整数的标准做法。

**建议：** 保留现状。

## Open Questions

无阻塞性开放问题。

## Residual Risk

| 风险 | Owner/Destination |
|---|---|
| 不填充 `ToolResultMeta` 的工具产生 `status="missing_tool_result_meta"`；这是 intentional limited signal，不是缺陷 | WU-OBS-00 analyzer 报告 limited signal |
| `duration_ms` 使用整数截断（`int(timedelta // 1ms)`），亚毫秒精度丢失；对工具耗时分析场景可接受 | 无需处理 |
| ISO timestamp 格式由 Python `datetime.isoformat()` 决定，当前测试验证了 `+00:00` 格式；若未来跨时区 timestamp 比较需求出现，需确认 analyzer 端解析兼容性 | WU-OBS-00 analyzer |

## Scope Creep Assessment

**无 scope creep。**

- 实现严格限制在 OBS-SIG-02 定义范围内：从 `ToolResultMeta` 产生 `tool_timing` signal 并投影到 Tool Trace。
- 未实现 P03 failure metadata、P04 partial tool-call diagnostics 或 analyzer aggregation。
- 未修改 Engine public contract、SQLite schema、ToolExecutor scheduling 或 ToolRuntime accept/governance 语义。
- `ToolAcceptResult` 新增 `tool_timing` 字段是 `TOOL_RESULT_ACCEPTED` payload 扩展的自然实现载体，不改变公共接口。

## Architecture Alignment

| 维度 | 状态 | 证据 |
|---|---|---|
| 分层边界 | PASS | 变更仅在 `dayu/host/tool_runtime.py`（Host ToolRuntime）和 `dayu/host/tool_trace.py`（Host Tool Trace projection），未触及 Engine、Service、UI 或 runtime 层 |
| Engine public contract | PASS | 无变更 |
| SQLite schema | PASS | 无变更 |
| ToolRuntime execution semantics | PASS | timeout、cancel、accept retry、duplicate governance、scheduling 语义均未改变 |
| EventLog payload contract | PASS | `tool_timing` 是 additive 字段，不修改或删除既有字段 |
| Design doc alignment | PASS | `docs/host/design.md:1658` 已定义 hot summary 可保存 duration；实现从 `ToolResultMeta` 同源获取，不使用 wall-clock 或 projection time |
| AGENTS.md coding constraints | PASS | 中文 docstring 完整；无 `object`/`Any`/无类型签名新增；无魔法字符串不合理扩散；无兼容 seam |
| AGENTS.md architecture constraints | PASS | 无反向依赖；无 God object/function；helper 函数模块级私有 |

## Test Coverage Assessment

| 测试维度 | 状态 | 证据 |
|---|---|---|
| Producer: meta present | PASS | `test_toolruntime_result_payload_carries_duration_from_result_meta` 覆盖 completed outcome 带 `ToolResultMeta` |
| Producer: meta missing | PASS | `test_engine_continues_only_after_toolruntime_host_accept` 断言 `missing_tool_result_meta` 状态 |
| Consumer: additive impact | PASS | `test_engine_continues_only_after_toolruntime_host_accept` 和 `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` 验证现有 consumer 容忍 additive 字段 |
| Hot/cold projection: available | PASS | `test_tool_trace_projects_tool_timing_available_and_missing_signals` 覆盖 available 和 missing 两个路径 |
| Hot/cold projection: malformed fail-closed | PASS | `test_tool_trace_rejects_malformed_tool_timing_signal` 覆盖负 duration、类型错误、missing-meta 非 null 字段三种 malformed 场景 |
| cancelled/failed tool_timing content | PARTIAL | `_fact_kind_candidate` 已传入 `_missing_tool_timing()`，但测试未断言 payload 中 tool_timing 内容。见 F1 |
| Pyright | PASS | 0 errors, 0 warnings, 0 informations |

**测试通过：** 80 passed in 0.60s

**Pyright：** 0 errors, 0 warnings, 0 informations

## Validation

- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py` → 80 passed in 0.60s
- `source .venv/bin/activate && pyright` → 0 errors, 0 warnings, 0 informations
- 动机与 root cause 成立：duration 来自 `ToolResultMeta` durable accepted outcome，不是 projection/wall-clock 猜测
- Producer 覆盖 completed/failed/cancelled outcomes；missing meta 产生 `missing_tool_result_meta`；`duration_ms` 非负整数
- Projection 仅 copy/validate `tool_timing`；malformed/负 duration fail closed 为 `HostDurableError`；missing meta 为 non-failing limited signal；hot/cold 同源
- 分层边界未被突破：Engine public contract、SQLite schema、ToolExecutor scheduling 不变
- 未提前实现 P03/P04 或 analyzer aggregation

## Verdict

**PASS with findings**

一个 MINOR 级别 finding（F1）：cancelled/failed outcome 的 tool_timing 内容未被测试断言。建议在后续修复中补齐 `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` 中对 `tool_timing` payload 的断言。该 finding 不阻塞 gate 通过，因为实现路径是统一的，回归风险低。

INFO 级别 findings（F2-F4）均为合理的防御性设计，无需修改。
