# Phase 13 Aggregate Fix Re-Review — AgentDS

**Date**: 2026-05-29
**Reviewer**: AgentDS
**Target**: 当前未提交 aggregate fix diff（F001 修复）
**Upstream Reviews**:
- Controller adjudication: `docs/reviews/phase13-aggregate-deepreview-controller-adjudication-20260529.md`
- Codex fix: `docs/reviews/phase13-aggregate-fix-codex-20260529.md`
- Original MiMo aggregate: `docs/reviews/phase13-aggregate-deepreview-mimo-20260529.md`
- Original DS aggregate: `docs/reviews/phase13-aggregate-deepreview-ds-20260529.md`

## Verdict: PASS

F001 已修复，无新增 blocking findings，无新增 non-blocking findings。

---

## 1. F001 — 确认已修复

### 1.1 import boundary 检查

| 检查项 | read_api.py | 结果 |
|--------|------------|------|
| `import dayu.host.durable.projection` | 不存在 | PASS |
| `from dayu.host.durable.projection import ...` | 不存在 | PASS |
| 引用 `ProjectionCheckpointRow` | 不存在 | PASS |
| 引用 `read_projection_checkpoint` | 不存在 | PASS |
| 引用 `read_projection_failure` | 不存在 | PASS |

原 MiMo F001 指出的 `dayu/host/read_api.py:53-57` 四行 `durable.projection` 导入已全部移除。当前 read_api.py 的 durable 依赖仅来自 `dayu.host.durable.{outbox, event_log, payload, state, transaction, codec, errors}` —— 全部是 read facade 合法依赖层。

### 1.2 import boundary 测试通过

```
pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth -q
→ 1 passed
```

该测试明确禁止 `dayu.host.durable.projection` 出现在 read_api 的模块导入图中，当前通过。

---

## 2. projection state 读取职责下沉验证

### 2.1 durable outbox helper — 正确承担职责

`dayu/host/durable/outbox.py` 新增 `read_outbox_terminal_projection_state(...)`（line 364），是 public outbox read / drain API 访问 projection checkpoint 与 failure row 的唯一 durable 入口。

下沉合理性：
- `outbox.py` 已经是 Outbox terminal durable owner（terminal item 读写、drain、idempotency 均在此模块）。
- `outbox.py` 作为 durable 层模块，import `dayu.host.durable.projection` 是合法的层内依赖，不跨越分层边界。
- 该 helper 只读取 projection-owned 状态（checkpoint、failure）和 EventLog 水位，不读写 Run / Attempt truth，不修改 drain state，职责单一。

### 2.2 read_api.py — 只调用 outbox durable helper

`_ReadOutboxTerminalItemsOperation.__call__` 和 `_DrainOutboxTerminalItemsOperation.__call__` 均改为：

```python
projection_state = _read_outbox_terminal_projection_state(
    transaction,
    OUTBOX_TERMINAL_CONSUMER_ID.value,
    catchup_error=self.catchup_error,
)
```

`read_api.py` 不再直接构造 projection state 逻辑，只负责 durable helper 返回值到 public 类型的映射（`_outbox_batch_from_page` → `_outbox_projection_status_from_durable`）。

### 2.3 删除的 read_api.py 私有代码

| 删除项 | 说明 |
|--------|------|
| `_OutboxCatchupError` dataclass | 替换为 `OutboxTerminalProjectionCatchupError`（来自 outbox.py） |
| `_OutboxProjectionReadState` dataclass | 替换为 `OutboxTerminalProjectionReadState`（来自 outbox.py） |
| `_read_outbox_projection_state(...)` | 替换为 `read_outbox_terminal_projection_state(...)`（来自 outbox.py） |
| `_checkpoint_sequence(...)` | 内联到 outbox.py 的 helper 中 |

全部删除合理，无残留引用。

---

## 3. public API 语义不变验证

### 3.1 Outbox read / drain API 形状

`Host.read_outbox_terminal_items` 和 `Host.drain_outbox_terminal_items` 的签名未变。`OutboxTerminalItemsBatch` 的字段未变。`OutboxProjectionStatus` enum 值未变（`CAUGHT_UP` / `LAGGED` / `FAILED`）。

### 3.2 projection_status 语义

CAUGHT_UP / LAGGED / FAILED 的判断逻辑从未变——只是执行位置从 `read_api.py` 移到 `outbox.py`。判断规则一致：
- catchup_error 非空 → FAILED
- failure row 存在 → FAILED
- checkpoint < EventLog watermark → LAGGED
- 否则 → CAUGHT_UP

### 3.3 watch_session_events

`git diff HEAD -- dayu/host/api.py | grep watch_session_events` 无输出。`dayu/host/open_host.py` 的 `watch_session_events` 无变更。确认 live-only 语义不变。

### 3.4 EventLog / Run / Attempt 边界

本次 diff 未修改 EventLog append、Run / Attempt terminal transaction、payload reader。`outbox.py` 的 `read_outbox_terminal_projection_state` 只读 EventLog watermark（`SELECT MAX(event_sequence)`），不写 EventLog，不读写 Run/Attempt。

---

## 4. 新增 durable helper 类型质量审查

### 4.1 新增类型

| 类型 | 定义 | 字段类型 | 结果 |
|------|------|----------|------|
| `OutboxTerminalProjectionStatus` | `StrEnum` | `caught_up`, `lagged`, `failed` | PASS |
| `OutboxTerminalProjectionCatchupError` | `@dataclass(frozen=True, slots=True)` | `str`, `str` | PASS |
| `OutboxTerminalProjectionReadState` | `@dataclass(frozen=True, slots=True)` | `int`, `OutboxTerminalProjectionStatus`, `str \| None`, `str \| None` | PASS |

### 4.2 函数签名

| 函数 | 参数类型 | 返回类型 | 结果 |
|------|----------|----------|------|
| `read_outbox_terminal_projection_state` | `HostTransaction`, `str`, `OutboxTerminalProjectionCatchupError \| None` | `OutboxTerminalProjectionReadState` | PASS |
| `_latest_event_sequence` (outbox.py) | `HostTransaction` | `int` | PASS |
| `_outbox_projection_status_from_durable` (read_api.py) | `OutboxTerminalProjectionStatus` | `OutboxProjectionStatus` | PASS |

### 4.3 硬约束检查

| 约束 | outbox.py 新增 | read_api.py 新增 | 结果 |
|------|---------------|-----------------|------|
| 无 `Any` | 0 处 | 0 处 | PASS |
| 无 `: object` | 0 处 | 0 处 | PASS |
| 无 `getattr` / `hasattr` | 0 处 | 0 处 | PASS |
| 中文 docstring（`:param`/`:returns`/`:raises`） | 完整 | 完整 | PASS |
| 无魔法数字/字符串 | 无新增 | 无新增 | PASS |
| frozen + slots dataclass | 是 | 是 | PASS |

---

## 5. 验证结果汇总

```
pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth
  → 2 passed (import boundary + fanout truth boundary)

pytest (import_boundary + public_outbox_api + public_offline_outbox_smoke + outbox_durable)
  → 10 passed in 0.47s

pytest (full aggregate host suite, 15 test files)
  → 108 passed in 2.08s

python -m pyright dayu/host tests/host
  → 0 errors, 0 warnings, 0 informations

git diff --check
  → clean
```

---

## 6. Residual Risks

无新增 residual risk。以下为已有 residual（owner 不变）：

| Risk | Owner |
|------|-------|
| Tool Trace cold JSONL marker-first crash 窗口可能导致缺失行（与 Audit cold-first 模式不一致） | Phase 15 |
| JSONL/SQLite 跨介质 exactly-once | Phase 15 |
| Outbox drain ≠ channel delivery success | Phase 14/15 Service |
| `_latest_event_sequence` 在 `read_api.py` 和 `outbox.py` 各有一份实现（同语义，不同调用方） | 低优先级，后续可考虑提取到公共 durable helper |

---

## 7. README 同步判断

本次只调整内部 durable helper 归属，public API、Outbox read/drain 行为、projection status 语义均未变化。`dayu/host/README.md` 中的稳定边界表述无需更新。与 Codex fix 报告的 docs decision 一致。

---

## 8. Finding Summary

**F001 → FIXED**。`read_api.py` 不再 import `dayu.host.durable.projection`，projection state 读取正确下沉到 `dayu/host/durable/outbox.py`。

**无新增 blocking findings。无新增 non-blocking findings。**

**Verdict: PASS。**
