# WU-STRESS-01 PR Fix Artifact - AgentCodex - 2026-06-01

## Gate

- Gate: WU-STRESS-01 draft PR fix gate
- Source finding: PR 102 review, AgentMiMo LOW finding
- Controller decision: accepted

## Accepted Finding

### PR-LOW-01-已修复-CLEAN_EOF 行为缺少直接 stress 覆盖

- **问题**: `StressWorkerBehavior.CLEAN_EOF` 已在 `tests/host/stress_support.py` 定义，但 `tests/host/test_host_production_stress.py` 没有直接使用。
- **直接证据**: plan 明确要求 clean EOF worker 行为覆盖 scheduler failed closeout；修复前目标 stress 文件只覆盖 `FINAL`、`FAILED`、`BLOCKING_FINAL` 和 `STREAM_EXCEPTION`。
- **影响**: scheduler clean EOF failed closeout 只能由低层测试证明，WU-STRESS-01 production stress 缺少直接哨兵。

## Fix

- 在 `DeterministicStressWorkerHandle.events()` 中为 `StressWorkerBehavior.CLEAN_EOF` 增加显式分支，语义为 worker event stream clean EOF 且不产出 terminal event。
- 在 Slice 4 scheduler/liveness mixed flow 中新增一个 `CLEAN_EOF` scripted run。
- 增加 `run_failed_reason_for_run()` stress helper，从 EventLog canonical fact 读取目标 Run 的 `RUN_FAILED` reason。
- 在 `Slice4SchedulerLivenessDiagnostics` 中新增 `clean_eof_failed_closeout_ok`，断言 clean EOF run 的 public snapshot 为 `FAILED`，且 durable `RUN_FAILED` reason 为 `stream_ended_without_terminal`。

## Changed Files

- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `docs/reviews/wu-stress-01-fix-pr-codex-20260601.md`

## Validation

- `source .venv/bin/activate && pytest -o addopts= -m stress tests/host/test_host_production_stress.py::test_scheduler_liveness_long_run_mixed_flow_stress -q`
  - Result: passed, `1 passed in 1.19s`
- `source .venv/bin/activate && pytest -o addopts= -m stress tests/host/test_host_production_stress.py -q`
  - Result: passed, `5 passed in 5.86s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`

## Docs Decision

- README 未更新。
- 原因: 本次只补 stress 内部覆盖和诊断 helper，没有改变测试分层、运行命令、marker 默认排除策略、公共契约或用户可见工作流。

## Residual Risk

- 未发现新的 blocking risk。
- clean EOF 覆盖仍限定在 stress marker 下，符合 WU-STRESS-01 stress suite 的默认排除策略。
