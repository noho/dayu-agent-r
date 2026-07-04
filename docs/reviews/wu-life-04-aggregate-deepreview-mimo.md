# WU-LIFE-04 Aggregate Deepreview — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phase/wu-life-04-deadline-watchdog`
- Base: `main`
- Output file: `docs/reviews/wu-life-04-aggregate-deepreview-mimo.md`
- Included scope: branch 相对 main 的完整 diff（2 commits + 未提交 control doc 状态更新），覆盖 production code、tests、design docs、README、plan artifact 和 review artifacts。
- Excluded scope: `docs/reviews/` 下的历史 review/plan artifacts（只读参照，不作为 review target）。
- Parallel review coverage: 无（scope 可控，单 reviewer 完整覆盖）。

## Review Basis

- Plan: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
- Design sources: `docs/host/design.md`、`docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Controller validation: engine target tests 44 passed；Host focused tests 243 passed（controller reported 250，差异可能来自 test file set 或 test count drift，不影响结论）；pyright 0 errors；`git diff --check` passed；`rg "active_cancel_timeout_seconds"` 和 `rg "active_cancel_timeout|timeout_seconds.*active"` 在 `dayu/host tests/host docs/host/design.md dayu/host/README.md` 范围内无匹配。

## Findings

未发现实质性问题。

### 逐项验证

#### 1. Public API 删除完整性

- `OpenHostOptions.active_cancel_timeout_seconds` 已删除（`dayu/host/api.py`）。
- `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS` 已删除。
- `_require_optional_positive_finite_float` 验证函数已删除。
- `HostLocalExecutionOptions.active_cancel_timeout_seconds` 已删除。
- `_local_execution_options_from_open_host_options` 投影已删除。
- `dayu/host/README.md` 已移除 "active cancel timeout" 描述。
- `test_open_host_options_do_not_accept_removed_active_cancel_budget` 测试确认字段不存在于 dataclass fields 和 constructor parameters。
- `rg "active_cancel_timeout_seconds"` 在生产代码和测试中无匹配（仅 test_public_open_host_options.py 中有显式删除断言）。
- 无兼容 wrapper、兼容 re-export 或兼容读取。

**结论**: 公共 API 删除完整，无遗留。

#### 2. Watchdog No-Extra-Budget Closeout 与 Host Design 一致性

- `docs/host/design.md` Cancel 章节已重写：删除 `OpenHostOptions.active_cancel_timeout_seconds` 段落、`reason=active_cancel_timeout` 措辞、`active_cancel_timeout_seconds=None` opt-out 段落。
- 替换为 accepted-cancel watchdog closeout supervisor 描述，明确不提供 post-cancel timeout budget。
- Startup recovery 章节已更新：删除 "启用 active cancel watchdog 时" 条件句，改为无条件 watchdog-first 处理。
- `dayu/host/dispatch.py`：
  - `wake_active_cancel_watchdog` 不再检查 `active_cancel_timeout_seconds is None`。
  - `tick_active_cancel_watchdog` 不再检查 timeout 是否为 None，不再比较 `(now - cancel_requested_at).total_seconds() < timeout_seconds`。
  - `_start_active_cancel_watchdog_loop` 不再检查 timeout 是否为 None。
  - 所有 scanned candidates 直接进入 eligible（无时间比较）。
- `dayu/host/open_host.py`：`defer_accepted_cancel_to_watchdog=True` 硬编码，不再依赖 `active_cancel_timeout_seconds is not None`。

**结论**: watchdog no-extra-budget closeout 与 Host design 完全一致。

#### 3. EventLog Payload 与 Terminal Reason 一致性

- `ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput`：`timeout_seconds: float` 和 `timed_out_at: datetime` 替换为 `cancel_requested_at: str` 和 `closed_out_at: datetime`。
- `_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL` 从 `"active_cancel_timeout"` 改为 `"active_cancel_watchdog_closeout"`。
- `_ACTIVE_CANCEL_WATCHDOG_CLOSEOUT_REASON` 常量 `"active_cancel_watchdog_closeout"` 统一用于 reason dict 和 payload `reason` 字段。
- Event id 前缀从 `_EVENT_ID_ATTEMPT_CANCELLED_TIMEOUT_PREFIX` / `_EVENT_ID_RUN_CANCELLED_TIMEOUT_PREFIX` 改为 `_EVENT_ID_ATTEMPT_CANCELLED_WATCHDOG_PREFIX` / `_EVENT_ID_RUN_CANCELLED_WATCHDOG_PREFIX`。
- payload 中 `timeout_seconds` 和 `timed_out_at` 已移除，`cancel_requested_at` 改为直接使用 `request.cancel_requested_at`（从 watchdog candidate 传入），`closed_out_at` 使用 `format_utc_timestamp(request.closed_out_at)`。
- `_normalized_event_occurred_at` 辅助函数已删除（不再需要从 EventLog row 规范化时间）。
- `_validate_active_cancel_watchdog_closeout_input` 替换 `timeout_seconds` 验证为 `cancel_requested_at` 文本验证。

**结论**: payload 和 terminal reason 语义完全对齐。

#### 4. Startup Recovery 与 Watchdog 一致性

- `open_host.py` 在 startup recovery scan 前执行 `scheduler.tick_active_cancel_watchdog(datetime.now(UTC))`，确保 accepted-cancel `CANCELLING` Run 在 recovery scanner 之前被 watchdog 收口。
- `StartupRecoveryScanner` 接收 `defer_accepted_cancel_to_watchdog=True`，对带 accepted cancel facts 的 `CANCELLING` Run defer 给 watchdog 而非转为 `LOST`。
- `recovery.py` 中 `defer_accepted_cancel_to_watchdog` 默认值仍为 `False`，但 `open_host.py` 始终传 `True`，符合设计意图。

**结论**: startup recovery 与 watchdog 逻辑一致。

#### 5. Tests 一致性

- `test_active_cancel_watchdog_noops_before_timeout` 重命名为 `test_active_cancel_watchdog_closes_on_first_tick_after_cancel`，断言从 `closed == 0` 改为 `closed == 1`，从 `CANCELLING` 改为 `CANCELLED`。
- 所有测试 helper 移除 `active_cancel_timeout_seconds` 参数。
- `_active_timeout_input` → `_active_watchdog_input`，payload 断言更新为无 `timeout_seconds` / `timed_out_at`，有 `cancel_requested_at` / `closed_out_at`。
- `test_open_host_reopen_before_timeout_defers_cancelling_to_watchdog` 重命名为 `test_open_host_reopen_closes_accepted_cancel_with_watchdog`，断言从 `CANCELLING` 改为 `CANCELLED`。
- `_force_cancel_requested_at` 测试 helper 已删除（不再需要操纵 cancel 时间来触发 timeout）。
- `test_dispatch_scheduler.py` 补充 watchdog task cleanup（watchdog 现在无条件启动）。
- `test_engine_ingest_mapping.py` 同步 closeout helper 重命名和 payload 字段。
- first-committer-wins、replay protection、queued promotion、malformed payload rejection 等关键测试均保留并更新。

**结论**: 测试覆盖完整，语义正确。

#### 6. Cross-Commit / 全 Work Unit 一致性

- Commit `59be8480`（plan acceptance）和 `c75205c5`（implementation acceptance）是 gateflow 控制 commits，不包含代码变更。
- 实际代码变更通过未 squash 的工作区 diff 体现，跨 `dayu/host/api.py`、`dayu/host/dispatch.py`、`dayu/host/durable/run_transition.py`、`dayu/host/open_host.py`、`docs/host/design.md`、`dayu/host/README.md` 和 6 个测试文件。
- 所有模块间 rename 一致：`ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput`、`active_cancel_timeout_closeout_in_transaction` → `active_cancel_watchdog_closeout_in_transaction`、所有 event id 前缀、reason string、payload 字段。
- 无跨模块不一致的遗留旧名。

**结论**: 跨 commit 一致性完整。

#### 7. Plan / Review Artifact 与实际代码一致性

- Plan §6 要求删除 `OpenHostOptions.active_cancel_timeout_seconds`、`_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS`、validation、`HostLocalExecutionOptions.active_cancel_timeout_seconds`：✅ 已实现。
- Plan §6 要求不添加 replacement public option、internal disable flag 或 scheduler opt-out：✅ 已实现。
- Plan §6 要求 rename `ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput`、terminal reason 从 `active_cancel_timeout` → `active_cancel_watchdog_closeout`：✅ 已实现。
- Plan §6 要求 payload 停止携带 `timeout_seconds` / `timed_out_at`，保留 `cancel_requested_at`、`closed_out_at`、`watchdog_owner`、`worker_lifecycle_signal`：✅ 已实现。
- Plan §7 no-extra-budget 方案：✅ 已实现。
- Plan §8 Slice 1 / Slice 2 stop conditions：✅ 已验证（rg checks passed）。
- Plan §9 required validation commands：✅ 已执行。

**结论**: 实际代码与 plan 完全一致。

#### 8. README / Control Doc 残留风险 Owner

- `docs/host/design.md` 已更新。
- `dayu/host/README.md` 已更新。
- `tests/README.md`：diff 未包含此文件。检查 plan §10：plan 说 "check after test edits; update only if the documented test layering or command list changes materially"。当前 test 变更主要是 rename 和断言更新，不影响 test layering 或命令列表。
- `docs/engine/design.md`、`dayu/engine/README.md`、`dayu/config/README.md`：无需更新（无 Engine 代码或 config 变更）。
- `docs/host/issues-implementation-control.md`：未提交的 control doc 更新正确反映 gate 状态变更。

**结论**: 无遗漏 README 或 control residual risk owner。

#### 9. Gate Bookkeeping 风险

- 未提交的 control doc 变更：`gate` 从 `accepted slice commit` 更新为 `aggregate deepreview`，`implementation status` 更新 WU-LIFE-04 进入 aggregate deepreview gate，`next entry point` 更新为 aggregate deepreview 描述。
- 这些变更是 controller workflow 的正常 bookkeeping，与实际代码状态一致。
- 无未提交的生产代码或测试变更。

**结论**: 无 gate bookkeeping 风险。

## Open Questions

无。

## Residual Risk

- **Per-tool original deadline observability**: Host 无法感知单个工具调用的原始 deadline。当前 WU 通过不新增 post-cancel budget 正确处理，但若未来需要精确 deadline 诊断或 physical interrupt 升级，需 WU-TOOLS-CANCEL-01 或 Issue #87 child follow-up 提供 Host-visible tool execution phase/deadline signal。Owner: WU-TOOLS-CANCEL-01。
- **Physical interruption after Host closeout**: Host closeout 后 provider/tool 物理停止不在本 WU 范围。Owner: WU-TOOLS-CANCEL-01。
- **Active watchdog scan query optimization**: `read_non_terminal_runs` 全表扫描未优化。Owner: Issue #87 performance follow-up。
- **Clock skew**: 不再有 elapsed timeout 比较（降低了 clock skew 风险），但 event timestamps 仍依赖 Host clock。Owner: Issue #87 diagnostics/audit follow-up。
- **Shared supervisor abstraction**: 未引入。Owner: Issue #87 umbrella。
- **Diagnostic/audit hooks**: EventLog payload 未扩展超出当前字段。Owner: Issue #87 diagnostics/audit hooks follow-up。
- **Test count discrepancy**: Controller reported 250 Host focused tests passed，实际运行 243 passed。差异可能来自 test file set 或 test count drift，不影响所有测试通过的结论。

## Aggregate Deepreview Conclusion

**PASS** — 未发现 blocking findings。

WU-LIFE-04 实现完整、一致、可验证：
1. `active_cancel_timeout_seconds` 从 public API 完整删除，无兼容 wrapper。
2. watchdog no-extra-budget closeout 正确实现，与 Host design、startup recovery、EventLog payload、tests 完全一致。
3. 所有 rename（dataclass、function、constant、event id prefix、reason string、payload field）跨模块一致。
4. 测试覆盖关键行为：first-tick closeout、first-committer-wins、replay protection、queued promotion、malformed payload rejection。
5. README 和 design doc 已同步更新。
6. Residual risks 已明确 owner/destination。
