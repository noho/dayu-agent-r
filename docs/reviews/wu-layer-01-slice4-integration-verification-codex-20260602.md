# WU-LAYER-01 Slice 4 Integration Verification / README Sync

## Changed Files

- `dayu/host/README.md`
  - 更新 Host durable foundation bullet，说明当前 schema validation 校验 schema version、required object 存在性与 required object 定义一致性。
- `tests/host/test_run_attempt_transitions.py`
  - 聚合验证暴露 Slice 3 row decode boundary 与两个 corrupted Run CAS guard 测试未同步。测试已改为断言 CAS 拒绝 corrupted row 后读取边界触发 `HostRowDecodeError`，与 Slice 3 已同步的 WaitRecord corrupted CAS 测试语义一致。
- `docs/reviews/wu-layer-01-slice4-integration-verification-codex-20260602.md`
  - 本 Slice 4 verification report。

说明：`docs/host/host-core-followup-implementation-control.md` 是 controller 状态推进文件，不属于本 Slice 4 实现质量主体；Slice 4 期间该文件由 controller 更新状态到 review gate。

## README/doc sync decision

- `dayu/host/README.md`: updated。
- 决策理由：原 durable foundation bullet 中“完整当前 schema validation”方向仍正确，但 Slice 1 已把 current schema validation 稳定扩展为 schema version、required object existence、required object definition validation。该能力属于 Host durable foundation 的稳定开发手册信息，因此只更新 Host README 对应 bullet，不写实现细节。
- 未更新根目录 `README.md`、`dayu/README.md`、`tests/README.md`：本轮没有改变 public usage、layering 关系或测试约定。

## Validation Output Summary

首次聚合验证暴露 2 个测试边界回归：

```text
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py
2 failed, 134 passed in 1.31s
```

失败项：

```text
tests/host/test_run_attempt_transitions.py::test_cancel_queued_run_row_requires_empty_terminal_refs
tests/host/test_run_attempt_transitions.py::test_cancel_running_run_row_requires_empty_terminal_refs
```

修正后 focused verification：

```text
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py::test_cancel_queued_run_row_requires_empty_terminal_refs tests/host/test_run_attempt_transitions.py::test_cancel_running_run_row_requires_empty_terminal_refs
2 passed in 0.29s
```

最终聚合验证：

```text
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py
136 passed in 1.17s
```

类型验证：

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

## Residual Risks / Uncovered Areas

- 未运行全量 pytest；本 slice 按计划运行了指定 Host 聚合验证与 full pyright。
- 本轮没有修改生产源码。测试同步只覆盖聚合验证暴露的 corrupted Run CAS guard 与 Slice 3 row decode boundary 不一致问题。
- `pyright` 输出提示存在新版本 `v1.1.410`，当前验证仍在项目环境版本 `v1.1.409` 下通过。

## Completion Status

Slice 4 integration verification complete. Host README 已完成必要同步，聚合 pytest 与 pyright 均通过。未 commit、未 push。
