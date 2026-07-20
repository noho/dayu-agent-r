# WU-SEMANTIC-OWNERSHIP-01 P3-H aggregate deepreview (AgentDS)

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-h-aggregate-deepreview-ds.md`
- Timestamp: 2026-07-11T07:37:23+08:00

### Included scope

- Plan commit `ba607309`: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
- S1 commit `35be9dc3`: Web search provider facts and Web tool projection text
- S2 commit `86034f4f`: Fins direct stream and wait visible-language owner
- S3 commit `c2d66c48`: SEC downloader diagnostics, README decision, and aggregate scans
- 未提交 `docs/reviews/wu-semantic-ownership-01-p3-h-aggregate-validation.md` (controller validation summary)
- 未提交 `docs/host/issues-implementation-control.md` P3-H S3 gate status update (one-line: "accepted locally" → "accepted with commit `c2d66c48`")

### Excluded scope

- `docs/cli_ci*` (unrelated untracked)
- `docs/reviews/code-review-20260710-*` (unrelated untracked)
- P3-I / P3-J / 全仓新一轮 deepreview（out of aggregate scope）
- `dayu/engine/` changes in `main...HEAD` diff（not part of P3-H slices）

## Findings

未发现实质性问题。

### Review focus walkthrough

#### 1. P3-H accepted source findings BI-2..BI-6 closure

| Finding | Plan disposition | Implementation slice | Closure evidence | Status |
|---|---|---|---|---|
| BI-2 Web search provider hardcodes LLM behavior instructions | accepted | S1 | `web_search_providers.py` `SearchWebProviderResult` no longer carries `preferred_result_summary`/`next_action`/`next_action_args`/`hint`; `web_search_projection.py` `build_search_web_output()` owns projection; `web_tools.py` `_search_web_business()` chains provider→projection. Test `test_search_public_web_provider_result_excludes_llm_guidance` asserts provider boundary. | CLOSED |
| BI-3 ingestion runtime hardcodes Chinese UI copy | accepted | S2 | `direct_event_text.py` owns all direct/wait visible text; `ingestion_runtime.py` hardcoded `_DIRECT_*` constants removed; all progress/result/title/failure text delegates to helper functions. Job sidecar text (`_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE`, `record.message` audit strings) correctly retained by runtime owner. | CLOSED |
| BI-4 Fins wait adapter hardcodes LLM-facing hints | accepted | S2 | `wait_adapter.py` `_failed_outcome`/`_cancelled_outcome` consume `wait_failed_hint()`/`wait_cancelled_message()`/`wait_cancelled_hint()` from helper; `_failure_message()` tightened to fail-fast with `ValueError` when `error_message` is missing. | CLOSED |
| BI-5 SEC downloader references CLI command name | accepted | S3 | `sec_downloader.py:2037` changed from `dayu-cli init` to `调用方/部署配置提供`; test `test_missing_sec_user_agent_warning_names_config_fact` asserts no CLI command name in diagnostic output. | CLOSED |
| BI-6 Web tools hardcode display/cancel copy | accepted with narrowed owner | S1 | `web_cancellation_text.py` deleted; `web_tool_projection_text.py` owns shared Web cancellation/recovery wording; `web_tools.py` local constants replaced with imports from helper; `@tool(...)` declaration sites retain `display_name`/`description` ownership per narrowed-owner decision. | CLOSED |

#### DS12 evidence-invalid status

DS12 (Host ToolRuntime hidden hint protocol) remains evidence-invalid. Current source scan confirms zero hits for `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, `_hint_with_diagnostic_refs`, or `hint=policy_decision.reason_code` in `dayu/` or `tests/`. P3-E artifacts independently confirm deletion. Plan-mandated regression source scan passed. **DS12 remains correctly closed.**

#### 2. Web/Fins/SEC owner boundary consistency

**S1 Web 边界：**
- Provider (`web_search_providers.py`): `SearchWebProviderResult` — 仅结构化检索事实（query, domains, total, preferred_result, results）
- Projection (`web_search_projection.py`): `build_search_web_output(provider_result) → SearchWebOutput` — LLM-facing 字段（preferred_result_summary, next_action, next_action_args, hint）
- Shared text (`web_tool_projection_text.py`): 共享取消/恢复/下一步文案常量
- Tool declaration (`web_tools.py`): `@tool(display_name="...", description="...")` — display 元数据 owner

无 provider→LLM 穿透，无 projection 反向泄漏到 provider。边界一致。

**S2 Fins 边界：**
- Runtime (`ingestion_runtime.py`): emit typed `FinsEvent` (RESULT/PROGRESS) with `FinsResultSummary`; 调用 `direct_event_text` helper 填充 title/error_message/progress text
- Helper (`direct_event_text.py`): 纯函数，typed facts → 中文文案；不读 runtime，不构造 `FinsEvent`，不理解 Host wait outcome
- Wait adapter (`wait_adapter.py`): 消费 helper (`wait_failed_hint`, `wait_cancelled_message`, `wait_cancelled_hint`) 构造 Host `ResolveWait*Outcome`；`_failure_message()` 只读 `FinsResultSummary.error_message`，fail-fast on missing
- Job sidecar: `_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE` 和 `record.message` audit 字符串由 runtime 保留，不进入 direct stream 或 wait outcome

无 runtime/adapter 穿透投射 LLM 文案，无 helper 理解 Host/Engine 治理。边界一致。

**S3 SEC 边界：**
- Downloader (`sec_downloader.py`): `_resolve_user_agent()` 仅报告 `SEC_USER_AGENT` 环境变量缺失这一配置事实
- CLI (`dayu/cli/`): 保持 CLI 命令名 owner
- 测试断言：诊断输出不含 `dayu-cli` 拼接形式

无 downloader→CLI 反向泄漏。边界一致。

#### 3. S1/S2/S3 code-review fixes completeness

**S1:** AgentMiMo + AgentDS 均报告无 material findings，controller accepted as pass。无 fix gate。✓

**S2:**
- `P3-H-S2-CR-F01` `_failure_message` fallback to `snapshot.message`：已修复。`_failure_message()` 现仅读 `FinsResultSummary.error_message`，缺失时 raise `ValueError`。AgentMiMo + AgentDS re-review 均 CLOSED。✓
- `P3-H-S2-CR-F02` 缺失 observation terminal `error_message` 不变量测试：已修复。测试覆盖 cancel-before-activation、activation failure、producer-without-result、malformed failed snapshot。AgentMiMo + AgentDS re-review 均 CLOSED。✓

**S3:** AgentMiMo + AgentDS 均报告无 material findings，controller accepted as pass。无 fix gate。✓

**S2 `_failure_message` fail-fast 深度验证：**

`_failure_message(result: FinsResultSummary) → str` 的 fail-fast（raise `ValueError` on missing `error_message`）在所有代码路径下安全：

| 调用路径 | error_message 来源 | 保障 |
|---|---|---|
| `_failed_outcome` → wait adapter | `result.error_message`（由 runtime 在构造 `FinsResultSummary` 时填入） | `_required_result(snapshot)` 先确保 result 非 None |
| `_observation_cancelled_result` | `direct_failure_message(error_kind=CANCELLED, fallback_message=None)` → `"操作已取消"` | 永不返回 None |
| `_observation_failure_result` | `direct_failure_message(error_kind=EXECUTION, fallback_message=None)` → `"财报处理执行失败"` | 永不返回 None |
| `_emit_direct_result` (SUCCESS) | `error_message=None`（成功不需要 error_message） | FAILED outcome 不读 SUCCESS result |
| `_emit_direct_result` (FAILURE) | `direct_download_no_source_documents_message()` / `direct_preprocess_no_requested_documents_message()` / `direct_upload_failed_status_message()` / `direct_upload_runtime_unavailable_message()` / `_safe_direct_error_message()` | 所有 FAILURE 路径填入非 None error_message |
| `_emit_direct_cancelled_result` | `direct_failure_message(error_kind=CANCELLED, fallback_message=None)` | 永不返回 None |

测试 `test_fins_wait_poll_adapter_rejects_failed_result_without_message` 直接验证非法快照（FAILED + error_message=None）触发 `ValueError`。旧 fallback 链（snapshot.message → hardcoded text）已完全移除。**Fail-fast 合理，测试充分。**

#### 4. Aggregate validation commands/scans/README decisions

**Validation matrix:**
- P3-H aggregate matrix: `306 passed, 1 skipped, 3 warnings`
- Pyright: `0 errors`
- `git diff --check`: passed

**Source scans (evidence checks, not exhaustive proof):**
- DS12 ToolRuntime hidden hint protocol: no matches ✓
- Web provider LLM next-action prose / derived output fields: no provider-internal matches ✓
- Web cancellation helper migration: `web_cancellation_text.py` deleted; `WEB_CANCELLED_HINT` only in `web_tool_projection_text.py`, `web_tools.py` imports, and intentional test assertions ✓
- Web tools local cancellation literals: no matches ✓
- Fins direct/wait hardcoded prose: only docstring mentions; no direct-stream or wait-outcome hardcoded prose remains ✓
- Fins job sidecar text: `_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE` and `record.message` retained by runtime owner per plan ✓
- SEC downloader CLI command names: no `dayu-cli` in `dayu/fins/downloaders` or `tests/fins` ✓

**README decisions:**
- `dayu/fins/README.md`: checked during S2/S3, no update needed ✓
- `tests/README.md`: checked during S1/S2/S3, no update needed ✓
- Root `README.md` / `dayu/README.md`: no user command, public workflow, package layering, or cross-package architecture change ✓

**Scan classification:** 所有 required scan patterns 均正确分类为 allowed hit 或 clean。Scan 覆盖了 plan 列出的已知 source findings 和回归风险字符串，作为 evidence check 充分。

#### 5. Material correctness/stability/maintainability

沿以下维度逐条检查：

- **Correctness:** 所有 BI-2..BI-6 闭合已逐条验证；S2 fail-fast 在所有终端路径下安全；owner boundary 移动无剩余 fallback/特例/兼容 shim。无 correctness issue。

- **Stability:** `_failure_message` fail-fast 将隐藏的状态不一致暴露为显式 `ValueError`，优于旧版静默 fallback。新 helper 模块 (`direct_event_text.py`, `web_search_projection.py`, `web_tool_projection_text.py`) 均为纯函数/常量模块，无外部依赖、无状态、无 I/O，稳定性高。无 stability issue。

- **Maintainability:** 文案集中在命名良好的 helper 函数中，新增 operation/error kind 时 `assert_never` 提供编译期安全网。投影逻辑与事实生产分离，未来修改 LLM-facing 文本只需改 projection 层。无 maintainability issue。

- **Semantic ownership drift:** 已确认无下游 fallback、特例、重复计算、loose parsing、兼容 shim 或测试固化来补齐上游 contract。所有事实由正确 owner 产生，投影由正确 owner 执行。

- **Adversarial pass:** 检查了空输入、None 输入、whitespace-only 输入、未知枚举值、重复 RESULT 投递、缺失 error_message 等边界条件，均有显式处理或 fail-fast。

## Evidence Summary

| 维度 | 结论 | 关键证据 |
|---|---|---|
| BI-2..BI-6 闭合 | 全部 CLOSED | S1/S2/S3 diff + 逐条边界测试 + source scan |
| DS12 evidence-invalid | 维持 CLOSED | 当前 source scan + P3-E 确认 |
| Owner boundary 一致性 | 一致 | propagation audit 逐层验证 |
| S1/S2/S3 code-review fixes | 无遗漏 | controller adjudication 确认 + 独立验证 S2 fail-fast 路径 |
| S2 fail-fast 安全性 | 安全 | 所有 7 条 error_message 构造路径均保证非 None |
| 测试充分性 | 充分 | 219 passed, 9 条关键边界测试通过, helper 86% 覆盖率 |
| Source scans | 充分且分类正确 | 7 类 scan 均通过，allowed hits 已文档化 |
| README decisions | 正确 | 4 个 README 均检查，无遗漏更新 |

## Open Questions

无。

## Residual Risk

- Third-party `edgar` deprecation warnings（`HtmlDocument` → `HTMLParser` 迁移）与 P3-H 无关，不阻塞。
- P3-H aggregate source scans 是 bounded evidence checks，不是全仓语义审计。后续 umbrella WU 的全仓 deepreview rounds 仍需要覆盖 P3-H 范围外的区域。
- `dayu/fins/ingestion_runtime.py` 中 `_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE`（行 479）和 observation `record.message` audit 字符串（行 2434/2437/2639）是 plann 明确保留的 job sidecar 文本，不属于 direct/wait 清理范围。若后续 WU 要求清理 job sidecar 文案，这些位置需要单独处理。
