# WU-TOOLS-AWAIT-FANOUT-01 Plan

## 1. Goal / Motivation / Success Signal

### Goal

修复 Host ToolRuntime 在等待型工具调用被 Host accept 后的 attempt-local duplicate cleanup 状态缺口，并把 awaiting fanout 明确降级为防御性 Host internal state。

目标行为：

- 同一 Attempt、同一 duplicate key 的第一个 awaiting owner 仍是唯一外部 job owner。
- owner 只有在 Host awaiting accept barrier 返回 accepted ack 后，才能向 Engine 返回 `ToolAwaitingOutcome`。
- awaiting accept accepted ack 后，ToolRuntime 必须把本次 duplicate owner 标记为 terminal，或以等价 marker 抑制 `finally` 中的 duplicate durable-missing cleanup。
- 当前 Host ToolRuntime production path 中，同一 batch 的第一个 `ToolAwaitingOutcome` 会让后续 calls 返回 `run_suspended_by_tool_awaiting` governed failure；这些后续 calls 不会启动第二个 business callable，也不会在当前端到端路径中命中 `AWAITING_FANOUT`。
- 如保留 `AWAITING_FANOUT`，它只能是防御性 Host internal state，用于未来并发或执行顺序变化时避免 waiter 重新竞争 owner；不得把它声明为当前 Engine / ToolRuntime production end-to-end 必达路径。
- `resolve_wait` 后的新 Attempt 输入能让模型理解：等待结果是该中断步骤中相同工具、相同参数重复请求共享的结果；不得向 LLM 暴露 wait id、tool call id、EventLog ref、digest、payload ref 或 Host 内部账本字段。

### Motivation Judgment

动机成立，但原始 fanout 可达性严重性曾被高估；本计划按 controller 裁决收敛。

第一性原理判断：等待型工具调用的副作用边界在外部 job 和 Host wait record 上。Host accept barrier 已 accepted 后，Run / Attempt / wait record 的 durable truth 已经成立；此时 `_execute_one` 的 `finally` 再把 duplicate state 记为 `DURABLE_MISSING`，是 attempt-local cleanup 状态错误。直接风险是 duplicate governance 的内存状态与 Host durable truth 分叉；在当前 production path 中，同批后续 calls 会被 `run_suspended_by_tool_awaiting` 拦截，不会继续命中 awaiting fanout waiter，因此本 WU 不应把 “同批 waiter fanout” 当作当前必达生产 bug 来设计。

### Success Signal

- awaiting owner accepted ack 后，ToolRuntime 不调用 `record_durable_missing`。
- awaiting accept rejected / timeout 时仍记录 durable missing，并保持现有 governed failure。
- awaiting 后同批剩余 calls 继续走 `run_suspended_by_tool_awaiting` governed failure，不启动第二个 business job。
- awaiting accept port 只收到 owner 的一次 candidate。
- durable `host_wait_records` 只存在 owner 的单条 active wait record。
- Engine waiting confirmation 仍以 Host accepted wait record 为 truth，不创建 wait record，不关闭 Attempt。
- resume material 在现有 result projection 之后追加业务可读 shared duplicate result guidance，不泄漏 Host internal refs。
- accept rejected / timeout、owner lost、cancel、late result、resolve replay 均有明确治理结果。

## 2. Non-goals / Scope Boundary

本 WU 不做：

- 不把 `ToolAwaitingOutcome` 简单当作 completed result 写入普通 duplicate accepted index。
- 不绕过 Host awaiting accept barrier。
- 不让 Engine、wait adapter、provider runtime 拥有 Host durable truth。
- 不实现 GitHub Issue #129 的 external job two-phase activation。
- 不实现 GitHub Issue #89 / #90 / #92 的 production callback、poller 或 physical cancel。
- 不新增重型 wait follower 表、durable duplicate ledger、跨 Attempt durable duplicate table、跨进程 waiter 队列或新的 public await lifecycle contract。
- 不扩展 `host_wait_records` schema 来记录 follower / alias。
- 不修改 Engine public contract 或 Host public `resolve_wait` contract。

## 3. Design Doc Alignment

本 plan 对齐 `docs/host/design.md`：

- Host 是 Session / Run / Attempt / EventLog / tool governance / wait-resume 的治理真源。
- ToolRuntime / TruncationManager 是工具执行治理、截断、`fetch_more`、等待与重复调用治理 owner；工具事实必须走 Host accept barrier。
- Engine 只执行单次 `AgentRunRequest`，不读取 Host durable store，不拥有 wait record，不恢复旧 Agent / Runner。
- duplicate governance 当前设计为 attempt-local in-memory index，不引入 session-scope、run-scope 或 cross-Attempt durable duplicate ledger。
- ToolRuntime Host accept path 是 awaiting canonical owner；Engine `tool_awaiting` / `run_suspended` 只能作为 preview、diagnostic 或 idempotent confirmation。
- wait record 是 Host durable state index，负责 active wait 查询、adapter observation 恢复、取消 CAS、resolution CAS 与 late result 拒绝；EventLog 仍是 canonical facts truth。
- RunInputBuilder LLM-facing material 不得暴露 wait record id、tool call id、EventLog id、payload ref、digest、cursor、Attempt / execution ledger 或 Host 内部治理术语。

本 plan 对齐 `docs/engine/design.md`：

- Engine 只通过 `ToolExecutor.execute(...)` 做 bounded handshake。
- 工具执行策略、权限、审计、长事务 awaiting、orphan cleanup、工具级取消与重复治理属于 Host / ToolRuntime。
- 恢复不复用旧 Agent / Runner；Host 必须构造新的 `AgentRunRequest.messages`。

## 4. First-principles Judgment And Direct Code Evidence

直接代码证据：

- `dayu/host/tool_duplicate_governance.py` 的 `_InFlightDuplicateState` 只有 `OWNER_RUNNING`、`ACCEPTED`、`DURABLE_MISSING`。它没有 “owner 已 accepted awaiting / waiter fanout” 状态。
- `dayu/host/tool_duplicate_governance.py` 的 `DuplicateAcceptedEntry` 保存 `accepted_outcome: ToolExecutionOutcome` 和 ordinary accepted refs，用于普通工具结果复用；它没有 wait id、awaiting accepted ack 或 fanout alias 语义。
- `dayu/host/tool_runtime.py` 的 `_execute_one` 在 `finally` 中只看 `duplicate_terminal_recorded`。当前 `_accept_awaiting` 成功后没有记录 duplicate terminal，因此 owner accepted awaiting 后仍会进入 `record_durable_missing` cleanup；如果存在 duplicate waiter，它会看到 durable missing 并重新竞争 owner。
- `dayu/host/tool_runtime.py` 的 `_accept_awaiting` 注释明确：awaiting 是等待中间态，不写入 duplicate accepted index，等待解析后的工具结果事实由 `resolve_wait` / resume path 负责。这个约束正确，不能用 “把 awaiting 当普通 completed result” 修补。
- `dayu/host/tool_runtime.py` 当前在第一个 `ToolAwaitingOutcome` 后会让同 batch 后续 calls 返回 `run_suspended_by_tool_awaiting` governed failure；因此这些后续 calls 在当前 production path 中不会继续执行到 duplicate awaiting fanout waiter。
- `dayu/host/waiting.py` 的 awaiting accept path 在单事务内写入 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`，插入 wait record，并把 Run / Attempt 推到 `WAITING` / `SUSPENDED`。
- `dayu/host/durable/schema.py` 已有 `host_wait_records`，并且 `host_wait_records_one_active_per_run` partial unique index 固定同一 Run 同时只有一条 `status='waiting'` active wait。
- `dayu/host/durable/state.py` 的 `WaitRecordRow` 只保存单个 `wait_id`、owner `tool_call_id`、`await_spec`、`external_job_ref` 与 resolution fields；没有 follower / alias 列。
- `dayu/host/engine_ingest.py` 的 `_validate_waiting_confirmation` 只把 Engine waiting event 当作 Host accepted wait record confirmation；它读取唯一 active wait record，不创建 wait record，不推进 Run。
- `dayu/host/engine_ingest.py` 当前 `_engine_awaiting_record_mismatch` 要求 Engine awaiting record 的 `tool_call_id` 等于 wait record owner `tool_call_id`；但当前 Host ToolRuntime 尚未证明会把 alias awaiting records 送到 Engine ingest，因此本 WU 不把 alias confirmation 作为 required change。
- `dayu/host/run_input.py` 的 `_resume_wait_message_from_current_start` 只投影一个 accepted wait result，当前没有说明该结果覆盖中断步骤中的相同工具 / 相同参数重复请求。
- `docs/host/archive/phase7-tool-awaiting-resolve-wait-plan.md` 是较重 Phase 7 等待设计背景，包含 wait record、adapter registry、resolution CAS、late diagnostic 等完整等待治理；当前代码已经落到薄 wait record 模型，本 WU 不应回到 follower ledger 或通用 alias schema。
- recent git history 显示当前分支基于 `main` 的近期 Host tool governance / duplicate governance 实施，包括 `cc0044ef Host duplicate governance attempt scope (#106)`；没有后续 durable duplicate ledger 或 wait follower 表落地。

Root cause：awaiting accept accepted ack 后，ToolRuntime 当前会返回 `ToolAwaitingOutcome`，但没有把本次 duplicate owner 标记为 terminal；随后 `_execute_one` 的 `finally` 误调用 `record_durable_missing`。这是 attempt-local duplicate cleanup 状态 bug，不是 durable wait record、Engine ingest 或 public wait contract 的问题。

当前生产可达性边界：Host ToolRuntime 在第一个 `ToolAwaitingOutcome` 后给后续 batch calls 返回 `run_suspended_by_tool_awaiting` governed failure，因此同批后续 waiter 当前不会命中 `AWAITING_FANOUT`。本 WU 的核心修复是 accepted awaiting 后不得误记 durable-missing；`AWAITING_FANOUT` 若保留，只能作为防御性内部状态覆盖未来并发或执行顺序变化。

## 5. Lightweight Await Decision

轻量方案可满足 #111；不需要 durable schema、public contract 或 Engine ingest alias confirmation 扩张。

决策：

- 核心修复是在 attempt-local duplicate governance 内新增 `record_awaiting_accepted(...)` 或等价 terminal marker，表达 “owner 已被 Host accepted 为等待中间态”，从而阻止 `_execute_one.finally` 误记 durable missing。
- 该 marker 只保存在当前 ToolRuntime Attempt 内存中，包含 owner accepted refs、owner `wait_id`、owner awaiting outcome、owner duplicate key 和 result digest；它首先服务于 cleanup correctness，而不是声明当前 production path 一定存在 waiter fanout。
- 如实现选择同时保留 `AWAITING_FANOUT` decision，它只能作为防御性 Host internal state；测试用 duplicate governance / ToolRuntime unit-level 数据覆盖，不写成当前 Engine 端到端必达验收。
- durable truth 仍只有 owner 的 wait record；follower / alias 不进入 `host_wait_records`。
- Engine ingest 不作为本 WU required change。只有 implementation 先用直接证据证明当前 Host ToolRuntime 会产生 alias awaiting records 并送达 Engine ingest，才能提出触及 `engine_ingest.py`；否则保持现状。
- resume material 用 LLM-facing 的业务语义说明 shared duplicate result，而不是把 alias ledger 投影给模型。

为什么不回到重型 durable await 设计：

- 当前 root cause 发生在同一 Attempt 的 awaiting accept cleanup window；attempt-local governance 正是这个 cleanup 状态的 owner。
- Host 已有 awaiting accept ack、wait record、resolve_wait、late rejection、WAITING cancel 和 resume Attempt 机制；缺口是 duplicate state machine 没有 awaiting accepted terminal。
- `host_wait_records` 已经通过 unique active wait per Run 约束 single wait owner；新增 follower 表或 cross-Attempt ledger会扩大持久化契约，但不能更直接地阻止当前 waiter 重新执行。
- Run 恢复后创建新 Attempt，设计真源明确不继承旧 Attempt duplicate index；跨 Attempt duplicate durable ledger 不是当前 correctness 前提。
- #129 的 two-phase activation 修 submit-before-accept 窗口，本 WU 只修 accept 已成功后的 duplicate cleanup terminal marker，不能抢先实现 activation protocol。

## 6. Affected Files / Modules

允许且计划触及：

- `dayu/host/tool_duplicate_governance.py`
  - 新增 attempt-local awaiting accepted terminal marker；若保留 `AWAITING_FANOUT`，只能作为防御性 internal state。
- `dayu/host/tool_runtime.py`
  - owner accepted awaiting 后记录 duplicate terminal，确保 `finally` 不调用 `record_durable_missing`。
  - 现有 batch 剩余 calls 继续返回 `run_suspended_by_tool_awaiting` governed failure，不启动第二个 job。
- `dayu/host/run_input.py`
  - 在现有 resume wait message 行之后追加 LLM-facing shared-result guidance，表达同一中断步骤中相同工具/参数重复请求共享该等待结果。
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_run_input_builder.py`
- 视实现触发范围按需补充 `tests/host/test_wait_awaiting_accept.py`、`tests/host/test_wait_cancel_late_result.py`、`tests/host/test_resolve_wait_command.py`、`tests/host/test_public_resolve_wait_resume.py` 的回归断言。

不计划触及：

- `dayu/host/engine_ingest.py`，除非 implementation 先证明当前 Host ToolRuntime 会产生 alias awaiting records 到 Engine ingest，并把该证据交给当前 gate 裁决后再改。
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- Host public API dataclass / `resolve_wait` public contract
- Engine contracts
- wait adapter activation contract

如果 implementation 发现必须修改上述不计划触及项，应停止并交回 blocking question。

## 7. Contract / Schema / State-machine / Public-interface Decision

### Durable Schema

不需要 schema 变更。

理由：

- 单 wait owner 已由现有 `host_wait_records` 表和 `host_wait_records_one_active_per_run` index 表达。
- follower / alias 是同 Attempt duplicate governance 的派生关系，不是独立 durable wait lifecycle。
- cancel、late result、resolve replay 都已经绑定 owner `wait_id`；给 follower 增加 durable row 会制造第二套 lifecycle truth。

### Public Contract

不新增或修改 Host public contract、Engine public contract、`ResolveWaitRequest` / outcome envelope、wait adapter public contract。

### Internal Contract

允许最小内部 contract 增量：

- `DuplicateGovernancePort` 新增 `record_awaiting_accepted(...)`，或实现语义等价的 internal terminal marker API。
- 新增 `DuplicateAwaitingEntry` 或等价 internal marker，字段建议：
  - `accepted_event_refs: tuple[HostEventRef, ...]`
  - `wait_id: str`
  - `awaiting_outcome: ToolAwaitingOutcome`
  - `result_digest: str`
- 如果 implementation 保留防御性 waiter decision，`DuplicateDecisionKind` 可新增 `AWAITING_FANOUT`，但它不是当前 production e2e 必达路径。
- 如果新增 `DuplicateDecision` 可选字段，建议：
  - `prior_awaiting_outcome: ToolAwaitingOutcome | None`
  - `prior_wait_id: str | None`

这些都是 Host internal / ToolRuntime internal contract，不进入 LLM-facing 文本，不进入 public API。

字段互斥语义：

- 普通 completed / failed / cancelled duplicate reuse 使用现有 `prior_outcome`，且 `prior_awaiting_outcome=None`、`prior_wait_id=None`。
- 防御性 `AWAITING_FANOUT` 使用 `prior_awaiting_outcome` 和 `prior_wait_id`，且 `prior_outcome=None`；awaiting 中间态不得伪装成普通 completed-result reuse。
- 如果 implementation 选择更简单的 terminal marker 方案，不新增 `AWAITING_FANOUT` decision，也必须保证 marker 不进入 ordinary accepted index，不让 `_accept_reuse` 消费 awaiting outcome。该方案更贴近当前 production path，因为当前同批后续 calls 已由 `run_suspended_by_tool_awaiting` governed failure 截断。

### State Machine

attempt-local duplicate state 从：

```text
OWNER_RUNNING -> ACCEPTED | DURABLE_MISSING
```

扩展为：

```text
OWNER_RUNNING -> ACCEPTED | AWAITING_ACCEPTED | DURABLE_MISSING
```

状态含义：

- `ACCEPTED`：普通 completed / failed / cancelled 或 reuse-governed tool fact 已经 Host accepted，可按现有 duplicate policy 复用、hint、hard stop。
- `AWAITING_ACCEPTED`：owner awaiting outcome 已经 Host accepted，并拥有唯一 wait record；它首先表示 owner terminal cleanup 已完成，`finally` 不得再记 durable missing。如保留防御性 `AWAITING_FANOUT`，waiter 可 fanout 到同一个 owner wait，但这不是当前 production end-to-end 必达路径。
- `DURABLE_MISSING`：owner 没有产生 Host accepted fact 或 accepted awaiting ack；等待者重新竞争 owner。

## 8. Implementation Decisions

### Owner Accepted Awaiting

当 `_accept_awaiting_with_retry` 返回 `ToolAwaitingAcceptedAck`：

1. `_accept_awaiting` 必须调用 duplicate governance 的 `record_awaiting_accepted(...)`，或调用等价 terminal marker API。
2. `_execute_one` 必须把 `duplicate_terminal_recorded=True`，避免 `finally` 误记 durable missing。
3. 记录内容必须来自 accepted ack，而不是未确认的 raw outcome：
   - accepted refs 来自 `ToolAwaitingAcceptedAck.accepted_event_refs`
   - `wait_id` 来自 `ToolAwaitingAcceptedAck.wait_id`
   - `result_digest` 来自 `ToolAwaitingAcceptedAck.result_digest`
   - `awaiting_outcome` 是 owner 即将返回给 Engine 的 outcome
4. 如果 `record_awaiting_accepted` 本身失败，按现有 cleanup 风格处理为 best-effort diagnostic；不得覆盖 owner 已 accepted awaiting 的原始返回。

### Current Batch Behavior

当前 Host ToolRuntime 已有生产行为必须保留：

1. 第一个 `ToolAwaitingOutcome` 使 Run 进入等待治理路径。
2. 同一 batch 中尚未执行的后续 calls 返回 `run_suspended_by_tool_awaiting` governed failure。
3. 这些后续 calls 不 dispatch business callable，不提交 awaiting accept candidate，不启动第二个 external job。
4. 本 WU 的实现不得为了制造 waiter fanout 而改变上述 batch 截断语义。

### Defensive Waiter Fanout

只有 implementation 保留 `AWAITING_FANOUT` internal decision 时，才适用本小节。它是防御性 Host internal state，不是当前 Engine / ToolRuntime production end-to-end 必达路径。

当 unit-level duplicate governance 数据中的 waiter 在 `decide_duplicate` 中命中 `AWAITING_ACCEPTED`：

1. `decide_duplicate` 返回 `DuplicateDecisionKind.AWAITING_FANOUT`，携带 owner accepted refs、owner `wait_id`、owner `ToolAwaitingOutcome`。
2. ToolRuntime 不 dispatch 业务 callable。
3. ToolRuntime 不调用 awaiting accept port。
4. ToolRuntime 发出 bounded diagnostic，建议 reason code `duplicate_awaiting_fanout`，内容只用于 Tool Trace / diagnostic，不进入 LLM-facing resume message。
5. ToolRuntime 返回 owner awaiting outcome，使 Engine 仍按等待型 outcome 结束当前 run，而不是把 waiter 当作普通 completed result。

注意：`AWAITING_FANOUT` 不走普通 duplicate accepted index，也不调用 `_accept_reuse`。它不是 “已有 completed result 可复用”，而是 “已有 wait owner，当前调用成为 follower”。该分支只能用 unit-level duplicate governance / ToolRuntime 测试覆盖，不能声明当前 production e2e 一定触发。

### Engine Awaiting Confirmation

保持原则：Engine waiting event 只能确认 Host accepted wait record，不能创建或修改 wait record。

本 WU 默认不修改 `engine_ingest.py`：

- owner record 仍按现状完整匹配 active wait record。
- 当前 Host ToolRuntime 尚未证明会产生 alias awaiting records 到 Engine ingest；因此 alias confirmation 不是 required implementation。
- implementation 必须先通过代码或 focused test 证明当前 production path 会把 alias awaiting record 送到 Engine ingest，才允许把 `engine_ingest.py` 变更提出来；没有该证据时不得修改。
- 若 future work 确实要支持 alias confirmation，只能作为防御性 diagnostic：不创建第二个 wait record，不追加第二份 awaiting canonical facts，不改变 Run / Attempt / wait state。

### Awaiting Accept Rejected / Timeout

owner awaiting accept rejected 或 timeout 时：

- 不记录 `AWAITING_ACCEPTED`。
- 不返回 `ToolAwaitingOutcome` 给 Engine。
- 继续返回现有 governed error：`tool_awaiting_accept_rejected` 或 `tool_awaiting_accept_timeout`。
- duplicate governance 记录 `DURABLE_MISSING`，reason 分别为 `HOST_ACCEPT_REJECTED` / `HOST_ACCEPT_TIMEOUT`。
- waiter 被唤醒后重新竞争 owner；这时允许重新执行业务工具，因为没有 Host accepted wait record。

### Owner Lost / Callable Failure / Runtime Cancel

owner 在 Host accepted awaiting 前失败、取消、超时或抛出异常：

- 沿用现有 durable missing 语义。
- 不创建 wait record。
- waiter 重新竞争 owner。

owner 在 Host accepted awaiting 后进程丢失：

- Host durable truth 已经是 `WAITING` + owner wait record。
- 不需要 durable follower ledger；Host recovery 对 `WAITING` Run 只恢复 wait adapter observation，不创建新 Attempt。
- 同 Attempt 内存 fanout entry 随进程消失是可接受的，因为 Attempt 已 suspended，不应继续执行新的 duplicate waiter。

### Cancel

Run 进入 `WAITING` 后取消：

- 沿用现有 Host cancel path：active owner wait record CAS 到 `cancelled`，Run 进入 cancelled terminal，不创建 resume Attempt。
- fanout alias 没有独立 cancel lifecycle。
- late result 仍以 owner `wait_id` 进入 existing late rejection diagnostic。

### Late Result

owner wait record 已 `cancelled` / `lost` / terminal 后收到结果：

- 沿用 `resolve_wait` late rejection path。
- 不为 fanout alias 追加 canonical tool result。
- 允许 diagnostic 提及这是 owner wait 的 late result；不得要求 durable follower ledger 参与裁决。

### Resolve Wait 后 Resume Material

`RunInputBuilder` 必须修改 `_resume_wait_message_from_current_start(...)` 的现有 message 构造，在当前已有行之后追加自解释说明，不替换既有 result projection。

当前既有投影语义必须保留：

```text
A previous interrupted step has an accepted wait result.
tool_name=...
resolution_kind=...
tool_fact_kind=...
result=...
```

在这些行之后追加 shared duplicate result guidance，建议语义：

```text
This wait result is the accepted result for the interrupted tool request. If the interrupted step made duplicate requests for the same tool with the same arguments, treat this same result as covering those duplicate requests. Do not call the same tool again only to obtain the same result.
```

约束：

- 不暴露 `wait_id`、`tool_call_id`、EventLog id、event sequence、payload ref、digest、cursor、Attempt id、execution id。
- 可以保留业务可读 `tool_name`、`resolution_kind`、`tool_fact_kind` 和 bounded `result`，因为当前实现已投影这些字段。
- 如果后续要投影工具参数，必须使用业务可读 arguments projection，不能投影 normalized digest。

## 9. Small Implementation Slices

建议 1 个 implementation slice：`S1 轻量 awaiting cleanup terminal marker`。

切分依据：

- 本 WU 是小型 execution-correctness cleanup。
- duplicate governance terminal marker、ToolRuntime cleanup suppression、current batch governed failure regression、RunInputBuilder resume wording 共同构成一个行为闭环。
- 单独实现 duplicate terminal marker 而不覆盖 ToolRuntime finally，不能修复 durable-missing 误记。
- 单独实现 resume material 而不修 duplicate owner terminal，不能修复 root cause。
- 代码范围小，语义是同一条 accepted awaiting cleanup 状态修复，不应按文件机械拆分。

Slice S1 allowed files：

- `dayu/host/tool_duplicate_governance.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/run_input.py`
- 上述对应 focused tests
- README 仅在读完 `dayu/host/README.md` 更新约束后按需修改

Slice S1 done signal：

- duplicate awaiting owner accepted 后不会被 cleanup 成 durable missing。
- accept rejected / timeout 后仍记录 durable missing。
- awaiting 后 batch 剩余 calls 继续返回 `run_suspended_by_tool_awaiting` governed failure，不启动第二个 business job。
- 同一 Run 仍只有一条 active wait record。
- resume message 表达 shared duplicate result。
- 如果保留防御性 `AWAITING_FANOUT`，unit-level tests 覆盖字段互斥和多个 waiter decision。

## 10. Tests / Validation Commands And Expected Assertions

Implementation 后必须先激活虚拟环境：

```bash
source .venv/bin/activate
```

Focused tests：

```bash
pytest tests/host/test_toolruntime_duplicate_governance.py
pytest tests/host/test_toolruntime_executor.py
pytest tests/host/test_wait_awaiting_accept.py
pytest tests/host/test_run_input_builder.py
pytest tests/host/test_resolve_wait_command.py
pytest tests/host/test_wait_cancel_late_result.py
pytest tests/host/test_public_resolve_wait_resume.py
```

Pyright：

```bash
pyright
```

Required new / updated assertions：

- `test_toolruntime_duplicate_governance.py`
  - owner `record_awaiting_accepted` 后 duplicate state 成为 accepted awaiting terminal marker，不是 `DURABLE_MISSING`。
  - accepted awaiting terminal marker 不污染 ordinary accepted index。
  - accept rejected / timeout 仍进入 durable missing，waiter 重新竞争 owner。
  - 如果保留防御性 `AWAITING_FANOUT`，`prior_outcome=None`，`prior_awaiting_outcome` / `prior_wait_id` 有值；普通 duplicate reuse 则反向互斥。
  - 如果保留防御性 `AWAITING_FANOUT`，owner accepted awaiting 后多个 waiter decision 均得到同一个 owner wait 的 fanout decision，无一重新竞争 owner。
- `test_toolruntime_executor.py`
  - owner accepted awaiting 后 `record_durable_missing` 不被调用。
  - awaiting accept port 只收到 owner 的一次 candidate。
  - accept rejected / timeout 路径保持 governed error，不向 Engine 暴露 awaiting outcome。
  - accept rejected / timeout 路径仍调用 `record_durable_missing`。
  - awaiting 后剩余 batch calls 继续走 `run_suspended_by_tool_awaiting` governed failure，不启动第二个 business job，不提交第二个 awaiting accept candidate。
  - 如果保留防御性 `AWAITING_FANOUT`，只用 unit-level / direct ToolRuntime path 测试 waiter outcome，不把该路径声明为当前 production e2e。
- `test_wait_awaiting_accept.py`
  - 现有 single wait record / idempotent replay / conflict 测试继续通过。
- `test_run_input_builder.py`
  - `_resume_wait_message_from_current_start(...)` 在现有 accepted wait result 行之后追加 shared duplicate result 语义，不替换既有 `tool_name` / `resolution_kind` / `tool_fact_kind` / `result` projection。
  - message 不包含 `wait_id`、`tool_call_id`、EventLog id、payload ref、digest、Attempt / execution id。
- `test_resolve_wait_command.py`
  - resolve owner wait 后仍只创建一个 resume Attempt。
- `test_wait_cancel_late_result.py`
  - cancel 后 late result 仍走 existing late rejection；fanout 不增加第二 terminal fact。
- `test_public_resolve_wait_resume.py`
  - public opener resume smoke 继续通过。
- `test_engine_ingest_mapping.py`
  - 默认不新增或修改。只有 implementation 先证明当前 Host ToolRuntime 会产生 alias awaiting records 到 Engine ingest，并因此获准修改 `engine_ingest.py`，才补充 alias diagnostic 的 direct unit test；该测试不得宣称当前 production e2e 必达。

只读核对命令已执行：

```bash
pwd
rg --files docs dayu tests | rg '^(docs/host/design.md|docs/engine/design.md|docs/host/issues-implementation-control.md|docs/host/archive/phase7-tool-awaiting-resolve-wait-plan.md|dayu/host/tool_duplicate_governance.py|dayu/host/tool_runtime.py|dayu/host/waiting.py|dayu/host/durable/schema.py|dayu/host/durable/state.py|dayu/host/engine_ingest.py|dayu/host/run_input.py|tests/host/test_toolruntime_duplicate_governance.py|tests/host/test_toolruntime_executor.py|tests/host/test_wait_awaiting_accept.py|tests/host/test_wait_cancel_late_result.py|tests/host/test_resolve_wait_command.py|tests/host/test_run_input_builder.py|tests/host/test_engine_ingest_mapping.py|tests/host/test_public_resolve_wait_resume.py)$'
git status --short
sed -n '1,260p' docs/host/design.md
sed -n '1,260p' docs/engine/design.md
sed -n '1,320p' docs/host/issues-implementation-control.md
sed -n '1,260p' docs/host/archive/phase7-tool-awaiting-resolve-wait-plan.md
sed -n '1,260p' dayu/host/tool_duplicate_governance.py
sed -n '260,620p' dayu/host/tool_duplicate_governance.py
sed -n '1,360p' dayu/host/tool_runtime.py
sed -n '2220,2885p' dayu/host/tool_runtime.py
sed -n '1,320p' dayu/host/waiting.py
sed -n '1,320p' dayu/host/durable/schema.py
sed -n '140,475p' dayu/host/durable/state.py
sed -n '657,730p' dayu/host/durable/schema.py
sed -n '1098,1118p' dayu/host/durable/schema.py
sed -n '187,245p' dayu/host/_event_payload.py
rg -n 'Duplicate|duplicate|_accept_awaiting|ToolAwaitingOutcome|awaiting' dayu/host/tool_runtime.py
rg -n 'TOOL_AWAITING|run_suspended|awaiting_records|ToolAwaiting|RUN_SUSPENDED' dayu/host/engine_ingest.py
rg -n 'wait|resume|TOOL_RESULT_ACCEPTED|accepted wait|await' dayu/host/run_input.py
sed -n '948,1025p' dayu/host/engine_ingest.py
sed -n '3290,3735p' dayu/host/engine_ingest.py
sed -n '3984,4055p' dayu/host/run_input.py
rg -n 'awaiting|duplicate|fanout|ToolAwaitingOutcome|record_accepted|durable_missing' tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_wait_awaiting_accept.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_resolve_wait_resume.py
sed -n '984,1185p' tests/host/test_toolruntime_executor.py
sed -n '1350,1510p' tests/host/test_engine_ingest_mapping.py
git log --oneline --decorate -n 20 -- docs/host/archive/phase7-tool-awaiting-resolve-wait-plan.md dayu/host/waiting.py dayu/host/durable/schema.py dayu/host/tool_runtime.py
rg -n 'heavy|重型|follower|ledger|two-phase|activation|thin|lightweight|observation|wait record|awaiting' docs/host/design.md docs/host/issues-implementation-control.md docs/host/archive/phase7-tool-awaiting-resolve-wait-plan.md
git branch --show-current
sed -n '1,160p' dayu/host/README.md
```

Plan gate 未运行测试或 pyright；implementation gate 必须运行上述 focused tests 与 pyright。

## 11. Docs / README Decision

Plan gate 只新增本 plan artifact，不更新 README。

Implementation gate 若修改 `dayu/host/`，必须先按仓库规则读取 `dayu/host/README.md` 的 “Agent更新约束”。当前判断：

- 如果 implementation 只落地 Host internal duplicate awaiting cleanup terminal marker，并且 `dayu/host/README.md` 已有 “工具结果、等待、截断、fetch_more 与重复调用治理必须经过 Host accept barrier” 的稳定说明，可不更新 README。
- 如果 implementation 新增了对开发者稳定有用的 ToolRuntime awaiting cleanup 或防御性 fanout 行为说明，才在 README 的既有 Host package 机制章节中补一句当前已实现能力。
- 不写 work unit 过程、测试清单、未来计划或 issue 状态进 README。

`docs/host/design.md` 当前设计真源已支持轻量方案；除非 implementation 发现必须改变 public contract、durable schema 或跨层状态机，否则不更新设计真源。

## 12. Risks / Open Questions

Risks：

- Engine 当前对 waiting confirmation 的 owner `tool_call_id` 匹配较严格；本 WU 默认不触及该路径，除非 implementation 先证明当前 production path 会产生 alias awaiting record 到 Engine ingest。
- ToolRuntime 当前 batch execution 会在 awaiting 后对剩余 batch calls 返回 `run_suspended_by_tool_awaiting`；测试必须锁定该行为，避免为了 fanout 改变现有截断语义。
- Resume material 只能表达业务语义，不能为了精确说明 alias 暴露内部 refs；这会牺牲一点诊断精确度，但符合 LLM-facing 约束。
- `record_awaiting_accepted` 失败只能 best-effort diagnostic；owner 已 accepted awaiting 的 durable truth 不能被内存索引失败回滚。

Open questions：

- None for plan gate.

Stop condition for implementation：

- 若 accepted awaiting cleanup terminal marker 不能阻止 `record_durable_missing` 误记，必须停止并重新定位 root cause。
- 若为了完成当前 root-cause fix 必须修改 `engine_ingest.py` alias confirmation，必须先提交直接证据并停止等待总控裁决。
- 若必须修改 `host_wait_records` schema、新增 public await lifecycle contract、引入 durable follower ledger 或实现 #129 two-phase activation，必须停止并交回总控裁决。
- 若 Engine contract 必须新增字段才能区分 owner 与 alias，必须停止并交回总控裁决。

## 13. Completion Report Format

Implementation / later gate closeout 应按以下格式报告：

```text
Artifact: docs/host/wu-tools-await-fanout-01-plan.md
Decision: plan-ready
Proposed slices: 1 - S1 轻量 awaiting cleanup terminal marker
Lightweight constraint: preserved
Schema/public contract: none
Validation performed: <commands>
Blocking questions: none
```

## 14. Plan Gate Decision

Artifact: `docs/host/wu-tools-await-fanout-01-plan.md`

Decision: `plan-ready`

Proposed slices: `1 - S1 轻量 awaiting cleanup terminal marker`

Lightweight constraint: `preserved`

Schema/public contract: `none`

Validation performed: only read-only inspection commands listed in §10; tests and pyright not run in plan gate.

Blocking questions: `none`
