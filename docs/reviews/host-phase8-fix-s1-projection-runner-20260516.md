# Host Phase 8 P8-S1 Projection Runner Fix - 2026-05-16

## Gate

当前 gate：P8-S1 code review fix。

Work unit：`Projection Runner / Checkpoint / Typed Consumer Contracts`。

Source review truth：

- `docs/reviews/host-phase8-code-review-s1-controller-adjudication-20260516.md`

## Scope

本次 fix 只处理 controller accepted 的测试覆盖缺口。生产代码、plan、design、implementation-control、README、其它 review artifact、
commit、push、PR 与 next gate 均未修改。

允许写入文件：

- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md`

## Motivation Check

三个 finding 的动机成立。它们不指向生产逻辑错误，而是 checkpoint 单调推进与 schema CHECK 约束的核心不变量缺少直接回归测试。
补测试比修改生产代码更符合当前 evidence：生产实现已有 `event_sequence <= 0`、`event_sequence <= checkpoint` 与 schema CHECK 拒绝分支。

## Accepted Finding Status

### P8S1-CR-001-已修复-[中]-Duplicate checkpoint advance rejection lacks test coverage

- **修复状态**: 已修复。
- **改动文件**: `tests/host/test_projection_checkpoint.py`
- **修复内容**: 新增同一 consumer 已推进到某个 EventLog row 后，再次使用相同 `event_sequence` / `event_id` 推进时抛出 `HostDurableError` 的断言。
- **验证点**: 覆盖 `event_sequence <= checkpoint.checkpoint_event_sequence` 的重复推进分支。

### P8S1-CR-002-已修复-[中]-Non-positive checkpoint event_sequence rejection lacks test coverage

- **修复状态**: 已修复。
- **改动文件**: `tests/host/test_projection_checkpoint.py`
- **修复内容**: 新增参数化测试，覆盖 `event_sequence=0` 与 `event_sequence=-1` 调用 `advance_projection_checkpoint` 时抛出 `HostDurableError`。
- **验证点**: 覆盖 checkpoint advance 的非正输入边界。

### P8S1-CR-003-已修复-[中]-Projection checkpoint CHECK constraint branches lack direct tests

- **修复状态**: 已修复。
- **改动文件**: `tests/host/test_durable_schema.py`
- **修复内容**: 新增 EventLog probe row，并在 projection schema 约束测试中覆盖：
  - `checkpoint_event_sequence=0` 且 `checkpoint_event_id` 非空时抛出 `sqlite3.IntegrityError`。
  - `checkpoint_event_sequence>0` 且 `checkpoint_event_id` 为 `NULL` 时抛出 `sqlite3.IntegrityError`。
- **验证点**: 覆盖 checkpoint DDL 的 `(0, NULL)` / `(>0, event_id)` 组合 CHECK 不变量。

## Source Artifact Status Note

原 source review / controller adjudication artifact 不在本次允许写入范围内，因此未回写原文件标题。最终状态映射如下：

- `P8S1-CR-001`: 已修复。
- `P8S1-CR-002`: 已修复。
- `P8S1-CR-003`: 已修复。

## Validation

已执行：

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

结果：

```text
31 passed in 0.64s
```

已执行：

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

已执行：

```bash
git diff --check
```

结果：通过，无 whitespace error。

## Docs Decision

未更新 README。原因：本次只补测试与 fix artifact，未改变用户入口、开发接口、架构边界、schema 真源说明或测试运行约定；且用户明确禁止修改 README。

## Residual Risks

未发现本 fix gate 新增 residual risk。后续 P8-S2 / P8-S3 范围仍按 controller adjudication 中 deferred finding 归属推进，本次未进入 next gate。

## Stop Status

P8-S1 fix pass 已完成。按用户要求停止于 fix artifact 与 summary，不 commit、不 push、不创建 PR、不进入 re-review 或 next gate。
