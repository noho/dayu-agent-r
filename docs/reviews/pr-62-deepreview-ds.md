# PR 62 Deep Review — Second Independent Reviewer

## Scope

- Mode: PR
- Repository: noho/dayu-agent-r
- PR: [#62](https://github.com/noho/dayu-agent-r/pull/62)
- Title: Host P10.5 ordinary local multi-turn public contract freeze
- Author: noho
- Head: feat/host-p10-5-public-contract-freeze
- Base: main
- Output file: docs/reviews/pr-62-deepreview-ds.md
- Included scope: 全量 diff（Host-owned compactor、async compaction operation、scheduler promotion lifecycle、Engine ingest async split、runtime lane refresh cancellation cleanup、manual smoke、README/docs、AGENTS/CLAUDE 更新、全部 tests）
- Excluded scope: 无
- Subagent coverage:
  - compaction/llm_compaction/context_events/context_policy/context_budget （Agent 1）
  - open_host/dispatch/admission/command/engine_ingest/api/__init__ （Agent 2）
  - lane/engine runner/durable state/read_api/run_input/tool_runtime/execution_config （Agent 3）
  - 全部 tests 和 manual smoke （Agent 4）
- Not covered: 无；所有关键链路均已走读。

## Conclusion: PASS（无 blocking findings）

未发现 correctness、stability 或 security blocker。以下 findings 按严重程度从高到低排序，均不构成 merge blocker，但建议在 merge 前或后续 phase 中处理。

---

## Findings

### F1-未修复-高-fake_compaction 预算估算与真实 LLM compactor 不一致

- **入口/函数**: `FakeContextCompactor.compact()` → `_candidate_from_request()`
- **文件(行号)**: `dayu/host/fake_compaction.py:92-94`
- **输入场景**: 集成测试使用 `FakeContextCompactor`，且 `estimated_input_tokens // 2 >= hard_threshold_tokens` 时
- **实际分支**: `budget_after_compact = max(0, request.budget_before_compact.estimated_input_tokens // 2)`
- **预期行为**: budget_after_compact 应被 clamp 到 `hard_threshold_tokens - 1`，与真实 LLM compactor 行为一致
- **实际行为**: fake compactor 不做 clamp，可能产生 `budget_after_compact >= hard_threshold_tokens`，导致 `compaction_operation.py:140-143` 的 hard threshold 检查拒绝该 candidate
- **直接证据**:
  - `llm_compaction.py:450-451`: `return min(half_estimate, estimate.hard_threshold_tokens - 1)` — 真实 compactor 有 clamp
  - `fake_compaction.py:92-94`: `max(0, request.budget_before_compact.estimated_input_tokens // 2)` — fake compactor 无 clamp
  - `compaction_operation.py:140-143`: 检查 `candidate.budget_after_compact >= hard_threshold_tokens` 时拒绝
- **影响**: 使用 `FakeContextCompactor` 的集成测试（如 `test_dispatch_scheduler.py` 中的 compaction 集成测试）在预算接近 hard threshold 时出现**假阴性失败** — 真实 LLM compactor 会成功但 fake compactor 被拒绝。这会导致测试不可信。
- **建议改法和验证点**: 在 `fake_compaction.py` 的 `_candidate_from_request` 中对 `budget_after_compact` 做与 `llm_compaction.py:_budget_after_compact` 相同的 clamp：`min(half_estimate, hard_threshold_tokens - 1)`。需从 `request.budget_before_compact.hard_threshold_tokens` 读取阈值。验证：使用 fake compactor 的 compaction 集成测试在 `estimated_input_tokens // 2 >= hard_threshold_tokens` 时不应出现 false negative。
- **修复风险（低）**: 仅改一行预算计算逻辑，不影响任何其他路径。
- **严重程度（高）**: 测试 fidelity 问题，可能导致 compaction 集成测试不可信。

### F2-未修复-高-engine_ingest reactive compaction 陈旧状态检查窄于 dispatch proactive 检查

- **入口/函数**: `EngineEventIngestor._execute_reactive_compaction()` → `_operation()`
- **文件(行号)**: `dayu/host/engine_ingest.py:1415-1424`
- **输入场景**: reactive compaction LLM 调用返回后，Run 状态仍为 `RECOVERING` 且有 `terminal_event_id`，但 `input_event_sequence` 已变化（如 Engine 在 compaction 期间又推送了新事件）
- **实际分支**: 仅检查 `run.status is not RunStatus.RECOVERING` 和 `attempt.terminal_event_id is None`
- **预期行为**: 应与 dispatch proactive 路径一致，检查 Run 的快照一致性（status + input_event_sequence）
- **实际行为**: 只检查 Run 仍是 `RECOVERING`，不检查快照序列号是否匹配。若 compaction LLM 调用期间有新的 Engine 事件被 ingest（改变了 EventLog），compacted 结果可能基于过时的 context snapshot 写入
- **直接证据**:
  - `dispatch.py:940-943`: `run.status != pending.expected_status or run.input_event_sequence != pending.expected_input_event_sequence` — proactive 路径有完整快照一致性检查
  - `engine_ingest.py:1415-1424`: 仅检查 `RECOVERING` + `terminal_event_id is None` — reactive 路径检查更窄
  - `engine_ingest.py:1406`: `await run_compaction_operation(...)` — LLM 调用在事务外，调用期间状态可能变化
- **影响**: 在极端时序下（Engine 在 compaction LLM 调用期间推送新事件并被另一个 ingest 路径处理），reactive compaction 可能基于过时的 context 写入 compacted event，导致 memory projection 消费了不反映最新事件的 compact artifact。
- **建议改法和验证点**: 在 `_execute_reactive_compaction` 的写事务中增加 `input_event_sequence` 快照一致性检查，与 proactive 路径对齐。或者在 `pending` 中保存预期的 `input_event_sequence`，写事务内做 CAS 比较。验证：新增 `test_engine_ingest_mapping.py` 测试，覆盖 compaction LLM 调用期间 Run 的 input_event_sequence 变化场景。
- **修复风险（中）**: 需要在 `_ReactiveCompactPending` 中新增字段保存预期快照，改动涉及 reactive compaction 的数据流。
- **严重程度（高）**: 极端时序下的 correctness 风险，可能导致 memory projection 消费不反映最新状态的 compact artifact。

### F3-未修复-中-test_public_compact_smoke 在多个路径上静默跳过

- **入口/函数**: `test_real_compactor_public_opener_compacts_and_preserves_continuity`
- **文件(行号)**: `tests/host/test_public_compact_smoke.py:56-57, 123, 136, 139`
- **输入场景**: DEEPSEEK_API_KEY 未设置、网络不可用、provider 返回 503/429，或 terminal event 为 FAILED 时
- **实际分支**: `api_key_or_skip` → `pytest.skip`；`skip_if_provider_exception` → `pytest.skip`；`skip_if_provider_terminal_failed` → `pytest.skip`
- **预期行为**: skip 应报告明确原因，且 skip 不应掩盖"compaction 未触发但 terminal 仍为 SUCCEEDED"的场景
- **实际行为**: 三条 skip 路径均可导致测试静默通过，核心断言 `first_terminal.kind is HostEventKind.SUCCEEDED`（line 140）和 `len(new_artifacts) > 0`（line 152）从未执行。测试结果为 "passed" 但 compaction 路径完全未验证
- **直接证据**:
  - line 57: `api_key_or_skip(deepseek_api_key, provider_case, request)` — API key 缺失时 skip
  - line 123: `skip_if_provider_terminal_failed(first_terminal, request, "round1")` — terminal FAILED 时 skip
  - line 136: `skip_if_provider_exception(request, "compact smoke")` — provider 异常时 skip
  - line 139: `skip_if_provider_terminal_failed(second_terminal, request, "round2")` — 第二轮 terminal FAILED 时 skip
- **影响**: S4 compact smoke 可能在 CI 中长期 skip 而无人察觉，compact 回归无法被 CI 捕获。与 design doc 要求"S4 真实 compactor smoke 不能在 provider 可用时被 mock 替代"矛盾。
- **建议改法和验证点**: 
  1. 新增一个不使用真实 provider 的 compaction 集成测试（使用 `FakeContextCompactor` + 可控 budget 触发），作为 S4 的 CI-gate 单元测试
  2. 真实 provider compact smoke 的 skip 改为 `pytest.skip` 带明确的 skip reason，并在 CI 日志中可见
  3. 在 smoke 报告中统计 skip 次数，超过阈值时 CI warning
- **修复风险（低）**: 新增测试文件，不影响现有测试。
- **严重程度（中）**: 测试 coverage gap，真实 compaction 路径在 CI 中无强制验证，回归风险累积。

### F4-未修复-中-cancel smoke 缺少 ACCEPTED 和 WAITING 状态覆盖

- **入口/函数**: 多个测试（`test_cancel_accepted_and_queued_runs_public_path` 等）
- **文件(行号)**: `tests/host/test_public_cancel_smoke.py` 全文
- **输入场景**: 
  1. Run 处于 ACCEPTED 状态（admission 已接受但尚未 queued）时调用 cancel
  2. Run 处于 WAITING 状态时调用 cancel
  3. 对已 CANCELLED 的 Run 再次调用 cancel（幂等性）
  4. 对 SUCCEEDED 或 FAILED 的 Run 调用 cancel（应拒绝）
  5. 使用非 `GRACEFUL` 的 `CancelMode`（如后续新增 FORCE）
- **实际分支**: 当前测试仅覆盖 queued、pre-dispatch、active/RUNNING、session-scope 四种场景
- **预期行为**: cancel 应在所有合法状态下有定义行为，非法状态应返回明确错误
- **实际行为**: ACCEPTED 和 WAITING 状态的 cancel 行为未验证；cancel 幂等性未验证；非法状态 cancel 行为未定义
- **直接证据**: 
  - 测试文件中仅 4 个测试函数，覆盖状态矩阵的 4/7+ 状态
  - design doc §5 明确要求验证 "accepted / queued / pre-dispatch / active / session-scope cancel"
  - `RunStatus.ACCEPTED` 存在于枚举中但 cancel smoke 未覆盖
- **影响**: ACCEPTED 或 WAITING 状态下的 cancel 行为未经测试验证，可能存在未定义行为或静默失败。
- **建议改法和验证点**: 新增 `test_cancel_accepted_run_public_path`、`test_cancel_waiting_run_public_path`、`test_cancel_idempotency`、`test_cancel_terminal_run_rejected`。验证：所有 cancel 路径返回正确的 HostEvent kind 和 cancel_reason。
- **修复风险（低）**: 新增测试，不修改生产代码（除非测试暴露 bug）。
- **严重程度（中）**: 测试 coverage gap，cancel 行为在非 happy-path 状态上未验证。

### F5-未修复-中-compaction_operation 测试仅覆盖 max_attempts=2

- **入口/函数**: `test_run_compaction_operation_retries_after_async_failure`、`test_run_compaction_operation_fails_after_async_attempt_budget`
- **文件(行号)**: `tests/host/test_compaction_operation.py:67, 86`
- **输入场景**: `max_attempts=1`（不重试）、`max_attempts=0`（非法输入）、`max_attempts` 为负数的场景
- **实际分支**: 两个测试均传入 `max_attempts=2`
- **预期行为**: `max_attempts=1` 时第一次失败应直接返回 failure result 不重试；`max_attempts=0` 或负数应被拒绝或按 `1` 处理
- **实际行为**: 边界行为未定义且未测试
- **直接证据**:
  - `test_compaction_operation.py:67`: `max_attempts=2` — 仅测试双 attempt 场景
  - `test_compaction_operation.py:86`: `max_attempts=2` — 同上
  - `compaction_operation.py:87`: `for attempt_number in range(1, max_attempts + 1)` — `max_attempts=0` 时循环体不执行，直接返回 `None` candidate，行为可能不符合预期
- **影响**: `max_attempts=1` 场景未验证（最常见配置）；`max_attempts=0` 时 `run_compaction_operation` 的默认行为（返回 `CompactionOperationResult` 全 None）可能被调用方误判。当前默认值为 `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 1`（`context_policy.py:25`），而测试从未覆盖此默认路径。
- **建议改法和验证点**: 新增 `test_run_compaction_operation_single_attempt_no_retry`（max_attempts=1，compactor 失败 → 直接返回 failure）；新增 `test_run_compaction_operation_zero_attempts_returns_empty_result`。验证 `max_attempts=0` 或负数时 `ContextBudgetPolicy.__post_init__` 的拒绝行为。
- **修复风险（低）**: 新增测试。
- **严重程度（中）**: 测试 coverage gap，默认配置路径（max_attempts=1）未覆盖。

### F6-未修复-低-HostApiErrorDetail 别名语义过窄

- **入口/函数**: TypeAlias 定义
- **文件(行号)**: `dayu/host/api.py:1203`
- **输入场景**: 调用方捕获 `HostApiError` 并检查 `detail` 字段类型
- **实际分支**: `HostApiErrorDetail: TypeAlias = SteerConflictDetail`
- **预期行为**: `HostApiErrorDetail` 应为 closed union（如 `SteerConflictDetail | RetryConflictDetail | ...`），或至少名称反映当前实际内容
- **实际行为**: 名称暗示通用 error detail，但实际只包含一种具体类型。未来新增 error detail 类型时需改为 `Union`，现有调用方的 `isinstance(detail, SteerConflictDetail)` 检查可能失效
- **直接证据**:
  - `api.py:1203`: `HostApiErrorDetail: TypeAlias = SteerConflictDetail`
  - `api.py:2578`: `detail: HostApiErrorDetail | None` — 在 `HostApiError` 中使用
- **影响**: 调用方可能误以为 `HostApiErrorDetail` 包含所有 error detail 类型的联合，实际上只是 steer conflict。未来扩展时是 API breaking change。
- **建议改法和验证点**: 改为显式 union：`HostApiErrorDetail: TypeAlias = SteerConflictDetail`（当前实际内容），并在 docstring 中标注 "closed union; 新增 error detail 类型时需扩展此别名"。或者在后续 phase 中统一处理。
- **修复风险（低）**: 仅改 docstring 或类型注解。
- **严重程度（低）**: 不影响当前 correctness，但影响 API 可演进性。

### F7-未修复-低-不可达的 RuntimeError 防御性检查

- **入口/函数**: `HostDispatchScheduler._append_compacted_event`、`EngineEventIngestor._append_reactive_compacted_event`
- **文件(行号)**: `dayu/host/dispatch.py:1264`, `dayu/host/engine_ingest.py:1521`
- **输入场景**: N/A — 代码路径在上游已被保护，永远不可达
- **实际分支**: `if self._compact_artifact_root is None: raise RuntimeError(...)`
- **预期行为**: 若上游保护逻辑正确，此检查不可达；应移除或改为 `assert`
- **实际行为**: 死代码。上游 `_execute_proactive_compaction`（dispatch.py:923-925）和 `_execute_reactive_compaction`（engine_ingest.py:1390-1399）已在调用前检查 `compactor is None or artifact_root is None`
- **直接证据**:
  - `dispatch.py:923-925`: `if compactor is None: return None` — 早返回
  - `dispatch.py:1264`: `if ... is None: raise RuntimeError(...)` — 不可达
  - `engine_ingest.py:1392-1399`: 已检查 `compactor is None or artifact_root is None`
  - `engine_ingest.py:1521`: `if ... is None: raise RuntimeError(...)` — 不可达
- **影响**: 死代码增加维护负担，可能误导后续开发者以为此路径可达。
- **建议改法和验证点**: 移除或改为 `assert`。不影响任何功能。
- **修复风险（低）**: 仅移除死代码。
- **严重程度（低）**: 代码清洁度问题，无功能影响。

---

## Open Questions

1. **`max_compaction_attempts_per_operation` 默认值为 1 是否过于保守？** 当前 `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 1` 意味着不做 semantic repair retry。LLM compactor 的 `_candidate_from_summary` 中有硬编码的 fallback 值（如 `open_questions=("continue-current-run",)`），若 LLM 返回空 summary，第一次且唯一的一次 attempt 就会失败。真实 multi-turn 场景中是否需要至少一次 repair attempt？当前默认值与"bounded semantic repair"的设计意图（host-owned-compactor-plan.md §3.6）有张力。

2. **`engine_ingest.py` sync `ingest()` 方法是否应被废弃？** sync `ingest()` 在遇到 reactive compaction 时直接 `raise RuntimeError`（engine_ingest.py:498），强制调用方使用 `ingest_async()`。如果所有真实调用路径都走 async，sync 方法可以考虑标记为内部/废弃。

3. **`_PublicHostHandle.close()` 中 `projection_catchup_port.catch_up_projection()` 是否同步阻塞？** 在 `_PublicHostHandle.close()`（open_host.py:382）中调用 `catch_up_projection()` 是在 async 上下文中执行同步方法。如果该操作涉及 I/O 或耗时较长，会阻塞 event loop。需要确认 `catch_up_projection` 的执行时间在 close 场景下足够短。

4. **`_promotion_drain_task` 和 `_drain_task` 在 close() 中的取消顺序是否最优？** 当前顺序为 drain → promotion → active_handles → active_tasks → lane_controller。如果 drain 循环中持有 lane token，先取消 drain 再取消 promotion 是正确的。但如果 promotion 循环中也有 lane token 依赖，需要确认不会出现死锁。

---

## Residual Risk

1. **真实 provider matrix smoke（S3）长期 skip 风险**：若 MIMO、Gemini、Qwen 的 API key / endpoint 长期不可用，P10.5 success signal 缺少多 provider 验证。当前 S3 smoke 中仅有 deepseek 被 compact smoke 验证，其他 provider 的 public path 正确性完全依赖 deterministic local runner 测试。

2. **真实 compactor smoke（S4）长期 skip 风险**：若 `DEEPSEEK_API_KEY` 在 CI 中不可用，compaction public path 验证完全依赖 fake compactor 集成测试。F1 发现的 fake compactor 预算估算不一致使此风险加剧。

3. **Phase 11 Recovery 依赖当前 close/shutdown 正确性**：`_PublicHostHandle.close()` 的 shutdown 顺序（scheduler → projection → store）在当前无 Recovery 的假设下工作。Phase 11 引入 startup scan / orphan proof 后，close 期间留在 active 队列中的 work 需要被正确处理。

4. **`HostInput` 仍在 public exports 中**：虽然这不是 leakage（`HostInput` 是 `StartRunRequest` 和 `SubmitFollowupRequest` 的共享 envelope），但如果未来 `StartRunRequest` 被完全废弃，`HostInput` 可能需要重新评估其 public 地位。

5. **未覆盖的并发场景**：多个 `open_host` 实例共享同一 durable store 的并发行为未测试。当前设计假设单 opener 单 store，但如果 Service 误用多 opener，行为未定义。

6. **`public_smoke_support.py` 中的内部 API 访问**：`wait_for_diagnostic_event_type_count`（line 1064）和 `_active_wait_id`（line 1430）直接读取 SQLite 数据库，绕过 public read API。这些是测试辅助函数，不进入生产代码，但长期维护中可能诱导其他测试复制此模式。
