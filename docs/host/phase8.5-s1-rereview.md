# P8.5 Slice 1 Fix Re-review

## Conclusion

pass

本次 re-review 只检查 fix 后当前 workspace，未修改生产代码、测试或 README。前序 review 的 3 个 finding 均已关闭；未发现新的 blocking finding。

## Findings

无。

## Closed Findings

### F01 credential-only scrub 已关闭

- 直接证据：`dayu/host/_credential_scrub.py:21-42` 只定义显式 credential key 与显式赋值正则，未把 `cursor`、`scope_token`、普通 `token` 作为敏感字段；`dayu/host/_credential_scrub.py:45-66` 递归只按显式 key / 显式凭证文本清洗；`dayu/host/_credential_scrub.py:95-121` 对 completed outcome 只清洗 `result.value`，保留 `truncation` 与 `meta`。
- EventLog 路径：`dayu/host/_event_translation.py:101-110` 在 Engine -> Host 事件翻译时清洗工具参数和工具结果；`dayu/host/_run_event_serializer.py:256-267` 在 serializer 侧再次清洗普通 tool payload；`dayu/host/_run_event_serializer.py:725-733` / `:759-770` 保留 truncation 的 `cursor`、`scope_token`、`scope_hash`、`limit`、`ttl_seconds` roundtrip。
- Trace 路径：`dayu/host/_tool_trace_projection.py:269-281` 写 trace 时清洗 arguments/result，同时把 truncation cursor/scope token 作为普通 trace 字段保留。
- 测试证据：`tests/host/test_phase6_run_event_serializer.py:135-212` 覆盖 serializer roundtrip 中 `API_KEY`/`api_key` 被替换为 `***`，`cursor`、`scope_token`、普通 `token` 保留；`tests/host/test_phase7_tool_trace_projection.py:199-263` 覆盖 trace record 同样策略。

### F02 durable owner scope guard 已关闭

- 直接证据：`dayu/host/_tool_runtime.py:296-334` 在 `HostToolRuntime.execute_tool_call()` 入口先解析 appender 并调用 `verify_active_owner()`，之后才进入 framework `fetch_more`、业务 executor 或 `RuntimeTruncateManager.apply_truncation()` mutation。
- Durable appender 证据：`dayu/host/_attempt_supervisor.py:223-241` 的 `AttemptScopedRunEventAppender.verify_active_owner()` 在独立短事务内执行 `AttemptLeaseStore.verify_owner()`，不写 RunEvent。
- 真实入口测试：`tests/host/test_phase8_tool_runtime_fencing.py:199-216` 覆盖 `ToolRuntimeToolExecutor.execute()` 无 owner scope 时业务 executor 未被调用；`tests/host/test_phase8_tool_runtime_fencing.py:244-279` 覆盖无 scope 的 framework `fetch_more` 不消费已有 cursor；`tests/host/test_phase8_tool_runtime_fencing.py:317-347` 覆盖 scope token 错误返回普通 failed outcome 且不写专用事实。

### F03 validation command path 已关闭

- 直接证据：`docs/host/phase8.5-plan.md:446-452` 与 `docs/host/phase8.5-s1-implementation-report.md:114-140` 均引用 `tests/contracts/test_tool_result_envelope.py`，不再引用不存在的 `tests/contracts/test_tool_result.py`。
- 复核命令：`rg -n "test_tool_result\\.py|tests/contracts/test_tool_result" docs/host/phase8.5-plan.md docs/host/phase8.5-s1-implementation-report.md` 对当前 plan/report 无命中；命中只存在于历史 review artifact 中。

## OLD/NEW Reliability Mechanisms

Retained:

- async lock / concurrent single-use：`dayu/host/_runtime_truncate_manager.py:221` 定义 `_read_lock`，`dayu/host/_runtime_truncate_manager.py:278-341` 在锁内读取、校验、续发 next cursor 并移除旧 cursor。
- 先查 record 再校验：`dayu/host/_runtime_truncate_manager.py:282-287` 先按 raw cursor 查 record，不存在直接普通失败。
- terminal guard：`dayu/host/_runtime_truncate_manager.py:288-292` 终态后返回普通 `run_terminal` failed outcome。
- run/session binding：`dayu/host/_runtime_truncate_manager.py:293-302` 调用 binding 校验，`dayu/host/_runtime_truncate_manager.py:645-664` 实现 session/run mismatch 拒绝。
- TTL / cleanup：`dayu/host/_runtime_truncate_manager.py:303-309` 过期时移除 cursor 并返回 `cursor_expired`；`dayu/host/_runtime_truncate_manager.py:608-622` 提供 opportunistic cleanup。
- scope token compare_digest：`dayu/host/_runtime_truncate_manager.py:667-684` 校验 cursor fingerprint 与 `hmac.compare_digest()` scope token。
- limit clamp：`dayu/host/_runtime_truncate_manager.py:316-317` 使用解析后的 limit 构造 chunk，`dayu/host/_runtime_truncate_manager.py:1002-1013` 将请求 limit clamp 到 record limit。
- raw cursor / scope token 不进 Memory / RunInput：本次指定验证的 `tests/host/test_phase3_conversation_memory_projection.py` 与 `tests/host/test_phase5_multiturn_no_governance_smoke.py` 均通过；`tests/README.md:105-111`、`:213-219` 已同步当前测试边界。

Intentionally not copied:

- 未恢复 OLD Engine 层 TruncationManager 位置；NEW 仍是 Host 私有 `RuntimeTruncateManager`。
- 未恢复 `TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_*` / `TOOL_FETCH_MORE_*` 专用 RunEvent；生产代码 grep 无命中。
- 未恢复 public fetch_more/cursor contract helper；生产 `dayu/contracts` 与 `dayu/host` grep 无 `framework_fetch_more_tool_schema` / `FRAMEWORK_FETCH_MORE_TOOL_NAME` / `ToolFetchMore*` public symbol 命中。

## Project Constraints

- 中文 docstring：本次重点新增/修改模块函数类均有中文 docstring；抽查 `_credential_scrub.py`、`_tool_runtime.py`、`_attempt_supervisor.py`、`_runtime_truncate_manager.py` 通过。
- 类型约束：指定 pyright 命令通过；重点新增签名未使用 `Any` / `object` 弱类型。`_framework_tools.py` 中 `"object"` 仅为 JSON schema 字面量。
- 兼容 wrapper / lazy import：未发现为旧 fetch_more/cursor contract 保留的兼容 wrapper 或 lazy import。
- README / tests docs：`tests/README.md:101-111` 与 `:213-219` 已描述当前 Slice 1 截断、EventLog、owner fencing 覆盖；未发现与本次 fix 相冲突的 README 表述。

## Validation Notes

已实际运行：

```bash
source .venv/bin/activate && python -m pyright dayu/host/ dayu/contracts/ tests/host/ tests/contracts/
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_package_exports.py -q
# 9 passed

source .venv/bin/activate && pytest tests/host/test_phase1_public_boundary.py tests/host/test_host_public_api_surface.py -q
# 7 passed

source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py -q
# 28 passed

source .venv/bin/activate && pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase5_multiturn_no_governance_smoke.py tests/host/test_phase8_tool_runtime_fencing.py tests/host/test_phase7_tool_trace_projection.py -q
# 43 passed
```

## Open Questions

无 blocking open question。
