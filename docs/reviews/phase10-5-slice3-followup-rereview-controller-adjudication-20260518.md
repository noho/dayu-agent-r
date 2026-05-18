# P10.5 Slice 3 Follow-up Re-review Controller Adjudication

## Gate

P10.5 Slice 3 follow-up re-review。

## Inputs

- MiMo follow-up re-review：`docs/reviews/phase10-5-slice3-followup-rereview-mimo-20260518.md`
- DS follow-up re-review：`docs/reviews/phase10-5-slice3-followup-rereview-ds-20260518.md`
- Controller re-review adjudication：`docs/reviews/phase10-5-slice3-rereview-controller-adjudication-20260518.md`
- Updated fix artifact：`docs/reviews/phase10-5-slice3-fix-codex-20260518.md`

## Verdict

接受 P10.5 Slice 3。进入 Slice 3 accepted slice commit。

MiMo follow-up re-review：PASS，blocking count = 0。

DS follow-up re-review：PASS，blocking count = 0。

## Accepted Fix Verification

- `tests/host/test_admission_queue.py` 的 `_service()` helper 已显式注入 `OrdinaryRunExecutionBaseline`，正常 queue / promotion / cancel / closeout 测试继续断言原有 durable admission 行为。
- `tests/host/test_projection_read_model.py` 只在两个正常 `submit_followup` read-model 测试中使用 baseline-aware test handle，未修改生产 `create_host_command_handle(...)` 或 public API。
- 无 baseline misuse contract 仍由 `tests/host/test_effective_execution_config.py::test_submit_followup_without_ordinary_baseline_fails_before_dispatch` 覆盖。
- `docs/reviews/phase10-5-slice3-fix-codex-20260518.md` 已补充 follow-up fix 与 residual risk。

## Validation Evidence

Controller 本地验证：

```text
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_projection_read_model.py tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
-> 47 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
-> 0 errors, 0 warnings, 0 informations
```

## Residual Risk

- P10.5 Slice 3 不覆盖 steer / retry / replay / live watch / real runner smoke；这些仍按 accepted plan 归后续 slices。
- 本 slice 未改 durable schema、Engine、Service、UI 或 Fins。
