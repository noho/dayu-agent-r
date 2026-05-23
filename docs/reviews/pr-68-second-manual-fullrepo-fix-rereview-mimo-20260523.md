# PR 68 second manual full-repo fix re-review — AgentMiMo

## 结论

**PASS**

## 已验证关键点

### 1. Public tool wiring smoke 断言重设计

- **原断言** `test_mock_tool_fact_enters_memory_and_next_run_input` 期望 `"event_id=event-tool-result-accepted-" in joined`，实际失败。
- **新断言** `test_mock_tool_result_feeds_same_run_and_later_run_continuity` 改为三重断言：
  - `"tool fact accepted" in joined`：确认工具结果文本进入 continuation。
  - `"调用 lookup_mock_fact 查询 DAYU。" in joined`：确认用户 query 作为对话连续性上下文保留。
  - `"event_id=event-tool-result-accepted-" not in joined`：确认 raw event id 不物化到 memory projection。
- **裁决合规性**：符合 P12.5 设计。`docs/host/design.md` 明确规定 `evidence_backed_facts` 只来自 accepted evidence refs 的 compaction-gated extraction；`TOOL_RESULT_ACCEPTED` 通过 accept barrier 记录 accepted evidence envelope，但不直接物化 stable evidence-backed fact。已有 `test_tool_result_accepted_does_not_project_evidence_backed_fact` 锁定该语义。后续普通 Run 依赖 recent raw turns / assistant conclusion 等 continuity，不要求 raw tool result event id 进入 stable memory block。原断言属于旧契约残留，新断言正确反映当前设计。

### 2. Service assembly 安全/配置边界测试

| 被测函数 | 测试用例 | 匹配的 ValueError 路径 | 验证 |
|---------|---------|---------------------|------|
| `_render_headers` | env 缺 key (`{}`) | `api_key is None` → `"missing env {api_key_ref}"` | ✓ |
| `_render_headers` | key 为空白 (`"   "`) | `api_key.strip() == ""` → 同上 | ✓ |
| `_render_headers` | 未解析占位符 | `_ENV_PLACEHOLDER_PATTERN` 匹配 → `"unresolved env placeholder"` | ✓ |
| `_resolve_prompt_asset_path` | 空字符串 | `_require_non_empty_text` → `"must not be empty"` | ✓ |
| `_resolve_prompt_asset_path` | 绝对路径 | `path.is_absolute()` → `"must be relative"` | ✓ |
| `_resolve_prompt_asset_path` | `../` 逃逸 | `relative_to` 抛 ValueError → `"escapes prompt asset root"` | ✓ |
| `_tooling_options_from_discovery` | 空 bundle | `not tool_bundle.definitions` → `return None` | ✓ |
| `_tooling_options_from_discovery` | 有工具无 source_refs | `not source_refs` → `"source refs"` | ✓ |
| `_tool_discovery_specs` | 缺 import_path 和 entry_point | `raise ValueError` → `"import_path or entry_point"` | ✓ |
| `_tool_discovery_specs` | 仅 entry_point | 正确构造 `PackageEntryPointProvider` → `spec.spec_id == "entry-provider"` | ✓ |

所有测试的 `match` 正则均与实际 `raise ValueError(...)` 消息内容匹配。测试覆盖了每个函数的安全敏感 fail-fast 路径。

### 3. Compactor scene AgentPolicy 必填字段测试

- 参数化覆盖 3 个字段：`max_iterations`、`fallback_mode`、`max_consecutive_failed_tool_batches`。
- 每个测试用 `_complete_compactor_agent_policy_override()` 构造完整 override，然后用 `dataclasses.replace(..., field=None)` 置空单个字段。
- `_compactor_scene_inputs` helper 正确构造 `PreparedSceneInputs`，传入被测 override。
- 代码中 8 个字段逐一校验（line 651-677），测试覆盖了 3 个主要字段。满足总控要求的"至少 2-3 个 parameterized 测试"。
- 已有 `test_compactor_prompt_scene_requires_agent_policy` 覆盖 `override is None` 路径。

### 4. runtime ToolsDiscovery `_validate_provider_output` 自包含 provider identity 校验

- **修改前**：`_validate_provider_output` 返回 `None`，调用方 `discover_from_bindings` 在调用前独立调用 `_require_provider_identity`。
- **修改后**：`_validate_provider_output` 内部调用 `_require_provider_identity(output.provider_id)`，返回规范化后的 `provider_id: str`。调用方直接使用返回值做重复检测和 report 构造。
- `_require_provider_identity`（line 596-598）执行 `strip()` + 空值检查，`_validate_provider_output`（line 542）在所有其它校验之前调用它，确保 provider identity 校验是函数自包含的。
- 新增 `test_empty_provider_identity_fails_inside_output_validation` 使用 `provider_id="  "` 的 provider，验证在 output validation 阶段 fail-fast，`match="provider identity"` 匹配 `"provider identity must be non-empty"`。
- 调用方 `discover_from_bindings`（line 235-241）使用返回的 `provider_id` 做重复检测，不再有独立的 `_require_provider_identity` 调用。逻辑等价且更内聚。

### 5. README 同步

- `tests/README.md` 新增 tools discovery 和 host assembly 边界测试覆盖说明，符合 `tests/` 变更触发规则。
- 内容准确描述新增覆盖范围，未越界到其它 README 职责。

## 非阻塞风险

1. **Compactor policy 测试未覆盖全部 8 个必填字段**：`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_prompt`、`continuation_prompt` 未单独测试。当前 3 个参数化用例已满足"至少 2-3 个"要求，且所有字段的校验逻辑同构，追加边际收益低。
2. **`_noop_tool` helper 引入**：为 `ToolDefinition` 构造提供 callable stub，仅用于 `_tooling_options_from_discovery` 测试中构造非空 bundle。不影响生产代码，符合测试隔离原则。
3. **本轮未跑全量 pytest**：仅跑受影响测试文件（36 passed）和 pyright（0 errors, 0 warnings, 0 informations）。未发现回归信号。

## Deferred 项确认

以下各项按总控要求 defer，本轮不视为 blocker：

- `owner_host_instance_id=None` recovery blind spot（F1）
- `_promote_after_release` PromotionResult 语义（F2）
- `_closeout_worker_startup_timeout` 诊断字段（F3）
- `WorkingAssumption` 死字段（F8）
- fact-candidate-only 降级接受（F9）
- compact 预算 ref 计数偏差（F10）
- semantic repair 重试（F11）
- `RAW_ASSISTANT_TURN` 未使用（F12）
- secret redaction 去重（F4/04, F13）
- `ensure_session` 幂等（F14）
- projection checkpoint CAS（F15）
- memory snapshot CAS（F16）
- `_require_non_empty_text` 跨模块重复（03）
- JSON helper 去重（10/12）
- token estimator 去重（11）
- runner_events re-export（09）
- filelock marker warning（13）
- engine_ingest 拆分（14）
- admission durable private import（15）
- schema version message（16）

## 总结

本轮修复正确关闭了总控 accepted scope 中的 4 个 finding，未引入新的 correctness / stability / maintainability blocking regression。生产代码修改范围最小化（仅 `tools_discovery.py` 的 `_validate_provider_output` 函数签名与调用方），测试覆盖充分，设计裁决有直接证据支撑。
