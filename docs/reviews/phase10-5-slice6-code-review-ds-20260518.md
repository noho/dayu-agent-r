# P10.5 Slice 6 Code Review — AgentDS

## 结论：PASS

Blocking count = 0。High count = 1（residual risk, 不阻塞 P10.5 exit）。Medium count = 2。Low count = 2。

## 审查范围

审查了当前 workspace uncommitted diff（18 文件，+969/-124），覆盖：
- 新增 smoke：`test_public_open_host_multiturn_smoke.py`、`test_public_tool_wiring_smoke.py`、`test_public_real_runner_matrix_smoke.py`、`test_public_compact_smoke.py`、`test_public_cancel_smoke.py`（部分新增）
- 测试支撑：`tests/host/public_smoke_support.py`
- 窄生产修复：`dayu/host/engine_ingest.py` empty final answer → FAILED
- Slice 5 follow-up 扩展：`test_public_steer.py`、`test_public_retry_replay.py`
- Watch 回归测试：`test_watch_session_events.py`、`test_engine_ingest_mapping.py`
- 旧测试迁移：`test_public_run_api.py`、`test_public_cancel_session_runs.py`、`test_active_cancel_dispatch.py`、`test_admission_multiprocess.py`、`test_phase7_waiting_integration.py`、`test_public_open_host_options.py`、`test_durable_schema.py`、`test_state_schema.py`、`test_import_boundary.py`
- 文档同步：`dayu/host/README.md`、`tests/README.md`、`docs/host/implementation-control.md`

对照设计真源 `docs/host/design.md`、总控文档 `docs/host/implementation-control.md`、P10.5 Plan Slice 6 与 Unified Coverage Table，逐项评审。

---

## 1. P10.5 Slice 6 Success Signal

### 1.1 S1 Real-runner No-tool Multi-turn — PASS

`test_real_runner_no_tool_two_turn_public_path` (`tests/host/test_public_open_host_multiturn_smoke.py:27`) 使用 `first_available_provider_case()` 选择第一个可用真实 provider，两轮均通过 `open_host` → `submit_followup(queue)` → `watch_session_events` terminal `HostEvent.final_answer` 断言，不读取 durable truth 作为 correctness assertion。第一轮成功后调用 `skip_if_provider_terminal_failed` 后再断言 `SUCCEEDED`，两轮间不依赖 durable 内部表。

### 1.2 S1 Multi-client Watch / Queue Idempotency — PASS

`test_two_watchers_observe_same_terminal_event` (`tests/host/test_public_open_host_multiturn_smoke.py:84`) 使用 `FinalAnswerWorkerFactory` deterministic worker，两个 watcher 通过 `asyncio.gather` 并发获取同一 terminal event，断言 `event_id` / `event_sequence` / `dedupe_key` 一致。`test_concurrent_queue_uses_client_request_id_idempotency` (同文件:122) 验证同一 `client_request_id` 并发重放返回同一 `accepted_run_id`，不同 `client_request_id` 产出不同 Run。

Plan coverage table 明确此两项 "No provider skip for deterministic local runner support; real runner variant may skip by provider"，不将 mock runner 计入 real-runner signal。

### 1.3 S1 Per-run Execution Override — PASS

`test_submit_followup_field_level_execution_override_freezes_effective_config` (`tests/host/test_public_open_host_multiturn_smoke.py:162`) 使用 `FinalAnswerWorkerFactory` 验证：只传 `runner_options` 时 `runner_spec` 来自 opener baseline；只传 `runner_spec` 时 `runner_options` 来自 baseline。worker factory 记录每次接受的 `AgentRunRequest`，断言 effective config 按字段冻结到 Engine request 层。

### 1.4 S2 Mock-tool Wiring — PASS

`test_mock_tool_fact_enters_memory_and_next_run_input` (`tests/host/test_public_tool_wiring_smoke.py:25`) 使用 `ToolCallingWorkerFactory` + `_ScriptedToolRunner`，第一轮产出 tool call → ToolRuntime accept → tool fact，第二轮 Continuation 中包含 `ToolMessage`，第三轮 RunInputBuilder 中包含 `event_ref=` 引用。`test_tool_names_subset_and_empty_freeze` (同文件:79) 验证 `tool_names=frozenset({"lookup_mock_fact"})` 产出单工具 schema、`tool_names=frozenset()` 产出空 schema。

Mock runner 不计入 real-runner success signal。工具 wiring 的 `MockFactTool` 只机械按参数返回固定事实，不读取测试私有答案。

### 1.5 S3 Real-runner Matrix — PASS with One Provider Skip

`test_{mimo,deepseek,gemini,qwen}_public_real_runner_two_turn_path` (`tests/host/test_public_real_runner_matrix_smoke.py:24-76`)。Controller 复跑：`3 passed, 1 skipped`（Gemini HTTP 429 / `RESOURCE_EXHAUSTED` / `QuotaFailure` / `RetryInfo`）。mimo、deepseek、qwen 真实 provider public path 全部通过。

Skip precision 见 §2。

### 1.6 S4 Real Compactor Smoke — PASS

`test_real_compactor_public_opener_compacts_and_preserves_continuity` (`tests/host/test_public_compact_smoke.py:242`) 使用显式真实 LLM compactor adapter `_RealLLMContextCompactor`。该 adapter 调用 `run_agent_and_wait` 以 deepseek provider 生成摘要，包装为 `CompactionCandidate`。ordinary Run 使用 `FinalAnswerWorkerFactory` deterministic worker；compactor baseline 独立于 ordinary Run override。`compactor_baseline` 显式注入 `CompactorExecutionBaseline(context_compactor=compactor)`，不依赖隐式 fake compactor。

**High finding — H1 (residual)**: compactor smoke 对 compactor provider 临时不可用（503/429）的保护仅覆盖 `api_key_or_skip`（secret 缺失），不覆盖 compactor 执行中途的 provider 临时不可用。若 deepseek 在执行 compaction 时返回 503 或 429，`_run_llm_summary` 会 raise `RuntimeError` 导致 test hard fail，不会被 skip。当前 deepseek 可用，测试通过，但这是 residual risk。见 §9。

### 1.7 S5 Cancel / Close Boundary — PASS

`test_cancel_accepted_queued_and_active_public_path`、`test_pre_dispatch_cancel_visible_in_watch`、`test_active_cancel_emits_public_cancel_event`、`test_cancel_session_runs_scoped_to_session` (`tests/host/test_public_cancel_smoke.py:32-203`)。全部通过 public handle 调用 `cancel_run` / `cancel_session_runs`，通过 `get_run` / `watch_session_events` 观察取消结果，通过 shared active registry 传播 cancel 到 worker。

---

## 2. Provider Skip Precision — PASS

`skip_if_provider_terminal_failed` (`tests/host/public_smoke_support.py:826`) 的三层 skip marker：

| 层级 | 触发条件 | 示例 |
|---|---|---|
| Network failure | `clientconnectorerror`, `connection refused`, `timeout`, `name or service not known`, `network is unreachable`, `connection reset` | 网络不可达 |
| Provider temporary unavailable | `503`, `unavailable`, `server overloaded`, `model is overloaded`, `temporarily unavailable`, `try again later` | 提供方临时过载 |
| Provider rate limit / quota | `429`, `rate_limit_exceeded`, `rate limit`, `retrydelay`, `retry delay` | Gemini `RESOURCE_EXHAUSTED` / `QuotaFailure` / `RetryInfo` |

三层均仅在 `terminal_status is HostTerminalStatus.FAILED` 时检查。非临时 API/schema/contract failure（如 invalid model、invalid API key format、provider 返回 400/401/403/404）不会命中任何 marker，会 hard fail。

Provider case 定义 (`public_smoke_support.py:512-558`) 使用硬编码 endpoint 和 env var name，不依赖 ConfigLoader 或全局配置。

**验证**: Gemini skip reason 为 `provider=gemini endpoint=... provider_quota_or_rate_limit=resource_exhausted message=...`，精确报告 provider、endpoint 与失败原因。

---

## 3. Empty Final Answer → FAILED Production Fix — PASS

### Root Cause 判断

旧 `_final_answer_plan` (`dayu/host/engine_ingest.py:2830-2850`) 对所有 `FinalAnswerData` 写入 `RUN_SUCCEEDED`，包括 `content=""` 的场景。当 `finish_reason=LENGTH` + `content=""` 时，public `watch_session_events` 需要投影 `HostFinalAnswerView`，但 `content` 为空白无法展示，导致 watch 读取时崩溃。

修复在 `_final_answer_plan` 添加 blank content guard：
```python
if data.content.strip() == "":
    return _failed_plan(
        reason=_REASON_EMPTY_FINAL_ANSWER,
        error_code=_REASON_EMPTY_FINAL_ANSWER,
        ...
    )
```

修复后空白 final answer 写入 `ATTEMPT_FAILED` + `RUN_FAILED`（`error_code=empty_final_answer`），不写入 `RUN_SUCCEEDED`。public watch 将其投影为 typed `HostEvent(kind=FAILED, terminal_status=FAILED, error_message="...no displayable content...")`。

### 设计真源一致性

- `docs/host/design.md` §11：`HostEvent` terminal `SUCCEEDED` 必须 inline `final_answer` view，`content` 字段承载可展示答案内容。空白 content 不能构成合法的 `SUCCEEDED` 终端事件。
- `docs/host/design.md` §5：EngineEvent Ingest "唯一负责把 Engine / Worker / ToolRuntime 回传事件验证、分类并转成 Host event"——拒绝空白 final answer 属于 ingest 层的验证职责。
- Plan §16：`watch_session_events` terminal final answer view 必须包含非空 `content`。

修复符合 root cause fix 标准：在 ingest 边界拒绝不合格的 terminal event，而非在投影层做事后修补。不改变 Run / Attempt / EventLog 状态机，不引入新的 EventLog event type。

### 回归测试

- `test_empty_final_answer_closes_failed_without_run_succeeded` (`tests/host/test_engine_ingest_mapping.py:230`)：低层 ingest 验证 RUN_SUCCEEDED count = 0, RUN_FAILED count = 1，error_code = "empty_final_answer"
- `test_empty_final_answer_terminal_projects_as_failed_event` (`tests/host/test_watch_session_events.py:482`)：public watch 路径验证 terminal kind = FAILED, final_answer = None, error_message 包含 "no displayable content"

---

## 4. Real Compactor Smoke — PASS (见 H1 residual)

真实 compactor adapter `_RealLLMContextCompactor` (`tests/host/test_public_compact_smoke.py:121`)：
- 在线程中 `asyncio.run()` 执行 `run_agent_and_wait`，使用 deepseek provider（`PROVIDER_CASES[1]`）
- `compactor_runner_spec` 从 deepseek `RunnerSpec` 派生，`provider_request=None`（compactor 不需要 thinking extension）
- `run_agent_and_wait` 传入 `disable_tools=True`、`tool_executor=_RejectingToolExecutor()`（defense-in-depth：compactor 不应调用业务工具）
- 构造 `CompactionCandidate` 通过 `_candidate_from_summary` 映射真实 LLM 摘要为 Host typed candidate

ordinary Run 使用 `FinalAnswerWorkerFactory`（deterministic），不干扰 compactor 真实性判断。

Compactor `call_count` 和 `last_summary` 断言在 test body 中，不依赖 durable compact artifact 解析。

`_RejectingToolExecutor` 对所有 tool call 返回 `ToolFailedOutcome(error="compact_tool_call_forbidden")`——这是 defense-in-depth，compactor prompt 要求不调用工具，若 LLM 误调用工具则拒绝。

---

## 5. 旧测试迁移 — PASS

### 5.1 `test_public_run_api.py`

| 旧断言 | 新断言 | 理由 |
|---|---|---|
| `start_run` → `RUNNING` | `start_run` → `ACCEPTED` | P10.5 pre-start governance contract |
| `attach_active` 附着 `RUNNING` Run | `attach_active` 对 `ACCEPTED` Run 返回 `CONFLICT` | `ACCEPTED` Run 尚无 Attempt，不能 attach |
| `submit_followup` 低层可用 | `submit_followup` 低层无 opener baseline 时 fail closed | 低层 command handle 缺少 opener ordinary baseline |
| steer → `UNSUPPORTED_OPERATION` | steer → `INVALID_STATE`（未启动 target） | 语义更精确 |
| retry/replay → `UNSUPPORTED_OPERATION` | retry/replay → `INVALID_STATE`（非目标源状态）；purge → `UNSUPPORTED_OPERATION` | retry/replay 已激活，purge 仍 deferred |

迁移方向与 P10.5 accepted contract 一致。旧行为（direct RUNNING、无 opener 可用 submit_followup）不再被保留为兼容行为。

### 5.2 `test_public_cancel_session_runs.py`

新增 `_start_governed_run()` helper，把 `ACCEPTED` Run 通过 scheduler pre-start governance 推进到 `RUNNING`，再 `_accept_active_worker`。旧测试直接假设 `start_run` 返回的 `current_attempt_id` 非空——这不再成立。

`unsupported non-terminal` 测试从 `WAITING` 改为 `RECOVERING`（当前 `WAITING` 已在 cancel 支持范围，`RECOVERING` 在 Phase 11）。测试注释同步更新。

### 5.3 `test_admission_multiprocess.py`

- `active Run` 统计从 `RUNNING` 改为 `ACCEPTED`（符合 pre-start contract：admission 只创建 `ACCEPTED` Run）
- `Attempt` 行数从 1 改为 0（`ACCEPTED` Run 尚无 Attempt）
- `_admission_service` 构造带 `ordinary_run_baseline` 的 admission service（`submit_followup_queue` 需要 baseline）
- `closeout_attempt_terminal` 后 promotion 使用 fallback `service.promote_next_queued_run`（因为 closeout 路径下 RunInputBuilder 不依赖 admission 自身 promotion）

多进程 durable invariant 断言不变：同 slot ensure 唯一 Session、同 Session 一个 active Run、FIFO promotion、跨进程幂等。

### 5.4 `test_active_cancel_dispatch.py`

- 原 `start_run` → `RUNNING` → 直接 `_refs()` 读取 Attempt refs 的路径改为：`start_run` → `ACCEPTED` → scheduler `_run_pre_start_governance` → `_start_governed_refs` → `_pending_dispatch`
- `_mark_waiting_for_lane`、`_mark_dispatching` 操作移到 async context 内（scheduler 持有 store transaction runner）
- cancel 后 dispatch 行为断言不变（cancel skip later dispatch、pre-accept cancel stays cancelled、active worker cancel propagates、late cancel doesn't overwrite terminal）

迁移在 async context 内使用 `asyncio.run()` 桥接同步测试——这是测试代码可接受的模式。

### 5.5 其他迁移

- `test_phase7_waiting_integration.py:389`：`_pending_dispatch_from_started_run` → `scheduler._run_pre_start_governance`。WAITING → resolve_wait resume 核心路径不变。
- `test_public_open_host_options.py:336`：从 "Slice 1 body is deferred"（`NotImplementedError`）改为实际 opener 功能验证（`ensure_session` + slot assertion）。自然演进。
- `test_durable_schema.py:233`：`user_version == 8` → `user_version == HOST_SCHEMA_VERSION`。Self-adapting，不硬编码版本号。
- `test_state_schema.py:124`：`RunStartReason` exhaustive 断言补充 `RECOVERY`、`STEER`。
- `test_import_boundary.py:47`：`_execution_config_projection.py` 加入 Host Engine contract 允许模块白名单。

**结论**：迁移严格跟随 P10.5 accepted pre-start governance contract，不掩盖真实行为回归。

---

## 6. Slice 5 Follow-up Coverage — PASS

| 覆盖项 | 证据 | 状态 |
|---|---|---|
| steer RUNNING 新 Attempt | `test_steer_running_run_creates_new_attempt_public_path` (`test_public_steer.py:36`) | covered |
| steer WAITING 新 Attempt | `test_steer_waiting_run_creates_new_attempt_public_path` (`test_public_steer.py:79`) | covered |
| steer terminal race 拒绝 | `test_steer_terminal_race_rejects_non_active_target` (`test_public_steer.py:121`) | covered |
| retry FAILED 关联新 Run | `test_retry_failed_run_creates_related_run_public_path` (`test_public_retry_replay.py:207`) | covered |
| retry idempotency | `test_retry_run_replays_same_client_request_id_idempotently` (`test_public_retry_replay.py:236`) | covered |
| retry policy limit | `test_retry_run_policy_limit_rejects_second_retry` (`test_public_retry_replay.py:269`) | covered |
| replay no-tool | `test_replay_succeeded_run_no_tool_public_path` (`test_public_retry_replay.py:310`) | covered |
| replay idempotency | `test_replay_run_replays_same_client_request_id_idempotently` (`test_public_retry_replay.py:349`) | covered |
| 非目标源状态 rejection | `test_retry_and_replay_reject_non_target_source_status` (`test_public_retry_replay.py:383`) | covered |
| cancel pre-dispatch watch visible | `test_pre_dispatch_cancel_visible_in_watch` (`test_public_cancel_smoke.py:79`) | covered |
| cancel active public event | `test_active_cancel_emits_public_cancel_event` (`test_public_cancel_smoke.py:121`) | covered |
| cancel session-scoped | `test_cancel_session_runs_scoped_to_session` (`test_public_cancel_smoke.py:156`) | covered |
| cancel queued + active | `test_cancel_accepted_queued_and_active_public_path` (`test_public_cancel_smoke.py:31`) | covered |

Full `tests/host -q` 695 passed 覆盖上述所有测试。

---

## 7. README / Tests README 同步 — PASS

### `dayu/host/README.md`

- Low-level Run command facade：`start_run` 描述从 `direct RUNNING` 改为 `ACCEPTED` pre-start，`attach_active` 条件更新
- `submit_followup` 低层描述从 "复用 internal submit_followup_queue" 改为 "低层 command handle 缺少 opener ordinary baseline 时会 fail closed"
- retry/replay 从 "stable unsupported" 移到 "current ordinary public retry / replay 已接入 Host admission"，只保留 purge 在 unsupported 列表
- EngineEvent ingest mapping 补充 "final answer 只有在 content 非空白时才写入 RUN_SUCCEEDED；空白 final answer 会按 empty_final_answer 收口为 FAILED"

均为同步当前实现事实，无未来设计或越界说明。

### `tests/README.md`

- 新增 "public-path smoke" 条目：列出五个 smoke 文件及其覆盖范围，明确 real runner / compactor smoke skip 规则
- 新增 "Engine ingest / watch regression" 条目：空 final answer → FAILED + public watch 投影

均为同步当前测试事实，无越界。

### `docs/host/implementation-control.md`

- 更新当前 gate 和下一 gate 状态到 "P10.5 Slice 6 code review"
- 追加 Slice 6 implementation artifact 引用与 Controller 复跑验证事实

---

## 8. 类型、Docstring、边界问题 — PASS

### 8.1 新增代码类型检查

- `public_smoke_support.py`：所有公开类/函数均为 typed，`ProviderSmokeCase` 使用 `frozen=True, slots=True`，`FinalAnswerHandle` / `FinalAnswerWorker` / `ToolCallingWorkerFactory` 等实现 `LocalWorkerHandle` / `LocalEngineWorker` 协议。docstring 完整覆盖参数、返回值、异常。
- Smoke 测试文件：所有测试函数签名完整 typed（`tmp_path: pathlib.Path` → `None`），docstring 完整。
- `_RealLLMContextCompactor` 实现 `ContextCompactor` 协议，`compact()` 返回 `CompactionCandidate`。

### 8.2 无禁止模式

- 未发现 `Any`、`object`、裸容器注解新增。
- 未发现 `hasattr`、`getattr` 滥用。
- 未发现 magic number 泄漏到生产代码（test 文件中的常量均有 `_` 前缀或模块级命名）。
- 未发现反向依赖：Engine 不导入 Host，Host 不导入 Service/Fins/UI。
- 未发现兼容性 re-export 或 wrapper。

### 8.3 Import Boundary

`tests/host/test_import_boundary.py` 新增 `_execution_config_projection.py` 到 Host Engine contract 允许模块白名单——这是 Slice 3 引入的 execution config projection 模块，Host 在 dispatch 路径需要导入以构造 Engine request 的可诊断 config 快照。该模块是 Host 内部模块，import 方向正确（Host → Engine contract），未违反分层。

### 8.4 测试间依赖

`test_public_cancel_smoke.py` 从 `test_public_retry_replay` import `_BLOCK`、`_SequencedWorkerFactory`、`_context`、`_ensure_request`、`_followup_request`、`_options`、`_wait_for_event_type_count`、`_wait_for_run_status`（`tests/host/test_public_cancel_smoke.py:19-28`）。`test_public_steer.py` 同样从 `test_public_retry_replay` import helper（`:19-28`），并从 `test_resolve_wait_command` import `_options` 和 `_seed_waiting_run`（`:29-33`）。

这是**Medium finding — M1**：跨测试模块私有 helper 依赖。`_BLOCK` / `_SequencedWorkerFactory` 等 helper 在多个测试文件中重复定义或跨模块 import，增加了耦合。`public_smoke_support.py` 已经作为共享支撑模块存在，但这些 Slice 5 测试的 helper 未迁移到共享模块。不阻塞 P10.5 exit，因为不影响生产代码，但增加后续测试维护成本。

### 8.5 `_unreachable_engine_event` Dead Code

`test_public_retry_replay.py:626-632` 中 `_unreachable_engine_event()` 使用 `if False: yield ...` 维持返回值类型。**Low finding — L1**：可以改为 `raise AssertionError("unreachable")` 返回 `Never` 类型（Python 3.11+ `typing.Never`）。当前实现功能正确，不修改。

### 8.6 `asyncio.run()` in Sync Tests

`test_active_cancel_dispatch.py` 在同步测试函数内使用 `asyncio.run()` 创建临时 event loop 以执行 scheduler 操作。这是合理模式（测试非 async，需要在同步测试内访问 async scheduler）。**Low finding — L2**：嵌套 `asyncio.run()` 可能在某些环境下触发 "event loop already running" 错误，但当前测试通过说明未触发。不阻塞。

---

## 9. Residual Risks

| Risk | Severity | Owner | Blocks P10.5 Exit? |
|---|---|---|---|
| **H1**: Compactor smoke 对 compactor provider 临时不可用（503/429）无内联 skip——`_run_llm_summary` 中 `run_agent_and_wait` 若因 provider 503/429 返回失败，会 `raise RuntimeError` 导致 test hard fail。当前 deepseek 可用，测试通过。 | HIGH (residual) | Slice 6 follow-up 或 Controller acceptance | **否**（residual risk acceptance by Controller）。若需修复，可在 `_RealLLMContextCompactor._run_llm_summary_async` 中 catch provider-unavailable error 并 `pytest.skip`。|
| Gemini provider quota 429 skip | MEDIUM (residual) | Environment / provider quota | **否**（已精确 skip）。mimo/deepseek/qwen 真实 public path 已证明。 |
| **M1**: 跨测试模块私有 helper 依赖（cancel smoke / steer 从 retry_replay import） | MEDIUM (maintenance) | Future test cleanup | **否** |
| `RECOVERING` cancel / recovery takeover / crash recovery | Phase 11 owner | Phase 11 | **否** |
| `LOST` / `RECOVERING` retry | Phase 11 owner | Phase 11 | **否** |

---

## Findings Summary

| ID | Severity | Finding | File(s) |
|---|---|---|---|
| — | BLOCKING | 无 | — |
| H1 | HIGH (residual) | Compactor smoke 缺少 compactor provider 临时不可用（503/429）内联 skip，当前 deepseek 可用故通过 | `tests/host/test_public_compact_smoke.py:157-191` |
| M1 | MEDIUM | 跨测试模块私有 helper import（cancel smoke / steer 从 retry_replay import helper） | `tests/host/test_public_cancel_smoke.py:19-28`, `tests/host/test_public_steer.py:19-33` |
| M2 | MEDIUM | Slice 6 smoke 测试 `public_smoke_support.py` 提供了 `_SequencedWorkerFactory` 等价能力（`FinalAnswerWorkerFactory`、`ToolCallingWorkerFactory`），但 Slice 5 测试未复用，各自定义 | `tests/host/test_public_retry_replay.py:138-205` vs `tests/host/public_smoke_support.py:222-305` |
| L1 | LOW | `_unreachable_engine_event` dead code 用 `if False: yield` | `tests/host/test_public_retry_replay.py:626-632` |
| L2 | LOW | 同步测试内嵌 `asyncio.run()` | `tests/host/test_active_cancel_dispatch.py` |

---

## 最终判定

**P10.5 Slice 6: PASS**。0 blocking findings。

P10.5 success signal 覆盖：
- S1 real-runner no-tool multi-turn ✓
- S2 mock-tool wiring ✓
- S3 real-runner matrix ✓（1 provider skip，精确标记原因）
- S4 real compactor smoke ✓（residual risk H1 不阻塞）
- S5 cancel / close boundary ✓
- Slice 5 follow-up coverage ✓
- 旧测试迁移 ✓
- Empty final answer → FAILED root cause fix ✓
- README / tests README 同步 ✓
- 类型/docstring/分层边界 ✓

Controller 应确认接受 H1 residual risk（compactor smoke 在 compactor provider 临时不可用时会 hard fail 而非 skip），或要求 follow-up fix 后再进入 accepted slice commit。
