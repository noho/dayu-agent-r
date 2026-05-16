# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase8-projection-core-event-stream
- Base: P8-S2 accepted commit c891792
- Output file: docs/reviews/host-phase8-code-review-s3-ds-20260516.md
- Plan truth: docs/host/phase8-projection-core-event-stream-plan.md
- Implementation artifact: docs/reviews/host-phase8-implementation-s3-read-model-repair-20260516.md
- Included scope:
  - dayu/host/_event_payload.py（新增 optional_payload_text）
  - dayu/host/durable/schema.py（新增 host_run_results / host_session_timeline_items DDL、索引、版本 bump）
  - dayu/host/durable/read_model.py（新文件：row codec、upsert、reset）
  - dayu/host/read_model.py（新文件：MinimalReadModelProjectionConsumer、repair_minimal_read_models）
  - tests/host/test_durable_schema.py（新增 read model 表/索引/约束断言）
  - tests/host/test_projection_read_model.py（新文件：projection / repair 测试）
  - tests/host/test_public_event_stream.py（新增 read model 缺失不影响 stream 测试）
  - tests/host/test_public_run_api.py（新增 get_run fallback 测试）
  - tests/host/test_import_boundary.py（新增 read_model.py / durable/read_model.py 到 PROJECTION_MODULES）
  - dayu/host/README.md、tests/README.md
- Excluded scope: dayu/host/api.py, dayu/host/__init__.py, dayu/host/read_api.py, tests/host/test_public_session_api.py, tests/host/test_package_exports.py, tests/host/test_weak_typing_guard.py（范围内但无需修改或 P8-S2 已覆盖，仅作引用核对）
- Parallel review coverage: 无

## Blocking Concern 裁决

以下 9 项为任务指定 blocking check，逐项给出裁决与证据。

### BC-1: Projection as governance truth — PASS

Projection tables `host_run_results` / `host_session_timeline_items` 均放在 `PROJECTION_TABLES`，plan §3 定义"所有新增表属于 projection / read model owner，不是 Host governance truth"。代码无任何 admission / command / recovery 路径读取 projection 表作为状态推进依据。

- read_model.py:32 定义 `PROJECTION_TABLES` 包含四张表，"Phase 8 projection checkpoint / failure / read model table 名称集合"。
- get_run（read_api.py）未读取 `host_run_results`；stream_run_events 未读取任何 projection 表。
- 测试 `test_get_run_uses_durable_status_when_minimal_read_model_is_missing` 证明 get_run 不依赖 projection。

### BC-2: Repair reading projection as input truth — PASS

`repair_minimal_read_models` 只从 EventLog 读取 canonical facts（通过 `ProjectionRunner.run_once` 内部调用 `read_events_after`），不读取 `host_run_results` 或 `host_session_timeline_items` 作为输入。plan §6 明确要求"Repair 不得读取 Session timeline 或 RunResult 作为输入，只能读取 EventLog 和必要 durable Run / Session rows 做 referential validation"。

- read_model.py:193 `ProjectionRunner(transaction_runner, (consumer,))` — repair 只注入 consumer，runner 从 EventLog 读取。
- read_model.py:201 `runner.run_once(consumer_id, limit=batch_size)` — 每次调用 run_once 通过 `_process_next_event` → `read_events_after` 读取 EventLog。
- repair 不包含任何 `read_run_result` 或 `read_session_timeline_items` 调用。

### BC-3: Public timeline facade without approval — PASS

P8-S3 未新增任何 public timeline API。`dayu/host/read_api.py` 未修改。`dayu/host/read_model.py` 的 `repair_minimal_read_models` 是 internal helper，不在包根导出。`MinimalReadModelProjectionConsumer` 不在 `dayu/host.__all__` 中。plan §2.1 要求"第一版建议不新增 public timeline API"并明确"若 implementation agent 认为必须新增 read_session_timeline(...) public facade，必须停止并交回 controller"——已遵守。

### BC-4: RunResult silent overwrite — PASS

`insert_run_result_if_absent`（durable/read_model.py:133）不使用 `INSERT OR REPLACE` 或 `ON CONFLICT(run_id) DO UPDATE`。冲突路径：

- 同一 terminal event → 返回 `DUPLICATE`（行 154–155）。
- 不同 terminal event → `raise HostDurableError("RunResult terminal event identity conflicts")`（行 156）。
- 测试 `test_conflicting_terminal_event_records_failure_without_overwrite` 证明既有 RunResult 的 `terminal_event_id` 在冲突后仍为首次写入值，未被覆盖。

### BC-5: Checkpoint advance on conflict/failure — PASS

plan §5 不变量 5："Consumer apply 失败时，runner 必须写 host_projection_failures，不得推进 checkpoint"。

- projection.py:477–479：`consumer.apply_event` 抛出异常 → 转为 `_ProjectionApplyFailed`，该异常在 run_once:372 被捕获 → `_record_failure` 在独立写事务中记录 failure（projection.py:517–527），run_once 内层 loop break。
- 关键：`_ProjectionApplyFailed` 发生在 `_process_next_event` 内部的 `run_write` lambda 中，lambda 抛异常 → SQLite 事务 rollback → checkpoint 未推进。
- `_record_failure` 使用新的 `run_write` 事务（projection.py:517），不依赖已回滚事务。
- 测试 `test_conflicting_terminal_event_records_failure_without_overwrite` 证实：conflict_result.failures == 1，checkpoint 停留在第一个成功的 terminal event sequence。

### BC-6: Raw payload text synthesis — PASS

plan §2.5 要求"可选 display_text 只允许从 typed USER_INPUT_ACCEPTED payload 的 display_text 字段读取；其它事件不得从 raw payload 任意拼展示文本"。

- read_model.py:320–333 `_display_text`：只对 `USER_INPUT_ACCEPTED` 读取 display_text，其他事件类型硬编码返回 `None`。
- _event_payload.py:393–412 `optional_payload_text`：字段缺失/null → `None`；字段存在但非 string 或空字符串 → 抛出 `HostDurableError`。不存在从 raw JSON 字符串拼接、截取或推导展示文本的路径。
- 测试 `test_user_input_timeline_preserves_repeated_text_and_null_fallback` 证实：缺失 `display_text` 的 item 的 `display_text` 为 `None`，`payload_ref` / `payload_digest` 保留。

### BC-7: Own SQLite connection / public command facade — PASS

plan §2.2："构造时必须接收现有 HostTransactionRunner 和 concrete consumers，由 HostCommandHandle 或后续 composition root 通过 private dependency 注入；不得自建 SQLite connection，不得持有或调用 public command facade"。

- `ProjectionRunner.__init__` 只接收 `HostTransactionRunner` 与 consumers tuple（projection.py:314–336）。
- `MinimalReadModelProjectionConsumer` 只依赖 `HostTransaction`（在 apply_event 方法参数中）。
- `repair_minimal_read_models` 接收 `HostTransactionRunner`（read_model.py:163），通过该 runner 执行所有读写。
- 测试通过 `host._transaction_runner()` 获取 private runner 注入，不调用 public command 方法进行 repair。

### BC-8: Schema mismatch — PASS

Schema version 从 5 bump 到 6（schema.py:24）。所有新增 DDL 使用 `CREATE TABLE IF NOT EXISTS`，遵循 fresh schema convention。`bootstrap_host_durable_store` 对非 (0, 6) 版本抛出 `HostSchemaMismatchError`，不做兼容读取。

host_session_timeline_items 的 `FOREIGN KEY(event_sequence) REFERENCES event_log(event_sequence)` 依赖 event_log(event_sequence) 是 PRIMARY KEY——已在 P8-S1 测试 `test_event_sequence_is_sqlite_foreign_key_parent_key` 中验证。run_id / session_id FK 引用 govvernance tables，由既有约束保障。

### BC-9: Insufficient tests — PASS

plan §7 P8-S3 测试要求 12 条，逐条对照：

| # | 要求 | 覆盖 |
|---|------|------|
| 1 | Terminal → RunResult | test_terminal_event_projects_run_result_and_duplicate_replay_is_noop |
| 2 | Duplicate replay no-op | 同上 |
| 3 | Conflicting terminal → failure, no checkpoint | test_conflicting_terminal_event_records_failure_without_overwrite |
| 4 | No INSERT OR REPLACE / ON CONFLICT overwrite | 同上（断言 stored.terminal_event_id == first.event_id） |
| 5 | Repeated display_text distinct items | test_user_input_timeline_preserves_repeated_text_and_null_fallback |
| 6 | Missing display_text → NULL, preserve refs | 同上（断言 null_item.display_text is None, null_item.payload_ref 非空） |
| 7 | Cancelled + later input separate | test_cancelled_input_and_later_input_remain_separate_items |
| 8 | Repair rebuilds same rows | test_repair_rebuilds_rows_after_deletion_and_reset |
| 9 | Repair batch failure → resume from checkpoint | test_repair_failure_resumes_from_last_committed_checkpoint |
| 10 | Stale/missing read model → stream unchanged | test_stream_run_events_ignores_missing_minimal_read_model |
| 11 | get_run fallback stable | test_get_run_uses_durable_status_when_minimal_read_model_is_missing |
| 12 | Package exports updated if needed | 无新 public type → 无需更新 |

全部 12 条计划测试要求已覆盖，7 个新测试 + 2 个既有文件增量测试。

## Findings

### 001-未修复-低-optional_payload_text 非法类型失败路径缺少测试

- **入口/函数**: `optional_payload_text` → `_display_text` → `MinimalReadModelProjectionConsumer.apply_event`
- **文件(行号)**: _event_payload.py:393–412, read_model.py:320–333
- **输入场景**: `USER_INPUT_ACCEPTED` payload 中 `display_text` 字段存在但值为 `123`（整数）、`[]`（列表）或空字符串 `""`
- **实际分支**: `optional_payload_text` 中 `isinstance(value, str) and value.strip() != ""` → False → 抛出 `HostDurableError`
- **预期行为**: 抛出 `HostDurableError`（当前行为与 plan 一致："invalid typed value fails projection"）
- **实际行为**: 抛出 `HostDurableError("payload field display_text must be non-empty text")`
- **直接证据**: _event_payload.py:410–412，当 value 非空 string 时直接 raise，无回退路径
- **影响**: 功能正确但无测试防御。若有调用方后续假设 payload 字段不存在时静默 fallback，可能在类型错误时静默丢失。
- **建议改法和验证点**: 在 `test_user_input_timeline_preserves_repeated_text_and_null_fallback` 或独立测试中增加一条：display_text 为数字 / 空字符串时，consumer apply_event 抛出 `HostDurableError`，且 failure row 写入 `host_projection_failures`。
- **修复风险**: 低（仅新增测试，不改生产代码）
- **严重程度**: 低

### 002-未修复-低-repair batch 语义与 plan 措辞存在温和偏差

- **入口/函数**: `repair_minimal_read_models` → `ProjectionRunner.run_once`
- **文件(行号)**: read_model.py:163–221, projection.py:338–399
- **输入场景**: repair batch_size=10，EventLog 中有 20 条事件
- **实际分支**: `run_once` 对每条事件独立调用 `run_write`，而非地将 10 条事件合并到一个 batch transaction 中
- **预期行为**: plan §6 写"每批使用独立 HostTransactionRunner.run_write() transaction"——该措辞可被解读为每批（batch_size 条事件）共享一个事务
- **实际行为**: 每批内每条事件有自己的独立 `run_write` 事务（projection.py:367），checkpoint 与 projection write 在同一事务内（projection.py:444–489）
- **直接证据**: projection.py:367 `self._transaction_runner.run_write(lambda transaction: self._process_next_event(...))` 在 for 循环内对每条事件创建独立事务
- **影响**: 不影响正确性，因为 plan §5 不变量 3 的核心要求"Checkpoint advance 与对应 projection writes 必须处于同一个 transaction"被每条事件级别满足。但多事件 batch 的事务原子性边界比 plan 措辞可能暗示的更细化。implementation artifact 已如实记录了此偏差（"The existing runner commits per scanned EventLog row; P8-S3 did not allow modifying dayu/host/projection.py"）。
- **建议改法和验证点**: 当前实现已满足正确性要求。如需严格对齐 plan 措辞，应在 Phase 9 或 Phase 15 重构 runner 支持 batch-transaction 模式。当前无需修改。
- **修复风险**: 低（不改动）
- **严重程度**: 低（已由 implementation artifact 如实披露）

## Open Questions

- `optional_payload_text` 对 value 为空字符串 `""` 的处理是抛异常，而 plan §2.5 的 P8-S3 payload stop check 只提到"保留 payload_ref / payload_digest，并将 nullable display_text 写为 NULL，同时用测试覆盖该行为"。空字符串是否应也走 NULL 路径？当前处理方式（抛异常）与空字符串非空这一事实一致，且更严格地防止无声降级。是否需要放宽由 controller 判断。

## Residual Risk

- **Repair 无事务型 batch**：repair replay 每条 event 独立 commit，不保证 batch_size 条 events 的批量原子性。若中途 crash，已 commit 的 event 的 checkpoint 被保留，未 commit 的事件在下一次 repair 从 checkpoint 继续——这是正确恢复语义，不构成数据损坏风险。但若需要在 Phase 15 提供"exactly-once batch atomic repair"保证，需要重构 runner 支持 batch-transaction。
- **`reset_minimal_read_model_projection` 做全局 DELETE**：`DELETE FROM host_session_timeline_items` 和 `DELETE FROM host_run_results` 无 WHERE 子句。当前这些表只有 `host.minimal-read-model` 一个 consumer 写入，所以正确。若未来其他 consumer 写入同名表（违反 plan），全局 reset 会被误伤。Phase 13–15 owner 应在扩展表写入者时检查此假设。
- **`get_run` 未读取 RunResult summary refs**：当前 `get_run` 不从 `host_run_results` 读取 summary_ref / summary_digest。`TerminalResultSummary` 保持 status-only 输出。这是 P8-S3 的有意延迟——implementation artifact 明确标注"Public get_run intentionally remains durable-state based"。Phase 9 Memory 或 Phase 15 production hardening owner 需要决定是否将 RunResult summary refs 接入 public snapshot。

## Review Conclusion

**PASS**。P8-S3 实现满足全部 9 项 blocking concern 检查与 plan §7 测试要求。无高或严重级别 finding。2 项低级别 finding 分别为测试覆盖缺口（optional_payload_text 非法类型）与 plan 措辞偏差（batch transaction 粒度），均不影响正确性或 merge 安全性。

代码实现了正确的 RunResult 幂等/冲突语义（no INSERT OR REPLACE, no silent overwrite）、正确的 checkpoint 推进逻辑（失败不推进、成功才推进）、正确的 display_text typed fallback（只从 USER_INPUT_ACCEPTED typed payload 读取，缺失/非法不静默降级）、正确的 repair 两阶段语义（reset + replay from EventLog）、以及正确的 public read truth boundary 保持（get_run / stream_run_events 不受 read model 缺失影响）。Import 边界、类型严格性、文档同步均符合计划要求。
