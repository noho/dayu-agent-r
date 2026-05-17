# P9-S1 Durable Memory Contracts and Schema — Code Re-Review (AgentDS)

**Artifact**: `docs/reviews/p9-s1-code-rereview-ds-20260517.md`
**Reviewer**: AgentDS
**Date**: 2026-05-17
**Branch**: `feat/host-p9-conversation-memory`
**Previous DS artifact**: `docs/reviews/p9-s1-code-review-ds-20260517.md`
**Previous MiMo artifact**: `docs/reviews/p9-s1-code-review-mimo-20260517.md`
**MiMo re-review**: `docs/reviews/p9-s1-code-rereview-mimo-20260517.md`
**Scope**: Updated `dayu/host/memory.py` and `tests/host/test_memory_projection.py` fixing DS C2 + MiMo B1 + MiMo N2

---

## 1. 独立验证结果

```bash
pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py = 21 passed (原 20)
pyright dayu/host/memory.py tests/host/test_memory_projection.py = 0 errors
```

---

## 2. Accepted Finding 修复验证

### 2.1 DS C2 / MiMo B1: Snapshot digest 包含非确定性字段 — 已修复

**原问题**：`_snapshot_digest_json_value` 通过 `memory_diagnostic_to_json_value` 将 `diagnostic_id` 和 `recorded_at` 纳入 digest input，违反 plan §4.7 "非确定性字段不得进入 digest input"。

**修复手段**：
1. 新增 `_memory_diagnostic_digest_json_value`（`memory.py:829-844`），只包含稳定语义字段：
   - `reason`（enum value）
   - `message`（diagnostic 文本）
   - `event_sequence`（EventLog 序列号）
   - `item_id`（关联 memory item id）
   - `policy_digest`（policy digest）
   - 排除：`diagnostic_id`、`recorded_at`

2. `_snapshot_digest_json_value`（`memory.py:813`）改为调用 `_memory_diagnostic_digest_json_value` 替代 `memory_diagnostic_to_json_value`

3. Docstring 已同步更新：
   - `calculate_memory_snapshot_digest`（line 594-596）：明确排除 `diagnostic_id` / `recorded_at`
   - `ConversationMemorySnapshot.snapshot_digest`（line 532-533）：注明排除 diagnostic id / recorded time
   - `_snapshot_digest_json_value`（line 797-801）：诊断只纳入稳定语义字段

**验证**：`memory_diagnostic_to_json_value`（line 727-735）仍保留 `diagnostic_id` 和 `recorded_at`，用于 durable 存储序列化。digest 计算与 durable 存储使用不同序列化路径，职责分离正确。

**Verdict**: DS C2 / MiMo B1 RESOLVED。

### 2.2 MiMo N2: 缺失 ConversationContinuityItem claim status 拒绝测试 — 已修复

**原问题**：`test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` 仅测试了 `WorkingAssumptionView` 拒绝 `CONFLICTED` 和 `ConversationContinuityItem` 拒绝 `STALE`，未覆盖全部 3×2 组合。

**修复手段**：测试（`test_memory_projection.py:571-609`）改为遍历 `reserved_statuses = (CONFLICTED, STALE, SUPERSEDED)`，对每个 status 分别测试：
- `WorkingAssumptionView` 拒绝（3 个测试用例）
- `ConversationContinuityItem` 拒绝（3 个测试用例）

共 6 个 pytest.raises(ValueError) 断言。

**Verdict**: MiMo N2 RESOLVED。

### 2.3 新增测试 `test_snapshot_digest_ignores_nondeterministic_diagnostic_fields`

**位置**: `tests/host/test_memory_projection.py:505-568`

**测试逻辑**：
- 构造两个 snapshot，其 semantic content 完全一致（相同的 `session_id`、`cursor`、`policy_digest`、`pinned_state`、`diagnostic.reason`、`diagnostic.message` 等）
- 差异仅在于非确定性字段：`snapshot_id`（"snapshot-1" vs "snapshot-2"）、`built_at`（前后两天）、`diagnostic.diagnostic_id`（"diagnostic-a" vs "diagnostic-b"）、`diagnostic.recorded_at`（前后两天）
- 断言 `calculate_memory_snapshot_digest(first) == calculate_memory_snapshot_digest(second)`

**验证通过**：测试正确覆盖了有 diagnostic 时的 digest 稳定性场景（原测试 `test_empty_event_log_snapshot_can_be_created_and_read` 的 snapshot diagnostics 为空 tuple，无法触发 B1）。

---

## 3. 未修复的 DS Findings 状态回顾

| ID | 描述 | 当前状态 |
|----|------|---------|
| C1 (MEDIUM) | `producer_name` 对非 TOOL producer 语义不精确 | 未修复，属 `durable/memory.py`，不在本次 scope。可延至 Slice 2 |
| C3 (LOW) | `_optional_str/int` 字段缺失时报错信息不够精确 | 未修复，边缘场景 |
| S3 (LOW) | `build_empty_conversation_memory_snapshot` 双实例构造 | 未修复，维护性优化 |
| A1 (LOW) | Snapshot upsert 不检测并发覆盖 | 未修复，属 `durable/memory.py` |
| T1 (LOW) | `cast()` 缺少注释 | 未修复，不影响功能 |
| M1 (MEDIUM) | `MemoryClaimStatus` 6 值仅 2 个在 S1 使用 | 设计决策，非缺陷 |

**结论**：剩余的 DS low/medium findings 均不威胁 correctness 或 stability，不阻塞 Slice 1 推进。

---

## 4. 新引入问题检查

### 4.1 `_memory_diagnostic_digest_json_value` 字段完整性

检查 `MemoryDiagnostic` 所有字段的稳定性分类：

| 字段 | 稳定性 | digest 纳入？ |
|------|--------|--------------|
| `diagnostic_id` | 非确定（每次生成唯一 id） | 排除 ✅ |
| `reason` | 确定（enum value） | 纳入 ✅ |
| `message` | 确定（与 projection state 绑定） | 纳入 ✅ |
| `event_sequence` | 确定（EventLog sequence） | 纳入 ✅ |
| `item_id` | 确定（memory item id） | 纳入 ✅ |
| `policy_digest` | 确定（policy content 决定） | 纳入 ✅ |
| `recorded_at` | 非确定（写入时间） | 排除 ✅ |

无遗漏。✅

### 4.2 两层序列化路径分离

- `memory_diagnostic_to_json_value`（line 720-735）：完整 durable 序列化，含 `diagnostic_id`、`recorded_at` — 用于 `conversation_memory_snapshot_to_json_value` 的 durable storage 路径 ✅
- `_memory_diagnostic_digest_json_value`（line 829-844）：digest 专用序列化，不含 `diagnostic_id`、`recorded_at` — 用于 `_snapshot_digest_json_value` 的 digest 计算路径 ✅
- `memory_diagnostic_from_json_value`（line 777-794）：完整反序列化，恢复所有字段 — 用于 `conversation_memory_snapshot_from_json_value` 的 durable read 路径 ✅

三层函数各司其职，无职责混淆。✅

### 4.3 新增测试的正确性

`test_snapshot_digest_ignores_nondeterministic_diagnostic_fields` 中的两个 snapshot：
- 共享同一个 `cursor` 对象（`first.cursor`）、`pinned_state` 对象（`first.pinned_state`）、`conversation_continuity` 对象
- diagnostic 共享相同的 `reason`、`message`、`event_sequence`、`item_id`、`policy_digest`
- 仅 `snapshot_id`、`built_at`、`diagnostic.diagnostic_id`、`diagnostic.recorded_at` 不同
- 断言 digest 相等

测试逻辑正确，覆盖了 B1 根因场景。✅

### 4.4 无新 type / import / boundary 问题

- 新增函数 `_memory_diagnostic_digest_json_value` 使用已有 `JsonValue` 类型，无新 import
- 函数签名为 `(MemoryDiagnostic) -> JsonValue`，类型严格
- 仍无 `Any`/`object`/untyped signature
- Host boundary 未变化

---

## 5. Scope 边界再确认

本次修复仅触及 `dayu/host/memory.py` 和 `tests/host/test_memory_projection.py`，均在 Slice 1 allowed files 范围内。未越界到：

- Projection consumer（Slice 2）
- RunInputBuilder / MemorySnapshotProvider（Slice 3）
- Repair / catch-up / rebuild（Slice 4）
- `dayu/host/durable/memory.py`（C1/A1 仍在待办）

✅

---

## 6. 求值

**Previous DS verdict**: PASS with findings (0 blocking, 3 medium, 3 low, 2 info)
**Current DS verdict**: PASS (0 blocking)

### 已修复

| 原 Finding | 状态 |
|-----------|------|
| DS C2 (MEDIUM) — digest 与 docstring 不一致 | RESOLVED |
| MiMo B1 (BLOCKING) — digest 包含 `recorded_at` | RESOLVED (同 DS C2 root) |
| MiMo N2 — 缺失 claim status 拒绝测试 | RESOLVED |

### 仍 Open（非 blocking）

| Finding | Severity | 建议处理时机 |
|---------|----------|------------|
| DS C1 — `producer_name` 语义不精确 | MEDIUM | Slice 2 |
| DS C3 — `_optional_str/int` 报错信息 | LOW | 后续优化 |
| DS S3 — 双实例构造 | LOW | 后续优化 |
| DS A1 — upsert 并发 | LOW | Slice 2/4 |
| DS T1 — `cast()` 注释 | LOW | 后续优化 |
| MiMo N1 — reason 命名差异 | LOW | Slice 2 前稳定 |
| MiMo N3 — `recorded_at` type surface | LOW | 后续优化 |

### Remaining Blocking Findings Count

**0**

---

## 7. 裁决

**Verdict: PASS** — 所有 accepted blocking/medium findings (DS C2 / MiMo B1 / MiMo N2) 已正确修复。Snapshot digest 现在排除 `diagnostic_id` 和 `recorded_at`，测试覆盖确定性 diagnostic digest 场景。无新 blocking issue 引入。21 tests passed，pyright 0 errors。

P9-S1 可安全推进到 Slice 2。
