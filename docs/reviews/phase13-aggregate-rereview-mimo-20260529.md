# Phase 13 Aggregate Re-Review — AgentMiMo

**Reviewer**: AgentMiMo
**Date**: 2026-05-29
**Branch**: `feat/phase-13-audit-trace-outbox`
**Scope**: F001 aggregate fix diff + aggregate fix artifact + original aggregate review artifacts

## Re-Review Inputs

- Fix artifact: `docs/reviews/phase13-aggregate-fix-codex-20260529.md`
- Controller adjudication: `docs/reviews/phase13-aggregate-deepreview-controller-adjudication-20260529.md`
- Original aggregate reviews: `docs/reviews/phase13-aggregate-deepreview-mimo-20260529.md`, `docs/reviews/phase13-aggregate-deepreview-ds-20260529.md`
- Fix diff: `git diff HEAD` (3 files: `dayu/host/durable/outbox.py`, `dayu/host/read_api.py`, `docs/host/implementation-control.md`)

## F001 Verification: `read_api.py` Import Boundary

### Before Fix

`dayu/host/read_api.py` 直接导入 `dayu.host.durable.projection`：
```python
from dayu.host.durable.projection import (
    ProjectionCheckpointRow,
    read_projection_checkpoint,
    read_projection_failure,
)
```
导致 `test_read_api_stream_does_not_reference_projection_or_fanout_truth` 失败。

### After Fix

**`grep` 验证**: `read_api.py` 中不存在任何 `durable.projection` import。✅

修复方案：
1. `dayu/host/durable/outbox.py` 新增 `read_outbox_terminal_projection_state()`，统一读取 checkpoint / failure / EventLog watermark。
2. `dayu/host/read_api.py` 删除 `durable.projection` import，改为调用 `read_outbox_terminal_projection_state`。
3. 原 `_OutboxCatchupError` / `_OutboxProjectionReadState` 私有 dataclass 下沉为 durable helper 的公开类型 `OutboxTerminalProjectionCatchupError` / `OutboxTerminalProjectionReadState`。

**Verdict**: F001 **FIXED**。import boundary 测试通过，root cause（projection state 查询职责错放在 public read facade）已修正。

---

## Projection State 读取职责下沉审查

### `durable/outbox.py` 新增 helper 分析

`read_outbox_terminal_projection_state()` (`durable/outbox.py:364-415`)：

| 检查项 | 结果 |
|--------|------|
| 严格类型签名 | ✅ `transaction: HostTransaction`, `consumer_id: str`, `catchup_error: OutboxTerminalProjectionCatchupError \| None` → `OutboxTerminalProjectionReadState` |
| 中文 docstring 含 `:param` / `:returns` / `:raises` | ✅ |
| 无 `Any` / `object` / 无类型参数 | ✅ |
| 无 `getattr` / `hasattr` | ✅ |
| 只读 projection-owned 状态 + EventLog watermark | ✅ 不写 EventLog，不读写 Run / Attempt |
| `consumer_id` 校验 | ✅ `_require_non_empty_text` |

`_latest_event_sequence()` (`durable/outbox.py:722-738`)：

| 检查项 | 结果 |
|--------|------|
| 严格类型签名 | ✅ `transaction: HostTransaction` → `int` |
| 中文 docstring | ✅ |
| 类型校验 | ✅ `isinstance(latest, int)` + `HostDurableError` |

新增公开类型：
- `OutboxTerminalProjectionStatus` (StrEnum) — ✅ frozen, 中文 docstring
- `OutboxTerminalProjectionCatchupError` (dataclass) — ✅ frozen, slots, 中文 docstring, 严格类型
- `OutboxTerminalProjectionReadState` (dataclass) — ✅ frozen, slots, 中文 docstring, 严格类型

`__all__` 已更新，包含所有新增类型和函数。

### `read_api.py` 修改分析

| 检查项 | 结果 |
|--------|------|
| `durable.projection` import 已移除 | ✅ grep 确认 0 匹配 |
| 调用 `read_outbox_terminal_projection_state` 替代直接读取 | ✅ |
| `OUTBOX_TERMINAL_CONSUMER_ID.value` 显式传入 | ✅ |
| `_OutboxCatchupError` → `OutboxTerminalProjectionCatchupError` | ✅ 类型替换 |
| `_OutboxProjectionReadState` → `OutboxTerminalProjectionReadState` | ✅ 类型替换 |
| durable status → public status 映射 | ✅ 新增 `_outbox_projection_status_from_durable()` |

---

## Public API / 语义边界不变性验证

| 检查项 | 结果 |
|--------|------|
| `OutboxProjectionStatus` (public enum) | ✅ 未修改，`CAUGHT_UP` / `LAGGED` / `FAILED` 语义不变 |
| `OutboxTerminalCursor` | ✅ 未修改 |
| `OutboxTerminalItem` | ✅ 未修改 |
| `ReadOutboxTerminalItemsRequest` | ✅ 未修改 |
| `DrainOutboxTerminalItemsRequest` | ✅ 未修改 |
| `OutboxTerminalItemsBatch` | ✅ 未修改 |
| `Host.read_outbox_terminal_items` Protocol 签名 | ✅ 未修改 |
| `Host.drain_outbox_terminal_items` Protocol 签名 | ✅ 未修改 |
| `watch_session_events` (live-only) | ✅ 未触碰 |
| `EventLog` / `Run` / `Attempt` 边界 | ✅ 未修改 |

---

## Aggregate Validation（独立复跑）

| Gate | 命令 | 结果 |
|------|------|------|
| Import boundary + public outbox + durable outbox | `pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_outbox_durable.py -q` | **10 passed in 0.45s** ✅ |
| Aggregate host suite (15 files) | `pytest tests/host/test_audit_sink.py ... tests/host/test_import_boundary.py -q` | **108 passed in 2.09s** ✅ |
| pyright | `python -m pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** ✅ |
| git diff --check | `git diff --check` | **passed (clean)** ✅ |

---

## 编码硬约束检查（新增 durable helper）

| 约束 | 状态 |
|------|------|
| 严格类型、无 Any/object/无类型签名 | ✅ |
| 中文 docstring | ✅ |
| 无 getattr/hasattr 逃避类型 | ✅ |
| 无魔法字符串扩散 | ✅ SQL 字面量属于 schema DDL 例外 |
| 无反向依赖 | ✅ durable helper 不依赖 read_api |
| frozen + slots dataclass | ✅ 全部新增类型 |

---

## Non-blocking Observations

### NB-01: `read_api.py` 与 `durable/outbox.py` 存在 `_latest_event_sequence` 重复实现

`read_api.py:558` 和 `durable/outbox.py:722` 各有一份 `_latest_event_sequence(transaction) -> int`，函数体完全相同。

- `read_api.py` 的副本在修复前就存在（供 `_SessionLiveEventStartCursorOperation` 使用，line 318）。
- `durable/outbox.py` 的副本是本次 fix 新增的（供 `read_outbox_terminal_projection_state` 使用，line 403）。

两份副本各自服务不同模块的私有需求，且 `read_api.py` 不能 import `durable.outbox` 的私有函数。这属于 `durable` helper 封装 projection 读取后带来的合理副本——将 `read_api.py` 的 `_latest_event_sequence` 也下沉到 `durable/outbox.py` 并暴露为公开 API 会过度扩大 durable helper 的职责边界（它只应服务于 outbox projection），因此当前副本是可接受的。

**Severity**: LOW (non-blocking)
**Owner**: 不需要立即修复；若未来多个 facade 需要 EventLog watermark，可在 `durable/state.py` 或 `durable/event_log.py` 中提取为 shared helper。

### NB-02: `read_api.py` 模块 docstring 对 Outbox 函数的描述略有偏差

模块 docstring 声称 "读取路径不使用 projection checkpoint、内存订阅位置、outbox state 或 session-local cursor"。但 `read_outbox_terminal_items` 和 `drain_outbox_terminal_items` 函数内部确实使用了 projection checkpoint（通过 durable helper 间接访问）。docstring 的本意是 read facade 不直接依赖 projection truth 作为自己的读取源，outbox 函数是新增的 projection-owned 例外。

**Severity**: COSMETIC (non-blocking)
**Owner**: 可在后续 docstring 维护中微调措辞，不影响功能或测试。

---

## Residual Risks（继承自原始 aggregate review，无新增）

| Risk | Owner | Notes |
|------|-------|-------|
| JSONL/SQLite 跨介质 exactly-once crash window | Phase 15 | Audit cold-first 可能重复行，Tool Trace marker-first 可能丢行 |
| Outbox drain ≠ channel delivery success | Phase 14/15 Service 集成 | drain side effect 只属于 projection queue state |
| Phase 15 retention/purge/cleanup | Phase 15 | JSONL、hot SQLite、outbox drained items 清理 |
| Outbox projection lag 导致空结果被误判 | Service 集成时 | `projection_status != CAUGHT_UP` 时调用方必须处理 |

无新增 residual risk。

---

## Verdict

**PASS**

F001 已修复。`read_api.py` 不再 import `dayu.host.durable.projection`，projection state 读取职责已正确下沉到 `dayu/host/durable/outbox.py`。Public Outbox read/drain API 形状、projection status 语义、`watch_session_events` live-only、EventLog/Run/Attempt 边界均未改变。新增 durable helper 严格类型、中文 docstring、无 Any/object/无类型签名、无 getattr/hasattr。全部验证 gate 通过：import boundary 10 passed、aggregate host suite 108 passed、pyright 0 errors、git diff --check clean。无 blocking findings，Phase 13 可进入 `ready-to-open-draft-PR`。
