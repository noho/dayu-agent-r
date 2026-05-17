# P9.5 S14 Code Review — Memory Cleanup And Production Catch-Up Wiring

## Review Context

- Reviewer: AgentMiMo
- Scope: S14 P9 Memory Cleanup And Production Catch-Up Wiring
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Plan: `docs/host/p9-5-pre-p10-hardening-plan.md` S14
- Implementation artifact: `docs/reviews/p9-5-s14-memory-cleanup-catchup-implementation-20260517.md`
- Diff: uncommitted changes on `p9.5-pre-p10-hardening`

## Verdict: PASS

S14 实现正确收口了 memory cleanup、legacy 移除、production catch-up wiring 和 root cause 修复。所有设计约束均已满足，无 blocker finding。

---

## Findings

### F1 — `current_goal` first-write-wins 只补测试是否合理

**Severity: INFO (合理)**

`_pinned_state_with_user_input` 在 `dayu/host/memory.py:1365-1398` 已正确实现 first-write-wins：

```python
current_goal = pinned_state.current_goal
if current_goal is None:
    current_goal = text
```

实现 artifact 说明不重写已有正确代码，只补 targeted tests。diff 中新增两个测试：

- `test_current_goal_first_write_wins_and_later_inputs_are_constraints`：3 条 `USER_INPUT_ACCEPTED` 事件，断言第一条保持为 `current_goal`，全部三条进入 `user_constraints`。
- `test_current_goal_preserved_when_projecting_later_user_delta`：已有 snapshot 上做 inline delta 投影，断言既有 `current_goal` 不被覆盖。

**判定**：合理。代码不变，测试覆盖了 first-write-wins 和 inline delta 保留两个边界。plan 要求的"若实现发现代码不再 first-write-wins 则修复"条件未触发。

---

### F2 — 移除 `read_run_input_continuity_events` 是否无生产调用且没有兼容 wrapper

**Severity: PASS**

diff 移除了：
- `dayu/host/durable/event_log.py` 中的模块级 `read_run_input_continuity_events` 函数（~62 行）
- `EventLogStore.read_run_input_continuity_events` 方法（~22 行）
- 相关常量 `_RUN_INPUT_CONTINUITY_EVENT_TYPES` 和 5 个 `_EVENT_TYPE_*` 常量

验证：
- `grep read_run_input_continuity_events **/*.py` 返回 0 匹配（生产代码和测试均无调用）
- 被移除的 `_EVENT_TYPE_*` 常量在 `read_model.py`、`admission.py`、`run_input.py`、`engine_ingest.py`、`memory.py`、`durable/memory.py`、`durable/run_transition.py` 中各自独立定义，不依赖 `event_log.py` 的版本
- 无兼容 wrapper 或 re-export

**判定**：移除干净，无遗留依赖。

---

### F3 — `SessionContinuityProvider` 是否仍只 resume-specific

**Severity: PASS**

探索 agent 确认 `DurableSessionContinuityProvider`（`dayu/host/run_input.py`）当前只返回 resume-specific continuity：从 `_resume_wait_message_from_current_start(...)` 获取已接受的 wait result 系统消息。不调用已移除的 `read_run_input_continuity_events`，不发射历史 raw turns。

plan 要求的"移除 legacy historical raw-turn behavior"已通过移除 reader 达成，provider 本身无需修改。

**判定**：符合设计约束。

---

### F4 — preview/reasoning/display-only exclusion 是否正确

**Severity: PASS**

新增测试 `test_preview_reasoning_and_display_only_events_do_not_enter_memory`：

- 写入 `PREVIEW` event_class 的 `CONTENT_DELTA`（preview 内容）
- 写入 `PREVIEW` event_class 的 `REASONING_DELTA`（reasoning preview）
- 写入 `DIAGNOSTIC` event_class 的 `RUN_SUCCEEDED`（display-only 结论）
- 写入 `CANONICAL_FACT` event_class 的 `USER_INPUT_ACCEPTED`（canonical 用户事实）

断言：
- `events_scanned == 4`（全部事件被扫描）
- `events_matched == 1`（只有 canonical 事件被投影）
- `current_goal == "canonical user fact"`
- `verified_facts == ()`（无 verified fact）
- `conversation_continuity.items` 只包含 canonical 用户事实

**判定**：覆盖了 PREVIEW、DIAGNOSTIC 两种排除路径，验证 memory 只消费 CANONICAL_FACT。

---

### F5 — memory import boundary 是否够

**Severity: PASS**

新增测试 `test_memory_modules_do_not_import_upper_business_or_engine_layers`：

- 检查模块：`memory.py`、`memory_repair.py`、`durable/memory.py`
- 禁止前缀：`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins`

符合 `docs/host/design.md` 的分层边界：memory 模块属于 Host 内部，不得反向依赖 Engine / Service / UI / Fins。`dayu.runtime` 不在禁止列表中（正确的低层依赖）。

**判定**：import boundary 覆盖完整。

---

### F6 — explicit concrete catch-up tests for user input / tool fact / resolve_wait 是否覆盖真实 post-commit path

**Severity: PASS**

三个端到端测试覆盖了 S14 plan 要求的全部 post-commit 路径：

1. **admission path** — `test_start_run_concrete_memory_catchup_projects_user_input`：
   - 注入 `ConversationMemoryProjectionCatchupPort` 到 `create_host_admission_service`
   - 调用 `start_run`，验证 memory snapshot 包含 `current_goal == "start input"`

2. **tool fact accept path** — `test_tool_fact_accept_concrete_memory_catchup_projects_verified_fact`：
   - 注入 concrete port 到 `DefaultHostToolFactAcceptPort`
   - 调用 `accept_tool_fact`，验证 memory snapshot 包含 1 条 verified fact，且 event_id 匹配

3. **resolve_wait path** — `test_resolve_wait_committed_tool_fact_catches_up_memory`：
   - 注入 concrete port 到 `create_host_admission_service`
   - 调用 `resolve_wait`，验证 memory snapshot 包含 1 条 verified fact，且 event_id 在 TOOL_RESULT_ACCEPTED 事件集合中

每个测试都使用真实 durable store（`tmp_path`），走完整的 write-then-catch-up 路径，不是 mock。

**判定**：三个 post-commit 路径全覆盖，测试质量高。

---

### F7 — 控制器撤回 `create_host_command_handle` / `HostDispatchScheduler.open` 默认 generic concrete catch-up 是否是正确保守裁决

**Severity: PASS (正确保守裁决)**

实现 artifact 和 README 更新明确说明：

> `create_host_admission_service(...)` 默认仍使用 no-op catch-up port，便于测试 / dev 显式控制。

探索 agent 确认：
- `create_host_command_handle` 不注入 concrete port（admission 默认 no-op）
- `HostDispatchScheduler` 传递 `None` 时 `catch_up_projection_best_effort` 为 no-op
- 只有显式构造 `ConversationMemoryProjectionCatchupPort` 并注入才激活 catch-up

设计理由（实现 artifact）：若 `create_host_command_handle` 或 `HostDispatchScheduler.open` 默认接入无 cursor 上限的 generic concrete catch-up port，在 queued future input 场景会把 latest-only memory snapshot 推到当前 dispatch 所需 cursor 之后，触发 `snapshot_missing`。这正是 S14 stop condition 中的 snapshot-history 依赖。

**判定**：保守裁决正确。latest-only snapshot 在 queued future input 下需要 snapshot history 才能安全做 generic catch-up；S14 不引入 snapshot history，因此不能默认接入。显式注入 + dispatch worker 前 cursor-bound catch-up 是正确的中间态。

---

### F8 — `_payload_digest_for_verified_fact` 是否正确修复无 payload_ref tool fact CHECK root cause

**Severity: PASS**

schema CHECK 约束（`schema.py:194-198`）：

```sql
CHECK (
    (payload_ref IS NULL AND payload_digest IS NULL)
    OR
    (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
)
```

旧代码在 `_insert_verified_fact_item` 中直接使用 `item.provenance.digest_ref`（类型为 `str`，非 `None`）作为 `payload_digest`，即使 `payload_ref` 为 `None`，违反 CHECK 约束。

修复后 `_payload_digest_for_verified_fact`（`memory.py:636-651`）逻辑：

1. `payload_ref is None` → 返回 `None`（满足 `payload_ref IS NULL AND payload_digest IS NULL`）
2. `evidence_anchor.digest is not None` → 返回 evidence anchor digest（payload 存在时优先使用证据锚点 digest）
3. 否则 → 返回 `provenance.digest_ref`（fallback）

端到端验证：`test_tool_fact_accept_concrete_memory_catchup_projects_verified_fact` 使用 `payload_ref=None` 的 `_completed_candidate`（`test_toolruntime_accept_barrier.py:548`），通过 catch-up 写入 durable store 并成功读回 verified fact，证明 CHECK 约束不再被违反。

**判定**：root cause 修复正确。函数是私有的，由集成测试间接覆盖；无直接单元测试，但可接受。

---

### F9 — README 更新准确性

**Severity: PASS**

`dayu/host/README.md` 更新（行 121）准确反映实现：

- admission、ToolRuntime accepted tool fact path 与成功的 `resolve_wait` **可显式注入** concrete catch-up port
- `create_host_admission_service(...)` 默认仍使用 no-op catch-up port
- 本地 dispatch worker 启动路径按 cursor 同步 catch-up
- 无"未来设计"承诺，只描述当前行为

---

## Summary

| Finding | Description | Severity |
|---------|-------------|----------|
| F1 | current_goal first-write-wins 只补测试 | INFO (合理) |
| F2 | read_run_input_continuity_events 移除干净 | PASS |
| F3 | SessionContinuityProvider 仍只 resume-specific | PASS |
| F4 | preview/reasoning/display-only exclusion 正确 | PASS |
| F5 | memory import boundary 覆盖完整 | PASS |
| F6 | concrete catch-up tests 覆盖三个 post-commit path | PASS |
| F7 | 默认 no-op catch-up 是正确保守裁决 | PASS |
| F8 | _payload_digest_for_verified_fact CHECK root cause 修复正确 | PASS |
| F9 | README 更新准确 | PASS |

**结论**：S14 实现完整、正确、保守。无 blocker，无需要修复的 finding。可以接受。
