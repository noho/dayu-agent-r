# Phase 11 Slice 4 Code Review — AgentDS — 2026-05-19

## Review Scope

- 工作区：`/Users/leo/workspace/dayu-agent-r`，分支 `feat/host-phase-11-recovery`
- 审查对象：未提交 Slice 4 diff（8 files changed, 518 insertions, 58 deletions）
- 设计真源：`docs/host/design.md`
- 实施总控：`docs/host/implementation-control.md`
- Phase 11 plan：`docs/host/phase11-host-lifecycle-recovery-plan.md`
- Implementation artifact：`docs/reviews/phase11-slice4-implementation-codex-20260519.md`

## 第一性原理：动机判断

Slice 4 动机成立。直接证据：

1. **设计真源要求**：`docs/host/design.md` §2 明确 Recovery 是唯一负责 Host startup scan、旧 Attempt LOST 收口和可恢复 Run 新 Attempt 创建的模块；§27.1 要求已 durable append `USER_INPUT_ACCEPTED` 的 prompt 重启后应基于 canonical facts 重建并产出 answer。Phase 11 plan §Implementation Slices Slice 4 明确要求 RECOVERING cancel 在 recovery dispatch 提交前只追加 `CANCEL_REQUESTED + RUN_CANCELLED`，不关闭旧 Attempt。

2. **当前代码缺口**：`dayu/host/admission.py:4199`（pre-diff）`_session_cancel_target_for_run` 对 RECOVERING 返回 `None`，导致 `cancel_session_runs` 在有 RECOVERING Run 的 Session 上直接 fail-closed 抛出 `UNSUPPORTED_OPERATION`。`dayu/host/command.py:1232-1236`（pre-diff）`_IsDeferredCancelStateOperation` 将 RECOVERING 归类为 deferred cancel，导致 `cancel_run` 对 RECOVERING 也抛出 `UNSUPPORTED_OPERATION`。这两处代码注释均明确写着"RECOVERING 取消由 Phase 11 负责"。

3. **非过度设计**：不引入新 API、不新增 schema 字段、不修改 Engine、不改变 graceful shutdown 行为、不改变 watcher close 语义。改动严格限制在 plan 允许的文件集合内。

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_public_cancel_session_runs.py \
  tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py \
  tests/host/test_watch_session_events.py -q
# → 19 passed in 0.65s

source .venv/bin/activate && python -m pyright dayu/host tests/host
# → 0 errors, 0 warnings, 0 informations

git diff --check
# → clean, no output
```

## 逐文件审查

### 1. `dayu/host/durable/run_transition.py` (+219/-0 净增)

**新增 `CancelRecoveringRunInput` (line 802-832)**：dataclass frozen slots，所有字段类型完备，docstring 完整。与 `CancelQueuedRunInput`、`CancelWaitingRunInput` 结构一致。`run_cancelled_event_id` 字段语义正确——RECOVERING cancel 只追加 `RUN_CANCELLED`，不需要 `attempt_cancelled_event_id`。

**新增 `cancel_recovering_run_in_transaction` (line 2356-2419)**：
- 前置校验 → 读 Run → status check → append `CANCEL_REQUESTED` → append `RUN_CANCELLED(terminal_attempt_id=None)` → CAS Run update → 读当前 Attempt/dispatch（不修改）
- EventLog append 与 Run state update 同事务 ✓
- `RUN_CANCELLED` 的 `terminal_attempt_id=None` 且 `attempt_id=None`，不引用任何 Attempt ✓
- 不调用 `_read_dispatch_for_attempt`（该函数要求 Attempt 必须存在），改用防御性的 `_read_current_attempt_if_present` / `_read_current_dispatch_record_if_present` ✓
- 错误路径完整：NOT_FOUND / INVALID_STATE / CAS_LOST ✓

**新增 `_cancel_recovering_run_row` (line 2754-2809)**：
- CAS WHERE 条件：`status = RECOVERING AND terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`
- 不检查 `current_attempt_id`——与 `cancel_waiting_run_row` 不同但语义正确。RECOVERING 的 `current_attempt_id` 指向已收口的旧 Attempt；若 recovery dispatch 已完成，status 会从 RECOVERING → RUNNING，CAS 自然 miss。不需要通过 `current_attempt_id` 做额外 guard。
- `updated_at` 与 `terminal_at` 设为同一值，与其它 cancel helper（`cancel_waiting_run_row`、`terminal_run_row`）一致 ✓

**新增 `_read_current_attempt_if_present` / `_read_current_dispatch_record_if_present` (line 5063-5117)**：
- 纯读 helper，不产生副作用
- 防御性实现：`current_attempt_id is None` 时返回 `None`，不抛异常
- docstring 完整 ✓

**`_validate_cancel_recovering_input` (line 5809-5828)**：复用 `_validate_common_cancel_input`，校验覆盖所有必填字段 ✓

**类型联合扩展**：
- `_cancel_requested_event_request` 的 `request` 参数加入 `CancelRecoveringRunInput`（line 3778-3781）✓
- `_run_cancelled_event_request` 的 `request` 参数加入 `CancelRecoveringRunInput`（line 3911-3915）✓
- `CancelRecoveringRunInput` 具备 `call_context_digest`、`run_cancelled_event_id` 等被引用字段 ✓

### 2. `dayu/host/admission.py` (+130/-0 净增)

**`_CancelRunOperation._cancel_run` 新增 RECOVERING 分支 (line 1547-1552)**：
- 放在 `WAITING` 分支与 `_is_terminal_run_status` 检查之间
- 优先级正确：terminal > recovering（terminal 在前，不会误入 recovering 分支） ✓
- 错误路径：非 terminal/recovering 的 unsupported status 仍触发 `INVALID_STATE` ✓

**新增 `_CancelRunOperation._cancel_recovering` (line 1695-1752)**：
- 构造 `CancelRecoveringRunInput` → 调用 `cancel_recovering_run_in_transaction` → 记录 idempotency → 返回 `CancelRunResult`
- `active_cancel_target=None`：不创建 WorkerProxy cancel 传播目标 ✓
- `released_active_slot=True`：RECOVERING 是非终态，持有 session active slot；过渡到 CANCELLED（终态）后释放 slot 并触发 after-commit queue promotion。语义正确 ✓
- Idempotency scope: `(run_id=_OPERATION_CANCEL_RUN, scope_id=run_id, idempotency_key=client_request_id)`——与其它 cancel_run 分支一致 ✓

**`_SupportedSessionCancelTarget` 新增 `recovering: bool` (line 1938)**：
- 所有已有构造点均已显式设 `recovering=False` ✓
- `_session_cancel_target_for_run` RECOVERING 分支设 `recovering=True`（line 4305）✓
- `_active_cancel_target_for_session_target` 只对 `active_worker=True` 生成 ActiveCancelTarget；recovering 目标 `active_worker=False`，不传播 worker cancel ✓

**`_CancelSessionRunsOperation._cancel_target` 新增 recovering 分支 (line 2081-2082)**：
- 放在 `waiting` 与 `active_worker` 之间，优先级合理 ✓
- `_cancel_recovering_target` 复用 `cancel_recovering_run_in_transaction` ✓

**`_session_cancel_target_for_run` RECOVERING 分支 (line 4288-4306)**：
- 旧代码：`if run.status == RunStatus.RECOVERING: return None` → 导致 fail-closed
- 新代码：读取 current_attempt（可选）和 dispatch_record（可选）→ 返回 `recovering=True` 的目标
- `current_attempt_id is None` 时 Attempt/dispatch 均设为 `None`——防御性处理。实际 RECOVERING 状态总有 `current_attempt_id`（由 recovery closeout 设置），但代码不假设这一点 ✓

**受影响的其他构造点**（`_SupportedSessionCancelTarget` 构造调用）：
- ACCEPTED/QUEUED（line 4252-4260）→ `recovering=False` ✓
- WAITING（line 4280-4287）→ `recovering=False` ✓
- pre-dispatch STARTING（line 4330-4337）→ `recovering=False` ✓
- active worker RUNNING/CANCELLING（line 4342-4349）→ `recovering=False` ✓
- 所有构造点显式设值，不依赖默认值 ✓

### 3. `dayu/host/command.py` (+9/-0 净增)

**`cancel_run` docstring (line 554-555)**：
- 旧："当前覆盖 queued、pre-dispatch ``STARTING``、pre-accept dispatching、active worker 与 ``WAITING``；``RECOVERING`` 取消由 Phase 11 负责。"
- 新："当前覆盖 queued、pre-dispatch ``STARTING``、pre-accept dispatching、active worker、``WAITING`` 与 ``RECOVERING``。"
- 移除"由 Phase 11 负责"的遗留注释 ✓

**`cancel_session_runs` docstring (line 609-610)**：
- 同上去掉"RECOVERING 取消由 Phase 11 负责" ✓

**`_IsDeferredCancelStateOperation` (line 1232-1233)**：
- 旧：`if run.status in (RunStatus.WAITING, RunStatus.RECOVERING): return True`
- 新：`if run.status == RunStatus.WAITING: return True`
- RECOVERING 从 deferred cancel 分类中移除 ✓
- 影响：`cancel_run` 的 INVALID_STATE → deferred 检查不再将 RECOVERING 误判为 deferred。现在 RECOVERING 在 admission 层直接被 `_cancel_recovering` 处理，不会到达 deferred 检查路径 ✓

### 4. `tests/host/test_public_cancel_session_runs.py` (+148/-58)

**新增 `test_cancel_run_recovering_appends_no_attempt_terminal` (line 458-492)**：
- 构造路径：start_run(ACCEPTED) → governed_start(STARTING Attempt) → DB 直接 mark RECOVERING
- cancel_run → 断言：Run CANCELLED，Attempt 仍为 STARTING（未修改），EventLog 最后两个为 CANCEL_REQUESTED + RUN_CANCELLED，无 ATTEMPT_CANCELLED
- 覆盖：RECOVERING cancel 不追加 Attempt terminal fact、不修改旧 Attempt ✓

**新增 `test_cancel_session_runs_includes_recovering_without_fail_closed` (line 495-517)**：
- 构造两个 Run，一个 mark RECOVERING，一个保持 QUEUED
- cancel_session_runs → 断言两者均 CANCELLED，active_run_id=None，queued_run_ids=()
- 覆盖：RECOVERING 不阻断同批 queued Run 取消 ✓

**旧测试替换**：`test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 被替换为上述两个新测试。旧测试验证"RECOVERING 导致 unsupported"，现在语义不再成立。替换判断正确 ✓

**新增辅助函数**：
- `_cancel_run_request`：构造单 Run cancel 请求，与 `_cancel_request`（session-scope）分离 ✓
- `_event_types_for_run`：按 event_sequence 读取 EventLog type 列表 ✓
- `_attempt_status`：读 Attempt 当前状态 ✓
- 导入清理：移除不再使用的 `pytest`、`HostApiError`、`HostApiErrorCode`、`FollowupBehavior`、`SubmitFollowupRequest`、`submit_followup`；新增 `AttemptStatus`、`CancelRunRequest`、`cancel_run`、`TABLE_EVENT_LOG` ✓

### 5. `tests/host/test_public_cancel_smoke.py` (+52/-0)

**新增 `test_recovering_cancel_does_not_propagate_worker_cancel` (line 160-193)**：
- 使用 `open_host` 异步 public path
- 构造 RUNNING Run + active worker handle → DB 直接 mark RECOVERING → cancel_run
- 断言：Run CANCELLED，`factory.handles[0].cancel_reasons == []`（worker 未收到 cancel）
- 覆盖：public async path RECOVERING cancel 不传播到 WorkerProxy ✓

**新增 `_mark_run_recovering` helper (line 246-258)**：与 `test_public_cancel_session_runs.py` 的 `_mark_run_status` 功能相同，但直接用 `RunStatus.RECOVERING.value` 做 UPDATE。测试级重复可接受 ✓

### 6. `dayu/host/README.md` (+6/-3)

- `cancel_run` / `cancel_session_runs` 描述新增 recovering 覆盖 ✓
- RECOVERING 状态说明新增"新 recovery dispatch 提交前可被 cancel 直接收口为 CANCELLED，不追加旧 Attempt terminal fact" ✓

### 7. `tests/README.md` (+4/-2)

- public cancel coverage 描述从"WAITING"扩展到"WAITING / RECOVERING" ✓
- public-path smoke 描述从"active / session-scoped cancel"扩展到"active / RECOVERING / session-scoped cancel" ✓

### 8. `docs/host/implementation-control.md` (+2/-2)

- 当前 gate 从 "Phase 11 design discussion / plan gate" 更新为 "Phase 11 Slice 4 code review"
- 下一 gate 设为 "Phase 11 Slice 4 code review adjudication / fix decision"
- 新增 Slice 3 accepted commit 与 Slice 4 implementation 两条事实记录 ✓

## 变更未触及的模块（确认保护）

- `dayu/host/dispatch.py`：**未修改**。graceful shutdown close 顺序（closed gate → scheduler close → flush projection → close command handle）保持 P10.5 行为 ✓
- `dayu/host/open_host.py`：**未修改**。public opener 不新增 API，不新增 option ✓
- `dayu/engine/`：**未修改** ✓
- `dayu/runtime/`：**未修改** ✓
- P10.5 public API surface：`open_host(options)`、public handle methods、`watch_session_events` contract 均未改变 ✓

## 状态机与 EventLog 校验

### EventLog append 顺序

RECOVERING cancel 在同一 write transaction 内按序 append：
1. `CANCEL_REQUESTED`（event_class=canonical_fact, attempt_id=None）
2. `RUN_CANCELLED`（event_class=canonical_fact, attempt_id=None, terminal_attempt_id=None）

与 plan §Implementation Decisions #9 一致：graceful shutdown 不写 CANCEL_REQUESTED；但用户主动 cancel 写 CANCEL_REQUESTED + RUN_CANCELLED ✓

### 状态迁移正确性

```
RECOVERING ──[cancel_recovering_run_in_transaction]──> CANCELLED (Run)
                                                        (Attempt 不变)
```

- 不经过 CANCELLING 中间态：RECOVERING 没有 active worker，无需 best-effort 传播
- 不追加 ATTEMPT_CANCELLED：旧 Attempt 已由 recovery closeout 收口（LOST），不重复关闭
- CAS guard：WHERE status=RECOVERING + terminal 字段全 NULL，防竞争 ✓

### 与相邻状态的交互

- RECOVERING → CANCELLED（本 slice）：Run terminal，释放 session slot，触发 queue promotion ✓
- RECOVERING → RUNNING（Slice 3 recovery dispatch）：CAS 检查 `status=RECOVERING`，dispatch 成功后 status 变为 RUNNING。若 cancel 与 dispatch 竞争：先到者 CAS 成功，后到者 CAS_LOST 回滚 ✓
- RECOVERING → RUN_LOST（Slice 3 unrecoverable）：同样通过 CAS 互斥 ✓

## 幂等性验证

### cancel_run RECOVERING 幂等

- Scope: `(operation=CANCEL_RUN, scope_id=run_id, idempotency_key=client_request_id)`
- 首次 cancel：执行 transition → 记录 `IdempotencyResultRef(result_kind=RUN, result_ref=run_id)` → 返回 CancelRunResult
- 重放：idempotency store 命中 → 返回缓存 Run snapshot
- scope 未漂移：`run_id` 用于 scope_id，与其它 cancel_run 路径一致 ✓

### cancel_session_runs RECOVERING 幂等

- Scope: `(operation=CANCEL_SESSION_RUNS, scope_id=session_id, idempotency_key=client_request_id)`
- 首次 cancel：遍历所有 target（含 RECOVERING）→ cancel 每个 → 记录 idempotency → 返回 Session snapshot
- 重放：返回当前 Session snapshot（可能包含新创建的 Run）→ 不取消新 Run
- `test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run` 继续通过 ✓

## Findings

### BLOCKING: 0

无阻断性问题。

### HIGH: 0

无高优先级问题。

### MEDIUM: 1

**M1. `_read_supported_targets_or_raise` 错误信息过期 (admission.py:2056-2062)**

```python
"cancel_session_runs supports only queued, pre-dispatch "
"STARTING, active worker, and WAITING Runs in the "
"current Host cancel scope"
```

未包含 RECOVERING。虽然该错误路径只在 `_session_cancel_target_for_run` 返回 `None` 时触发（RECOVERING 不会触发），但错误信息不够准确。建议改为：

```
"cancel_session_runs supports queued, pre-dispatch STARTING, "
"active worker, WAITING, and RECOVERING Runs"
```

或改为自适应枚举当前实际支持的状态集。

**严重性**：MEDIUM——不影响功能正确性但属于 stale 文档字符串，违反项目"文档以代码为准"的约束；若后续新增 unsupported 状态触发此错误路径，信息会误导排查方向。

### LOW: 3

**L1. `_cancel_recovering` 中 `released_active_slot=True` 的隐含语义 (admission.py:1751)**

`released_active_slot=True` 触发 after-commit `_promote_after_release`。当前语义：RECOVERING 是非终态，持有 session active slot；进入 CANCELLED 终态后释放 slot 并尝试 promotion。行为正确，但 `released_active_slot` 字段名容易误解为"释放了 active worker 的 slot"。建议在 `_cancel_recovering` docstring 或行内注释说明释放的是 session slot（非 worker slot），且 promotion 是预期行为。

**严重性**：LOW——行为正确，只是语义可读性可加强。

**L2. RECOVERING cancel smoke test 构造的 intermediate 状态不完全等价于生产路径 (test_public_cancel_smoke.py:160-193)**

`test_recovering_cancel_does_not_propagate_worker_cancel` 通过 direct DB UPDATE 将 RUNNING Run 标记为 RECOVERING，但旧 Attempt 保持 RUNNING（未 LOST），active worker proxy 仍存在。在真实 recovery 路径中，RECOVERING 状态的前提是旧 Attempt 已 LOST，worker proxy 已被清理。测试仍正确验证了"cancel_run 不传播到 worker"，因为运行路径在 admission 层按 RunStatus 分发，不进 `_cancel_active_attempt`。

**严重性**：LOW——测试契约 focused，不会导致虚假通过。Slice 5 multi-process 测试应覆盖完整 recovery → RECOVERING → cancel 路径。

**L3. 缺少 `cancel_run` RECOVERING 专用幂等性测试**

现有测试覆盖 `cancel_session_runs` 幂等重放（不取消新 Run），但不覆盖 `cancel_run` 对 RECOVERING 的幂等重放。当前实现通过通用 idempotency store 机制保证幂等，机制上无漏洞，但无 RECOVERING-specific 断言验证。

**严重性**：LOW——通用幂等机制已被其它 cancel_run 路径充分测试（`test_cancel_session_runs_active_replay_does_not_append_facts` 等），RECOVERING 不引入新的幂等路径或 scope 变化。

## 架构与分层合规

| 检查项 | 状态 |
|--------|------|
| Host 不依赖 Engine | ✓ |
| Engine 不修改 | ✓ |
| 不新增 public API | ✓ |
| 不新增 schema 字段 | ✓ |
| 不改变 P10.5 public contract | ✓ |
| 状态迁移通过 CAS + 同事务 EventLog | ✓ |
| RECOVERING cancel 不调用 WorkerProxy | ✓ |
| `cancel_session_runs` 不 fail-closed 于 RECOVERING | ✓ |
| graceful shutdown / close 行为不变 | ✓ |
| watcher 行为不变 | ✓ |
| 分层清晰：durable transition → admission → command facade | ✓ |
| 类型完备：无 `Any`、无 `object`、无缺失类型注解 | ✓ |
| docstring 完整 | ✓ |

## 文档合规

- `dayu/host/README.md`：更新 cancel_run / cancel_session_runs 覆盖范围与 RECOVERING 语义 ✓
- `tests/README.md`：更新 public cancel 与 public smoke coverage 描述 ✓
- `docs/host/implementation-control.md`：更新 gate 状态与事实记录 ✓
- 根 `README.md`、`dayu/README.md`、`dayu/engine/README.md`：无需更新（无 user-facing CLI / layer boundary 变化）✓

## 结论

**PASS** — 0 blocking, 0 high, 1 medium, 3 low.

实现严格遵循 Phase 11 Slice 4 plan 的 exact changes。RECOVERING cancel 正确追加 `CANCEL_REQUESTED + RUN_CANCELLED`，不修改旧 Attempt，不调用 WorkerProxy。`cancel_session_runs` 正确将 RECOVERING 纳入 session-scope 目标集。deferred-cancel 分类正确移除 RECOVERING。graceful shutdown / close / watcher 行为确认未被修改。禁改模块（`dayu/host/dispatch.py`、`dayu/host/open_host.py`、`dayu/engine/`）确认未被触碰。测试覆盖 RECOVERING cancel 的 Run-level fact、Attempt 不变性、session-scope 同批取消和 public async 路径不传播 worker cancel。pyright 零错误，19 tests passed。

建议：M1（错误信息过期）可在 Slice 4 fix 或 Slice 5 中顺手修正。L1-L3 不影响正确性，可由 Controller 裁决是否处理。
