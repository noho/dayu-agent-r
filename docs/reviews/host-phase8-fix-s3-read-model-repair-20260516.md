# Host Phase 8 P8-S3 Read Model Repair Fix - 2026-05-16

## Gate

当前 gate：P8-S3 code review fix。

Work unit：`Minimal RunResult / Session Timeline Read Model / Repair`。

Source review truth：

- `docs/reviews/host-phase8-code-review-s3-controller-adjudication-20260516.md`

## Scope

本次 fix 只处理 controller accepted 的测试覆盖缺口。生产代码、README、plan、design、implementation-control、其它 review
artifacts、commit、push、PR 与 next gate 均未修改。

允许写入文件：

- `tests/host/test_projection_read_model.py`
- `docs/reviews/host-phase8-fix-s3-read-model-repair-20260516.md`

## Motivation Check

P8S3-CR-001 的动机成立。`USER_INPUT_ACCEPTED.display_text` 是 typed payload 字段，缺失时允许投影为 `NULL`，但字段存在且为
数字或空字符串时必须失败，避免 read model consumer 静默从 raw payload 合成展示文本。本次缺口是失败路径缺少直接回归测试，
生产实现已有 `optional_payload_text` 的 `HostDurableError` 分支，因此最佳修复是只补测试，不修改生产逻辑。

## Accepted Finding Status

### P8S3-CR-001-已修复-[中]-Invalid display_text typed value failure path lacks test coverage

- **修复状态**: 已修复。
- **改动文件**: `tests/host/test_projection_read_model.py`
- **修复内容**:
  - 将测试辅助 `_append_event` 的 `run_id` 参数放宽为 `str | None`，用于构造没有 Run 外键干扰的 projection payload 边界样本。
  - 新增 `_assert_invalid_display_text_fails_without_timeline_item(...)`，集中断言非法 `display_text` 经
    `ProjectionRunner` + `MinimalReadModelProjectionConsumer` 处理后只记录 projection failure。
  - 新增数字 `display_text=123` 与空字符串 `display_text=""` 两个回归用例。
- **验证点**:
  - `ProjectionRunResult.failures == 1`。
  - `finished_cursor` 停在非法事件之前。
  - projection checkpoint 不推进到非法事件。
  - projection failure row 记录非法事件 id / sequence，错误码为 `HostDurableError`。
  - `host_session_timeline_items` 不写入非法事件对应的 timeline item。

## Source Artifact Status Note

原 source review / controller adjudication artifact 不在本次允许写入范围内，因此未回写原文件标题。最终状态映射如下：

- `P8S3-CR-001`: 已修复。

## Validation

已执行目标测试：

```bash
source .venv/bin/activate && pytest tests/host/test_projection_read_model.py -q
```

结果：

```text
9 passed in 0.24s
```

已执行 controller adjudication 要求的完整 P8-S3 pytest：

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

结果：

```text
73 passed in 0.92s
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

## Worktree Note

`tests/host/test_projection_read_model.py` 在本次 fix 开始前已是未跟踪文件；本次仅在该允许文件内追加 regression coverage。

## Residual Risks

未发现本 fix gate 新增 residual risk。P8S3-CR-002 已由 controller 裁决为 non-blocking residual observation，owner 保持为
Phase 13 / Phase 15，本次未处理。

## Stop Status

P8-S3 fix pass 已完成。按用户要求停止于 fix artifact 与 summary，不 commit、不 push、不创建 PR、不进入 re-review 或 next gate。
