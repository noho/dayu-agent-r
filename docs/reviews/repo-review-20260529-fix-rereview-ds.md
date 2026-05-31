# Re-review — AgentCodex 修复判定

## 元信息

- **Gate**: code-review-re-review
- **审查者**: AgentDS
- **日期**: 2026-05-29
- **输入 artifact**:
  - Review A: `docs/reviews/repo-review-20260529-204703.md`
  - Review B: `docs/reviews/repo-review-20260529-205643.md`
  - 修复说明: `docs/reviews/repo-review-20260529-fix-codex.md`
- **审查范围**: 当前 workspace diff 中与本轮修复相关的生产代码、测试、README、pyproject.toml

## 判定

**PASS** — 所有核验项均通过直接代码证据与测试证据验证，无 blocker。

## 逐项核验

### F1: EventLog 并发 append 同 event_id UNIQUE 冲突重新分类 ✅

- **原始**: Review A 1-CRITICAL — 跨事务 UNIQUE 冲突被错误分类为通用 `HostUniqueConstraintError`
- **修复**: `dayu/host/durable/event_log.py` — INSERT 包裹 `try/except sqlite3.IntegrityError`，捕获后重读 event_id row，同 digest 幂等返回，异 digest 抛 `HostEventIdentityConflictError`
- **测试**: `tests/host/test_event_log_multiprocess.py` — `test_append_event_reclassifies_insert_unique_race_as_identity_conflict` 通过 monkeypatch 模拟 read/insert 交错，验证 `HostEventIdentityConflictError` 正确抛出
- **证据**: diff 第 401-521 行，测试通过

### F2: Ollama api_key_ref=null 合法 ✅

- **原始**: Review A 2-HIGH — Ollama 模型 `api_key_ref=null` 导致运行时 `ValueError`
- **修复**:
  - `dayu/engine/contracts/runner_spec.py` — `api_key_ref: str` → `api_key_ref: str | None`
  - `dayu/service/host_assembly.py` — `_runner_spec_from_model` 移除 `api_key_ref is None` 的硬性断言；`_render_headers` 签名改为 `api_key_ref: str | None`，`None` 时跳过 env 查询和 Authorization header 注入
  - `dayu/host/_execution_config_projection.py` — `required_json_text` → `optional_json_text`
- **测试**:
  - `tests/engine/contracts/test_runner_spec.py::test_runner_spec_allows_none_api_key_ref_for_local_provider`
  - `tests/service/test_host_assembly.py::test_render_headers_allows_missing_api_key_ref_without_placeholders`
  - `tests/service/test_host_assembly.py::test_runner_spec_from_ollama_model_skips_api_key_header`
- **证据**: diff 第 215-237 行（runner_spec）、第 838-875 行（_render_headers）、第 278-288 行（projection），测试通过

### F3: HostDurableStore.close() 拒绝活跃 transaction ✅

- **原始**: Review A 3-HIGH — close() 静默 rollback 未提交数据
- **修复**:
  - `dayu/host/durable/transaction.py` — 新增 `_active_transaction_count` 计数器与 `has_active_transaction` 属性；`run_write` 和 `run_read` 中 BEGIN 后 +1、COMMIT 的 finally 中 -1
  - `dayu/host/durable/connection.py` — `close()` 检查 `has_active_transaction`，活跃时抛 `HostDurableError`
- **测试**: `tests/host/test_durable_transaction.py::test_store_close_rejects_active_transaction` — 在 write transaction 内调用 close，验证拒绝且后续 COMMIT 正常完成
- **证据**: diff 第 379-399 行（connection）、第 522-598 行（transaction），测试通过

### F4: ToolCallRequest.arguments 构造期校验 ✅

- **原始**: Review A 4-HIGH — 空键、非 JSON 兼容值穿透到执行器
- **修复**: `dayu/contracts/tool_call.py` — 新增 `_validate_json_value()` 递归校验函数（检查 float 有限性、嵌套 object 空键、非 JSON 类型）；`__post_init__` 对 arguments 逐键校验
- **测试**:
  - `tests/contracts/test_tool_call.py::test_tool_call_request_rejects_blank_argument_key`
  - `tests/contracts/test_tool_call.py::test_tool_call_request_rejects_non_finite_argument_number`
- **证据**: diff 第 58-116 行，测试通过

### F5: RunnerDone finish_reason 不再静默覆盖 ✅

- **原始**: Review A 5-MEDIUM — ContentCompleted 与 Done 不一致时 Done 值无条件覆盖
- **修复**: `dayu/engine/agent.py` — mismatch 时保留先到的 ContentCompleted `finish_reason`，仅记录 warning 和 Done 的 provider_request_id
- **测试**: `tests/engine/test_agent_phase2.py::test_finish_reason_mismatch_logs_warning` — 断言更新为期望 `FinishReason.STOP`（ContentCompleted 值）而非 `FinishReason.LENGTH`（Done 值）
- **证据**: diff 第 174-213 行，测试通过

### F6: Startup recovery 无 wakeup port 时 ERROR 诊断 ✅

- **原始**: Review A 6-MEDIUM — ACCEPTED/QUEUED Run 在无 wakeup port 时被静默丢弃
- **修复**: `dayu/host/recovery.py` — 新增 `_LOGGER`；`scan()` 中 `queue_promotion_sessions` 非空但 `dispatch_wakeup_port is None` 时记录 ERROR 级别日志
- **测试**: `tests/host/test_recovery_scan.py::test_scan_accepted_without_wakeup_port_logs_error` — 设置 caplog 验证 ERROR 消息包含 `host.recovery.queue_promotion_wakeup_unavailable`
- **证据**: diff 第 599-631 行，测试通过

### F10: Orphan proof pid ≤ 0 不再无限 inconclusive ✅

- **原始**: Review A 10-MEDIUM — pid 损坏导致永久的 `OrphanProofInconclusive`
- **修复**: `dayu/host/recovery_process.py` — `classify_orphan_candidate` 中 `pid <= 0` 时直接返回 `PositiveOrphanProof`（reason=`owner_pid_missing`），无需 probe 调用
- **测试**: `tests/host/test_recovery_orphan_classifier.py::test_invalid_owner_pid_is_positive_orphan_proof_without_probe` — pid=0 验证返回 positive proof
- **证据**: diff 第 633-653 行，测试通过

### F14: 空 ToolDefinition/ToolBundle 构造期拒绝 ✅

- **原始**: Review A 14-MEDIUM — 空名称、空 bundle 可构造
- **修复**:
  - `dayu/contracts/tool_declaration.py` — `ToolDefinition.__post_init__` 拒绝空白 name；`ToolBundle.__post_init__` 拒绝空 definitions
  - `dayu/runtime/tools_discovery.py` — 新增 `_NoToolBundle` sentinel（通过 `cast` 满足 `ToolBundle` 类型），工具发现无结果时使用 sentinel 而非空 `ToolBundle`
  - `dayu/host/admission.py` — `_effective_tool_set_json` / `_no_tool_effective_tool_set_json` 改用原始 `ToolDefinition` 元组和 `tool_definitions_digest`，不再构造空 `ToolBundle`
  - `dayu/host/tool_runtime_schema_projection.py` — 新增 `tool_definitions_digest` 函数
- **测试**:
  - `tests/contracts/test_tool_declaration.py::test_tool_definition_rejects_empty_name`
  - `tests/contracts/test_tool_declaration.py::test_tool_bundle_rejects_empty_definitions`
  - `tests/runtime/test_smoke_host_public_multiturn_assembly.py` — 更新 `test_find_smoke_tool_only_inspects_passed_tool_bundle`，用非空 bundle 替代空 bundle 调用
  - `tests/service/test_host_assembly.py` — 移除 `test_tooling_options_from_discovery_empty_bundle_returns_none`（空 bundle 不再可构造）
- **证据**: diff 第 121-152 行（tool_declaration）、第 712-797 行（tools_discovery）、第 290-378 行（admission）、第 654-679 行（projection），测试通过

### F15: fallback_mode 最终值二次枚举验证 ✅

- **原始**: Review A 15-MEDIUM — `_select_value` 最终值未校验，直接构造 run override 可绕过
- **修复**: `dayu/runtime/assembly.py` — `merge_agent_policy_config` 对 `_select_value` 返回的最终 `fallback_mode` 调用 `_validate_fallback_mode`
- **测试**: `tests/runtime/test_assembly_helpers.py::test_merge_agent_policy_config_revalidates_selected_fallback_mode` — 传入非法 `fallback_mode="finalize"` 验证 `RuntimeAssemblyFieldError`
- **证据**: diff 第 681-695 行，测试通过

### F16: Prompt 渲染双花括号字面量误判修复 ✅

- **原始**: Review A 16-MEDIUM — `"{{" in rendered` 子串检查误杀合法双花括号字面量
- **修复**: `dayu/runtime/scene_prepare.py` — 移除 `"{{" in rendered or "}}" in rendered` 检查，仅保留 `_UNRESOLVED_PLACEHOLDER_PATTERN.search(rendered)` 正则匹配
- **测试**: `tests/runtime/test_scene_prepare.py::test_literal_double_braces_without_placeholder_pattern_are_preserved` — 验证 `{{ company`（无闭合）被保留而非报错
- **证据**: diff 第 695-711 行，测试通过

### pytest.ini 误导注释移除 ✅

- **原始**: Review B 05 — `pyproject.toml` 引用不存在的 `pytest.ini`
- **修复**: `pyproject.toml` — 删除 `# 具体 pytest 设置见 pytest.ini（保留为单一事实源）。`
- **证据**: diff 第 883-893 行

## 裁定不改项合理性判断

以下项被 Codex 裁定为"暂不实施"，逐项核验裁定合理性：

| 项 | 裁定 | 判断 |
|----|------|------|
| WAITING 超时取消 | 涉及状态机新增转换路径，非本轮 bugfix 范围 | 合理 — 需要独立设计文档 |
| Service 生产入口迁移 | 涉及 CLI/Web/WeChat 入口重构，非本轮范围 | 合理 — 需要跨层协调 |
| execution profile 继承 | 配置 schema 变更，非 bugfix | 合理 — 正交于本轮 hardening |
| memory rebuild 原子化 | 需要增加 rebuilding 标记和 compact builder 协调 | 合理 — 涉及多模块协同 |
| compaction estimator | 需要 deterministic token estimator 实现 | 合理 — 独立功能 |
| conftest 重构 | 测试辅助代码去重 | 合理 — 纯测试工程改进 |
| 端到端压测 | 测试基础设施 | 合理 — 独立工作流 |
| 绝对路径逃逸验证 | 当前配置来源受信任，现有语义依赖绝对路径 | 合理 — 安全沙箱与部署配置职责不同 |

所有裁定不改项判断合理，不构成本轮阻断。

## README 同步

以下 README 更新已按触发规则完成，内容与代码变更一致：

- `README.md` — `api_key_ref` 说明更新
- `dayu/README.md` — `tools_discovery` 和 `ToolBundle` 非空约束说明
- `dayu/config/README.md` — `api_key_ref` 说明更新
- `dayu/engine/README.md` — `RunnerSpec` 和 `api_key_ref=None` 说明
- `dayu/host/README.md` — 新增 recovery ERROR 诊断、EventLog identity conflict、store close 拒绝活跃 transaction、ToolBundle 非空约束说明
- `tests/README.md` — 上述测试覆盖更新

## 测试与类型检查

- **测试**: 227 passed, 0 failed
- **pyright**: 0 errors, 0 warnings, 0 informations

## 残余风险

1. **EventLog 并发 UNIQUE 测试** — 当前通过 monkeypatch 模拟 read/insert 交错覆盖分类分支；SQLite `BEGIN IMMEDIATE` 写事务会串行化多数真实 writer race，生产并发场景的实际竞态窗口极窄
2. **_NoToolBundle sentinel** — 使用 `cast(ToolBundle, _NoToolBundle())` 绕过类型检查，但实现了完整的 duck-type 接口（`definitions`、`to_tool_schemas`、`truncate_specs`），下游消费安全
3. **admission.py 重构** — `_effective_tool_set_json` / `_no_tool_effective_tool_set_json` 从直接构造 `ToolBundle` 改为操作原始 `ToolDefinition` 元组，语义等价但调用链变化需要关注 `tool_runtime_schema_projection` 中新旧 digest 函数的一致性

## 结论

PASS — 无 blocker。所有 11 项修复均通过代码审查和测试验证，裁定不改项判断合理。
