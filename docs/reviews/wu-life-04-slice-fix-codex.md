# WU-LIFE-04 Slice Fix - AgentCodex

## 基本信息

- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Gate: fix
- Finding: S1S2-CR-F01
- Date: 2026-07-04

## Finding 状态

S1S2-CR-F01：已修复。

直接修复动作：删除 `dayu/host/durable/run_transition.py` 中重构后无调用点的私有辅助函数 `_normalized_event_occurred_at`。该 helper 已不在 accepted-cancel watchdog closeout payload 路径中使用，删除不改变运行时状态迁移语义。

## Changed Files

- `dayu/host/durable/run_transition.py`
- `docs/reviews/wu-life-04-slice-fix-codex.md`

## Validation Results

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：0 errors, 0 warnings, 0 informations
- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q`
  - 通过：123 passed
- `git diff --check`
  - 通过：无输出
- `rg "_normalized_event_occurred_at" dayu/host/durable/run_transition.py`
  - 通过：无输出，exit code 1，表示目标文件内无命中

## Residual Risk

- 本 fix 仅删除无调用私有 helper，未改变业务逻辑、schema、public contract 或测试夹具。
- 未新增测试；原因是变更目标是删除死代码，现有 pyright、目标 Host 测试和符号搜索已覆盖本 finding 的修复证据。
- WU 原有 deferred residual risk 未在本 fix gate 处理，保持 controller adjudication 中的归属不变。
