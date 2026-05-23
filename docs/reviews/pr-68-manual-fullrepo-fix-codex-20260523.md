# PR 68 post-draft manual full-repo review repair

## 实际修复项

1. 修正 `tests/runtime/test_tools_discovery_digest.py` 的 non-string key digest 测试：构造 `ToolParametersSchema` 时不再被 `required` 提前拦截，测试现在覆盖 `normalize_json_value` 对非字符串 key 的 `TypeError`。
2. 在 `dayu/host/engine_ingest.py` 的 durable context 校验中增加 `run.current_attempt_id == envelope.attempt_id`，防止旧 Attempt 的 EngineEvent 污染当前 Run；补充 steer 后旧 Attempt 被拒绝、新 current Attempt 正常接收的测试，并同步更新既有旧 Attempt late event 的拒绝 reason 断言。
3. 在 `dayu/engine/runners/openai/tool_call_aggregator.py` 中将 synthetic index 改为负数 keyspace，并补充 position fallback 映射，避免 synthetic index 与 provider native index 碰撞；补充 SSE 回归测试。
4. 新增 `tests/service/test_weak_typing_guard.py`，按现有 AST 守卫风格扫描 `dayu.service` 的弱类型签名。
5. 更新 `tests/service/test_import_boundary.py`，将 `dayu.config` 纳入 Service 禁止导入前缀。
6. 在 `dayu/engine/agent.py` 的敏感异常 marker 中加入 `api key` 空格形式，并补充测试。
7. 在 `dayu/host/llm_compaction.py` 的 assignment 脱敏 pattern 中加入 `token` / `secret`，并扩展失败 outcome 脱敏测试。
8. 在 `dayu/engine/runners/openai/sse_parser.py` 中处理 `choices` 全部为非 dict 的 SSE chunk：无有效 usage 时以 protocol error 收口，不再静默成功空响应；补充测试。
9. 在 `dayu/service/host_assembly.py` 中为相对 project path 增加 `relative_to(workspace_root)` 校验；绝对路径保持原行为；补充测试。
10. 更新 `tests/README.md`，记录 Service import boundary / weak typing guard 的测试职责。

## Deferred 项

1. durable transaction rollback 失败 warning：该项会触及 durable transaction runner 错误/回滚路径，超出本轮 accepted 窄范围，且用户明确 deferred 了 durable 大范围补齐。
2. `waiting.py` 中 `resolve_semantic_digest is None` 的处理：当前 payload builder 已使用 `outcome_digest` 做 typed defensive fallback；改为拒写会改变等待恢复语义，容易扩大到 waiting 状态机行为，本轮不改。

## 验证结果

已运行并通过：

```bash
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery_digest.py tests/host/test_engine_ingest_mapping.py tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_old_protocol_parity_regressions.py tests/engine/runners/openai/test_protocol_error.py tests/service/test_weak_typing_guard.py tests/service/test_import_boundary.py tests/service/test_host_assembly.py tests/engine/test_agent_phase2.py tests/host/test_llm_compaction.py
```

结果：`146 passed in 2.12s`。

```bash
source .venv/bin/activate && pyright dayu tests
```

结果：`0 errors, 0 warnings, 0 informations`。

## README 检查结论

- `dayu/engine/README.md`：已说明 Runner / SSE 协议错误、日志脱敏和 EngineEvent 边界；本轮为内部健壮性修复，无需更新。
- `dayu/host/README.md`：已说明 EngineEvent 必须经 Host envelope identity 与 durable state 校验、旧 Attempt 不 resume、compactor 错误摘要脱敏；本轮为同一稳定边界补强，无需更新。
- `tests/README.md`：Service 新增 weak typing guard，且 import boundary 禁止项扩展到 `dayu.config`，已更新测试职责说明。

## 剩余风险

1. synthetic tool call delta 的 `tool_call_index` 现在可能为负数；这是内部 RunnerEvent 归属 key，用于避免与 provider native index 碰撞，最终 `ToolCallRequest.index_in_iteration` 仍保持从 0 开始的顺序。
2. 旧 Attempt late event 的拒绝 reason 更早收口为 `stale_execution_id`，不再走 terminal-late 的 `terminal_already_closed`；这与新增 current Attempt 同源校验一致。
3. optional deferred 项未处理，原因见 Deferred 项。
