# Host Phase 8 Aggregate Re-review Controller Adjudication - 2026-05-16

## Gate

当前 gate：Phase 8 aggregate re-review after accepted fix。

Aggregate review / fix artifacts：

- `docs/reviews/host-phase8-aggregate-review-mimo-20260516.md`
- `docs/reviews/host-phase8-aggregate-review-ds-20260516.md`
- `docs/reviews/host-phase8-aggregate-review-controller-adjudication-20260516.md`
- `docs/reviews/host-phase8-aggregate-fix-20260516.md`

Aggregate re-review artifacts：

- `docs/reviews/host-phase8-aggregate-re-review-mimo-20260516.md`
- `docs/reviews/host-phase8-aggregate-re-review-ds-20260516.md`

## Controller Verdict

PASS。Phase 8 aggregate review / fix / re-review gate 通过，可以进入 accepted deepreview commit gate。

MiMo 与 DS 均确认 P8-AGG-F1 与 P8-AGG-F2 已修复，P8-AGG-F3 维持 deferred，无新增 blocking finding 或 scope creep。

## Accepted Finding Verification

| Finding | Status | Evidence |
| --- | --- | --- |
| P8-AGG-F1 ProjectionRunner payload parsing failure should record failure row | fixed | 新增 `_ProjectionEventViewFailed`，`ProjectionRunner.run_once()` 捕获后写入 `host_projection_failures`；测试覆盖非 object JSON 与 invalid JSON，确认 checkpoint 不推进、failure row 指向失败 EventLog row、consumer 不被调用。 |
| P8-AGG-F2 Final Phase 8 schema version should align with plan version 5 | fixed | `HOST_SCHEMA_VERSION` 最终值为 `5`，schema bootstrap 测试期望更新为 5，Phase 8 projection / read model tables 仍全部创建。 |

## Rejected / Deferred Finding Verification

| Finding | Status | Evidence |
| --- | --- | --- |
| P8-AGG-F3 `get_run` does not consume RunResult projection | deferred | `dayu/host/read_api.py` 和 public API shape 未修改；该能力仍由 Phase 9 / Phase 15 或后续 public read enhancement owner 决定。 |

## Residual Risks And Owners

- Automatic after-commit projection catch-up：Phase 9 owner。
- Heavy sink / batch-transaction runner：Phase 13 / Phase 15 owner。
- Per-session repair filter：Phase 15 owner。
- RunResult summary refs 接入 public `RunSnapshot`：Phase 9 / Phase 15 或 public read enhancement owner。

上述 residual risks 已有 owner，不阻塞 Phase 8 accepted deepreview commit。

## Validation

AgentCodex aggregate fix validation 与 DS re-review 均执行完整 aggregate validation 并通过：

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Result：75 passed。

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result：0 errors。

```bash
git diff --check
```

Result：clean。

Controller 在 accepted deepreview commit 前需复跑上述验证。
