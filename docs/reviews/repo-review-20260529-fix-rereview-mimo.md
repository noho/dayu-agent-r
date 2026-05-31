# Code Re-Review: Codex Fix

## Scope

- Gate: `code-review-re-review`
- Reviewer: AgentMiMo
- Date: 2026-05-29
- Input artifacts:
  - `docs/reviews/repo-review-20260529-204703.md` (review A, 26 findings)
  - `docs/reviews/repo-review-20260529-205643.md` (review B, 8 findings)
  - `docs/reviews/repo-review-20260529-fix-codex.md` (fix manifest, 11 items)
- Review scope: workspace diff 中与本轮修复相关的生产代码、测试、README、pyproject.toml

## 逐项核验

### F1 EventLog 同 event_id INSERT 阶段 UNIQUE 冲突重分类

- **代码证据**: `dayu/host/durable/event_log.py:344-405` — INSERT 包裹 `try/except sqlite3.IntegrityError`，捕获后 `read_event_by_id()` 重新读取：同 digest 幂等返回 `EventLogAppendResult(inserted=False)`，异 digest 抛 `HostEventIdentityConflictError`
- **测试证据**: `tests/host/test_event_log_multiprocess.py` — `test_append_event_reclassifies_insert_unique_race_as_identity_conflict` 通过 monkeypatch 注入 read/insert 交错，验证 `HostEventIdentityConflictError` 被正确抛出
- **结论**: PASS

### F2 Ollama api_key_ref=null 合法

- **代码证据**:
  - `dayu/engine/contracts/runner_spec.py:257` — `api_key_ref: str | None`
  - `dayu/service/host_assembly.py:939-970` — `_render_headers()` 在 `api_key_ref=None` 时跳过 API key 注入，仅做占位符检查
  - `dayu/service/host_assembly.py:911-935` — `_runner_spec_from_model()` 移除 `if model.api_key_ref is None: raise ValueError` 断言
- **测试证据**:
  - `tests/engine/contracts/test_runner_spec.py` — `test_runner_spec_allows_none_api_key_ref_for_local_provider`
  - `tests/service/test_host_assembly.py` — `test_render_headers_allows_missing_api_key_ref_without_placeholders`、`test_runner_spec_from_ollama_model_skips_api_key_header`
- **结论**: PASS

### F3 HostDurableStore.close() 拒绝活跃事务

- **代码证据**:
  - `dayu/host/durable/transaction.py:236-245` — `HostTransactionRunner` 新增 `_active_transaction_count` 计数器和 `has_active_transaction` 属性；`run_write` 和 `run_read` 均在 `BEGIN` 后递增、`finally` 块中递减，确保异常路径（含 CancelledError）计数正确
  - `dayu/host/durable/connection.py:95-101` — `close()` 在 `_closed` 检查后、`_connection.close()` 前检查 `has_active_transaction`，存在时抛 `HostDurableError`
- **测试证据**: `tests/host/test_durable_transaction.py` — `test_store_close_rejects_active_transaction` 在 `run_write` operation 内调用 `store.close()`，验证 `HostDurableError` 被抛出且事务仍可正常提交
- **结论**: PASS

### F4 ToolCallRequest.arguments 构造期校验

- **代码证据**: `dayu/contracts/tool_call.py:86-92` — `__post_init__` 遍历 arguments，空白 key 抛 ValueError；`_validate_json_value()` 递归校验非有限 float、空白嵌套 object key、非 JSON 兼容值（bytes/set 等落入最终 `raise ValueError`）
- **测试证据**: `tests/contracts/test_tool_call.py` — `test_tool_call_request_rejects_blank_argument_key`、`test_tool_call_request_rejects_non_finite_argument_number`
- **结论**: PASS

### F5 RunnerDone 不再静默覆盖更早完成原因

- **代码证据**: `dayu/engine/agent.py:1311-1352` — ContentCompleted 先到时 `state.finish_reason` 已设置；Done 到达且不一致时，`finish_reason = state.finish_reason`（保留先到值），仅记录 warning；Done 先到时正常设置
- **测试证据**: `tests/engine/test_agent_phase2.py` — `test_finish_reason_mismatch_logs_warning` 断言 `iteration_completed[0].data.finish_reason is FinishReason.STOP`（ContentCompleted 先到的 STOP 优先于 Done 的 LENGTH）
- **结论**: PASS

### F6 startup recovery 无 wakeup port 时输出 ERROR 诊断

- **代码证据**: `dayu/host/recovery.py:217-225` — `elif result.queue_promotion_sessions:` 分支在 `dispatch_wakeup_port is None` 且有待 promotion session 时记录 `_LOGGER.error("host.recovery.queue_promotion_wakeup_unavailable ...")`
- **测试证据**: `tests/host/test_recovery_scan.py` — `test_scan_accepted_without_wakeup_port_logs_error` 验证 ERROR 日志包含 `host.recovery.queue_promotion_wakeup_unavailable`
- **结论**: PASS

### F10 owner liveness pid 非正不再无限 inconclusive

- **代码证据**: `dayu/host/recovery_process.py:233-241` — `classify_orphan_candidate()` 在读取 `row = candidate.owner_liveness` 后立即检查 `if row.pid <= 0:`，直接返回 `PositiveOrphanProof(reason=_ORPHAN_REASON_PID_MISSING)`，绕过 `StdlibPidLivenessProbe.collect()`
- **测试证据**: `tests/host/test_recovery_orphan_classifier.py` — `test_invalid_owner_pid_is_positive_orphan_proof_without_probe` 验证 `pid=0` 时返回 `PositiveOrphanProof` 且 `reason == "owner_pid_missing"`
- **结论**: PASS

### F14 空 ToolDefinition.name 与空 ToolBundle 拒绝

- **代码证据**:
  - `dayu/contracts/tool_declaration.py:105-107` — `ToolDefinition.__post_init__` 新增 `if self.name.strip() == "": raise ValueError`
  - `dayu/contracts/tool_declaration.py:137-139` — `ToolBundle.__post_init__` 新增 `if not self.definitions: raise ValueError`
  - `dayu/runtime/tools_discovery.py:32-64` — `_NoToolBundle` sentinel 作为 `cast(ToolBundle, ...)` 传给 `ToolsDiscoveryResult`，避免构造空 `ToolBundle`
- **测试证据**:
  - `tests/contracts/test_tool_declaration.py` — `test_tool_definition_rejects_empty_name`、`test_tool_bundle_rejects_empty_definitions`
  - `tests/runtime/test_tools_discovery.py` — 现有测试增加 `assert result.tool_bundle is not None` 断言
  - `tests/service/test_host_assembly.py` — 删除 `test_tooling_options_from_discovery_empty_bundle_returns_none`（空 bundle 不再合法）
- **结论**: PASS

### F15 fallback_mode 最终值二次验证

- **代码证据**: `dayu/runtime/assembly.py:558-562` — `_select_value()` 返回后立即调用 `_validate_fallback_mode(fallback_mode.value, context=...)`，对直接构造 `AgentPolicyOverrideConfig` 绕过解析器的路径也生效
- **测试证据**: `tests/runtime/test_assembly_helpers.py` — `test_merge_agent_policy_config_revalidates_selected_fallback_mode` 验证 `run_override=AgentPolicyOverrideConfig(fallback_mode="finalize")` 触发 `RuntimeAssemblyFieldError`
- **结论**: PASS

### F16 prompt 渲染双花括号字面量保留

- **代码证据**: `dayu/runtime/scene_prepare.py:1065` — 移除 `"{{" in rendered or "}}" in rendered` 子串检查，仅保留 `_UNRESOLVED_PLACEHOLDER_PATTERN.search(rendered)` 正则检查
- **测试证据**: `tests/runtime/test_scene_prepare.py` — `test_literal_double_braces_without_placeholder_pattern_are_preserved` 验证 `"代码示例：{{ company"` 渲染后被保留
- **结论**: PASS

### pyproject.toml pytest.ini 注释

- **代码证据**: `pyproject.toml` — 删除 `# 具体 pytest 设置见 pytest.ini（保留为单一事实源）。` 注释（`pytest.ini` 文件不存在）
- **结论**: PASS

## 暂不实施项裁定审查

| 项目 | 裁定 | 合理性 |
|------|------|--------|
| Service 绝对路径配置逃逸验证 | 不改：配置来源是 package defaults 与 workspace config，受信任 | 合理。收窄为安全沙箱会破坏部署配置能力 |
| WAITING 超时取消 | 暂不实施 | 合理。状态机转换需仔细设计，非本轮 bugfix 范围 |
| Service 生产入口迁移 | 暂不实施 | 合理。涉及生产入口重构，需独立 slice |
| profile 继承 | 暂不实施 | 合理。配置机制变更，非本轮 bugfix |
| memory rebuild 原子化 | 暂不实施 | 合理。rebuild 期间空 projection 有自动恢复路径 |
| compaction estimator | 暂不实施 | 合理。LLM 输出质量问题，非代码 defect |
| conftest 重构 | 暂不实施 | 合理。测试基础设施改善，非本轮 bugfix |
| 端到端压测 | 暂不实施 | 合理。测试基础设施建设，非本轮 bugfix |

## 测试与类型验证

- `pytest tests/contracts/test_tool_call.py tests/contracts/test_tool_declaration.py tests/engine/contracts/test_runner_spec.py tests/engine/test_agent_phase2.py tests/host/test_durable_transaction.py tests/host/test_event_log_multiprocess.py tests/host/test_recovery_orphan_classifier.py tests/host/test_recovery_scan.py tests/runtime/test_assembly_helpers.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/service/test_host_assembly.py -q` — **201 passed**
- `pyright` — **0 errors, 0 warnings, 0 informations**

## README 同步

- `README.md` — 更新 `api_key_ref` 说明，支持 null
- `dayu/README.md` — 更新 `tools_discovery` no-tool sentinel 说明、`ToolBundle` 非空约束
- `dayu/config/README.md` — 更新 `api_key_ref` 支持 null 说明
- `dayu/engine/README.md` — 更新 `RunnerSpec` api_key_ref 可为空说明
- `dayu/host/README.md` — 更新 EventLog 并发重分类、非正 pid orphan proof、wakeup port ERROR 诊断、store close 活跃事务拒绝、ToolBundle 非空约束说明
- `tests/README.md` — 更新 scene prepare 双花括号字面量、tool declaration 空名/bundle 拒绝、runner_spec api_key_ref=None 测试说明

所有 README 变更准确反映代码修复内容，无过度描述或遗漏。

## 结论

**PASS**

11 个已修复项（F1、F2、F3、F4、F5、F6、F10、F14、F15、F16、pyproject.toml 注释）均有直接代码证据和测试验证，201 个受影响测试通过，pyright 无错误。暂不实施项裁定合理，README 同步完整。无 blocker。
