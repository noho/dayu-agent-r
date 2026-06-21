# WU-TOOLS-AWAIT-FANOUT-01 Code Re-Review — AgentMiMo

## Gate

- Work unit: `WU-TOOLS-AWAIT-FANOUT-01` / GitHub Issue #111
- Gate: `code re-review` (post-fix, narrow scope)
- Prior review artifacts:
  - `docs/reviews/wu-tools-await-fanout-01-code-review-mimo.md` (initial review — PASS)
  - `docs/reviews/wu-tools-await-fanout-01-code-review-ds.md` (initial review — PASS, 3 non-blocking findings)
  - `docs/reviews/wu-tools-await-fanout-01-code-review-controller-adjudication.md` (controller — CHANGES_REQUESTED, DS-F01 accepted, DS-F03 accepted, DS-F02 deferred)
- Fix artifact: `docs/reviews/wu-tools-await-fanout-01-fix-codex.md`
- Plan: `docs/host/wu-tools-await-fanout-01-plan.md`

## Scope

- Mode: narrow rereview (no pytest/pyright rerun, no code modification)
- Base: `main`
- Files examined:
  - `dayu/host/tool_runtime.py` — `_record_duplicate_awaiting_accepted` (line 2944-3003), `_accept_awaiting` (line 2752-2771), `_execute_one` finally (line 2453-2458)
  - `dayu/host/tool_duplicate_governance.py` — `record_durable_missing` AWAITING_ACCEPTED guard (line 545-567)
  - `tests/host/test_toolruntime_executor.py` — `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` (line 1079-1156)
  - `tests/host/test_toolruntime_duplicate_governance.py` — `test_durable_missing_preserves_awaiting_accepted_marker` (line 1478-1508)
- Sources of truth consulted:
  - `docs/host/wu-tools-await-fanout-01-plan.md` §4, §5, §8
  - Controller adjudication finding table

## Conclusion

**PASS** — 0 unfixed accepted findings, 0 new blocking findings.

## Required Check Results

### 1. DS-F01 是否关闭

**已关闭。**

`_record_duplicate_awaiting_accepted`（line 2944-3003）：

- accepted ack 后构造 `DuplicateAwaitingAcceptedEntry`（line 2969-2980）。
- `record_awaiting_accepted` 调用包裹在 try/except 中（line 2981-3002）。
- 异常时：记录 warning 日志（line 2987-2998），best-effort 发出诊断（line 2999-3002），诊断 emitter 自身也有 try/except 兜底（line 3028-3037）。
- **无条件返回 `True`**（line 3003），不传播异常。
- `_accept_awaiting` 将返回值赋给 `duplicate_terminal_recorded`（line 2755-2763），构造 `_AwaitingAcceptExecution` 时 `durable_missing_reason=None`（line 2770）。
- `_execute_one` finally 条件 `duplicate_owner_needs_terminal and not duplicate_terminal_recorded`（line 2454）不满足，不调用 `record_durable_missing`。
- owner 的 `ToolAwaitingOutcome` 始终被返回（line 2767），未被覆盖。

测试 `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` 直接覆盖：

- monkeypatch 注入 `record_awaiting_accepted` 抛出 `RuntimeError("marker write failed")`。
- 断言 `recorded_reasons == []`（cleanup 未触发）。
- 断言 `isinstance(record.outcome, ToolAwaitingOutcome)`（owner 返回未被覆盖）。
- 断言诊断 `reason_code == "duplicate_awaiting_marker_failed"`。
- 断言 wait_id 未泄漏到诊断 message（符合 LLM-facing 约束）。

plan §8 第 4 点要求 "`record_awaiting_accepted` 失败不得覆盖 owner 已 accepted awaiting 的原始返回"，实现满足。

### 2. DS-F03 是否关闭

**已关闭。**

`record_durable_missing`（line 545-567）AWAITING_ACCEPTED guard：

- line 561: `if in_flight.state is _InFlightDuplicateState.AWAITING_ACCEPTED`
- line 562: `self._state.in_flight_by_key[duplicate_key] = in_flight` — pop 后立即 put 回
- line 563: `self._state.condition.notify_all()`
- line 564: `return` — 不进入 `DURABLE_MISSING` 状态

测试 `test_durable_missing_preserves_awaiting_accepted_marker`（line 1478-1508）直接覆盖：

- owner → `record_awaiting_accepted` → `record_durable_missing(GOVERNED_BEFORE_ACCEPT)` → `decide_duplicate`。
- 断言 `decision.kind is DuplicateDecisionKind.AWAITING_FANOUT`（未重新竞争 owner）。
- 断言 `decision.prior_wait_id == "wait-owner"`、`decision.prior_awaiting_outcome is awaiting_outcome`、`decision.prior_outcome is None`。

### 3. DS-F02 是否仍 deferred

**仍 deferred。**

fix artifact 明确记录 DS-F02 状态为 "Deferred / 按 controller 裁决不处理"。实现未扩展 record schema、public diagnostics 或 durable design。`_awaiting_fanout_record`（line 2784-2800）仍只返回 `BatchToolExecutionRecord`，不接收 diagnostic refs。controller 裁决理由（"AWAITING_FANOUT 仍为防御性 Host-internal/unit-level 行为，不影响 core accepted-awaiting cleanup correctness"）仍然成立。

### 4. 轻量约束是否保持

**保持。**

fix 改动文件：

- `dayu/host/tool_runtime.py` — best-effort 异常处理 + bounded diagnostic
- `tests/host/test_toolruntime_executor.py` — marker 写入失败 focused test
- `tests/host/test_toolruntime_duplicate_governance.py` — AWAITING_ACCEPTED guard focused test
- `docs/reviews/wu-tools-await-fanout-01-fix-codex.md` — fix gate artifact

未触及：

- 无 `engine_ingest.py` 修改
- 无 durable schema/state 修改
- 无 public contract 修改
- 无 issue-129 activation
- 无 heavy follower ledger
- 无 wait alias schema
- 无 `DuplicateDecision` 字段扩展

## Verification Artifact Reference

fix artifact 报告：

- `pytest ... -q` → 184 passed in 1.28s
- `pyright` → 0 errors, 0 warnings, 0 informations

## Residual Risk

- `AWAITING_FANOUT` 仍为防御性 Host-internal state；当前 batch 行为（首个 awaiting 后剩余 calls 返回 `run_suspended_by_tool_awaiting`）不变。
- marker 写入失败后 Host durable truth 已成立但 attempt-local marker 可能缺失；本 fix 按 controller 要求优先保护 owner awaiting 返回。跨并发 waiter 强可观测恢复应另起独立 WU。
- DS-F02（diagnostic refs 丢弃）未处理，不阻塞本 WU。
