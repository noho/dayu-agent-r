# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S1 Code Review — AgentDS

## Scope

- **Review target**: S1 working tree changes（10 files, +1289/−463 lines）
- **Plan**: `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- **Implementation artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s1-implementation-codex.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s1-controller-validation.md`
- **Design truth**: `docs/engine/design.md`, `docs/host/design.md`
- **Agent instructions**: `AGENTS.md`
- **Date**: 2026-07-12

## Review Method

按用户指定的 7 个 focus area 逐项做 adversarial review，每项给出直接代码证据与通过/风险判定。

---

## Focus 1: EngineEvent Runtime Validation

### 生产代码检查

**`engine_events.py`** (diff: +92 lines)

- `ENGINE_EVENT_TYPE_TO_DATA` (L547-573): `MappingProxyType` 包裹的 19 个 `EngineEventType → data class` mapping，覆盖全部枚举成员。直接代码证据：`set(EngineEventType) == set(ENGINE_EVENT_TYPE_TO_DATA.keys())` 在 contract test 中自动验证。✅
- `engine_event_type_for_data()` (L577-588): 遍历 mapping，用 `isinstance(data, data_type)` 匹配，复用 RunnerEvent 既有模式。✅
- `validate_engine_event_pairing()` (L591-611): 先校验 `isinstance(event_type, EngineEventType)`，再校验 type/data 一致性。✅
- `EngineEvent.__post_init__()` (L635-643): 调用 `validate_engine_event_pairing(self.type, self.data)` — 唯一构造入口。✅

**不破坏合法 producer 验证**:

- Engine Agent 全部构造点通过 `_make_event(event_type=..., data=...)` 显式配对。`_make_event()` 内部 `EngineEvent(type=event_type, data=data, ...)` 经过 `__post_init__`，所有现有 pairing 已验证正确（154 Engine tests pass）。
- Host `_cancelled_eof_candidate` 构造 `RUN_CANCELLED + RunCancelledData` — 配对正确，事前已验证（plan review 阶段确认）。Host consumer matrix 180 passed。
- **不存在 Host 下游 repair**: `rg -n 'from dayu\.host|import dayu\.host'` 在 4 个生产文件中无命中。Host 不新增 event repair/fallback。

**测试不复制 truth 验证**:

- 旧 `EVENT_TYPE_TO_DATA` 本地 mapping 已从 `test_engine_event_contract.py` 删除。
- 新测试导入 production `ENGINE_EVENT_TYPE_TO_DATA`、`engine_event_type_for_data()`、`validate_engine_event_pairing()`。
- 新增 4 个 contract tests: 全部合法 pair 构造、mismatch rejection、非枚举 discriminator rejection、联合外 data rejection。✅

**判定**: ✅ Pass — 完整且不破坏合法 producer。

---

## Focus 2: AgentMessage Role / AgentRunRequest Union Validation

### 生产代码检查

**`messages.py`** (diff: +80 lines)

- `_validate_message_role()` (L46-67): 私有 helper。`isinstance(role, AgentMessageRole)` + `role is expected_role`（使用 `is` 而非 `==`，正确用于 enum singleton）。✅
- `SystemMessage.__post_init__()` (L81-93): 校验 `SYSTEM`。✅
- `UserMessage.__post_init__()` (L107-119): 校验 `USER`。✅
- `AssistantMessage.__post_init__()` (L158-170): 校验 `ASSISTANT`。✅
- `ToolMessage.__post_init__()` (L186-198): 校验 `TOOL`。✅
- 四种 message 都拒绝 raw string role（`TypeError`）与 wrong enum role（`ValueError`）。✅

**`agent_run.py`** (diff: +21 lines)

- `AgentRunRequest.__post_init__()` (L107-134): 校验 `messages` 中每个元素是 `(SystemMessage, UserMessage, AssistantMessage, ToolMessage)` 联合成员。使用 `isinstance(message, message_types)` 而非字符串类名比较。✅
- 错误类型: 非联合成员 → `TypeError`；空 messages → `ValueError`；attempt_id/execution_id 不成对 → `ValueError`。✅

**下游不承担纠错验证**:

- Agent payload builder、Runner payload builder、Host 无新增 role fallback/repair。
- `rg -n 'from dayu\.host|import dayu\.host'` 无命中。✅

**判定**: ✅ Pass — 在正确 owner 处校验，无下游 repair。

---

## Focus 3: RunnerDone Commit Boundary

### 生产代码检查

核心 race condition 修复在 `_run_runner_iteration()` (L1294-1318):

```
L1305: if self._is_cancelled(): → RUN_CANCELLED + return  # 消费 event 前仍可抢占
L1308: engine_events = self._consume_runner_event(...)     # 消费 event
L1312: yield engine_events
L1314: if state.runner_done is not None: break             # ← 关键：RunnerDone 后立即退出 loop
L1316: if self._is_cancelled(): → RUN_CANCELLED + return  # 只在非 RunnerDone event 后检查
```

**关键修改**:
1. 旧代码在 `_consume_runner_event()` 后（L1306 旧位置）无条件检查取消 ← **已移除**
2. 新代码在消费 event 后先检查 `runner_done is not None` → break（L1314），再检查取消（L1316）
3. RunnerDone event 被消费后，**break 立即终止 loop**，取消检查只在非 RunnerDone event 后生效

**Post-loop commit boundary** (L898):
```python
if self._is_cancelled() and state.runner_done is None:
    yield await self._make_cancelled_terminal_with_close()
    return
```
- `state.runner_done is None` guard 确保 RunnerDone 后取消不抢占。✅

**Force-answer 路径** (L2372): 相同 guard。✅

**`_make_iteration_failure_terminal()`** (L2488):
```python
if state.runner_done is not None:
    return self._make_terminal_failed(failure)  # 不检查取消
return await self._make_failed_or_cancelled_terminal_with_close(failure)  # 检查取消
```
- RunnerDone 后 → 直接提交 RUN_FAILED，不检查取消。✅
- RunnerDone 前 → 检查取消，可抢占。✅

**Tool-call done 路径** (`_execute_tool_batch()` L1920-1964):
- L1920-1948: 先 yield `TOOL_CALLS_BATCH_READY` + 全部 `TOOL_CALL_REQUESTED`。✅
- L1963-1965: **然后**检查取消 → `RUN_CANCELLED`。✅
- tool facts 投影后才允许 cancel handshake 收口。✅

**Pre-done cancellation 保留**:
- L1294-1296: Runner call 前检查取消
- L1305-1307: 消费每个 event 前检查取消
- L1316-1318: 消费非 RunnerDone event 后检查取消
- L898-900: Post-loop 检查取消（仅 runner_done is None）
- 所有 pre-done 路径均保留取消抢占能力。✅

**判定**: ✅ Pass — post-done cancellation 被有效阻止，pre-done cancellation 完整保留。

---

## Focus 4: First Failure Candidate

### 生产代码检查

**`_set_first_failure_candidate()`** (L551-565):
```python
def _set_first_failure_candidate(state, candidate) -> bool:
    if state.failure_candidate is not None:
        return False
    state.failure_candidate = candidate
    return True
```
- 仅当 `failure_candidate is None` 时写入。✅
- `state.failure_candidate =` 出现在 **仅此一处**（L564），scan 确认。✅

**各路径使用情况**:

| 路径 | 位置 | 使用 helper | 证据 |
|------|------|-------------|------|
| protocol error | L1504-1509 | ✅ | `_set_first_failure_candidate(state, RunFailedData(...))` |
| HTTP context overflow | L1571-1580 | ✅ | `_set_first_failure_candidate(state, RunFailedData(...))` |
| HTTP error (non-overflow) | L1555-1560 | ✅ | `_set_first_failure_candidate(state, ...)` |
| malformed finish_reason | L1593-1602 | ✅ | `_set_first_failure_candidate(state, ...)` |
| runner exception | L1359-1368 | ✅ | `candidate_accepted = _set_first_failure_candidate(state, ...)` |

**Runner exception 不覆盖已有 candidate** (L1369-1378):
```python
if not candidate_accepted and state.failure_candidate is not None:
    _LOGGER.warning("engine.agent.runner_exception_preserved_first_failure ...")
```
- 当 protocol/HTTP/context candidate 已存在时，runner exception 只记日志，不覆盖。✅
- 保留原 candidate 的 error_code、provider_request_id、recoverable、client_correlation。✅

**Exception + cancel + no-done 并发** (L1359-1378):
- exception handler 内不直接检查取消。
- 回到外层 `_run_runner_iteration()` 后，`state.runner_done is None` + `_is_cancelled()` 在 L898 被外层 cancel guard 捕获 → `RUN_CANCELLED`。✅
- 这符合 plan 的 "Runner 未完成时取消可抢占"。

**判定**: ✅ Pass — first-candidate helper 是唯一赋值点，exception 不覆盖已有候选。

---

## Focus 5: Invalid/Missing Finish Reason Fail-Closed

### 生产代码检查

**`_consume_runner_event()`** (L1582-1603):
```python
if isinstance(data, RunnerDoneData):
    if not isinstance(data.finish_reason, FinishReason):    # ← 类型守卫
        _LOGGER.error("...runner_done_invalid_finish_reason...")
        _set_first_failure_candidate(state, RunFailedData(
            error_code=_ERROR_RUNNER_ABNORMAL_STOP,
            message=_RUNNER_DONE_INVALID_FINISH_REASON_MESSAGE,
            ...
        ))
        return ()  # 不设置 state.runner_done，不产出 ITERATION_COMPLETED
    state.runner_done = data
    # 产出 ITERATION_COMPLETED...
```
- `cast(FinishReason, None)` 注入的 `data.finish_reason` 不是 `FinishReason` → `isinstance` 返回 False → fail-closed。✅
- 不设置 `runner_done`，不产出 `ITERATION_COMPLETED`。✅

**`_classify_iteration()`** (L1786-1798):
```python
runner_done = state.runner_done
if runner_done is None:
    # 走既有 fail-closed: failure_candidate 或 ABNORMAL_STOP
    ...
finish_reason = runner_done.finish_reason    # ← 直接 typed 读取，无 or STOP
```
- `or FinishReason.STOP` 已完全删除（`rg -n 'or FinishReason\.STOP'` 无命中）。✅
- `runner_done` 非 None 时 `finish_reason` 直接从 typed field 读取，不会出现 `None`。✅

**判定**: ✅ Pass — invalid finish_reason fail-closed，未恢复 STOP fallback。

---

## Focus 6: Host Test Migration

### 测试代码检查 (`tests/host/test_engine_ingest_mapping.py`)

三个迁移的 negative fixtures:

1. **`test_unsupported_engine_event_shape_is_rejected`**:
   - 旧: `EngineEventIngestor.ingest(candidate)` → 断言 `REJECTED` + `unsupported_engine_event_type`
   - 新: `pytest.raises(ValueError, match="type/data mismatch")` 在 `EngineEvent(...)` 构造处
   - ✅ 迁移到 owner boundary — EngineEvent 构造时即失败

2. **`test_transient_delta_event_rejects_missing_or_wrong_data`**:
   - 旧: 2 个 parametrized cases (None data + wrong type data) → Host ingest `REJECTED`
   - 新: 2 个 parametrized cases，分别断言 `TypeError` / `ValueError` 在构造边界
   - ✅ 每个 case 有独立的 `expected_error` 与 `expected_message`

3. **未使用 `object.__new__`**: diff 中无不通过构造器的绕过方式。✅
4. **合法 Host ingest coverage 不变**: 其他 100+ test cases 继续通过 `EngineEvent(...)` 构造合法 event → Host ingest → 断言 consumer 行为。`180 passed` 确认。✅
5. **Host production 未修改**: `dayu/host/` 生产文件不在 diff 中。✅

**判定**: ✅ Pass — 迁移合理，只移至 owner boundary，不削弱 Host coverage。

---

## Focus 7: 无新增 Compat Shim / hasattr/getattr / Loose Parsing / 反向依赖

### Scan 结果

| Scan | 结果 |
|------|------|
| `hasattr(` / `getattr(` in 4 production files | **无命中** |
| `from dayu.host` / `import dayu.host` in 4 production files | **无命中** |
| `loose pars` / `compat shim` / `compat flag` / `allow_dict` / `默认 role` / `兼容` | **无命中** |
| 新增 `object.__new__` | **无使用** |
| 新增 Optional/Any 类型 fallback | **无引入** |
| `state.failure_candidate =` 直接赋值（非 helper） | **无命中**（仅 L564 helper 内一处） |
| `or FinishReason.STOP` | **无命中** |

### README 决策

按 accepted plan：`dayu/engine/README.md`、`tests/README.md`、`docs/engine/design.md` 延至 S3 后统一更新。当前 S1 不修改 README — 符合 plan 的 README trigger decisions。✅

**判定**: ✅ Pass — 无 compat shim、hasattr/getattr、loose parsing、反向依赖。

---

## Additional Adversarial Checks

### 旧 `done_seen`/`finish_reason`/`provider_request_id` 字段残留

- `rg -n 'state\.(done_seen|finish_reason|provider_request_id)' dayu/engine/agent.py` → **无命中** ✅

### `_IterationState` 字段完整性

- 新增字段 `runner_done: RunnerDoneData | None` (L543)
- 删除字段: `done_seen`、`finish_reason`、`provider_request_id`
- 所有旧字段引用已迁移到 `state.runner_done.[attr]` ✅

### 续写轮 `_continuation_tool_call_failure`

- 从 `state.runner_done.finish_reason is FinishReason.TOOL_CALLS` 读取（L1187），有 `is not None` guard (L1186) ✅

### Runner close exactly once

- `_close_runner_once()` 不变，仍在 `_make_cancelled_terminal_with_close()`、`_make_final_after_close()` 等 terminal 方法中调用。✅

### Post-done test methodology

- 实现 artifact 确认 5 个 post-done 测试 + malformed finish_reason 测试 + first-candidate 保留测试 + exception+cancel 并发测试全部通过。✅
- 控制器独立 rerun 确认 8 个 high-risk node ids 全通过。✅

---

## Findings

无。7 个 focus area 全部通过，未发现 material issue。

## Plan Review Finding 验证

原 AgentDS 3 个 findings 在 S1 implementation 中验证：

| Finding | 验证结果 |
|---------|----------|
| DS-F1 (position routing) | → S2 范围，S1 不涉及。**待 S2 review 验证** |
| DS-F2 (exception first-candidate) | → ✅ 已修。`_set_first_failure_candidate` 是唯一赋值点，exception handler 使用 helper |
| DS-F3 (finish_reason fallback) | → ✅ 已修。`or FinishReason.STOP` 删除，`isinstance(data.finish_reason, FinishReason)` 守卫 |

AgentMiMo F1 (post-done tests) → ✅ 已修。5 个 post-done 反例测试全部通过。

---

## Plan Review Conclusion

**Pass** — 0 findings, 0 blocking questions.

**Artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s1-code-review-ds.md`
