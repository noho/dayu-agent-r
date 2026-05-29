# Phase 13 Slice 4 Implementation Artifact

## Gate

Phase 13 Slice 4 implementation：`Public Outbox Read / Drain API And Offline Smoke`。

## Scope / Non-goals

本 slice 只实现 additive public Outbox terminal read / drain API 与 offline smoke。

未做：

- 未新增 `OpenHostOptions` 字段。
- 未新增 `wait_final_answer`、`get_run_result`、payload reader 或 timeline replay API。
- 未修改 EventLog append、Run / Attempt terminal transaction、`watch_session_events` signature 或 live-only 语义。
- 未把 Outbox drain 状态解释为 Service / UI / channel delivery success。

## Changed Files

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/open_host.py`
- `dayu/host/read_api.py`
- `tests/host/test_public_outbox_api.py`
- `tests/host/test_public_offline_outbox_smoke.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_open_host_runtime.py`
- `dayu/host/README.md`

## Implementation Summary

- 在 public API 中新增 Outbox terminal cursor、item、batch、read request、drain request、item state、projection status 与 read/seen 上限常量，并把 `read_outbox_terminal_items` / `drain_outbox_terminal_items` 加入 `Host` Protocol。
- 在 `read_api.py` 接入 Slice 3 的 `catch_up_outbox_terminal_projection`、`read_outbox_terminal_items_after` 与 `drain_outbox_terminal_items` durable helper；public 层不重新实现查询、drain、identity 或 watermark 逻辑。
- public read / drain 均先校验 Session 存在，再 best-effort catch-up Outbox projection，并返回 `CAUGHT_UP` / `LAGGED` / `FAILED` projection 状态、checkpoint、scanned watermark 与 has_more。
- `drain_outbox_terminal_items` 只写 Outbox projection queue state 与 drain idempotency row；幂等冲突沿用现有 `HostApiErrorCode.IDEMPOTENCY_CONFLICT` public 风格。
- `open_host` public handle 暴露 read / drain 方法，并在 close flush 的 composite projection port 中加入 Outbox terminal projection。
- README 同步当前已实现的 public Outbox read / drain 契约和边界。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_package_exports.py tests/host/test_open_host_runtime.py -q`
  - Result：23 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - Result：passed。

## Coverage Notes

- 覆盖 public request validation、closed handle、session not found、drain idempotency conflict。
- 覆盖 projection lag 可见状态：catch-up 未运行时返回 `LAGGED`，后续正常 read 可补到 terminal item。
- 覆盖 offline terminal read、drain 幂等、不写 EventLog。
- 覆盖 live-first seen ids 去重，以及 drain-first 后 second read 覆盖 live attach 窗口。
- 覆盖 `open_host.close()` projection flush 包含 Outbox terminal projection。

## Residual Risks

- Outbox item 的 `final_answer` 只在 terminal EventLog payload 已携带内联 final answer 字段时返回；当前真实 terminal path 主要通过 terminal summary refs 暴露结果摘要，本 slice 按边界不新增 payload reader。
- 本 slice 不实现 channel delivery ack、channel retry 或 Service / UI 持久化 seen watermark；这些仍由 Service / channel adapter owner 承担。
- Projection failure path 返回 failure row / catch-up exception 摘要，但不新增 public repair API；projection repair / retention hardening 仍归后续 owner。
