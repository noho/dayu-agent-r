# Code Review — WU-DUR-P01-S2-R2 关键路径窄版评审

## Scope

- Mode: current changes（窄版，限定 WU-DUR-P01-S2-R2 关键路径）
- Branch: phaseflow/wu-dur-obs-cm-closeout
- Base: main
- Output file: docs/reviews/wu-dur-p01-s2-r2-code-review-ds.md
- Included scope:
  - `dayu/host/engine_ingest.py`: `_append_iteration_started_events` (L2389-2522)、`_append_runner_call_iteration_link_event` (L2581-2619)、`_append_limited_runner_call_manifest_event` (L2524-2579)、`_append_rejected_diagnostic` (L2892-2961)、`_append_preview_event` (L2360-2387)
  - `dayu/host/engine_ingest.py`: `_find_unlinked_prepared_runner_call_manifest_events` (L5125-5173)、`_linked_manifest_event_ids` (L5176-5221)、`_is_unlinked_prepared_ordinary_manifest` (L5224-5257)
  - `dayu/host/engine_ingest.py`: `_has_prior_iteration_observation` (L5260-5328)
  - `dayu/host/engine_ingest.py`: `_runner_call_iteration_link_payload` (L5331-5405)、`_runner_call_iteration_link_matches` (L5408-5436)
  - `dayu/host/engine_ingest.py`: `_resolution_from_link_event` (L5439-5466)、`_iteration_started_preview_payload` (L5519-5556)
  - `tests/host/test_engine_ingest_mapping.py`: 13 个 iteration_started / runner_call_manifest 测试 (L2202-2910)
  - `docs/reviews/wu-dur-p01-s2-r2-implementation-codex.md`: 验证摘要
- Excluded scope: 非 WU-DUR-P01-S2-R2 的其他 engine_ingest.py 函数、其他测试、全仓探索
- Parallel review coverage: 无

## 七个检查点逐条审计

### Check 1: missing/ambiguous/mismatch/conflict 是否 fail closed

全部 fail-closed，均写入 `stop_worker_stream=True`：

| 场景 | 入口 | 证据 |
|------|------|------|
| **missing** (首个 iteration 无 prepared manifest) | `_append_iteration_started_events:2457` → `len(candidates)==0 && !_has_prior_iteration_observation` | L2464-2468: `_append_rejected_diagnostic(reason="missing_runner_call_manifest", stop_worker_stream=True)` |
| **ambiguous** (多个 unlinked prepared manifest) | `_append_iteration_started_events:2450` → `len(candidates)>1` | L2451-2456: `_append_rejected_diagnostic(reason="ambiguous_runner_call_manifest", stop_worker_stream=True)` |
| **mismatch** (新 link 与 Engine observation 不一致) | `_append_iteration_started_events:2500` → `resolution.status=="mismatch"` | L2501-2511: `_append_rejected_diagnostic(reason="runner_call_manifest_mismatch", stop_worker_stream=True, additional_events=(link_event,))` |
| **mismatch replay** (既有 link validation_status≠"complete") | `_append_iteration_started_events:2412` → existing_link matched 但 `resolution.status!="complete"` | L2424-2434: `_append_rejected_diagnostic(reason="runner_call_manifest_mismatch", stop_worker_stream=True)` |
| **link conflict** (同一 iteration 既有 link 与新 observation 不一致) | `_append_iteration_started_events:2412` → `!_runner_call_iteration_link_matches(existing_link, data)` | L2416-2422: `_append_rejected_diagnostic(reason="runner_call_iteration_link_conflict", stop_worker_stream=True)` |

测试覆盖:
- `test_iteration_started_missing_initial_manifest_fails_closed` (L2377): 首个 iteration 缺 manifest → `missing_runner_call_manifest`
- `test_iteration_started_ambiguous_prepared_manifest_fails_closed` (L2537): 2 个 unlinked manifest → `ambiguous_runner_call_manifest`
- `test_iteration_started_mismatch_fails_closed_after_link` (L2287): message count / role digest mismatch → `runner_call_manifest_mismatch`
- `test_iteration_started_link_conflict_fails_closed` (L2592): 同一 iteration 不同 observation → `runner_call_iteration_link_conflict`

结论：**通过，无阻断 finding**。

### Check 2: existing mismatch link replay 是否不写 accepted ITERATION_STARTED preview

代码路径：`_append_iteration_started_events:2411-2442`。当 exist_link 存在且 `_runner_call_iteration_link_matches` 返回 True 但 `resolution.status != "complete"` 时，仅返回 `_append_rejected_diagnostic`，**不进入** L2435-2442 的 preview 写入路径。

测试 `test_iteration_started_mismatch_fails_closed_after_link:2362-2374` 验证：
```python
assert [event.event_type for event in replay.events] == ["ENGINE_EVENT_REJECTED"]
assert _event_count(store.transaction_runner, "ITERATION_STARTED") == 0
```
重放只产出 `ENGINE_EVENT_REJECTED`，`ITERATION_STARTED` count 为 0。

结论：**通过，无阻断 finding**。

### Check 3: mismatch link 和 ENGINE_EVENT_REJECTED 是否不会 seed continuation prior observation

`_has_prior_iteration_observation` (L5260-5328) 的判断逻辑分两步：

1. **Link events 检查**（L5278-5307）: 遍历所有 `RUNNER_CALL_INPUT_ITERATION_LINKED`，仅当 `validation_status == "complete"` 时返回 True。Mismatch link 的 `validation_status` 为 `"mismatch"`，不满足条件。
2. **Preview 检查**（L5309-5328）: 仅查询 `ITERATION_STARTED` + `EventClass.PREVIEW`。`ENGINE_EVENT_REJECTED` 是 `EventClass.DIAGNOSTIC`，不匹配。

测试覆盖：
- `test_iteration_started_mismatch_link_does_not_seed_continuation` (L2412): mismatch 后新 iteration → `missing_runner_call_manifest`，不写 limited-signal manifest
- `test_iteration_started_rejected_event_does_not_seed_continuation` (L2486): 连续两次 rejected → 第二次仍为 `missing_runner_call_manifest`，`RUNNER_CALL_INPUT_ASSEMBLED` count 保持为 0

结论：**通过，无阻断 finding**。

### Check 4: continuation iteration_index 0 是否只在 accepted prior observation 后 limited-signal

代码路径：`_append_iteration_started_events:2457-2490`。当 `len(candidates) == 0` 且 `_has_prior_iteration_observation` 返回 True 时才写入 limited-signal manifest (`_append_limited_runner_call_manifest_event`)。

`_has_prior_iteration_observation` 返回 True 的条件：存在 `validation_status == "complete"` 的 link 或 `ITERATION_STARTED` PREVIEW。mismatch link 和 `ENGINE_EVENT_REJECTED` 都不满足。

测试覆盖：
- `test_iteration_started_continuation_reset_uses_limited_signal_after_link` (L2748): 首个 iteration accepted link 后，continuation iteration_index=0 → writes limited-signal manifest，`runner_call_kind="tool_result_continuation"`，`validation["continuation_limited_signal"]=True`
- `test_iteration_started_writes_limited_runner_call_manifest_for_continuation` (L2823): 有 prior ITERATION_STARTED preview 后的 continuation → writes limited canonical manifest signal

结论：**通过，无阻断 finding**。

### Check 5: old payload_iteration_id None + iteration_index 0 fallback 是否彻底消除

确认：实现报告中的 `rg` 结果——代码中不存在 `payload_iteration_id is None and iteration_index == 0` 模式。`_is_unlinked_prepared_ordinary_manifest` (L5224-5257) 使用显式判断：
- `iteration_id is not None` → 排除
- `iteration_index is not None` → 排除
- `runner_call_kind not in _ORDINARY_RUNNER_CALL_KINDS` → 排除
- `compactor_identity is not None` → 排除

旧函数 `_find_runner_call_manifest_event` / `_runner_call_manifest_matches_iteration` 已在当前 diff 中删除（实现报告确认）。

结论：**通过，无阻断 finding**。

### Check 6: link+preview 或 link+rejected 是否同 transaction

**Accepted 路径**（L2492-2522）：`self._append_runner_call_iteration_link_event(transaction, ...)` 和 `self._append_preview_event(transaction, ...)` 共享同一 `transaction` 对象，结果通过 `_event_rows_result(tuple(rows))` 合并返回。两者在同一事务边界内。

**Rejected mismatch 路径**（L2492-2511）：`link_event = self._append_runner_call_iteration_link_event(transaction, ...)` 先写入 link，再 `self._append_rejected_diagnostic(transaction, ..., additional_events=(link_event,))` 写入 rejected diagnostic。两者使用同一 `transaction`。`EngineIngestResult(events=additional_events + (row,))` 将 link 与 rejected 一起返回。

**Replay 路径**（L2411-2442）：existing_link 已存在时不重写 link，只写 preview（或 rejected diagnostic）。preview/rejected 的 `append_event` 通过 EventLogStore 的同体 idempotent 机制（`event_log.py:338-341`）处理重放：相同 event_id + 相同 body_digest → 返回既有 row，`inserted=False`。不在 replay 中产生重复写入。

**注意**：`EventLogStore.append_event` 的性质是**写入级幂等**而非**查询级幂等**——每次 replay 仍然会走到 `_append_preview_event` 调用，依赖 store 层做去重。这本身不是 bug，但意味着 replay 路径对 store 幂等行为的依赖是隐式的：如果 `_iteration_started_preview_payload` 或 `_resolution_from_link_event` 的逻辑在初始写入后、replay 前发生变化，`append_event` 会因 body_digest 不一致而抛出 `HostEventIdentityConflictError`。这是正确的 fail-closed 行为——宁可报错也不静默返回不一致结果。

结论：**通过，发现一个低风险维护注意点**（见 Findings）。

### Check 7: tests 是否覆盖这些路径且无 raw SQL

13 个 focused tests 全部 PASS（本次运行确认）。

测试辅助函数 `_append_prepared_runner_call_manifest` (L3632)、`_append_prior_iteration_started_preview` (L3714) 均使用 `EventLogStore().append_event()` 和 `transaction_runner.run_write()`，不涉及 raw SQL。`_event_count` (L3614) 使用 `EventLogStore().read_events_after()`。

测试文件中的 raw SQL（`_attempt_count` L3793、`_delete_event_by_id` L3930 等）属于其他测试辅助函数，不在 iteration_started / runner_call_manifest 测试的调用链内。

结论：**通过，无阻断 finding**。

## Findings

### 001-未修复-低-`_append_iteration_started_events` 三个分支返回类型路径的 readability 不足

- **入口/函数**: `EngineEventIngestor._append_iteration_started_events` (L2389-2522)
- **文件(行号)**: `dayu/host/engine_ingest.py:2389-2522`
- **输入场景**: 任何 ITERATION_STARTED ingest
- **实际分支**: 函数内三个主要返回点（existing_link accepted preview / existing_link rejected / candidates==0 missing / candidates==0 continuation / candidates>1 ambiguous / candidates==1 link+preview/rejected），部分由早期 return 实现，部分由 if-else 嵌套实现
- **预期行为**: 功能正确，控制流虽然可追踪但分支密度较高
- **实际行为**: 函数 133 行内包含 3 个 return 点、2 层嵌套 if，分支路径需要全量线性阅读才能确认无遗漏
- **直接证据**: L2416（冲突 return）、L2425（mismatch replay return）、L2442（accepted replay return）、L2451（ambiguous return）、L2464（missing return）、L2490（continuation return）、L2511（mismatch new return）、L2522（accepted new return）
- **影响**: 后续修改容易因分支覆盖不全引入回归；当前行为经测试验证正确
- **建议改法和验证点**: 考虑将 existing_link replay 路径和 first-time link 路径提取为独立 private method，使每个 method 只处理一种核心场景；或至少用显式状态机枚举替换 boolean guard 嵌套。不阻塞当前 merge
- **修复风险（低）**: 纯结构重构，逻辑不变量可被现有 13 个测试保护
- **严重程度（低）**: 不影响正确性，仅影响 maintainability

### 002-未修复-低-replay accepted preview 对 EventLogStore idempotency 的隐式依赖

- **入口/函数**: `EngineEventIngestor._append_iteration_started_events` (L2435-2442)
- **文件(行号)**: `dayu/host/engine_ingest.py:2435-2442`
- **输入场景**: 同一 candidate 重放 (replay) 且 original ingest 已写入 accepted ITERATION_STARTED preview
- **实际分支**: `existing_link is not None && _runner_call_iteration_link_matches==True && resolution.status=="complete"` → `self._append_preview_event(transaction, ...)` → `EventLogStore.append_event()` → `read_event_by_id` 命中已有 row → `event_body_digest` 匹配 → `inserted=False`
- **预期行为**: replay 应返回已有 preview，不产生重复事件
- **实际行为**: 当前依赖 `EventLogStore.append_event` 的同体幂等机制（`event_log.py:338-341`），成功去重。但代码在调用 `_append_preview_event` 前未显式检查 preview 是否已存在，控制流未区分"首次写入"与"幂等返回"两个语义
- **直接证据**: L2435-2441 无条件调用 `self._append_preview_event(transaction, ...)`，无 `_find_existing_preview` 类检查；正确性完全委托给 store 层
- **影响**: 若 `_iteration_started_preview_payload` 或 `_resolution_from_link_event` 的逻辑在写入与重放之间发生变更（例如 hotfix 修改了 preview payload 结构），同 event_id 将遇到不同 body_digest，触发 `HostEventIdentityConflictError`——这是 fail-closed，不会静默写坏数据。当前路径行为正确，但隐式依赖降低代码自明性
- **建议改法和验证点**: 可选：在 `existing_link is not None` 路径先尝试 `read_event_by_id` 查询已有 preview，存在且 body 一致时直接返回；不存在或 body 不一致时再走 append 路径。不阻塞当前 merge
- **修复风险（低）**: 增加一次 read 查询，不影响语义
- **严重程度（低）**: 当前行为正确，只是可维护性改善

## Open Questions

无。

## Residual Risk

- 未检查 `_append_runner_call_iteration_link_event` 对 `_event_id` 的生成规则是否会在跨 execution 边界（同一 attempt 内 execution 切换）时产生冲突。最小实现限定在当前 attempt/execution 范围，该风险低但未在测试中显式覆盖跨 execution replay。
- Tool Trace 当前不投影 link event（实现报告已注明），link event 是 durable truth，未来若 Tool Trace 需要重建 iteration-manifest 映射，需额外实现。这是已知设计选择，非遗漏。
- 未检查 `_runner_call_iteration_link_payload` 构造的 link payload 在 manifest 字段缺失时是否全部 fail-closed（`_manifest_text` / `_manifest_optional_text` 的 raise 行为）。从函数实现看 `_manifest_text` 对缺失必填字段抛出 `HostDurableError`，符合 fail-closed 预期。

## 结论

**ACCEPT**。七个检查点全部通过代码路径追踪验证，未发现阻断性缺陷。两个低严重度发现为 maintainability 建议，不阻塞 merge。
