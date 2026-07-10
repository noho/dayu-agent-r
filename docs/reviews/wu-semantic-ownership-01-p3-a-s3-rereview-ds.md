# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 Code Re-Review (AgentDS)

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A / S3`。
- Gate：code re-review。
- Reviewer：AgentDS。
- Fix truth：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-controller-adjudication.md`（4 accepted finding）。
- Fix artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-fix-codex.md`。
- Re-review target：当前 workspace diff（含 fix 与 fix validation）。
- 只 re-review，不修改生产代码/测试/README/control doc，不 commit/push/PR。

## Validation summary

```text
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py \
  tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py \
  tests/host/test_run_attempt_transitions.py tests/host/test_state_schema.py -q
214 passed in 2.05s
```

- pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- import cycle：`import-ok`。

Source scans：

| Scan | Result |
|---|---|
| synthetic `EngineEvent(` / `RunFailedData(` | 无匹配 |
| `_TerminalPlan`（legacy mixed） | 无匹配 |
| `_EVENT_TYPE_(RUN\|ATTEMPT)_(SUCCEEDED\|FAILED\|CANCELLED\|LOST)` | 无匹配 |
| `hasattr` / `getattr` seam | 无匹配 |
| `terminal_event_id is None`（status proxy） | 无匹配 |
| `Any` / `object` 类型注解 | 无匹配 |
| `command.py` 直接读 `worker_accepted_*` nullable refs | 无匹配 |

---

## 逐项 Finding 最终状态

### S3-CR-F01：reactive compaction 使用 terminal refs 代理 Attempt terminal status

**最终状态：已修复。**

直接代码证据：

- `engine_ingest.py:1933-1936`：reactive post-compaction gate 已改为 `not is_terminal_attempt_status(latest.attempt.status)`，不再读取 `latest.attempt.terminal_event_id`。
- `engine_ingest.py` 全文件 `terminal_event_id is None` scan 无匹配，确认无其他 terminal ref 代理 status 的残留分支。
- `is_terminal_attempt_status` import 自 `dayu.host.durable.state`（`engine_ingest.py:182`），消费 durable status owner。

测试证据：

- `test_reactive_compaction_gate_consumes_terminal_attempt_status_truth`（`test_engine_ingest_mapping.py:916-970`）通过 `monkeypatch.setattr` 拦截 `is_terminal_attempt_status`，当 Attempt status 为 `FAILED` 时返回 `False` 强制阻止 compact commit；断言：
  - `AttemptStatus.FAILED in observed_statuses` — 证明 gate 输入是 `AttemptStatus`，不是 `terminal_event_id`。
  - `_event_count(..., CONTEXT_COMPACTED) == 0` — 无 compact 事件被提交。
  - `_attempt_count(...) == 1` — 无 recovery Attempt 被创建。
  - Run/Attempt 保持 `RECOVERING/FAILED`。
- 原有 reactive compaction success path 测试（`test_context_compaction_requested_none_budget_uses_host_estimator_and_recovers`、`test_reactive_compaction_calls_llm_outside_write_transaction` 等）继续通过，确认成功 recovery 路径未被破坏。

check #1 全部满足：
- ✅ reactive compaction public path 真实消费 Attempt status owner（`is_terminal_attempt_status`）。
- ✅ terminal refs 不再充当 lifecycle routing truth。
- ✅ 测试不是只验证 mock 调用而漏掉成功/失败行为——`status_gate` 拦截真实 predicate 调用并控制返回值，同时验证 EventLog、attempt count、status 的 before/after。

---

### S3-CR-F02：_TerminalPlan 同时包含互斥 optional Engine/Host 字段

**最终状态：已修复。**

直接代码证据：

- 旧 `_TerminalPlan` 已删除（`rg "_TerminalPlan"` 无匹配）。
- 新增三个分离 dataclass（`engine_ingest.py:442-481`）：
  - `_TerminalFactPlan`（`engine_ingest.py:443-451`）：只承载两类来源真正共享的 canonical Attempt/Run event type、status、reason 与 terminal payload。
  - `_EngineTerminalPlan`（`engine_ingest.py:454-467`）：只承载 Engine-origin terminal 字段（`finish_reason`、`filtered`、`degraded`、`error_code`、`message`、`provider_request_id`、`client_correlation_id`、`recoverable`、`unsupported_later_owner`）。
  - `_HostLifecycleTerminalPlan`（`engine_ingest.py:470-481`）：只承载 Host worker lifecycle terminal 字段（`error_code`、`message`、`recoverable`、`worker_lifecycle_signal`、`stream_error_code`、`last_observed_worker_event_index`、`last_accepted_event_id`）。
- 两条 closeout path 在构造 `TerminalCloseoutInput` 时显式写各自字段（`engine_ingest.py:1261-1265` Engine path 传 `worker_lifecycle_signal=None` 等；`engine_ingest.py:1349-1354` Host path 传 `engine_event_ref=None, finish_reason=None` 等）。
- 无 optional probing：每条 path 的类型是 `_EngineTerminalPlan` 或 `_HostLifecycleTerminalPlan`，编译期区分。
- 无 `hasattr`/`getattr`、compatibility wrapper、god-bag。

测试证据：

- `test_terminal_plans_use_lifecycle_event_owner_helpers`（`test_engine_ingest_mapping.py:501-576`）：
  - 断言 `_final_answer_plan` / `_run_failed_plan` 返回 `_EngineTerminalPlan`。
  - 断言 `_lost_lifecycle_plan` 返回 `_HostLifecycleTerminalPlan`。
  - 用 `dataclasses.fields` 精确断言 Engine plan 字段集合不含 Host lifecycle 字段（`worker_lifecycle_signal` 等不在 `engine_plan_fields` 中），Host lifecycle plan 字段集合不含 Engine 字段（`finish_reason` 等不在 `host_plan_fields` 中）。
  - 断言两类 plan 的 terminal fact event type 均从 `closeout_attempt_terminal_event_type_for_status` / `run_terminal_event_type_for_status` lifecycle owner helper 派生。

check #2 全部满足：
- ✅ 旧 `_TerminalPlan` 确实消失。
- ✅ `_EngineTerminalPlan` 与 `_HostLifecycleTerminalPlan` 无互斥字段混装，只共享真正 canonical `_TerminalFactPlan`。
- ✅ 无 optional probing、hasattr/getattr、compat wrapper、god-bag。
- ✅ 所有构造函数与 closeout signatures 类型闭合，pyright 零错误确认。

---

### S3-CR-F03：Host lifecycle ingress 缺少 run.run_id 显式校验

**最终状态：已修复。**

直接代码证据：

- `_validate_host_lifecycle_context`（`engine_ingest.py:1167-1176`）identity 条件已包含 `run.run_id != envelope.run_id`，与 `_validate_durable_context` 的 Engine-origin ingress guard 一致：
  ```python
  if (
      run.session_id != envelope.session_id
      or run.run_id != envelope.run_id        # ← 新增
      or run.current_attempt_id != envelope.attempt_id
      or attempt.run_id != envelope.run_id
      or attempt.execution_id != envelope.execution_id
      or dispatch_record.dispatch_record_id != envelope.dispatch_record_id
      or dispatch_record.execution_id != envelope.execution_id
  ):
      return None
  ```
- 没有抽取额外的 validation seam 或兼容 wrapper。

测试证据：

- `test_host_lifecycle_ingress_rejects_mismatched_run_identity`（`test_engine_ingest_mapping.py:3016-3071`）：
  - 通过 `monkeypatch.setattr` 注入 `misatched_read_run` test double：按 `run_id` key 命中正常 Run row，但返回 `replace(run, run_id=f"{run_id}-mismatched")` — row.run_id 漂移。
  - 通过 public `close_clean_eof` 路径注入错 identity，断言：
    - `result.status is REJECTED`，`result.reason == "stale_execution_id"`。
    - 只写 `HOST_LIFECYCLE_DIAGNOSTIC`，不写 `RUN_FAILED`。
    - Run/Attempt 保持 `RUNNING/RUNNING`。
  - repository test double 而非 mock — 真实写入真实 durable store，验证 ingress 在 identity 不匹配时 fail closed。

check #3 全部满足：
- ✅ Host lifecycle run_id guard 在 ingress 生效。
- ✅ test double / public path 测试可信 — 通过替换 `read_run_by_id` 返回错 identity row 并验证 `close_clean_eof` 拒绝。
- ✅ 不产生错误 terminal fact — 只写 diagnostic，不写 `RUN_FAILED`，status 保持不变。

---

### S3-CR-F04：non-UPDATED terminal closeout 提交孤儿 payload descriptor

**最终状态：已修复。**

#### 4.1 修复机制

直接代码证据：

- 新增私有 typed exception `_TerminalCloseoutRollback`（`engine_ingest.py:336-338`）。
- Engine-origin `_close_terminal`（`engine_ingest.py:1268-1271`）：`terminal_closeout_in_transaction` 返回非 `UPDATED` 时 `raise _TerminalCloseoutRollback(...)`。
- Host lifecycle `_close_host_lifecycle_terminal`（`engine_ingest.py:1357-1360`）：同上。
- Engine-origin catch site：`_ingest_before_reactive_compaction`（`engine_ingest.py:820-823`）在 `run_write` 外捕获 `_TerminalCloseoutRollback`，返回 `_terminal_closeout_precondition_failed_result()`。
- Host lifecycle catch site：`_close_worker_lifecycle`（`engine_ingest.py:2716-2719`）同上。

#### 4.2 Transaction rollback 验证

`HostTransactionRunner.run_write`（`dayu/host/durable/transaction.py:288-360`）的异常处理路径：

- 第 314 行 `BEGIN IMMEDIATE`。
- 第 317 行 `result = operation(...)` — 此处 `_TerminalCloseoutRollback` 被抛出。
- 第 325 行 `COMMIT` 不被执行（异常在它之前）。
- 第 326 行 `finally` 递减计数器。
- 第 353 行 `except Exception` 捕获：调用 `_rollback_if_needed_or_mark_unusable()` 执行真实 SQLite rollback，然后 `raise` 透传。
- 异常被 catch site（第 822/2718 行）捕获并映射为 REJECTED contract。

**直接证据确认**：`_TerminalCloseoutRollback` 触发真实 `BEGIN IMMEDIATE` → rollback（不在 transaction 异常列表 `sqlite3.Error` / `HostDurableError` 中），异常透传到 transaction runner 外，由 ingest/closeout method 捕获并恢复 REJECTED contract。

#### 4.3 测试证据

**真实 invalid-state 路径**（`terminal_closeout_in_transaction` 真实返回 `INVALID_STATE`）：

- `test_engine_terminal_invalid_state_rolls_back_payload_and_events`（`test_engine_ingest_mapping.py:3142-3180`）：
  - 构造 `Run WAITING / Attempt RUNNING` 跨对象 invalid-state（通过 `_force_run_status_for_invalid_terminal_precondition` 把 Run status 改为 `WAITING`）。
  - 通过 public `ingest` 发送 `FINAL_ANSWER`，进入 `terminal_closeout_in_transaction` → 真实返回 `INVALID_STATE`。
  - `before` snapshot 比较 `host_sqlite_payloads` row count、`payload_descriptors` row count、`EventLog` row count、Run status、Attempt status。
  - 断言 `result.status is REJECTED`、`result.reason == "terminal_closeout_precondition_failed"`、`result.events == ()`。
  - 断言 after snapshot `== before` — 证明无 orphan payload、无 orphan descriptor、无 orphan EventLog、无 status mutation。

- `test_host_lifecycle_invalid_state_rolls_back_payload_and_events`（`test_engine_ingest_mapping.py:3183-3215`）：
  - 同上述构造，但通过 public `close_worker_lost` 进入 Host lifecycle path。
  - 相同四项 before/after 比较断言。

**CAS-lost 注入路径**（`terminal_closeout_in_transaction` 被 monkeypatch 替换为返回 `CAS_LOST`）：

- `test_engine_terminal_cas_lost_rolls_back_real_payload_repository`（`test_engine_ingest_mapping.py:3218-3258`）：
  - `monkeypatch.setattr` 把 `terminal_closeout_in_transaction` 替换为 `_cas_lost_terminal_closeout`（返回 `CAS_LOST` + 真实 durable rows）。
  - 关键：payload 仍由生产 `_write_terminal_payload → PayloadStore.write_sqlite_payload` 在真实 SQLite transaction 内写入——只有 terminal helper result 被注入。
  - 四项 before/after snapshot 断言：payload/descriptor/EventLog/status 全部不变。
  - 结果仍为 `REJECTED / terminal_closeout_precondition_failed / events=()`。

- `test_host_lifecycle_cas_lost_rolls_back_real_payload_repository`（`test_engine_ingest_mapping.py:3261-3293`）：
  - 同上但走 Host lifecycle path。

**四条测试的比较维度**：`_terminal_storage_snapshot`（`test_engine_ingest_mapping.py:5059-5093`）在同一 read transaction 内读取：
1. `host_sqlite_payloads` row count
2. `payload_descriptors` row count
3. `EventLog` row count
4. `Run.status`
5. `Attempt.status`

不是假阳性——每条测试都证明真实 SQLite 表中的 durable material 在 rollback 后完全不变。

**原有 accepted/duplicate 回归**：`test_worker_lost_closeout_uses_lost_event_ids_and_duplicate`（ACCEPTED + DUPLICATE 幂等）、`test_worker_clean_eof_closeout_uses_host_lifecycle_identity_and_source`（ACCEPTED）、Engine-origin terminal accepted 测试全部通过。

check #4 全部满足：
- ✅ non-UPDATED 返回先抛私有异常 `_TerminalCloseoutRollback`。
- ✅ 真实 transaction rollback（`transaction.py:353-358` `except Exception` → `_rollback_if_needed_or_mark_unusable()`）。
- ✅ 在 transaction 外恢复 REJECTED contract（`_terminal_closeout_precondition_failed_result()`）。
- ✅ Engine/Host 两条 catch 都覆盖（第 822 行和第 2718 行）。
- ✅ accepted/duplicate/ordinary diagnostic 不被误捕——`_TerminalCloseoutRollback` 只在 `result.status != UPDATED` 时抛出，accepted/duplicate 在抛出前已 return。
- ✅ 四条 adversarial 测试确实比较 sqlite payload rows、descriptor、EventLog、status 且不是假阳性。

---

### check #5：rollback exception 泄漏 / HostDurableError 误吞 / stop_worker_stream / promotion

**全部通过。**

- **泄漏检查**：`_TerminalCloseoutRollback` 由 `_close_terminal` / `_close_host_lifecycle_terminal` 在 write transaction 内抛出 → `transaction.py:353 except Exception` 执行 rollback 并 re-raise → `ingest_async` / `_close_worker_lifecycle` 的 try/except 在 `run_write` 外捕获 → 映射为 `REJECTED`。异常永不泄漏到 public caller。
- **HostDurableError 误吞检查**：`transaction.py:347 except HostDurableError` 在 `except Exception` 之前捕获并 re-raise，不被 `_TerminalCloseoutRollback` 的 catch site 拦截（catch site 只匹配 `_TerminalCloseoutRollback`）。HostDurableError 透传到 public caller，与修复前一致。
- **stop_worker_stream**：`_terminal_closeout_precondition_failed_result` 依赖 `EngineIngestResult.stop_worker_stream=False` 默认值。rollback 路径不要求 stop worker stream（worker stream 已因 EOF/crash 自然结束），语义正确。
- **promotion contract**：`_with_terminal_promotion_retry`（`engine_ingest.py:2743-2766`）只在 `result.status in (ACCEPTED, DUPLICATE)` 时触发 queue promotion。REJECTED 结果直接返回，不触发 promotion。`_finish_ingest`（line 840）和 `_close_worker_lifecycle`（line 2720）均正确调用 `_with_terminal_promotion_retry`。

---

### check #6：tests / pyright / diff check / source scans

- ✅ 214 passed（S3 required + state schema + transitions + cancel dispatch + recovery dispatch + public cancel）。
- ✅ pyright `0 errors, 0 warnings, 0 informations`。
- ✅ `git diff --check` 通过。
- ✅ 全部 source scans 通过（见 Validation summary 表格）。

---

### check #7：完整中文 docstring / 严格类型 / README decision / propagation audit / residual risk

**中文 docstring**：
- `_TerminalCloseoutRollback`（line 337）：有中文 docstring。
- `_TerminalFactPlan`（line 444）、`_EngineTerminalPlan`（line 456）、`_HostLifecycleTerminalPlan`（line 472）：有中文概览 docstring。
- `_close_terminal`（line 1192-1201）、`_close_host_lifecycle_terminal`（line 1290-1297）：有完整中文 docstring，含参数、返回值、异常。
- `_terminal_closeout_precondition_failed_result`（line 3781-3785）：有中文 docstring。
- `_validate_host_lifecycle_context`（line 1151-1157）：有中文 docstring。
- `_execute_reactive_compaction`（line 1848-1852）：有中文 docstring。

**严格类型**：
- 无 `Any` / `object` 类型注解（scan 零匹配）。
- `_TerminalFactPlan` / `_EngineTerminalPlan` / `_HostLifecycleTerminalPlan` 使用 `frozen=True, slots=True` dataclass，所有字段强类型。
- `_TerminalCloseoutRollback` 是强类型 private exception class。
- pyright 零错误零警告确认。

**README decision**：
- `dayu/host/README.md`：fix gate 不更新。现 S3 implementation 已描述 EngineEvent 与 worker lifecycle 是两条 typed path，共享 durable terminal transaction。本次 fix 的 private plan 类型拆分与 transaction failure atomicity 符合该稳定边界，无新增开发者公共接口、状态或执行路径。
- `tests/README.md`：不更新。新增测试仍属于现有 Engine ingest、durable transaction rollback、EventLog/payload foundation 与 reactive 类别，无新增测试层级或命令类别。
- 根 README / `dayu/README.md`：不触发。

**propagation audit**：

| 语义事实 | 产生 → 校验 → 持久化 → 投影 | 一致性状态 |
|---|---|---|
| Attempt terminal status（F01） | `is_terminal_attempt_status(latest.attempt.status)` 消费 durable state owner | 一致：reactive gate 只读 status，terminal refs 只留 row consistency |
| Terminal plan 类型边界（F02） | `_EngineTerminalPlan` / `_HostLifecycleTerminalPlan` 编译期分离，只共享 `_TerminalFactPlan` | 一致：两条 closeout 路径的类型系统不阻止跨来源字段污染 |
| Host lifecycle identity（F03） | `_validate_host_lifecycle_context` 显式校验 `run.run_id` | 一致：Engine-origin 与 Host lifecycle ingress 的 identity guard 语义对齐 |
| Terminal payload/event/status atomicity（F04） | `_TerminalCloseoutRollback` → transaction rollback → REJECTED contract | 一致：non-UPDATED 时 payload descriptor、canonical terminal facts、status rows 原子回滚，无 orphan material 可进入 projection/LLM-facing 消费者 |

**residual risk**：

| 风险 | 分类 | 理由 |
|---|---|---|
| 跨进程 Engine/Host lifecycle 并发 stress | assigned to later work unit | 正确性由 `BEGIN IMMEDIATE`、EventLog unique identity、shared terminal CAS 与本次 non-UPDATED rollback 共同保证 |
| 非 terminal EventLog 常量统一 | assigned to later work unit (P3-J) | P3-A scope 边界 |
| P3-B final answer / outbox continuity | covered by later approved slice | 未触碰 |
| 外部 artifact 先发布、SQLite 后失败的 cleanup | covered by existing design/non-goal | 当前固定 SQLite payload repository，rollback 覆盖 payload row 与 descriptor |

**无未分类 residual risk、blocking open question 或 deferred accepted finding。**

---

### check #8：不扩张 P3-B/P3-J

- ✅ 未发现 P3-B final answer / outbox continuity 修改。
- ✅ 未发现 P3-J EventLog schema hardening 修改。
- ✅ 非 terminal EventLog 常量仍保持现有分散定义，作为 P3-J residual input 记录。
- ✅ 未发现新 public API、新 status 成员、schema migration 或 dispatch state machine 修改。

---

## 新 Finding 检查

逐项 adversarial 检查未发现以下 material defect：

| 检查项 | 结果 |
|---|---|
| `_TerminalCloseoutRollback` 被更宽泛的 `except Exception` 误捕 | PASS — catch site 精确匹配 `except _TerminalCloseoutRollback` |
| promotion 在 REJECTED rollback 后误触发 | PASS — `_with_terminal_promotion_retry` 只对 ACCEPTED/DUPLICATE 触发 |
| `stop_worker_stream` 在 closeout rollback 后错误设为 True | PASS — `REJECTED` 默认 `stop_worker_stream=False` |
| duplicate detection 在 partial duplicate 时误把 rollback 当成 REJECTED | PASS — duplicate 在 `_TerminalCloseoutRollback` 抛出前已 return（`_close_terminal:1222-1229` / `_close_host_lifecycle_terminal:1310-1317`） |
| `_TerminalFactPlan` 的 event type/status 不用 lifecycle owner helper | PASS — `test_terminal_plans_use_lifecycle_event_owner_helpers` 显式断言 |
| Engine CAS-lost 测试只 mock terminal helper 但未验证真实 payload 写入 | PASS — `_cas_lost_terminal_closeout` 不写 EventLog（`del event_log_store`），但 payload 由生产 `_write_terminal_payload` 在同一个真实 SQLite transaction 内写入 |
| Host lifecycle ingress 缺少 dispatch_record.execution_id 校验 | PASS — 已在 `_validate_host_lifecycle_context:1174` 检查 |
| `_validate_host_lifecycle_context` 的 `run.run_id` 行已在 `read_run_by_id` 隐含但测试 double 证明显式检查的价值 | PASS — `test_host_lifecycle_ingress_rejects_mismatched_run_identity` 通过替换 repository 返回错 identity 行验证 fail-closed |

**无新 material defect finding。**

---

## Verdict

**PASS** — 0 新 finding。

| Finding | 最终状态 | 证据 |
|---|---|---|
| S3-CR-F01 | 已修复 | `engine_ingest.py:1934-1935` + test line 916-970 |
| S3-CR-F02 | 已修复 | `engine_ingest.py:442-481` + test line 501-576 |
| S3-CR-F03 | 已修复 | `engine_ingest.py:1169` + test line 3016-3071 |
| S3-CR-F04 | 已修复 | `engine_ingest.py:336-338, 820-823, 1268-1271, 1357-1360, 2716-2719` + tests line 3142-3293 |

四项 finding 全部已修复，无证据失效，无新 material defect 引入。

## Completion

- Verdict：PASS。
- F01：已修复。
- F02：已修复。
- F03：已修复。
- F04：已修复。
- 新 finding 数：0。
- Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-rereview-ds.md`。
