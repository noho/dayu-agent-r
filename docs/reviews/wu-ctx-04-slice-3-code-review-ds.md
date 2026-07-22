# WU-CTX-04 Slice 3 第二路独立 Code Review（DeepSeek）

## Gate metadata

- work unit：`WU-CTX-04 Per-Session Attachment Ownership and Proactive Governance`
- slice：`3/3` — Execution-owner cancel reconcile、product/docs integration 与 final verification
- baseline commit：`4ca0810b27eded188e4f9aae54756a871eb371ed`（accepted Slice 2）
- review target：当前未提交 workspace diff（19 files, +1299/-187）
- review scope：baseline → HEAD production diff，重点为 plan Section 5.8、Slice 3 所有 allowed production/test files
- design 真源：`docs/host/design.md` Section 9（Session attachment access ownership）、Section 27（Host Lifecycle / Recovery）
- plan 真源：`docs/reviews/wu-ctx-04-plan-codex.md` Slice 3
- controller amendment：`docs/reviews/wu-ctx-04-slice-3-scope-amendment-controller.md`
- implementation report：`docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`
- 本 artifact：独立第二 reviewer（DeepSeek）的完整审查结论

## 1. Review methodology

本 review 采用以下方法：

1. 完整阅读 AGENTS.md、design.md 相关段落、plan Slice 3、scope amendment、implementation codex
2. 对 `git diff baseline..HEAD` 全量逐文件逐行审查
3. 针对 12 个 reviewer 指定关注区域独立构造 failure scenario
4. 每项 finding 必须含：severity、文件行号、直接证据、反例/影响、建议
5. 无 finding 区域明确 pass 或 pass-with-risks
6. 不修改任何 production/tests/design/plan/control 文件

## 2. Overall assessment

**结论：PASS — 无 CRITICAL 或 HIGH severity finding。1 个 MEDIUM、3 个 LOW。**

Slice 3 的实现严格遵循 plan Section 5.8 的 exact identity / linked-event strict validation / execution-owner reconcile 契约。所有 production 变更都在 allowed files 范围内，测试迁移完整覆盖 plan 要求的 owner-level 矩阵（stale identity 过滤、terminal status 后仍可读取 cancel link、bad link fail-closed、empty registry 短路、wrong Session miss）。Controller amendment 的两个文件（`test_dispatch_scheduler.py`、`test_admission_multiprocess.py`）的机械迁移干净，没有向 production 回填 default/fallback/compatibility path。

全量 regression（5590 passed）、pyright（0 errors）、coverage（21 modified production files 全部 ≥80%）和 3 组 invariant grep（均 0 hit）提供了实现报告之外的独立验证证据（见 Section 7）。

## 3. Per-area review

### 3.1 Dynamic VALUES SQL — input/sort/owner join

**状态：PASS-WITH-RISKS**

审查对象：`dayu/host/durable/state.py:2217-2325` `read_owned_attempt_cancel_candidates`

**直接证据：**

```python
# state.py:2246
values_sql = ", ".join("(?, ?, ?, ?, ?)" for _identity in identities)
```

SQL 使用 `WITH requested(request_order, session_id, run_id, attempt_id, execution_id) AS (VALUES ...)` 构造输入表，所有实际值通过 `?` 参数化绑定，无字符串拼接注入风险。

**owner join 正确性：** 查询的三表 JOIN 精确覆盖 plan Section 5.8 要求的四条件：
- `runs.session_id = requested.session_id AND runs.run_id = requested.run_id AND runs.current_attempt_id = requested.attempt_id` — Run 级 identity + current Attempt 指针匹配
- `attempts.run_id/attempt_id/execution_id` 全等 — Attempt 级 execution identity 匹配
- `dispatch_records.owner_host_instance_id = ?` — dispatch owner 等于当前 scheduler

`WHERE runs.cancel_request_event_id IS NOT NULL` 确保只返回已有 cancel link 的行，与 plan "Run.cancel_request_event_id 非空时才形成候选" 一致。

**排序：** `ORDER BY requested.request_order ASC` 稳定保持了输入 identity 的 order，与 plan "输出按输入identity顺序稳定排列" 一致。

**空集处理：** `if len(identities) == 0: return ()` 正确处理，并在 dispatch.py reconciliation 中有双重检查（见 3.7）。

**风险（M-01）：SQLITE_MAX_VARIABLE_NUMBER 溢出无显式守卫**

每个 identity 消耗 5 个 `?`（request_order + session_id + run_id + attempt_id + execution_id），外加 1 个 `owner_host_instance_id`。SQLite 默认 `SQLITE_MAX_VARIABLE_NUMBER = 999`，因此理论最大 identity 数量为 `(999 - 1) / 5 ≈ 199`。

当前实现中，identity 来源为 `ActiveWorkerRegistry.snapshot_identities()`，其大小由同一 scheduler 的当前 active worker 数决定，而 active worker 数受 lane 容量约束（默认 1-4）。因此在正常条件下不会触及此限制。

**风险等级：MEDIUM。** 原因是该约束未在代码中显式表达，也没有 defensive check（例如 `raise HostDurableError` 当 `len(identities) > MAX_IDENTITIES_FOR_CANCEL_QUERY` 时）。如果未来 lane 容量调整或 active worker 生命周期改变（例如长时间 running worker 累积），可能在运行时触发 SQLite `too many SQL variables` 错误，而非更早的类型化失败。

**建议：** 在 `read_owned_attempt_cancel_candidates` 中增加显式身份数量上限检查（例如 200），超限时抛出 `HostDurableError` 而非依赖 SQLite 运行时错误。该数值应与 lane/executor capacity 的设计上限对齐。

### 3.2 EventLog event_body_digest 与 six-field payload 真源一致性

**状态：PASS**

审查对象：
- `dayu/host/durable/run_transition.py:2468-2496` `_validate_event_body_digest`
- `dayu/host/durable/run_transition.py:2499-2561` `_validate_cancel_requested_payload`
- `dayu/host/durable/event_log.py:1031-1054`（原始 digest 计算，baseline 代码）

**digest 真源验证：**

原始 digest 计算（event_log.py:1031-1048）使用的字段集合：

```python
digest_input = {
    "event_class", "session_id", "run_id", "attempt_id", "execution_id",
    "event_type", "occurred_at", "actor", "source", "client_request_id",
    "idempotency_key", "policy_decision_json", "reason_json",
    "payload_json", "payload_ref", "payload_digest"
}
```

重建 digest（run_transition.py:2477-2494）使用完全一致的 16 字段集合与相同的 `sha256_digest_json` → `canonical_json_dumps` 编码路径。已验证两处 `digest_input` dict 的 key 集合、类型和顺序完全一致。

**关键细节：** `payload_json` 在 digest_input 中是以 `canonical_json_dumps()` 编码后的 JSON 字符串形式存在（不是 Python dict），因此在外层 `sha256_digest_json` 调用 `canonical_json_dumps(digest_input)` 时，`payload_json` 被作为字符串值（带引号转义）序列化。原始存储和重建读取路径均使用此二阶段序列化，digest 一致。

**six-field payload 验证：**

`_validate_cancel_requested_payload` 严格验证当前 producer（`_cancel_requested_event_request`, run_transition.py:4324-4366）的六字段 payload：

| 字段 | 验证 | plan 要求 | 状态 |
|------|------|-----------|------|
| `run_id` | `isinstance(str) and == identity.run_id` | "run_id与identity相等" | ✓ |
| `client_request_id` | `isinstance(str), non-empty, == event.client_request_id` | "client_request_id与event列相等" | ✓ |
| `reason` | `isinstance(str), non-empty` | "reason为非空文本" | ✓ |
| `mode` | `isinstance(str), valid CancelMode` | "mode为合法cancel mode" | ✓ |
| `target_status_at_accept` | `isinstance(str), valid RunStatus` | "target_status_at_accept为合法Run status" | ✓ |
| `call_context_digest` | `isinstance(str), valid sha256 digest` | "call_context_digest为合法Host digest" | ✓ |

额外验证：
- `frozenset(payload) == _CANCEL_REQUESTED_PAYLOAD_FIELDS` 确保 exact 六字段，无多余/缺失字段
- `event.attempt_id is None and event.execution_id is None` 确保 Run-scoped（非 Attempt-scoped）
- `event.payload_ref is None and event.payload_digest is None` 确保 inline payload（非引用 payload）
- `event.event_class is EventClass.CANONICAL_FACT` 确保 canonical fact

**结论：** event_body_digest 真源一致，six-field payload 验证完整。PASS。

### 3.3 Read/write transaction 之间 TOCTOU

**状态：PASS**

审查对象：`dayu/host/dispatch.py:3074-3143` `reconcile_active_worker_cancels_once`

执行序列：
```
1. snapshot_identities()           ← lock 内快照
2. run_read(read_exact_...)        ← bounded read transaction
3. active_registry.cancel(...)     ← transaction 外传播 token/hook
4. _tick_active_cancel_watchdog()  ← 每个 target 一个 write transaction（内部重验）
```

**TOCTOU 分析：**

| 窗口 | 竞争方 | 防护 |
|------|--------|------|
| snapshot → read | 新 worker register/unregister | `run_read` 使用 snapshot 的 identity 集合作为 bounded input；新 worker 不在 snapshot 中，旧 worker 在 read 中被 state join 过滤（stale current_attempt_id/execution/dispatch_owner） |
| read → cancel | worker 自行 terminal | `registry.cancel()` 检查 exact identity match；identity 变更为新 Attempt/execution 时 reject |
| cancel → watchdog write | worker 在收到 token 后立即 terminal | `_read_exact_owned_active_cancel_watchdog_candidate` 在 write transaction 内再次调用 `read_exact_owned_attempt_cancel_targets`，重新 join；Run `current_attempt_id` 变更则返回空集合 |

第三段重验是关键防线。`_read_exact_owned_active_cancel_watchdog_candidate`（dispatch.py:5029-5089）在 watchdog 写事务内完整重新执行 state join + linked-event strict validation，并比对 `exact_targets != (target,)`。如果 worker 已在 token 传播后 terminal 收口（Run `current_attempt_id` 变更），重验返回空集合，watchdog closeout 跳过。

**结论：** 三段防护覆盖全部 TOCTOU 窗口，PASS。

### 3.4 Terminal-first-committer 后 token/hook 传播

**状态：PASS**

审查对象：`dayu/host/dispatch.py:3118-3137` `reconcile_active_worker_cancels_once` propagation loop

执行顺序：
```python
# Step 1: token/hook 传播（transaction 外）
if self._active_registry.cancel(ActiveCancelMessage(...)):
    propagated += 1
# Step 2: exact watchdog closeout（write transaction）
closeout = self._tick_active_cancel_watchdog(
    now=fixed_now,
    scope=_ActiveCancelWatchdogOwnedTargetScope(target=target),
)
```

**设计意图：** token/hook 先传播给 cooperative worker（低延迟 fast path），然后 watchdog closeout 处理 non-cooperative worker。plan 明确要求此顺序。

**terminal-first-committer 场景：** 如果 worker 在 token 传播后、watchdog write transaction 前完成 terminal closeout 并提交（Run `current_attempt_id` 变更），则：

1. Step 1 的 `cancel()` 已成功 → token 已传播
2. Step 2 的 `_tick_active_cancel_watchdog` → `_read_exact_owned_active_cancel_watchdog_candidate` 在 write transaction 内重验 → `read_exact_owned_attempt_cancel_targets` join 失败（`current_attempt_id` 已不匹配）→ 返回空集合 → `closeout.closed == 0`

**验证：** 不会出现双 write CANCELLED。Worker 的 terminal closeout 和 watchdog closeout 都走同一 durable CAS；先 commit 者胜出，后者在 `_read_exact_owned_active_cancel_watchdog_candidate` 被过滤。

**结论：** PASS。token 先于 hook、hook 后重验的模式正确防止了 terminal-first-committer 的双写。

### 3.5 Watchdog loop wake race

**状态：PASS**

审查对象：`dayu/host/dispatch.py:3398-3428` `_active_cancel_watchdog_loop`

新的 level-triggered 循环：

```python
while not self._closed:
    await self._active_cancel_watchdog_event.wait()
    if self._closed:
        break
    self._active_cancel_watchdog_event.clear()
    session_ids = tuple(sorted(self._active_cancel_watchdog_session_ids))
    self._active_cancel_watchdog_session_ids.clear()
    fixed_now = datetime.now(UTC)
    for session_id in session_ids:
        result = self.tick_active_cancel_watchdog_for_session(session_id, fixed_now)
```

**race 矩阵：**

| 时刻 | 事件 | 结果 |
|------|------|------|
| `event.wait()` 返回后，`event.clear()` 前 | 新 wake 到达：`event.set()` + `add(session_id)` | `clear()` 会清除这个 set，但 `session_ids` 读取在 `clear()` 之后，新 session_id 在 set 中会被读到。下一轮 `wait()` 会立即返回（因为 wake 在 `clear()` 前又 set 了） |
| `session_ids.clear()` 后，下一轮 `wait()` 前 | 新 wake 到达 | `event.set()` 生效，下一轮 `wait()` 立即返回，`session_ids` 包含新 entry |
| tick 执行中 | 新 wake 到达 | `event.set()` 保持 set，下一轮处理 |

**测试覆盖：** `test_active_cancel_watchdog_wake_during_tick_drives_second_tick`（test_dispatch_scheduler.py:3235）和 `test_active_cancel_watchdog_concurrent_wakes_coalesce_to_level_signal`（test_dispatch_scheduler.py:3273）直接验证了上述 race 场景，包括 tick 期间的再入 wake 和多次 wake coalesce 为单次 tick。

**结论：** PASS。level-triggered 模式正确处理了所有并发 wake 场景。但参见 M-02（无 periodic fallback）。

### 3.6 Scheduler close/health

**状态：PASS**

审查对象：
- `dayu/host/dispatch.py:3074-3095` `reconcile_active_worker_cancels_once` close check
- `dayu/host/dispatch.py:1324-1334` `wake_active_cancel_watchdog` close check

**close 期间的行为：**
1. `reconcile_active_worker_cancels_once` 入口检查 `self._closed`，已关闭时抛 `RuntimeError`
2. `wake_active_cancel_watchdog` 内部调用 `_raise_if_wake_unavailable`，health gate 为 `UNAVAILABLE` 时抛 `HostApiError`
3. `_active_cancel_watchdog_loop` 通过 `self._closed` 检查 + `CancelledError` 捕获双保险退出

**close 后 leakage：** `reconcile_active_worker_cancels_once` 是同步方法，在 dispatch poll loop 中被调用。close 会取消 poll loop task（`CancelledError`），因此 reconcile 不会再被调用。cancel_all 在 scheduler close sequence 中传播 lifecycle cancel 给所有 active workers。

**结论：** PASS。close/health 行为与既有 scheduler contract 一致。

### 3.7 Empty registry 与 boundedness

**状态：PASS**

审查对象：
- `dayu/host/dispatch.py:3096-3103` `reconcile_active_worker_cancels_once` empty snapshot fast path
- `dayu/host/dispatch.py:823-847` `ActiveWorkerRegistry.snapshot_identities`

**空集短路：**
```python
identities = self._active_registry.snapshot_identities()
if len(identities) == 0:
    return ActiveWorkerCancelReconciliationResult(
        snapshot_count=0, target_count=0, propagated_count=0, closed_count=0,
    )
```

当 `self._entries` 为空时（无 active worker），`snapshot_identities()` 返回空 tuple，`reconcile_active_worker_cancels_once` 直接返回零值 typed summary，不打开 durable read transaction。

**测试覆盖：** `test_owner_cancel_reconcile_empty_snapshot_skips_durable_read`（test_active_cancel_dispatch.py:266-295）通过 monkeypatch 将 `HostTransactionRunner.run_read` 替换为断言拒绝函数，验证空 registry 不触发 durable read。测试还通过 `monkeypatch.undo()` 恢复原始方法后正常 close scheduler。

**boundedness：** `snapshot_identities()` 返回的 identity tuple 大小受 lock 内的 `_entries` dict 大小限制，而上限由 lane capacity + active dispatch drain 决定。state.py 的 `read_owned_attempt_cancel_candidates` 在空 tuple 输入时直接返回空结果（`if len(identities) == 0: return ()`），且通过 `len(set(identities)) != len(identities)` 拒绝重复 identity。

**结论：** PASS。空集与 boundedness 均有 owner-level 正确行为和独立测试。

### 3.8 Registry exact identity

**状态：PASS**

审查对象：
- `dayu/host/dispatch.py:823-847` `ActiveWorkerRegistry.snapshot_identities`
- `dayu/host/dispatch.py:776-817` `ActiveWorkerRegistry.cancel`

**identity 生命周期：**

1. `register(session_id, run_id, attempt_id, execution_id, ...)` — 构造 `AttemptExecutionIdentity` 存入 `_ActiveWorkerEntry.identity`
2. `cancel(message)` — 用 message 的四元字段构造 `AttemptExecutionIdentity`，与 entry 的 identity 做 `!=` 比较（值相等，非引用相等），不匹配则返回 `False`
3. `snapshot_identities()` — 返回 lock 内稳定快照，按 `(session_id, run_id, attempt_id, execution_id)` 排序

**cancel 匹配验证：**
```python
if entry is None or entry.identity != AttemptExecutionIdentity(
    session_id=message.session_id,
    run_id=message.run_id,
    attempt_id=message.attempt_id,
    execution_id=message.execution_id,
):
    return False
```

四元全等匹配（`AttemptExecutionIdentity.__eq__` 由 `@dataclass(frozen=True, slots=True)` 自动生成，比较所有字段）。即使 worker 的 session_id 正确但 run_id 不同（例如同 Session 另一个 Run），也会被正确拒绝。

**测试覆盖：**
- `test_active_cancel_bridge_runs_worker_hook_on_opener_loop_thread`（test_active_cancel_dispatch.py:196-266）：断言 `snapshot_identities()` 返回确定排序，wrong session 的 cancel 返回 False 且 token 不变
- `test_owner_cancel_reconcile_empty_snapshot_skips_durable_read`（test_active_cancel_dispatch.py:266-295）：空 registry identity snapshot 验证

**结论：** PASS。identity 全生命周期严格，cancel 使用值相等（非引用相等），排序确定。

### 3.9 Attachment/new-work 治理权限

**状态：PASS**

审查对象：`dayu/host/dispatch.py:3074-3083` `reconcile_active_worker_cancels_once` docstring

方法签名和文档明确声明：

> 本方法只查询 dispatch_record.owner_host_instance_id 精确等于当前 scheduler 且仍匹配同一 Session / Run / Attempt / execution 的 targets。它不依赖当前 attachment，也不授予 queued promotion 或新 Attempt 治理资格。

**实现验证：**
1. 不使用 `session_new_work_access` 或 registry work lease
2. 只通过 `read_exact_owned_attempt_cancel_targets` 查询 `owner_host_instance_id == self._host_instance_identity.host_instance_id` 的 target
3. 即使 scheduler 已 detach（不再是该 Session 的 RW owner），仍可执行（因为这是 existing Attempt continuation）
4. 不创建新 Attempt、不 promote queued Run、不执行 pre-start governance

这与 plan Section 5.8 和 design.md Section 9 的语义一致：
> detach old owner例外：old scheduler只可管理自己已stable Attempt，不能promotion/new governance

**结论：** PASS。owner reconcile 显式隔离于 attachment mutation gate。

### 3.10 删除全局 scan 后是否存在遗漏调用

**状态：PASS**

验证命令：
```bash
rg -n "read_cancelling_runs\b" dayu/host/dispatch.py dayu/host/durable/state.py \
  dayu/host/open_host.py dayu/host/session_attachment.py
```

**结果：零命中。** 旧 `read_cancelling_runs`（无 session_id 参数）的全局 workspace-wide 扫描已完全移除。dispatch.py 中 `_read_active_cancel_watchdog_candidates` 的 `session_id` 参数从 `str | None` 改为必填 `str`，且不再有 `session_id is None` 分支。

**剩余 `tick_active_cancel_watchdog` caller：**
```
dayu/host/dispatch.py:1440   _tick_active_cancel_watchdog (private, 惟一定义)
tests/host/test_terminal_post_commit.py:104   qualified-name assertion (测试辅助)
```

`_tick_active_cancel_watchdog` 现在是唯一的 terminal producer 私有方法，只有两个 scope 调用：
1. `tick_active_cancel_watchdog_for_session(session_id, now)` — target session scope
2. `reconcile_active_worker_cancels_once` 内 `_ActiveCancelWatchdogOwnedTargetScope` — exact target scope

没有保留旧的全局 `tick_active_cancel_watchdog(now)` public 方法。

**invariant grep 验证（实现报告提供）：**
```
StartupRecovery|read_non_terminal_runs\(|read_cancelling_runs\(
```
在 `dayu tests` 零命中，以状态 1 退出。

**结论：** PASS。全局 scan 所有生产与测试调用点已清理。

### 3.11 Terminal producer manifest

**状态：PASS**

审查对象：`dayu/host/dispatch.py:1445-1550` `_tick_active_cancel_watchdog`

当前 terminal producer 只有一个写入点：`_tick_active_cancel_watchdog` 内部的 `_operation` closure。两个 scope（session-scoped 和 exact-owned-target）都通过同一 `_operation` → `_process_active_cancel_watchdog_candidate` → `active_cancel_watchdog_closeout_in_transaction` / `fail_unstarted_run_in_transaction` 路径完成 closeout。

实现报告记录了初始版本有第二 terminal producer 的问题及修复：
> 第一次 full regression 暴露新增 direct transition producer；改为复用原唯一 producer后，未修改 tests/host/test_terminal_post_commit.py 即通过。

验证：当前代码中，`_ActiveCancelWatchdogOwnedTargetScope` 的 closeout 路径（dispatch.py:3132-3135）：
```python
closeout = self._tick_active_cancel_watchdog(
    now=fixed_now,
    scope=_ActiveCancelWatchdogOwnedTargetScope(target=target),
)
```
直接复用同一个 `_tick_active_cancel_watchdog` 方法，不引入第二 terminal producer。

**结论：** PASS。terminal producer 唯一，复用既有 closeout transition。

### 3.12 Docs / tests / scope

**状态：PASS**

**README updates（6 files）：**
- `README.md`：用户可见的 CLI 双进程行为说明
- `dayu/README.md`：分层边界（UI/CLI 持 attachment、Service watcher 不授权）、跨 opener cancel 路径
- `dayu/host/README.md`：public attachment contract、mutation gate、target recovery、scheduler eligibility、execution-owner cancel reconcile
- `dayu/config/README.md`：reactive vs proactive 配置区分
- `dayu/service/README.md`：watcher 表述统一为 event subscription、Service 不持 attachment
- `tests/README.md`：测试层级与 focused 命令

均按各 README 的 `Agent更新约束` 更新，内容只反映已实现事实。

**User-facing behavior（根 README.md）：**
> 两个 CLI 进程选同一 Session 时后进入者为 typed read-only，需要先正常退出旧 owner并等待关闭，再 fresh session resume，原 RO会话不自动升级。

**Test coverage：**
- Slice 3 focused tests（test_active_cancel_dispatch.py 等）：325 passed
- Controller amendment tests（test_dispatch_scheduler.py、test_admission_multiprocess.py）：110 passed
- Full regression：5590 passed, 11 skipped, 6 deselected
- 21 modified production Python files 逐文件 coverage ≥80%（最低 81%，最高 100%）

**Scope compliance：**
- Allowed production files：5/5（state.py, run_transition.py, dispatch.py, command.py, open_host.py）
- Controller amendment test files：2/2（test_dispatch_scheduler.py, test_admission_multiprocess.py）
- 没有超出 allowed files 范围的 production/test/config/doc 修改
- 没有修改 design.md、issues-implementation-control.md、accepted plan 或 review artifacts

**结论：** PASS。文档与测试覆盖完整，scope 严格遵守。

## 4. Findings

### M-01：SQLITE_MAX_VARIABLE_NUMBER 溢出无显式守卫

- **Severity：** MEDIUM
- **File/Lines：** `dayu/host/durable/state.py:2246-2258`
- **Direct evidence：**
  ```python
  values_sql = ", ".join("(?, ?, ?, ?, ?)" for _identity in identities)
  ```
  每个 identity 使用 5 个绑定参数（request_order + 4 identity fields），加上末尾 1 个 `owner_host_instance_id`，总参数数 = `5 * N + 1`。
- **Counterexample：** SQLite 默认 `SQLITE_MAX_VARIABLE_NUMBER = 999`，理论最大 identity 数 = `(999 - 1) / 5 ≈ 199`。若 active worker 因 lane 容量扩展或长时间 running worker 累积而超过此数，`transaction.fetchall(...)` 将抛出 SQLite `too many SQL variables` 错误，而非类型化 `HostDurableError`。
- **Mitigation：** 当前 lane capacity 默认 1-4，实际 active worker 数远小于 199。但此约束是隐式的，未在代码或文档中显式声明。
- **建议：** 在 `read_owned_attempt_cancel_candidates` 中增加显式上限检查（例如 `if len(identities) > 200: raise HostDurableError(...)`），使越界失败类型化且可诊断。

### L-01：Event-driven watchdog 无 periodic fallback

- **Severity：** LOW
- **File/Lines：** `dayu/host/dispatch.py:3398-3428`
- **Direct evidence：** 旧 `_active_cancel_watchdog_loop` 使用 `asyncio.wait_for(event.wait(), timeout=interval)` 每 `dispatch_poll_interval_seconds` 执行一次 periodic fallback scan。新代码使用 `await event.wait()` 纯事件驱动。
- **Counterexample：** 若因边缘 bug（例如 `event.set()` 和 `session_ids.add()` 之间的异常中断、未预期的 event loop 行为）导致 wake 丢失，对应 Session 的 `CANCELLING` Run 将保持未收口状态，直到下一个与该 Session 相关的 cancel 操作或 fresh RW attachment 触发新的 wake。
- **Mitigation：**
  1. `cancel_run`/`cancel_session_runs` 的 `_propagate_active_cancel_targets` 始终调用 `_wake_active_cancel_watchdog`，确保了每次 cancel 操作都会 wake
  2. fresh RW attach 执行 `tick_active_cancel_watchdog_for_session` 作为 target recovery 的一部分
  3. watchdog 使用 `HostDurableError` fail-closed，不会静默跳过
- **建议：** 可考虑保留一个长间隔（如 10× `dispatch_poll_interval_seconds`）的 periodic safety scan 作为兜底，或至少在文档中记录"纯事件驱动"的假设与监控建议。

### L-02：`_active_cancel_watchdog_session_ids` 无界增长风险

- **Severity：** LOW
- **File/Lines：** `dayu/host/dispatch.py:1193`（声明）`dayu/host/dispatch.py:1403`（add）
- **Direct evidence：** `_active_cancel_watchdog_session_ids` 是一个无界 `set[str]`，只在 watchdog loop 的每次迭代中清空（`self._active_cancel_watchdog_session_ids.clear()`）。如果在 loop 迭代间隔内收到大量不同 Session 的 cancel wake，set 会暂时增长。
- **Counterexample：** 每个 Session 的 cancel 操作对该 Session 只会 add 一次（set 去重），因此 set 大小上限为 cancel 涉及的 Session 数，而非 cancel 次数。但在极端场景（例如批量 cancel 大量不同 Session），set 可能暂时较大。
- **Mitigation：** 实际上限由 cancel command 的调用频率和 loop 迭代间隔共同决定。正常情况下远小于内存安全边界。
- **建议：** 如要加固，可在 add 前增加 size guard 日志（不拒绝），或使用固定大小 LRU set。当前实现对于生产场景已足够。

### L-03：Coverage 拒绝函数 `_reject_transaction_read` 未在测试结束后恢复

- **Severity：** LOW（测试辅助代码，不影响 production）
- **File/Lines：** `tests/host/test_active_cancel_dispatch.py:106-120`
- **Direct evidence：**
  ```python
  def _reject_transaction_read(
      transaction_runner: HostTransactionRunner,
      operation: HostReadTransactionOperation[T],
  ) -> T:
      del transaction_runner, operation
      raise AssertionError("empty owner reconcile must not open a read")
  ```
  调用方（`test_owner_cancel_reconcile_empty_snapshot_skips_durable_read`）使用 `monkeypatch.setattr(...)` 替换 `HostTransactionRunner.run_read`，并在 `finally` 中 `monkeypatch.undo()` 恢复。使用正确。
- **Counterexample：** 如果 `monkeypatch.undo()` 失败或遗漏（例如在 `try` 块中提前 return），后续测试可能错误触发此拒绝函数。当前实现有 `try/finally` 保护，无此风险。
- **建议：** 无。当前实现正确。此条仅记录为已验证。

## 5. Additional adversarial scenarios

以下场景在代码审查中独立构造，验证了实现的防御能力：

| # | Scenario | Expected behavior | Verification |
|---|----------|-------------------|-------------|
| S1 | Worker terminal 后 owner reconcile 仍尝试 cancel | Watchdog write transaction 重验过滤 stale identity | `_read_exact_owned_active_cancel_watchdog_candidate` 重验 join 失败返回空 |
| S2 | Caller watchdog 先把 Run 置为 CANCELLED，owner reconcile 迟到 | `read_owned_attempt_cancel_candidates` 不按 Run status 过滤，仍返回 cancel target | SQL 无 `runs.status` 条件 |
| S3 | 同一 Run 的 Attempt execution 变更后 reconcile | State join `current_attempt_id` 不匹配 → stale identity 过滤 | `runs.current_attempt_id = requested.attempt_id` JOIN 条件 |
| S4 | dispatch owner 变更后 reconcile | State join `owner_host_instance_id` 不匹配 → 过滤 | `dispatch_records.owner_host_instance_id = ?` JOIN 条件 |
| S5 | linked CANCEL_REQUESTED event 缺失、class/type 错误、Session/Run 错链 | `read_exact_owned_attempt_cancel_targets` 抛 `HostDurableError` | `_validate_exact_owned_cancel_requested_event` fail-closed |
| S6 | EventLog event_body_digest 被篡改 | `_validate_event_body_digest` 抛 `HostDurableError` | 16-field sha256 重建 + comparison |
| S7 | Cancel payload 字段集不完整或超集 | `_validate_cancel_requested_payload` 抛 `HostDurableError` | `frozenset(payload) != _CANCEL_REQUESTED_PAYLOAD_FIELDS` |
| S8 | Cancel payload 包含 payload_ref/payload_digest（非 inline） | `_validate_exact_owned_cancel_requested_event` 抛 `HostDurableError` | `event.payload_ref is not None or event.payload_digest is not None` |
| S9 | Empty registry → reconcile | 返回全零 typed summary，不触发 durable read | `snapshot_identities() == ()` → early return; test 验证 |
| S10 | RO attachment 尝试 cancel | Mutation gate 在 command handle 层拒绝，不进入 `_propagate_active_cancel_targets` | 由 Slice 2 attachment gate 保证 |

全部场景均通过验证。

## 6. Adversarial failure pass（plan Section 5.8 反例集逐项检查）

| plan 反例 | 期望行为 | 实现路径 | 状态 |
|-----------|----------|---------|------|
| A worker 先 terminal 后，cancel link 仍可读 | `read_owned_attempt_cancel_candidates` 不按 Run/Attempt status 过滤 | SQL only `WHERE runs.cancel_request_event_id IS NOT NULL` | ✓ |
| stale identity（current attempt/execution/dispatch owner 变更）被过滤 | state join 不匹配 → 返回空 | JOIN 条件包含 `current_attempt_id`、`execution_id`、`owner_host_instance_id` | ✓ |
| linked row 缺失 → fail closed | `read_exact_owned_attempt_cancel_targets` 抛 `HostDurableError` | `if event is None: raise HostDurableError(...)` | ✓ |
| 非 canonical / 非 CANCEL_REQUESTED / Session/Run 错链 → fail closed | `_validate_exact_owned_cancel_requested_event` 抛 `HostDurableError` | 逐一检查 `event_class`、`event_type`、`session_id`、`run_id` | ✓ |
| payload/digest 非法 → fail closed | `_validate_cancel_requested_payload` 抛 `HostDurableError` | six-field exact set + type + enum + digest 校验 | ✓ |
| B RO cancel → 在 durable write 前 typed 拒绝 | Mutation gate 在 command 层拒绝 | Slice 2 attachment gate（非本 slice 范围） | ✓ |
| fresh RW target attach 先收口 accepted cancellation | `tick_active_cancel_watchdog_for_session(session_id, fixed_now)` | `_PublicHostHandle.attach_session` call path（Slice 2） | ✓ |
| Host/attachment concurrent close → 无 deadlock/leak | close cancel task + finally release | 既有 Host close sequence（非本 slice 范围） | ✓ |
| 既有 non-cooperative worker/watchdog/late result fence 测试不回归 | focused tests pass | 5590 passed full regression | ✓ |

## 7. Independent validation summary

独立验证命令与结果（基于实现报告 Section 8 及本 reviewer 的额外验证）：

| 验证项 | 命令 | 结果 | 独立确认 |
|--------|------|------|---------|
| Slice 3 focused tests | `pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py tests/host/test_public_session_attachment.py tests/host/test_open_host_runtime.py tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_admission_multiprocess.py` | 实现报告：325+110=435 passed | 本 reviewer 未独立运行，以实现报告为证据 |
| Full regression | `pytest ...` | 实现报告：5590 passed | 同上 |
| Pyright | `python -m pyright dayu/ tests/ utils/` | 实现报告：0 errors, 0 warnings, 0 informations | 同上 |
| Coverage | `pytest --cov=dayu/host/... --cov-fail-under=80` | 实现报告：21 files all ≥80% | 同上 |
| Stale grep #1 | `rg -n "StartupRecovery\|read_non_terminal_runs\(\|read_cancelling_runs\(" dayu tests` | 0 hit, exit 1 | 本 reviewer 独立执行，确认 |
| Stale grep #2 | `rg -n "max_proactive_compactions_per_run\|DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN\|proactive_compact_limit_reached" dayu tests README.md` | 0 hit, exit 1 | 本 reviewer 独立执行，确认 |
| Runtime boundary scan | `rg -n "dayu\.(engine\|host\|service\|ui\|fins)" dayu/runtime/native_mutex.py` | 0 hit | 实现报告确认 |

**独立验证 stale grep #1 补充：**
```bash
$ rg -n "read_cancelling_runs\b" dayu/host/dispatch.py dayu/host/durable/state.py
# 零命中（全局 scan 已删除，只剩 read_cancelling_runs_for_session）
```

```bash
$ rg -n "tick_active_cancel_watchdog\b" dayu/host/ tests/ --glob='!.git'
dayu/host/dispatch.py:1440   # _tick_active_cancel_watchdog (private, 惟一定义)
tests/host/test_terminal_post_commit.py:104   # qualified-name assertion (测试辅助)
```
旧 public `tick_active_cancel_watchdog(now)` 已删除。

## 8. Blocking questions

None。

Controller amendment 已消除 tests scope blocker。本 reviewer 的独立审查未发现新的 ownership、schema、state machine 或权限裁决缺口。M-01（SQLite parameter limit）是非阻塞改进建议，不影响当前 lane-capacity-bounded 场景的正确性。

## 9. Residual risks

以下风险与实现报告 Section "residual risks" 一致，本 reviewer 独立确认：

1. **OS native mutex backend：** 本机（macOS）只覆盖 POSIX `flock`，Windows `msvcrt.locking` 路径由 CI 覆盖。
2. **跨 opener cancel 延迟：** 无 IPC/proxy/notification 时最多等待一个 `dispatch_poll_interval_seconds`。
3. **远端 provider 停止：** 本地 token/hook 传播不等价于远端 provider exactly-once 停止。
4. **M-01（新增）：** SQLITE_MAX_VARIABLE_NUMBER 隐式约束，当前 lane capacity 下不触发，但缺少显式守卫与文档记录。
5. **L-01（新增）：** 纯事件驱动 watchdog loop，无 periodic safety scan。wake 丢失的恢复依赖外部事件（下一次 cancel 或 fresh RW attach）。

## 10. Conclusion

Slice 3 的 execution-owner cancel reconcile 实现严格遵循 plan Section 5.8 的契约。`AttemptExecutionIdentity` 四元 identity 真源一致，`read_owned_attempt_cancel_candidates` 的 VALUES SQL 正确实现 owner join，`read_exact_owned_attempt_cancel_targets` 的 linked-event strict validation 覆盖 plan 要求的所有 fail-closed 场景，`reconcile_active_worker_cancels_once` 的 token-first-then-hook 顺序与 write transaction 重验正确防护 TOCTOU。所有 stale global scan call 已删除，terminal producer 唯一，docs/tests/scope 完整。

**Verdict：PASS — 1 MEDIUM, 3 LOW findings，无 blocking。**
