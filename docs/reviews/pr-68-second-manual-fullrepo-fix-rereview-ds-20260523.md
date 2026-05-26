# PR 68 Post-Draft Second Manual Full-Repo Fix — AgentDS Re-Review

## 结论：PASS

本轮修复正确关闭了总控 accepted scope 的全部 4 类 findings，未引入新的 correctness / stability / maintainability blocking regression。

---

## 已验证关键点

### 1. Public tool wiring smoke 测试 root cause 裁决

**原 finding**: review-211917 Finding 01 — `test_mock_tool_fact_enters_memory_and_next_run_input` 断言失败，期望 `event_id=event-tool-result-accepted-` 在后续 Run input 中出现但实际不存在。

**裁决结论**: 旧 smoke 断言过期，不修 production code。裁决正确。

**直接证据**:
- `dayu/host/memory.py:1192-1195` — TOOL_RESULT_ACCEPTED 分支明确注释："Accepted tool results only carry accepted evidence envelopes. Final evidence-backed facts are materialized by compacted context output in a later slice, not directly from raw tool result acceptance."
- `tests/host/test_memory_projection.py:1322` — `test_tool_result_accepted_does_not_project_evidence_backed_fact` 锁定该语义：TOOL_RESULT_ACCEPTED 只推进 cursor，不生成 evidence-backed fact。
- 后续 Run 依赖 recent raw turns / assistant conclusion 等 continuity，不要求 raw TOOL_RESULT_ACCEPTED event id 进入 stable memory block。

**修复**: 测试重命名为 `test_mock_tool_result_feeds_same_run_and_later_run_continuity`，断言改为：
- 确认 `"tool fact accepted"` 存在于 second run initial messages（continuity 保留）
- 确认 `"调用 lookup_mock_fact 查询 DAYU。"` 存在于 second run initial messages（用户原始指令保留）
- 显式确认 `"event_id=event-tool-result-accepted-"` 不存在（锁定新契约）

**验证**: 测试通过（codex 报告 1 passed）。

### 2. Service assembly 安全/配置边界测试

**原 findings**: review-211917 Findings 02, 05, 06, 07, 08。

| 原 Finding | 被测函数 | 新增测试 | 覆盖路径 |
|-----------|---------|---------|---------|
| 02 | `_render_headers` | `test_render_headers_requires_api_key_env` | env 缺 key、key 为空白字符串 |
| 02 | `_render_headers` | `test_render_headers_rejects_unresolved_placeholder` | header 含未解析 `{{OTHER_KEY}}` 占位符 |
| 06 | `_resolve_prompt_asset_path` | `test_resolve_prompt_asset_path_rejects_invalid_paths` | 空字符串、绝对路径、`../` 逃逸（parameterized） |
| 07 | `_tooling_options_from_discovery` | `test_tooling_options_from_discovery_empty_bundle_returns_none` | 空 definitions → None |
| 07 | `_tooling_options_from_discovery` | `test_tooling_options_from_discovery_requires_source_refs` | 非空 definitions + 空 source_refs → ValueError |
| 08 | `_tool_discovery_specs` | `test_tool_discovery_specs_requires_provider_location` | import_path 和 entry_point 均为 None → ValueError |
| 08 | `_tool_discovery_specs` | `test_tool_discovery_specs_uses_entry_point_location` | entry_point 正确映射为 discovery spec |
| 05 | `_compactor_agent_policy_from_scene_inputs` | `test_compactor_agent_policy_requires_selected_fields` | max_iterations/fallback_mode/max_consecutive_failed_tool_batches 缺失（parameterized 3 字段） |

所有新增测试均直接验证 fail-fast 路径，断言匹配对应 ValueError 消息片段。测试与生产代码的异常消息一致（已逐项核对 `host_assembly.py:598-623`, `host_assembly.py:640-689`, `host_assembly.py:760-793`, `host_assembly.py:939-964`, `host_assembly.py:1074-1093`）。

**验证**: 24 passed（codex 报告）。

### 3. runtime ToolsDiscovery `_validate_provider_output` 自包含 provider identity 校验

**原 finding**: review-211835 F4 — `_validate_provider_output` 在错误消息中使用 `output.provider_id` 但本函数未调用 `_require_provider_identity`。

**修复** (`dayu/runtime/tools_discovery.py:528-551`):
- `_validate_provider_output` 内部调用 `_require_provider_identity(output.provider_id)` 获取规范化 identity（line 542）
- 错误消息全部使用规范化后的 `provider_id`（line 548, 550）
- 返回值改为 `str`（规范化 identity），调用方 `discover_from_bindings` 直接使用返回值做重复检测（line 235-241）
- 消除了旧的"上游预校验 → 下游使用原始值"的隐式契约

**测试**: `test_empty_provider_identity_fails_inside_output_validation` — provider 返回 `provider_id="  "`（纯空白），验证在 `_validate_provider_output` 内部 fail-fast，错误消息匹配 `"provider identity"`。

**语义安全性**: 旧代码先 dedup 再 validate output，新代码先 validate output（含 identity 校验）再 dedup。两者等价——身份非法时均在重复检测前 fail，且错误消息现在使用规范化 identity。无回归。

**验证**: 10 passed（codex 报告）。

---

## 非阻塞风险

1. **Smoke 测试重命名**: `test_mock_tool_fact_enters_memory_and_next_run_input` → `test_mock_tool_result_feeds_same_run_and_later_run_continuity`。若 CI 配置或外部脚本硬编码了旧测试名，需同步更新。codex 文档已标注此风险。

2. **Compactor policy 字段覆盖不完整**: `_compactor_agent_policy_from_scene_inputs` 共校验 8 个必填字段，本轮 parameterized 测试覆盖 3 个（max_iterations, fallback_mode, max_consecutive_failed_tool_batches）。原始 review finding 05 要求"至少补 2-3 个"，已满足最低要求。剩余 5 个字段（continuation_max_attempts, allow_tool_calls, tool_execution_timeout_seconds, fallback_prompt, continuation_prompt）仍无直接单元测试，但与 `override is None` 共享同一 fail-fast 模式，实际回归风险极低。

3. **未跑全量测试**: codex 仅跑了受影响测试文件（36 passed）和 pyright（0 errors）。全量 1056 测试中预存 1 个无关失败（test_steer_replays_same_client_request_id_idempotently），本轮修改不应引入新失败。

---

## 审查范围确认

以下总控 deferred 项未纳入本轮 blocker 审查（按用户指令）：

owner_host_instance_id recovery blind spot、PromotionResult 语义、startup timeout 诊断、working_assumptions、fact-candidate-only partial projection、budget estimate、repair attempts、RAW_ASSISTANT_TURN、ensure_session idempotency、projection/memory CAS、helper 去重、secret redaction 去重、runner_events re-export、filelock marker warning、engine_ingest 拆分、admission durable private import、schema version message。

---

## 审查方法

- 阅读全部 3 个 review/fix 文档（review-211835, review-211917, codex-20260523）
- 阅读完整 `git diff`
- 核对 production code 变更点与对应测试断言（tools_discovery.py:528-551, host_assembly.py:598-689, host_assembly.py:760-793, host_assembly.py:939-964, host_assembly.py:1074-1093）
- 验证 root cause 裁决的直接证据（memory.py:1192-1195, test_memory_projection.py:1322）
- 未修改任何代码
