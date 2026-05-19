# Phase 11 Slice 3 Fix — AgentCodex

## Scope

- 角色：Phase 11 Slice 3 fix specialist
- 输入 review：
  - `docs/reviews/phase11-slice3-code-review-mimo-20260519.md`
  - `docs/reviews/phase11-slice3-code-review-ds-20260519.md`
- Controller 裁决：
  - `docs/reviews/phase11-slice3-code-review-controller-adjudication-20260519.md`
- 限定范围：只修 controller-accepted findings；未提交、未 push、未创建 PR、未进入下一 slice。

## Per-Finding Status

### MiMo 001：`dayu.host.recovery` 模块 docstring stale

状态：FIXED

处理：

- 更新 `dayu/host/recovery.py` 模块 docstring，使其描述当前 Slice 3 职责：
  - startup scan；
  - positive orphan closeout；
  - recovery Attempt / execution / pending dispatch record 创建；
  - commit 后 scheduler wake；
  - 仍不直接调用 WorkerProxy、不读取 projection/read-model。

### DS 1：orphan closeout 成功但 recovery dispatch 创建返回 `INVALID_STATE`

状态：FIXED

处理：

- 保持 durable mutation 语义不变。
- 在 `_close_positive_orphan` 中，当 orphan closeout 已成功提交到事务内状态，后续 recovery dispatch 创建 action 为 `INVALID_STATE` 时，scanner 返回 `RECOVERING_READY`，reason 为 `startup_recovery_dispatch_pending_follow_up`。
- 新增聚焦测试，通过 monkeypatch 让 recovery dispatch 创建 helper 返回 `INVALID_STATE`，验证：
  - scanner action 为 `RECOVERING_READY`；
  - action status 反映当前 Run 已为 `RECOVERING`；
  - 不产生 pending dispatch wake；
  - orphan closeout 的 `ATTEMPT_LOST` 与 `RUN_RECOVERING` durable facts 已写入；
  - 未创建新的 recovery `RUN_STARTED`。

### DS 2：`lose_recovering_run_in_transaction` precondition

状态：NO_ACTION

处理：

- 按 controller 裁决，该项已关闭为 sufficient。
- 未修改 `lose_recovering_run_in_transaction`，未改变 RECOVERING lost/cancel 语义。

## Changed Files

- `dayu/host/recovery.py`
- `tests/host/test_recovery_dispatch.py`
- `docs/reviews/phase11-slice3-fix-codex-20260519.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_recovery_dispatch.py tests/host/test_run_input_builder.py tests/host/test_open_host_runtime.py -q`
  - PASS：40 passed in 0.48s
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - PASS：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - PASS

## New Risks / Open Questions

- 新增逻辑只改变 scan action 的可观测分类，不改变 durable closeout 或 recovery dispatch helper 的写入语义。
- 若 recovery dispatch helper 在 append EventLog 后通过异常触发事务回滚，该路径仍由 durable transition helper 的既有事务保护处理；本次 fix 未改变该语义。
- 未覆盖多进程并发 scan；该项仍属于后续 slice 范围。
- 未实现 RECOVERING cancel；该项仍属于 Slice 4 范围。

## Conclusion

FIX_COMPLETE
