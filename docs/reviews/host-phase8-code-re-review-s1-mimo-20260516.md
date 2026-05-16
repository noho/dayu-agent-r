# Code Re-Review — P8-S1 Fix Verification

## Scope

- Mode: current changes (fix re-review)
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: fix artifact `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md`
- Source adjudication: `docs/reviews/host-phase8-code-review-s1-controller-adjudication-20260516.md`
- Original reviews: `host-phase8-code-review-s1-mimo-20260516.md`, `host-phase8-code-review-s1-ds-20260516.md`
- Output file: `docs/reviews/host-phase8-code-re-review-s1-mimo-20260516.md`
- Included scope: fix-allowed files (`tests/host/test_projection_checkpoint.py`, `tests/host/test_durable_schema.py`) + 全 workspace 变更 scope creep 检查
- Excluded scope: 生产代码修改、plan/design/README 修改、commit/push/PR
- Parallel review coverage: 无

## Verdict

**PASS** — 三个 accepted findings 全部已修复，验证范围充分，未引入新问题或 scope creep。

---

## Finding Verification

### P8S1-CR-001: Duplicate checkpoint advance rejection — FIXED

**裁决要求**: 在 `tests/host/test_projection_checkpoint.py` 增加重复推进同一 `event_sequence` 时抛出 `HostDurableError` 的断言。

**修复证据**:

- 新增测试函数 `test_advancing_checkpoint_to_same_event_sequence_is_rejected` (行 157-183)
- 测试逻辑：先推进 checkpoint 到 `event-1` 的 `event_sequence`，再用相同 `event_sequence` / `event_id` 尝试推进，断言 `pytest.raises(HostDurableError)`
- 覆盖的生产代码分支：`projection.py:163` — `if event_sequence <= checkpoint.checkpoint_event_sequence` 的 `==` 子条件

**验证结论**: 覆盖精确，断言正确。**FIXED**。

### P8S1-CR-002: Non-positive event_sequence rejection — FIXED

**裁决要求**: 增加 `event_sequence=0` 与负数时抛出 `HostDurableError` 的参数化测试。

**修复证据**:

- 新增测试函数 `test_advance_checkpoint_rejects_non_positive_event_sequence` (行 186-203)
- 使用 `@pytest.mark.parametrize("event_sequence", (0, -1))` 覆盖零值与负值
- 覆盖的生产代码分支：`projection.py:160` — `if event_sequence <= _INITIAL_CHECKPOINT_SEQUENCE`

**验证结论**: 参数化覆盖完整，断言正确。**FIXED**。

### P8S1-CR-003: Projection checkpoint CHECK constraint branches — FIXED

**裁决要求**: 在 `tests/host/test_durable_schema.py` 增加两个 `sqlite3.IntegrityError` 断言，覆盖 `cursor=0 + event_id != NULL` 和 `cursor>0 + event_id IS NULL` 两个 CHECK 违反分支。

**修复证据**:

- 在 `test_projection_schema_constraints_reject_invalid_rows` 中新增两个 INSERT 断言 (行 344-375)
- 断言 1 (行 344-359): `checkpoint_event_sequence=0, checkpoint_event_id='event-1'` → `IntegrityError` — 覆盖 DDL `CHECK ((checkpoint_event_sequence = 0 AND checkpoint_event_id IS NULL) OR ...)` 的第一个分支违反
- 断言 2 (行 360-375): `checkpoint_event_sequence=1, checkpoint_event_id=NULL` → `IntegrityError` — 覆盖 DDL `CHECK (... OR (checkpoint_event_sequence > 0 AND checkpoint_event_id IS NOT NULL))` 的第二个分支违反
- 辅助：新增 `_insert_event_log_probe` helper (行 98-131) 提供 FK 目标 row，确保 FK 约束不干扰 CHECK 约束验证

**验证结论**: 两个 CHECK 分支均被直接覆盖，DDL 约束 `(schema.py:565-569)` 与测试 INSERT 精确匹配。**FIXED**。

---

## Validation

| 验证项 | 结果 | 证据 |
|---|---|---|
| `pytest ... -q` | **31 passed in 0.64s** | 全部通过 |
| `pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** | 无类型错误 |
| `git diff --check` | **通过** | 无 whitespace error |

---

## Scope Creep 检查

### Fix 允许写入文件 vs 实际修改

| 文件 | Fix 允许 | 实际状态 | 判定 |
|---|---|---|---|
| `tests/host/test_projection_checkpoint.py` | 是 | 新增 3 个测试函数 | 合规 |
| `tests/host/test_durable_schema.py` | 是 | 新增 `_insert_event_log_probe`、`test_projection_checkpoint_and_failure_tables_are_created`、`test_projection_schema_constraints_reject_invalid_rows`（含 CR-003 修复）、`test_event_sequence_is_sqlite_foreign_key_parent_key`、`test_schema_does_not_create_future_sink_tables` | 合规 |
| `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md` | 是 | 已写入 | 合规 |
| 生产代码 | 禁止 | 未修改 | 合规 |
| plan/design/README | 禁止 | 未修改 | 合规 |

### Workspace 中非 fix 变更

以下文件在 workspace 中有未提交变更，但它们属于 P8-S1 implementation scope（已在原始 code review 中通过），不属于本次 fix scope：

- `dayu/host/durable/schema.py` — schema bump 与 projection DDL
- `dayu/host/durable/projection.py` — projection checkpoint/failure 持久化
- `dayu/host/projection.py` — ProjectionRunner / ProjectionEventFilter
- `tests/host/test_projection_runner.py` — runner 测试
- `tests/host/test_import_boundary.py` — import boundary 守卫
- `tests/README.md` — 测试手册更新

这些变更不构成 scope creep，因为它们是 implementation artifact 的一部分，已在原始 review 中审查通过。

---

## 新增测试质量审查

修复新增的 3 个测试函数/参数化覆盖了以下行为：

1. **单调性守卫**: `event_sequence <= checkpoint.checkpoint_event_sequence` 的 `==` 分支（CR-001）
2. **输入边界守卫**: `event_sequence <= 0` 的防御分支（CR-002）
3. **DDL 约束守卫**: checkpoint 表的 `(0, NULL)` / `(>0, event_id)` 组合 CHECK（CR-003）

测试不覆盖 happy path（已有其它测试覆盖），只覆盖拒绝路径，符合 fix scope 要求。断言均为 `pytest.raises` 精确异常类型，无弱断言。

---

## Open Questions

无。

## Residual Risk

- 无新增 residual risk。修复仅补充测试，不改变生产行为。
- 原始 review 中标记的 deferred items（P8-S2/P8-S3 scope）不受本次 fix 影响。
