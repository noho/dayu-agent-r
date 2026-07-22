# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Code Re-Review（AgentDS）

## Verdict

**PASS — S3-CR-F01 CLOSED, S3-CR-F02 CLOSED, 0 new material finding.**

## 审查范围

- **Mode**: current changes re-review（deepreview --base b33bb80b）
- **Accepted base**: `b33bb80b`
- **审查 Diff**: 28 files, +3095/-432 lines（production 9 + test 19，含 1 new terminal_post_commit.py + 1 new test）
- **排除**: `docs/host/issues-implementation-control.md`（Controller-owned dirty change，不审查）、AgentMiMo 本轮新 re-review artifact（未读）
- **已读前置文档**: AGENTS.md、prior Codex review、Controller adjudication、Codex fix artifact
- **Methodology**: 逐文件 read/diff + grep 验证 + 完整 pyright + F01/F02 逐项证据链走读

---

## F01 确认：`_fail_recovering_run` UPDATED → wake=True notice；CAS_LOST/INVALID_STATE → 零 notice

**状态：CLOSED**

### 1. UPDATED 分支从 same-tx exact result 生成 notice

**直接证据** — `dayu/host/engine_ingest.py:2606-2613`：

```python
return EngineIngestResult(
    status=EngineIngestStatus.ACCEPTED,
    events=rows,
    terminal_closeout=True,
    terminal_notice=terminal_notice_from_transition(
        result,
        wake_queue_promotion=True,
    ),
    reason=_REASON_CONTEXT_COMPACTION_RECOVERY_FAILED,
    transient_delta=None,
)
```

- `result` 是同一 `fail_recovering_run_in_transaction(...)` 返回的 `RunTransitionResult`，包含 same-transaction `run_event`。
- 参数 `wake_queue_promotion=True` 符合 Plan 5.3 manifest 的 flag 规则：RECOVERING→FAILED 首次释放 active slot。
- 不读取 store、不执行第二事务、不做 latest/max/readback。

### 2. `_finish_ingest` → port 在 commit 后且 exact

**直接证据** — `dayu/host/engine_ingest.py:872-875`：

```python
if result.terminal_notice is not None:
    self._terminal_post_commit_port.notify_terminal_post_commit(
        result.terminal_notice
    )
```

- `_finish_ingest` 在每次 ingest 的 commit 成功后调用。
- 只有当 result 包含 non-None notice 时才调用 port —— 不存在伪造 notice 路径。

### 3. CAS_LOST / INVALID_STATE → 零 notice

**直接证据** — `dayu/host/engine_ingest.py:2592-2600`：

```python
if result.status != StateMutationStatus.UPDATED:
    return EngineIngestResult(
        status=EngineIngestStatus.REJECTED,
        events=(),
        terminal_closeout=True,
        terminal_notice=None,
        reason="recovering_run_failed_precondition_failed",
        transient_delta=None,
    )
```

- 非 UPDATED（CAS_LOST、INVALID_STATE 等）统一返回 `terminal_notice=None`。
- rejected status 保证 `_finish_ingest` 不调用 port。

### 4. 测试证据

**success path** — `tests/host/test_engine_ingest_mapping.py:1472` `test_reactive_fallback_over_budget_fails_closed_without_lost`：
- 走真实 context compaction → RUN_RECOVERING → fallback over hard budget → RUN_FAILED 路径。
- 用独立 SQLite connection 在 callback 后读回 committed Run/EventLog join，断言 notice、Run、EventLog row 的 Session、sequence 及 Run identity 一致。
- `wake_queue_promotion=True`、`terminal_port.observations` 恰好一次。

**rejection path** — `tests/host/test_engine_ingest_mapping.py:1539` `test_reactive_fail_closed_propagates_recovering_fail_rejection`：
- 参数化覆盖 `CAS_LOST` 与 `INVALID_STATE`。
- 两种结果均断言 `terminal_notice is None`、port notices 为空、`RUN_FAILED` row 为零。

---

## F02 确认：run_transition 唯一 typed owner helper；四 consumer 无本地 wrapper/alias/re-export

**状态：CLOSED**

### 1. 唯一定义

**直接证据** — grep 全量 Host 源码：

```text
dayu/host/durable/run_transition.py:926:def terminal_notice_from_transition(
```

仅此一处定义。无 `_terminal_notice_from_transition` 本地副本在任何 consumer 模块中。

### 2. 四 consumer 直接 import

**直接证据** — 各模块 import 语句：

| Module | Import Line | 本地定义 |
|--------|------------|---------|
| `admission.py` | `from dayu.host.durable.run_transition import ... terminal_notice_from_transition,` | 无 |
| `engine_ingest.py` | `from dayu.host.durable.run_transition import ... terminal_notice_from_transition,` | 无 |
| `recovery.py` | `from dayu.host.durable.run_transition import ... terminal_notice_from_transition,` | 无 |
| `dispatch.py` | `from dayu.host.durable.run_transition import ... terminal_notice_from_transition,` | 无 |

各 consumer 无本地 wrapper、alias 或 re-export。

### 3. 参数名一致

**直接证据** — 全量 `wake_queue_promotion` 命中（不含旧 `should_wake_queue_promotion`）：

- `run_transition.py:929`: `wake_queue_promotion: bool,` — owner 签名
- admission.py: 9 处调用全部使用 `wake_queue_promotion=...`
- engine_ingest.py: 10 处调用全部使用 `wake_queue_promotion=...`
- recovery.py: 2 处调用全部使用 `wake_queue_promotion=True`
- dispatch.py: 3 处调用全部使用 `wake_queue_promotion=...`

零命中 `should_wake_queue_promotion`。

### 4. Stable ref 校验

**直接证据** — `run_transition.py:943-958`：

```python
def terminal_notice_from_transition(
    transition: RunTransitionResult,
    *,
    wake_queue_promotion: bool,
) -> TerminalPostCommitNotice:
    run = transition.run
    run_event = transition.run_event
    if run is None or run_event is None:
        raise HostDurableError("transition result is missing exact Run event")
    if (
        run.terminal_event_id != run_event.event_id
        or run.terminal_event_sequence != run_event.event_sequence
        or run.session_id != run_event.session_id
        or run.run_id != run_event.run_id
    ):
        raise HostDurableError("transition exact Run event is inconsistent")
    return TerminalPostCommitNotice(
        session_id=run.session_id,
        terminal_event_sequence=run_event.event_sequence,
        wake_queue_promotion=wake_queue_promotion,
    )
```

- 两阶段 fail-closed：先验存在，再验一致性。
- 不读取 durable store，不依赖 post-commit readback。

### 5. 完整中文 docstring

**直接证据** — `run_transition.py:931-941`：包含参数、返回值、异常说明。

### 6. Producer flags / manifest / post-commit 时点不变

**直接证据**：
- `test_static_terminal_producer_manifest_is_exact`：21 个 producer 闭集精确通过，`_fail_recovering_run` 保持在 manifest 中。
- `test_direct_queue_promotion_allowlist_is_exact`：5 处 ordinary direct promotion 精确通过。
- 所有 producer 在 `run_write` 返回后才调用 `notify_terminal_post_commit`（admission、waiting、engine ingest、recovery batch、dispatch 均已逐点验证）。

### 7. Owner/static 测试

- `test_terminal_notice_projection_has_single_durable_owner`：AST 断言 owner 模块恰好 1 个定义、四 consumer 零本地定义且全部 direct import。
- `test_terminal_closeout_appends_concrete_terminal_events`：真实 terminal transition result → notice 投影，断言 exact sequence/stable Run ref/Session 一致与 flag 原样保留；覆盖 missing event 与 inconsistent sequence 的 fail-closed。

---

## New Material Finding Scan

对全部最终 workspace diff（b33bb80b → HEAD + unstaged changes）执行 targeted/focused/pyright/boundary scans，**结果：0 new material finding**。

### 逐项扫描记录

1. **waiting.py `_terminal_notice_from_wait_transition`** — 该函数处理 `WaitResolutionTransitionResult`（非 `RunTransitionResult`），是 waiting 模块的合理私有辅助。Controller 的 F02 裁决 scope 为四个 `RunTransitionResult` consumer；本函数属于不同输入类型的独立投影逻辑，不构成 F02 违反或新 material finding。

2. **admission.py `_record_terminal_cancel_ack`** 使用 `confirm_terminal_run_in_transaction`（same-tx 读取既存 terminal）后通过共享 helper 投影 notice — 正确，是幂等重放路径而非新 terminal 产生。

3. **dispatch.py `_fail_unstarted_in_transaction`** 返回类型从 `None` 改为 `TerminalPostCommitNotice | None` — 所有 caller 通过 `_GovernanceStageResult.terminal_notice` 和 `_ProactiveCompactionExecutionResult.terminal_notice` 正确消费（line 1679-1680、1907-1908）。

4. **dispatch.py `_closeout_worker_startup_failed`** — terminal notice 在 `run_write` 返回后立即消费（line 3983-3985），正确。

5. **dispatch.py `_active_cancel_watchdog_tick`** — batch notices 在 `run_write` 返回后逐条消费（line 1377-1379），正确。

6. **dispatch.py scheduler 构造** — `_bind_terminal_post_commit_port` 仅允许一次 bind（重复抛 RuntimeError），factory failure 路径的 `close_after_failed_scheduler_open` 正确清理。

7. **open_host.py Host close order** — public gate → wait poller → actor drain → scheduler close → terminal coordinator close → delivery hub close → projection flush → actor handle → actor executor → scheduler store。coordinator 在 scheduler drain 后、delivery hub 前关闭，顺序正确。

8. **command.py `_NoLocalDeliveryTerminalPostCommitPort`** 与 **open_host.py `_AdminNoLocalDeliveryTerminalPostCommitPort`** — standalone 与 admin command handle 的无本地 delivery 端口，正确。

9. **`_run_pre_start_governance` → caller** — terminal_notice 在 `_run_pre_start_governance` 内已消费（line 1679-1680），caller `run_queue_promotion`（line 1404）不再重复消费，正确。

10. **Pyright**: `dayu/host/` 完整 pass — **0 errors, 0 warnings, 0 informations**。

11. **Engine boundary**: `dayu/engine` 对 `TerminalPostCommit`、`terminal_post_commit`、`session_event_delivery` 零命中。

12. **`dayu.runtime` reverse dependency**: 零命中 Engine/Host/Service/UI/Fins。

13. **Producer manifest / direct promotion / single owner static** tests — 全部保持精确通过。

14. **`terminal_post_commit.py` 模块** — 仅 import `__future__`、`dataclasses`、`typing`，无上层依赖；`TerminalPostCommitNotice` 严格校验 session_id/sequence/flag 类型与值域。

---

## Open Questions

无。

## Residual Risk

1. **`_terminal_notice_from_wait_transition`（waiting.py:2181）与 `terminal_notice_from_transition`（run_transition.py:926）语义重复** — 两者投影逻辑完全相同，仅输入类型不同（`WaitResolutionTransitionResult` vs `RunTransitionResult`）。当前不构成 correctness gap，且 Controller F02 裁决 scope 为四个 `RunTransitionResult` consumer，未包含 waiting。若未来 `WaitResolutionTransitionResult` 的 `run`/`run_event` 字段语义变化，两处投影可能不一致。建议后续 cleanup 中考虑将共享投影逻辑抽取为接受 `run: RunRow, run_event: EventLogRow` 的基础函数，或使用 Protocol。

---

## 审查统计

- Production files re-reviewed: 9（+1 new）
- Test files reviewed: 2（F01/F02 owner tests）
- F01: **CLOSED**
- F02: **CLOSED**
- New material findings: **0**
- pyright: 0 errors, 0 warnings, 0 informations
- Prior findings re-checked: S3-CR-F01/F02 两项均已关闭，证据链完整
