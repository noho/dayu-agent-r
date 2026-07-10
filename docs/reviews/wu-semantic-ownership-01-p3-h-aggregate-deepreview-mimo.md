# WU-SEMANTIC-OWNERSHIP-01 P3-H Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-h-aggregate-deepreview-mimo.md`
- Included scope:
  - Plan commit `ba607309`: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
  - S1 commit `35be9dc3`: Web provider facts / web projection boundary
  - S2 commit `86034f4f`: Fins direct/wait visible text helper boundary
  - S3 commit `c2d66c48`: SEC downloader diagnostic boundary
  - Uncommitted: `docs/reviews/wu-semantic-ownership-01-p3-h-aggregate-validation.md`
  - Uncommitted: `docs/host/issues-implementation-control.md` P3-H status update
- Excluded scope: `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`, P3-I/P3-J or full-repository deepreview
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Evidence Summary

### 1. P3-H accepted source findings BI-2..BI-6 闭合状态

| Finding | Disposition | Evidence |
|---|---|---|
| BI-2 Web search provider hardcodes LLM behavior instructions | closed | `web_search_providers.py` 现在只返回 `SearchWebProviderResult`（含 `query`, `domains`, `total`, `preferred_result`, `results`）；`hint`/`next_action`/`next_action_args`/`preferred_result_summary` 已移至 `web_search_projection.py`。源码扫描确认 provider 内部无 LLM prose。 |
| BI-3 ingestion runtime hardcodes Chinese UI copy | closed | `ingestion_runtime.py` 的 direct progress/result 路径已改为调用 `direct_event_text` helper。删除了 `_DIRECT_CANCELLED_MESSAGE`/`_DIRECT_FAILURE_TITLE`/`_DIRECT_SUCCESS_TITLE`/`_DIRECT_ERROR_TEXT_FALLBACK` 常量。Job sidecar text 仍保留在 runtime 中（按 plan 分类为 out-of-scope）。 |
| BI-4 Fins wait adapter hardcodes LLM-facing hints | closed | `wait_adapter.py` 的 `_failed_outcome` 和 `_cancelled_outcome` 现在消费 `wait_failed_hint()`/`wait_cancelled_message()`/`wait_cancelled_hint()`。`_failure_message` 简化为只读取 `result.error_message`，移除了 snapshot message 回退路径。 |
| BI-5 SEC downloader references CLI command name | closed | `sec_downloader.py:2037` 的 warning 已从 `dayu-cli init` 改为 `调用方/部署配置提供`。源码扫描确认 `dayu/fins/downloaders` 和 `tests/fins` 中无 `dayu-cli` 残留。 |
| BI-6 Web tools hardcode display/cancel copy | closed | `web_cancellation_text.py` 已删除（无兼容 re-export）。`WEB_CANCELLED_HINT` 等常量已移至 `web_tool_projection_text.py`。`web_tools.py` 从新 helper 导入。`display_name`/`description` 保留在 `@tool(...)` declaration 边界。 |

### 2. DS12 evidence-invalid 状态

DS12（ToolRuntime hidden hint protocol）在 P3-H 范围内仍为 evidence-invalid。源码扫描 `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_hint_with_diagnostic_refs|hint=policy_decision.reason_code` 在 `dayu` 和 `tests` 中零命中。P3-E 已确认该协议已删除。

### 3. Owner boundary 一致性

- **Web**: provider 产结构化事实 → `web_search_projection.py` 产 LLM-facing 输出 → `web_tools.py` 消费投影结果。
- **Fins direct**: runtime 产 typed operation/status/count/payload 事实 → `direct_event_text.py` 产可见文案 → Service/CLI 消费 `FinsEvent` 文本。
- **Fins wait**: observation snapshot 产 status/result/error 事实 → wait adapter 消费 helper 产 LLM-facing hint/message → Host wait outcome。
- **SEC**: downloader 产 `SEC_USER_AGENT` 配置事实 → warning 不含 CLI 命令名。

三条路径的 owner boundary 一致：provider/runtime/downloader 只产事实，projection/CLI/docs owner 产 LLM/user-facing 文本。

### 4. S1/S2/S3 code-review fixes 完整性

- **S1**: `SearchWebProviderResult` 替代旧 `SearchWebOutput`（provider 内部类型），`SearchWebOutput` 移至 `web_search_projection.py`。`web_cancellation_text.py` 删除。所有导入直接更新，无兼容别名。测试新增 `test_search_public_web_provider_result_excludes_llm_guidance` 和 `test_web_tool_display_and_description_stay_at_declaration_boundary`。
- **S2**: `_emit_direct_result` 签名移除 `title` 参数，改由 helper 在方法内部生成。`_failure_message` 简化为 fail-fast（`ValueError` on missing `error_message`）。测试新增 `test_fins_wait_poll_adapter_rejects_failed_result_without_message` 和 `test_observed_producer_without_result_uses_helper_failure_message`。
- **S3**: 单行变更，SEC downloader warning 移除 `dayu-cli init` 引用。测试新增 `test_missing_sec_user_agent_warning_names_config_fact`。

### 5. S2 `_failure_message` fail-fast 合理性

`wait_adapter.py:_failure_message` 对缺少 `error_message` 的 failed result 直接抛出 `ValueError`。这是合理的设计选择：

- 运行时所有 failure 路径都通过 `_safe_direct_error_message` 或 `direct_failure_message` 保证 `error_message` 非空。
- `_observation_failure_result` 和 `_observation_cancelled_result` 始终产 `error_message`。
- fail-fast 捕捉 runtime bug 而非静默降级到 implementation-specific message（如旧版的 `"Fins operation failed."`）。
- 测试 `test_fins_wait_poll_adapter_rejects_failed_result_without_message` 显式覆盖此路径。

### 6. Aggregate validation 充分性

- 测试矩阵: 227 passed, 1 skipped, 3 warnings（当前 workspace 运行确认）。
- Pyright: 0 errors, 0 warnings（当前 workspace 运行确认）。
- 源码扫描: DS12、Web provider prose、Web cancellation 模块、Fins direct/wait 硬编码文案、SEC downloader CLI 命令名 — 全部通过。
- README 决策: `dayu/fins/README.md`、`tests/README.md`、根 `README.md`、`dayu/README.md` 均无需更新。决策记录在 aggregate validation 中。

## Open Questions

无。

## Residual Risk

- 第三方 `edgar` deprecation warnings 与 P3-H 无关，不影响结论。
- Aggregate scans 是有界证据检查，不替代后续全仓 deepreview。
- Job sidecar text（`_append_job_event_warn(...)` 中的中文文案）仍保留在 runtime 中，按 plan 分类为 durable job event/audit owner 的职责，不在 direct/wait projection scope 内。aggregate validation 已正确记录此分类。
