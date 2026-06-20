# WU-ENG-02-R1 Code Review Fix Report - AgentCodex

- **Work unit**: WU-ENG-02-R1 Provider Debugging Correlation Default Enablement And Fallback Diagnostics
- **Gate**: code-review fix
- **Agent**: AgentCodex
- **Date**: 2026-06-20
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Accepted plan artifact**: `docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md`
- **Implementation artifact**: `docs/reviews/implementation-wu-eng-02-r1-codex-20260620.md`
- **Code review artifacts**:
  - `docs/reviews/code-review-20260620-213746.md`
  - `docs/reviews/code-review-20260620-214050.md`

## Scope

只处理 controller 接受的低风险 code review fixes。未处理 `_lost_host_event` 后缀建议，因为 controller 已明确 rejected：当前 `_lost_lifecycle_plan` 写入 `provider_request_id=None` 和 `client_correlation_id=None`，且本 WU scope 是 failed terminal。

## Findings Addressed

1. **terminal diagnostic helper 直接测试覆盖**
   - 新增 `tests/host/test_terminal_diagnostics.py`。
   - 覆盖 only provider id、only client id、both ids、both absent、message is `None` with ids、message is empty string with ids、id truncation。
   - 双 id 断言固定顺序为 `provider_request_id` 在前，`client_correlation_id` 在后。

2. **terminal suffix 双 id 格式与空字符串消息行为**
   - 更新 `dayu/host/_terminal_diagnostics.py`。
   - `message=""` 且存在诊断 id 时按无 message 处理，返回纯 suffix，避免前导空行。
   - 未改变 durable payload validation 或 call-site 写入语义；改动仅在 public projection helper 输出边界。

3. **Tool Trace raw payload ref fallback 覆盖**
   - 更新 `tests/host/test_tool_trace_projection.py`。
   - 新增 `ENGINE_EVENT_DIAGNOSTIC` 场景：`provider_request_id=None`、`client_correlation_id` 存在、`raw_payload_ref` 存在。
   - 断言 hot row `diagnostic_ref == raw_payload_ref`，`client_correlation_id` 保留；cold JSONL 保留 `diagnostic_refs` 与 `client_correlation_id`。

## README Check

已检查 `tests/README.md`。本次没有新增测试层级、运行入口或测试职责边界，只是在现有 Host terminal / Tool Trace 测试层内补覆盖，因此未更新 README。

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_terminal_diagnostics.py tests/host/test_read_api_terminal_policy.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
```

Result: `51 passed in 0.55s`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

Pyright printed the existing version notice: `v1.1.409 -> v1.1.410`.

```bash
git diff --check
```

Result: passed with no output.

## Residual Risks

None.
