# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 fix

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A / S3`。
- Gate：code review fix only。
- Finding 裁决真源：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-controller-adjudication.md`。
- 只修复 controller accepted 的 `S3-CR-F01` 至 `S3-CR-F04`；未执行 re-review，未修改 control doc、既有 implementation/review/adjudication/validation artifacts，未 commit、push 或创建 PR。
- 本 fix 实际修改：`dayu/host/engine_ingest.py`、`tests/host/test_engine_ingest_mapping.py` 与本 artifact。`dayu/host/durable/state.py`、`dayu/host/command.py`、其它 allowed tests 和 README 未在本 fix gate 继续改动。

## 第一性原理与 owner boundary

四项 finding 的动机均成立：

- Attempt terminal 与否由 durable `AttemptStatus` 首次表达并持久化，`terminal_event_id` 只是同事务 row consistency ref；reactive gate 必须消费 `is_terminal_attempt_status`。
- Engine terminal 与 Host worker lifecycle terminal 是两种不同来源事实；两者可以共享 canonical terminal event/status 规划与 durable transaction，但不能共享一个装满互斥 optional 字段的 plan。
- Host lifecycle ingress 负责完整验证 envelope 与 repository rows 的 identity；`run.run_id` 必须显式参与契约。
- terminal payload descriptor、canonical terminal facts、Run/Attempt status 是同一 terminal closeout 的 durable facts。只要 terminal mutation 未更新，当前 transaction 就不能正常 commit 其中任一部分。

修复保持在 semantic owner：`engine_ingest.py` 的 reactive consumer、typed ingress/closeout boundary 与 transaction result mapping；未在 projection、cleanup、展示或兼容读取处补特例。

## S3-CR-F01

### Root cause

`_execute_reactive_compaction` 在 compactor 返回后的 write transaction 中使用 `latest.attempt.terminal_event_id is None` 代理“旧 Attempt 是否已经 terminal”。正常 row shape 下 ref 与 status 一致，但这仍把 row consistency ref 提升成 lifecycle truth，绕过了 `durable.state.is_terminal_attempt_status` owner。

### 具体修复

- reactive post-compaction gate 改为 `not is_terminal_attempt_status(latest.attempt.status)`。
- 不修改 terminal ref 的持久化与 row consistency 校验职责。

### 测试证据

- `test_reactive_compaction_gate_consumes_terminal_attempt_status_truth` 通过 public `ingest_async` reactive path 运行真实 compactor/transaction 流程，记录并控制 owner predicate 对 `AttemptStatus.FAILED` 的判断；predicate 决定不允许 compact commit 时，不写 `CONTEXT_COMPACTED`、不创建 recovery Attempt，Run/Attempt 保持 `RECOVERING/FAILED`。
- `test_context_compaction_requested_none_budget_uses_host_estimator_and_recovers`、`test_reactive_compaction_calls_llm_outside_write_transaction` 等原有 public reactive success path 继续通过，证明成功 recovery 回归未破坏。

### 最终状态

`已修复`。

## S3-CR-F02

### Root cause

原 `_TerminalPlan` 同时承载 Engine-only 的 finish/provider/recovery 字段与 Host-lifecycle-only 的 worker signal/stream/index 字段。虽然调用路径已有 `EngineEventCandidate` 与 `_HostLifecycleCloseoutCandidate`，plan 类型本身仍允许跨来源字段污染，违反 approved S3 typed boundary。

### 具体修复

- 删除混装的 `_TerminalPlan`，拆为：
  - `_EngineTerminalPlan`：只承载 Engine-origin terminal 字段；
  - `_HostLifecycleTerminalPlan`：只承载 Host worker lifecycle terminal 字段；
  - `_TerminalFactPlan`：只承载两类来源真正共享的 canonical Attempt/Run event type、status、reason 与 terminal payload。
- `EngineEventCandidate -> _close_terminal` 只接受 `_EngineTerminalPlan`；`_HostLifecycleCloseoutCandidate -> _close_host_lifecycle_terminal` 只接受 `_HostLifecycleTerminalPlan`。
- `_failed_terminal_fact_plan` 复用 lifecycle owner helper 生成 FAILED canonical facts；未复制 status-to-event mapping，两个 closeout 仍调用同一个 `terminal_closeout_in_transaction`。
- 构造 `TerminalCloseoutInput` 时两条路径显式写各自字段；没有 optional probing、`hasattr/getattr`、compatibility wrapper 或新的 god-bag。

### 测试证据

- `test_terminal_plans_use_lifecycle_event_owner_helpers` 使用 dataclass field contract 断言 Engine plan 与 Host lifecycle plan 的字段集合互不混装，并继续断言两类 plan 的 Attempt/Run event type 都来自 lifecycle owner helper。
- 全仓 `pyright`：`0 errors, 0 warnings, 0 informations`，证明 candidate、plan 与 closeout 签名的静态类型链路成立。
- `_TerminalPlan` source scan 无匹配。

### 最终状态

`已修复`。

## S3-CR-F03

### Root cause

`_validate_host_lifecycle_context` 已检查 session、current attempt、Attempt run/execution 与 dispatch identity，却遗漏 `run.run_id == envelope.run_id`。当前 SQLite `read_run_by_id` 隐含该不变量，但 ingress guard 自身没有完整表达 identity contract，测试 double 或未来 repository 实现可能暴露差异。

### 具体修复

- 在 Host lifecycle ingress identity 条件中显式加入 `run.run_id != envelope.run_id` 拒绝分支。
- 没有抽取新的 validation seam，也没有改变 Engine-origin ingress guard。

### 测试证据

- `test_host_lifecycle_ingress_rejects_mismatched_run_identity` 通过 public `close_clean_eof` path 注入“按 key 命中但 row.run_id 漂移”的 repository test double，断言只写 Host lifecycle diagnostic，不写 `RUN_FAILED`，Run/Attempt 保持 `RUNNING/RUNNING`。

### 最终状态

`已修复`。

## S3-CR-F04

### Root cause 与真实 transaction contract 证据

直接代码证据确认 finding 有效，但需区分 terminal helper 的两个失败阶段：

1. `HostTransactionRunner.run_write` 使用 `BEGIN IMMEDIATE`；operation 正常返回后 commit，任意 `HostDurableError` 或其它 exception 都 rollback，after-commit 只在 commit 成功后执行。
2. `PayloadStore.write_sqlite_payload` / `write_sqlite_payload` 在调用方 transaction 中先写 `host_sqlite_payloads` 与 `payload_descriptors`。
3. `terminal_closeout_in_transaction` 在 append terminal events 前遇到 precondition failure 时正常返回 `NOT_FOUND/INVALID_STATE`；原 `_close_terminal` / `_close_host_lifecycle_terminal` 把它映射为 `REJECTED` 后让 transaction 正常 commit，因此会提交先写 payload descriptor。
4. terminal events 已 append 后，Attempt/Run mutation 非 `UPDATED` 会由 `_require_attempt_mutation_updated` / `_require_run_mutation_updated` 抛 `HostDurableError`，该阶段原本已经会 rollback；不能把这条已有保障误写成“所有 non-UPDATED 都正常返回”。

因此 F04 不是证据失效；真实缺口是 terminal helper **正常返回非 `UPDATED`** 时调用方没有中止 transaction。

### 具体修复

- 新增最小私有 typed exception `_TerminalCloseoutRollback`。
- Engine-origin 与 Host lifecycle closeout 在 `terminal_closeout_in_transaction` 返回任何非 `UPDATED` status 时抛出该 exception，强制当前真实 SQLite transaction rollback。
- `_ingest_before_reactive_compaction` 与 `_close_worker_lifecycle` 只在 transaction 外捕获该 exception，并统一映射回原有 `REJECTED / events=() / terminal_closeout=True / terminal_closeout_precondition_failed` contract。
- accepted、complete duplicate 与 ordinary rejected/diagnostic contract 保持；rollback 后不触发 queue promotion。
- 未增加 cleanup、展示过滤、兼容读取，也未修改 shared durable transition helper。

### 测试证据

- 真实 invalid-state 路径：
  - `test_engine_terminal_invalid_state_rolls_back_payload_and_events`；
  - `test_host_lifecycle_invalid_state_rolls_back_payload_and_events`。
  两者构造 row 可解码但不满足 shared terminal precondition 的 `Run WAITING / Attempt RUNNING` adversarial state，分别通过 public Engine `FINAL_ANSWER` 与 public Host lifecycle closeout 进入真实 `terminal_closeout_in_transaction`，得到真实 `INVALID_STATE`。
- CAS-lost 路径：
  - `test_engine_terminal_cas_lost_rolls_back_real_payload_repository`；
  - `test_host_lifecycle_cas_lost_rolls_back_real_payload_repository`。
  两者只在 terminal helper result 点注入 `CAS_LOST`，payload 仍由生产 `_write_*_terminal_payload -> PayloadStore.write_sqlite_payload` 写入真实 SQLite transaction；随后私有 exception 触发真实 runner rollback。
- 四条测试都比较 operation 前后的 `host_sqlite_payloads` row count、`payload_descriptors` row count、EventLog row count、Run status 与 Attempt status，证明无 orphan payload、无错误 event、无 status mutation；结果仍为稳定 `REJECTED`。
- 原有 Engine accepted、Host lifecycle accepted、duplicate replay 测试继续通过。

### 最终状态

`已修复`。

## Validation

```text
pytest tests/host/test_engine_ingest_mapping.py -q
84 passed in 1.12s

pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py tests/host/test_state_schema.py -q
214 passed in 2.36s

pytest tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q
88 passed in 1.93s

pyright
0 errors, 0 warnings, 0 informations

git diff --check
PASS
```

Source scans：

- synthetic EngineEvent：`EngineEvent(`、`type=EngineEventType.RUN_FAILED`、`RunFailedData(` 构造 scan 无匹配。
- terminal-ref routing：`engine_ingest.py` 的 late Engine/Host routing 与 reactive gate 都只调用 `is_terminal_run_status` / `is_terminal_attempt_status`；剩余 `attempt_terminal_event_id` / `run_terminal_event_id` 仅是 shared terminal transaction 输入和 deterministic event-id helper，不参与状态分类。
- direct-cancel duplicate predicate：`command.py` 只 import/call `is_dispatch_record_direct_cancelable`；worker-accepted nullable 字段组合仍只由 `durable.state` owner、row codec 与 CAS 实现消费。
- terminal event constant source：`run_transition.py` 与 `engine_ingest.py` 中 `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)` scan 无匹配。
- legacy mixed plan：`_TerminalPlan` scan 无匹配。

## Propagation audit

### Engine-origin terminal

真实 `EngineEvent` -> `EngineEventCandidate` -> `_EngineTerminalPlan` -> `_TerminalFactPlan`（lifecycle owner helper 派生 event type/status）-> 当前 transaction 写 terminal payload -> shared `terminal_closeout_in_transaction` -> Attempt/Run canonical facts与 status rows -> commit 后 projection/read model/outbox/memory 消费 committed truth。

若 shared terminal helper 返回非 `UPDATED`，`_TerminalCloseoutRollback` 回滚 payload、EventLog 与所有状态写入，事务外只返回 rejected result；没有可供下游错误投影的 orphan fact。

### Host lifecycle terminal

worker EOF/crash -> `_HostLifecycleCloseoutCandidate` -> 完整 envelope/repository identity validation -> `_HostLifecycleTerminalPlan` -> `_TerminalFactPlan` -> Host lifecycle payload/identity -> shared `terminal_closeout_in_transaction` -> Attempt/Run canonical facts与 status rows -> committed projections。

Host lifecycle plan 不含 Engine finish/provider/correlation/unsupported-owner 字段，canonical payload/source/ref 仍保持 `host.worker_lifecycle` 真源；non-UPDATED 时与 Engine path 使用同一 rollback/result contract。

### Reactive compaction

Engine provider overflow -> reactive request fact -> old Attempt FAILED + Run RECOVERING -> transaction 外 compactor -> fresh durable context -> `is_terminal_attempt_status(latest.attempt.status)` gate -> compact accepted/fallback/failure -> recovery Attempt 或 fail closed。terminal refs只保留 row consistency 与 canonical refs，不参与 gate truth。

### Identity、projection 与 LLM-facing consistency

Host lifecycle ingress 同时校验 session id、run id、current attempt、Attempt run/execution 与 dispatch identity。只有完整 identity 匹配的来源才能进入 terminal transaction。diagnostic 仍是 non-canonical Host lifecycle diagnostic，不进入 terminal projection或 LLM-facing memory；本 fix 未新增或修改任何 LLM-facing 文本 producer。

## README decision

- `dayu/host/README.md`：本 fix gate 不更新。现有 S3 implementation 已写明 EngineEvent 与 worker lifecycle 是两条 typed path，并共享 durable terminal transaction；本次只是让 private plan 类型与 transaction failure atomicity符合该稳定边界，没有新增开发者公共接口、状态或执行路径。
- `tests/README.md`：不更新。新增断言仍属于现有 Engine ingest、durable transaction rollback、EventLog/payload foundation 与 Context Governance reactive 类别；没有新增测试层级、命令类别或维护规则。
- 根 README 与 `dayu/README.md`：不触发。没有用户可见入口、命令、安装流程或分层装配变化。

## Residual risks / uncovered areas

- 跨进程 Engine terminal 与 Host lifecycle terminal 的高并发 stress 未在本 fix 新增；当前正确性由 `BEGIN IMMEDIATE`、EventLog unique identity、shared terminal CAS 与本次 non-UPDATED rollback 共同保证。分类：`assigned to later work unit`，沿用 production stress / EventLog hardening owner；不阻塞本 S3 fix。
- terminal payload 当前固定使用 SQLite payload repository，因此本次 rollback 覆盖 payload row 与 descriptor。外部 artifact 先发布、SQLite 后失败的通用 cleanup 语义不由本路径触发。分类：`covered by existing design/non-goal`。
- 非 terminal EventLog 常量统一仍属于 P3-J。分类：`assigned to later work unit`。
- P3-B final answer / outbox continuity 未触碰。分类：`covered by later approved slice`。
- 没有 unclassified residual risk、blocking open question 或 deferred accepted finding。

## Completion

- `S3-CR-F01`：已修复。
- `S3-CR-F02`：已修复。
- `S3-CR-F03`：已修复。
- `S3-CR-F04`：已修复。
- Fix gate status：completed。
- Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-fix-codex.md`。
- Next action：停止，等待 controller re-review。
