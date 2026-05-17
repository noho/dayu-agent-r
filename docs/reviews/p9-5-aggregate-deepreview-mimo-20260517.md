# P9.5 Aggregate Deepreview — AgentMiMo

## Review Context

- Reviewer: AgentMiMo
- Scope: `p9.5-pre-p10-hardening` 全分支 diff against `main`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Method: 并行四路审查（state machine / durable truth / public API / ownership；ToolRuntime / fetch_more；memory catch-up / logging；schema / CHECK / tests gaps），合并后统一出 artifact

## Verdict: PASS

无 blocking finding，无 high finding。1 个 medium、3 个 low、3 个 info/style。均不阻塞 PR 合并。

---

## Findings

### F1 — `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES` 硬编码为默认值，不读取用户配置

**Severity: MEDIUM**

**File:line**: `dayu/host/durable/event_log.py:45`

```python
_MAX_CANONICAL_INLINE_PAYLOAD_BYTES = _DEFAULT_INLINE_PAYLOAD_MAX_BYTES
```

**问题**: 模块级常量在 import 时从 `_DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES`（65536）赋值，之后不再读取 `PayloadStoragePolicy.payload_inline_threshold_bytes` 的用户配置值。若用户通过 `HostCommandHandleOptions.payload_inline_threshold_bytes` 设置了不同的阈值，`EventLogStore._validate_canonical_inline_payload_size` 仍使用 65536。

**影响**: `PayloadStoragePolicy` 的 `payload_inline_threshold_bytes` 配置对 EventLog canonical fact inline 检查无效。当前默认值一致（65536），行为正确，但配置语义被削弱。

**建议修法**: 将 `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES` 改为从 `PayloadStoragePolicy` 实例读取，或在 `EventLogStore` 构造时注入阈值参数。若确认 EventLog 阈值应独立于 `PayloadStoragePolicy`，则在 `_validate_canonical_inline_payload_size` docstring 中明确说明此阈值不随用户配置变化。

---

### F2 — `mark_dispatch_waiting_for_lane_row` 和 `mark_dispatch_worker_accepted_row` WHERE 子句缺少 `cancelled_event_sequence IS NULL` 检查

**Severity: LOW**

**File:line**: `dayu/host/durable/state.py:3076-3095`、`dayu/host/durable/state.py:3233-3247`

**`mark_dispatch_waiting_for_lane_row` WHERE 子句**:
```sql
WHERE attempt_id = ?
  AND status = ?
  AND waiting_for_lane_at IS NULL
  AND lane_name IS NULL
  AND lane_claim_id IS NULL
  AND lane_owner_id IS NULL
  AND lane_acquired_at IS NULL
  AND dispatching_at IS NULL
  AND worker_accept_event_id IS NULL
  AND cancelled_event_id IS NULL
  -- 缺少: AND cancelled_event_sequence IS NULL
```

**`mark_dispatch_worker_accepted_row` WHERE 子句**:
```sql
WHERE attempt_id = ?
  AND status = ?
  AND worker_accepted_at IS NULL
  AND worker_accept_event_id IS NULL
  AND worker_accept_event_sequence IS NULL
  AND cancelled_event_id IS NULL
  -- 缺少: AND cancelled_event_sequence IS NULL
```

**对比**: `mark_dispatch_dispatching_row`（line 3165-3184）同时检查 `cancelled_event_id IS NULL` 和 `cancelled_event_sequence IS NULL`。

**影响**: 实际风险极低——`cancelled_event_id` 和 `cancelled_event_sequence` 在 cancel 流程中同时写入（line 3293-3305），只检查 `cancelled_event_id IS NULL` 已能阻止对已取消记录的误操作。但 defense-in-depth 不对称。

**建议修法**: 在 `mark_dispatch_waiting_for_lane_row` 和 `mark_dispatch_worker_accepted_row` 的 WHERE 子句中补充 `AND cancelled_event_sequence IS NULL`。Pre-existing，可放入后续清理。

---

### F3 — `tool_runtime.py:1393-1404` 截断后超过 inline 限制时 cursor 泄漏

**Severity: LOW**

**File:line**: `dayu/host/tool_runtime.py:1393-1404`

```python
if (
    _tool_outcome_inline_size_bytes(truncated_outcome)
    > _MAX_LLM_INLINE_TOOL_RESULT_BYTES
):
    return TruncationAppliedOutcome(
        outcome=_truncation_failure(...),
        cursor_hint=None,  # ← 未清理已创建的 cursor
        fact=None,
    )
```

**问题**: `_apply_truncation` 在成功截断后创建 cursor（通过 `_create_cursor`），但若截断结果仍超过 LLM inline 限制，early return 不清理已创建的 cursor。

**影响**: cursor 残留直到 TTL 过期（`_cleanup_expired_cursors`）。不影响正确性（cursor 不会被引用），但浪费内存。

**建议修法**: 在 early return 前清理 cursor：`self._cursors.pop(truncated_outcome.cursor_id, None)`（若 cursor 已创建）。或移动 cursor 创建到 inline size 检查之后。

---

### F4 — `fetch_more` 先加载完整内容再做 size check

**Severity: LOW**

**File:line**: `dayu/host/tool_runtime.py:1443-1461`

```python
fetched = _fetch_more_value(cursor.remaining_ref, request.limit)  # 先加载
# ...
if (
    _tool_outcome_inline_size_bytes(fetched_outcome)
    > _MAX_LLM_INLINE_TOOL_RESULT_BYTES  # 后检查
):
```

**问题**: `fetch_more` 通过 `_fetch_more_value` 加载完整 `request.limit` 条记录到内存，然后才检查 inline size。若单条记录极大（接近 192KB LLM inline limit），可能加载不必要的大量数据。

**影响**: 当前 `request.limit` 受 `_validate_fetch_more_request` 限制（默认 max 50 条），实际风险低。属于设计权衡——需要先加载才能计算 size。

**建议修法**: 若需要优化，可在 `_fetch_more_value` 中增加 streaming size check 或逐条累加 size 后提前终止。当前实现可接受，标记为设计考量。

---

### F5 — `engine_ingest.py:1682` dead code in `RunSuspendedData` 分支

**Severity: INFO**

**File:line**: `dayu/host/engine_ingest.py:1681-1683`

```python
else:
    # ...
    record = data.awaiting_records[0]
    iteration_id = record.batch_snapshot.iteration_id  # ← 赋值
if record.batch_snapshot.iteration_id != iteration_id:  # ← 永远为 False
    return "awaiting_iteration_mismatch"
```

**问题**: `else` 分支中 `iteration_id` 从 `record.batch_snapshot.iteration_id` 赋值，随后的 `if` 比较同一值，永远为 False。

**影响**: 无功能影响。Pre-existing dead code。

**建议修法**: 删除 line 1682-1683 的 dead check，或添加注释说明保留原因。

---

### F6 — schema v7->v8 无 migration 路径

**Severity: INFO**

**File:line**: `dayu/host/durable/schema.py`（HOST_SCHEMA_VERSION 7->8 变更）

**问题**: `HOST_SCHEMA_VERSION` 从 7 升级到 8，新增 `host_memory_items` 表和 CHECK 约束，但无 migration 路径。

**影响**: 无。这是有意设计——项目约束明确要求"按全新 schema 起库处理；禁止旧库兼容读取"。

**判定**: 符合项目 schema 变更约束，无需修改。

---

### F7 — `event_log.py:46` 缺少空行（PEP 8 E302）

**Severity: STYLE**

**File:line**: `dayu/host/durable/event_log.py:45-46`

```python
_MAX_CANONICAL_INLINE_PAYLOAD_BYTES = _DEFAULT_INLINE_PAYLOAD_MAX_BYTES
class EventClass(StrEnum):
```

**问题**: 赋值语句与 class 定义之间缺少 PEP 8 E302 要求的两个空行。

**建议修法**: 在 line 45 和 line 46 之间插入一个空行。

---

## Verified Clean Areas

以下区域经并行四路审查确认无问题：

### State Machine / Durable Truth
- dispatch 状态机（PENDING -> WAITING_FOR_LANE -> DISPATCHING -> accepted/terminal）正确
- `run_attempt_transitions.py` 中所有状态转换有正确的 WHERE 守卫
- `resolve_wait` 原子 resume / terminal closeout 正确
- terminal duplicate promotion retry 正确
- EventLog append 幂等 / 冲突检测正确

### ToolRuntime / fetch_more
- `EffectiveToolBundle` attempt-local 隔离正确（frozen dataclass，fresh TruncationManager per factory call）
- `FetchMoreToolCallable` 不跨 attempt 共享
- `ToolRuntimeHandle.__post_init__` 强制 `tool_schemas` 来自 `effective_bundle`
- `tool_runtime_schema_projection.py` 不引入 `ToolCallable` 或 runtime 类型
- accept barrier validators 正确

### Memory Catch-up
- `ConversationMemoryProjectionCatchupPort` 注入正确
- `current_goal` first-write-wins 语义正确
- 三个 post-commit catch-up 路径（admission、tool fact、resolve_wait）正确
- catch-up 失败只记录 WARNING，不阻塞主流程
- memory 模块不导入 Engine / Service / UI / Fins

### Logging Redaction
- 所有新增日志使用 opaque IDs（session_id、run_id、attempt_id、sequence）
- 无完整 prompt / tool args / tool results 泄漏
- 日志级别符合 `dayu/README.md` 定义（VERBOSE=15、DEBUG=10、WARNING、ERROR、CRITICAL）
- projection catch-up 失败使用 WARNING（正确——可恢复失败）

### Import Boundaries / Ownership
- Engine 不导入 Host / ToolCallable / ToolBundle / ToolDefinition / dayu.runtime
- Host 不导入 Service / UI / Fins
- Contracts 不导入 runtime implementation
- `fetch_more` 只在 `tool_runtime.py` 和 `tooling.py` 中
- Host 不使用 `importlib` / `pkgutil` 扫描业务工具模块
- `dayu.runtime` 不导入 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`

### Public API / Exports
- `dayu.host.__all__` 和 `dayu.host.api.__all__` 白名单稳定
- `dayu.engine.__all__` 稳定
- `start_run` / `submit_followup` / `resolve_wait` 签名稳定
- `_host_api_error_from_durable_error` 映射完整

### Schema / CHECK
- `host_memory_items` 和 `host_event_log` 的 `payload_ref` / `payload_digest` CHECK 约束正确
- `_payload_digest_for_verified_fact` 在 `payload_ref is None` 时返回 None，满足 CHECK 约束
- schema 版本号正确递增

### Tests Coverage
- 1066 tests passed，0 pyright errors
- import boundary tests 覆盖所有层
- memory projection tests 覆盖 first-write-wins / catch-up / boundary
- accept barrier tests 覆盖 concrete catch-up / logging
- effective bundle tests 覆盖 attempt-local isolation

---

## Summary

| Finding | File:line | Description | Severity |
|---------|-----------|-------------|----------|
| F1 | `event_log.py:45` | `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES` 硬编码为默认值 | MEDIUM |
| F2 | `state.py:3076,3233` | WHERE 子句缺少 `cancelled_event_sequence IS NULL` | LOW |
| F3 | `tool_runtime.py:1393-1404` | 截断后超限 cursor 泄漏 | LOW |
| F4 | `tool_runtime.py:1443-1461` | fetch_more 先加载再检查 size | LOW |
| F5 | `engine_ingest.py:1682` | Dead code in RunSuspendedData 分支 | INFO |
| F6 | `schema.py` | v7->v8 无 migration（有意设计） | INFO |
| F7 | `event_log.py:46` | 缺少空行 | STYLE |

## 结论

P9.5 分支 diff 质量高，架构边界正确，状态机守卫完整，public API 稳定，memory catch-up 隔离正确，日志无敏感数据泄漏。1 个 medium finding（hardcoded payload threshold）不影响当前行为（默认值一致），建议后续清理。3 个 low findings 均为 defense-in-depth 或设计权衡，不阻塞合并。可以进入 PR 流程。
