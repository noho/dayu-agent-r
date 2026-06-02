# Residual Risk Follow-up Deep Review

- Reviewer: MiMo (agent)
- Date: 2026-06-02
- Target: workspace uncommitted changes (residual risk follow-up)
- Scope: RR-STRESS-01/02, RR-DUR-02/03/05, RR-LIFE-01, RR-LAYER-02-01 status transitions; code/test/doc evidence

## Verification Summary

| Check | Result |
|---|---|
| `pytest -q tests/host/test_durable_connection.py tests/host/test_durable_schema.py tests/host/test_dispatch_scheduler.py tests/host/test_import_boundary.py` | 112 passed, 0 failed |
| `pyright dayu/host/durable/maintenance.py dayu/host/durable/schema.py dayu/host/dispatch.py tests/` | 0 errors, 0 warnings |

## Findings

### F-01 [LOW] test 断言风格不一致：bare index name substring

**文件**: `tests/host/test_durable_schema.py:497`

```python
assert INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE in error_message
```

同文件的其他批量诊断测试使用带前缀的精确匹配：

```python
assert f"tables: {TABLE_HOST_MEMORY_DIAGNOSTICS}" in error_message
assert (
    f"indexes: {INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON}, "
    f"{INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE}"
) in error_message
```

裸 index name 子串匹配不会误判（当前消息格式下 name 只出现在 `indexes:` 后），但风格不一致降低了断言对消息格式变更的防线强度。

**建议**: 改为 `f"indexes: {INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE}" in error_message`，与同文件其他断言保持一致。

---

### PASS: RR-DUR-02 WAL checkpoint connection / db_path 一致性校验

**实现**: `dayu/host/durable/maintenance.py:77` 在 checkpoint 入口调用 `_assert_connection_matches_db_path`，通过 `PRAGMA database_list` 读取 connection 实际 main database 路径并与传入 `db_path` 做 `Path.resolve(strict=False)` 比较。不一致时 fail closed 抛 `HostDurableError`。

**测试**: `tests/host/test_durable_connection.py:181` `test_wal_checkpoint_rejects_mismatched_connection_and_db_path` 覆盖两个独立 store 的 connection/path 错配场景，断言精确错误消息。已关闭 connection 的错误路径也更新为匹配新的 inspect-database 错误消息（:213-218）。

**Fail closed 行为**: 无法读取 database list、main database 不是文件型、路径不一致均抛 `HostDurableError`，不执行 checkpoint。

**不影响正确路径**: 正常 connection/path 同源时 `_assert_connection_matches_db_path` 通过后才执行 PRAGMA checkpoint。

**结论**: RR-DUR-02 关闭有充分代码/测试证据支撑。

---

### PASS: RR-DUR-03 schema required object 缺失批量诊断

**实现**: `dayu/host/durable/schema.py:1372` `_validate_required_objects_exist` 同时收集缺失 tables 和 indexes，由 `_missing_required_objects_message` 构造诊断消息。单对象缺失保留精确单对象消息格式；多对象缺失批量列出。仍 fail closed、不 repair、不迁移。

**测试**:
- `test_current_schema_missing_table_opener_raises_without_repair`（:471）：DROP TABLE 同时删除关联 index，触发多对象缺失路径，断言批量诊断消息包含 table 和 index 名称。
- `test_current_schema_multiple_missing_objects_are_reported_together`（:534）：显式删除一个 table 和一个 index，断言批量诊断消息同时列出两者。
- `test_secondary_connection_missing_table_raises_without_repair`（:647）：secondary connection 路径同样走批量诊断。

**结论**: RR-DUR-03 关闭有充分代码/测试证据支撑。

---

### PASS: RR-DUR-05 same-name wrong table/index definition validation

**实现**: `dayu/host/durable/schema.py:1463` `_validate_required_object_definitions` 从 `HOST_DURABLE_DDL` 在内存 fresh DB 中生成 expected SQLite catalog SQL，与目标 DB 的 `sqlite_master.sql` 逐对象比较。DDL 真源唯一，不引入 brittle string mismatch。

**测试**:
- `test_current_schema_wrong_index_definition_opener_raises_without_repair`（:564）：替换 index 定义为错误版本，断言 definition mismatch fail closed。
- `test_current_schema_mutated_table_definition_opener_raises_without_repair`（:604）：变异 table catalog SQL，断言 definition mismatch fail closed。

**注意**: 此 validation 在本次 diff 之前已存在（WU-LAYER-01 实现），本次未修改。RR-DUR-05 关闭的论证是"已由 WU-LAYER-01 实现"，符合事实。

**结论**: RR-DUR-05 关闭有充分代码/测试证据支撑。

---

### PASS: RR-LIFE-01 scheduler close residual active handle / registry cleanup

**实现**: `dayu/host/dispatch.py:1991-1994` 在 close 中新增：
1. 遍历 `_active_handles`，逐个 `_safe_close_worker_handle` 并 discard。
2. 调用 `_active_registry.clear()` 清空 registry。

此逻辑位于 `cancel_all` + `_suppress_task_cancel` 之后、`_lane_controller.close` 之前，确保：
- worker accepted 后 consumer task 尚未启动的窗口中，handle 仍被 close。
- registry 被清空，不再残留 entry。
- 不写 scheduler-close-created terminal fact（close 不写任何 EventLog）。

**测试**: `test_scheduler_close_cleans_active_handle_when_consumer_task_never_started`（:2791）：
- 手动构造 active task（`_unstarted_active_consumer_probe`）不进入 consume body。
- 手动注册 handle 到 registry 和 `_active_handles` / `_active_tasks`。
- 调用 `scheduler.close()` 后断言：consumer 未启动、cancellation token 已取消（reason="scheduler_close"）、handle cancel/close 各一次、registry 清空、后续 registry.cancel 返回 False。

**正常路径不受影响**: 现有 `test_scheduler_close_lets_active_task_own_handle_close` 等测试覆盖正常 close 流程。

**结论**: RR-LIFE-01 关闭有充分代码/测试证据支撑。

---

### PASS: RR-STRESS-01 transferred-to-issue / RR-STRESS-02 closed

**RR-STRESS-01**: 高强度慢盘 / Docker stress 测试转入 GitHub Issue #38 独立跟踪，当前 stress suite 仍为确定性 production hardening suite。转移合理。

**RR-STRESS-02**: pytest-timeout 强杀会导致测试失败（timeout error），不会被误判为测试通过。原 residual risk 描述"pytest-timeout limitation"被重新评估为"不是 residual risk"。论证合理。

**结论**: 两个 stress risk 的状态变更论证合理，不存在误关。

---

### PASS: RR-LAYER-02-01 新增 residual risk

**描述**: `_safe_outcome_text` 截断形状（前 240 字符 + "..."，总长可到 243）与 runtime `truncate_diagnostic_text`（总长不超过 max_chars）语义不同。

**状态**: deferred-with-owner（future Host compactor diagnostic hardening）。

**评估**: 描述准确，差异已由 controller 裁决和测试锁定，不影响安全性或当前 PR，不阻塞当前 PR。

**结论**: RR-LAYER-02-01 新增合理，不阻塞。

---

### PASS: README / tests README 同步

- `dayu/host/README.md`: 更新 schema validation 描述（批量诊断）和 WAL checkpoint 描述（connection/path 同源校验），符合代码实际行为。
- `tests/README.md`: 更新 dispatch scheduler 测试覆盖描述（active task 与 pre-consumer active handle 资源释放），符合新增测试。
- `docs/host/host-core-followup-implementation-control.md`: residual risk 表状态更新有对应代码/测试/文档证据。

各 README 职责边界符合 AGENTS.md 规定。

---

### PASS: 编码硬约束合规

| 检查项 | 结果 |
|---|---|
| Any / object / 无类型签名 | 未发现 |
| getattr / hasattr | 未发现 |
| lazy import | 未发现 |
| 兼容 wrapper / re-export | 未发现 |
| 分层反向依赖 | 未发现（maintenance.py 只依赖 errors + transaction；dispatch.py 只依赖同层模块） |
| 魔法字符串 | 常量已提取为模块级 `_SQLITE_*` / `_HOST_WAL_*` 常量 |
| docstring | 所有新增函数/方法均有完整中文 docstring（参数、返回值、异常） |

---

## Conclusion

| Residual Risk | 建议 | 理由 |
|---|---|---|
| RR-STRESS-01 | 维持 transferred-to-issue | Issue #38 独立跟踪 |
| RR-STRESS-02 | 维持 closed | pytest-timeout 强杀 = 测试失败，非 residual risk |
| RR-DUR-02 | 维持 closed | connection/path 校验已实现并测试覆盖 |
| RR-DUR-03 | 维持 closed | 批量诊断已实现并测试覆盖 |
| RR-DUR-05 | 维持 closed | definition validation 已由 WU-LAYER-01 实现并测试覆盖 |
| RR-LIFE-01 | 维持 closed | close 窗口 cleanup 已实现并测试覆盖 |
| RR-LIFE-02 | 维持 deferred | 未变更 |
| RR-CTX-SLICED-01 | 维持 deferred | 未变更 |
| RR-LAYER-02-01 | 维持 deferred | 新增合理，不阻塞当前 PR |

**未发现误关 residual risk 或行为回归。** 仅有一处低优测试断言风格不一致（F-01）。
