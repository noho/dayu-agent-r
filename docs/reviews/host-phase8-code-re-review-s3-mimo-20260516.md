# Host Phase 8 P8-S3 Fix Re-Review - 2026-05-16

## Scope

- Mode: current changes (fix re-review)
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: P8-S2 accepted commit `c891792`
- Output file: `docs/reviews/host-phase8-code-re-review-s3-mimo-20260516.md`
- Included scope: P8-S3 fix gate changes — only `tests/host/test_projection_read_model.py`（新增 2 个 regression 用例与 1 个共享 helper）
- Excluded scope: 生产代码、README、plan、design、implementation-control、其它 review artifacts
- Parallel review coverage: 无

## Re-Review Target

Controller adjudication：`docs/reviews/host-phase8-code-review-s3-controller-adjudication-20260516.md`

Fix artifact：`docs/reviews/host-phase8-fix-s3-read-model-repair-20260516.md`

Required verification：

1. P8S3-CR-001（accepted current fix）是否已修复。
2. P8S3-CR-002（rejected-as-non-blocking / residual observation）是否未被本次 fix 触及。
3. Validation scope 是否充分。
4. 是否引入新 issue 或 scope creep。

## P8S3-CR-001 修复验证：PASS

### Finding 回顾

P8S3-CR-001 裁决：`USER_INPUT_ACCEPTED.display_text` 字段存在但为数字或空字符串时，`optional_payload_text` 抛出 `HostDurableError`，projection failure 记录，checkpoint 不推进，timeline item 不写入。生产代码已有该分支，但缺少回归测试。

### Fix 内容

新增共享 helper `_assert_invalid_display_text_fails_without_timeline_item`（`test_projection_read_model.py:335–389`）以及两个 regression 用例：

- `test_numeric_user_input_display_text_records_projection_failure`（display_text=123）
- `test_empty_user_input_display_text_records_projection_failure`（display_text=""）

### 逐项断言核查

| 裁决要求 | 断言位置 | 证据 |
|---------|---------|------|
| `ProjectionRunResult.failures == 1` | 行 378 | `assert result.failures == 1` ✓ |
| `finished_cursor` 停在非法事件之前 | 行 379 | `assert result.finished_cursor == previous_cursor`，`previous_cursor = invalid_event.event_sequence - 1` ✓ |
| checkpoint 不推进到非法事件 | 行 380–381 | `assert checkpoint is not None` 且 `checkpoint.checkpoint_event_sequence == previous_cursor` ✓ |
| failure row 记录非法事件 id / sequence / error code | 行 382–386 | `failure.failed_event_id == invalid_event.event_id`、`failed_event_sequence`、`last_error_code == "HostDurableError"`、`"display_text" in failure.last_error_message` ✓ |
| timeline item 不写入 | 行 387 | `tuple(item for item in items if item.event_id == invalid_event.event_id) == ()` ✓ |

所有 5 项验证点均通过。helper 集中在一处，两个用例覆盖数字和空字符串两种非法 typed value 路径。

### 生产代码变更核查

`git diff -- dayu/host/` 显示的生产代码变更（schema bump、DDL、read_model.py、_event_payload.py、README）与 P8-S3 original code review 一致，**fix gate 期间未新增任何生产代码变更**。`git diff --cached` 为空，无 staged 变更。

## P8S3-CR-002 状态：未触及

P8S3-CR-002 裁决为 rejected-as-non-blocking / residual observation（repair batch transaction 粒度）。本次 fix gate 未修改 `dayu/host/projection.py`、`dayu/host/read_model.py` 或任何生产代码。该 observation 状态不变，owner 保持 Phase 13 / Phase 15。

## Validation Scope 核查

Controller adjudication 要求的完整 validation：

```bash
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

结果：**73 passed in 0.96s**（原始 P8-S3 code review 时为 71 passed，新增 2 个 regression 用例）。

```bash
python -m pyright dayu/host tests/host
```

结果：**0 errors, 0 warnings, 0 informations**。

```bash
git diff --check
```

结果：通过，无 whitespace error。

## Scope Creep 检查

| 检查项 | 结果 |
|-------|------|
| 生产代码变更 | 未新增（fix gate 期间 diff 为零） |
| README 修改 | 未修改（fix artifact 已说明理由） |
| 允许文件范围 | 仅 `tests/host/test_projection_read_model.py`（+37 行：2 个 test + 1 个 helper） |
| 其它 test 文件 | 未修改 |
| plan / design / implementation-control | 未修改 |
| commit / push / PR | 未执行 |

无 scope creep。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- P8S3-CR-002（repair batch transaction 粒度）保持为 non-blocking residual observation，owner Phase 13 / Phase 15。
- `_delete_minimal_read_model_rows` helper 在 `test_public_event_stream.py` 和 `test_public_run_api.py` 中重复定义。当前两个文件不构成阻塞，未来第三个文件需要时应抽取到共享 fixture。
- `optional_payload_text` 对空字符串 `""` 走异常路径而非 NULL 路径（DS review open question）。当前行为更严格地防止静默降级，与 plan "invalid typed value fails projection" 一致，不构成阻塞。

## Conclusion

**PASS**。

P8S3-CR-001 已修复：两个 regression 用例覆盖数字和空字符串非法 `display_text` typed value 的 failure 路径，断言完整覆盖 controller adjudication 要求的全部 5 个验证点。P8S3-CR-002 未被触及，状态不变。Validation scope 充分（73 tests pass、pyright clean、无 whitespace error）。未引入新 issue 或 scope creep。
