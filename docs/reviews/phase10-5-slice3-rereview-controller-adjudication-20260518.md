# P10.5 Slice 3 Re-review Controller Adjudication

## Gate

P10.5 Slice 3 re-review。

## Inputs

- MiMo re-review：`docs/reviews/phase10-5-slice3-rereview-mimo-20260518.md`
- DS re-review：`docs/reviews/phase10-5-slice3-rereview-ds-20260518.md`
- Slice 3 fix：`docs/reviews/phase10-5-slice3-fix-codex-20260518.md`
- Controller code-review adjudication：`docs/reviews/phase10-5-slice3-code-review-controller-adjudication-20260518.md`

## Verdict

不接受进入 Slice 3 accepted slice commit。当前进入 P10.5 Slice 3 follow-up fix。

MiMo 结论为 PASS，blocking count = 0。DS 结论为 PASS，blocking count = 0，但 DS 在复审中额外发现既有 admission / projection read-model 测试因 `ordinary_run_baseline=None` 失败。Controller 本地复跑确认：

```text
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_projection_read_model.py -q --tb=short
-> 17 failed, 19 passed
```

失败根因同源：Slice 3 让 `HostAdmissionService.submit_followup_queue(...)` 在 admission 前解析 per-run effective execution config，并要求 `ordinary_run_baseline` 存在；既有低层 admission service / command handle 测试 helper 未随实现边界迁移，因此 `submit_followup` 路径在 admission 阶段抛 `HostApiErrorCode.INVALID_STATE`。

该问题不是生产 public `open_host(...)` contract 的缺口，但它是本 slice 修改触及的既有测试边界破损。按项目验证约束，不能把受影响既有测试失败带入 accepted slice commit。

## Accepted Follow-up Fix

### F1. 迁移受影响低层测试 helper 到新的 admission baseline 边界

- 修改 `tests/host/test_admission_queue.py` 中构造 `HostAdmissionService` 的 helper，使正常 queue / promotion / cancel / closeout 测试显式提供 `ordinary_run_baseline`，必要时提供空或当前语义等价的 `tooling_options`。
- 修改 `tests/host/test_projection_read_model.py` 中受影响 command handle / service helper，使正常 follow-up 路径具备 ordinary baseline。
- 不删除 `tests/host/test_effective_execution_config.py::test_submit_followup_without_ordinary_baseline_fails_before_dispatch`；该测试继续覆盖无 baseline 的 fail-early 低层 misuse contract。

### F2. 修正 fix artifact residual risk

- 更新 `docs/reviews/phase10-5-slice3-fix-codex-20260518.md`，记录本次补充修复：既有低层测试 helper 已迁移到 baseline 边界；无 baseline fail-early 仍由 dedicated misuse test 覆盖。

## Allowed Scope

- `tests/host/test_admission_queue.py`
- `tests/host/test_projection_read_model.py`
- 必要时复用或新增测试内私有 helper
- `docs/reviews/phase10-5-slice3-fix-codex-20260518.md`

禁止修改生产代码、public API、payload shape、digest/ref、durable schema、state machine、README。

## Required Validation

```text
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_projection_read_model.py tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

修复后重新进入 Slice 3 re-review。
