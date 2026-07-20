# Code Review

## Scope

- Mode: PR
- PR: #180
- Branch: `phaseflow/wu-cli-smoke-01-r1`
- Base: `main`
- Head: `ff5d515a`
- Author: noho
- URL: https://github.com/noho/dayu-agent-r/pull/180
- Draft: yes (confirmed)
- Output file: `docs/reviews/wu-cli-smoke-01-r1-pr-180-review-mimo.md`
- Included scope: PR diff 全部 75 files，8743 insertions，1245 deletions
- Excluded scope: generated/vendor/build 无
- Parallel review coverage: 无（PR 规模可控，单 reviewer 完整覆盖）

## PR Metadata 核验

| 检查项 | 结果 |
|---|---|
| PR title | ✅ `WU-CLI-SMOKE-01-R1: move engine deltas to Host transient live stream` |
| PR body 摘要 | ✅ 准确描述三类 delta 统一为 transient live stream |
| PR body 验证 | ✅ Host/Service/CLI 2816 passed / 8 skipped / 6 deselected |
| PR body Closes footer | ✅ 无（正确，WU 无独立 Issue owner） |
| Draft 状态 | ✅ 仍为 Draft，未意外 request reviewers / mark ready |
| 远端 diff 完整性 | ✅ 包含 accepted plan 两 Slice、aggregate artifacts、最新 control |

## Findings

未发现实质性问题。

### 补充说明（非 blocking，severity=low）

#### 1-未修复-低-api.py 大量纯格式化 reformatting

- **入口/函数**: `dayu/host/api.py` 多处 `__post_init__` 校验
- **文件(行号)**: `dayu/host/api.py` (277-298, 683-698, 917-972, 1016-1073, 1194-1216, 1253-1288, 1692-1790, 2579-2834, 3275-3420, 3572-3598)
- **输入场景**: N/A（格式化变更，不影响运行时行为）
- **实际分支**: N/A
- **预期行为**: 格式化变更应与行为变更分离或在 PR body 中说明
- **实际行为**: ~150 行多行字符串拼接被压缩为单行，穿插在行为变更中
- **直接证据**: 例如 `dayu/host/api.py:288` `"OpenHostOptions.wait_poller_policy.adapter_call_timeout_seconds must be finite"` 从 3 行变为 1 行；同类变更覆盖全文约 40 处
- **影响**: 不影响 correctness / stability；增加 diff 噪声，略微降低 review 信噪比
- **建议改法和验证点**: 未来 PR 可将纯格式化变更与行为变更分离提交
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否

## 关键架构路径逐行走读结论

### 1. HostTransientDeltaHub — identity、fanout、overflow、close

`transient_delta.py:388-509`

- Hub 在构造时分配 UUID runtime identity（`_runtime_id`），每次 publish 分配单调递增 `runtime_sequence`。
- `publish` 取当前 session 快照，对每个 subscription 调用 `_offer`，non-blocking。
- `_offer` 内 `put_nowait` 溢出时标记 `_overflowed = True` 并 detach，不影响快 watcher。
- `close` 遍历所有 subscription 调用 `_close_from_hub`，清空 queue 并 set ready event。
- ✅ identity、fanout、overflow isolation、close 语义正确。

### 2. Terminal fence — 同 Run delta 先于 terminal 交付

`open_host.py:964-1021`

- `_watch_session_events_after` 在交付 durable terminal 前先 `drain_nowait()` 并检查 overflow。
- 对非 PROGRESS event 且有 `run_id` 的 durable event，先 drain → overflow check → `mark_run_terminal(run_id)` → yield。
- 后续 `_offer` 对 `event.run_id in self._terminal_run_ids` 直接 return。
- ✅ terminal fence 正确：delta 前缀先交付，terminal 后不再交付该 Run 的迟到 delta。

### 3. Engine ingest — transient delta 校验与发布隔离

`engine_ingest.py:1038-1048`

- `_is_transient_delta_event` 现在包含三类：CONTENT_DELTA、REASONING_DELTA、TOOL_CALL_DELTA。
- 旧的 `REASONING_DELTA → PREVIEW row` 路径已删除。
- `_accepted_no_event_result` 接收 `ValidatedTransientDeltaCandidate`，events=()。
- `_publish_transient_delta` 在事务提交后发布，try/except 隔离 publisher 异常。
- ✅ 三类 delta 统一走 transient path，不写 EventLog，发布与 durable commit 隔离。

### 4. Service 层 — reasoning-only 投影

`entrypoint_runtime.py:1268-1318`

- `_emit_entrypoint_thinking_from_transient_delta` 用 `assert_never(data)` 穷举类型分支。
- `HostContentDelta` → return（不投影）。
- `HostToolCallDelta` → return（不投影）。
- `HostReasoningDelta` → dedupe → callback。
- ✅ Service 只把 reasoning delta 投影为 thinking，content/tool-call 不越层。

### 5. CLI thinking renderer — runtime_id + runtime_sequence 去重

`cli/thinking.py:87-105`

- 旧 `_last_event_sequence` 改为 `_last_runtime_id` + `_last_runtime_sequence`。
- `runtime_id` 变化时重置 sequence（Host restart 后新 runtime）。
- `runtime_sequence <= _last_runtime_sequence` 时跳过（out-of-order 或 duplicate）。
- ✅ 去重语义从 EventLog event_sequence 切换到 runtime identity + sequence，正确。

### 6. HostThinkingView 完全移除

- `dayu/host/api.py`: 删除 `HostThinkingView` dataclass 及其 `__post_init__` 校验。
- `HostEvent.thinking` 字段已移除。
- `dayu/host/__init__.py`: 从 `__all__` 移除 `HostThinkingView`。
- `dayu/host/read_api.py`: 无 `HostThinkingView` 残留。
- `dayu/service/entrypoint_runtime.py`: 无 `HostThinkingView` 残留。
- ✅ 无兼容 shim，clean removal。

### 7. HostSessionEvent public union

`api.py:3499`

- `HostSessionEvent: TypeAlias = HostEvent | HostTransientDelta`
- `Host.watch_session_events` 返回 `AsyncIterator[HostSessionEvent]`
- ✅ Service 只消费 Host public union，不穿透到内部实现。

### 8. Composition root — hub 生命周期

`open_host.py:1460-1549`

- `HostTransientDeltaHub()` 在 `open_host` 内创建。
- 传给 `HostDispatchScheduler.open(transient_delta_publisher=transient_delta_hub)`。
- 传给 `_PublicHostHandle(transient_delta_hub=transient_delta_hub)`。
- `_close_owned_resources` 首先 `self._transient_delta_hub.close()`（先于 actor drain）。
- ✅ hub 生命周期与 Host runtime 一致，close 顺序正确。

## Open Questions

无。

## Residual Risk

1. **PR body 格式化混杂**: ~150 行纯格式化 reformatting 穿插在行为变更中，增加 diff 噪声但不影响 correctness。未来 PR 建议分离。
2. **stress test 默认排除**: 3×1000 stress 测试标记为 `pytest.mark.stress`，默认 CI 不运行。已由 controller validation 独立复跑确认。
3. **transient delta 容量 256 为内部安全值**: 不暴露为 public knob，未来可能需要按场景调优。当前值对生产足够。

## 结论

**PASS，0 blocking finding，不需要 current fix。**

PR 远端 diff 完整包含 accepted plan 两 Slice、aggregate artifacts 与最新 control。三类 delta（content/reasoning/tool-call）统一走 Host-owned transient live stream，不写 EventLog；terminal fence、slow-consumer isolation、multi-watcher fanout、detach/close 语义均正确实现。Host→Service→CLI public union 边界清晰，`HostThinkingView` clean removal 无兼容 shim。PR body 准确、无错误 Closes footer、仍为 Draft 状态。测试覆盖充分（2816 passed，90.96% owner coverage，3×1000 stress passed）。
