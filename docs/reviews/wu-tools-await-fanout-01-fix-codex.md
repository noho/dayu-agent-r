# WU-TOOLS-AWAIT-FANOUT-01 Fix - Codex

## 修复摘要

- Work unit: `WU-TOOLS-AWAIT-FANOUT-01` / GitHub issue #111
- Fix scope: controller accepted findings `DS-F01`、`DS-F03`
- 第一性原理确认：Host awaiting accept ack accepted 后，wait record / Run waiting / Attempt suspended durable truth 已成立；attempt-local duplicate awaiting marker 只是 cleanup 与防御性 fanout 的内存辅助状态。该 marker 写入失败不应覆盖 owner 的 `ToolAwaitingOutcome` 返回，也不应让 `_execute_one.finally` 误记 durable-missing。
- 直接根因证据：`ToolRuntimeExecutor._accept_awaiting` 在 accepted ack 后调用 `_record_duplicate_awaiting_accepted`；该调用原先无 try/except，异常会跳过 `_AwaitingAcceptExecution` 构造，导致 `_execute_one.finally` 继续用默认 `GOVERNED_BEFORE_ACCEPT` 执行 durable-missing cleanup。这个问题发生在同一 accepted awaiting 逻辑路径内，不是 durable schema、Engine ingest 或 public wait contract 问题。
- 修复方式：`_record_duplicate_awaiting_accepted` 改为 best-effort。若 Host accepted ack 已返回且 marker 写入失败，记录 warning 和 ToolRuntime 私有诊断，仍返回 terminal 已处理，使 owner 返回原始 `ToolAwaitingOutcome`，并抑制 durable-missing cleanup。

## 逐 Finding 处理状态

| Finding | 状态 | 处理 |
|---|---|---|
| DS-F01 | Fixed | `record_awaiting_accepted` 失败后不传播异常；accepted awaiting owner 仍返回 `ToolAwaitingOutcome`；`finally` 不调用 `record_durable_missing`。新增 executor focused test 注入 marker 写入失败并断言 durable-missing cleanup 未被调用。 |
| DS-F03 | Fixed | 新增 duplicate governance 直接单元测试：owner 记录 `AWAITING_ACCEPTED` 后调用 `record_durable_missing`，后续 duplicate decision 仍为 `AWAITING_FANOUT`，保留同一 owner wait/outcome，不重新竞争 owner。 |
| DS-F02 | Deferred | 按 controller 裁决不处理。未扩展 record schema、public diagnostics 或 production path。 |

## 改动文件

- `dayu/host/tool_runtime.py`
  - accepted awaiting marker 写入改为 best-effort。
  - marker 写入失败时发出 bounded diagnostic，不把 wait id 放入 ToolTrace diagnostic message。
- `tests/host/test_toolruntime_executor.py`
  - 新增 marker 写入失败 focused test，覆盖 owner outcome 和 cleanup suppression。
- `tests/host/test_toolruntime_duplicate_governance.py`
  - 新增 `AWAITING_ACCEPTED` guard focused test。
- `docs/reviews/wu-tools-await-fanout-01-fix-codex.md`
  - 记录本 fix gate 结果。

## 验证命令结果

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_public_resolve_wait_resume.py -q`
  - Result: `184 passed in 1.28s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## README 决策

- 已读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。
- 本次 narrow fix 不新增 public API、durable schema、Engine contract、Host 稳定状态机或开发者扩展点；只是 accepted awaiting marker 写入失败的 best-effort 异常处理和 focused tests。
- 因此本次 fix 不需要继续修改 README。工作树中既有 `dayu/host/README.md` 修改属于前序 implementation 对 `AWAITING_FANOUT` 当前能力的说明，不在本次 fix 中扩写。

## 残余风险

- `AWAITING_FANOUT` 仍按 controller 裁决保持为防御性 Host-internal/unit-level 行为；当前 batch 行为仍是首个 awaiting 后剩余 calls 返回 `run_suspended_by_tool_awaiting`。
- `record_awaiting_accepted` 失败后，Host durable truth 已成立但 attempt-local marker 可能缺失；本 fix 按 controller 要求优先保护 owner awaiting 返回并抑制 durable-missing cleanup。若未来需要跨并发 waiter 的强可观测恢复，应另起独立 WU 设计，不在本 fix scope 内引入 durable follower ledger 或 public lifecycle。
- 未处理 DS-F02，未修改 diagnostic refs 附着方式。
- 未修改 `dayu/host/engine_ingest.py`、durable schema/state、public API/contracts、wait adapter activation contract，也未实现 issue-129 two-phase activation。
