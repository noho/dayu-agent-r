# WU-TOOLS-01-F02 PR Review — AgentMiMo

## 元数据

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Review type: PR review (draft-PR-pass gate)
- Reviewer: AgentMiMo
- Date: 2026-06-09
- PR: [#132](https://github.com/noho/dayu-agent-r/pull/132)
- Branch: `phase/wu-tools-01-f02` -> `main`
- Head SHA: `d75fcf7b8a105b7d3c8b59e99510401c79a3b913`
- Base SHA: `c8a934c271540e042efda2bb6dec044a653aac0c`
- Plan artifact: `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Readiness artifact: `docs/reviews/wu-tools-01-f02-draft-pr-readiness-controller.md`
- Aggregate deepreview: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-mimo.md`
- Aggregate re-review: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-rereview-mimo.md`

## Verdict

**pass**

PR 132 正确实现了 WU-TOOLS-01-F02 目标，无阻断问题，无 late drift，无 non-goal 违规。

## 验证结果

| 验证项 | 结果 |
|--------|------|
| `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q` | 27 passed in 0.34s |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | 通过 |
| `git diff --check` | 通过（仅 review 文档有 EOF 空行，非代码文件） |
| forbidden import 扫描 | 无匹配 |
| wide-type (`Any`/`object`) 扫描 | 无匹配 |

## Late Drift 检查

Aggregate deepreview commit (`0f843b34`) 之后仅新增 2 个 commit：

| Commit | 内容 | 代码变更 |
|--------|------|----------|
| `05f1229e` | readiness controller artifact | 无代码变更 |
| `d75fcf7b` | draft PR record | 无代码变更 |

`utils/diagnose_web_access.py` 和 `tests/tools/web/test_diagnose_web_access.py` 在 aggregate deepreview 后**零变更**。`docs/host/issues-implementation-control.md` 的变更为 controller-owned 状态推进（gate: `ready-to-open-draft-PR` -> `PR review`），符合预期。

**结论**: 无 late drift。

## PR Body 与实际变更一致性

| PR Body 声明 | 验证 |
|-------------|------|
| migrate opt-in Web diagnostics scripts and URL corpus into utils | ✅ `utils/diag_web.sh`, `utils/diag_web_batch.sh`, `utils/web_ci_urls.jsonl`, `utils/diagnose_web_access.py` 已创建 |
| add current-contract diagnose_web_access.py using current Web ToolsDiscovery / ToolDefinition callable boundary | ✅ 通过 `discover_tools(spec)` + `ToolDefinition.callable` 调用 |
| add deterministic Web diagnostics tests | ✅ `tests/tools/web/test_diagnose_web_access.py` (27 tests) |
| No default live CI workflow or Web smoke gate is added | ✅ 无 CI workflow 变更 |
| WU-TOOLS-01-S5-R2 remains owned by WU-TOOLS-01-F03 | ✅ 无 S5-R2 关闭操作 |
| Host, Engine, ToolRuntime, durable schema, EventLog, and production Web tool behavior are unchanged | ✅ 未修改 `dayu/host/`、`dayu/engine/`、`dayu/tools/web/` production code |

## Non-Goal 合规检查

| Non-Goal | 状态 | 证据 |
|----------|------|------|
| 不定义 Web smoke pass/fail/skip gate | ✅ | 无 gate 逻辑 |
| 不关闭 `WU-TOOLS-01-S5-R2` | ✅ | 无相关操作 |
| 不把 live diagnostics 放入默认 CI | ✅ | 无 CI workflow 修改 |
| 不恢复 OLD `ToolRegistry`/truncation/fetch_more/`dayu.web`/UI | ✅ | AST guard 测试确认无 forbidden imports |
| 不重写 production Web tools | ✅ | 未修改 `dayu/tools/web/` production code |
| 不修改 Host/Engine/ToolRuntime contract | ✅ | 未修改 `dayu/host/`、`dayu/engine/` |
| 不把单站点失败判定为 regression | ✅ | 只输出证据和分类 |

## Correctness 深度审查

### CLI Mode Validation (`_validate_cli_mode`, line 776-794)

- `--url` 与 `--url-file` 互斥校验在 `main()` 分流前执行。
- 同时提供时 raise `ValueError`，同时缺失时 raise `ValueError`。
- `main()` catch `Exception` 输出到 stderr 并返回退出码 2。
- `test_cli_requires_exactly_one_url_mode` 覆盖两种错误路径。
- **结论**: 正确。

### URL Safety / Redaction

- `_normalize_url_for_http` (line 882-903): 补全 scheme、拒绝空值/非 HTTP/缺失 host。
- `_is_private_or_local_host` (line 906-935): 覆盖 localhost、.localhost、.local、0.0.0.0、IPv4 私有/环回/链路本地/保留/多播/未指定、IPv6 环回/链路本地。
- `_validate_url_safety` (line 938-958): 组合规范化与私有网络检测。
- `_redact_headers` (line 986-1008): 对 5 个敏感关键词片段（authorization、cookie、token、secret、key）做 header 值替换。
- 测试覆盖: `test_url_normalization_requires_http_url`、`test_url_safety_rejects_private_and_local_hosts_by_default`（含 IPv4-mapped IPv6）、`test_header_redaction_masks_sensitive_header_values`。
- **结论**: 正确。IPv6 scope ID（如 `fe80::1%eth0`）未被 `_is_private_or_local_host` 覆盖，但该场景在诊断中极罕见，风险低。

### Comparison Bucket Classifier (`_classify_diagnostic_bucket`, line 1811-1870)

决策树按计划规则优先级实现：

1. `child_process_error` — 子进程崩溃不混入访问路径分桶 ✅
2. `all_success` — 三条路径均采样且均成功 ✅
3. `playwright_challenge_detected` — Playwright 采样且 challenge 检测 ✅
4. `fetch_only_success` — fetch 成功、requests 失败、Playwright 采样失败 ✅
5. `fetch_outperforms_requests` — fetch 成功、requests 失败、Playwright 未采样或失败 ✅
6. `requests_only_sampled` — requests 成功、fetch/Playwright 未采样 ✅
7. `requests_only_success` — requests 成功、fetch 失败、Playwright 未采样或失败 ✅
8. `browser_only_success` — Playwright 成功、fetch/requests 失败 ✅
9. `requests_and_fetch_success_playwright_failed` — requests+fetch 成功、Playwright 采样失败 ✅
10. `fetch_only_failure` — fetch 失败、至少一个其他路径成功 ✅
11. `all_failed` — 所有采样路径均失败 ✅
12. `partial_sample` — 其他非空采样组合 ✅
13. `mixed` — 无法归类 ✅

边界验证:
- `all_success` 优先于 `playwright_challenge_detected`（三路径成功 + challenge = `all_success`）— 符合计划规则 5 例外 ✅
- 零采样 (`sampled_path_count=0`) 返回 `mixed` 而非 `all_failed` — 正确 ✅
- 两路径成功 + Playwright 未采样返回 `partial_sample` — 符合计划 ✅

### Fetch Adapter (`_build_tool_fetch_profile`, line 1253-1339)

覆盖所有 current outcome 类型:

| Outcome | Profile | 正确性 |
|---------|---------|--------|
| `ToolCompletedOutcome` | `ok=True`, 提取 title/final_url/fetch_backend/content | ✅ |
| `ToolFailedOutcome` | `ok=False`, 保留 error_code/message/hint/next_action/diagnostics | ✅ |
| `ToolCancelledOutcome` | `ok=False`, 保留 reason/message/hint | ✅ |
| `ToolAwaitingOutcome` | `ok=False`, 标记 `unexpected_awaiting_outcome` | ✅ |
| Unknown outcome | `ok=False`, `unknown_outcome` | ✅ |
| Callable exception | `ok=False`, `callable_exception` | ✅ |

`_DiagnosticCancellationToken` (line 156-212) 实现 never-cancelled semantics，不连接 Host 取消状态。

### Batch Child Process Handling

- `_build_batch_child_command` (line 2122-2181): 完整传递所有 CLI 选项到子进程。
- 子进程返回码非零时构造 `_child_error_payload`，标记 `child_process_error`，不混入 comparison bucket。
- 子进程返回码为零但 JSON 解析失败时同样构造 `child_process_error` payload。
- `interactive_mode` 控制 `capture_output`：headed/pause/manual-wait 时不捕获输出。
- **结论**: 正确、健壮。

### Playwright Profile (`_build_playwright_profile`, line 1578-1730)

- Playwright 包缺失时返回 `playwright_package_missing` profile（`sampled=True`, `ok=False`）。
- Protocol 类型定义（`_PlaywrightProtocol`、`_BrowserProtocol` 等）避免了 `getattr` 和宽类型。
- `sync_playwright()` 返回值通过 `cast` 到 `_PlaywrightContextManagerProtocol`，理由充分。
- `storage_state` 只记录路径，不内联内容。
- network events 有上限 (`max_network`)。
- 异常时仍返回完整 profile（含已收集的 network events）。
- 清理通过 `_safe_close_context` / `_safe_close_browser` 忽略异常。
- **结论**: 正确。

### Diagnostic JSON Schema 与 LLM-facing 文本

- `schema_version` 固定为 `web-diagnostics-v1`。
- 所有 profile 字段使用业务可读名称（`sampled`、`ok`、`status`、`error`、`message`）。
- `_tool_failed_outcome_diagnostics` 显式说明 `ToolFailedOutcome` 的字段边界。
- `header_source_note` 明确 raw requests 是对照路径，不是 production fetch。
- `storage_state_note` 显式说明不内联敏感内容。
- 无裸 `event_id`、`payload_ref`、digest、cursor 或 tool call id 暴露。
- **结论**: 符合 LLM-facing 语义约束。

### Control / Readiness Artifacts

- `docs/host/issues-implementation-control.md` 状态推进正确（gate: `PR review`，active work unit: `WU-TOOLS-01-F02`）。
- `docs/reviews/wu-tools-01-f02-draft-pr-readiness-controller.md` 准确记录已接受的 commits 和验证结果。
- Controller-owned 文档未被 implementation 意外修改。
- **结论**: 正确。

## Findings

无 blocking findings。

### F-01 [INFO] `git diff --check` 在 review 文档中有 EOF 空行警告

**文件**: 6 个 controller adjudication 文档

**证据**: `git diff --check` 报告以下 review 文档有 new blank line at EOF:
- `wu-tools-01-f02-plan-rereview-controller-adjudication.md`
- `wu-tools-01-f02-plan-review-controller-adjudication.md`
- `wu-tools-01-f02-slice1-code-review-controller-adjudication.md`
- `wu-tools-01-f02-slice1-rereview-controller-adjudication.md`
- `wu-tools-01-f02-slice2-code-review-controller-adjudication.md`
- `wu-tools-01-f02-slice2-rereview-controller-adjudication.md`

**评估**: 纯文档格式问题，不影响代码功能。review artifacts 由 controller 流程生成，非 implementation 代码。不阻断。

### F-02 [INFO] `_is_private_or_local_host` 未覆盖 IPv6 scope ID

**文件**: `utils/diagnose_web_access.py:924-927`

**证据**: `ipaddress.ip_address("fe80::1%eth0")` 会 raise `ValueError`，被 `_is_private_or_local_host` catch 后返回 `False`。这意味着带 scope ID 的链路本地 IPv6 地址不会被默认安全策略阻止。

**评估**: IPv6 scope ID 在 Web 诊断场景中极罕见（浏览器通常不使用 scope ID），且诊断脚本是 opt-in developer utility。风险极低，已在 aggregate deepreview 中记录为已知限制。不阻断。

## 残余风险

| 风险 | 严重性 | Owner | 目标 |
|------|--------|-------|------|
| live network / 真实 Playwright / storage-state 环境差异不在默认 CI 覆盖内 | 低 | WU-TOOLS-01-F03 | 通过 explicit opt-in 和 evidence-only 输出降低 |
| F03 消费 diagnostic JSON 字段需显式声明 | 中 | WU-TOOLS-01-F03 | F02 保证 utility schema 子集稳定 |
| 批量诊断串行执行 | 低 | F03 or later | 仅在实际成为瓶颈时优化 |
| `_is_private_or_local_host` 未覆盖 IPv6 scope ID | 极低 | 维护者 | 诊断场景极罕见 |

## 建议

**下一 gate**: PR review 通过。建议用户做出 merge decision。

**后续改进项**（不阻断）:
1. 为 `_is_private_or_local_host`、`_redact_headers`、`_validate_url_safety` 补充直接单元测试（已在 aggregate deepreview 中记录）。
2. F03 plan 中声明消费的 diagnostic JSON 字段子集，避免 schema drift。
