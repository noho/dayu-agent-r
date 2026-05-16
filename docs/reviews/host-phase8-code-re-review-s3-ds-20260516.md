# Code Re-Review — P8-S3 Fix Verification

## Scope

- Mode: current changes（P8-S3 fix re-review）
- Branch: `feat/host-phase8-projection-core-event-stream`
- Gate: P8-S3 fix re-review
- Source adjudication: `docs/reviews/host-phase8-code-review-s3-controller-adjudication-20260516.md`
- Fix artifact: `docs/reviews/host-phase8-fix-s3-read-model-repair-20260516.md`
- Original reviews: `docs/reviews/host-phase8-code-review-s3-mimo-20260516.md`, `docs/reviews/host-phase8-code-review-s3-ds-20260516.md`
- Output file: `docs/reviews/host-phase8-code-re-review-s3-ds-20260516.md`
- Included scope: `tests/host/test_projection_read_model.py`（fix 允许的唯一修改文件）、所有生产代码文件（只读验证未修改）
- Excluded scope: Engine, runtime, Service, UI, Fins, command path, dispatch
- Parallel review coverage: 无

## Re-Review Objective

验证 controller adjudication 的 accepted finding P8S3-CR-001 已正确修复；
确认 P8S3-CR-002 保持 non-blocking residual observation 状态；
确认 fix 未引入 scope creep 或新问题；
确认 validation scope 充足。

## Accepted Finding Status

### P8S3-CR-001: Invalid display_text typed value failure path lacks test coverage — **PASS（已修复）**

**原始 finding**（DS 001）：`optional_payload_text` 对数字、空字符串等非法 typed value 的 `HostDurableError` 路径缺少回归测试。

**Controller 修复要求**：
1. `result.failures == 1`
2. `finished_cursor` 停在非法事件之前
3. checkpoint 不推进到非法事件
4. failure row 记录非法 event_id / sequence，error_code 为 `HostDurableError`
5. timeline 不写入非法事件对应的 item

**修复内容**（`tests/host/test_projection_read_model.py`）：

- `_append_event` helper 的 `run_id` 参数从 `str` 放宽为 `str | None`（line 200），用于构造无 Run FK 干扰的 projection payload 边界样本。
- 新增 `_assert_invalid_display_text_fails_without_timeline_item(...)` 集中断言辅助函数（lines 335–389）。
- 新增 `test_numeric_user_input_display_text_records_projection_failure`（lines 553–567）：`display_text=123`。
- 新增 `test_empty_user_input_display_text_records_projection_failure`（lines 570–584）：`display_text=""`。

**断言覆盖逐条验证**：

| # | Controller 要求 | 断言位置 | 证据 |
|---|----------------|---------|------|
| 1 | `result.failures == 1` | line 378 | `run_once` 在 `_ProjectionApplyFailed` 捕获后 `failures += 1`（projection.py:374） |
| 2 | `finished_cursor == previous_cursor` | line 379 | `run_once` 的 `finished_cursor` 只在 `run_write` 成功返回后更新（projection.py:376）；失败 event 的 transaction rollback 后不更新 |
| 3 | checkpoint 不推进 | line 381 | `advance_projection_checkpoint`（projection.py:482）在 `apply_event` 成功后才执行；`apply_event` 抛异常 → transaction rollback → checkpoint 不变 |
| 4 | failure row 记录正确 | lines 383–386 | `_record_failure`（projection.py:517–527）用新独立事务写入 `failed_event_id`、`failed_event_sequence`、`error_code=exception.__class__.__name__`（`"HostDurableError"`）、`error_message=str(exception)`（含 `"display_text"`） |
| 5 | timeline 不写入非法事件 | line 387 | `insert_session_timeline_item_if_absent` 在 `_display_text` 抛异常前未执行；`SessionTimelineItemRow` 构造时 Python 先求值 `_display_text(event)` 参数，异常在 INSERT 前抛出 |

**非法值覆盖**：
- 数字 `123`：`optional_payload_text` 中 `isinstance(123, str)` → `False` → 抛 `HostDurableError`（_event_payload.py:412）
- 空字符串 `""`：`isinstance("", str)` → `True` 但 `"".strip() != ""` → `False` → 抛 `HostDurableError`（_event_payload.py:412）

**结论**：P8S3-CR-001 已完整修复，5 项 controller 要求全部有直接断言覆盖，2 个非法值类型均覆盖。**PASS**。

### P8S3-CR-002: repair batch transaction granularity differs mildly from plan wording — **PASS（保持 non-blocking residual）**

**原始 finding**（DS 002）：`repair_minimal_read_models` 的 batch 语义为逐事件独立事务，与 plan 措辞"每批独立 transaction"存在温和偏差。

**Controller 裁决**：rejected-as-non-blocking / accepted as residual observation。P8-S3 不允许修改 `dayu/host/projection.py`。

**Re-review 验证**：
- `dayu/host/projection.py` 不在 `git status` 的 modified 或 untracked 列表中。
- `dayu/host/projection.py` 不在 `git diff` 输出中。
- 生产代码未在 fix 阶段被修改。
- 该 finding 的 residual risk owner 仍为 Phase 13 / Phase 15。

**结论**：P8S3-CR-002 保持 controller 裁决的 non-blocking residual observation 状态，未在本次 fix 中处理。**PASS**。

## Findings

未发现实质性问题。

## Adversarial Failure Pass

对 fix 变更执行了以下 adversarial 检查，均通过：

### 测试逻辑正确性
- `_assert_invalid_display_text_fails_without_timeline_item` 创建独立 Host（fresh SQLite），无测试间状态泄漏。
- `previous_cursor = invalid_event.event_sequence - 1` 在所有场景下正确：无论 `ensure_session` 是否产生中间 EventLog rows，`run_once` 对非匹配事件会推进 checkpoint（projection.py:376 在 `matched=False` 的 `continue` 之前更新），只有投影失败时 checkpoint 不推进。
- `_record_failure` 使用独立写事务（projection.py:517），不依赖已回滚事务的状态。
- `read_projection_checkpoint` / `read_projection_failure` / `read_session_timeline_items` 各自在独立 `run_write` 中读取，互不干扰。

### 非法值边界覆盖
- 数字 `123`：覆盖 `isinstance(value, str)` 为 `False` 的分支。
- 空字符串 `""`：覆盖 `isinstance(value, str)` 为 `True` 但 `value.strip() != ""` 为 `False` 的分支。
- 缺失字段（`None`）路径已在既有测试 `test_user_input_timeline_preserves_repeated_text_and_null_fallback` 中覆盖。
- 合法非空字符串路径已在既有测试中覆盖。

### 测试辅助变更安全性
- `_append_event` 的 `run_id: str | None` 放宽仅影响测试 helper；所有既有调用方传递 `str`，完全向后兼容。
- `EventLogAppendRequest.run_id` 接受 `str | None`（由 73 个测试全量通过证实）。

### Scope Creep 检查
- `tests/host/test_projection_read_model.py` 是唯一在 fix 阶段修改的文件。
- 生产代码（`_event_payload.py`、`durable/schema.py`、`durable/read_model.py`、`read_model.py`）未在 fix 阶段被修改——其内容与 DS 原始 review 描述一致。
- README、plan、design、implementation-control、其它 review artifacts 未修改。
- 无 commit、push、PR 或 next gate 推进。

### 参数生效链
- `display_text: JsonValue` 参数从测试函数 → `_assert_invalid_display_text_fails_without_timeline_item` → `_append_event(..., payload={"display_text": display_text})` → `EventLogAppendRequest.payload_json` → SQLite → `ProjectionRunner` 读取 → `event.payload` → `optional_payload_text(event.payload, field_name="display_text")`。全程无覆盖、无丢失、无静默默认值。

## Open Questions

无。

## Residual Risk

- P8S3-CR-002（repair batch transaction granularity）仍为 non-blocking residual observation，owner Phase 13 / Phase 15。本次 fix 未改变其风险等级。
- `_assert_invalid_display_text_fails_without_timeline_item` 使用 `host._transaction_runner()` 私有 API，与同文件其它测试一致，不引入新风险。
- 未覆盖的非法 `display_text` 类型（如 `[]`、`{}`、`True`、`3.14`）均落入相同的 `isinstance(value, str) and value.strip() != ""` 为 `False` 分支，与已覆盖的数字/空字符串共享同一错误路径，无需额外测试。

## Validation Results

独立执行 controller adjudication 要求的验证命令：

```bash
pytest tests/host/test_durable_schema.py \
       tests/host/test_projection_checkpoint.py \
       tests/host/test_projection_runner.py \
       tests/host/test_projection_read_model.py \
       tests/host/test_public_event_stream.py \
       tests/host/test_public_run_api.py \
       tests/host/test_public_session_api.py \
       tests/host/test_package_exports.py \
       tests/host/test_import_boundary.py \
       tests/host/test_weak_typing_guard.py -q
```

结果：**73 passed in 1.01s**

```bash
python -m pyright dayu/host tests/host
```

结果：**0 errors, 0 warnings, 0 informations**

```bash
git diff --check
```

结果：**通过，无 whitespace error**

## Review Conclusion

**PASS**。P8S3-CR-001 已正确修复：5 项 controller 要求的断言全部有直接证据覆盖，2 个非法值类型（数字、空字符串）均有独立回归用例；失败路径沿 `optional_payload_text → _display_text → _project_timeline_item → apply_event → _process_next_event → run_once` 完整闭环验证。P8S3-CR-002 保持 non-blocking residual observation 状态，`dayu/host/projection.py` 未被修改。无 scope creep，无新增 finding，无性能退化，类型检查与测试全量通过。
