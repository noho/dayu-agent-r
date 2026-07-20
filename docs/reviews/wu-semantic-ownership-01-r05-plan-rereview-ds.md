# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Complete Re-Review — AgentDS 第二路

## 0. Review 身份与 Gate 位置

- **reviewer**: AgentDS（第二路 complete re-review）
- **immutable target**: `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
- **base/HEAD**: `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`
- **umbrella**: `WU-SEMANTIC-OWNERSHIP-01` continuation；本 review 只覆盖 R05 plan re-review gate
- **review scope**: 全文 adversarial re-review，不只看 PF-01 至 PF-04 局部 diff
- **已读输入（完整）**:
  - `AGENTS.md`（全部约束章节）
  - `docs/host/issues-implementation-control.md`（R05 段、当前状态表、umbrella manifest 链接）
  - `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（R05 manifest §12）
  - `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（Topic 5 final decision）
  - `docs/host/design.md`（wait observation/abandon 段 lines 2420-2449）
  - `docs/engine/design.md`（§4 §6 §11 §12 handshake/timeout/awaiting 相关段）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-review-mimo.md`（初审 MiMo PASS-WITH-RISKS）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-review-ds.md`（初审 DS PASS）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-review-controller-adjudication.md`（Controller 裁决 PF-01..04）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md`（AgentCodex plan-fix）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-controller-validation.md`（Controller fix validation）
- **直接代码证据（全量复核）**:
  - `dayu/host/wait_adapter.py`（全文件 1950+ 行）
  - `dayu/host/_wait_observation.py`（token/fence 段 lines 110-170, 320-379）
  - `dayu/host/waiting.py`（typed ResolveWaitLostOutcome 段 line 1016-1024）
  - `dayu/host/durable/state.py`（claim/release/abandon/abandon_timeout 段 lines 2465-2797）
  - `dayu/host/durable/schema.py`（poll_abandoned_at 段 lines 873, 921）
  - `dayu/engine/agent.py`（handshake timeout 段 lines 1960-2088, 2170-2194）
  - `utils/smoke_host_public_awaiting_entrypoint.py`（前 60 行）
- **验证命令（全量执行）**:
  - `rg` symbol scan for `mark_wait_record_poll_abandon_timeout` / `_MarkWaitRecordAbandonTimeoutOperation`
  - `rg` symbol scan for `ResolveWaitLostOutcome` in production
  - `rg` symbol scan for `tool_execution_timeout_seconds` in `agent.py`
  - `rg` symbol scan for `poll_abandoned_at IS NULL` in `state.py`
  - `git diff --name-only` for `design.md` and `schema.py` vs base
  - engine design.md grep for handshake timeout semantics
- **结论**: **PASS**（零 blocker、零 accepted finding、零 open question、两条 residual risk note）

---

## 1. R05-PF-01..04 逐项关闭复核

### 1.1 R05-PF-01 — cancelled abandon timeout 长期 capped retry residual

| 复核维度 | 计划位置 | 直接证据 | 结论 |
|---|---|---|---|
| CANCELLED 绕过 `_handle_time_boundary` | §2.1 表、§4 分支矩阵 row 13 | `wait_adapter.py:1021-1029`: `record.status is CANCELLED` → `_abandon_cancelled_wait(...)` → `continue`; `_handle_time_boundary` 在 line 1030 仅对非-CANCELLED 路径生效 | **CLOSED** |
| 长期 retry 事实登记 | §15 explicit residual | 描述 call order `claimed CANCELLED → poll_once() → _abandon_cancelled_wait → continue`，明确不进入 `_handle_time_boundary` | **CLOSED** |
| 有限资源边界 | §15 | 列出 claim CAS、`max_outstanding_adapter_calls` cap、finite single-call timeout、late-publication fencing、backoff cap | **CLOSED** |
| future owner | §15 | Host cancel/abandon durable evidence policy（独立于 Issue 175 的物理 containment） | **CLOSED** |
| 禁止扩域 | §15 + §1.3 | 明确不发明 max retry、abandon deadline、timeout terminal marker | **CLOSED** |
| 不误称 deadline 收口 | §2.1 直接证据表 + §4 row 13 | `_handle_time_boundary(...)` 只在非-CANCELLED poll path 被调用；不能作为 CANCELLED retry 的终止证据 | **CLOSED** |

**验证**：Controller 裁决明确要求 "不误称既有 wait deadline 会收口 CANCELLED"。现在计划在三个独立位置（§2.1、§4、§15）都明确记录 CANCELLED 先走 abandon path 并绕过 `_handle_time_boundary`。DS 初审 challenge 3.3 的 "deadline expiry 是独立 terminal 路径" 判断已被代码证据纠正——`_handle_time_boundary` 对 CANCELLED 确实不生效，因为 `poll_once()` 在 status=CANCELLED 时 `continue` 了。

**R05-PF-01 判定：真正关闭。**

### 1.2 R05-PF-02 — smoke timing 可执行性

| 复核维度 | 计划位置 | 直接证据 | 结论 |
|---|---|---|---|
| event/condition-driven phases | §5.2 第 8 点、§11 phase order | handshake accepted、operation start/finish、first observation entered、late result release、second observation entered 全部分别由 `asyncio.Event` / `threading.Event`、`Condition` 或 durable state polling 驱动 | **CLOSED** |
| monotonic deadline | §5.2 第 10 点、§11 | 只用 `time.monotonic()` 建立具名 overall deadline；所有 phase wait 从同一 deadline 计算 remaining budget | **CLOSED** |
| relative margin | §5.2 第 8 点 | `margin >= 5 * state-poll quantum`；三段严格不等式 | **CLOSED** |
| 禁止固定 sleep 推断 | §5.2 第 8 点、§11 | "状态 polling 只允许按具名 quantum 让出执行，不得用单次固定 sleep 的经过推断业务状态" | **CLOSED** |
| CI cap | §5.2 第 10 点 | overall deadline 不得超过具名 CI duration cap | **CLOSED** |
| phase failure evidence | §5.2 第 10 点、§11 | module-level phase helper 失败时输出 phase ledger、monotonic elapsed、runner dropped count、Run/Wait claim/status/next-observe/diagnostic/`poll_abandoned_at`/terminal outbox 快照 | **CLOSED** |
| test-effective policy 从 packaged snapshot 派生 | §5.2 第 4 点 | `dataclasses.replace`，packaged snapshot 与 test-effective timing 分开打印 | **CLOSED** |

**验证**：Controller 裁决要求 "handshake acceptance、operation start/finish、first observation entered、late result release、runner dropped count、second observation entered 均使用 event/condition 或状态 polling"。修订计划全部响应。

**可行性附加检查**：用 packaged 值 `adapter_call_timeout_seconds=30`、`backoff_initial_delay_seconds=30`，不等式链为 `handshake_budget + margin < 30 < operation_duration < 30 + 30 = 60`。operation_duration 窗口约为 `(30 + margin, 60 - margin)`。若 `margin >= 5 * 0.1s = 0.5s`（假设 quantum=0.1s），窗口为 `(30.5, 59.5)`——宽约 29 秒，完全可操作。总耗时约 `operation(~40s) + backoff_wait(~30s) + second_observe(~1s) ≈ 71s`，完全在合理 CI cap 内。

**R05-PF-02 判定：真正关闭。**

### 1.3 R05-PF-03 — Host design `close marker` 真源纠错

| 复核维度 | 计划位置 | 直接证据 | 结论 |
|---|---|---|---|
| allowlist 纳入 | §5.1、§6.2 | `docs/host/design.md` 加入 R05-S1 write allowlist | **CLOSED** |
| 精确改写 | §5.1 | "只把当前...精确改写为：cancelled wait 的 abandon observation timeout 只写 poll-local transient `wait_abandon_timeout` diagnostic、释放 claim 并按 Host policy backoff，durable status 保持 `CANCELLED` 且不写 terminal `poll_abandoned_at`；只有 provider 显式返回 applied / unsupported / noop lifecycle outcome，才沿既有 transition 写 terminal abandon marker，且不调用 wait resolve" | **CLOSED** |
| 不扩写新 policy/schema | §5.1 + §13 stop condition 11 | 明确禁止新增 retry 上限、deadline、policy/schema；超出即 stop | **CLOSED** |
| explicit lifecycle terminal 保留 | §5.1 | "只有 provider 显式返回 applied / unsupported / noop lifecycle outcome，才沿既有 transition 写 terminal abandon marker" | **CLOSED** |

**验证**：当前 `docs/host/design.md:2429-2430` 仍为旧文本 "cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker"。`git diff --name-only 5ba0d8b61f -- docs/host/design.md` 返回空——该文件自 base 以来无任何 diff。同时 lines 2425-2427 已描述正确的 poll timeout 行为（transient diagnostic + release + backoff + no LOST），这部分无需修改。

值得注意的是：design.md 当前 poll timeout 描述（lines 2425-2427）已与代码不一致——代码仍走 `WaitPollLost(ResolveWaitLostOutcome(...))`。这不是 plan 的 defect，而是 design-as-truth 先行于 code 的正常状态；R05-S1 的代码修改将使两者一致。修订计划明确只改 cancel abandon 那句，不改 poll 那句——范围精确。

**R05-PF-03 判定：真正关闭。**

### 1.4 R05-PF-04 — durable invalid timeout-only primitive 删除

| 复核维度 | 计划位置 | 直接证据 | 结论 |
|---|---|---|---|
| production allowlist | §5.1、§6.2 | `dayu/host/durable/state.py` 加入 R05-S1 production allowlist | **CLOSED** |
| 精确删除范围 | §5.1 | "删除 `mark_wait_record_poll_abandon_timeout(...)` 的完整定义；不得改名保留、标 deprecated、兼容 re-export 或留下只服务该 invalid semantic 的 helper/code" | **CLOSED** |
| explicit terminal 保留 | §5.1、§3.1 | "保留 `mark_wait_record_poll_abandoned(...)` 对 explicit applied/unsupported/noop lifecycle outcome 的 terminal `poll_abandoned_at` 写入" | **CLOSED** |
| schema 不变 | §5.1 + §10.1 | `durable/schema.py` 必须无 diff；`poll_abandoned_at` 继续承载 explicit lifecycle terminal marker | **CLOSED** |
| zero-symbol scan | §10.1 | `mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation` 在 `dayu tests` 中零定义、零调用；guard 返回零 | **CLOSED** |
| owner tests | §5.1、§7.1 | `tests/host/test_wait_record_state.py` 加入 test allowlist，新增 CANCELLED release/backoff 后同 row 到期可再次 claim 的 durable owner test | **CLOSED** |
| per-file coverage | §5.1、§8 | actual changed production files 各 >=80% | **CLOSED** |

**直接符号验证**：当前全仓 scan 确认：
```
dayu/host/wait_adapter.py:51:    mark_wait_record_poll_abandon_timeout,
dayu/host/wait_adapter.py:706:class _MarkWaitRecordAbandonTimeoutOperation:
dayu/host/wait_adapter.py:723:        return mark_wait_record_poll_abandon_timeout(
dayu/host/wait_adapter.py:1368:                _MarkWaitRecordAbandonTimeoutOperation(
dayu/host/durable/state.py:2728:def mark_wait_record_poll_abandon_timeout(
```
仅 5 处命中：1 import + 1 class def + 1 call-through + 1 call-site + 1 function def。tests 零命中。删除路径完全可追踪。

**schema 验证**：`durable/schema.py:873` 定义 `poll_abandoned_at TEXT NULL`，line 921 CHECK 约束 `poll_abandoned_at IS NULL OR status = 'cancelled'`。该字段同时服务于 `mark_wait_record_poll_abandoned`（显式 lifecycle terminal）和待删除的 `mark_wait_record_poll_abandon_timeout`（invalid timeout terminal）。删除后者后，字段仍被前者使用，schema 无需变更。`git diff --name-only 5ba0d8b61f -- dayu/host/durable/schema.py` 返回空——自 base 以来无 diff。

**R05-PF-04 判定：真正关闭。**

---

## 2. 全计划 Adversarial Re-Review（非局部 diff）

### 2.1 Storage Primitive 删除 Owner Root Fix 验证

**Challenge**: 删除 `mark_wait_record_poll_abandon_timeout` 是否真的是 owner-boundary root fix，还是只是删除一个下游 symptom？

**验证路径**:

1. **语义 owner 判定**：timeout 的 policy 解释 owner 是 `WaitPoller`（`wait_adapter.py`），不是 durable store。plan §3 的 owner 表明确：observation timeout 的 policy 解释 owner = `WaitPoller`，claim release/backoff 入口 = `WaitPoller._release_with_backoff`，timeout-only terminal abandon primitive = `durable/state.py` 的 `mark_wait_record_poll_abandon_timeout`。

2. **Caller-consumer 关系**：`mark_wait_record_poll_abandon_timeout` 的唯一 production consumer 是 `_MarkWaitRecordAbandonTimeoutOperation`（`wait_adapter.py:706-731`），而该 wrapper 的唯一 call-site 是 `_abandon_cancelled_wait` 的 timeout 分支（`wait_adapter.py:1363-1382`）。删除 consumer → primitive 无合法 caller → 必须在 owner boundary 删除 primitive。

3. **为什么不能保留为 dead code**：Controller 裁决明确三点：(a) 该 function 的唯一语义是把 generic timeout 投影成 `poll_abandoned_at` terminal marker，该语义已被否定；(b) 保留它会在 durable owner boundary 留下可再次误用的 invalid semantic operation；(c) 项目禁止兼容/dead shim。因此保留为 dead code 违反项目约束。

4. **Schema/compat 边界**：`poll_abandoned_at` 字段同时被 `mark_wait_record_poll_abandoned`（正确语义）和 `mark_wait_record_poll_abandon_timeout`（错误语义）写入。删除后者只删除错误写入路径；前者（explicit lifecycle terminal）继续工作。schema DDL 不变。无 migration 需要。

5. **无第二 consumer**：全仓 symbol scan 确认除 wait_adapter 外无任何 production module import 或调用该 function。tests 中也无合法 caller。

**结论**：删除是 owner-boundary root fix——删除的是 durable store 中唯一服务于已被否定语义的 primitive。无 schema/compat 扩域。✅

### 2.2 Design Writeback 精确性验证

**Challenge**: 计划中的 design writeback 是否只纠正已裁决句子，不引入新 policy/schema？

**验证**:

- **Writeback target**: `docs/host/design.md:2429-2430` 的 "cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker"
- **Planned replacement**: 精确描述 transient diagnostic + release claim + policy backoff + keep CANCELLED + no terminal `poll_abandoned_at`，同时保留 explicit lifecycle terminal outcome
- **Boundary**: §5.1 明确 "不新增 retry 上限、deadline、policy/schema"，§13 stop condition 11 明确 "若需要超出 §5.1 精确句子纠错的新产品 contract 裁决" 必须停止
- **不扩写**: plan 明确只改该句；不在 design.md 新增 retry 上限、deadline 或其它 policy 描述
- **既存正确文本保留**: design.md lines 2425-2427（poll timeout 行为）已正确描述 transient diagnostic + release + backoff + no LOST，R05 不修改该段

**结论**：writeback 精确且受限。✅

### 2.3 CANCELLED 长期 Retry Residual 准确性验证

**Challenge**: 计划是否准确描述了 CANCELLED 长期 retry 的行为边界，且不误称既有 deadline 收口？

**验证路径**:

1. **Call order 验证**（`wait_adapter.py:980-1053`）:
   ```
   poll_once():
     for claimed in claimed_records:
       record = claimed.record
       if record.status is CANCELLED:           # line 1021
         _abandon_cancelled_wait(record, ...)    # line 1022-1024
         continue                                 # line 1029 ← 关键：跳过 _handle_time_boundary
       _handle_time_boundary(record, ...)        # line 1030-1036 ← 仅对非-CANCELLED 执行
   ```
   确认：`_handle_time_boundary` 对 CANCELLED record **永不执行**。

2. **Retry 通路验证**:
   - R05 前：abandon timeout → `_MarkWaitRecordAbandonTimeoutOperation` → 写 `poll_abandoned_at` → claim query (line 2537) 要求 `poll_abandoned_at IS NULL` → **永久不可 claim**
   - R05 后：abandon timeout → `_release_with_backoff` → 清 claim、设 `next_observe_at`、递增 attempt、不写 `poll_abandoned_at` → claim query 可通过 → **backoff 到期后可 claim**

3. **资源边界验证**:
   - `max_outstanding_adapter_calls = 8`：最多 8 个并发 observation thread
   - `backoff_max_delay_seconds = 300`：最慢每 5 分钟一次重试
   - claim CAS：单 record 同时只有一个 poller 持有有效 claim
   - late-publication fencing：timeout 后迟到结果被 token fence 拒绝
   - finite single-call timeout：单次 observation 有上界

4. **计划描述准确性**:
   - §2.1 代码证据表：明确记录 `CANCELLED → _abandon_cancelled_wait → continue`，不进入 `_handle_time_boundary`
   - §4 row 13：明确 "`CANCELLED` 在 `poll_once()` 中先进入 abandon path，不能用 `_handle_time_boundary(...)` 解释或终止其长期 retry"
   - §15 explicit residual：完整描述长期 retry 事实、当前安全边界、future owner

**结论**：描述准确，不误称 deadline 收口。✅

### 2.4 新增 Durable Owner Tests / Exact Nodes 可实现性

**Challenge**: 计划中的新增测试节点是否可以直接用当前测试基础设施实现？

**验证**:

| Test Node | 位置 | 实现方式 | 可实现性 |
|---|---|---|---|
| `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve` | `test_wait_observation_runner.py` | 替换旧 `test_stuck_poll_times_out_to_lost_and_late_result_is_dropped`；使用现有 runner/adapter fixture | ✅ 可复用现有 fixture |
| `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal` | `test_wait_observation_runner.py` | 替换旧 `test_stuck_abandon_writes_timeout_marker_without_external_success`；使用现有 runner/adapter fixture | ✅ 可复用现有 fixture |
| `test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run` | `test_phase7_waiting_integration.py` | 新增 integration test；使用现有 Host assembly fixture | ✅ 可复用现有 integration fixture |
| `test_cancelled_poll_timeout_release_preserves_claimability_after_due` | `test_wait_record_state.py` | 直接 claim CANCELLED row → `release_wait_record_poll_claim` → 断言四个 claim fields 清空 + `poll_abandoned_at is None` → 到期后再次 claim | ✅ `release_wait_record_poll_claim` 当前已支持 CANCELLED (line 2654-2655)；直接调用即可 |
| `test_poll_abandon_success_marks_row_and_clears_claim` | `test_wait_record_state.py` | 保留现有测试；`mark_wait_record_poll_abandoned` 不修改 | ✅ 保留即可 |

**附加验证**：`release_wait_record_poll_claim` 的 WHERE 子句（`state.py:2643`）接受 `status IN (WAITING, CANCELLED)`——这意味着新增 durable owner test 可以直接在 CANCELLED row 上调用该 function 而无需修改 store。`test_cancelled_poll_timeout_release_preserves_claimability_after_due` 作为 preservation green node（计划明确 "不能把它误列为 test-first 红灯"）是正确的——该 function 的 contract 已支持 CANCELLED，只是当前没有 test 直接证明。

**结论**：全部可实现，无基础设施缺口。✅

### 2.5 1916 Green Coverage Command 与逐文件门禁可信性

**Challenge**: 覆盖命令的排除策略是否可信，且不掩盖 R05 propagation？

**验证**:

1. **排除项分析**：
   - 排除文件：`tests/host/test_toolruntime_executor.py`
   - 排除原因：process-backed ToolRuntime 路径，与 WaitPoller observation timeout 无关
   - 该文件当前有 15 个 `PicklingError` 失败（macOS multiprocessing 限制），已在 plan-fix artifact 完整登记六元组
   - 排除仅用于 coverage session，不改变功能矩阵（功能矩阵单独运行全部 passed）

2. **Coverage 数据可信性**：
   - Plan-fix probe 结果：`1916 passed, 1 skipped, 5 deselected` → `durable/state.py=83%`、`wait_adapter.py=85%`
   - 该 probe 在**当前未改代码**上运行，包含了待删除的 `mark_wait_record_poll_abandon_timeout`（~70 lines）
   - R05-S1 实现后，该 function 被删除，分母减小，覆盖率**只升不降**
   - 新增 owner tests 将额外覆盖 release/backoff diagnostic path

3. **逐文件门禁可靠性**：
   - Plan §8 要求对 actual changed production files 逐个执行 `coverage report --include='<exact file>' --fail-under=80`
   - 若 diff 出现 unexpected file，先 stop（§13 stop condition 10）
   - 禁止用聚合覆盖率代替逐文件门禁

4. **排除不掩盖 R05 propagation**：
   - `test_toolruntime_executor.py` 不 import `wait_adapter` 或 `durable/state` 的 timeout 相关符号
   - R05 修改的两个 timeout branch 与该文件的 process-backed 路径无调用关系
   - 功能矩阵（§7.1 exact test nodes）不排除任何相关测试

**结论**：Coverage command 可信，排除策略不掩盖 R05 propagation。✅

### 2.6 Smoke Event/Condition/Monotonic Margin 真实有界性

**Challenge**: Smoke 的时序约束是否在 packaged policy 值下真实可行且不 flake？

**验证**:

1. **Packaged 值下的时序窗口**（使用 `dataclasses.replace` 覆写前）：
   - `adapter_call_timeout_seconds = 30`
   - `backoff_initial_delay_seconds = 30`
   - 不等式：`handshake_budget(可覆写为更小值) + margin < adapter_timeout(30) < operation_duration < adapter_timeout(30) + backoff_initial(30) = 60`
   - operation_duration 窗口约 `(30 + margin, 60 - margin)`，margin ≥ 5 * quantum
   - 若 quantum=0.1s, margin=0.5s → 窗口约 29s，远大于操作抖动

2. **总体耗时上界**：
   - `operation(~30-55s) + backoff_wait(~30s) + second_observe(~1s) + overhead ≈ 61-86s`
   - CI duration cap 可设为 120s，留有 34-59s 余量

3. **Event-driven 时序验证**：
   - Plan 要求每个 phase transition 由 event/condition/state-poll 驱动
   - `asyncio.Event` / `threading.Event` 保证无竞态信号传递
   - monotonic deadline + remaining budget 保证不超时
   - state polling quantum 保证轮询开销可控

4. **Smoke 失败证据完整性**：
   - Plan 要求失败时输出 phase ledger（已完成/未完成 phase）
   - 最近 monotonic elapsed
   - runner dropped count
   - Run/Wait claim、status、next-observe、diagnostic、`poll_abandoned_at`、terminal outbox 快照
   - 不裸抛 timeout

**结论**：Timing 约束真实有界，在合理 CI cap 内可实现。✅

### 2.7 两 Slice 原子边界保持

**Challenge**: PF-03（design writeback）和 PF-04（durable primitive 删除）是否破坏了原始两 slice 原子边界？

**验证**:

- **原始两 slice**：S1 = Host production semantic transaction（adapter decision 修正）；S2 = Engine no-diff regression + public smoke evidence
- **PF-03 归属 S1**：`docs/host/design.md` 的 writeback 是 design truth correction，与 adapter decision 修正同属一个 semantic transaction——"abandon timeout 不应写 terminal marker"
- **PF-04 归属 S1**：`durable/state.py` 的 primitive 删除是 storage owner boundary 修正，与 adapter 不再调用该 primitive 同属一个语义闭环——consumer 删除 + primitive 删除是一体的
- **不新增 slice**：Controller 裁决明确 "PF-03/PF-04 都属于 S1 同一个 semantic transaction，不增加 slice"

**结论**：两 slice 原子边界保持，PF-03/PF-04 自然归入 S1。✅

### 2.8 Engine agent.py No-Diff 验证

**Challenge**: `agent.py` no-diff 判定是否仍成立？

**验证**:

1. **Timeout read locations**（仅两处）：
   - `agent.py:1974`: 构造 `BatchToolExecutionContext.timeout_seconds` 时读取
   - `agent.py:2184`: `_execute_batch` 内部 `await_or_cancel_or_timeout` 使用

2. **Awaiting 后无 timeout 复用**：
   - `agent.py:1983`: `batch_outcome = await self._execute_batch(batch_request)` —— handshake 在此完成
   - `agent.py:2017-2019`: `ToolAwaitingOutcome` → 加入 `awaiting_records` —— 无后续 timeout 读取
   - `agent.py:2029+`: 对 accepted/completed/failed outcome 的处理 —— 无 timeout 相关逻辑

3. **设计真源确认**：
   - `docs/engine/design.md:114`: "`tool_execution_timeout_seconds` 是 Engine 等待 `ToolExecutor.execute` 返回 outcome 的握手超时真源"
   - `docs/engine/design.md:120`: "`BatchToolExecutionContext.timeout_seconds` 不是独立真源...供工具执行环境协作使用"
   - `docs/engine/design.md:134-135`: "对包含 awaiting 的 batch...产出 `tool_awaiting` 和 `run_suspended`，结束本次 run"

4. **Plan regression test**：
   - `test_accepted_awaiting_external_operation_outlives_handshake_timeout` 预期在 base production 上直接通过
   - 若失败则 stop 回 Controller（§13 stop condition 4）

**结论**：No-diff 判定有直接代码证据支撑，regression test 提供可执行验证。✅

### 2.9 R04 12 Fields/Modes 保持

**验证**：
- Plan §1.2 完整列出 12 字段及 packaged 值
- §1.3 非目标明确 "不改变 R04 config ownership"
- §10.5 R04 ownership scan 命令验证 provider modes 与 12 fields 仍只从 R04 owner 路径投影
- §7.3 R04 ownership preservation 回归命令覆盖 config_loader、fins_ingestion_tools、service/test_host_assembly

**结论**：R04 contract 完全保持。✅

### 2.10 Security/Deferred Boundaries 保持

**验证**：
- §1.3 非目标：不实施 Issue 175、callback transport、unified authorization、R06+
- §10.5 security/deferred scope scan 命令验证无 R05 新语义命中
- §13 stop condition 9：capacity、CAS、claim ownership、cancellation、close-drain、security/fencing 断言不得删除、放宽或绕过

**结论**：Security/deferred boundaries 完整保持。✅

---

## 3. 完整 Coverage Matrix

| 验证维度 | Plan 位置 | 复核证据 | 结论 |
|---|---|---|---|
| PF-01 cancelled retry residual | §2.1, §4, §15 | `wait_adapter.py:1021-1029` call order 确认 | **PASS** |
| PF-02 smoke timing | §5.2, §11 | event/condition/monotonic/margin/CI cap 全部覆盖 | **PASS** |
| PF-03 design writeback | §5.1 | 精确改写一句话，不扩域 | **PASS** |
| PF-04 storage primitive 删除 | §5.1, §10.1 | owner-root fix, zero-symbol scan, schema no-diff | **PASS** |
| Poll timeout → release/backoff (owner change) | §5.1, §4 | `wait_adapter.py:1102-1128` → 改用 `_release_with_backoff` | **PASS** |
| Abandon timeout → release/backoff (owner change) | §5.1, §4 | `wait_adapter.py:1363-1382` → 改用 `_release_with_backoff` | **PASS** |
| Authoritative typed lost 保留 | §4 row 3 | `wait_adapter.py:1107-1108` 只删除 timeout→LOST，不删除 typed LOST | **PASS** |
| Explicit lifecycle terminal 保留 | §4 rows 6-8 | `mark_wait_record_poll_abandoned` 不变 | **PASS** |
| Adapter exception/capacity 保留 | §4 rows 5, 10-11 | 既有 release/backoff 路径不变 | **PASS** |
| Close-drain 保留 | §4 row 12 | shared deadline + CLOSING 不变 | **PASS** |
| Wait deadline (FAILED) 保留 | §4 row 13 | `_handle_time_boundary` 不变（仅对非 CANCELLED 生效） | **PASS** |
| Runner token/fence no-diff | §5.1 | `_wait_observation.py:336-361` `_publish` 不变 | **PASS** |
| waiting.py typed terminal no-diff | §5.1 | `waiting.py:1016-1024` 只接受显式 `ResolveWaitLostOutcome` | **PASS** |
| Engine agent.py no-diff | §5.2 | `agent.py:1974,2184` 只在 handshake 内读取 timeout | **PASS** |
| R04 12-field config 不变 | §1.2 | 12 字段完整列出，packaged 值不变 | **PASS** |
| R04 typed modes 不变 | §1.2 | poll/callback/manual 不变 | **PASS** |
| Test-first red→green | §7.1 | 两条 timeout owner tests 在 base 上预期精确失败 | **PASS** |
| Durable preservation green nodes | §7.1 | `test_wait_record_state.py` 两个节点在 base 和实现后均绿 | **PASS** |
| Coverage 门禁 | §8 | actual changed files 各 >=80%，逐文件执行 | **PASS** |
| Pyright | §9.1 | 0 errors | **PASS** |
| Ruff changed-file | §9.2 | 全绿 | **PASS** |
| Ruff full registry | §9.2 | 167→166，六元组匹配 | **PASS** |
| Diff check | §9.3 | allowlist 内 | **PASS** |
| Source scan | §10.1-10.5 | 五组 scan 命令 + 人工核对 | **PASS** |
| Security scan | §10.5 | 零命中 | **PASS** |
| Smoke command | §11 | exact command + 8 条证据断言 | **PASS** |
| Stop conditions | §13 | 11 条 stop condition 覆盖全部扩域路径 | **PASS** |
| README decision | §5.2 | Host/tests README 命中；Engine README no diff 不改 | **PASS** |
| Two-slice boundary | §5 | S1 = production transaction, S2 = evidence | **PASS** |
| Closed allowlist | §6 | 精确列出 production/tests/smoke/docs/README 可写路径 | **PASS** |

---

## 4. 对初审 Findings 的最终确认

| 初审 Finding | 初审状态 | Re-review 确认 |
|---|---|---|
| MiMo 001（中）cancelled abandon timeout 无限重试资源影响 | → PF-01 accepted narrowed | PF-01 closed；residual 在 §15 完整登记 |
| MiMo 002（低）smoke timing 敏感性 | → PF-02 accepted narrowed | PF-02 closed；event/condition/monotonic/margin 完整 |
| DS RR-1（低）design.md "close marker" 歧义 | → PF-03 accepted | PF-03 closed；精确 writeback |
| DS RR-2（低）mark_wait_record_poll_abandon_timeout dead code | → PF-04 accepted | PF-04 closed；owner-boundary deletion |
| DS RR-3（低）smoke 执行时间 | → PF-02 accepted narrowed | 合并入 PF-02 |
| DS RR-4（无）backoff attempt 连续性 | → CLOSED_NO_ACTION | 确认无风险 |
| DS RR-5（低）smoke 覆盖缺口 | → CLOSED_BY_PLAN_SCOPE | S2 即目标场景 |

**全部初审 finding 已关闭或确认无风险。零新增 finding。**

---

## 5. Controller Validation 一致性检查

对照 `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-controller-validation.md` 的 5 条特别复核要求：

| Controller 要求 | 本 re-review 验证 | 结论 |
|---|---|---|
| storage primitive 删除是否 owner-boundary root fix，coverage/scans 足够 | §2.1 全量验证：single consumer → no legal consumer after deletion → must delete at owner boundary；1916 green + per-file ≥80% + zero-symbol scan | **一致** |
| design writeback 是否只纠正已裁决句子 | §2.2：精确一句话改写，不扩 policy/schema | **一致** |
| smoke phase/margin 是否可形成有界非 flake oracle | §2.6：packaged 值下 operation 窗口 ~29s，总耗时 ~61-86s，event/condition-driven | **一致** |
| cancelled abandon 长期 retry residual 是否准确，不误称 deadline 收口 | §2.3：call order 确认 CANCELLED 绕过 `_handle_time_boundary`，plan 三处明确记录 | **一致** |
| 两 slice、R04 config、Engine no-diff、deferred boundaries 保持 | §2.7-2.10：全部独立验证通过 | **一致** |

**无矛盾。Controller validation 的所有关键判断均被独立代码证据确认。**

---

## 6. Residual Risks

| # | Risk | 严重程度 | Owner | 追踪 |
|---|---|---|---|---|
| RR-1 | 修订计划 §2.1 代码证据表中 design.md "当前事实" 行未反映 lines 2425-2427 已部分正确（poll timeout description 已是 transient diagnostic + release/backoff + no LOST）的事实——该表述在 §5.1 的 writeback 范围精确性上没有歧义，但可能让只看 §2.1 表的 reader 误以为 design.md 全文仍描述旧语义 | 低（文档表述，非逻辑错误） | 无需修复 | R05 implementation 时确认 writeback 只改 line 2429-2430 |
| RR-2 | Smoke `dataclasses.replace` 从 packaged snapshot 派生 test-effective policy 时，若 future 新增 required 字段，`replace` 不会失败（dataclass field exists）但如果新增字段影响时序逻辑，smoke 的 timing 假设可能被 silently 打破 | 低（future concern；当前 12 fields 不变） | future smoke maintainer | 无需追踪；smoke 的具名 constants 和 explicit inequality 自身即检测机制 |

---

## 7. Open Questions

**无 blocking open question。** 以下为已自行验证的设计级问题：

1. **Q**: design.md lines 2425-2427 已描述正确 poll timeout 行为，但代码仍走 `WaitPollLost(ResolveWaitLostOutcome(...))`。这算不算 plan 的 scope gap？
   **A**: 不算。plan §5.1 的 production 变更明确覆盖了 poll `WaitObservationTimedOut` 分支（line 1102-1128），从 `WaitPollLost(ResolveWaitLostOutcome(...))` 改为 `_release_with_backoff`。设计文本先行于代码是正常的——R05-S1 的代码修改将使两者一致。Plan 不需要修改 lines 2425-2427 因为它们已经正确。

2. **Q**: 若 `_release_with_backoff` 对 CANCELLED abandon timeout 的 CAS 失败（另一个 poller 先释放了同一 claim），会发生什么？
   **A**: `_release_with_backoff` 返回 `claim_conflicts += 1`（line 1541-1543）。这是与 WAITING adapter_error 路径完全相同的既有行为。无新增 race condition。

3. **Q**: 在 S1 与 S2 之间，如果只完成 S1 而 S2 未完成，系统是否处于一致状态？
   **A**: 是。S1 的 production change（adapter decision + storage primitive deletion）是自包含的 semantic transaction。S2 的 Engine regression 在 base 上预期直接通过（当前 production 已正确），public smoke 是新增 acceptance evidence。S1 完成后的系统行为正确且可独立验证。

---

## 8. Final Plan Review Conclusion

**PASS**

该修订计划全文经过 adversarial re-review，所有维度均通过：

- **R05-PF-01..04**：全部真正关闭，每个都有独立代码证据验证
- **Storage primitive 删除**：owner-boundary root fix；单一 consumer 删除后 primitive 无合法 caller；schema/compat 无扩域
- **Design writeback**：精确一句话纠错，不引入新 policy/schema
- **CANCELLED 长期 retry**：准确描述 call order（绕过 `_handle_time_boundary`）、资源边界、future owner；不误称 deadline 收口
- **Exact test nodes**：全部可用现有 fixture 直接实现；preservation green node 逻辑正确
- **Coverage 门禁**：1916 green command 可信；排除 `test_toolruntime_executor.py` 有充分理由且不掩盖 R05 propagation
- **Smoke timing**：packaged 值下 window ~29s、总耗时 ~61-86s，event/condition/monotonic/margin 真实有界
- **两 slice**：原子边界保持；PF-03/PF-04 自然归入 S1
- **Engine agent.py no-diff**：直接代码证据 + 设计真源 + regression test 三重验证
- **R04 12 fields/modes**：显式保留，回归命令覆盖
- **Security/deferred**：全部边界 hold；stop conditions 覆盖所有扩域路径

**零 accepted finding、零 blocking question、零 owner/allowlist 修改建议。**

计划已达到 code-generation-ready 标准。下一 gate：AgentMiMo 完成第二路 complete re-review，随后 Controller 裁决。

---

## Appendix A: 全量验证命令记录

以下命令均已在本 review 中执行并记录结果：

```bash
# Symbol scan: invalid timeout primitive
rg -n 'mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation' dayu tests
# 结果: 5 处命中（1 import + 1 class def + 1 call-through + 1 call-site + 1 function def），tests 零命中

# Symbol scan: ResolveWaitLostOutcome in production
rg -n 'ResolveWaitLostOutcome' dayu/host tests/host
# 结果: 广泛存在于 api.py, waiting.py, wait_adapter.py, wait_callback.py, durable/, tests/；保留正确

# Engine timeout usage
rg -n 'tool_execution_timeout_seconds' dayu/engine/agent.py
# 结果: 仅两处（line 1974 context 构造, line 2184 await_or_cancel_or_timeout），均在 handshake 内

# poll_abandoned_at IS NULL conditions
rg -n 'poll_abandoned_at IS NULL' dayu/host/durable/state.py
# 结果: 5 处（line 2479 read_next_due, line 2537 claim SELECT, line 2567 claim UPDATE,
#       line 2712 mark_abandoned WHERE, line 2782 mark_abandon_timeout WHERE）

# Schema diff vs base
git diff --name-only 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu/host/durable/schema.py
# 结果: 空（无 diff）

# Design diff vs base
git diff --name-only 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- docs/host/design.md
# 结果: 空（无 diff）

# Error code constants
rg -n '_POLL_ERROR_CODE' dayu/host/wait_adapter.py | head -10
# 结果: lines 69-77 定义了全部 九个常量，包括 OBSERVATION_TIMEOUT 和 ABANDON_TIMEOUT

# WaitPollLastOutcome enum
rg -n 'class WaitPollLastOutcome|ADAPTER_ERROR|ABANDON_ERROR' dayu/host/durable/state.py
# 结果: ADAPTER_ERROR 和 ABANDON_ERROR 均为既有 enum 值
```
