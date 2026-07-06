# WU-CLI-SMOKE-01 / MANUAL-F01 Fix Review — AgentMiMo

## Scope

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: MANUAL-F01 root cause and candidate fix review
- Reviewer: AgentMiMo
- Date: 2026-07-06
- Artifacts reviewed:
  - Manual validation evidence: `docs/reviews/wu-cli-smoke-01-manual-validation-evidence.md`
  - Code: `dayu/host/tool_runtime.py` lines 6954-6982 (`_wait_snapshot_ref`, `_wait_snapshot_digest`)
  - Code: `dayu/contracts/tool_await.py` lines 70-98 (`ToolAwaitSnapshot`)
  - Code: `dayu/host/durable/state.py` lines 369-400 (`WaitSnapshotRef`), 706-739 (serializers), 2710-2804 (`insert_wait_record`)
  - Code: `dayu/host/durable/schema.py` lines 683-760 (DDL and CHECK constraint)
  - Test: `tests/host/test_toolruntime_executor.py` lines 2179-2215 (`test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref`)

---

## 1. Root Cause 是否与用户现象同源

### 结论：**是，root cause 与用户现象同源。**

### 证据链

用户现象为 `dayu-cli interactive` 中 `start_fins_download` 返回 `HostDurableError`，而 `dayu-cli download --ticker V` 直接启动下载成功。

直接证据链：

| 步骤 | 文件 : 行号 | 证据 |
|---|---|---|
| Engine 工具返回 `ToolAwaitingOutcome` | `dayu/fins/tools/_ingestion_tool_helpers.py` | `ToolAwaitSnapshot(snapshot_id=..., captured_at=...)` 只有 2 个字段，无 `snapshot_digest` |
| `_wait_snapshot_ref` 构造 `WaitSnapshotRef` | `dayu/host/tool_runtime.py:6954-6967` | 当前代码已调用 `_wait_snapshot_digest(outcome.snapshot)` 派生 digest（修复后状态） |
| 修复前状态（probe 复现） | `dayu/host/tool_runtime.py:6964` (修复前) | `snapshot_digest=None` 硬编码 |
| `WaitSnapshotRef` 数据模型 | `dayu/host/durable/state.py:369-400` | `snapshot_digest: str \| None`，`__post_init__` 中 `_require_optional_non_empty_text` 允许 `None` |
| 序列化写入 | `dayu/host/durable/state.py:2776-2778` | `serialize_wait_snapshot_digest` 返回 `ref.snapshot_digest`（修复前为 `None`） |
| SQLite CHECK 约束 | `dayu/host/durable/schema.py:752-759` | 三列必须全 NULL 或全 NOT NULL：`snapshot_ref IS NOT NULL AND snapshot_captured_at IS NOT NULL AND snapshot_digest IS NOT NULL` |
| INSERT 失败 | SQLite runtime | `snapshot_ref=NOT NULL`, `snapshot_captured_at=NOT NULL`, `snapshot_digest=NULL` → CHECK 约束违反 |

**修复前的失败路径**：Engine `ToolAwaitSnapshot`（2 字段）→ `_wait_snapshot_ref`（`snapshot_digest=None`）→ `WaitSnapshotRef`（`snapshot_digest=None`）→ 序列化（`snapshot_ref=非空`, `snapshot_captured_at=非空`, `snapshot_digest=NULL`）→ SQLite INSERT → CHECK 约束违反 → `HostDurableError`。

**修复后的成功路径**：Engine `ToolAwaitSnapshot`（2 字段）→ `_wait_snapshot_ref` → `_wait_snapshot_digest`（`sha256_digest_json({"captured_at": "...", "snapshot_id": "..."})`）→ `WaitSnapshotRef`（`snapshot_digest=sha256:...`）→ 序列化（三列全 NOT NULL）→ SQLite INSERT → 通过 CHECK 约束。

**用户现象与 root cause 的对应**：
- `dayu-cli interactive` 中 Agent 调用 `start_fins_download` → 走 ToolRuntime `_accept_awaiting` → `_wait_snapshot_ref` → 遇到 CHECK 约束失败 → `HostDurableError` → tool result 为 failed。
- `dayu-cli download --ticker V` → 走 Fins direct CLI path，不经过 Host wait record 写入 → 不触发 CHECK 约束 → 正常启动。

两者差异的唯一原因就是 Agent path 需要写 Host durable wait record，而 direct CLI path 不需要。

---

## 2. 候选修复是否符合设计真源和分层

### 结论：**符合。修复正确实现了 Host 层对 Engine opaque snapshot 的 durable 派生语义。**

### 设计真源核对

**Engine 设计真源**（`docs/engine/design.md`）：
- Engine 只通过 `ToolExecutor` 协议做 bounded handshake；长事务 awaiting、wait record、durable snapshot 属于 Host / ToolRuntime。
- `ToolAwaitSnapshot` 只有 `snapshot_id` 和 `captured_at`，docstring 明确："快照内容由 Host / ToolRuntime 持有；Engine 只透传 opaque `snapshot_id` 与采集时间"。

**Host 设计真源**（`docs/host/design.md` Section 20）：
- wait record 最小语义包含 `snapshot_ref?`。
- `snapshot_ref` 必须是强类型字段或受限 typed refs。
- Host 持有 ToolRuntime 的治理 ownership；Engine 不知道 `@tool`、`ToolDefinition` 或业务工具实现。

**修复的分层合规性**：
- 修复位置在 `dayu/host/tool_runtime.py`（Host 层），不在 Engine 或 contracts 层。
- 修复不修改 `ToolAwaitSnapshot`（Engine contract），保持 Engine 的 opaque 语义。
- 修复不修改 `WaitSnapshotRef` 数据模型或 SQLite DDL。
- digest 派生使用 `dayu/host/durable/codec.py` 的 `sha256_digest_json`，与 Host durable 标准 digest 格式一致。

**关键设计对齐**：`snapshot_digest` 的语义是"durable 引用的完整性标识"，不是"快照内容的 checksum"。Engine 不知道也不需要知道 digest 的存在。Host 在 accept 时从 Engine 提供的 opaque ref 派生 digest，确保 durable row 的三列完整性约束满足。这完全符合 Host 作为 durable truth owner 的设计定位。

### 具体实现评估

```python
def _wait_snapshot_digest(snapshot: ToolAwaitSnapshot) -> str:
    return sha256_digest_json(
        {
            "captured_at": format_utc_timestamp(snapshot.captured_at),
            "snapshot_id": snapshot.snapshot_id,
        }
    )
```

- **确定性**：`sha256_digest_json` 对相同输入产生相同输出；`format_utc_timestamp` 格式化为固定 UTC timestamp 文本。
- **稳定性**：同一 `snapshot_id + captured_at` 组合，无论重试多少次，digest 不变。
- **幂等性**：accept 重试时，同一 `ToolAwaitSnapshot` 产生同一 digest，不违反 idempotency。
- **格式合规**：`sha256_digest_json` 返回 `sha256:<64 lowercase hex>`，符合 Host durable 标准 digest 格式。

---

## 3. 是否存在更优最佳实践方案

### 结论：**候选修复是当前最佳方案。**

已考虑的替代方案：

| 方案 | 评估 | 结论 |
|---|---|---|
| **A. 在 Engine contract `ToolAwaitSnapshot` 中增加 `snapshot_digest`** | 违反 Engine opaque 语义。Engine 不持有快照内容，无法有意义地计算 digest。增加 Engine 认知负担，违反"Engine 只透传 opaque ref"的设计真源。 | ❌ 不符合分层 |
| **B. 放宽 DDL CHECK 约束，允许 `snapshot_digest` 单独为 NULL** | 破坏三列完整性语义。如果 `snapshot_ref` 存在但 `snapshot_digest` 为 NULL，读取路径的 `deserialize_wait_snapshot_ref` 需要处理不完整 row，增加防御性校验负担。且当前 CHECK 约束是设计真源的一部分（三列同存同缺）。 | ❌ 破坏完整性 |
| **C. 当 Engine 不提供 digest 时，`snapshot_ref` 整体设为 None** | 丢失 snapshot 追踪语义。Fins observation handle 的 snapshot_id 和 captured_at 对 poll adapter 恢复、idempotency 和诊断有价值。 | ❌ 丢失信息 |
| **D. 在 Host `_wait_snapshot_ref` 中派生 digest（候选修复）** | 最小改动。不改 Engine contract、不改 DDL、不改数据模型。Host 层自行补全 durable row 所需的完整性字段。符合 Host 作为 durable truth owner 的设计定位。 | ✅ 最佳方案 |

**方案 D 是正确的**，因为它：
1. 遵循 Host 作为 durable truth owner 的架构定位。
2. 保持 Engine opaque snapshot 语义不变。
3. 不修改 DDL 或数据模型。
4. digest 派生确定性、稳定、幂等。
5. 与 Host durable 标准 digest 格式一致。

### 一个值得注意的设计前提

`snapshot_digest` 的语义定位需要明确：它是 **durable 引用完整性标识**，不是 **快照内容 checksum**。Engine 的 `ToolAwaitSnapshot` 不承载快照内容（内容由 Host / ToolRuntime 持有），因此 Host 从 Engine 提供的 opaque ref 字段派生 digest 是语义正确的——它标识的是"这个引用的组合"，而非"引用指向的内容"。

如果未来需要 content-level integrity check（例如验证 Fins observation handle 的内容未被篡改），那是一个独立的 concern，不应与 durable row 的引用完整性混为一谈。

---

## 4. 必测项 / 真实验证项

### 4.1 已有测试覆盖

| 测试 | 文件 | 覆盖范围 |
|---|---|---|
| `test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref` | `tests/host/test_toolruntime_executor.py:2179` | 验证 `_wait_snapshot_ref` 构造的 `WaitSnapshotRef.snapshot_digest` 等于 `sha256_digest_json({"captured_at": "...", "snapshot_id": "..."})` |
| `test_wait_record_ddl_rejects_orphan_snapshot_digest` | `tests/host/test_wait_record_state.py:533` | 验证 DDL CHECK 约束拒绝部分 NULL 的 snapshot 列 |

### 4.2 必须补充的测试

| 测试项 | 优先级 | 说明 |
|---|---|---|
| **T1: 修复后 `insert_wait_record` 成功写入** | P0 | 使用 `snapshot_digest=sha256_digest_json(...)` 的 `WaitSnapshotRef` 构造 `WaitRecordRow`，验证 `insert_wait_record` 不抛异常且 row 可读回。 |
| **T2: round-trip 一致性** | P0 | 序列化 → 反序列化 round-trip：`WaitSnapshotRef` → `serialize_wait_snapshot_ref/captured_at/digest` → `deserialize_wait_snapshot_ref` → 原始 `WaitSnapshotRef`。 |
| **T3: 修复后 E2E Agent awaiting path** | P0（真实验证） | `dayu-cli interactive` 中执行 `下载Visa财报`，验证 `start_fins_download` 不再返回 `HostDurableError`，wait record 写入成功，`host_wait_records` 有对应 row。 |
| **T4: direct CLI path 无回归** | P1 | `dayu-cli download --ticker V` 行为不变。 |
| **T5: accept idempotency** | P1 | 同一 `ToolAwaitingOutcome` 重试 accept 时，同一 `accept_idempotency_key` 和同一 `snapshot_digest`，不创建第二个 wait record。 |
| **T6: `snapshot=None` 路径不受影响** | P2 | `ToolAwaitingOutcome(snapshot=None)` 仍返回 `snapshot_ref=None`，三列全 NULL，CHECK 约束通过。 |

### 4.3 真实验证命令

```bash
# T3: 验证修复后 Agent awaiting path
dayu-cli --log-level debug \
  --log-file workspace/tmp/wu-cli-smoke-01-manual/interactive-fix.log \
  interactive --label wu-cli-smoke-fix-test

# 在 interactive 中输入：
# dayu> 下载Visa财报

# 预期：
# - 不再出现 HostDurableError
# - 日志中出现 host.waiting.accept_tool_awaiting.accepted
# - 日志中出现 tool_result_accepted ... outcome=awaiting（不是 failed）
# - host_wait_records 表有对应 row
```

---

## 5. 总体裁决

### Verdict: **PASS — 修复正确且符合设计真源。**

| 维度 | 裁决 | 说明 |
|---|---|---|
| Root cause 同源性 | ✅ 通过 | SQLite CHECK 约束违反直接导致 `HostDurableError`，与用户观察到的 interactive Agent `start_fins_download` 失败完全同源。 |
| 设计真源合规性 | ✅ 通过 | 修复在 Host 层派生 digest，不改 Engine contract，不改 DDL，符合 Host durable truth owner 定位。 |
| 分层合规性 | ✅ 通过 | `tool_runtime.py`（Host 层）使用 `durable/codec.py`（Host durable 基础设施）的标准 digest 函数。无反向依赖。 |
| 最佳实践 | ✅ 通过 | 候选修复是 4 个方案中最小、最可维护、最符合架构的方案。 |
| 测试覆盖 | ⚠️ 需补充 | 核心修复已有单元测试覆盖，但缺少 E2E 真实验证（T3）和 round-trip 测试（T2）。 |

### 已知修复状态

代码证据显示修复 **已合入** 当前分支 `phase/host-issues-control`：
- `_wait_snapshot_digest` 函数已定义于 `dayu/host/tool_runtime.py:6970-6982`
- `_wait_snapshot_ref` 已调用 `_wait_snapshot_digest` 于 `dayu/host/tool_runtime.py:6966`
- 测试 `test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref` 已更新并验证

### MANUAL-F01 关闭前置

MANUAL-F01 要求 "dayu-cli core Fins direct / interactive main path usable"。当前修复已合入代码，但需要以下真实验证才能关闭：

1. **P0**: 在修复后的代码上重新运行 `dayu-cli interactive` → `下载Visa财报`，确认 `start_fins_download` 不再返回 `HostDurableError`。
2. **P0**: 确认 `host_wait_records` 表有对应 row（之前为 0 行）。
3. **P1**: 确认 `dayu-cli download --ticker V` 直接路径无回归。

### 残余风险

| 风险 | 严重性 | 说明 |
|---|---|---|
| 修复后可能仍有其他 awaiting path 失败 | 低 | 如果 `MANUAL-F01` 的 `HostDurableError` 仅由 snapshot_digest 缺失引起，修复后应消失。若仍有错误，需进一步诊断 activation adapter 或 Fins runtime 路径。 |
| `snapshot_digest` 语义混淆 | 低 | 当前 digest 是引用完整性标识，不是内容 checksum。如果未来有人误以为它是内容完整性校验，可能产生错误的安全假设。建议在 docstring 中明确说明。 |
