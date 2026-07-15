# WU-SEMANTIC-OWNERSHIP-01 R05 Wait observation 状态机实施计划

## 0. Gate 身份与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；本文件只覆盖既有 umbrella 的 R05 plan gate，不创建新 WU、feature 或 issue。
- 当前分支：`phaseflow/host-issues-control`。
- plan base / HEAD：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- 硬依赖：R04 completion commit `4898c6aa` 已是当前 HEAD 的 ancestor。
- 当前 gate：同一 `R05-S1 validation plan correction` 已由 AgentCodex 完成，当前等待 Controller validation；Controller 接受后只进入 AgentMiMo / AgentDS 双路完整 plan-correction review，未经该 review / fix / re-review / Controller adjudication 闭环不得恢复 R05-S1 validation，更不得进入 R05-S2、code review、commit、aggregate gate、push 或 PR。
- 计划状态：`WAITING_FOR_CONTROLLER_VALIDATION_AFTER_R05_S1_VALIDATION_PLAN_CORRECTION`。
- owner / allowlist 裁决：历史 plan review 中 `R05-PF-01` 至 `R05-PF-04` 与 `R05-PRR-F01` 均已关闭；其既有 owner / allowlist 裁决继续有效：`dayu/host/durable/state.py` 是 invalid timeout-only terminal primitive 的删除 owner，`docs/host/design.md` 是既有 retry 语义的设计真源纠错 owner，`state.py` touched-file 只额外包含 §2.3 已登记的唯一 unused import hygiene。本次同一 R05-S1 correction 只修订 validation / gate-state 文本与 correction artifact，不新增 schema、policy 字段、owner、产品 allowlist 或 slice；若实现证据要求超过既定精确变化，按 §13 stop conditions 立即停回 Controller。

第一性原理结论如下：

1. observation timeout 只能证明“Host 这一次同步观察没有在预算内拿到可发布结果”，不能证明外部任务丢失。把它提升为 `ResolveWaitLostOutcome` 或 cancelled-wait 的 durable terminal abandon，是把不确定的 transport/observation 事实伪装成业务事实。
2. `WaitObservationRunner` 已以单一 token/generation fence 在 timeout 时撤销 publication authority，late result 已不能进入 poller；这一 owner 当前正确，不需要第二 token、第二 fence 或第二 runner。
3. `WaitPoller` 是 observation 结果解释、claim release 和下一轮调度的 policy owner。当前 poll timeout 在这里被构造为 typed lost，cancelled-wait abandon timeout 在这里被构造为 terminal abandon marker；这是 R05 的直接 root cause。
4. durable state 已有 `release_wait_record_poll_claim(...)` 原子操作及完整 poll-local diagnostic 字段，可同时服务 `WAITING` 与 `CANCELLED`；与此同时，`mark_wait_record_poll_abandon_timeout(...)` 的唯一语义正是把 generic timeout 写成 terminal `poll_abandoned_at`。R05 必须复用前者并在 storage owner boundary 删除后者，不保留 deprecated/dead helper；不需要第二 scheduler、第二 backoff 算法或第二 lost 语义。
5. `dayu/engine/agent.py` 当前只在 `ToolExecutor.execute` 返回前读取并使用 `tool_execution_timeout_seconds`；得到 accepted `ToolAwaitingOutcome` 后的 suspend 路径没有再次读取该 timeout。R05 必须先用 regression 固化这个边界，预期 production **no diff**；只有 regression 在未改 production 的当前 base 上证明真实错误，才可停回 Controller 申请重新裁决，不能在 R05 内自行改写 handshake 语义。

## 1. Goal、非目标与已裁决约束

### 1.1 唯一目标

在 poll observation 与 cancelled-wait abandon observation 两条同步调用路径中，observation timeout 必须完成同一类 Host transition：

```text
ACTIVE publication token
  -> INVALIDATED
  -> late publication rejected
  -> write poll-local transient diagnostic
  -> release current claim
  -> compute next_observe_at from the existing Host backoff policy
  -> keep current durable business status
```

- poll wait 保持 `WAITING`，不调用 `resolve_wait`，不 terminalize Wait/Run。
- cancelled wait 保持 `CANCELLED`，不写 timeout-generated terminal abandon marker；下一轮到期后仍可重试 explicit provider lifecycle observation。
- 只有 provider 明确返回的 authoritative typed `WaitPollLost(ResolveWaitLostOutcome(...))`，或未来经单独裁决的显式 Host durable evidence policy，才允许进入 LOST。
- provider 明确返回的 terminal lifecycle outcome（applied / unsupported / noop）保留既有 transition。

### 1.2 必须保留的 R04 contract

R05 不得改变 R04 config ownership：

- `awaiting_resolution_mode` 的 closed typed modes 仍为 `poll` / `callback` / `manual`，owner 仍为 provider config。
- 三个 packaged Fins awaiting providers 仍显式配置 `poll`；不恢复 scene/name heuristic。
- Host runtime policy 的 12 字段仍全部由 config snapshot 提供，不增加代码默认或第二份 policy：

| 顺序 | 字段 | packaged 值 |
|---:|---|---:|
| 1 | `enabled` | `true` |
| 2 | `poll_interval_seconds` | `1` |
| 3 | `claim_ttl_seconds` | `60` |
| 4 | `claim_batch_size` | `100` |
| 5 | `backoff_initial_delay_seconds` | `30` |
| 6 | `backoff_multiplier` | `2` |
| 7 | `backoff_max_delay_seconds` | `300` |
| 8 | `not_ready_observe_interval_seconds` | `1` |
| 9 | `idle_poll_interval_seconds` | `5` |
| 10 | `adapter_call_timeout_seconds` | `30` |
| 11 | `close_drain_timeout_seconds` | `5` |
| 12 | `max_outstanding_adapter_calls` | `8` |

### 1.3 明确非目标

- 不实施 Issue 175 的 process isolation、process-backed cancellation 或 Docling containment。
- 不实现 callback transport，不统一 authorization/permission schema。
- 不实施 R06+，不改变 Engine handshake 的既有语义。
- 不改变 wait deadline 的既有 FAILED 语义。
- 不放宽现有安全、fencing、capacity、CAS、claim ownership 或 close-drain containment。
- 不新增 durable schema、enum、migration、policy 字段、scheduler、runner、timer 或 lost outcome。
- 不修改 control 或既有 review artifacts。`docs/host/design.md` 只允许在 R05-S1 按 §5.1 的精确句子纠正既有真源，不扩写新 policy/schema；若需要超出该句的设计裁决，只能停止并交 Controller。

## 2. 当前 base 的直接证据与错误语义基线

### 2.1 代码证据

| 证据 | 当前事实 | R05 判定 |
|---|---|---|
| `dayu/host/_wait_observation.py` | observation start 创建 token/generation；timeout 在同一锁下 invalidates token；`_publish` 同时校验 token identity、state、closed、generation，late result 只增加 dropped count | 正确 owner；保留，不另建 fence |
| `dayu/host/wait_adapter.py` poll timeout 分支 | `WaitObservationTimedOut` 被包装成 `WaitPollLost(ResolveWaitLostOutcome(reason_code="wait_observation_timeout", ...))`，继而进入 `_resolve_claimed_wait(...)` | root cause：把 observation uncertainty 提升为业务 LOST |
| `dayu/host/wait_adapter.py` abandon timeout 分支 | `WaitObservationTimedOut` 调用 `_MarkWaitRecordAbandonTimeoutOperation`，写 timeout terminal marker 且停止正常 retry cadence | root cause：把 observation uncertainty 提升为 terminal abandon |
| `dayu/host/wait_adapter.py::_release_with_backoff` | 唯一调用现有 backoff calculator，递增 `poll_backoff_attempt`，并调用既有 release operation | R05 唯一 release/backoff 路径 |
| `dayu/host/durable/state.py` | `release_wait_record_poll_claim(...)` 已支持 `WAITING`/`CANCELLED`；`mark_wait_record_poll_abandon_timeout(...)` 只把 timeout 写为 `poll_abandoned_at` terminal marker，且当前唯一 consumer 是 wait adapter 的 timeout-only wrapper | 保留前者；在 durable owner boundary 删除后者及仅服务 invalid semantic 的代码 |
| `dayu/host/waiting.py` | 只有收到显式 `ResolveWaitLostOutcome` 才执行 LOST projection | 正确 typed terminal owner；保留，无 diff |
| `dayu/engine/agent.py` | timeout 只包住 `_execute_batch` / `ToolExecutor.execute`；得到 `ToolAwaitingOutcome` 后投影 awaiting 并 suspend，后段无 timeout 再读取 | 预期 production no diff |
| `dayu/host/wait_adapter.py::poll_once(...)` | `record.status is CANCELLED` 时先调用 `_abandon_cancelled_wait(...)` 并 `continue`，`_handle_time_boundary(...)` 只在后续非-CANCELLED poll path 执行 | cancelled abandon timeout 可长期按 capped backoff retry；不得误称 wait deadline 会经该 helper 收口 CANCELLED |

`mark_wait_record_poll_abandon_timeout(...)` 不是可保留的公共 contract：它的唯一 durable 语义已被 Controller 判为 invalid，当前没有 export、migration、schema consumer 或第二 production caller。R05-S1 必须同时删除 `wait_adapter.py` 的 import / `_MarkWaitRecordAbandonTimeoutOperation` / timeout call 与 `durable/state.py` 的 function definition；不得留下 deprecated wrapper、兼容 re-export、dead helper 或 docstring。实现后 strict source scan 必须证明该 symbol 与 wrapper 在 production 和 tests 中均为零定义、零调用，同时保留 explicit lifecycle outcome 使用的 `mark_wait_record_poll_abandoned(...)` 与 schema 字段 `poll_abandoned_at`。

### 2.2 现有绿色测试固化了错误语义

当前 base 上以下命令为绿色：

```bash
source .venv/bin/activate
python -m pytest -q \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_phase7_waiting_integration.py
```

结果：`41 passed`。这不是 R05 contract 已正确的证据，因为其中两条 owner-level 测试明确断言了旧错误：

- `test_stuck_poll_times_out_to_lost_and_late_result_is_dropped` 期望 timeout 后 Wait/Run LOST。
- `test_stuck_abandon_writes_timeout_marker_without_external_success` 期望 timeout 写 `poll_abandoned_at` 且不再按 backoff 重试。

实施必须先把这两条测试替换为 R05 owner contract；在未改 production 的 base 上，新断言应精确失败，分别暴露 LOST terminalization 与 timeout terminal abandon。不得为了维持 41 个绿色旧断言而加入兼容分支。

当前以下正确回归也为绿色，必须保留：

- runner low-level token invalidation：`test_timeout_invalidates_token_and_late_result_cannot_publish`。
- authoritative typed lost：`test_poll_adapter_lost_result_closes_run`。
- explicit abandon terminal outcomes、adapter exception、capacity、CAS conflict、expired claim、close shared deadline。
- Engine awaiting / timeout 选集：`7 passed, 40 deselected`。
- 当前 public awaiting smoke：packaged modes 与 12-field snapshot 正确，Run 经 WAITING 最终 SUCCEEDED/outbox match；但尚未覆盖 long operation 与 late timeout retry，因此只能作为 R04 preservation baseline。

### 2.3 静态基线

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `python -m ruff check dayu tests utils`：当前 base 为既有红线，`Found 167 errors`，不得把它误报为 R05 新失败，也不得借 R05 扩域清理。
- 对最终 planned changed Python paths 运行以下定向 Ruff，当前 base 有两条既有错误：

```bash
python -m ruff check \
  dayu/host/durable/state.py \
  dayu/host/wait_adapter.py \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_record_state.py \
  tests/engine/test_agent_phase3_tool_call.py \
  utils/smoke_host_public_awaiting_entrypoint.py
```

六元组 A：

```text
exact command: python -m ruff check dayu/host/durable/state.py dayu/host/wait_adapter.py tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py tests/host/test_phase7_waiting_integration.py tests/host/test_wait_record_state.py tests/engine/test_agent_phase3_tool_call.py utils/smoke_host_public_awaiting_entrypoint.py
node/path: dayu/host/durable/state.py
error type: F401
first stable location: dayu/host/durable/state.py:40:5
text fingerprint: `dayu.host.durable._row_rules.TERMINAL_RUN_STATUS_VALUES imported but unused`
baseline SHA: 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

六元组 B：

```text
exact command: python -m ruff check dayu/host/durable/state.py dayu/host/wait_adapter.py tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py tests/host/test_phase7_waiting_integration.py tests/host/test_wait_record_state.py tests/engine/test_agent_phase3_tool_call.py utils/smoke_host_public_awaiting_entrypoint.py
node/path: tests/host/test_phase7_waiting_integration.py
error type: F401
first stable location: tests/host/test_phase7_waiting_integration.py:8:22
text fingerprint: `datetime.UTC imported but unused`
baseline SHA: 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

`dayu/host/durable/state.py` 与该测试文件都会在 R05 被修改，因此两条 F401 均不能作为 inherited failure 留在 changed files：R05-S1 删除 invalid primitive 时同时删除已证实未使用的 `TERMINAL_RUN_STATUS_VALUES` import，测试修改时继续删除未使用的 `UTC` import，使所有 changed Python files Ruff 为零。这两项都是 touched-file lint hygiene；不得借机清理其它 Ruff 项或扩张产品语义。

## 3. Semantic owner 与唯一状态真源

| 语义 | 唯一 owner | R05 动作 |
|---|---|---|
| observation 调用的 timeout、token、generation、late publication fence | `WaitObservationRunner` | 保留现有实现；只补/保留 owner-level 断言 |
| provider poll 的 typed business outcome | `WaitPollNotReady` / `WaitPollReady` / `WaitPollLost` | 保留；只有 provider 显式 typed lost 可 LOST |
| provider lifecycle terminal outcome | `WaitExternalJobLifecycleApplied` / `Unsupported` / `Noop` | 保留既有 terminal abandon transition |
| observation timeout 的 policy 解释 | `WaitPoller` | 从 typed lost/terminal abandon 改为 release + backoff |
| claim release、backoff attempt 与 `next_observe_at` 计算入口 | `WaitPoller._release_with_backoff(...)` | poll/abandon timeout 统一复用，不复制公式 |
| claim 清理与 poll-local diagnostic 的 durable projection | 既有 `release_wait_record_poll_claim(...)` | 复用；保持其原子 update contract |
| timeout-only terminal abandon primitive | `dayu/host/durable/state.py` | 删除 `mark_wait_record_poll_abandon_timeout(...)`；invalid semantic 无合法消费者，不保留 dead/compat surface |
| typed terminal wait resolution | `ResolveWaitService` / `dayu/host/waiting.py` | 保留，no diff；timeout 不再调用它 |
| Engine tool handshake budget | `Agent` 对 `ToolExecutor.execute` 的 timeout wrapper | regression 固化；production no diff |

### 3.1 Transient diagnostic 的既有字段

这里的 “transient” 表示 poller observation diagnostic，不是业务 terminal fact；它可以持久化在 WaitRecord 供 retry/audit 使用，但不能投影成 LOST、Run terminal 或 LLM-facing 财报事实。

timeout 必须通过既有 release operation 写入：

- claim owner fields：`poll_claim_id`、`poll_claim_owner_id`、`poll_claimed_at`、`poll_claim_expires_at` 全部清空；
- schedule fields：`poll_next_observe_at`、`poll_backoff_attempt`；
- diagnostic fields：`poll_last_outcome`、`poll_last_error_code`、`poll_last_error_message`；
- poll timeout：`poll_last_outcome=ADAPTER_ERROR`，`poll_last_error_code=wait_observation_timeout`；
- abandon timeout：`poll_last_outcome=ABANDON_ERROR`，`poll_last_error_code=wait_abandon_timeout`；
- `poll_abandoned_at` 不因 timeout 写入。

error message 只描述本次 observation 超时，不声称 external job lost、cancel succeeded 或 terminal。不得新增 schema/enum/default；不得在 UI、Service、tests fixture 或日志字符串中重算这些语义。

### 3.2 Backoff 真源

timeout 与既有 adapter exception 使用完全相同的 `_release_with_backoff(...)`：

1. 基于 claim snapshot 的 `poll_backoff_attempt + 1` 形成下一 attempt；
2. 调用现有 `_backoff_delay_seconds(attempt, policy)`；
3. 使用同一 `backoff_initial_delay_seconds`、`backoff_multiplier`、`backoff_max_delay_seconds`；
4. 由 existing release operation 原子写 `next_observe_at`、attempt、diagnostic 并清 claim；
5. CAS/claim conflict 沿既有计数和 fail-closed 路径处理。

禁止在 timeout 分支内自行计算时间、复制 exponent/cap、使用 `poll_interval_seconds` 替代 error backoff，或引入第二 scheduler/policy。

## 4. 完整分支矩阵

| 路径 | observation / provider 结果 | publication authority | durable status | claim / cadence | terminal resolution |
|---|---|---|---|---|---|
| poll | `WaitPollReady` | 正常 finish | `WAITING -> resolved existing transition` | 既有 resolve path | 保留 completed/failed typed transition |
| poll | `WaitPollNotReady` | 正常 finish | `WAITING` | 既有 not-ready cadence，attempt reset/现有语义 | 无 |
| poll | authoritative `WaitPollLost` | 正常 finish | `WAITING -> LOST` | 既有 resolve path | **保留** typed lost |
| poll | observation timeout | token invalidated；late result rejected | `WAITING` | `ADAPTER_ERROR` + `wait_observation_timeout`，release，同 policy backoff | **禁止** `resolve_wait` / LOST |
| poll | adapter exception / invalid result | invocation 结束 | `WAITING` | 保留既有 adapter-error release/backoff | 无 |
| poll | observation capacity exhausted | 无新 authority 或依既有 runner contract | `WAITING` | 保留既有 capacity diagnostic/release cadence | 无 |
| cancelled abandon | explicit applied | 正常 finish | `CANCELLED` + existing abandoned marker | 保留既有 terminal abandon transition | 不调用 wait resolve |
| cancelled abandon | explicit unsupported | 正常 finish | `CANCELLED` + existing unsupported marker | 保留既有 transition | 不调用 wait resolve |
| cancelled abandon | explicit noop | 正常 finish | `CANCELLED` + existing noop marker | 保留既有 transition | 不调用 wait resolve |
| cancelled abandon | observation timeout | token invalidated；late result rejected | `CANCELLED` | `ABANDON_ERROR` + `wait_abandon_timeout`，release，同 policy backoff | **禁止** timeout terminal abandon |
| cancelled abandon | exception / snapshot failure | invocation 结束 | `CANCELLED` | 保留既有 abandon-error release/backoff | 无 |
| cancelled abandon | capacity exhausted | 无新 authority或依既有 runner contract | `CANCELLED` | 保留 retryable release/cadence | 无 |
| poller close/drain | outstanding observation 未在 shared close deadline 内结束 | revoke/close runner；late result rejected | 保持原业务状态 | 既有 shutdown diagnostic/release；poller 可保持 CLOSING | 禁止伪造 LOST/abandon terminal |
| wait deadline（非-CANCELLED poll path） | durable deadline 到期 | 与 observation timeout 分离 | 保留既有 FAILED contract | 既有 owner | 不受 R05 改写；`CANCELLED` 在 `poll_once()` 中先进入 abandon path，不能用 `_handle_time_boundary(...)` 解释或终止其长期 retry |

测试必须逐格断言状态、claim、diagnostic、next-observe 与 terminal side effects；不能只断言计数或日志。

## 5. 两 slice 原子边界

umbrella 的 2-slice baseline 仍是最佳最小原子边界，按“业务 owner 变更”与“跨层 no-diff/真实 public 证据”分离：

1. R05-S1 是唯一 production semantic transaction：修正 Host observation timeout transition，并以 Host owner tests 证明 token fence、release/backoff、non-terminal 与 provider terminal preservation。它不依赖 Engine 修改，单独可回滚、可审查。
2. R05-S2 不再创建第二 production transaction：先证明 Engine `agent.py` no diff，再增强真实本地 public smoke，证明 S1 经 Service/public Host wiring 后成立，同时保留 R04 config snapshot。把它并入 S1 会混合 state-machine root fix 与跨层 evidence；拆成第三 slice 又会把同一 no-diff/public acceptance 证据人为割裂，增加无语义价值的 gate。

### 5.1 R05-S1 — Host observation timeout release/backoff

#### Production 变更

- `dayu/host/wait_adapter.py`
  - poll `WaitObservationTimedOut`：删除 `WaitPollLost(ResolveWaitLostOutcome(...wait_observation_timeout...))` 构造及 `_resolve_claimed_wait(...)` 路径，改为 `_release_with_backoff(...)`，outcome `ADAPTER_ERROR`，error code `wait_observation_timeout`，保持 `WAITING`。
  - cancelled abandon `WaitObservationTimedOut`：删除 `_MarkWaitRecordAbandonTimeoutOperation` reachable transition，改为同一 `_release_with_backoff(...)`，outcome `ABANDON_ERROR`，error code `wait_abandon_timeout`，保持 `CANCELLED` 且不写 `poll_abandoned_at`。
  - 删除 `mark_wait_record_poll_abandon_timeout` import、`_MarkWaitRecordAbandonTimeoutOperation` 与旧调用；保留新 transient diagnostic 仍使用的 `_POLL_ERROR_CODE_ABANDON_TIMEOUT`，不删除或改写 typed authoritative lost / explicit lifecycle terminal types。
  - 不复制 token、backoff 或 durable update 逻辑。
- `dayu/host/durable/state.py`
  - 删除 `mark_wait_record_poll_abandon_timeout(...)` 的完整定义；不得改名保留、标 deprecated、兼容 re-export 或留下只服务该 invalid semantic 的 helper/code。
  - 同时删除当前 base 在 `dayu/host/durable/state.py:40:5` 已证明未使用的 `TERMINAL_RUN_STATUS_VALUES` import；这只是 planned changed owner file 的唯一 lint hygiene，不改变 durable semantic contract，也不授权清理其它 import、Ruff 项或代码。
  - 保留 `release_wait_record_poll_claim(...)` 对 `WAITING` / `CANCELLED` 的原子 release/backoff/diagnostic projection，保留 `mark_wait_record_poll_abandoned(...)` 对 explicit applied/unsupported/noop lifecycle outcome 的 terminal `poll_abandoned_at` 写入。
  - 不修改 durable schema、row shape、enum、codec、migration 或 fresh-schema contract；若 symbol scan 发现第二消费者，先停回 Controller，不在下游补兼容。
- `docs/host/design.md`
  - 只把当前 “cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker” 精确改写为：cancelled wait 的 abandon observation timeout 只写 poll-local transient `wait_abandon_timeout` diagnostic、释放 claim 并按 Host policy backoff，durable status 保持 `CANCELLED` 且不写 terminal `poll_abandoned_at`；只有 provider 显式返回 applied / unsupported / noop lifecycle outcome，才沿既有 transition 写 terminal abandon marker，且不调用 wait resolve。
  - 这是对已裁决状态机的真源纠错；不新增 retry 上限、deadline、policy/schema，也不改写 explicit terminal lifecycle outcome。
- `dayu/host/_wait_observation.py`：预期 no diff；现有 runner token/fence owner 已正确。若 owner-level regression 在 base 上证明 token 可 late publish，停止交 Controller，不在同 slice 自建第二 fence。
- `dayu/host/waiting.py`：预期 no diff；typed terminal resolution owner 已正确。若为通过测试需要在此识别 timeout string/code，说明 owner 放错，必须停止。

#### Tests

- `tests/host/test_wait_observation_runner.py`
  - 将旧 poll timeout-to-lost 测试替换为 `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve`：先在 base 上红；实现后断言 `lost=0`、Wait/Run 保持 WAITING、四个 claim fields 清空、attempt 增加、`next_observe_at` 按 policy、diagnostic 为 `ADAPTER_ERROR/wait_observation_timeout`、resolver/terminal events 均无调用；释放 stuck adapter 后断言 late Ready dropped；到下一 due observation 再由 authoritative Ready 成功 resolve。
  - 将旧 abandon-timeout-marker 测试替换为 `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal`：先在 base 上红；实现后断言 Wait 仍 CANCELLED、`poll_abandoned_at is None`、claim release、attempt/next-observe、`ABANDON_ERROR/wait_abandon_timeout`；late Applied 不可发布；下一 due observation 的 explicit terminal outcome 才写 existing abandon marker。
  - 保留 low-level token invalidation、outstanding capacity 与 shared close deadline 测试。
- `tests/host/test_wait_adapter_polling.py`
  - 保留/强化 authoritative typed lost、Ready、NotReady、adapter exception、capacity、explicit applied/unsupported/noop、CAS conflict、close/shutdown owner assertions。
  - 对 authoritative lost 明确断言仍调用 common resolve path并 terminalize；timeout code 不得出现在该 provider typed branch。
- `tests/host/test_phase7_waiting_integration.py`
  - 增加 owner integration：poll timeout 不产生 resolve/terminal event，下一轮 Ready 仍能从同一 durable WAITING record 恢复并完成。
  - 删除 changed-file 内既有未使用 `UTC` import，使该文件 Ruff 归零。
- `tests/host/test_wait_record_state.py`
  - 增加 `test_cancelled_poll_timeout_release_preserves_claimability_after_due`：直接在 durable owner boundary claim `CANCELLED` row，以 `release_wait_record_poll_claim(...)` 写 `ABANDON_ERROR/wait_abandon_timeout`，断言四个 claim fields 清空、`poll_abandoned_at is None`、attempt/next-observe/diagnostic 同源；到 due 后同一 row 可再次 claim。
  - 保留 `test_poll_abandon_success_marks_row_and_clears_claim`，证明 explicit applied/unsupported/noop terminal outcome 仍通过 `mark_wait_record_poll_abandoned(...)` 写 terminal marker；不得用 test fixture 直接调用已删除 timeout primitive。

#### R05-S1 atomic completion

- 新 timeout owner tests 在未改 production 时按预期失败，生产修改后通过。
- branch matrix 的 poll、abandon、exception、capacity、close-drain、authoritative lost 全部有 owner assertion。
- `dayu/host/durable/state.py` 的 atomic diff 只允许删除 invalid `mark_wait_record_poll_abandon_timeout(...)` primitive、仅服务该 invalid semantic 的代码，以及 §2.3 已登记的 unused `TERMINAL_RUN_STATUS_VALUES` import；两条 touched-file F401 均须在同一 S1 归零，不授权其它 lint cleanup。
- planned changed production files 为 `dayu/host/wait_adapter.py` 与 `dayu/host/durable/state.py`；实际 changed-production list 中每个文件都必须在 §8 的 green coverage session 内分别 >=80%，不得用聚合覆盖率代替。
- `_wait_observation.py`、`waiting.py` 若出现 diff，除非有新的直接 owner evidence，否则 stop。
- `docs/host/design.md` 的精确真源纠错在 S1 与 owner code 同一 semantic transaction 完成；Host README/test README 的最终开发者说明仍放在 S2 acceptance，不在 S1 制造中间 README contract。

### 5.2 R05-S2 — Engine no-diff regression 与真实 public smoke

#### Engine production no-diff 前置证据

先只改 `tests/engine/test_agent_phase3_tool_call.py` 增加 `test_accepted_awaiting_external_operation_outlives_handshake_timeout`，不得预先改 `dayu/engine/agent.py`：

1. test executor 在小于 handshake budget 的时间内返回 accepted `ToolAwaitingOutcome`；
2. 它同时启动一个独立、可观测的 local async operation；operation duration 明确大于 `tool_execution_timeout_seconds`；
3. Agent 必须投影 `TOOL_AWAITING` / `RUN_SUSPENDED`，不得产生 timeout `RUN_FAILED`；
4. 越过 handshake budget 后，外部 operation 仍可完成；其完成不被 Agent handshake timer cancel；
5. 现有 `test_tool_execution_timeout_fails_run_without_tool_result` 继续证明 `ToolExecutor.execute` 自身未返回时仍会 timeout。

该 regression 预期在 base production 上直接通过。通过后执行 source audit，确认 `tool_execution_timeout_seconds` 只在 execute handshake 前读取/使用，并记录 `dayu/engine/agent.py: no diff`。若 regression 失败或 source audit 发现 accepted awaiting 后仍读取该 timeout，不得在本 plan 下直接改 `agent.py`；先停回 Controller，提交直接失败证据并重新裁决 allowlist/owner。因当前证据预期通过，R05 最终 closed diff **不包含** `dayu/engine/agent.py`。

#### 真实本地 public smoke

修改 `utils/smoke_host_public_awaiting_entrypoint.py`，保留 packaged `ConfigLoader -> provider discovery -> Service composition -> open_host -> durable poller -> public terminal/outbox` 主链，无网络、无 monkeypatch、无私有 direct-resolve shortcut。local deterministic worker 只替代外部 LLM/provider，不替代 Host/poller/durable/public entrypoint。

smoke 必须同时证明：

1. 输出并断言 R04 三个 typed provider modes 与 packaged 12-field policy snapshot 完全不变。
2. 通过 `ServiceRunOverrides` 设定一个具名 test-only handshake budget；worker 收到的 `AgentRunRequest` 必须含该 budget。
3. local external operation 的实测 duration 大于 handshake budget，但 awaiting handshake 在 budget 内被 accepted；Run 进入 WAITING，不因 budget 到期 FAILED。
4. 从 config-owned typed policy 以 `dataclasses.replace` 只派生 test timing override；不能调用无参数 `WaitPollerRuntimePolicy()`，不能把 smoke 值写回产品 config，也不能创建第二 backoff 算法。packaged snapshot 与 test-effective timing 分开打印。
5. 第一次 poll observation 故意阻塞超过 `adapter_call_timeout_seconds`，poller 返回 timeout 后立即断言 durable Run/Wait 仍 WAITING、claim 已释放、`next_observe_at` 为 backoff、diagnostic 为 `ADAPTER_ERROR/wait_observation_timeout`，没有 terminal outbox。
6. 第一次 observation 在 timeout 后晚到 Ready；token fence 必须拒绝该 publication。smoke 要输出 late-publication-dropped 证据，且 Run 仍 WAITING。
7. 不篡改 durable due time；等待真实 backoff 到期后，第二次 observation 读取同一已完成 local operation 并返回 Ready，最终 public result SUCCEEDED，worker resume count、terminal event 与 outbox 精确匹配。
8. timing 必须由具名 test-only constants 表达，至少包含 handshake budget、adapter timeout、initial backoff、state-poll quantum、relative margin、overall deadline 与 CI duration cap；必须在运行时打印并断言 `handshake budget + margin < observation timeout`、`observation timeout + margin < measured operation duration`、`measured operation duration + margin < observation timeout + initial backoff`，且 `margin >= 5 * state-poll quantum`。所有 test-effective policy 仍从 packaged snapshot 通过 `dataclasses.replace` 派生；不得写回产品 config。
9. handshake accepted、operation started/finished、first observation entered、late result release、runner dropped count、second observation entered 必须分别由 `asyncio.Event` / `threading.Event`、`Condition` 或 durable state polling 驱动；状态 polling 只允许按具名 quantum 让出执行，不得用单次固定 sleep 的经过推断业务状态。
10. smoke 开始时只用 `time.monotonic()` 建立一个具名 overall deadline；所有 phase wait 都从该 deadline 计算 remaining budget，且 overall deadline 不得超过具名 CI duration cap。实现应提供模块级 phase wait / diagnostic helper；任一 phase 失败必须报告已完成/未完成 phase、最近 monotonic elapsed、runner dropped count，以及 Run/Wait claim、status、next-observe、diagnostic、`poll_abandoned_at`、terminal outbox 快照，不能只抛裸 timeout。

#### README decision

- `dayu/host/README.md`：需要更新。只写已实现的 current contract：observation timeout 是 poll-local diagnostic + claim release/backoff，poll 保持 WAITING，abandon timeout 保持 retryable CANCELLED；只有 typed provider lost / explicit lifecycle terminal outcome 可 terminalize。
- `tests/README.md`：需要更新。记录 R05 owner regression 与 public awaiting smoke 覆盖的 contract，不写实施过程或 gate 状态。
- `dayu/engine/README.md`：已阅读；当前已说明 timeout 只限制 tool execution handshake 且不证明底层工作停止。`agent.py` no diff 时不做机械修改；只有新增稳定用户 contract 未被当前文本覆盖且 Controller 同意时才更新。
- 根 `README.md`、`dayu/README.md`：无入口、用户工作流、分层或装配 contract 变化，不触发。

## 6. Closed allowlist

### 6.1 本次 plan artifact gate

唯一可写：

- `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
- `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md`

### 6.2 后续 implementation gate 的 closed allowlist

Production：

- `dayu/host/_wait_observation.py` — 允许核对，预期 no diff；只有直接 owner regression 证明错误才可停回 Controller，不能自行修改。
- `dayu/host/wait_adapter.py` — 预期 production diff；修正两个 timeout decision branches并删除 invalid wrapper/import/call。
- `dayu/host/durable/state.py` — 预期 production diff；只删除 `mark_wait_record_poll_abandon_timeout(...)` 及仅服务该 invalid semantic 的代码，并删除 §2.3 已登记的唯一 unused `TERMINAL_RUN_STATUS_VALUES` import；禁止其它 lint cleanup 或 durable/schema 扩域。
- `dayu/host/waiting.py` — 允许核对，预期 no diff。
- `dayu/engine/agent.py` — regression 前置 conditional allowlist；当前判定 no diff，最终 diff 不得包含。

Tests / smoke：

- `tests/host/test_wait_observation_runner.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_wait_record_state.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `utils/smoke_host_public_awaiting_entrypoint.py`

Implementation docs / README：

- `docs/host/design.md` — R05-S1 write allowlist；只允许 §5.1 的精确 close-marker 句纠错。
- `dayu/host/README.md`
- `tests/README.md`
- `dayu/engine/README.md` — read/decision only，预期 no diff。

只运行、不修改的完整 `tests/host/` coverage 集与相关 Service/config/Fins tests 不因被执行而进入 write allowlist。任何其他路径出现在 diff，立即停止。

## 7. Exact test nodes 与 commands

所有 Python 命令先执行：

```bash
source .venv/bin/activate
```

### 7.1 R05-S1 test-first 与 focused owner nodes

先仅修改 tests，运行以下新节点；在 production 未改时必须失败在预期 semantic assertion，而非 fixture/setup：

```bash
python -m pytest -q \
  tests/host/test_wait_observation_runner.py::test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve \
  tests/host/test_wait_observation_runner.py::test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal \
  tests/host/test_phase7_waiting_integration.py::test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run
```

durable release primitive 已有正确 owner 行为；新增 preservation node 在删除 invalid sibling primitive 前后都必须为绿，不能把它误列为 test-first 红灯：

```bash
python -m pytest -q \
  tests/host/test_wait_record_state.py::test_cancelled_poll_timeout_release_preserves_claimability_after_due \
  tests/host/test_wait_record_state.py::test_poll_abandon_success_marks_row_and_clears_claim
```

实现后运行：

```bash
python -m pytest -q \
  tests/host/test_wait_observation_runner.py::test_timeout_invalidates_token_and_late_result_cannot_publish \
  tests/host/test_wait_observation_runner.py::test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve \
  tests/host/test_wait_observation_runner.py::test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal \
  tests/host/test_wait_observation_runner.py::test_supervisor_close_uses_one_shared_deadline_and_stays_closing \
  tests/host/test_wait_adapter_polling.py::test_poll_adapter_ready_result_resolves_wait \
  tests/host/test_wait_adapter_polling.py::test_poll_adapter_not_ready_leaves_wait_active \
  tests/host/test_wait_adapter_polling.py::test_poll_adapter_lost_result_closes_run \
  tests/host/test_wait_adapter_polling.py::test_abandon_adapter_snapshot_projection_failure_releases_with_backoff \
  tests/host/test_wait_adapter_polling.py::test_cancelled_poll_wait_is_abandoned_once_without_resolve \
  tests/host/test_wait_adapter_polling.py::test_failed_cancelled_wait_abandon_is_retried_next_poll \
  tests/host/test_wait_adapter_polling.py::test_active_poll_claim_suppresses_second_poller_adapter_call \
  tests/host/test_wait_adapter_polling.py::test_expired_poll_claim_allows_retry \
  tests/host/test_wait_adapter_polling.py::test_invalid_poll_deadline_fails_closed_without_business_lost \
  tests/host/test_wait_record_state.py::test_cancelled_poll_timeout_release_preserves_claimability_after_due \
  tests/host/test_wait_record_state.py::test_poll_abandon_success_marks_row_and_clears_claim \
  tests/host/test_phase7_waiting_integration.py::test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run
```

Host focused files：

```bash
python -m pytest -q \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_record_state.py
```

### 7.2 R05-S2 Engine nodes

```bash
python -m pytest -q \
  tests/engine/test_agent_phase3_tool_call.py::test_accepted_awaiting_external_operation_outlives_handshake_timeout \
  tests/engine/test_agent_phase3_tool_call.py::test_tool_awaiting_suspends_run_with_accepted_and_awaiting_records \
  tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_fails_run_without_tool_result \
  tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_wins_over_cleanup_cancel \
  tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_wins_over_runner_close_cancel \
  tests/engine/test_agent_phase3_tool_call.py::test_all_awaiting_batch_suspends_with_empty_accepted_records \
  tests/engine/test_agent_phase3_tool_call.py::test_late_cancel_after_accepted_before_awaiting_does_not_swallow_suspend
```

然后运行整文件：

```bash
python -m pytest -q tests/engine/test_agent_phase3_tool_call.py
```

### 7.3 R04 ownership preservation 与相关 Service/public assembly regression

```bash
python -m pytest -q \
  tests/runtime/test_config_loader.py::test_host_runtime_wait_poller_policy_block_is_required \
  tests/runtime/test_config_loader.py::test_host_runtime_wait_poller_policy_fields_are_all_required \
  tests/runtime/test_config_loader.py::test_host_runtime_wait_poller_policy_rejects_unknown_field \
  tests/fins/test_fins_ingestion_tools.py::test_awaiting_resolution_mode_parser_accepts_closed_typed_modes \
  tests/fins/test_fins_ingestion_tools.py::test_awaiting_resolution_mode_parser_rejects_missing_or_illegal_values \
  tests/fins/test_fins_ingestion_tools.py::test_each_fins_awaiting_provider_validates_mode_before_runtime_creation \
  tests/service/test_host_assembly.py::test_compose_open_host_options_projects_complete_config_owned_wait_policy \
  tests/service/test_host_assembly.py::test_scene_tool_selection_does_not_own_wait_poller_composition \
  tests/service/test_host_assembly.py::test_manual_mode_composes_binding_without_background_poller \
  tests/service/test_host_assembly.py::test_poll_and_manual_modes_partition_runtime_composition \
  tests/service/test_host_assembly.py::test_callback_mode_fails_closed_before_open_host
```

Aggregate regression：

```bash
python -m pytest -q \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_record_state.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/runtime/test_config_loader.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/service/test_host_assembly.py \
  tests/service/test_fins_wait_adapter.py \
  tests/service/test_entrypoint_runtime_interactive_path.py
```

不得使用会收集零节点的 `tests/service/test_entrypoint_runtime.py -k 'awaiting or resume'` 作为 validation；当前 base 该命令是 `43 deselected`，R05 已以上述 exact Service nodes 作等价、非空替换。

## 8. Coverage 门禁：R05 changed-owner coverage measurement

R05-S1 必须先完整运行并通过 §7.1 的 exact owner / focused / aggregate 功能矩阵；本节 session 只测量 R05 两个实际 changed production owner 的覆盖率，不是完整 Host regression acceptance，也不能替代、删减或放宽 §7.1 的任何功能节点。

R05 changed-owner coverage measurement 的唯一命令为：

```bash
python -m pytest -q tests/host \
  --ignore=tests/host/test_toolruntime_executor.py \
  --ignore=tests/host/test_dispatch_scheduler.py \
  --cov=dayu.host.durable.state \
  --cov=dayu.host.wait_adapter \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:workspace/tmp/r05-s1-coverage.json
python -m coverage report --include='dayu/host/durable/state.py' --fail-under=80
python -m coverage report --include='dayu/host/wait_adapter.py' --fail-under=80
```

只允许上述两个 `--ignore`：保留既有 `tests/host/test_toolruntime_executor.py` 排除，并只额外排除 `tests/host/test_dispatch_scheduler.py`。不得再增加其它 ignore、deselect、xfail、retry、failure exemption 或测试选择豁免。

plan-fix 期间的直接 probe 证明原四文件 owner 集只有 `durable/state.py=64%`、`wait_adapter.py=78%`，不满足门禁。Controller 在当前 R05-S1 diff 上独立运行上述候选 session，结果为 `1830 passed, 2 skipped, 5 deselected`，`durable/state.py=83%`、`wait_adapter.py=86%`，随后两个逐文件 `coverage report --fail-under=80` 均通过；这只证明修订后的 coverage measurement 可执行，不提前接受 S1。排除的 `test_toolruntime_executor.py` 属于无关 process-backed ToolRuntime 路径；额外排除的 `test_dispatch_scheduler.py` 属于 §12 已确定的 Host scheduler close / terminal promotion coordination owner，且对 R05 wait observation owner 无 source / propagation 交集。两者仍受各自 owner 的项目矩阵治理，不能把排除解释成忽略 R05 propagation 或把 scheduler 缺陷称为已修复。

修订后的 R05 changed-owner coverage measurement 必须整体绿色；planned changed production files `durable/state.py` 与 `wait_adapter.py` 必须分别 >=80%，不得用 aggregate coverage 替代逐文件门禁。`_wait_observation.py`、`waiting.py` 只要出现 diff 就先触发 owner/allowlist stop，而不是仅靠覆盖率继续。

R05-S2：

```bash
python -m pytest -q tests/engine/test_agent_phase3_tool_call.py \
  --cov=dayu.engine.agent \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:workspace/tmp/r05-s2-coverage.json
```

当前 base `agent.py=80%`；最终预期 no diff，因此不存在 Engine changed-production coverage debt。若 `agent.py` 出现 diff，即使覆盖 >=80% 也不能继续，必须先回 Controller。

最终从 `git diff --name-only 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu` 生成 actual changed-production list；预期精确为 `dayu/host/durable/state.py`、`dayu/host/wait_adapter.py`。对每个实际 changed production file 单独执行 `coverage report --include='<exact file>' --fail-under=80`，禁止用总覆盖率代替逐文件门禁；若列表出现其它文件，先按 §13 停止。

## 9. Pyright、Ruff 与 diff 门禁

### 9.1 Pyright

```bash
python -m pyright dayu/ tests/ utils/
```

必须继续为 0 error；任何新增或扩散立即停止。

### 9.2 Ruff 既有基线与 changed-file 门禁

在 implementation 开始前，以固定 base 重跑并保存完整 machine-readable Ruff 输出到 `workspace/tmp/`。每个既有诊断必须登记 umbrella 六元组：

```text
(exact command,
 test node 或 lint path,
 error type / Ruff rule,
 first stable stack frame 或 path:line:column,
 normalized text fingerprint,
 baseline SHA)
```

baseline SHA 固定为 `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。只有六项全部相同且 source/propagation 与 R05 changed files 不相交，才可继承。当前全量 167 条是既有 registry；changed files `durable/state.py` 与 `test_phase7_waiting_integration.py` 的两条 F401 必须在本 WU 清除，不能继承。

changed Python files 必须单独 Ruff 全绿：

```bash
python -m ruff check \
  dayu/host/durable/state.py \
  dayu/host/wait_adapter.py \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_record_state.py \
  tests/engine/test_agent_phase3_tool_call.py \
  utils/smoke_host_public_awaiting_entrypoint.py
```

最终再运行：

```bash
python -m ruff check dayu tests utils
```

全量命令允许继续非零，但 residual registry 必须精确等于 base registry 减去本 WU 明确修复的两条 changed-file F401：若没有其他 base diagnostic 因本 WU 路径位移，预期为 `167 - 2 = 165` 条。仍须逐六元组核对其它 residual；任何新增 rule、severity、path/location、fingerprint，或无法由“明确删除的 touched-file baseline entry”解释的数量变化，都算 new/spread failure，立即停止。不得用 `noqa`、per-file ignore、配置改动或关闭 rule 绕过。

### 9.3 Diff

```bash
git diff --check
git status --short
git diff --name-only 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
git diff --stat 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

逐项对照 §6 allowlist；预期 production diff 为 `dayu/host/durable/state.py`、`dayu/host/wait_adapter.py`，implementation-doc diff 包含 `docs/host/design.md`；`dayu/engine/agent.py`、`dayu/host/_wait_observation.py`、`dayu/host/waiting.py` 最终应无 diff。

## 10. Source、propagation 与 security scans

### 10.1 timeout 不得传播成 terminal

```bash
rg -n 'WaitObservationTimedOut|wait_observation_timeout|wait_abandon_timeout|ResolveWaitLostOutcome' \
  dayu/host/_wait_observation.py dayu/host/wait_adapter.py dayu/host/waiting.py dayu/host/durable/state.py \
  tests/host
if rg -n 'mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation' dayu tests; then
  echo 'invalid timeout-only abandon terminal symbol remains' >&2
  exit 1
fi
git diff --exit-code 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu/host/durable/schema.py
```

人工核对：

- `wait_observation_timeout` 只作为 poll-local diagnostic code 和测试预期出现，不得位于 `ResolveWaitLostOutcome` 构造或 `_resolve_claimed_wait` timeout 分支。
- `_MarkWaitRecordAbandonTimeoutOperation` 与 `mark_wait_record_poll_abandon_timeout` 在 production/tests 中必须零定义、零调用；scan 的成功条件是 `rg` 无匹配并由 guard 返回零，不接受 deprecated/docstring/compat/dead helper 残留。
- `dayu/host/durable/schema.py` 必须无 diff；`poll_abandoned_at` 继续只承载 explicit lifecycle terminal marker，不因删除 invalid timeout primitive而删除或迁移。
- `ResolveWaitLostOutcome` 仍存在于 public typed contract、waiting owner、`WaitPollLost` 与 authoritative provider tests；禁止为了让 scan 为零而删除正确 LOST 语义。

### 10.2 late publication token/fence 唯一路径

```bash
rg -n '_start_observation|_invalidate_token|_publish|WaitObservationTokenState|generation|result_queue' \
  dayu/host/_wait_observation.py dayu/host/wait_adapter.py tests/host/test_wait_observation_runner.py
```

人工核对 runner 仍是唯一 publication authority；不得在 adapter/store 新建 token、event、queue、future 或 late-result fallback。timeout invalidation 与 `_publish` 检查必须继续由同一锁和同一 token/generation 决定。

### 10.3 claim/backoff 唯一真源

```bash
rg -n '_release_with_backoff|_backoff_delay_seconds|release_wait_record_poll_claim|poll_next_observe_at|poll_backoff_attempt' \
  dayu/host/wait_adapter.py dayu/host/durable/state.py tests/host
```

timeout 分支只能调用既有 `_release_with_backoff`；不得出现第二套计算或直接 raw-field update。

另外核对 `tests/host/test_wait_record_state.py::test_cancelled_poll_timeout_release_preserves_claimability_after_due` 与 explicit terminal parameterized node 同时通过，证明 timeout retry 与 explicit terminal marker 仍由两个合法 owner operation 分开承诺。

### 10.4 Engine handshake no-diff

```bash
rg -n 'tool_execution_timeout_seconds|await_or_cancel_or_timeout|ToolAwaitingOutcome|RUN_SUSPENDED' \
  dayu/engine/agent.py tests/engine/test_agent_phase3_tool_call.py
git diff --exit-code 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu/engine/agent.py
```

人工核对 timeout read/use 均发生在 `ToolExecutor.execute` 返回前；accepted awaiting 之后无 timer reuse。

### 10.5 R04 ownership 与禁止项

```bash
rg -n 'awaiting_resolution_mode|wait_poller_policy' \
  dayu/config/tool_discovery.json dayu/config/host_runtime.json dayu/fins/tools dayu/service \
  dayu/config/prompts dayu/config/execution_profiles.json
rg -n 'with_entrypoint_wait_poller_policy|_scene_selects_fins_awaiting_tools|WaitPollerRuntimePolicy\(\)' dayu tests utils
```

预期：provider modes 与 12 fields 仍只从 R04 owner 路径投影；prompt/execution profile 不拥有 policy；旧 scene/name heuristic 与无参数 code-default construction 为零。

对 production diff 做安全/延期 scope scan：

```bash
git diff --unified=0 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu \
  | rg -n 'authorization|permission|callback transport|process isolation|process_backed|subprocess|Issue 175'
```

预期零命中。若命中只是既有上下文，改用 `git diff --unified=0` 的 added lines 人工复核；任何 R05 新语义命中都停止。另核对 cancellation、claim CAS、capacity 与 close-drain 测试未被删除或放宽。

## 11. 真实本地 smoke command 与通过证据

```bash
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r05-host-public-awaiting-entrypoint
```

必须在无外网、无外部 provider credential 的本地环境通过，并打印/断言至少以下证据：

- packaged `poll/manual/callback` typed modes；
- 完整 packaged 12-field policy snapshot；
- test-effective handshake/observation/backoff timings 及不等式；
- accepted handshake elapsed 小于 budget；
- external operation elapsed 大于 handshake budget；
- public Run observed WAITING；
- first observation timeout；
- timeout 后 `WAITING + claim released + next_observe_at + ADAPTER_ERROR/wait_observation_timeout`；
- late Ready publication dropped，且无 terminal outbox；
- backoff 到期后的 second observation Ready；
- final SUCCEEDED、resume accept count、terminal event 与 outbox exact match。

smoke orchestration 必须按以下 condition-driven phase 顺序执行：

1. 用 `time.monotonic()` 建立唯一 overall deadline，启动 operation 后等待 `operation_started` event；等待 worker 的 accepted-handshake signal 与 durable/public WAITING state，而不是 sleep 后猜测。
2. 等待 `first_observation_entered` event；adapter 的首次调用由 event gate 阻塞，直到 Host durable polling 显示 timeout diagnostic、claim release 与 backoff due time。
3. timeout state 成立后 signal operation finish / late-result release，并等待 `operation_finished`、`late_result_released` 与 runner dropped-count condition；只有 dropped count 增加且 durable state 仍 WAITING 才进入下一 phase。
4. 不篡改 due time，按 state-poll quantum 查询 durable due/claim state并等待 `second_observation_entered` event；第二次 observation 从同一 finished operation 返回 Ready。
5. 通过 public result/state condition 等待 SUCCEEDED、terminal event 与 outbox exact match。

每个 event/condition/state-poll wait 都使用 overall deadline 的 remaining budget；state polling 间的 quantum 只负责让出调度，不作为“时间已过所以状态必然成立”的证据。实现必须打印具名 constants、相对 margin 断言和 overall/CI cap，并保证最坏路径在有限 CI duration 内结束。任一 phase 失败时，错误必须包含 phase ledger 和最近 durable/public snapshot，至少覆盖 Run/Wait status、四个 claim fields、next observe、backoff attempt、diagnostic、`poll_abandoned_at`、runner dropped count 与 terminal outbox；不得只输出 `TimeoutError`。

smoke workspace 只位于 `workspace/tmp/`，不删除 Host artifacts；输出不得包含 secret。

## 12. Baseline failure registry 与非 R05 root-cause disposition

每个非绿 command 都必须登记：

1. exact command；
2. test node / lint path；
3. error type 或 Ruff/pyright rule；
4. first stable stack frame / `path:line:column`；
5. normalized error text fingerprint；
6. baseline SHA。

继承条件是六项完全相同，且 changed source 与 propagation path 均不相交。以下任一情况不能标记 inherited：

- failure count、node、location、fingerprint 或 severity 变化；
- 同一 rule 移入 R05 changed file；
- 原失败消失但出现数量相同的新失败；
- timeout semantic assertion、terminal event、claim state 或 smoke 行为变化；
- pyright 从零变为非零。

accepted plan 修订前的 coverage command 产生以下完整失败六元组：

```text
exact command:
  python -m pytest -q tests/host
    --ignore=tests/host/test_toolruntime_executor.py
    --cov=dayu.host.durable.state
    --cov=dayu.host.wait_adapter
    --cov-branch
    --cov-report=term-missing
    --cov-report=json:workspace/tmp/r05-s1-coverage.json
node:
  tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
error:
  HostApiError: Host execution is unavailable
first stable frame:
  dayu/host/_execution_health.py:258 in raise_if_scheduler_unavailable
normalized fingerprint:
  scheduler close 已提交私有 close gate 时，active worker clean EOF terminal closeout 同步 wake queue promotion，被 force health gate 拒绝
validation HEAD:
  f52b81f9f4abd37a65c35ea98955a416079e5d9e plus current uncommitted R05-S1 diff
```

该 session 的结果是 `1 failed, 1917 passed, 1 skipped, 5 deselected`；失败 session 中两个 owner 分别为 83% / 86%，但整个 session 不是绿色，不能冒充通过。

Controller 读取 `HostDispatchScheduler.close()`、worker clean-EOF closeout、`EngineEventIngestor._with_terminal_promotion_retry(...)`、scheduler wake health gate 与失败测试，并独立运行 `workspace/tmp/test_r05_scheduler_close_probe.py`，结果 `1 passed`。确定性 probe 证明同一事件顺序：

1. scheduler `close()` 先提交 `self._closed = True`；
2. close 在取消并等待 promotion task 时让出 event loop；
3. 已 active 的 worker 此时以 clean EOF 完成，Host 提交 terminal closeout；
4. terminal closeout 同步调用 queue-promotion wake；
5. scheduler 私有 close gate 以 `force=True` 拒绝 wake，异常从 active task 传播回 `close()`。

因此 root cause 是 Host scheduler close 与 terminal promotion coordination 的线性化缺口，不是 R05 timeout transaction、测试 fixture、wait policy 或 coverage instrumentation 的错误。`tests/host/test_dispatch_scheduler.py` 对 `wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord` 及 R05 两个删除/复用 primitive 的 source scan 为零；`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 与该测试文件相对 R05 plan base 均无本 slice diff。该失败不得称为 flake、inherited pass 或已修复；其产品 owner 超出 R05-S1 closed allowlist，当前 umbrella 不修复、不创建 issue，也不归入 Issue 175。

§8 通过只额外排除该独立 owner test，把 coverage measurement 与无关 scheduler lifecycle owner 解耦；这不是一般失败豁免。修订后的候选 session 已由 Controller 取得 `1830 passed, 2 skipped, 5 deselected`、83% / 86% 及两个逐文件阈值通过证据，但 S1 仍须在 plan correction review 闭环后回 Controller 执行全部 functional、coverage、pyright、Ruff、scan 与 README-decision gates。

plan-fix 探索性完整 `tests/host` coverage probe 另触发 15 个 `test_toolruntime_executor.py` process-backed `PicklingError`；其六元组登记在 plan-fix artifact，不能当作通过证据或 R05 inherited exemption。§8 保留对该无关文件的既有排除。Ruff 全量 167 是 required-gate 已知既有红线；两条 changed-file F401 明确在本 WU 修复，预期 residual 为 165，其余 residual 必须逐六元组匹配。任何测试新增失败都不是“因为旧测试也绿/红”可豁免。

## 13. Stop conditions

出现以下任一条件立即停止并把 evidence 交 Controller；不得用 fallback、兼容 shim 或扩大 allowlist继续：

1. 正确 transition 要求 `dayu/host/durable/state.py` 超出“删除 `mark_wait_record_poll_abandon_timeout(...)` 及仅服务 invalid semantic 的代码，并删除 §2.3 已登记的唯一 unused `TERMINAL_RUN_STATUS_VALUES` import”的其它修改，或要求修改 schema、enum、migration、任一 allowlist 外 production owner。
2. 需要新增 policy 字段、timer、scheduler、runner、token/fence 或 lost outcome 才能通过。
3. `WaitObservationRunner` owner regression 证明当前 token/generation fence 可接受 late result。
4. Engine regression 在 base production 上失败，或 accepted awaiting 后仍读取/使用 handshake timeout。
5. 实现需要改 `dayu/engine/agent.py`、`dayu/host/waiting.py` 或 `_wait_observation.py` 才能补救 adapter decision。
6. timeout 仍能调用 resolve path、写 LOST、写 `poll_abandoned_at`，或 terminal outbox/Run status 与 WaitRecord 不同源。
7. provider authoritative lost 或 explicit lifecycle terminal outcome 被误改为 retry。
8. R04 12-field snapshot、typed modes、provider config ownership发生变化，或恢复 scene/name heuristic/code default。
9. capacity、CAS、claim ownership、cancellation、close-drain、security/fencing 断言被删除、放宽或绕过。
10. 修订后的 R05 changed-owner coverage measurement 未整体绿色、两个实际 changed production files 任一逐文件 coverage <80%、pyright 新增错误、changed-file Ruff 非零、full Ruff residual 无法按六元组解释，或 required source / propagation / security scan 与 README decision 被删除、放宽或跳过。
11. diff 出现 closed allowlist 外文件，或 `docs/host/design.md` 需要超出 §5.1 精确句子纠错的新产品 contract 裁决。
12. 为绕过 scheduler close / terminal promotion coordination 缺口而尝试新增第三个 ignore、deselect、xfail、retry、failure exemption，或需要修改 `dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` / scheduler owner tests；必须保留完整六元组与确定性 probe，停止交 Controller，不得称为 flake、inherited pass 或已修复。

## 14. Review handoff 与 completion evidence

本次 validation plan correction 是 accepted plan 的同一 R05 correction，不改变两 slices、产品 owner、产品 allowlist 或 semantic contract。correction 完成后下一步只回 Controller validation；不得自行进入 R05-S1 剩余 validation、R05-S2、code review、commit、aggregate gate、push 或 PR。

Controller validation 与后续完整双路 plan-correction review 必须核对：

- §7.1 exact owner / focused / aggregate functional matrices 是否原样保留，coverage measurement 是否没有替代任何功能节点；
- §8 修订前后命令是否只增加 `tests/host/test_dispatch_scheduler.py` 排除，并保留 `tests/host/test_toolruntime_executor.py` 排除；是否没有其它 ignore / deselect / xfail / retry / failure exemption；
- 修订后的 R05 changed-owner coverage measurement 是否要求整体绿色，`durable/state.py` 与 `wait_adapter.py` 是否仍分别执行 `--fail-under=80`；
- §12 是否保留失败 session 的完整六元组、`1 failed, 1917 passed, 1 skipped, 5 deselected`、确定性 probe `1 passed`、同源 root cause 与 Controller 候选 session `1830 passed, 2 skipped, 5 deselected` / 83% / 86% 证据；
- scheduler close / terminal promotion coordination 是否只作为非 R05 产品 residual owner boundary，当前不修、不创建 issue、不归入 Issue 175，也不被称为 flake、inherited pass 或已修复；
- 当前七路径受保护 implementation/test/design diff digest 是否保持 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`，correction 是否只修改计划与 correction artifact。

原 accepted-plan 全文双路 review 要点继续保留：

- 本 plan 是否严格映射 R05 manifest 与 Topic 5 final decision；
- root cause 是否只落在 `WaitPoller` decision owner；
- `durable/state.py` 是否只删除 invalid timeout-only primitive 与 §2.3 已登记的唯一 unused `TERMINAL_RUN_STATUS_VALUES` import，`agent.py` no-diff 是否有直接证据；
- `docs/host/design.md` 的 planned writeback 是否精确表达 transient diagnostic + release/backoff + keep CANCELLED + no `poll_abandoned_at`，同时保留 explicit lifecycle terminal outcome；
- 两 slice 是否保持 umbrella 原子边界；
- branch matrix、exact nodes、coverage、Ruff registry、scans、public smoke 是否 code-generation-ready；
- closed allowlist 与 stop conditions 是否足以阻止 R06+/Issue 175/callback/permission 扩域。

本轮同一 R05-S1 validation plan correction 与 `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md` 已完成，当前停回 Controller validation。只有 Controller 接受后，才可进入 AgentMiMo / AgentDS 双路完整 plan-correction review；review 必须覆盖修订后的完整 validation / gate-state contract，不能只看本次 stale 文本局部 diff。历史 `R05-PF-01` 至 `R05-PF-04` 与 `R05-PRR-F01` 保持已关闭，不得冒充当前 gate；本轮不得自行启动 review、恢复 R05-S1 validation 或进入 implementation。

未来 implementation completion report 必须逐项提供：

- slice base/end SHA 与 exact diff paths；
- 新 owner tests 在 base 上的预期红、production 修改后的绿；
- focused、aggregate、修订后 R05 changed-owner coverage measurement、两个逐文件 coverage、pyright、Ruff、diff-check 的 exact command/result；coverage session 必须整体绿色；
- full Ruff 六元组 residual diff；
- source/propagation/security scan 结果；
- README decision；
- public smoke 完整关键证据；
- `agent.py` no-diff 证明；
- residual risks 与 deferred owners。
- scheduler close / terminal promotion coordination 的完整六元组、确定性 probe 与非 R05 owner disposition；不得把它报告为已修复、inherited pass、flake、Issue 175 子项或 R05 completion。

## 15. Residual owners 与 blocking questions

Residual owners 保持既有归属：

- Host scheduler close / terminal promotion coordination：scheduler `close()` 先提交私有 close gate，在等待 promotion task cancellation 时允许 active worker clean EOF terminal closeout；closeout 同步 wake queue promotion 后被 force health gate 拒绝，异常传播回 `close()`。这是已由确定性 probe 复现的独立 Host lifecycle owner 缺口，不属于 R05 timeout transaction、测试 fixture、wait policy 或 coverage instrumentation。当前 umbrella 只在 coverage measurement 中与其解耦，不修改 scheduler 产品/测试、不创建新 issue、不归入 Issue 175；后续 destination 只能由 Controller / 用户另行裁决。
- R05 explicit residual：`CANCELLED` wait 的 abandon observation 若一直 timeout 且 provider 从不返回 explicit lifecycle terminal outcome，当前 call order 不进入 `_handle_time_boundary(...)`，因此该 record 可能长期按 `backoff_max_delay_seconds` capped cadence 重试，并间歇占用有限 observation capacity。当前安全边界仅是 claim CAS、`max_outstanding_adapter_calls` cap、finite single-call timeout、late-publication fencing 与 backoff cap；它们限制单轮/并发资源，不等同于终止证据。
- future Host cancel/abandon durable evidence policy：若产品需要在缺少 provider terminal outcome 时停止上述长期 retry，必须由 Host 另行定义 durable evidence、终止条件、资源 policy、schema/contract 与 owner tests；R05 不发明 max retry、abandon deadline、timeout terminal marker，也不把 `_handle_time_boundary(...)` 误当现有 CANCELLED 收口路径。
- Issue 175：process isolation / process-backed containment；不由 R05 实现。
- Issue 175 与 future Host durable evidence policy 是两个 owner：前者处理 Fins Docling 的物理终止/containment，后者才有权定义 cancelled-wait durable stop evidence；不得把进程被终止或 observation timeout 自动投影成业务 terminal fact。
- callback transport 与 authenticated callback ingress：后续对应 WU/issue；R05 只保留 typed mode 与 fail-closed composition。
- unified authorization/permission schema、R06+ semantic ownership remediation：不进入本 slice。
- future explicit Host LOST durable evidence policy：若要让 observation timeout 推导 LOST，必须另行定义 evidence、owner、schema/contract 与 tests；R05 不预留 heuristic branch。

当前 blocking questions：**无**。

历史 `R05-PF-01` 至 `R05-PF-04` 与 `R05-PRR-F01` 均已关闭，其中 PF-03/PF-04 的 owner / allowlist 扩大裁决继续有效。当前下一动作是 Controller validation 本次同一 R05-S1 validation plan correction；Controller 接受后只进入 AgentMiMo / AgentDS 双路完整 plan-correction review。任何超出已裁决 `docs/host/design.md` 精确纠错，或超出 `durable/state.py` invalid primitive 与 §2.3 唯一 unused import 删除的新增 owner/allowlist 需求，仍必须停回 Controller。
