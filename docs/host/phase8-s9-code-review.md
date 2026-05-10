# P8-S9 Code Review：手工 Smoke

## 结论

**PASSED**

smoke 脚本功能可用、安全输出合规、scope 边界清晰。原有 2 个 Medium finding 和 1 个 Low finding 已全部修复：S3 改用 supervisor scan、plan §15 文案对齐、S7 通过 P8-S8 gap fix 后的 repair 路径验证 `memory_recovered=true recovery_mode=checkpoint_rebuild`。无 blocker，允许 commit。

---

## 1. 审查范围确认

| 检查项 | 结果 |
| --- | --- |
| 新增文件 | `utils/smoke_host_p8_attempt_lease.py` (463 行) |
| 修改文件 | `dayu/host/README.md` (+10 行 smoke 说明) |
| 生产代码修改 | 无 |
| 自动 wire `recover_stale_attempts` 到 production startup | 无 |
| P9 Session / Run lifecycle admission | 未实现 |
| 真实 provider / 外部服务 / API key 调用 | 无 |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | clean |

---

## 2. Smoke 场景覆盖分析

### S1: Owner A acquire + renew

- **路径**：`AttemptSupervisor.lease_context()` -> `AttemptLeaseStore.acquire_new_attempt()` + `AttemptLeaseStore.renew()`
- **输出**：`owner_acquired=true owner=***8ad8 fencing_token=1 renewed=True`
- **评估**：✅ 正确覆盖 lease acquire 与 renew。`lease_context` 是 supervisor 级入口，renew 在 context 内手动调用 store 层验证。

### S2: Owner B acquire 同 attempt_index -> busy

- **路径**：`AttemptLeaseStore.acquire_new_attempt()` with `UNIQUE(run_id, attempt_index)` conflict
- **输出**：`busy=True`
- **评估**：✅ 正确。通过 store 层直接调用验证同 attempt_index 的唯一约束冲突。

### S3: Recovery attempt 创建

- **路径**：`AttemptSupervisor.recover_stale_attempts(run_id=...)` -> 候选扫描 -> per-candidate `BEGIN IMMEDIATE` -> `AttemptLeaseStore.mark_recovering_and_create_attempt()`
- **输出**：`recovered_from=***6176 recovery_attempt=***c663 recovery_index=1 old_state=recovering`
- **评估**：✅ Finding 001 已修复。S3 现在验证 supervisor recovery scan、候选过滤与 CAS 编排路径，不再直接绕过 supervisor 调用 store 层。

### S4: Late write fenced

- **路径**：`AttemptScopedRunEventAppender.append()` -> `AttemptLeaseStore.verify_owner()` -> `AttemptFencingError`
- **输出**：`late_write=fenced reason=attempt_not_running`
- **评估**：✅ 正确验证旧 owner 的 late write 被 fencing 拒绝。reason `attempt_not_running` 合理——旧 attempt 已被 S3 推到 `RECOVERING` 状态。

### S5: Terminal close

- **路径**：`AttemptSupervisor.append_terminal_and_close()` -> atomic verify_owner + append + close
- **输出**：`terminal_event_position=2 attempt_state=failed`
- **评估**：✅ Finding 002 已修复。smoke 明确使用 Host-owned `RUN_FAILED` terminal 覆盖 failure diagnostic 路径，plan §15 已同步为 `attempt_state=failed`。

### S6: Observer caught up

- **路径**：close bundle -> reopen -> `startup_reconcile()` -> `coordinator.drain()` -> check `lag_events == 0`
- **输出**：`observer_caught_up=True`
- **评估**：✅ 正确模拟"terminal 后未 drain，重新装配后 startup_reconcile 追平 observer"。file SQLite 跨 harness 实例持久化保证了场景真实性。

### S7: Durable memory recovery

- **路径**：checkpoint CAUGHT_UP -> 删除 `host_conversation_memory_snapshots` 中当前 session row -> reopen -> `startup_reconcile()` -> `DurableConversationMemoryStore.repair_missing_session_snapshots()` -> EventLog 重投
- **输出**：`checkpoint_caught_up=True snapshot_deleted=True memory_recovered=True recovery_mode=checkpoint_rebuild`
- **评估**：✅ Finding 003 已修复。S7 现在验证 checkpoint 已追平且 memory snapshot row 丢失时，startup reconcile 后的 durable repair 路径可从 EventLog 重建 session memory。

---

## 3. Findings

### Finding 001 [Medium]：S3 Recovery 路径绕过 supervisor，直接调用 store 层

- **严重度**：Medium
- **文件行号**：`utils/smoke_host_p8_attempt_lease.py:281-295`
- **直接证据**：

```python
async with bundle.storage.transaction() as tx:
    recovery_decision = (
        bundle.attempt_lease_store
        .mark_recovering_and_create_attempt(
            tx=tx,
            source_attempt_id=a_attempt_id,
            ...
        )
    )
```

smoke 调用 `AttemptLeaseStore.mark_recovering_and_create_attempt()`（`_run_state_store.py:915`），而非 `AttemptSupervisor.recover_stale_attempts()`（`_attempt_supervisor.py:717`）。

- **影响**：P8-S9 plan §15 明确描述场景 3 为"lease 过期后 **recovery scan** 标记 owner A attempt 为 recovering，创建 owner B recovery attempt"。`recover_stale_attempts()` 包含候选扫描（`state IN ('running','created') AND lease_expires_at <= now`）+ per-candidate `BEGIN IMMEDIATE` CAS + typed `AttemptRecoveryDecision` 返回。绕过 supervisor 意味着 smoke 未验证 supervisor 的扫描逻辑、候选过滤和 CAS 编排，smoke 证明力不足。
- **建议修法**：改用 `bundle.attempt_supervisor.recover_stale_attempts(run_id=_SMOKE_RUN_ID)` 获取决策，再从 decision 中取出 `recovery_attempt_id` 构造后续 owner_context。smoke 仍可通过 `attempt_state_store.get()` 读取旧 attempt 状态和新 recovery attempt 的 fencing_token。
- **修复状态**：`fixed` — S3 改用 `bundle.attempt_supervisor.recover_stale_attempts(run_id=_SMOKE_RUN_ID)`，通过 `AttemptRecoveryDecision` 验证 supervisor scan 路径。recovery attempt 的 owner_token 由 supervisor 内部持有，S5 改用 `lease_context()` acquire 新 attempt (attempt_index = recovery_index + 1) 执行 terminal close。

### Finding 002 [Low]：S5 `attempt_state=failed` 与 plan 预期不一致

- **严重度**：Low
- **文件行号**：`utils/smoke_host_p8_attempt_lease.py:364-384`
- **直接证据**：

smoke 使用 `_terminal_failed_draft()`（`RUN_FAILED`），产出 `attempt_state=failed`。Plan §15 写：

> 场景 5：owner B 写 terminal event 并 close attempt，输出 `terminal_event_position=<int> **attempt_state=succeeded**`。

- **影响**：不影响正确性。`append_terminal_and_close` 路径对 `SUCCEEDED` / `FAILED` 都走同一原子事务，smoke 已正确验证 `terminal_event_position` 非空且 attempt 终态已写入。使用 `RUN_FAILED` 是合理的测试选择（Host-owned failure terminal 是 P8 重要路径）。但 plan 与实现不一致，需明确是 plan 文案错误还是实现应改为 `SUCCEEDED`。
- **建议修法**：二选一：(a) 将 plan §15 场景 5 文案改为 `attempt_state=failed` 以匹配实现；(b) 将 smoke 改为 `_terminal_succeeded_draft()` 以匹配 plan。建议 (a)，因为 `RUN_FAILED` 覆盖了 Host-owned failure terminal 这条更具诊断价值的路径。
- **修复状态**：`fixed` — 采用建议 (a)，plan §15 场景 5 文案改为 `attempt_state=failed` 以匹配实现。`RUN_FAILED` 覆盖 Host-owned failure terminal 诊断路径。

### Finding 003 [Medium]：S7 Durable memory recovery 语义覆盖不足

- **严重度**：Medium
- **文件行号**：`utils/smoke_host_p8_attempt_lease.py:399-412`
- **直接证据**：

```python
bundle2 = build_durable_harness(config=config, clock=clock)
# ...
snapshot = await bundle2.memory_store.get_snapshot(_SMOKE_SESSION_ID)
has_user_input = any(
    _SMOKE_USER_TEXT in (turn.user_text or "")
    for turn in snapshot.recent_raw_turns
)
```

smoke 只测试"reopen 后 memory snapshot 仍可读取"。P8-S8 的核心目标是：projection checkpoint 已 caught up 但 memory read model 丢失时，`startup_reconcile` 能从 EventLog 重投重建 memory。当前 smoke 未覆盖：

1. checkpoint 已 caught up + memory 丢失 + rebuild 场景。
2. crash-before-projection（terminal 已持久化但 drain 未执行）后 memory 重建。
3. `build_durable_harness` 默认不再依赖 `InMemoryConversationMemoryStore` 的断言。

- **影响**：P8-S8 已通过 `tests/host/test_phase8_durable_memory_recovery.py` 覆盖完整 recovery 语义（crash-before-projection、checkpoint-caught-up rebuild、InMemory 残留扫描）。smoke 不需要重复 pytest 级覆盖，但作为 P8-S9 验收信号，当前 S7 只证明"durable store 跨 reopen 持久化"，不证明"durable memory recovery 路径"。对不了解测试覆盖的运维人员，smoke 输出可能误读为 memory recovery 已完整验证。
- **建议修法**：在 S7 中增加 checkpoint caught-up 断言（验证 `host_projection_checkpoints` 中 memory observer 的 `lag_events == 0`），并在重新装配前通过 `memory_store.apply_patch(session_id, {"type": "SESSION", "scope": "SESSION"})` 清空 memory，再验证 `startup_reconcile` 重建。若改动过大，至少在 smoke docstring 中注明 S7 只覆盖普通 reopen 持久化，完整 recovery 语义由 `test_phase8_durable_memory_recovery.py` 覆盖。
- **修复状态**：`fixed` — P8-S9 初始发现了 memory recovery gap（checkpoint CAUGHT_UP + snapshot row 缺失时 memory 无法恢复）。P8-S8 gap fix 已通过 `DurableConversationMemoryStore.repair_missing_session_snapshots` 修复：在 `DurableHarnessBundle.startup_reconcile` 之后调用，checkpoint 已 `CAUGHT_UP`、EventLog 无新事件、但 snapshot row 缺失时从 EventLog 重投重建；`MemoryResetPatch` / `ScopeClearPatch(SESSION)` 写入的空 snapshot 行因 row 仍存在不会被 repair 误恢复。smoke S7 现在输出 `memory_recovered=true recovery_mode=checkpoint_rebuild`，pytest 新增 repair / 不误恢复 intentional empty 两条覆盖。本 Finding 在 S8 gap fix 落地后 re-review 通过。

---

## 4. 安全输出审查

| 检查项 | 结果 |
| --- | --- |
| owner token 明文 | 未泄露。所有 owner 使用 `masked()` 显示 `***xxxx` |
| scope token | 未出现 |
| cursor token | 未出现 |
| prompt 内容 | `_SMOKE_USER_TEXT = "P8 smoke 用户问题"` 仅用于内部验证，不出现在 summary 输出 |
| tool result | 未出现 |
| provider raw payload | 无真实 provider 调用 |
| owner/session/attempt id masking | ✅ `_mask_id()` 对所有 id 做末尾 4 位 masking |
| 输出行数 | 7 行 summary + 1 行 VERBOSE log（默认模式），≤20 行 |
| key=value 格式 | ✅ 稳定 |
| DEBUG log 泄露 | owner_token 在 DEBUG log 中已 masked（`***a624` 等）；lease_expires_at、attempt_id、owner_id 为诊断信息，不构成安全风险 |

---

## 5. 文档同步审查

| 检查项 | 结果 |
| --- | --- |
| `dayu/host/README.md` 新增内容 | 在"当前手工验证"section 新增 P8 smoke 说明，属于 Host README 职责范围 |
| 内容准确性 | ✅ 描述 7 个场景、file SQLite + fake clock + deterministic fake worker、token masking、≤20 行 |
| 是否误写 P9 能力为已落地 | 否 |
| `tests/README.md` 不更新 | 合理。本 slice 是 `utils/` 手工 smoke，不是 pytest 层级，`AGENTS.md` 明确 `utils/` 下脚本默认无需测试 |
| `migration-plan.md` 不更新 | ⚠️ P8-S9 状态未在 `migration-plan.md` §4.4 中登记。按 gateflow §3.1，Phase 状态应在 commit 前落文档。当前 §4.4 只追踪到 P8-S8，S9/S10 状态缺失。不阻塞 commit，但应在 P8-S10 文档收口时一并更新 |

---

## 6. 代码质量 / 项目约束审查

| 检查项 | 结果 |
| --- | --- |
| 中文 docstring | ✅ 所有函数、类、模块均有完整中文 docstring，包含参数、返回值、异常 |
| lazy import / glue seam | `_ensure_repo_root_on_path()` 是 `utils/` 脚本标准模式，有充分理由（直接 `python` 运行时需将 repo root 加入 `sys.path`） |
| `Any` / `object` / 无类型签名 | 未发现 |
| 魔法字符串/数字 | `_LEASE_TTL_SECONDS=30`、`_LEASE_RENEW_INTERVAL_SECONDS=10`、`_REPO_ROOT_PARENT_INDEX=1`、`tail=4` 均为 smoke 级常量，合理 |
| brittle direct DB/store bypass | ⚠️ S3 绕过 supervisor 直接调 store（见 Finding 001） |
| 真实 sleep | 无。使用 `FakeUtcClock.advance()` |
| 时间敏感 race | 无。fake clock 消除所有时间依赖 |
| 隐藏 flakiness | 无。file SQLite + deterministic fake clock + 无网络依赖 |

---

## 7. 验证命令复核

```bash
# smoke 默认模式
python utils/smoke_host_p8_attempt_lease.py
# → 7 行 summary，全部通过

# smoke DEBUG 模式
python utils/smoke_host_p8_attempt_lease.py --log-level DEBUG
# → 7 行 summary + DEBUG 日志，owner_token masked，无敏感信息泄露

# 类型检查
python -m pyright
# → 0 errors, 0 warnings, 0 informations

# 空白检查
git diff --check
# → clean
```

---

## 8. Residual Risks 与 Owner

| 风险 | Owner | 状态 |
| --- | --- | --- |
| 慢硬盘 + Docker Linux 多进程压力 | GitHub issue #38 | `deferred` |
| `recover_stale_attempts` 自动 wire 进 production startup lifecycle | P9 | `deferred` |
| P8-S10 文档收口（`migration-plan.md` 状态同步、`docs/host/design.md` 更新） | P8-S10 | `deferred` |
| S3 smoke recovery 路径证明力不足 | Finding 001 | `fixed` |
| S7 smoke memory recovery 语义覆盖不足 | Finding 003 | `fixed (P8-S8 gap fix landed, re-reviewed)` |

---

## 9. Gate 建议

**允许 commit**。Finding 001 / 002 / 003 已全部修复：

- Finding 001: S3 改用 `recover_stale_attempts()` supervisor scan，S5 改用 `lease_context()` 新 attempt terminal close。
- Finding 002: Plan §15 场景 5 文案已改为 `attempt_state=failed`。
- Finding 003: P8-S9 初始发现了 memory recovery gap；P8-S8 gap fix 已通过
  `DurableConversationMemoryStore.repair_missing_session_snapshots` 与
  `DurableHarnessBundle.startup_reconcile` 联动修复，smoke S7 现在输出
  `memory_recovered=true recovery_mode=checkpoint_rebuild`。
