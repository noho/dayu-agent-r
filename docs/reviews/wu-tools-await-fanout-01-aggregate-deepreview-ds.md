# WU-TOOLS-AWAIT-FANOUT-01 Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-await-fanout-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-ds.md`
- Included scope: all branch changes since `main` — 25 files, including plan (`docs/host/wu-tools-await-fanout-01-plan.md`), implementation (`dayu/host/tool_duplicate_governance.py`, `dayu/host/tool_runtime.py`, `dayu/host/run_input.py`), tests (3 files), README (`dayu/host/README.md`), control doc (`docs/host/issues-implementation-control.md`), and review artifacts.
- Excluded scope: nothing excluded from the branch diff.
- Parallel review coverage: 无。本次 aggregate deepreview 由 AgentDS 单人完成全量走读。

## Validation Re-run

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_public_resolve_wait_resume.py -q` → `184 passed in 1.29s`
- `source .venv/bin/activate && pyright` → `0 errors, 0 warnings, 0 informations`

已引用已有验证：controller 已复跑 focused suites 184 passed 和 pyright 0 errors。本次重新验证结果一致。

## Findings

### 五个重点维度逐项复核

#### 1. 架构边界与契约归属

**复核结论：未发现泄漏。**

- `DuplicateAwaitingAcceptedEntry`、`DuplicateDecisionKind.AWAITING_FANOUT`、`_InFlightDuplicateState.AWAITING_ACCEPTED` 均在 `dayu/host/tool_duplicate_governance.py` 中定义，属于 Host 内部包，未进入 `dayu.contracts`（公共契约）或 `dayu.engine.contracts`（Engine 契约）。
- `DuplicateGovernancePort.record_awaiting_accepted` 是已有 Host-internal port 的新方法，调用方仅限 `ToolRuntimeExecutor`，未导出为 public API。
- `_AwaitingAcceptExecution`（`tool_runtime.py:1112`）是私有 dataclass，仅作为 `_accept_awaiting` 内部返回类型，未在 Host 公开面或 Engine 边界出现。
- Engine 未被要求解释 Host duplicate 治理：`engine_ingest.py` 未修改（diff 确认），`AWAITING_FANOUT` decision 仅在 `_execute_one` 内被消费，返回给 Engine 的仍是 Engine 已理解的 `ToolAwaitingOutcome`。
- `run_input.py` 中追加的 shared duplicate result guidance（`run_input.py:4028`）是纯业务语义说明，不包含 `wait_id`、`tool_call_id`、`EventLog` id、digest、cursor 或任何 Host 内部治理术语。测试 `test_resume_wait_message_appends_shared_duplicate_result_guidance` 明确断言不包含这些内部 refs。

**证据链**：`DuplicateAwaitingAcceptedEntry.__module__` → `dayu.host.tool_duplicate_governance`；`_AwaitingAcceptExecution` 前导 `_` → 模块私有；`git diff main...HEAD -- dayu/host/engine_ingest.py` → empty。

#### 2. 状态机闭合性

**复核结论：OWNER_RUNNING、ACCEPTED、AWAITING_ACCEPTED、DURABLE_MISSING 四态转换闭合，异常、timeout、rejected、marker failure、guard 路径一致。**

走读每条转换路径：

| 路径 | 触发条件 | 入状态 | `duplicate_terminal_recorded` | `finally` 行为 | 证据 |
|---|---|---|---|---|---|
| Owner accepted awaiting | `_accept_awaiting_with_retry` → `ToolAwaitingAcceptedAck` | AWAITING_ACCEPTED | True | 不调用 `record_durable_missing` | `tool_runtime.py:2755-2769` |
| Owner accept rejected | `_accept_awaiting_with_retry` → `ToolAwaitingRejectedAck` | DURABLE_MISSING | False | 调用 `record_durable_missing(HOST_ACCEPT_REJECTED)` | `tool_runtime.py:2773-2779`, `tool_runtime.py:2454-2457` |
| Owner accept timeout | `_accept_awaiting_with_retry` → `ToolAwaitingAcceptTimedOut` | DURABLE_MISSING | False | 调用 `record_durable_missing(HOST_ACCEPT_TIMEOUT)` | `tool_runtime.py:5718-5732` |
| Marker 写入失败 | `record_awaiting_accepted` raise | AWAITING_ACCEPTED (best-effort) | True (marker 失败不传播) | 不调用 `record_durable_missing` | `tool_runtime.py:2995-3007` |
| Waiter 命中 AWAITING_ACCEPTED | `decide_duplicate` 见 state=AWAITING_ACCEPTED | 不创建新 in-flight | N/A (非 owner) | N/A (非 owner) | `tool_duplicate_governance.py:483-492` |
| `record_durable_missing` guard | in_flight.state=AWAITING_ACCEPTED | 保留 AWAITING_ACCEPTED | — | 不覆盖 awaiting marker | `tool_duplicate_governance.py:561-564` |
| Waiter 命中 DURABLE_MISSING | `decide_duplicate` 见 DURABLE_MISSING | 重新竞争 OWNER_RUNNING | — | — | `tool_duplicate_governance.py:495-497` |

关键闭合点：

- **accepted awaiting → 不误记 durable-missing**：`_accept_awaiting` 在 `ToolAwaitingAcceptedAck` 分支返回 `duplicate_terminal_recorded=True`，`finally` 中的 `if duplicate_owner_needs_terminal and not duplicate_terminal_recorded` 为 False，不调用 `record_durable_missing`。当 marker 写入本身失败时，`_record_duplicate_awaiting_accepted` 仍返回 `True`（`tool_runtime.py:3007`），同样抑制 cleanup。该行为由 `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` 直接覆盖。
- **rejected/timeout → 正确记录 durable-missing**：`_accept_awaiting` 在非 accepted 分支设置 `durable_missing_reason`，`_execute_one` 将其传播到外层 `durable_missing_reason`（`tool_runtime.py:2394-2396`），`finally` 正确调用 `record_durable_missing`。
- **guard：durable-missing 不能覆盖 AWAITING_ACCEPTED**：`record_durable_missing` 在 `tool_duplicate_governance.py:561-564` 检查 `in_flight.state is AWAITING_ACCEPTED`，若命中则保留 marker 不做任何变更。`test_durable_missing_preserves_awaiting_accepted_marker` 直接覆盖。
- **DURABLE_MISSING 后 waiter 重新竞争 owner**：`decide_duplicate` 在 `tool_duplicate_governance.py:495-497` 对 DURABLE_MISSING 执行 `continue`，回到循环顶部重新创建 OWNER_RUNNING。`test_durable_missing_still_reopens_owner_competition` 直接覆盖。
- **取消路径**：owner 在 accepted awaiting 前被取消 → `durable_missing_reason=OWNER_CANCELLED` → `finally` 正确记录 DURABLE_MISSING；owner 在 accepted awaiting 后进程丢失 → Host durable truth 已是 WAITING + owner wait record，同 Attempt 内存 fanout entry 随进程消失，Host recovery 不创建新 Attempt — 与 plan §8 "Owner Lost" 一致。

#### 3. 测试覆盖

**复核结论：新增 tests 真实覆盖关键行为，monkeypatch 使用有界且不掩盖风险，focused coverage 满足。**

| 测试 | 覆盖行为 | 覆盖层次 | monkeypatch 评估 |
|---|---|---|---|
| `test_record_awaiting_accepted_marks_terminal_without_ordinary_reuse` | AWAITING_ACCEPTED 不污染 accepted index | 纯 duplicate governance 单元 | 无 monkeypatch — 直接调用 |
| `test_record_awaiting_accepted_fans_out_multiple_waiters` | 多 waiter 共享同一 owner wait | 纯 duplicate governance 单元 | 无 monkeypatch — 直接调用 |
| `test_durable_missing_preserves_awaiting_accepted_marker` | guard：durable-missing 不能覆盖 AWAITING_ACCEPTED | 纯 duplicate governance 单元 | 无 monkeypatch — 直接调用 |
| `test_durable_missing_still_reopens_owner_competition` | 非 awaiting 的 durable-missing 允许 re-competition | 纯 duplicate governance 单元 | 无 monkeypatch — 直接调用 |
| `test_awaiting_outcome_returns_only_after_awaiting_accepted_ack` | accepted awaiting 后不调用 durable-missing cleanup | ToolRuntime executor 集成 | monkeypatch `record_durable_missing` → 观察调用；底层的 governance 状态机由上面单元测试覆盖，此处只测 cleanup suppression |
| `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` | marker 写入失败 best-effort：owner outcome 保留 + cleanup suppressed | ToolRuntime executor 集成 | monkeypatch `record_awaiting_accepted` → raise + `record_durable_missing` → 观察；底层的 governance 状态机分别覆盖 |
| `test_resume_wait_message_appends_shared_duplicate_result_guidance` | resume material 追加 shared duplicate guidance + 不泄漏内部 refs | RunInputBuilder 集成 | 无 monkeypatch — 通过 durable store + real event 构造 |

monkeypatch 风险评估：两个 executor 测试用 monkeypatch 注入 failure mode 和观察调用，这是测试"在特定条件成立时不调用某方法"的合理手段。被 monkeypatch 覆盖的底层行为（状态机转换、guard 逻辑）在 `test_toolruntime_duplicate_governance.py` 中由不依赖 monkeypatch 的 direct unit tests 独立覆盖。不存在 monkeypatch 掩盖真实风险的情况。

#### 4. 文档一致性

**复核结论：control doc、README、plan/review artifacts 与代码现状一致，无未来计划伪装成已实现能力。**

- `docs/host/issues-implementation-control.md` §WU-TOOLS-AWAIT-FANOUT-01 → 状态准确："accepted slice commit `2e5791c9`; awaiting aggregate deepreview" ✅
- `dayu/host/README.md` → 新增 `AWAITING_FANOUT` 说明："这是 Host internal 防御分支，不是普通 completed result 复用" — 明确信号这是防御性/内部能力 ✅
- `dayu/host/README.md` → 新增 cleanup 说明："owner 被 Host accepted 为等待中间态后，会记录 attempt-local terminal marker，避免 cleanup 把已 accepted awaiting 误标为 durable-missing" — 描述当前已实现能力 ✅
- Plan §5 声明 AWAITING_FANOUT "只能作为防御性 Host internal state" → 实现中 `_awaiting_fanout_record` 只通过 unit-level / direct ToolRuntime path 可达，不声明为 production e2e 必达路径 ✅
- Plan §2 Non-goals 列出的禁止项（不修改 engine_ingest、durable schema、public API、#129 activation）→ 实现均未触及 ✅
- Review artifacts（code-review、fix、rereview、controller adjudication）→ finding 状态与最终代码一致：DS-F01 closed（marker failure best-effort），DS-F03 closed（guard test），DS-F02 deferred（diagnostic refs）✅

#### 5. 轻量约束

**复核结论：无 durable schema/state/public API/issue-129/Engine ingest/heavy ledger/alias schema 扩张。**

| 约束项 | Plan 承诺 | 实现验证 |
|---|---|---|
| Durable schema | 不变更 | `dayu/host/durable/schema.py` 未修改（diff 确认） |
| Durable state | 不变更 | `dayu/host/durable/state.py` 未修改（diff 确认） |
| Public API | 不新增/修改 | `dayu/host/api.py` 等未修改；`DuplicateAwaitingAcceptedEntry` 是 Host 内部 dataclass |
| Issue #129 | 不实现 | 无 two-phase activation 相关代码 |
| Engine ingest | 不修改 | `dayu/host/engine_ingest.py` 未修改（diff 确认） |
| Heavy ledger | 不引入 | 无 follower 表、无 durable duplicate ledger、无跨 Attempt 持久化 |
| Alias schema | 不扩展 | `host_wait_records` schema 未变；无 follower/alias 列 |
| Internal contract 增量 | 仅 `record_awaiting_accepted` + `DuplicateAwaitingAcceptedEntry` | 仅此两项，均在 Host 内部 |

### 无阻塞 Findings

经过对五个重点维度和全部变更的逐路径走读，未发现实质性问题。

### 非阻塞观察

以下为走读过程中注意到的非阻塞项，不要求修改：

1. **`AWAITING_FANOUT` 在当前 production path 中不可达**：当前 batch execution 在第一个 `ToolAwaitingOutcome` 后将 `run_suspended_by_awaiting=True`，后续 batch calls 返回 `run_suspended_by_tool_awaiting` governed failure，不会进入 duplicate governance 的 `decide_duplicate`。这意味着 `AWAITING_FANOUT` decision 和 `_awaiting_fanout_record` 在当前端到端路径中不会执行。这与 plan 的明确声明一致（"AWAITING_FANOUT 只能作为防御性 Host internal state"），但值得在此记录：若未来 Engine/ToolRuntime 改变 batch 并发模型，需要重新验证该路径的端到端可达性和 Engine ingest 的 alias confirmation 语义。该风险已在 controller adjudication 中记录为 deferred。

2. **`record_awaiting_accepted` marker 写入失败后 attempt-local marker 缺失**：当 marker 写入失败且 owner 进程在返回 Engine 前崩溃，新 recovery 创建的 Attempt 不继承旧 Attempt 的 duplicate index（这是 attempt-scoped design 的有意行为）。已在 fix artifact 的残余风险中记录。

## Open Questions

无。

## Residual Risk

- `AWAITING_FANOUT` 保持为防御性 Host-internal/unit-level 行为；当前 production batch 路径不会触发。若未来 Engine 或 ToolRuntime 并发模型变更使 fanout 成为 production 可达路径，需重新验证 diagnostic visibility（DS-F02 deferred）和 Engine ingest alias 语义。
- `record_awaiting_accepted` marker 写入失败后，Host durable truth 已成立但 attempt-local marker 可能缺失。当前 fix 优先保护 owner awaiting 返回并抑制 durable-missing cleanup。若未来需要跨并发 waiter 的强可观测恢复，应另起独立 WU 设计。

## Verdict

**PASS** — 0 blocking findings.

经过对全部 branch changes 的逐路径走读、五个重点维度的系统复核、focused tests 184 passed 和 pyright 0 errors 的验证，确认：
- 架构边界和契约归属未泄漏。
- 状态机四态转换闭合，异常/timeout/rejected/marker failure/guard 路径一致。
- 测试真实覆盖关键行为，monkeypatch 使用有界。
- 文档与代码现状一致，无未来计划伪装。
- 轻量约束完整保持。
