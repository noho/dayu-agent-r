# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Narrow Re-Review（AgentMiMo）

## 结论

**S3-RR-F01 CLOSED — 0 new material finding。**

- Gate：`code-rereview-fix-slice-3`
- Accepted base：`b33bb80b`
- 角色：原 reviewer narrow re-review，复核 accepted `S3-RR-F01` 修复并对最终 diff 做 new material finding scan
- 排除项：`docs/host/issues-implementation-control.md` 是 Controller-owned dirty change，已排除出被审查实现与 finding
- 未读取另一 reviewer（AgentDS）本轮新产物

## S3-RR-F01 逐项确认：关闭

### 1. Durable owner 唯一性与签名

**要求**：唯一 owner `project_terminal_notice_from_exact_run_event`，签名为直接 typed `RunRow | None`、`EventLogRow | None`、keyword-only `bool`；无为此新增 Protocol。

**代码证据**：

- `dayu/host/durable/run_transition.py:935-966`：唯一定义
  - 参数：`run: RunRow | None`、`exact_run_event: EventLogRow | None`、`*, wake_queue_promotion: bool`
  - 完整中文 docstring，含参数/返回值/异常
  - fail-closed 覆盖 missing rows 与 terminal event id/sequence、Session id、Run id 四类不一致
  - notice 只携带 exact Session、terminal event sequence 与原始 promotion flag

- `dayu/host/terminal_post_commit.py:52-66`：`TerminalPostCommitPort` Protocol 已存在于 S3 早期，非本 fix 新增

- AST static test `tests/host/test_terminal_post_commit.py:337-419`：
  - 断言 `run_transition.py` 中恰好一个 `project_terminal_notice_from_exact_run_event` 定义
  - 断言参数名为 `run`、`exact_run_event`（positional），`wake_queue_promotion`（keyword-only）
  - 断言类型注解为 `RunRow | None`、`EventLogRow | None`、`bool`

**结论**：✅ 通过。唯一 owner，直接 typed rows，无新增 Protocol。

### 2. 五 consumer direct import/call，无 alias/wrapper/re-export

**要求**：admission/engine_ingest/recovery/dispatch/waiting 五 consumer direct import/call，无 alias/wrapper/re-export/本地 `TerminalPostCommitNotice` 构造。

**代码证据**：

- `dayu/host/admission.py:97`：`from dayu.host.durable.run_transition import ... project_terminal_notice_from_exact_run_event`
- `dayu/host/engine_ingest.py:181`：同上
- `dayu/host/recovery.py:31`：同上
- `dayu/host/dispatch.py:74`：同上
- `dayu/host/waiting.py:75`：同上

- AST static test `tests/host/test_terminal_post_commit.py:372-419`：
  - 遍历五个 consumer，断言无本地同名/旧私有 helper 定义
  - 断言恰好一个 direct import（无 `asname`）
  - 断言 `helper_name in called_names`（实际被调用）
  - 断言无 `TerminalPostCommitNotice(...)` 本地构造
  - 断言无 local helper alias（`Assign`/`AnnAssign` 赋值）

**结论**：✅ 通过。五 consumer 全部 direct import/call，无 wrapper/alias/re-export。

### 3. Waiting 旧 pure projection 删除与 terminal snapshot helper 职责

**要求**：`_terminal_notice_from_wait_transition` 删除；`_terminal_notice_from_terminal_wait_snapshot` 只做 confirmation 并交给 shared helper；failed/lost/expiry/replay flags 与时点不漂移。

**代码证据**：

- `grep -rn "_terminal_notice_from_wait_transition" dayu/host/`：零命中。旧 helper 已删除。

- `dayu/host/waiting.py:2130-2174`：`_terminal_notice_from_terminal_wait_snapshot` 实现
  - 检查 `wait_record.status in (FAILED, LOST)` → non-terminal 返回 `None`
  - 检查 `is_terminal_run_status(run.status)` → nonterminal owner Run 抛 `HostDurableError`
  - 调用 `confirm_terminal_run_in_transaction` 读取并校验 exact terminal event
  - 调用 `project_terminal_notice_from_exact_run_event(confirmation.run, confirmation.run_event, wake_queue_promotion=False)`
  - 不构造临时 transition，不复制投影校验

- Flag 时点验证：
  - `_resolve_failed`（waiting.py:1263）：`wake_queue_promotion=True` ✓（首次 failed 释放 active slot）
  - `_resolve_lost`（waiting.py:1336）：`wake_queue_promotion=True` ✓（首次 lost 释放 active slot）
  - `_expire_wait_in_transaction` 首次 expiry（waiting.py:1537）：`wake_queue_promotion=True` ✓
  - `_terminal_notice_from_terminal_wait_snapshot`（waiting.py:2168）：`wake_queue_promotion=False` ✓（replay/confirmation）

**结论**：✅ 通过。旧 helper 删除，snapshot helper 只做 confirmation + 交给 shared helper，flags 与时点不漂移。

### 4. Owner 行为/static tests 真实覆盖

**要求**：owner 行为测试覆盖 missing 与四类 identity mismatch；static test 覆盖五 consumer 闭集。

**代码证据**：

- `tests/host/test_run_attempt_transitions.py:360-470`：`test_terminal_closeout_appends_concrete_terminal_events`
  - 验证 `project_terminal_notice_from_exact_run_event` 投影正确
  - 验证 exact sequence/stable Run ref/Session 一致
  - `pytest.raises(HostDurableError, match="exact Run/Event projection is missing a row")`：Run=None 和 Event=None
  - 四类 identity mismatch（terminal_event_id、terminal_event_sequence、session_id、run_id）：`pytest.raises(HostDurableError, match="exact Run/Event projection rows are inconsistent")`

- `tests/host/test_terminal_post_commit.py:337-419`：`test_terminal_notice_projection_has_single_durable_owner`
  - 五 consumer 闭集：`_TERMINAL_NOTICE_PROJECTION_CONSUMERS = ("admission.py", "engine_ingest.py", "recovery.py", "dispatch.py", "waiting.py")`
  - AST 断言每个 consumer 无本地定义、direct import、实际调用、无本地构造、无 alias

**结论**：✅ 通过。missing + 四类 mismatch + 五 consumer 闭集均有真实覆盖。

### 5. Producer manifest/direct promotion/local-only/Engine boundary/pyright/coverage 保持

**要求**：各项不变性保持。

**代码证据**：

- `test_static_terminal_producer_manifest_is_exact`：冻结 21 个 producer 闭集。✅
- `test_direct_queue_promotion_allowlist_is_exact`：ordinary direct promotion 精确为 5 处。✅
- `test_terminal_contract_module_has_no_upper_layer_dependency`：`terminal_post_commit.py` 只依赖 `__future__`、`dataclasses`、`typing`。✅
- `test_notice_strict_validation_and_private_package_boundary`：`TerminalPostCommitNotice`/`TerminalPostCommitPort` 未从 `dayu.host` public package export。✅
- Engine boundary：`dayu/engine` 对 `TerminalPostCommit`/`terminal_post_commit`/`session_event_delivery` 零命中。✅
- pyright：`0 errors, 0 warnings, 0 informations`。✅
- 单文件 coverage：全部 modified production 文件 ≥80%（durable/run_transition 93%、admission 91%、waiting 89%、engine_ingest 91%、dispatch 91%、recovery 92%）。✅

**结论**：✅ 通过。所有不变性保持。

## New Material Finding Scan

对全部最终 diff（`b33bb80b` 以来的 workspace changes）执行 new material finding scan。

### 检查范围

- durable owner 与 `RunTransitionResult.run_event` 传播
- 五 consumer 调用点 flag 语义
- `confirm_terminal_run_in_transaction` 与 `read_terminal_run_event_in_transaction` 校验
- `_terminal_closeout_replay_result` / `_active_cancel_watchdog_replay_result` 新增 `transaction`/`event_log_store` 参数
- `_expiry_noop_transition` 新增 confirmation 逻辑
- dispatch.py watchdog closeout / worker startup timeout 动态 flag 计算
- session cancel 批量 terminal notice 收集与排序
- coordinator watermark/dedupe/close barrier

### 逐项检查

1. **`RunTransitionResult.run_event` 传播**：所有 transition 函数（30+ 处）正确填充 `run_event`；early-return/CAS_LOST/INVALID_STATE 路径为 `None`；event-writing 路径为 exact event。通过。

2. **`confirm_terminal_run_in_transaction`**：校验 `run.status in TERMINAL_RUN_STATUSES`，读取并校验 terminal ref。用于 replay/ack/duplicate 场景。通过。

3. **`read_terminal_run_event_in_transaction`**：校验 terminal ref 缺失、event 缺失、sequence/session_id/run_id 不一致。通过。

4. **replay helpers 新增参数**：`_terminal_closeout_replay_result` 和 `_active_cancel_watchdog_replay_result` 新增 `transaction`/`event_log_store`，用于在 replay 路径读取 exact terminal event。通过。

5. **`_expiry_noop_transition`**：新增 confirmation 逻辑，对 terminal run 调用 `confirm_terminal_run_in_transaction` 获取 `run_event`。通过。

6. **dispatch.py 动态 flag**：watchdog closeout（line 1351）和 worker startup timeout（line 3961）使用 `result.run_event.event_id == run_cancelled_event_id` / `run_event_id` 动态判断。语义正确：只有实际写入 terminal event 的那次才触发 promotion。通过。

7. **session cancel 批量收集**：`_CancelSessionRunsOperation` 收集 `_SessionCancelTargetResult.terminal_notice`，按 `terminal_event_sequence` 排序后返回。通过。

8. **coordinator**：watermark 只在 `True` notice 且 `sequence > watermark` 时更新；`False` notice 不更新 promotion watermark；dedupe 正确；close barrier 正确。通过。

### 结论

**未发现新的 material finding。**

## Residual Risks / Open Questions

无 S3 contract 的已知 residual correctness risk。

Service exact-five、CLI callback execution domain、旧 Service relay 删除及 README 最终同步属于已批准的 S4，不在本 narrow re-review scope 内。

## Artifact 路径

`docs/reviews/wu-host-session-event-delivery-01-slice3-narrow-rereview-mimo.md`
