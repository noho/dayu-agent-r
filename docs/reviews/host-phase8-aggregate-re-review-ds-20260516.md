# Host Phase 8 Aggregate Fix Re-Review

## Scope

- Mode: current changes (aggregate fix re-review)
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: HEAD `8b538f5`
- Output file: `docs/reviews/host-phase8-aggregate-re-review-ds-20260516.md`
- Review target: current uncommitted workspace after aggregate fix (4 modified files)
- Source adjudication: `docs/reviews/host-phase8-aggregate-review-controller-adjudication-20260516.md`
- Fix artifact: `docs/reviews/host-phase8-aggregate-fix-20260516.md`
- Original aggregate reviews: `docs/reviews/host-phase8-aggregate-review-mimo-20260516.md` and `docs/reviews/host-phase8-aggregate-review-ds-20260516.md`
- Included scope:
  - `dayu/host/projection.py` — P8-AGG-F1 fix: `_ProjectionEventViewFailed` exception + `run_once` / `_process_next_event` / `_record_failure` changes
  - `dayu/host/durable/schema.py` — P8-AGG-F2 fix: `HOST_SCHEMA_VERSION` 6→5, docstring update
  - `tests/host/test_projection_runner.py` — P8-AGG-F1 test: parametrized `test_payload_parsing_failure_records_failure_without_advancing_checkpoint`, `_replace_event_payload_json` helper
  - `tests/host/test_durable_schema.py` — P8-AGG-F2 test: version assertion update, test function rename phase7→phase8
- Excluded scope: Engine, runtime, service, ui, fins; command path, admission, waiting, dispatch, recovery; public read API; README; commits
- Review method: full path tracing of fix code; adversarial failure pass on new exception flow, checkpoint invariants, transaction boundaries; scope creep scan

## Re-Review Verdict

**PASS** — P8-AGG-F1 和 P8-AGG-F2 均已正确修复，P8-AGG-F3 保持 deferred，无新增 issue 或 scope creep。

## Findings

### 逐项验证

#### P8-AGG-F1: ProjectionRunner payload parsing failure should record failure row ✅ 已修复

修复路径追踪（`dayu/host/projection.py`）：

1. **内部控制流异常定义** (`projection.py:307-325`)：新增 `_ProjectionEventViewFailed(Exception)`，携带 `event_row: EventLogRow` 和 `original_exception: HostDurableError`。类型标注精确，与 `_ProjectionApplyFailed` 平行的内部控制流模式。

2. **payload 解析异常捕获** (`projection.py:511-515`)：`_process_next_event()` 中 `projection_event_view_from_row(row)` 调用外包 `try/except HostDurableError`，捕获后 raise `_ProjectionEventViewFailed(row, exc) from exc`。异常链保留（`from exc`），root cause 不丢失。

3. **run_once 异常处理** (`projection.py:404-412`)：新增 `except _ProjectionEventViewFailed` 分支，调用 `_record_failure()` 写入 failure row，`failures += 1`，`break` 停止批次。与 `_ProjectionApplyFailed` 处理对称。

4. **`_record_failure` 签名重构** (`projection.py:540-556`)：从接收 `ProjectionEventView` 改为接收 `event_sequence: int` + `event_id: str`。两个 failure 路径（apply failure 和 view failure）通过各自的异常对象访问不同来源的相同字段（`exc.event.event_sequence` / `exc.event_row.event_sequence`），统一写入 `host_projection_failures`。

不变式验证：

- **checkpoint 不推进**：`_ProjectionEventViewFailed` 在 `_process_next_event()` 中抛出，该异常被 `run_write` 回滚原事务，checkpoint advance 未执行。测试断言 `checkpoint.checkpoint_event_sequence == 0`（line 512）。
- **failure row 指向失败 row**：`_record_failure` 使用 `exc.event_row.event_sequence` 和 `exc.event_row.event_id`，即原始 `EventLogRow` 的标识。测试断言 `failure.failed_event_sequence == event.event_sequence` 和 `failure.failed_event_id == event.event_id`（lines 514-515）。
- **consumer 未被调用**：`projection_event_view_from_row()` 失败后直接进入 except，`consumer.event_filter.matches()` 和 `consumer.apply_event()` 均未执行。测试断言 `consumer.applied_events == []`（line 510）。
- **caller 不收透传异常**：`run_once()` 内部捕获 `_ProjectionEventViewFailed` 后正常返回 `ProjectionRunResult`。caller 仅通过 `result.failures == 1` 感知失败。
- **不影响 apply failure 路径**：`_ProjectionApplyFailed` 分支仅修改了 `_record_failure` 调用签名（`exc.event` → `exc.event.event_sequence` / `exc.event.event_id`），语义等价。

测试覆盖（`tests/host/test_projection_runner.py:469-517`）：

- 两参数化用例：非 object JSON `"[]"` 和非法 JSON `"{"`，分别对应 `payload_object()` 的两个 `HostDurableError` 分支。
- 断言覆盖：`result.failures`、`result.finished_cursor`、`result.events_scanned`、consumer 调用、checkpoint 值、failure row 各字段。
- 测试辅助函数 `_replace_event_payload_json`（`test_projection_runner.py:177-200`）使用参数化 SQL，安全地模拟 corrupt EventLog row。

#### P8-AGG-F2: Final Phase 8 schema version should align with plan version 5 ✅ 已修复

修复追踪：

1. **`HOST_SCHEMA_VERSION`** (`schema.py:25`)：`6` → `5`。
2. **测试期望** (`test_durable_schema.py:150-151`)：`PRAGMA user_version == 5`，`HOST_SCHEMA_VERSION == 5`。
3. **测试函数重命名** (`test_durable_schema.py:141`)：`test_fresh_db_creates_foundation_and_phase7_tables` → `test_fresh_db_creates_foundation_and_phase8_tables`。修正预存的命名错误（Phase 7 应改为 Phase 8）。
4. **模块 docstring** (`schema.py:1-7`)：从排除列表中移除 `projection`，添加"以及 Phase 8 projection / read model tables"。
5. **Phase 8 DDL 保留**：`PROJECTION_TABLES` 和 `HOST_DURABLE_TABLES` 不变，fresh bootstrap 仍创建所有 Phase 8 表。

验证：

- `test_fresh_db_creates_foundation_and_phase8_tables` 断言 fresh DB `PRAGMA user_version == 5` 且 Phase 8 表存在于 `HOST_DURABLE_TABLES` 中。
- `test_projection_checkpoint_and_failure_tables_are_created` 继续断言 Phase 8 projection / read model tables 存在。

#### P8-AGG-F3: `get_run` does not consume RunResult projection ✅ 保持 deferred

- `dayu/host/read_api.py`、`dayu/host/api.py` 均未在本次修改中出现（`git diff HEAD --name-only` 仅 4 文件）。
- 与 controller adjudication "rejected-as-current-fix / deferred" 一致。

### 新增 issue 检查

无新增 issue。

#### 交易边界正确性

`_record_failure()` 通过 `self._transaction_runner.run_write(...)` 打开**新**独立写事务写入 failure row。两个 failure 路径（`_ProjectionApplyFailed`、`_ProjectionEventViewFailed`）均在 `run_write` 外被捕获，原事务已回滚。failure row 写入与 checkpoint advance 不在同一事务——这是有意设计：原事务回滚确保 checkpoint 不推进，新事务独立写入 failure row 提供 durable 诊断。

#### 异常链完整性

`_ProjectionEventViewFailed(row, exc) from exc` 保留原始 `HostDurableError` 为 `__cause__`，`_record_failure` 通过 `str(exception)` 和 `exception.__class__.__name__` 提取错误信息。两个 failure 路径均使用相同的 `error_code` / `error_message` 提取逻辑，不会因异常类型不同而产生不一致的 failure row。

#### 参数有效性

`_record_failure` 新增的 `event_sequence: int` 和 `event_id: str` 为 keyword-only 参数，调用方必须显式指定，避免传参位置错误。两个调用点均从异常对象中直接读取 `event_sequence` / `event_id`，来源链路清晰：`exc.event.event_sequence`（来自 `ProjectionEventView`）和 `exc.event_row.event_sequence`（来自 `EventLogRow`）。

#### 无 scope creep

- 仅修改 controller adjudication 允许的 4 个文件。
- 未修改 Engine、runtime、service、ui、fins。
- 未修改 command path、admission、waiting、dispatch、recovery。
- 未修改 public read API shape。
- 未修改 README。
- `test_durable_schema.py` 函数重命名（phase7→phase8）是修正预存命名错误，属于 schema version fix 的合理附带修正。

## Validation

独立验证结果：

```
75 passed in 0.92s
0 errors, 0 warnings, 0 informations
```

与 fix artifact 声称一致。

## Open Questions

无。

## Residual Risk

1. **Corrupt EventLog payload 的防御范围**：当前仅防御 `projection_event_view_from_row()` 抛出的 `HostDurableError`（即 `payload_object()` 的非 object / 非法 JSON 场景）。`optional_payload_text()` 对非字符串 display_text 也抛出 `HostDurableError`，但该调用发生在 `MinimalReadModelProjectionConsumer.apply_event()` 内，已由 `_ProjectionApplyFailed` 路径覆盖。两个场景均有 failure row 写入和 checkpoint 不推进保护。无遗漏。

2. **`get_run` 未消费 RunResult projection**：按 controller adjudication deferred，owner 为 Phase 9 / Phase 15。

3. **Automatic after-commit projection catch-up**：deferred to Phase 9 owner。

4. **Heavy sink / batch-transaction runner**：deferred to Phase 13 / Phase 15 owner。

5. **Per-session repair filter**：deferred to Phase 15 owner。
