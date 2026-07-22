# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Code Re-Review

## Scope

- Mode: re-review after Codex fix
- Gate: `code-rereview-slice-1`
- Base: `33af05fa`（accepted plan amendment commit）
- Fix artifact: `docs/reviews/wu-host-session-event-delivery-01-slice1-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-host-session-event-delivery-01-slice1-code-review-controller-adjudication.md`
- 原 review（本人）: `docs/reviews/code-review-20260721-203720.md`
- 未读取 AgentDS 的原 review 或本轮 artifact，保持独立。
- Included scope: `33af05fa` 之后全部 workspace 变更（53 文件），重点审查 Codex fix 修改的 `dayu/host/transient_delta.py` 与 `tests/host/test_transient_delta.py`。
- Excluded scope: `docs/host/issues-implementation-control.md`（Controller bookkeeping）。

## Accepted Finding Closure

### DS-F02 `pop_next_nowait()` 丢失 terminal fence 过滤

**Status: CLOSED**

Controller 裁决为 `accepted-current-fix-required`，严重度为 correctness finding。Codex 在 `HostTransientDeltaSubscription.pop_next_nowait()` 的 single-pop owner boundary 恢复了 terminal fence 过滤。

**修复逻辑验证**（`dayu/host/transient_delta.py:415-436`）：

```python
def pop_next_nowait(self) -> HostTransientDelta | None:
    if self._in_flight is not None:
        raise RuntimeError("subscription in-flight item must be released before pop")
    while self._mailbox:
        event = self._mailbox.popleft()
        if event.run_id in self._terminal_run_ids:
            continue
        self._in_flight = event
        self._refresh_readiness()
        return event
    self._refresh_readiness()
    return None
```

逐项验证：

1. **stale item 不进入 in-flight**：`event.run_id in self._terminal_run_ids` 命中时 `continue`，item 已从 mailbox 移除但不赋值给 `_in_flight`。
2. **retained accounting 正确**：stale item 从 mailbox 移除后 `len(self._mailbox)` 减一，`_in_flight` 未增加，`retained_items` 净减一。这是正确行为——stale item 被丢弃，不再 retained。
3. **pop 不批量返回**：while 循环只在命中 stale 时 continue，首个有效 item 立即赋值 `_in_flight` 并 return。无 batch drain、list/tuple 返回。
4. **readiness 刷新**：无论返回有效 item 还是 `None`，均调用 `_refresh_readiness()`。mailbox 空 + 非 overflow + 非 closed → readiness 清除。
5. **与 `_offer()` fence 一致性**：`_offer()` 在 `event.run_id in self._terminal_run_ids` 时拒绝新 publish；`pop_next_nowait()` 在 pop 时过滤已进入 mailbox 的 stale item。两条路径覆盖 fence 前后两个窗口。

**Deterministic test 验证**（`tests/host/test_transient_delta.py::test_single_pop_filters_prequeued_terminal_stale_item`）：

覆盖两个场景：

- 场景 1：mailbox 预存 Run A stale + Run B valid → mark Run A terminal → pop 返回 Run B，`retained_items` 从 2 变 1。Run A 不被交付。
- 场景 2：mailbox 只预存 Run A stale → mark terminal → pop 返回 `None`，`retained_items` 从 1 变 0，readiness 清除。

红灯证据：Codex 报告修复前 `1 failed`（实际交付 `run-1`），修复后 `1 passed`。

**Adversarial 确认**：

- `_clear_retained_state()` 清空 `_terminal_run_ids`，close 路径正确。
- `_offer()` 在 `_overflowed` 后不再接受新 event，pop 不会遇到 overflow 后新 stale 混入。
- overflow 路径：mailbox 满 → `_offer` 设 `_overflowed=True` + detach fanout → 后续 pop 过滤 stale → mailbox 空时 readiness 仍因 `overflowed` 保持 True → caller 观察 `overflow_error()`。正确。
- `_in_flight` 非空时 pop 抛 RuntimeError，强制 caller 先 release，防止 retained double-count。

**结论**：DS-F02 已在 owner boundary 真正关闭，无回归。

## Adversarial New Finding Check

对 `33af05fa` 后全部 S1 current changes 的 adversarial 扫描，逐项检查：

### 1. Public policy/iterator/error typed contract 与 exports

`api.py` 新增类型定义、`__all__`、`__init__.py` 导出无变化。原 review 结论维持。

### 2. Config → strict parse → assembly → OpenHostOptions → Host owner 效链

`config_loader.py`、`host_runtime.json`、`host_assembly.py` 无变化。原 review 结论维持。

### 3. Transient delivery owner 状态机

`transient_delta.py` 除 DS-F02 fix 外无新增变更。`pop_next_nowait()` 的 stale 过滤逻辑、`release_in_flight()`、`_offer()` prospective check、`_close_from_hub()` 清理、hub `reserve()`/`attach()` 分离——全部与原 review 验证一致，加 DS-F02 fix 补全了 terminal fence。

### 4. Async attach activation boundary

`open_host.py` 无变化。原 review 结论维持。

### 5. Host close ordering

`open_host.py` 无变化。scheduler → delivery hub close 顺序不变。

### 6. Service mechanical propagation

`entrypoint_runtime.py` 无变化。S1 冻结清单内 queue/drain/task 保留原样。

### 7. Utils propagation

4 个 utils 文件无变化。

### 8. Low-card observability、无兼容 shim

无新增 observability 字段或 identity 泄漏。原 review 结论维持。

### 9. Tests 覆盖

DS-F02 fix 新增的 `test_single_pop_filters_prequeued_terminal_stale_item` 是精确 owner-contract test，不引入 mock/fixture 漂移。其余测试从 `drain_nowait()` → `pop_next_nowait()` + `release_in_flight()` 的机械更新正确。

### 10. Adversarial failure/cancellation/concurrency

`pop_next_nowait()` 的 `_in_flight` guard 和 stale 过滤不引入新 race window。原 review 的 cancellation/idempotent release 分析维持。

**结论：无新增 material finding。**

## Open Questions

无。

## Residual Risk

- S2-S4 未实现的 contract（causal fence、terminal port/coordinator、Service relay 删除、exact-five、UI executor）是 accepted 4-slice dependency graph 中已有 owner/destination，不是 S1 缺陷。
- `entrypoint_runtime.py` 中 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY=256` 与 `_drain_host_events` 仍存在——S1 plan 明确冻结，S4 删除。stale scan 命中是预期行为。
- `test_transient_slow_consumer_path.py` 在 S1 仍保留，S4 删除并替换。
- 任意第三方 callback 无限阻塞不具备物理终止保证，沿用 accepted plan 边界。

## Validation Results

| 验证项 | 结果 |
|---|---|
| S1 focused gate（9 文件） | 318 passed, 3 warnings |
| affected suites（host/runtime/service） | 2851 passed, 1 skipped, 6 deselected |
| pyright | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | exit 0 |
| transient_delta coverage | 92.09%（≥80%） |
| stale delivery scan | 仅 S1-frozen `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`（预期） |

## Gate Decision

**PASS**

- DS-F02 已在 `HostTransientDeltaSubscription.pop_next_nowait()` single-pop owner boundary 真正关闭。
- stale item 不进入 in-flight；retained/readiness/overflow/close accounting 无回归。
- deterministic test `test_single_pop_filters_prequeued_terminal_stale_item` 有效覆盖红灯→绿灯路径。
- 全部 S1 current changes 无新增 material finding。
- 建议 Controller accepted-commit Slice 1（需 AgentDS re-review 也 PASS）。
