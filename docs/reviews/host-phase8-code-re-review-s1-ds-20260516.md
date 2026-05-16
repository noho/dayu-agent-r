# Code Re-Review — Host Phase 8 P8-S1 Fix

## Gate

当前 gate：P8-S1 fix re-review。

验证 accepted findings P8S1-CR-001、P8S1-CR-002、P8S1-CR-003 是否已修复、修复范围内是否有 scope creep、是否有新增问题。

## Scope

- Mode: current changes (uncommitted workspace after fix)
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: `main` (HEAD: `133408a` gateflow: record host phase 8 plan state)
- Output file: `docs/reviews/host-phase8-code-re-review-s1-ds-20260516.md`
- Source adjudication: `docs/reviews/host-phase8-code-review-s1-controller-adjudication-20260516.md`
- Fix artifact: `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md`
- Original code reviews: `docs/reviews/host-phase8-code-review-s1-mimo-20260516.md`, `docs/reviews/host-phase8-code-review-s1-ds-20260516.md`
- Included scope: fix-allowed files only (`tests/host/test_projection_checkpoint.py`, `tests/host/test_durable_schema.py`)
- Excluded scope: production code, plan, design, README, other review artifacts, commit/push/PR

## Accepted Finding Verification

### P8S1-CR-001 — Duplicate checkpoint advance rejection — PASS

- **要求**: 在 `tests/host/test_projection_checkpoint.py` 增加相同 `event_sequence` 重复推进时抛出 `HostDurableError` 的断言。
- **实现**: `test_advancing_checkpoint_to_same_event_sequence_is_rejected` (test_projection_checkpoint.py:157-183)
  - 插入 EventLog row → 推进 checkpoint 至 event-1 → 再次以相同 `event_sequence` 推进。
  - 断言 `pytest.raises(HostDurableError)`。
- **证据**: 生产代码 `advance_projection_checkpoint` (durable/projection.py:163) 的 `if event_sequence <= checkpoint.checkpoint_event_sequence` 条件正确覆盖 `=` 分支。测试直接命中该分支。
- **验证**: 31 passed, pyright 0/0/0.

### P8S1-CR-002 — Non-positive event_sequence rejection — PASS

- **要求**: 在 `tests/host/test_projection_checkpoint.py` 增加 `event_sequence=0` 与负数时抛出 `HostDurableError` 的参数化测试。
- **实现**: `test_advance_checkpoint_rejects_non_positive_event_sequence` (test_projection_checkpoint.py:186-203)
  - `@pytest.mark.parametrize("event_sequence", (0, -1))` — 覆盖 0 与 -1 两个边界。
  - 断言 `pytest.raises(HostDurableError)`。
- **证据**: 生产代码 (durable/projection.py:160-161) 的 `if event_sequence <= _INITIAL_CHECKPOINT_SEQUENCE:` (`_INITIAL_CHECKPOINT_SEQUENCE=0`) 在 `ensure_projection_checkpoint` 之前先行检查，早于 FK 检查。测试不依赖 EventLog 已有 row。
- **验证**: 31 passed, pyright 0/0/0.

### P8S1-CR-003 — CHECK constraint branch tests — PASS

- **要求**: 在 `tests/host/test_durable_schema.py` 增加 `cursor=0 + event_id != NULL` 与 `cursor>0 + event_id IS NULL` 两个 CHECK 违反分支的 `IntegrityError` 断言。
- **实现**: `test_projection_schema_constraints_reject_invalid_rows` (test_durable_schema.py:299-393) 内新增两段：
  - Line 344-358: `checkpoint_event_sequence=0, checkpoint_event_id='event-1'` → `sqlite3.IntegrityError`（违反 `cursor=0 AND event_id IS NULL`）
  - Line 360-374: `checkpoint_event_sequence=1, checkpoint_event_id=NULL` → `sqlite3.IntegrityError`（违反 `cursor>0 AND event_id IS NOT NULL`）
- **证据**: 测试先通过 `_insert_event_log_probe` 插入有效 EventLog row（满足 FK），再分别触发两个 CHECK 分支。CHECK DDL 来自 schema.py `_HOST_PROJECTION_CHECKPOINTS_DDL`。
- **验证**: 31 passed, pyright 0/0/0.

## Scope Creep Check — PASS

Controller adjudication 允许的 fix 文件：

- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md`

实际 fix 变更：

| 文件 | 是否在允许范围 | 变更内容 |
|---|---|---|
| `tests/host/test_projection_checkpoint.py` | 是 | 新增 `test_advancing_checkpoint_to_same_event_sequence_is_rejected`、`test_advance_checkpoint_rejects_non_positive_event_sequence` |
| `tests/host/test_durable_schema.py` | 是 | 新增 `cursor=0+event_id` 与 `cursor>0+event_id=NULL` 两条 CHECK 违反断言 |
| `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md` | 是 | fix artifact |

未修改生产代码。`dayu/host/durable/schema.py`、`tests/README.md`、`tests/host/test_import_boundary.py` 的变更为原始 P8-S1 实现（非 fix 引入），不在 fix scope 内，不在本次 re-review 范围内。

禁止项验证：

- 未修改生产代码 ✓
- 未修改 plan、design、implementation-control、README ✓
- 未修改其他 review artifact ✓
- 未 commit、push、PR ✓

## New Issue Check — PASS

对 fix 新增代码逐行走读：

1. **P8S1-CR-001 测试 (test_projection_checkpoint.py:157-183)**
   - 入参：正常 `tmp_path` → 创建 store → 插入 EventLog row → 推进 checkpoint → 重复推进。
   - 断言：`pytest.raises(HostDurableError)` 精确匹配异常类型。
   - 无新增问题。

2. **P8S1-CR-002 测试 (test_projection_checkpoint.py:186-203)**
   - 入参：`event_sequence ∈ {0, -1}` 参数化，`event_id="event-1"`。
   - 验证顺序：生产代码先检查 `event_sequence <= 0`（line 160），早于 `ensure_projection_checkpoint`（line 162），因此不需要 EventLog 中有对应 row。测试正确依赖此顺序。
   - 无新增问题。

3. **P8S1-CR-003 测试 (test_durable_schema.py:344-374)**
   - 依赖 `_insert_event_log_probe` 创建有效 FK target（`event_id='event-1'`）。
   - cursor=0+event_id 测试：FK 满足，CHECK 不满足 → `IntegrityError`。
   - cursor=1+event_id=NULL 测试：不涉及 FK，CHECK 不满足 → `IntegrityError`。
   - 与同一测试函数中已有的负值 cursor、zero failure_count、missing FK 断言无冲突。
   - 无新增问题。

## Validation — PASS

```text
source .venv/bin/activate && pytest tests/host/test_durable_schema.py \
  tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py \
  tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
→ 31 passed in 0.62s

python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ 无 whitespace error
```

## Open Questions

无。

## Residual Risk

- **P8-S2 / P8-S3 范围**: 按 controller adjudication deferred findings 归属后续 slice，本次 re-review 不涉及。
- **测试覆盖**: 三个 accepted finding 的回归测试已到位。同一测试函数 `test_projection_schema_constraints_reject_invalid_rows` 中包含 5 条 `IntegrityError` 断言，需注意任一断言失败时后续断言不执行（pytest.raises 在 context manager 内会拦截异常）；但各断言独立，互不依赖前置状态，不影响诊断。
- **未发现本 fix gate 新增 residual risk。**

## Verdict

**PASS** — P8S1-CR-001、P8S1-CR-002、P8S1-CR-003 全部正确修复。无 scope creep，无新增问题。31 测试全 pass，pyright 零报错。
