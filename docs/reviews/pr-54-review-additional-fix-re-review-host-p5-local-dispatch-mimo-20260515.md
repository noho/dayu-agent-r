# PR 54 Additional Fix Re-Review

## Verdict

**PASS** -- A1-A10 accepted fix items全部正确落地，未实现 rejected/deferred 项，可进入 controller final adjudication。

## Scope

- Mode: Current Changes re-review
- Branch: `feat/host-phase5-local-dispatch`
- Base: `main` (committed HEAD)
- Reviewer: AgentMiMo
- Source controller artifact: `docs/reviews/pr-54-review-additional-controller-adjudication-20260515.md`
- Source fix artifact: `docs/reviews/pr-54-review-additional-fix-host-p5-local-dispatch-codex-20260515.md`
- Source review artifacts:
  - `docs/reviews/pr-54-review-20260515-1221.md`
  - `docs/reviews/pr-54-review-20260515-1224.md`
- Included scope: 8 production files, 7 test files, 2 README files (all unstaged workspace changes)
- Output file: `docs/reviews/pr-54-review-additional-fix-re-review-host-p5-local-dispatch-mimo-20260515.md`

## Accepted Fix Coverage A1-A10

### A1 `_consume_worker_events` pre-event exception 资源释放 -- PASS

- **修复内容**: `dispatch.py` 中 `LocalEngineEnvelope` 构造、`EngineEventIngestor` 构造、`worker_event_index`/`terminal_seen`/`last_accepted_event_id` 初始化从 try 块前移入 try 块内。
- **覆盖验证**: `test_consume_pre_event_exception_releases_lane_and_unregisters` 测试注入 `_FlakyLocalWorkerIdHandle`，验证 pre-event 异常后 lane 仍被释放、active worker 被注销。
- **资源释放链**: finally 块执行 `_active_handles.discard(handle)` + `_safe_close_worker_handle(handle)` + `_safe_release_lane_token(token)`。pre-event 异常现在也进入此 finally。
- **无遗留风险**: 修复仅移动代码位置，不改变正常路径控制流。

### A2 preview event type + data 校验 -- PASS

- **修复内容**: `engine_ingest.py` 中 `_is_preview_event` 从 `event.type in {set}` 改为对 10 种 preview type 逐一做 `event.type == X and isinstance(event.data, XData)` 双重校验。
- **覆盖验证**: `test_preview_event_rejects_missing_or_wrong_data` 参数化测试覆盖 None data 和错误 data 类型；`test_preview_event_accepts_matching_type_and_data` 覆盖合法 preview。
- **误拒风险**: 无。合法 preview event 的 type 与 data 类型是 Engine 契约强绑定，isinstance 精确匹配不会误拒。
- **与 terminal 分支一致性**: 与 `FINAL_ANSWER + isinstance FinalAnswerData`（L383）、`RUN_FAILED + isinstance RunFailedData`（L391）等已有分支模式完全一致。

### A3 RunInputBuilder 可 dispatch 状态校验 -- PASS

- **修复内容**: `run_input.py` 中 `_validate_snapshot_rows` 新增三条校验：`run.status == RunStatus.RUNNING`、`attempt.status == AttemptStatus.STARTING`、`dispatch_record.status == DispatchRecordStatus.DISPATCHING`。
- **覆盖验证**: `test_current_facts_reject_non_dispatchable_snapshot_state` 参数化测试覆盖 Run/Attempt/Dispatch 三种非可派发状态组合。
- **设计对齐**: 符合 design.md Attempt startup 边界 -- "`Run RUNNING + Attempt STARTING` 是合法组合，表示该用户目标已进入 Host 治理执行态，但执行环境尚未确认接住"。dispatch record `DISPATCHING` 表示已提交 dispatch intent。
- **不把 dispatch record 当 owner truth**: 校验仅用于防御性前置检查，不改变 dispatch record 的诊断定位。校验失败抛 `HostDurableError`，不写入任何状态。

### A4 `AttemptDispatchSnapshot.__post_init__` cancellation_token 校验 -- PASS

- **修复内容**: `api.py` 新增 `isinstance(self.cancellation_token, CancellationToken)` 检查，不匹配时抛 `TypeError`。
- **覆盖验证**: `test_attempt_dispatch_snapshot_rejects_none_cancellation_token` 测试传入 None token 时抛 `TypeError`。
- **校验方式**: `CancellationToken` 是 `@runtime_checkable` Protocol，`isinstance` 检查 Protocol 方法存在性。TypeError 符合 `HostLocalExecutionOptions.__post_init__` 对 `worker_factory` 的已有模式。

### A5 `_run_mutation_result_for_active` 终态 CAS_LOST -- PASS

- **修复内容**: `state.py` 中 `_run_mutation_result_for_active` 的 CAS_LOST 判断条件从 `latest.status in (RUNNING, WAITING, CANCELLING, RECOVERING)` 扩展为 `... or _is_terminal_run_status(latest.status)`。
- **覆盖验证**: `test_terminal_run_row_reports_cas_lost_for_latest_terminal_status` 测试 SUCCEEDED/FAILED/CANCELLED/LOST 四种终态均返回 `CAS_LOST`。
- **逻辑正确**: 两个并发事务同时 terminal 同一 Run 时，第二个 rowcount=0 且 latest 已为终态，语义是 CAS 丢失而非无效状态。

### A6 `_validate_terminal_input` ValueError 包装 -- PASS

- **修复内容**: `run_transition.py` 中 `_validate_terminal_input` 用 `try/except ValueError` 包裹 `_attempt_terminal_event_type` 和 `_run_terminal_event_type` 调用，转抛 `HostDurableError`。
- **覆盖验证**: `test_terminal_closeout_wraps_terminal_event_type_errors` 测试非法终态组合（如 CANCELLED）抛 `HostDurableError`。
- **异常链保留**: `raise HostDurableError(str(exc)) from exc` 保留原始 ValueError 作为 cause。

### A7 `HostDispatchScheduler.close()` handle 关闭归属 -- PASS

- **修复内容**: `dispatch.py` 中 `close()` 方法移除 `_safe_close_worker_handle(handle)` 调用，只保留 `_safe_cancel_worker_handle(handle, "scheduler_close")`。handle close 由 `_consume_worker_events` 的 finally 块负责。
- **覆盖验证**: `test_scheduler_close_lets_active_task_own_handle_close` 使用 `_CloseCountingHandle` 验证 handle 只被 close 一次（由 active task finally 执行），scheduler close 不二次 close。
- **资源所有权清晰**: scheduler 负责 cancel signal，consume task 负责自身资源清理。单一所有者，无 double-close。

### A8 `_DefaultLocalWorkerHandle` close 语义 -- PASS

- **修复内容**: `local_proxy.py` 新增 `_closed` 标志；`close()` 幂等（已关闭时 return）；`events()` 在已关闭时抛 `RuntimeError`；`close()` 清空 `self._events = None`。
- **覆盖验证**: `test_default_local_worker_close_is_idempotent_and_events_fail_after_close` 验证 close-after-close 为 no-op、events-after-close 抛 `RuntimeError`。
- **实现细节**: `close()` 中 `events = self._events` 先捕获引用，再置 `None`/`_closed=True`，最后调用 `aclose()`。若 `aclose()` 抛异常，handle 仍标记为已关闭，异常正常传播。行为合理。

### A9 LocalProxy 真实 Engine 边界错误路径测试 -- PASS

- **修复内容**: `test_local_proxy_engine_ingest.py` 新增 3 个测试覆盖 stream 异常传播、空流、close 幂等。`test_dispatch_scheduler.py` 新增 `test_scheduler_with_default_local_proxy_stream_error_closes_lost` 使用真实 `DefaultLocalEngineWorkerFactory` 验证 stream error 映射为 LOST。
- **关键验证**: scheduler 经真实 proxy 的 stream error -> LOST closeout 路径被端到端覆盖，不再依赖 `_ScriptedLocalWorker` 绕过。

### A10 Host import boundary 禁止 dayu.config -- PASS

- **修复内容**: `test_import_boundary.py` 中 `HOST_FORBIDDEN_PREFIXES` 新增 `"dayu.config"`，docstring 同步更新。
- **架构对齐**: Phase 5 design 明确 RunInputBuilder / Host 不得隐式读取全局配置或环境变量。`dayu.config` 若承载业务配置（prompt 模板、财报工具 schema），Host 层不应依赖。

## Rejected Items 确认 -- 均未实现

| 拒绝项 | 确认状态 | 证据 |
| --- | --- | --- |
| active cancel dispatch record cancelled | 未实现 | `dispatch.py` diff 无 active cancel 流程中标记 dispatch record 为 cancelled 的逻辑；`cancel_starting_dispatch_record_row` 仅用于 starting 阶段 |
| 非 terminal duplicate precheck | 未实现 | grep `duplicate.*precheck` / `precheck.*duplicate` 无匹配；`_duplicate_terminal_event_ids` 对非 terminal 仍返回空 tuple |
| token-cancel build short-circuit | 未实现 | `run_input.py` diff 仅添加状态校验，无 `cancellation_token.is_cancelled()` 短路逻辑 |

## Deferred Items 确认 -- 均未实现

| Deferred 项 | 确认状态 |
| --- | --- |
| worker 收到 cancel 后长期不产出 terminal (watchdog) | 未实现 |
| `_drain_loop` 非预期异常结构化日志 | 未实现 |
| terminal event sub-index plan 去重结构化 | 未实现 |
| scheduler 并发 lane 竞争专项测试 | 未实现 |
| command.py active cancel port 抽象 | 未实现 |
| 多 RUN_CANCELLING 与具体 cancel request 关联 | 未实现 |
| duplicate helper / payload helper 抽取 | 未实现 |
| `admission.py` / `run_input.py` EventLogStore DI 一致性 | 未实现 |

## Non-blocking Observations

1. **A8 close 顺序**: `_DefaultLocalWorkerHandle.close()` 在调用 `aclose()` 前已将 `self._events = None`。若 `aclose()` 抛异常且调用方 catch 后再次调用 `close()`，第二次 `close()` 因 `_closed=True` 直接 return，不会再尝试关闭 generator。行为正确，但依赖 `_closed` 标志而非 `_events is None` 来做幂等判断，设计意图需保持一致。

2. **A5 `_is_terminal_run_status` 复用**: `_run_mutation_result_for_active` 现在对非 active 非终态的未知状态（如未来新增的状态枚举值）仍返回 `INVALID_STATE`，这是安全的默认行为。

3. **A2 isinstance 与 event type 耦合**: 10 种 preview event 的 type-data 映射硬编码在 `_is_preview_event` 中。若 Engine 契约新增 preview type，需同步修改此处。与已有 terminal 分支（L383/L391/L423/L469）的模式一致，当前可接受。

## Residual Risks

| 风险 | Owner | 说明 |
| --- | --- | --- |
| active cancel watchdog 未实现 | Phase 11 lifecycle / recovery hardening | worker 收到 cancel 后长期不产出 terminal 时无超时收口 |
| `_drain_loop` 异常不可观测 | 后续 observability / lifecycle cleanup | drain_once 异常静默退出，wake_dispatch 可重建但中间唤醒可能丢失 |
| scheduler 并发 lane 竞争未测试 | 后续 scheduler hardening | 当前 scheduler drain 是单队列串行推进，runtime lane 已有容量测试 |
| command.py cancel port 耦合 | Phase 11 / composition lifecycle | DEFAULT_ACTIVE_WORKER_REGISTRY 模块级单例假设单 scheduler |
| EventLog 幂等性依赖 | 已确认 | EventLog append 以 event_id 唯一为 identity；非 terminal event 的幂等由 EventLog 层保证 |

## 结论

A1-A10 全部正确落地，修复范围严格限于 accepted items，未引入 rejected/deferred 项。测试覆盖充分，生产代码变更低风险。可进入 controller final adjudication。
