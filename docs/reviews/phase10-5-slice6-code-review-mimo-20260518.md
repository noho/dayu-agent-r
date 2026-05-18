# P10.5 Slice 6 Code Review — AgentMiMo

## Gate

当前 gate：P10.5 Slice 6 code review。
Review 依据：design doc（`docs/host/design.md`）、plan（`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`）、implementation artifact（`docs/reviews/phase10-5-slice6-implementation-codex-20260518.md`）、workspace uncommitted diff。

## 结论

**PASS**，0 blocking / 0 high / 2 medium / 3 low findings。

## Review Scope

本轮 diff 涵盖 18 文件、+969 / -124 行。修改范围：
- 新增 `tests/host/public_smoke_support.py`：Slice 6 public smoke 测试支撑。
- 新增 5 个 smoke 测试文件：multi-turn、tool wiring、real runner matrix、real compactor、public cancel smoke。
- 扩展 3 个 Slice 5 follow-up 测试：steer、retry/replay、cancel。
- 迁移 9 个旧 Host 测试到 P10.5 pre-start governance contract。
- 窄生产修复 `dayu/host/engine_ingest.py`：empty final answer → FAILED。
- 更新 `dayu/host/README.md`、`tests/README.md`、`docs/host/implementation-control.md`。

## 逐项审查

### 1. Slice 6 Success Signal 满足情况

| Signal | 状态 | 证据 |
|---|---|---|
| S1 real-runner no-tool two-turn | ✓ | `test_real_runner_no_tool_two_turn_public_path`：open_host → submit_followup × 2 → watch terminal → assert SUCCEEDED + content 非空。 |
| S1 multi-client watch / queue idempotency | ✓ | `test_two_watchers_observe_same_terminal_event`、`test_concurrent_queue_uses_client_request_id_idempotency`。 |
| S1 per-run execution override | ✓ | `test_submit_followup_field_level_execution_override_freezes_effective_config`：只传 runner_options 时 spec 来自 baseline，只传 runner_spec 时 options 来自 baseline。 |
| S2 mock-tool wiring | ✓ | `test_mock_tool_fact_enters_memory_and_next_run_input`、`test_tool_names_subset_and_empty_freeze`。mock tool 只机械返回，不计入 real-runner signal。 |
| S3 real-runner matrix | ✓ (1 skip) | mimo、deepseek、qwen 通过；gemini 因 HTTP 429 / RESOURCE_EXHAUSTED / QuotaFailure / RetryInfo 精确 skip。 |
| S4 real compactor | ✓ | `test_real_compactor_public_opener_compacts_and_preserves_continuity`：显式 `_RealLLMContextCompactor` 调用真实 Engine runner，不使用 `FakeContextCompactor`。assert `compactor.call_count >= 1`。 |
| S5 cancel / close boundary | ✓ | `test_pre_dispatch_cancel_visible_in_watch`、`test_active_cancel_emits_public_cancel_event`、`test_cancel_session_runs_scoped_to_session`。 |

全部 success signal 均通过 public path（open_host / submit_followup / watch_session_events / get_run）断言，不读取 internal durable truth 作为 correctness assertion。mock runner / FakeContextCompactor 未计入 real-runner / real-compactor success signal。

**判定：满足 Slice 6 success signal。**

### 2. Provider Skip 精确性

`public_smoke_support.py` 定义三组 skip marker：

- `_NETWORK_FAILURE_MARKERS`：clientconnectorerror、timeout、connection refused 等网络层 marker。
- `_TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS`：503、unavailable、server overloaded、model is overloaded、try again later 等。
- `_TEMPORARY_PROVIDER_RATE_LIMIT_MARKERS`：429、rate_limit_exceeded、RetryDelay 等。

`skip_if_provider_terminal_failed` 只在 terminal FAILED 时检查 marker；SUCCEEDED 事件不触发 skip。API key 认证失败（401/403）产生的错误消息不包含上述 marker，会 hard fail。schema / contract failure 也不匹配。

Gemini skip 精确记录了 `provider=gemini`、endpoint、`provider_quota_or_rate_limit=resource_exhausted` 与原始 message。

**判定：skip 规则满足要求。**

### 3. Empty Final Answer → FAILED 生产修复

`engine_ingest.py:2837`：`data.content.strip() == ""` 时返回 `_failed_plan(reason="empty_final_answer", recoverable=False)`，不写入 `RUN_SUCCEEDED`。

设计依据：design.md §11 要求 terminal SUCCEEDED 的 HostEvent 必须 inline final answer view（content / filtered / degraded / finish_reason）。Engine 产出空 content 的 final_answer 时，content 无法展示，写入 SUCCEEDED 会导致 public watch 读取时 `HostDurableError` 崩溃。修复把这类事件归类为 FAILED，使 public watch 返回 typed failed terminal event。

修复位置正确：`_final_answer_plan` 是 EngineEvent → TerminalPlan 的唯一映射入口，在 terminal plan 边界拒绝空白 content 成功收口。`_failed_plan` 参数签名匹配，`recoverable=False` 符合"空 final answer 不可恢复"语义。

回归测试覆盖：
- `test_engine_ingest_mapping.py::test_empty_final_answer_closes_failed_without_run_succeeded`：验证 ATTEMPT_FAILED + RUN_FAILED、无 RUN_SUCCEEDED、error_code="empty_final_answer"。
- `test_watch_session_events.py::test_empty_final_answer_terminal_projects_as_failed_event`：验证 public watch 投影为 FAILED kind、final_answer is None、error_message 包含 "no displayable content"。

**判定：root cause fix，符合 Host public terminal final answer typed contract 与 Run/Attempt/EventLog 状态机。**

### 4. Real Compactor Smoke 真实性

`test_public_compact_smoke.py` 中 `_RealLLMContextCompactor`：
- 显式实现 `ContextCompactor` 协议。
- `compact()` 调用 `_run_llm_summary()` → `asyncio.run(run_agent_and_wait(...))`，使用真实 Engine runner 和 compactor 独立 RunnerSpec。
- 不读取 expected answer、run id、轮次或测试私有答案。
- `compactor_runner_spec` 来自 `PROVIDER_CASES[1]`（deepseek）真实 API key。

普通 Run 使用 `FinalAnswerWorkerFactory`（deterministic worker），但 compact smoke 的验证重点是 compaction 触发 → canonical compact events → memory projection → subsequent Run continuity，不依赖普通 Run 的 LLM 执行。real runner matrix 测试已覆盖 LLM 执行路径。

**判定：real compactor smoke 使用显式真实 LLM compactor adapter，不削弱 S4 success signal。**

### 5. 旧测试迁移

迁移的旧测试遵循 P10.5 accepted pre-start governance contract：

- `start_run` 返回 `ACCEPTED`（非 `RUNNING`），`current_attempt_id is None`。测试断言已同步。
- 需要 active Run 的测试通过 `_start_governed_refs` / `_start_governed_run` 显式执行 pre-start governance → `RUNNING` + Attempt。
- `submit_followup(queue)` 在低层 command handle 无 opener baseline 时 fail closed（`INVALID_STATE`），旧测试 `test_submit_followup_queue_active_and_no_active` 替换为 `test_submit_followup_queue_requires_opener_baseline`。
- `submit_followup(steer)` 对未启动 target 返回 `INVALID_STATE`（非 `UNSUPPORTED_OPERATION`）。
- `retry_run` / `replay_run` 对非目标源状态返回 `INVALID_STATE`（非 `UNSUPPORTED_OPERATION`），`purge_session` 仍为 `UNSUPPORTED_OPERATION`。
- `attach_active` 对 ACCEPTED（未启动）Run 返回 `CONFLICT`。
- 多进程 admission 断言：`accepted_runs == 1`、`attempt_count == 0`（governance 前状态）。
- `cancel_session_runs` unsupported non-terminal 从 `WAITING` 改为 `RECOVERING`，因为 `WAITING` 现在是 cancelable 的。

所有迁移都是把旧低层断言对齐到 P10.5 已 accepted 的 public contract，未在生产代码中添加兼容逻辑。

**判定：迁移正确，未掩盖行为回归。**

### 6. Slice 5 Follow-up 覆盖

| Follow-up | 状态 | 证据 |
|---|---|---|
| WAITING steer | ✓ | `test_steer_waiting_run_creates_new_attempt_public_path` |
| Terminal race steer rejection | ✓ | `test_steer_terminal_race_rejects_non_active_target` |
| Retry idempotency | ✓ | `test_retry_run_replays_same_client_request_id_idempotently` |
| Replay idempotency | ✓ | `test_replay_run_replays_same_client_request_id_idempotently` |
| Retry policy limit | ✓ | `test_retry_run_policy_limit_rejects_second_retry` |
| Non-target status rejection | ✓ | `test_retry_and_replay_reject_non_target_source_status` |
| Cancel pre-dispatch | ✓ | `test_pre_dispatch_cancel_visible_in_watch` |
| Cancel active | ✓ | `test_active_cancel_emits_public_cancel_event` |
| Cancel session-scope | ✓ | `test_cancel_session_runs_scoped_to_session` |

**判定：Slice 5 follow-up 覆盖充分。**

### 7. README / Tests README 同步

- `dayu/host/README.md`：`start_run` 描述更新为 ACCEPTED 语义；`submit_followup` 描述更新为 opener baseline requirement；`retry_run` / `replay_run` 从 unsupported 移到已实现；`purge_session` 保留为 unsupported；Engine ingest 描述更新为 empty final answer → FAILED。全部与当前代码一致。
- `tests/README.md`：新增 public-path smoke 与 Engine ingest / watch regression 段落。描述与实际测试文件一致。
- 未发现"未来设计"、旧术语残留或越界说明。

**判定：文档同步正确。**

### 8. 类型 / Docstring / 分层边界

- 新增代码全部提供完整中文 docstring（参数、返回值、异常）。
- pyright 0 errors。
- 未发现 `Any`、`object`、无类型参数或无类型返回值。
- 未发现反向依赖或 schema 兼容代码。
- `_execution_config_projection.py` 正确加入 `HOST_ENGINE_CONTRACT_ALLOWED_MODULES`。

**判定：无类型 / docstring / 分层边界问题。**

## Findings

### Medium

**M1. 测试文件跨模块导入私有 helper**

- 文件：`tests/host/test_public_steer.py:29-32`
- 证据：`from tests.host.test_resolve_wait_command import _options as _command_options, _seed_waiting_run`。同时 `test_public_cancel_smoke.py` 和 `test_public_steer.py` 导入 `test_public_retry_replay.py` 的私有符号（`_BLOCK`、`_SequencedWorkerFactory`、`_context` 等）。
- 风险：测试模块间形成私有依赖链，重构一个测试文件可能破坏其它测试文件。
- 建议：将共享的 deterministic worker、context helper、seed helper 抽取到 `public_smoke_support.py` 或新的 `tests/host/_smoke_helpers.py`。当前不阻塞 P10.5 exit，但应在 aggregate review 或后续 slice 中处理。
- Owner：aggregate review 或 Phase 11 test hardening。

**M2. 调用 scheduler 私有方法 `_run_pre_start_governance`**

- 文件：`tests/host/test_active_cancel_dispatch.py:758`、`tests/host/test_phase7_waiting_integration.py:731`
- 证据：`scheduler._run_pre_start_governance(session_id)` 直接调用 HostDispatchScheduler 的私有方法。
- 风险：scheduler 内部重构会破坏测试。
- 建议：若 governance wakeup 是公开测试需求，考虑在 scheduler 上暴露一个 typed test helper 或 public `wake_pre_start(session_id)` 方法。当前不阻塞 P10.5 exit。
- Owner：Phase 11 scheduler test hardening。

### Low

**L1. Skip marker "503" 匹配范围偏宽**

- 文件：`tests/host/public_smoke_support.py:106`
- 证据：`"503"` 作为 substring marker 匹配 provider error message。理论上可匹配非 HTTP 503 的数字文本。
- 风险：极低。provider error message 通常包含 "HTTP 503" 或 "status 503" 上下文，纯数字 "503" 出现在非 HTTP 语境的概率极小。
- 建议：可考虑改为 `"status 503"` 或 `"http 503"` 以提高精确度，但不阻塞。

**L2. Skip marker "unavailable" 匹配范围偏宽**

- 文件：`tests/host/public_smoke_support.py:110`
- 证据：`"unavailable"` 作为 substring marker。理论上可匹配 "temporarily unavailable" 以外的 "unavailable" 用法。
- 风险：极低。Gemini 503 错误消息通常为 "The model is overloaded" 或 "UNAVAILABLE"，匹配精确。
- 建议：可考虑改为 `"unavailable"` + `"overloaded"` 组合检查，但不阻塞。

**L3. `_NeverCancelledToken` 在 compactor smoke 中硬编码**

- 文件：`tests/host/test_public_compact_smoke.py:58-86`
- 证据：`_NeverCancelledToken` 实现了 `CancellationToken` 接口但始终返回未取消。
- 风险：无。这是 smoke 测试的合理 stub。
- 备注：仅作记录。

## Residual Risk

| 风险 | Owner | 阻塞 P10.5 exit |
|---|---|---|
| Gemini provider quota skip 覆盖不完整（环境限制） | 环境 provider quota | 否。mimo / deepseek / qwen 已通过。 |
| `RECOVERING` cancel、recovery takeover、远端 worker wait 恢复 | Phase 11 | 否。不属于 P10.5 scope。 |
| 测试跨模块私有 helper 依赖链 | aggregate review / Phase 11 | 否。不影响生产代码。 |
| scheduler `_run_pre_start_governance` 私有方法测试依赖 | Phase 11 test hardening | 否。不影响生产代码。 |
| 多进程 admission 旧测试迁移后不再测试即时 promotion timing | 无需修复 | 否。旧 timing 断言不是 public-path success signal。 |

## 验证确认

- Controller 复跑：target smoke 11 passed；provider matrix 3 passed / 1 skipped；tests/host -q 695 passed / 1 skipped；pyright 0；git diff --check clean。
- Reviewer 独立审查：全部 diff 逐行阅读，8 项 review 重点逐项通过。
