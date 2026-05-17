# P9.5 S14 Code Review — AgentDS

**Review scope**: S14 P9 Memory Cleanup And Production Catch-Up Wiring 未提交 diff  
**Base**: `p9.5-pre-p10-hardening` vs HEAD unstaged changes  
**Reviewer**: AgentDS  
**Date**: 2026-05-17  
**Verdict**: **PASS** — 6 findings, 0 blocking, 0 medium/high severity regressions

---

## Review methodology

按第一性原理逐项复核 6 个指定重点 + adversarial failure pass。所有证据来自直接代码阅读与工具验证（rg、pytest、pyright、git diff --check），不依赖间接推断。

---

## Finding 1: Legacy `read_run_input_continuity_events` 删除安全性

**Severity**: PASS (info)

**Checked**:
- `rg "read_run_input_continuity_events" --glob="*.py"` → 0 matches in production code
- `dayu/host/run_input.py` 中 `rg "read_run_input_continuity|continuity_events"` → 0 matches
- `_EVENT_TYPE_USER_INPUT_ACCEPTED`、`_EVENT_TYPE_RUN_SUCCEEDED` 等模块级常量：`rg "_EVENT_TYPE_USER_INPUT_ACCEPTED|_RUN_INPUT_CONTINUITY_EVENT_TYPES" --glob="*.py"` 返回的文件中不包括删除目标 `event_log.py` 以外的调用方——这些常量在 `admission.py`、`memory.py`、`run_transition.py` 等中独立定义，删除 `event_log.py` 中的副本不影响它们
- `EventLogStore.read_run_input_continuity_events` 方法与模块级函数 `read_run_input_continuity_events` 均已删除，无残留 re-export 或 compatibility wrapper

**Conclusion**: 这是纯粹的 dead code removal。所有引用仅存在于 `docs/reviews/` 历史 artifact 中，无生产或测试依赖。符合 CLAUDE.md "禁止兼容性代码" 约束。

---

## Finding 2: `current_goal` first-write-wins 测试充分性

**Severity**: PASS

**Checked**:
- 生产逻辑 `_pinned_state_with_user_input` (memory.py:1390-1391):
  ```python
  current_goal = pinned_state.current_goal
  if current_goal is None:
      current_goal = text
  ```
  只在 `pinned_state.current_goal is None` 时写入，后续用户输入不覆盖

- 测试覆盖两个维度:
  1. `test_current_goal_first_write_wins_and_later_inputs_are_constraints`: 3 条连续 `USER_INPUT_ACCEPTED` 事件 → 第一条为 `current_goal`，三条全在 `user_constraints`
  2. `test_current_goal_preserved_when_projecting_later_user_delta`: 已有 goal 的 snapshot 投影后续 delta event → `current_goal` 保持不变，delta 文本加入 constraints

**Conclusion**: "fresh build" 路径与 "delta projection" 路径均被覆盖。first-write-wins 的语义与 `_replace_item_by_id` 的幂等设计（同 event_id 的 item 会被替换而非追加）一致——用户输入是 idempotent per event，但 goal 是 first-write-wins，二者互不冲突。

---

## Finding 3: Concrete `ProjectionCatchupPort` 测试覆盖三个投影入口

**Severity**: PASS

**Checked**:

| 测试 | 入口 | 验证点 |
|---|---|---|
| `test_start_run_concrete_memory_catchup_projects_user_input` | admission `start_run` commit 后 | `current_goal == "start input"`，snapshot 非空 |
| `test_tool_fact_accept_concrete_memory_catchup_projects_verified_fact` | `DefaultHostToolFactAcceptPort.accept_tool_fact` commit 后 | `verified_facts[0].event_id == tool_result_event_ref.event_id` |
| `test_resolve_wait_committed_tool_fact_catches_up_memory` | `DefaultHostResolveWaitService.resolve_wait` commit 后 | verified fact 的 `event_id` 匹配已提交 `TOOL_RESULT_ACCEPTED` event |

三个测试均遵循相同模式：注入 `ConversationMemoryProjectionCatchupPort(transaction_runner, policy, batch_size=8)` → 执行 command → `read_latest_memory_snapshot` 读回并断言 memory state。

**Conclusion**: 三个关键 catch-up 入口（admission user input、tool runtime accept、resolve_wait committed fact）均有端到端 concrete port 测试，证明 committed EventLog 可被正确地 catch up 进入 memory snapshot。

---

## Finding 4: 默认不接入 command handle/scheduler 的正确性

**Severity**: PASS

**Checked**:
- `create_host_admission_service` 默认 `projection_catchup_port=NoopProjectionCatchupPort()`
- `HostAdmissionService.cancel_run` → 不调用 `catch_up_projection_best_effort`（cancel 产生的事件类型 `CANCEL_REQUESTED`/`RUN_CANCELLED`/`RUN_CANCELLING` 均不在 memory consumer 的 filter 内）
- `HostAdmissionService.promote_next_queued_run` → 不调用 `catch_up_projection_best_effort`（promotion 产生 `RUN_STARTED`/`ATTEMPT_STARTED`，同样不在 memory filter 内）
- `HostAdmissionService` 中只有 `start_run`（产生 `USER_INPUT_ACCEPTED`）、`submit_followup_queue`（同上）、`closeout_attempt_terminal`（可能产生 `RUN_SUCCEEDED`/`RUN_FAILED`/`RUN_LOST`）调用 `catch_up_projection_best_effort`

**Reasoning validation**: 题干所述 "generic post-commit catch-up 默认不接入是因为它无 `max_event_sequence` 且 latest-only snapshot 会越过当前 dispatch cursor" 经核实正确。`catch_up_conversation_memory_projection` 在没有 `max_event_sequence` 参数时会从当前 checkpoint 一直读到 EventLog 末尾，可能越过还未 dispatch 的事件边界。`dispatch.py:878` 的 worker 启动路径有自己独立的 synchronous catch-up 并传入 `batch_size` 约束。只有显式注入 `ConversationMemoryProjectionCatchupPort` 的调用方才承担此语义责任。

**Conclusion**: 默认 no-op 是安全的保守选择。显式注入是 opt-in 的语义契约。

---

## Finding 5: Durable memory `payload_digest` 列修复

**Severity**: PASS

**Checked**:
- 修复前 (`git diff` 中的原始行): `payload_digest=item.provenance.digest_ref`
  - `digest_ref` 由 `_tool_fact_digest_ref` 计算，其 fallback 链包含 `outcome_digest`（非 payload digest 值），可破坏 `payload_ref`/`payload_digest` 成对 CHECK 约束
- 修复后 `_payload_digest_for_verified_fact`:
  1. `payload_ref is None` → 返回 `None`（正确：无 payload_ref 则 payload_digest 也应为 None）
  2. `evidence_anchor is not None and evidence_anchor.digest is not None` → 返回 `evidence_anchor.digest`（正确：`evidence_anchor.digest` 来自 `_payload_ref_pair_from_event` 的实际 payload_digest）
  3. 否则 → `item.provenance.digest_ref`（fallback：当 evidence_anchor 缺失 digest 时保留 digest_ref 作为 best-effort；此路径在 payload_ref 有值但 payload_digest 缺失时触发，但实际 `_payload_ref_pair_from_event` 返回成对值，此路径概率极低）

- `ConversationContinuityItem.__post_init__` (memory.py:485-486) 明确要求 `payload_ref` 与 `payload_digest` 成对，修复后的逻辑与此 invariant 一致

**Adversarial check**: 即使 fallback 路径写入非 payload digest 值，也不会比修复前更差（修复前总是写入 digest_ref，修复后在 case 2 已纠正为正确的 payload_digest）。

**Conclusion**: 修复正确，在常见路径上纠正了 invariant，且不引入新的退化。

---

## Finding 6: Full Host regression 验证

**Severity**: PASS

**Evidence**:
- `pytest tests/host -q` → **554 passed** in 6.30s
- `pyright dayu tests` → **0 errors, 0 warnings, 0 informations**
- `git diff --check` → clean（无 trailing whitespace、无 conflict markers）

---

## Additional findings

### Finding 7: Import boundary 静态防护

**Severity**: PASS (info)

新增 `test_memory_modules_do_not_import_upper_business_or_engine_layers` 静态检查 `memory.py`、`memory_repair.py`、`durable/memory.py` 不导入 `dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins`。与 `memory.py` 模块级 docstring 声明一致（"不导入 Engine / Fins / Service / UI"）。

### Finding 8: Display-only events 不入 memory

**Severity**: PASS (info)

新增 `test_preview_reasoning_and_display_only_events_do_not_enter_memory` 验证 `EventClass.PREVIEW`（CONTENT_DELTA、REASONING_DELTA）和 `EventClass.DIAGNOSTIC`（RUN_SUCCEEDED display-only）事件不被 memory consumer 处理。结果 `events_scanned=4, events_matched=1`，仅 `EventClass.CANONICAL_FACT` 的 `USER_INPUT_ACCEPTED` 进入 snapshot。

### Finding 9: README 更新精确

**Severity**: PASS (info)

README 变更精准反映了代码行为：
- "可显式注入 concrete catch-up port"（非强制接入）
- "默认仍使用 no-op catch-up port，便于测试 / dev 显式控制"
- worker 启动路径的同步 catch-up 描述与 `dispatch.py:878` 的 `memory_projection_catchup_batch_size` 一致

---

## Adversarial failure pass

对以下 failure modes 进行了 adversarial check，均未发现可利用路径：

1. **catch-up 在 write transaction 内触发部分失败**：`catch_up_conversation_memory_projection` 内部 `ProjectionRunner` 每个 EventLog row 在独立 `run_write` 内完成，consumer failure 只影响该 row 并写入 failure row，不 rollback 已提交的 command write transaction。验证通过。

2. **catch-up failure 影响 command 返回值**：`catch_up_projection_best_effort` 使用 `try/except Exception: logger.exception`，不抛异常、不修改返回值。验证通过。

3. **concurrent catch-up 竞争**：`catch_up_conversation_memory_projection` 使用 `ProjectionRunner` 从 checkpoint cursor 开始逐行推进，每个 row 的 checkpoint advance 在同一个 write transaction 内完成。SQLite serialized mode 下无 race。验证通过。

4. **event_log.py 删除后 import 引用残留**：全量 rg 确认 `read_run_input_continuity_events` 和 `_RUN_INPUT_CONTINUITY_EVENT_TYPES` 在 `.py` 文件中无残留引用。验证通过。

5. **`promote_next_queued_run` 在 `dispatch.py:443-447` 被 scheduler 用 admission service wrapper 调用**：该路径有独立的 `catch_up_projection_best_effort` 在 L442 触发（在 promotion 之前），且传给 `create_host_admission_service` 的 `projection_catchup_port` 与 scheduler 相同。双重 catch-up（L442 + admission 内部的 catch-up）会触发两次 projection runner，但 runner 的 idempotent checkpoint 机制保证第二次为 no-op。Not a bug。

---

## Summary

| # | Finding | Severity | Verdict |
|---|---|---|---|
| F1 | `read_run_input_continuity_events` 删除安全性 | info | PASS |
| F2 | `current_goal` first-write-wins 测试 | — | PASS |
| F3 | Concrete catch-up port 三入口测试 | — | PASS |
| F4 | 默认 no-op catch-up 正确性 | — | PASS |
| F5 | `payload_digest` 列修复 | — | PASS |
| F6 | Full Host regression (554 passed, pyright clean) | — | PASS |
| F7 | Import boundary 静态防护 | info | PASS |
| F8 | Display-only events 不入 memory | info | PASS |
| F9 | README 更新精确性 | info | PASS |

**Overall verdict**: PASS — S14 在不引入 snapshot history/P10/recovery 的前提下正确收口了 memory cleanup（移除 legacy continuity reader）与 catch-up wiring（三入口显式注入 + 默认 no-op + worker 启动同步 catch-up）。无局部止血或错误缩小 scope。
