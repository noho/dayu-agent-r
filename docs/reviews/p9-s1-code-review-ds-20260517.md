# P9-S1 Durable Memory Contracts and Schema — Code Review (AgentDS)

**Artifact**: `docs/reviews/p9-s1-code-review-ds-20260517.md`
**Reviewer**: AgentDS
**Date**: 2026-05-17
**Branch**: `feat/host-p9-conversation-memory`
**Scope**: P9 Slice 1 workspace changes
**Design truth**: `docs/host/design.md` §23/§24/§26
**Control truth**: `docs/host/implementation-control.md` Phase 9
**Plan truth**: `docs/host/phase9-conversation-memory-plan.md` Slice 1
**Verdict**: PASS with findings (0 blocking, 3 medium, 3 low, 2 info)

---

## 审查材料

| File | Role |
|------|------|
| `dayu/host/memory.py` | Typed contracts, enums, digest/JSON helpers |
| `dayu/host/durable/memory.py` | Transaction-scoped durable read/write primitives |
| `dayu/host/durable/schema.py` | Schema v6 DDL with 3 memory tables |
| `tests/host/test_memory_projection.py` | Contract & durable behavior tests |
| `tests/host/test_durable_schema.py` | Schema bootstrap & constraint tests |
| `docs/host/implementation-control.md` (P9 section) | Phase 9 status tracking |

---

## 1. Slice 1 Scope 边界审查

### ✅ 已实现（在 Slice 1 范围内）

- Memory typed contracts 完整：7 个 enum、12 个 dataclass、8 个 public helper function
- Durable schema v6：`host_memory_snapshots`、`host_memory_items`、`host_memory_diagnostics` 三表，含 CHECK、FK、index
- Transaction-scoped read/write：`write_memory_snapshot`、`write_memory_snapshot_with_checkpoint`、`read_memory_snapshot`、`read_latest_memory_snapshot`
- Diagnostic 独立读写：`write_memory_diagnostic`、`read_memory_diagnostic`
- Fresh bootstrap：`HOST_SCHEMA_VERSION = 6`，幂等 bootstrap，非当前版本抛 `HostSchemaMismatchError`
- Digest 基础设施：`digest_memory_projection_policy`、`calculate_memory_snapshot_digest`，均基于 `sha256_digest_json` + canonical JSON

### ✅ 未越界（确认不包含在 Slice 1 中）

- 无 `ConversationMemoryProjectionConsumer`（属 Slice 2）
- 无 `DurableMemorySnapshotProvider` / `MemorySnapshotProvider`（属 Slice 3）
- 无 `RunInputBuilder` 接线（属 Slice 3）
- 无 projection repair / catch-up / rebuild service（属 Slice 4）
- 无 `final_answer` → verified fact 投影逻辑（属 Slice 2）
- 无 stable layer / history pool builder（属 Slice 2）

---

## 2. Correctness 审查

### Finding C1 (MEDIUM): `producer_name` 对非 TOOL producer 存储 `producer_kind.value`，语义不精确

**位置**: `dayu/host/durable/memory.py:418,449`

```python
# _insert_working_assumption_item (line 418)
producer_name=item.producer_kind.value,  # "user"/"assistant"/"host_projection"

# _insert_continuity_item (line 449)
producer_name=item.producer_kind.value,  # 同上
```

**对比** verified fact 的 producer_name（line 388）：
```python
producer_name=item.provenance.producer_name,  # 实际 tool name, e.g. "tool-a"
```

**问题**：`WorkingAssumptionView` 和 `ConversationContinuityItem` 的 typed contract 中只有 `producer_kind: MemoryProducerKind`，没有独立的 `producer_name` 字段。但 durable `host_memory_items` 表要求 `producer_name TEXT NOT NULL`。当前实现用 `producer_kind.value` 填充 `producer_name`，使该列既存储真实 tool name（如 "search_financial_reports"）又存储 kind 值（"user"/"assistant"），下游消费者按 `producer_name` 分组时会混淆。

**根因**：`WorkingAssumptionView` / `ConversationContinuityItem` 的设计未提供 `producer_name` 字段，而 user/assistant 在当前系统中确实没有独立名称标识。

**建议**：在 Slice 2 的 `WorkingAssumptionView` 和 `ConversationContinuityItem` 中补充 `producer_name: str | None`（对应 item_kind 的非 TOOL producer 场景可为 None），并使 durable 写入路径优先使用该字段；若为 None 则回退到 `producer_kind.value`。或在 docs 中明确记录当前行为为有意设计。

**严重性**：MEDIUM — 不影响 Slice 1 功能正确性，但为后续 slice 的消费者做了语义模糊的 durable 列。

---

### Finding C2 (MEDIUM): `_snapshot_digest_json_value` 包含所有 diagnostics，与 docstring 不一致

**位置**: `dayu/host/memory.py:795-821` vs `dayu/host/memory.py:591-600`

Docstring（line 591-600）：
```
digest 覆盖 cursor、policy digest、四类 view 与影响 message 的 diagnostics；
不包含 ``snapshot_id``、``built_at`` 与 ``snapshot_digest``。
```

实现（line 795-821）：
```python
def _snapshot_digest_json_value(snapshot):
    return {
        ...
        "diagnostics": [memory_diagnostic_to_json_value(d) for d in snapshot.diagnostics],
        ...
    }
```

**问题**：docstring 声称只包含“影响 message 的 diagnostics”，但实现将 ALL diagnostics 纳入 digest。在 Slice 1 所有 diagnostics 都可能是 message-affecting（如 `EMPTY_EVENT_LOG_SNAPSHOT`），所以当前无功能错误。但后续 slice 可能产生纯观测型 diagnostic（如仅用于 trace 的记录），这类 diagnostic 不应改变 digest，否则同一 EventLog + policy 会在有/无 trace diagnostic 时产生不同 digest。

**建议**：二者择一 — (a) 更新 docstring 为“覆盖 cursor、policy digest、四类 view 与 diagnostics”；(b) 给 `MemoryDiagnostic` 增加 flag（如 `affects_digest: bool`）并在 digest 计算时过滤。推荐 (a) 作为当前策略，因为 diagnostic 的存在本身就表示 projection 状态差异，digest 变化是合理的。

**严重性**：MEDIUM — 当前无 bug，但 docstring 与实现不一致会误导后续开发。

---

### Finding C3 (LOW): `_optional_str` / `_optional_int` 要求字段存在于 JSON mapping 中

**位置**: `dayu/host/memory.py:1325-1339`

```python
def _optional_str(mapping, field_name):
    value = _required_value(mapping, field_name)  # raises if field missing
    if value is None:
        return None
    return _as_str(value, field_name)
```

**行为**：若 JSON 中某 optional 字段完全缺失（而非值为 `null`），会抛出 `ValueError("{field_name} is required")`。当前所有 durable 序列化都显式写入 `null` 值，所以 round-trip 不会触发。但如果外部 JSON（如手动构造的测试 fixture）缺失 optional 字段，会得到误导性错误信息。

**建议**：区分“字段缺失”与“字段值为 null”——前者返回 `None`，后者也返回 `None`；只在字段存在且非 null 但类型不符时抛错。或者将错误信息改为 `"{field_name} is required or must be null"`。

**严重性**：LOW — round-trip 场景不受影响，仅边缘输入路径可能触发。

---

## 3. Stability 审查

### Finding S1 (INFO): Snapshot digest 正确排除 `built_at` 和 `updated_at`

**确认通过**：
- `_snapshot_digest_json_value`（line 795）不包含 `snapshot_id`、`built_at`、`snapshot_digest`
- `conversation_memory_snapshot_to_json_value`（line 693）包含 `built_at` 用于 durable 存储，但 digest 计算走独立路径
- `build_empty_conversation_memory_snapshot`（line 603）先用 `"pending"` 占位 digest，再计算真实 digest 后重建 snapshot
- digest 基于 `canonical_json_dumps`（sorted keys、deterministic separators、UTF-8、no NaN）

**结论**：同一 EventLog + 同一 policy 的 snapshot digest 稳定。✅

### Finding S2 (INFO): Transaction scope 行为验证

**确认通过**：
- `write_memory_snapshot` 写入 snapshot content + items + diagnostics，均在同一个 `transaction` 对象上操作
- `write_memory_snapshot_with_checkpoint` 在 snapshot 写入后立即推进/初始化 checkpoint，同事务内
- 测试 `test_snapshot_and_checkpoint_rollback_together` 验证了 snapshot 与 checkpoint 一起 rollback
- `write_memory_snapshot` 在写入后立即 read-back 验证（line 209-212），read-back 在同一未提交事务内可读到未提交变更

**潜在关注点**：`write_memory_snapshot` 内部直接调用 `transaction.execute` 进行 INSERT/DELETE/INSERT，如果中间某步失败（如 items DELETE 成功但 INSERT 中途抛错），整个事务应由调用方的 `transaction_runner` 管理 rollback。当前设计依赖调用方正确管理 transaction lifecycle。在 `write_memory_snapshot_with_checkpoint` 路径中这是由 `HostTransactionRunner.run_write` 保证的  — 测试已覆盖。

**结论**：transaction-scoped 一致性正确。✅

### Finding S3 (LOW): `build_empty_conversation_memory_snapshot` 创建两个 snapshot 实例

**位置**: `dayu/host/memory.py:603-659`

```python
snapshot_without_digest = ConversationMemorySnapshot(
    ...,
    snapshot_digest="pending",
)
digest = calculate_memory_snapshot_digest(snapshot_without_digest)
return ConversationMemorySnapshot(
    ...,
    snapshot_digest=digest,
)
```

**问题**：函数构造了两个 `ConversationMemorySnapshot` 实例——第一个用 `"pending"` 做临时 digest，计算真实 digest 后重建第二个。这重复了字段赋值且存在 drift 风险（如某字段在第一个实例中为 `None` 但第二个中为具体值，需人工对齐）。

当前代码在第二个实例中显式使用了 `snapshot_without_digest.pinned_state` 等字段（避免重复构造子对象），这是防御性的。但 `verified_facts=()` 等空 tuple 在两个实例中重复字面量，若日后默认值变更可能导致不一致。

**建议**：用 `dataclasses.replace(snapshot_without_digest, snapshot_digest=digest)` 替代手动重建，消除字段重复风险。`replace` 对 frozen dataclass 安全且高效。

**严重性**：LOW — 当前代码正确，但维护性略差。

---

## 4. Maintainability 审查

### Finding M1 (MEDIUM): `MemoryClaimStatus` enum 保留 6 个值但 Slice 1 只用 2 个

**位置**: `dayu/host/memory.py:35-43`

```python
class MemoryClaimStatus(StrEnum):
    TOOL_VERIFIED = "tool_verified"
    ASSUMPTION = "assumption"
    CANDIDATE = "candidate"
    CONFLICTED = "conflicted"
    STALE = "stale"
    SUPERSEDED = "superseded"
```

**确认**：`CANDIDATE`、`CONFLICTED`、`STALE`、`SUPERSEDED` 是为 issue 39 / 后续 phase 预留的 enum 值，符合 plan 的明确指示（plan §4.2："P9 不主动合成 conflict / stale / supersede"）。测试 `test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` 验证了 typed contracts 拒绝这些 status 进入 view。

**潜在关注**：`_optional_str` → `MemoryClaimStatus(value)` 将接受任何合法 enum 值，包括 `"conflicted"` 等。这意味着从 durable JSON 反序列化时可以读回预留值，但 `VerifiedFactView` / `WorkingAssumptionView` / `ConversationContinuityItem` 的 `__post_init__` 会拒绝它们。这是正确的两层防御。

**结论**：设计合理。✅

### Finding M2 (LOW): `_validate_reason_pair` 只在 contract dataclass 的 `__post_init__` 中调用，不在 durable 写入路径中调用

**位置**: `dayu/host/memory.py:1202-1215`；`dayu/host/durable/memory.py` `_insert_item`

**确认**：`VerifiedFactView`、`WorkingAssumptionView`、`ConversationContinuityItem` 的 `__post_init__` 均调用 `_validate_reason_pair`。Durable `_insert_item` 直接使用 `item.included_reason` 和 `item.excluded_reason`，但此时 contract 已保证互斥。Schema 层有 `CHECK (included_reason IS NULL OR excluded_reason IS NULL)` 提供额外防御。无问题。

**结论**：两层防御正确。✅

---

## 5. Host Boundary 审查

### ✅ 通过

- `dayu/host/memory.py` 的 import：`dayu.contracts.json_value`（层中立契约）、`dayu.host.durable.codec`（Host 内 durable 基础设施）、标准库 — **无** `dayu.fins`、`dayu.engine`、`dayu.service`、`dayu.ui`
- `dayu/host/durable/memory.py` 的 import：`dayu.contracts.json_value`、`dayu.host.durable.*`（同层基础设施）、`dayu.host.memory`（public contract）— **无**跨层 import
- Durable tables 不包含业务字段：schema 中无 `company`、`business_line`、`technology_release`、`financial_report` 等业务词语
- `OpaqueMemoryRef.ref_kind` 使用 `HostNeutralRefKind`：SOURCE、CHUNK、ENTITY、SUBJECT、TOPIC、EVIDENCE、PAYLOAD、EXTERNAL — 纯 Host 中立分类
- 测试 `test_host_neutral_ref_kind_rejects_business_specific_kind` 验证 ref_kind 不接受非枚举值
- 测试 `test_memory_contracts_do_not_expose_business_specific_fields` 验证 contract/enum 不包含业务专有字段

**注意**：测试使用文本搜索（`_FORBIDDEN_BUSINESS_TERMS = ("company", "business_line", "technology_release")`），这是 plan 描述的 "不要实现脆弱的业务词 blocklist" 的验证端使用，不是生产代码中的 blocklist。生产代码通过类型系统（`HostNeutralRefKind` StrEnum）确保中立性。✅

---

## 6. Schema 审查

### Finding SC1 (INFO): 所有 FK/CHECK/Index 验证通过

**确认**：

| 表 | PK | FK | CHECK | Index |
|----|----|----|-------|-------|
| `host_memory_snapshots` | `snapshot_id` | `checkpoint_event_id` → `event_log` | cursor 0/positive + event_id consistency | `host_memory_snapshots_session_cursor` |
| `host_memory_items` | `item_id` | `snapshot_id` → snapshots (CASCADE), `event_id` → event_log, `event_sequence` → event_log | item_kind enum, claim_status enum, producer_kind enum, payload_ref/digest paired, included/excluded mutual exclusion | `host_memory_items_session_sequence` |
| `host_memory_diagnostics` | `diagnostic_id` | `snapshot_id` → snapshots (CASCADE) | reason enum, event_sequence positive when set | `host_memory_diagnostics_session_reason` |

- `host_memory_items` 的 `snapshot_id` FK 使用 `ON DELETE CASCADE`，删除 snapshot 时自动清理 items
- `host_memory_diagnostics` 的 `snapshot_id` FK 使用 `ON DELETE CASCADE`
- `HOST_SCHEMA_VERSION = 6`，bootstrap 幂等，mismatch 时抛 `HostSchemaMismatchError`
- 不做旧库兼容读取或迁移 ✅
- 测试覆盖：tables 存在、indexes 存在、CHECK 拒绝非法值、FK 拒绝悬空引用

**结论**：schema 设计正确。✅

### Finding SC2 (INFO): `host_memory_items` 的 `event_id` / `event_sequence` FK 引用 `event_log`

`event_sequence` 作为 FK 引用 `event_log(event_sequence)`，这要求 `event_log` 的主键 `event_sequence` 是 SQLite FK 可引用的 parent key。测试 `test_event_sequence_is_sqlite_foreign_key_parent_key` 已覆盖验证。✅

---

## 7. 测试审查

### 覆盖率矩阵（对比 plan Slice 1 要求）

| Plan 要求 | 测试 | 状态 |
|-----------|------|------|
| schema 创建 memory tables / indexes | `test_memory_projection_tables_and_indexes_are_created` | ✅ |
| `HOST_SCHEMA_VERSION` fresh bootstrap 通过 | `test_fresh_db_creates_foundation_phase8_and_memory_tables` | ✅ |
| typed contract 拒绝空 id | `test_typed_contracts_reject_invalid_ids_cursor_and_verified_fact` | ✅ |
| 拒绝非法 cursor | 同上 | ✅ |
| 拒绝 verified fact 非 TOOL provenance | 同上 | ✅ |
| PinnedStateView 包含正确字段，open questions 不重复 | `test_pinned_state_open_questions_are_not_duplicated` | ✅ |
| OpaqueMemoryRef.ref_kind 只接受 Host-neutral enum | `test_host_neutral_ref_kind_rejects_business_specific_kind` | ✅ |
| schema/contracts 不包含业务专有字段 | `test_memory_contracts_do_not_expose_business_specific_fields` | ✅ |
| MemoryDiagnostic 写入 memory diagnostics contract | `test_memory_diagnostic_contract_round_trips_through_durable_store` | ✅ |
| 空 EventLog 上创建并读取空 snapshot | `test_empty_event_log_snapshot_can_be_created_and_read` | ✅ |
| checkpoint / snapshot content 同事务提交 | `test_snapshot_and_checkpoint_rollback_together` | ✅ |
| P9 不合成 CONFLICTED/STALE/SUPERSEDED | `test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` | ✅ |
| no `Any`/`object` signature; pyright 通过 | 已确认 0 errors | ✅ |

### Finding T1 (LOW): 测试使用裸 `cast()` 模拟非法输入

**位置**: `tests/host/test_memory_projection.py:423-427`

```python
with pytest.raises(ValueError):
    OpaqueMemoryRef(
        ref_kind=cast(HostNeutralRefKind, "company"),
        ref_id="opaque-company-ref",
    )
```

**问题**：`cast()` 是类型擦除操作，不产生运行时效果。当 `OpaqueMemoryRef.__post_init__` 中 `isinstance(self.ref_kind, HostNeutralRefKind)` 检查失败时，抛出 `ValueError`。测试依赖 `isinstance` 检查而非 `cast`。`cast` 在此处仅用于绕过 pyright 的类型检查，让测试代码通过类型系统。这是合理的测试技术，但值得注释说明意图。

**严重性**：LOW — 测试覆盖有效，`cast` 仅用于类型绕过。

---

## 8. Adversarial Failure Pass

以下 adversarial 场景被显式测试或通过类型系统防御：

| 攻击/故障场景 | 防御方式 | 状态 |
|--------------|---------|------|
| 空 snapshot_id | `_require_non_empty` in post_init + schema TEXT PK | ✅ |
| cursor=0 带 event_id | `MemorySnapshotCursor.__post_init__` | ✅ |
| cursor>0 不带 event_id | `MemorySnapshotCursor.__post_init__` | ✅ |
| verified fact 用 ASSUMPTION status | `VerifiedFactView.__post_init__` | ✅ |
| verified fact 用 USER provenance | `VerifiedFactView.__post_init__` | ✅ |
| working assumption 用 TOOL producer | `WorkingAssumptionView.__post_init__` | ✅ |
| continuity 用 TOOL producer | `ConversationContinuityItem.__post_init__` | ✅ |
| included + excluded reason 同时存在 | `_validate_reason_pair` + schema CHECK | ✅ |
| snapshot digest 被篡改 | `_validate_snapshot_digest` in read path | ✅ |
| 损坏 JSON 在 durable 列 | try/except in `_snapshot_from_json_text` | ✅ |
| 负数 checkpoint sequence | schema CHECK | ✅ |
| checkpoint 倒退 | `advance_projection_checkpoint` guard | ✅ |
| 并发写同一 snapshot_id | `ON CONFLICT ... DO UPDATE` (upsert) | ⚠️ 见下方 |

### Finding A1 (LOW): Snapshot upsert 不检测并发覆盖

**位置**: `dayu/host/durable/memory.py:169-206`

Snapshot INSERT 使用 `ON CONFLICT(snapshot_id) DO UPDATE SET ...`。这意味着如果两个并发 writer 使用相同 `snapshot_id`，后者会静默覆盖前者，且 `snapshot_digest` 可能不一致（前者写入的 items + diagnostics 已被 `_replace_memory_items` / `_replace_snapshot_diagnostics` 整体替换）。

在单 Host 实例 + serialized projection runner 的正常操作路径中这不会发生。但如果 (a) 手动使用重复 snapshot_id 或 (b) 将来引入并发 projection consumer，可能产生静默数据覆盖。

**建议**：在 Slice 2/4 的 projection consumer 中确保 snapshot_id 唯一性（如基于 session_id + consumer_id + sequence 生成），或添加 `updated_at` 比较防御并发覆盖。

**严重性**：LOW — Slice 1 无并发 projection runner，且 snapshot_id 唯一性由上层调用方保证。

---

## 9. Docstring 与类型系统审查

### ✅ 通过

- 所有 public function 有完整中文 docstring，含 `:param`、`:returns`、`:raises`
- 所有 dataclass 有模块级中文 docstring
- 无 `Any`、`object` 类型
- 无 untyped signature
- 所有 `TypeAlias` 有 docstring 说明用途
- 所有 enum 有中文 docstring 说明各成员语义

---

## 10. 文件级 Observation

### `dayu/host/memory.py` (1406 lines)

- **职责清晰**：typed contracts、enums、digest/JSON helpers、empty snapshot factory
- **无 IO 依赖**：不 import durable store、不 import Engine、不 import Fins
- **辅助函数名以 `_` 开头**：模块级私有，命名一致
- `_require_non_empty` 同时检查 `""` 和 whitespace-only 字符串 — 防御充分

### `dayu/host/durable/memory.py` (710 lines)

- **职责清晰**：transaction-scoped read/write，复用 `HostTransaction` 和 `projection.py` checkpoint primitive
- **不启动 transaction**：所有函数接受 `transaction: HostTransaction`，由调用方管理 lifecycle
- **不修改治理真源**：只写 memory-owned tables，不碰 Run/Attempt/wait/dispatch
- `write_memory_snapshot` 在写入后 read-back 验证 — 防御充分
- `_insert_item` 正确处理 `None` → `None` for included/excluded_reason (line 526-527)

### `dayu/host/durable/schema.py`

- `HOST_SCHEMA_VERSION` 从 5 递增到 6
- `MEMORY_PROJECTION_TABLES` 独立 tuple，合并进 `HOST_DURABLE_TABLES`
- `MEMORY_PROJECTION_DDL` 按外键依赖顺序（snapshots → items → diagnostics）
- `MEMORY_PROJECTION_INDEX_DDL` 包含 session cursor、items sequence、diagnostics reason 三个 index
- bootstrap 只接受 fresh (version=0) 或当前版本 (version=6)

---

## 11. 求值

**Blocking**: 0
**Medium**: 3
**Low**: 3
**Info**: 2

### Blocking Findings

无。当前实现满足 Slice 1 的 stop condition：可在空 EventLog 上创建并读取空 snapshot，checkpoint 与 snapshot content 同事务提交，未接 RunInputBuilder，未做 projection catch-up。

### Medium Findings 摘要

| ID | 位置 | 描述 |
|----|------|------|
| C1 | `durable/memory.py:418,449` | `producer_name` 对非 TOOL producer 存储 `producer_kind.value`，语义不精确 |
| C2 | `memory.py:795,591` | `_snapshot_digest_json_value` 包含所有 diagnostics，与 docstring "影响 message 的 diagnostics" 不一致 |
| M1 | `memory.py:35-43` | `MemoryClaimStatus` 6 个值仅 2 个在 Slice 1 中被 contract 接受，预留值受 JSON 反序列化路径接受但被 view `__post_init__` 拒绝 |

### Low Findings 摘要

| ID | 位置 | 描述 |
|----|------|------|
| C3 | `memory.py:1325` | `_optional_str/int` 将字段缺失报为 "is required" 而非区分缺失 vs null |
| S3 | `memory.py:628-659` | `build_empty_conversation_memory_snapshot` 构造两个 snapshot 实例，可用 `dataclasses.replace` |
| A1 | `durable/memory.py:183` | Snapshot upsert 不检测并发覆盖 |
| T1 | `test_memory_projection.py:423` | `cast()` 用于绕过类型检查，缺少注释 |

---

## 12. 裁决

**Verdict: PASS with findings (0 blocking)**.

P9-S1 `Durable Memory Contracts and Schema` 实现满足 plan 的全部 Slice 1 要求：
- Typed contracts 严格，无 `Any`/`object`/untyped signature，中文 docstring 完整
- Verified facts 只接受 TOOL provenance，非 TOOL producer 被 contract 拒绝
- Snapshot digest 不包含 `built_at`、`updated_at`，基于 deterministic canonical JSON
- Durable write/read 是 transaction-scoped，snapshot content 与 checkpoint 可同事务提交/rollback
- Schema v6 fresh bootstrap 正确，FK/CHECK/index 完备，不做旧库兼容
- Host boundary 干净：不 import `dayu.fins`，不保存业务原文，无业务字段写入 schema
- Tests 覆盖 plan 要求的全部场景，pyright 0 errors，20 tests passed

0 个 blocking finding 中没有一个威胁 correctness 或 stability。3 个 medium findings 均为语义精确性或文档一致性问题，可在 Slice 2 中低成本修正。建议在进入 Slice 2 前处理 C1（producer_name）和 C2（docstring），避免问题扩散。
