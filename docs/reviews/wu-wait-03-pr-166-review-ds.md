# Code Review

## Scope

- Mode: PR
- PR: #166 — WU-WAIT-03: external wait lifecycle abandon target
- Repo: noho/dayu-agent-r
- Head: phase/wu-wait-03-issue-92
- Base: main
- URL: https://github.com/noho/dayu-agent-r/pull/166
- Author: noho
- State: OPEN, Draft
- Checks: no checks reported on branch (consistent with repo pattern: PRs #165/#163/#162 also reported no checks)
- Reviews: 无
- Output file: docs/reviews/wu-wait-03-pr-166-review-ds.md
- Included scope: PR diff against main — dayu/host/wait_adapter.py, dayu/host/durable/state.py, dayu/host/durable/schema.py, dayu/fins/ingestion/wait_adapter.py, dayu/host/README.md, tests/README.md, tests/host/test_wait_adapter_polling.py, tests/host/test_wait_poller_runtime.py, tests/host/test_durable_schema.py, tests/host/test_wait_record_state.py, tests/host/test_open_host_runtime.py, tests/fins/test_fins_ingestion_tools.py, tests/fins/test_fins_ingestion_runtime.py, docs/host/issues-implementation-control.md, docs/host/wu-wait-03-external-job-lifecycle-plan.md, docs/reviews/wu-wait-03-*
- Excluded scope: 无
- Review focus: PR diff 是否完整实现 WU-WAIT-03 accepted plan，且无 state machine / durable schema / Host/Fins boundary regression；PR body 是否准确描述变更/验证/review artifacts/residual risk 并含 Closes #92；checks/reviews 状态是否阻塞 final closeout；是否有需要当前修复的 correctness/testing/README/doc sync 或 residual-risk owner 问题
- Parallel review coverage: 无（按 deepreview 指令不派 subagents）

## Design Doc & Plan Alignment

- Plan artifact: `docs/host/wu-wait-03-external-job-lifecycle-plan.md` — accepted plan commit `6be72997`
- Host design alignment: `docs/host/design.md` 确认 Host 是 Session/Run/Attempt/EventLog/wait record 治理真源；cancel command transaction 不在事务内执行 provider I/O；resolve_wait 是等待结果唯一治理入口；wait poller 只能调用 resolve_wait 或更新自身 poll/backoff 诊断 state。PR diff 未修改 `cancel_waiting_run_in_transaction(...)`、`cancel_run(...)`、`cancel_session_runs(...)` 或 `resolve_wait(...)`，Host cancellation correctness 保持独立于 provider lifecycle 结果。✅
- Engine design alignment: `docs/engine/design.md` 确认 Engine 不拥有 wait record、不轮询 job、不托管外部长事务生命周期。PR diff 未修改 Engine 公共入口或 contract。✅
- Plan completeness: PR diff 完整实现了 accepted plan 的 Slice 1（Host lifecycle contract and poller diagnostics）与 Slice 2（Fins adapter/runtime mapping and provider-focused tests），无 plan deviation。

## Implementation Trace

### Slice 1: Host Lifecycle Contract And Poller Diagnostics

1. `dayu/host/wait_adapter.py` — 新增 typed lifecycle dataclasses 与 union:
   - `WaitExternalJobLifecycleAction(StrEnum)`: CANCEL/REVOKE/ABANDON ✅
   - `WaitExternalJobLifecycleApplied(action, message)` with `__post_init__` validation ✅
   - `WaitExternalJobLifecycleUnsupported(reason)` with `__post_init__` validation ✅
   - `WaitExternalJobLifecycleNoop(reason)` with `__post_init__` validation ✅
   - `WaitExternalJobLifecycleResult` TypeAlias union ✅
   - `__all__` 导出新增类型 ✅
   - `WaitPollAdapter.abandon_wait(...)` Protocol 签名更新为 `-> WaitExternalJobLifecycleResult` ✅
   - 新增 `_last_outcome_for_lifecycle_result()` 映射 helper，含 TypeError fallback ✅
   - `_MarkWaitRecordAbandonedOperation` 新增 `last_outcome` 字段 ✅
   - `_abandon_cancelled_wait(...)` 消费 typed lifecycle result：applied → ABANDONED, unsupported → ABANDON_UNSUPPORTED, noop → ABANDON_NOOP, exception → ABANDON_ERROR backoff（未修改）✅

2. `dayu/host/durable/state.py` — 新增 enum 值与标记参数化:
   - `WaitPollLastOutcome.ABANDON_UNSUPPORTED`、`WaitPollLastOutcome.ABANDON_NOOP` ✅
   - `mark_wait_record_poll_abandoned(...)` 新增 keyword-only `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED` ✅
   - 参数校验：`isinstance(last_outcome, WaitPollLastOutcome)` ✅
   - CAS SQL 使用 `serialize_wait_poll_last_outcome(last_outcome)` 替代硬编码 ✅
   - 现有调用方通过默认值兼容 ✅

3. `dayu/host/durable/schema.py` — schema version 18→19，CHECK constraint 新增 `abandon_unsupported`/`abandon_noop` ✅

4. `dayu/host/README.md` — 新增 wait lifecycle contract 段落，描述 typed result 三类封闭结果与 poller durable outcome 映射 ✅

### Slice 2: Fins Adapter/Runtime Mapping

5. `dayu/fins/ingestion/wait_adapter.py` — Fins adapter abandon_wait 返回 typed result:
   - 无效 observation handle → `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")` ✅
   - cancel_observation 返回 LOST snapshot → `WaitExternalJobLifecycleNoop(reason="observation_missing")` ✅
   - `PERMANENT_NOT_FOUND` error → `WaitExternalJobLifecycleNoop(reason="observation_missing")` ✅
   - 其他非 transient error → `WaitExternalJobLifecycleNoop(reason="observation_error:<kind>")` ✅
   - `TRANSIENT_UNAVAILABLE` → re-raise 给 Host poller 退避重试 ✅
   - 成功路径 → `WaitExternalJobLifecycleApplied(action=ABANDON, message=...)` ✅
   - `_observation_error_reason()` helper 格式为 `observation_error:<error_kind.value>` ✅

### Test Coverage

6. Host tests (`tests/host/test_wait_adapter_polling.py`):
   - `test_cancelled_poll_wait_is_abandoned_once_without_resolve` 增强断言: lifecycle result type/action、`poll_last_outcome=ABANDONED` ✅
   - 新增 `test_cancelled_poll_wait_unsupported_marks_terminal_without_resolve` ✅
   - 新增 `test_cancelled_poll_wait_noop_marks_terminal_without_resolve` ✅
   - 新增 `test_cancelled_poll_wait_missing_adapter_stays_retryable` ✅
   - 新增 `test_terminal_abandon_cas_conflict_leaves_cancelled_wait_retryable` (parametrized unsupported/noop) ✅
   - 新增 `_StaticLifecycleAdapter`、`_NoResolveResolver`、`_poller_with_resolver` 测试基础设施 ✅
   - `_AbandonClaimStealingAdapter` 扩展支持自定义 `lifecycle_result` ✅
   - 已有 `test_cancelled_abandon_success_marks_abandoned_when_close_gate_closes` 新增 `poll_last_outcome` 断言 ✅
   - `test_late_result_after_cancel_writes_bounded_diagnostic` 未修改 ✅

7. State/schema tests:
   - `test_wait_poll_terminal_outcome_codecs_roundtrip_new_values` — serialize/deserialize roundtrip for ABANDON_UNSUPPORTED/ABANDON_NOOP ✅
   - `test_poll_abandon_success_marks_row_and_clears_claim` parametrized over all three terminal outcomes ✅
   - `test_host_schema_version_is_query_index_version` 断言更新为 19 ✅
   - `test_wait_record_table_and_indexes_are_created` 新增 CHECK constraint 字符串断言 ✅

8. Fins tests (`tests/fins/test_fins_ingestion_tools.py`):
   - `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation` 增强断言 typed result ✅
   - `test_fins_wait_poll_adapter_abandon_corrupt_token_is_noop` 增强断言 typed noop ✅
   - 新增 `test_fins_wait_poll_adapter_abandon_missing_observation_is_noop` ✅
   - 新增 `test_fins_wait_poll_adapter_abandon_lost_snapshot_is_noop` ✅
   - 新增 `test_fins_wait_poll_adapter_abandon_non_transient_error_is_noop` (abandon 侧) ✅
   - 新增 `test_fins_wait_poll_adapter_abandon_cancel_non_transient_error_is_noop` (cancel 侧) ✅
   - 新增 `test_fins_wait_poll_adapter_abandon_transient_unavailable_re_raises` ✅
   - `_FakeObservationRuntime` 扩展 `cancel_errors`/`abandon_errors` 注入能力 ✅

9. Fins runtime tests (`tests/fins/test_fins_ingestion_runtime.py`):
   - 新增 `test_abandon_cancelled_prepared_observation_releases_handle_before_activation` ✅
   - 新增 `test_abandon_submitted_observation_cancels_and_keeps_storage_artifacts` — 覆盖 submitted observation abandon 后协作式取消并保留仓储产物 ✅
   - `_BlockingArtifactUploadRunner` 测试 helper ✅

10. Other test updates:
    - `tests/host/test_open_host_runtime.py`: `_ReadyPollAdapter.abandon_wait` 签名更新，raise AssertionError 作为防御 guard ✅
    - `tests/host/test_wait_poller_runtime.py`: `_SequenceAdapter`/`_BlockingReadyAdapter` abandon_wait 签名更新返回 applied result ✅

### README Sync

11. `dayu/host/README.md` — 新增 wait lifecycle contract 段落 ✅
12. `tests/README.md` — 更新 Host wait 覆盖描述（新增 lifecycle outcome/schema 描述）与 Fins 覆盖描述（新增 observation cancel/abandon 分支） ✅

### Control Doc Update

13. `docs/host/issues-implementation-control.md` — 顶层状态表 gate 从 final-closeout-pass 更新为 draft-PR-pass，WU-WAIT-03 从 pending 更新为 draft-PR-pass ✅
14. 新增 WU-WAIT-03 plan review gate 约束 section ✅

## State Machine / Boundary Verification

- **cancel_waiting_run_in_transaction(...)**: 未修改 ✅
- **cancel_run / cancel_session_runs**: 未修改；返回来 RunStatus.CANCELLED 路径不含 provider I/O ✅
- **resolve_wait(...)**: 未修改；仍是 poll/callback/manual 等待结果唯一治理入口；late-result rejection 不变 ✅
- **poller cancelled wait path**: lifecycle result -> _last_outcome_for_lifecycle_result -> _MarkWaitRecordAbandonedOperation CAS write -> terminal poll diagnostic or backoff retry ✅
- **Host/Fins boundary**: Fins adapter 只返回 typed lifecycle result，不直接写 Host EventLog/wait record；Host poller 只通过 CAS 写 poll diagnostic field，不写 Run/Attempt terminal truth ✅
- **Schema safety**: CHECK constraint 扩展（additive），schema version 18→19，无 table/column 变更 ✅
- **No new runtime/watchdog**: 复用现有 WaitPoller/WaitPollerSupervisor ✅
- **No Engine contract change**: Engine public model 未修改 ✅

## Adversarial Failure Pass

- **缺失 adapter**: cancelled wait 缺失 adapter → MISSING_ADAPTER backoff retry，不 crash ✅
- **Adapter 异常**: 任意 Exception → ABANDON_ERROR backoff retry ✅
- **CAS 冲突**: applied/unsupported/noop 终态标记 CAS 冲突 → claim_conflicts 计数，wait 保持 retryable，不丢失 ✅
- **Close gate during abandon**: lifecycle_gate 关闭 → SHUTDOWN_SKIPPED backoff ✅
- **Fins transient unavailable**: TRANSIENT_UNAVAILABLE re-raise → Host poller ABANDON_ERROR retry ✅
- **Fins non-transient error**: cancel/abandon 非临时错误 → noop with typed reason，不以 exception 逃逸 ✅
- **Fins invalid handle**: 无 valid observation handle → noop，不调用 runtime ✅
- **Fins LOST observation**: cancel_observation 返回 LOST → noop("observation_missing")，不调用 abandon_observation ✅
- **Type guard**: `_last_outcome_for_lifecycle_result` 对未知 type raise TypeError（fail-loud）✅
- **协程取消**: prepared observation abandon 后 activate 不提交后台操作 ✅
- **协作式取消**: submitted observation abandon 触发协作式取消并保留仓储产物 ✅

## Findings

### 01-未修复-低-control-doc-WU-WAIT-03-detailed-section-stale-gate-text

- **入口/函数**: `docs/host/issues-implementation-control.md` WU-WAIT-03 detailed status section
- **文件(行号)**: `docs/host/issues-implementation-control.md:265`
- **输入场景**: PR review gate 已进入 draft-PR-pass，但 detailed section 末尾仍描述前一个 gate
- **实际分支**: 该 section（始于 line 261 `## WU-WAIT-03 External Job Physical Cancel / Revoke / Abandon`）的 `### 状态` 段落末尾仍为 "Current gate is Slice 2 code review;不得 fix、commit、push、create PR、close issue、request reviewers 或 merge。" 且未包含 Aggregate deepreview、Aggregate fix、Aggregate re-review、Accepted aggregate commit 与 Draft PR #166 创建记录
- **预期行为**: detailed section 状态段落末尾应更新为 "Current gate is draft-PR-pass"，或包含完整的 aggregate deepreview 至 draft PR 创建历史
- **实际行为**: 段落末尾 gate 文本停留在 Slice 2 code review，与顶层状态表（line 158 `gate: draft-PR-pass`）和 WU-WAIT-03 汇总行（line 256 `draft-PR-pass`）不一致
- **直接证据**: `git show phase/wu-wait-03-issue-92:docs/host/issues-implementation-control.md | sed -n '260,300p'` 输出显示 line 265 末尾为 "Current gate is Slice 2 code review;不得 fix、commit、push、create PR、close issue、request reviewers 或 merge。"；同一文件 line 1725 的另一个 WU-WAIT-03 引用 section 已正确更新为 "Current gate is draft-PR-pass."
- **影响**: 读者可能依据 stale gate 限制判断当前 gate 不可进入 PR review，造成操作混淆；对生产代码正确性无影响
- **建议改法和验证点**: 更新 line 265 的 gate 文本为 "Current gate is draft-PR-pass"，补充 Aggregate deepreview、Aggregate fix、Aggregate re-review、Accepted aggregate commit 与 Draft PR #166 创建记录（可参照 line 1725 处的完整历史）；`grep -n "Slice 2 code review" docs/host/issues-implementation-control.md` 确认不再匹配 WU-WAIT-03 detailed section
- **修复风险（低）**: 纯文档文本更新，不涉及生产代码或测试
- **严重程度（低）**: 文档一致性问题，不影响代码正确性、测试或部署

## Open Questions

无。

## Residual Risk

- Provider-specific physical cancel 支持：归 provider-specific Fins/source adapter owners，Host 已表达 Unsupported 终态
- Poller-disabled deployments：外部 lifecycle 动作不会执行，归 Service/composition deployment 与 WU-WAIT-04
- Fins cooperative cancellation：只请求协作式取消，不承诺硬抢占，归 Fins provider/runtime owners
- Tool trace projection 扩展：当前使用 wait poll diagnostic 字段（poll_last_outcome），不增加 EventLog canonical facts
- 无 CI checks 覆盖当前 branch：与 repo 历史一致（PR #165/#163/#162 同样无 checks）；PR body 记录了本地验证结果，本 review 已独立复跑并通过全部五组测试与 pyright

## Verdict

**Pass — 可进入 final closeout。**

Blocking findings: **0**。一项低严重度文档一致性 finding（01）不阻塞 final closeout。

Required fixes before final closeout: **无**。Finding 01 建议在 final closeout artifact 中记录修复或在 control doc 下次更新时一并修正。

Verification（独立复跑）:
- `pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q`: **35 passed**
- `pytest tests/host/test_wait_record_state.py tests/host/test_durable_schema.py -q`: **60 passed**
- `pytest tests/host/test_open_host_runtime.py tests/host/test_package_exports.py -q`: **31 passed**
- `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`: **126 passed**, 3 upstream edgar deprecation warnings
- `pyright`: **0 errors, 0 warnings, 0 informations**

PR 完整实现了 WU-WAIT-03 accepted plan，无 state machine / durable schema / Host/Fins boundary regression。PR body 准确描述变更、验证、review artifacts、residual risk，并含 `Closes #92`。checks 状态（无 CI on branch）与 repo 历史一致，不阻塞 final closeout。
