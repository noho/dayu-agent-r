# WU-PROJ-01 S3/S4 Residual Implementation Artifact

## 元数据

- Gate: implementation
- Work unit: `WU-PROJ-01`
- Scope: `WU-PROJ-01-S3-R1` / `WU-PROJ-01-S4-R1`
- Agent: AgentCodex
- Date: 2026-06-11
- Changed files:
  - `tests/host/test_dispatch_scheduler.py`
  - `docs/reviews/wu-proj-01-s3-s4-implementation-codex.md`

## 动机判断

两个 residual 成立，且严重性评估合理。

`WU-PROJ-01-S3-R1` 是 dispatch before-worker memory projection catch-up 的正向覆盖缺口。已有测试覆盖 lag repair 失败收口、inline repair view 缺失和 rebuild 未达 required cursor 的 fail-closed，但没有独立证明 required cursor 已由 projection checkpoint 覆盖时，dispatch 继续构造 ordinary `RunInput` 并接受 worker。

`WU-PROJ-01-S4-R1` 是测试 fixture timing 风险。`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 验证的是 reactive compact failure fallback dispatch 语义，不验证 lane acquire timeout。该用例继续使用 `_open_scheduler(...)` 默认 `lane_default_timeout_seconds=0.01` 会把测试暴露给无关的宿主调度窗口。

两个 residual 都是测试和 fixture hardening，不需要修改 production semantics。

## 修改摘要

### S3-R1

新增 `test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input`：

- 先用真实 `catch_up_conversation_memory_projection(...)` 将 conversation memory projection checkpoint 追到当前 dispatch 的 required cursor。
- 通过 wrapper 观察 dispatch 内部真实 before-worker catch-up 返回值，不替换 catch-up 语义。
- 断言 dispatch 内部 catch-up 在 checkpoint-covered 情况下 `started_cursor == finished_cursor == required_event_sequence`、`events_scanned == 0`、`target_reached is True`。
- 断言 worker accepted、ordinary no-tool `AgentRunRequest` 已构造、用户输入 `"dispatch prompt"` 进入 request、Run / Attempt 进入 `RUNNING`。
- 断言没有 `RUN_FAILED`、没有 `RUN_RECOVERING`、Attempt 数量仍为 1，证明没有被 memory lag fail-closed 或 recovery 路径替代。

新增 `_read_memory_checkpoint_sequence(...)` 测试 helper，用 public durable projection read primitive 读取 checkpoint cursor。

### S4-R1

在 `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 的 `_open_scheduler(...)` 调用中显式设置 `lane_default_timeout_seconds=1.0`。

保留原有断言强度：fallback artifact / `CONTEXT_COMPACTION_FAILED` payload、第二次 dispatch request、Attempt 数量、无 `CONTEXT_COMPACTED`、无 `RUN_LOST`、第二次 request 不包含 accepted compact artifact 文本。

## 直接证据

- `docs/host/design.md` 说明 ordinary dispatch 前 snapshot cursor 不能覆盖 required cursor 时必须做 bounded catch-up / repair；这不是 Run crash recovery，不得进入 `RECOVERING`。
- `docs/host/design.md` 说明 reactive compact failure fallback 可创建新的 recovery Attempt，但 fallback 不写 `CONTEXT_COMPACTED`，也不得用 `LOST` 表达 compact failure。
- `docs/reviews/wu-proj-01-s3-s4-residual-controller-adjudication.md` 裁决 S3-R1 / S4-R1 都必须在当前 PR 内实施，且优先只改 `tests/host/test_dispatch_scheduler.py`。
- `tests/host/test_dispatch_scheduler.py` 既有 lag repair 测试通过 monkeypatch 跳过 before-worker catch-up 来覆盖失败路径；新增测试覆盖相反的 checkpoint-covered happy path。
- `_open_scheduler(...)` 默认 `lane_default_timeout_seconds=0.01`，S4 用例此前未覆盖 lane timeout 语义。

## 验证结果

已在 `source .venv/bin/activate` 后运行：

- `python -m pytest tests/host/test_dispatch_scheduler.py::test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input`
  - 结果：1 passed
- `python -m pytest tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view`
  - 结果：1 passed
- `python -m pytest tests/host/test_dispatch_scheduler.py`
  - 结果：68 passed
- `pyright`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过，无输出

## README 判断

本次修改命中 `tests/` README 检查触发。已读取 `tests/README.md`。

判断：无需更新 README。理由是本次仅在既有 `tests/host/test_dispatch_scheduler.py` 内补充 dispatch scheduler 行为覆盖并调整单个测试的 lane timeout fixture，不新增测试层级、运行方式、公共测试约定或维护入口。

## 剩余风险

- `WU-PROJ-01-S3-R1`: fixed in current slice。新增测试已覆盖 projection checkpoint 已覆盖 required cursor 时的 before-worker catch-up no-op happy path、ordinary RunInput 构造、worker accept，以及非 fail-closed / 非 recovery 断言。
- `WU-PROJ-01-S4-R1`: fixed in current slice。目标 flaky 的无关 lane acquire timing 风险已由测试专用 timeout 隔离，fallback 语义断言未降低。
- 未覆盖项：未运行全仓测试。当前 residual 范围仅限 `tests/host/test_dispatch_scheduler.py`，已运行目标文件全量测试与 pyright。

## 完成状态

Implementation gate complete. 未 commit、未 push、未创建 PR，未进入 review 或后续 gate。
