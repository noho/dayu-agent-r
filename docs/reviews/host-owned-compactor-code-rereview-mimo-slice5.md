# Code Review

## Scope

- Mode: current changes (narrow re-review)
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: uncommitted diff (`git diff`)
- Timestamp: 20260519-113434
- Output file: `docs/reviews/host-owned-compactor-code-rereview-mimo-slice5.md`
- Included scope:
  - `dayu/host/llm_compaction.py` — 脱敏诊断 + non-final outcome handling
  - `tests/host/test_llm_compaction.py` — 脱敏测试 + 非 final outcome 断言更新
  - `tests/host/test_public_compact_smoke.py` — 真实 compactor smoke + artifact 断言
  - `utils/smoke_host_public_multiturn.py` — manual smoke 多轮闭环
  - `docs/reviews/host-owned-compactor-code-fix-codex-slice5.md` — fix artifact
- Excluded scope: 未触及的 Host / Engine / Service 文件
- Design truth source: `docs/host/design.md`
- Parallel review coverage: 无

## Gate 1: Service-facing public contract 是否仍只暴露 CompactorRunnerBaseline，未恢复 ContextCompactor 注入

**结论：通过。**

证据：

1. `tests/host/test_public_compact_smoke.py:15` — import `CompactorRunnerBaseline`，无 `ContextCompactor` import。整个 diff 中无 `ContextCompactor` 出现。
2. `tests/host/test_public_compact_smoke.py:100-105` — `open_host` 通过 `compactor_runner_baseline=CompactorRunnerBaseline(...)` 传入 runner spec/options，不传 `ContextCompactor` 实例。
3. `utils/smoke_host_public_multiturn.py:348-353` — manual smoke 同样使用 `CompactorRunnerBaseline`，无 `ContextCompactor` 注入。
4. `dayu/host/__init__.py:58,154` — package export 只有 `CompactorRunnerBaseline`，无 `ContextCompactor`。
5. `tests/host/test_package_exports.py:191` — 显式断言 `"CompactorExecutionBaseline" not in package_symbols`。
6. `dayu/host/api.py:1022` — `OpenHostOptions`（Service-facing contract）使用 `compactor_runner_baseline: CompactorRunnerBaseline | None`。
7. `dayu/host/api.py:746` 的 `context_compactor` 字段属于内部 `HostLocalExecutionOptions`，不在 `__init__.py` export 中，不构成 Service-facing contract。

## Gate 2: LLMContextCompactor 对 EngineRunOutcomeFailed/Cancelled/Suspended 的处理是否脱敏、类型正确、无泄漏

**结论：通过。**

证据：

1. `dayu/host/llm_compaction.py:252-271` — `_non_final_outcome_message` 对三种非 final outcome 分别处理：
   - `EngineRunOutcomeFailed`：提取 `error_code`、`recoverable`、`message`，`message` 经 `_safe_outcome_text` 脱敏。
   - `EngineRunOutcomeCancelled`：固定文案 `"compactor runner was cancelled"`，无 provider 数据。
   - `EngineRunOutcomeSuspended`：提取 `reason`，经 `_safe_outcome_text` 脱敏。
   - fallback：固定文案。

2. `dayu/host/llm_compaction.py:274-290` — `_safe_outcome_text` 脱敏逻辑：
   - `_BEARER_SECRET_PATTERN` 匹配 `Bearer <token>` 并替换为 `Bearer <redacted>`。
   - `_ASSIGNMENT_SECRET_PATTERN` 匹配 `api_key=<value>` / `authorization=<value>` 并替换 value 为 `<redacted>`。
   - 截断到 240 字符，防止 provider payload 泄漏到异常消息。

3. `tests/host/test_llm_compaction.py:117-158` — `test_llm_context_compactor_sanitizes_failed_runner_outcome` 覆盖：
   - 输入包含 `Authorization: Bearer deepsecret` 和 `api_key=plainsecret`。
   - 断言 `error_code=server_error`、`recoverable=True`、`503`、`transient unavailable` 保留。
   - 断言 `deepsecret`、`plainsecret`、`provider-request-1` 不出现在异常消息中。

4. `dayu/host/llm_compaction.py:181-182` — `compact()` 中 `LLMCompactionProposalError(_non_final_outcome_message(outcome))` 确保所有非 final outcome 走脱敏路径。

5. `EngineRunOutcomeFailed` 的 `provider_request_id` 不被 `_non_final_outcome_message` 使用，不出现在异常消息中。

## Gate 3: compactor max_retries=1 与 max_compaction_attempts_per_operation=2 是否符合 Engine 低层 retry + Host semantic retry 设计

**结论：通过。**

设计真源 (`docs/host/design.md`) 分层：

- 第 2597 行：Runner/provider 层负责低层 transport retry（network、timeout、HTTP 429、HTTP 5xx），由 Engine Runner 按 `RunnerSpec.max_retries` 处理。
- 第 2581 行：`max_compaction_attempts_per_operation` 控制 Host governance 的 proposal attempt / semantic repair 预算，不控制 Engine provider retry。
- 第 2599 行：compaction operation 内 `max_compaction_attempts_per_operation` 控制 proposal + repair attempts 总预算。
- 第 2601 行：budget 耗尽后只允许写 `CONTEXT_COMPACTION_FAILED`，不能无限 retry。

diff 中的设置：

| 参数 | 值 | 职责层 | 语义 |
|------|-----|--------|------|
| `RunnerSpec.max_retries` | 1 | Engine transport | 单次 proposal 调用内 1 次 transport retry |
| `max_compaction_attempts_per_operation` | 2 | Host governance | operation 内最多 2 次 proposal attempt（含首次） |

证据：

1. `tests/host/test_public_compact_smoke.py:35-36,59-62,95-98` — smoke 设置 `max_retries=1` 和 `max_compaction_attempts_per_operation=2`。
2. `utils/smoke_host_public_multiturn.py:80-81,293-296,340-345` — manual smoke 同样设置。
3. `tests/host/test_llm_compaction.py:188-211` — `test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair` 验证 `max_retries` 透传到 Engine request，compactor 内部不做 semantic repair loop。
4. `dayu/host/llm_compaction.py:145-164` — `LLMContextCompactor.__init__` 接收 `runner_spec`，`runner_spec.max_retries` 由调用方控制。

两层 retry 正交：Engine 层处理 transient transport 故障；Host 层处理 proposal 级别的 non-final outcome / empty summary。设计意图成立。

## Gate 4: smoke test/manual smoke 是否仍覆盖 public opener -> Host-owned compactor -> artifact -> 多轮闭环

**结论：通过。**

`tests/host/test_public_compact_smoke.py` 覆盖链路：

1. `open_host(options)` — public opener，options 包含 `CompactorRunnerBaseline`。
2. `host.ensure_session(...)` — 创建 session。
3. `host.submit_followup(...)` — 第一轮，输入 `"x" * 220` 触发 proactive compaction。
4. `next_terminal_for_run(...)` — 等待第一轮 terminal，断言 `SUCCEEDED`。
5. `host.submit_followup(...)` — 第二轮 followup。
6. `next_terminal_for_run(...)` — 等待第二轮 terminal，断言 `SUCCEEDED`。
7. artifact 断言：
   - `_compact_artifact_files` 对比前后文件数，确认有新 artifact。
   - `_compact_artifact_for_run` 按 `candidate_id=llm-compact:{run_id}` 定位 artifact。
   - 校验 `artifact_kind=context_compaction`、`input_snapshot_refs.current_user_input_ref` 非空。
8. session_id / run_id 一致性断言：`first_terminal.session_id == session.session_id`、`first_terminal.run_id == compacted.accepted_run_id`。

`utils/smoke_host_public_multiturn.py` 覆盖链路：

1. `open_host(options)` — public opener，options 包含 `CompactorRunnerBaseline`。
2. Round 1：工具调用，记录 smoke fact。
3. Round 2：长 prompt 触发 compaction，打印 compact artifact 摘要。
4. Round 3：验证 compact 后连续性（marker 可见性）。
5. `_print_compact_summary` 输出 artifact 文件数和路径，不输出 API key / prompt / provider payload。

两条路径均验证：public opener → Host 内部构造 `LLMContextCompactor` → Engine public runner → candidate → artifact → 多轮连续性。

## Gate 5: 是否有 blocker

**结论：无 blocker。**

- pyright：`0 errors, 0 warnings, 0 informations`（已验证）。
- 单元测试：`6 passed`（已验证）。
- 无 `ContextCompactor` 注入恢复。
- 无敏感信息泄漏。
- retry 分层符合设计。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 真实 provider 连续两次返回非 final / provider failure 时，smoke 会失败。这是预期行为：生产 Host-owned compactor 链路确实没有 accepted compact output 时，失败是正确语义。
- `_safe_outcome_text` 的 regex 覆盖 `Bearer <token>` 和 `api_key=value` / `authorization=value` 格式。若 provider 错误消息使用非标准 secret 格式（如自定义 header 名），可能不会被脱敏。当前 DeepSeek / OpenAI 兼容 API 的错误格式已被覆盖。
- `HostLocalExecutionOptions`（内部数据类，非 export）仍保留 `context_compactor` 字段。该字段不在 Service-facing contract 中，不影响本次 gate 判定；后续清理属于独立任务。
