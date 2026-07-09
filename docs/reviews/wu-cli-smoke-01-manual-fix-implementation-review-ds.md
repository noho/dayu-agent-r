# WU-CLI-SMOKE-01 / MANUAL-F01 Implementation Review — AgentDS

## 结论

**Verdict: pass**

MANUAL-F01 root cause fix 正确且充分。改动最小、精准、无破坏性副作用。Schema 的 Python invariant hardening 方向正确，消除了 Python 代码与 SQLite CHECK 约束之间的语义间隙。无过度设计、无层间污染。自动化验证和真实环境验证均已通过。

有一个 low-severity 评论性 finding（F-LOW-01），不构成 required fix。

---

## 审查范围

- 当前未提交 diff：6 文件，+137/-15 行
- 生产代码：`dayu/host/durable/state.py`、`dayu/host/tool_runtime.py`
- 测试：`tests/host/test_toolruntime_executor.py`、`tests/host/test_wait_awaiting_accept.py`、`tests/host/test_wait_record_state.py`
- 控制文档：`docs/host/issues-implementation-control.md`
- 设计真源：`AGENTS.md`、`docs/host/design.md`、`docs/engine/design.md`
- 上游修复记录：`docs/reviews/wu-cli-smoke-01-manual-validation-fix-codex.md`

---

## 1. Root Cause 修复审查

### 1.1 Root Cause 确认

直接证据链完整且可信：

1. 日志证据来自 `workspace/tmp/wu-cli-smoke-01-manual/interactive.log`：
   - Engine 请求 `start_fins_download` → Host 进入 awaiting accept → Engine 收到 failed tool result
2. 异常探针复现到同一 SQLite CHECK constraint 错误：
   ```
   HostDurableError: CHECK constraint failed:
   (snapshot_ref IS NULL AND snapshot_captured_at IS NULL AND snapshot_digest IS NULL)
   OR
   (snapshot_ref IS NOT NULL AND snapshot_captured_at IS NOT NULL AND snapshot_digest IS NOT NULL)
   ```
3. 代码根因在 `dayu/host/tool_runtime.py:6954-6968`（`_wait_snapshot_ref`）：`snapshot_digest=None` 硬编码。

Root cause 逻辑/数据同源，符合 AGENTS 思考纪律第 4 条。

### 1.2 修复方案评估

**`dayu/host/tool_runtime.py:6970-6982` — `_wait_snapshot_digest`**

```python
def _wait_snapshot_digest(snapshot: ToolAwaitSnapshot) -> str:
    return sha256_digest_json(
        {
            "captured_at": format_utc_timestamp(snapshot.captured_at),
            "snapshot_id": snapshot.snapshot_id,
        }
    )
```

- 从 Engine 公共 `ToolAwaitSnapshot` 的两个字段 (`snapshot_id`, `captured_at`) 计算 Host durable sha256 digest
- 使用 `format_utc_timestamp` (canonical UTC `Z` format, 固定微秒精度) 与 `sha256_digest_json` (canonical JSON → sha256) — 均为 Host durable 层内的稳定格式
- Digest 输出格式 `sha256:<64 lowercase hex>` 匹配 `is_sha256_digest` pattern `^sha256:[0-9a-f]{64}$`（`dayu/host/durable/codec.py:22`）
- 函数签名明确为 `str`（非 `str | None`），与 `WaitSnapshotRef.snapshot_digest` 类型收紧一致

**`dayu/host/tool_runtime.py:6954-6968` — `_wait_snapshot_ref` 修复**

```python
def _wait_snapshot_ref(outcome: ToolAwaitingOutcome) -> WaitSnapshotRef | None:
    if outcome.snapshot is None:
        return None
    return WaitSnapshotRef(
        snapshot_id=outcome.snapshot.snapshot_id,
        captured_at=outcome.snapshot.captured_at,
        snapshot_digest=_wait_snapshot_digest(outcome.snapshot),  # 修复点
    )
```

- `outcome.snapshot is None` 路径不受影响（返回 `None`，三列全部 NULL，满足 CHECK 约束的 NULL 分支）
- `outcome.snapshot` 非空时现在生成完整 digest

### 1.3 Root Cause 修复完整性

| 检查项 | 结论 |
|---|---|
| 是否修复了 `start_fins_download` 返回 `HostDurableError` 的根因 | ✓ 是，`snapshot_digest=None` 是唯一违反 CHECK 约束的路径 |
| 是否修复了所有通过 `_wait_snapshot_ref` 进入 awaiting 的工具 | ✓ 是，所有 `ToolAwaitingOutcome` 携带 snapshot 的工具都走同一个函数 |
| 是否影响了 `snapshot=None` 的工具 | ✗ 否，`_wait_snapshot_ref` 返回 `None` 的逻辑未改动 |
| 是否绕过了 Host accept barrier | ✗ 否，`_wait_snapshot_ref` 在 accept 调用之前计算 digest（`tool_runtime.py:3458`），等待 accept 仍通过 `_accept_awaiting_with_retry` 走完整 barrier |
| 是否改变了 Engine 公共 awaiting contract | ✗ 否，只消费 `ToolAwaitSnapshot` 的公共字段，不要求 Engine 新增字段 |
| 是否需要在 Fins 层修改 | ✗ 否，Fins 工具只提供 snapshot，不负责 digest 计算 |

---

## 2. Durable/State.py Python Invariant Hardening 审查

### 2.1 `WaitSnapshotRef` 类型收紧 (`state.py:371-401`)

**变更：**
- `snapshot_digest: str | None` → `snapshot_digest: str`
- 验证：`_require_optional_non_empty_text` → `_require_sha256_digest`

**评估：**

- 类型收紧与 SQLite CHECK 约束一致：数据库中 `snapshot_digest` 列在三列非空分支下必须是 NOT NULL 的有效 digest
- `_require_sha256_digest` 来自 `dayu/host/durable/_validation.py:46-56`，是 durable 层 centralized validation helper，不是又一份本地副本 — 正确遵循了 DRY 原则
- `is_sha256_digest` 使用 `re.compile(r"^sha256:[0-9a-f]{64}$").fullmatch(value)` — 严格格式校验，不接受空字符串、非 hex 字符、长度不对的值

**副作用分析：**

| 潜在影响 | 评估 |
|---|---|
| `WaitSnapshotRef` 不再接受 `snapshot_digest=None` | ✓ 正确，已经不存在合法的 `snapshot_digest=None` 场景（要么三列全 NULL，要么全非 NULL） |
| `serialize_wait_snapshot_digest` (`state.py:731-740`) | ✓ 不受影响，`ref` 为 `None` 时返回 `None`（三列全 NULL），非 `None` 时 `ref.snapshot_digest` 必为非空 digest |
| `WaitRecordRow.snapshot_ref` 类型为 `WaitSnapshotRef \| None` | ✓ 不受影响，row 级别的 `Optional` 不变，只是 `WaitSnapshotRef` 内部字段收紧 |
| 现有 round-trip 测试（`test_wait_record_codecs_round_trip_all_typed_fields`） | ✓ 测试已使用 `_SNAPSHOT_DIGEST = "sha256:" + "1" * 64`，该值通过 `is_sha256_digest` 校验 |

### 2.2 `deserialize_wait_snapshot_ref` 三列配对校验 (`state.py:757-759`)

**变更：**
```python
# Before
if snapshot_id is None or captured_at is None:
# After
if snapshot_id is None or captured_at is None or snapshot_digest is None:
```

**评估：**

- 这是 fail-fast 保护层：在 Python row codec 层拒绝不完整的三列组合，避免推迟到 SQLite CHECK 才暴露
- 与 SQLite CHECK 约束语义一致
- 错误信息 `"snapshot ref columns must be paired"` 准确描述了三个 `None` 的三列共存约束
- 对全 NULL 三列（`snapshot_id is None and captured_at is None and snapshot_digest is None`）正确返回 `None`（不抛异常）

### 2.3 `_validation.py` 导入 (`state.py:55`)

**新增导入：**
```python
require_sha256_digest as _require_sha256_digest,
```

- 这是 `_validation.py` 的既定用途（`"""Host durable 私有标量校验 helper...不作为公共导出面"""`）
- `state.py` 位于同一 `dayu/host/durable/` 包内，属于 intra-package import — 正确
- `require_optional_non_empty_text` 导入保留，因为它在 `state.py` 其他地方仍有大量使用 — 正确

---

## 3. 最佳实践、过度设计、层间污染审查

### 3.1 最佳实践

| 检查项 | 结论 |
|---|---|
| 最小修复原则 | ✓ 只修改 2 个生产文件，+30 行，无新抽象 |
| 不绕过现有 barrier | ✓ 仍经过 `_accept_awaiting_with_retry` → `DefaultHostToolAwaitingAcceptPort` → durable transaction |
| Digest 使用 canonical Host codec | ✓ `sha256_digest_json` + `format_utc_timestamp` 均为 Host durable 标准工具 |
| 函数完整中文 docstring | ✓ `_wait_snapshot_digest` 有 `:param` `:returns` |
| 类型完备 | ✓ 新函数 `_wait_snapshot_digest` 明确 `str` 返回类型，无 `Any`、`object` |
| 无魔法字符串 | ✓ digest 格式由 `_SHA256_DIGEST_PATTERN` 统一定义 |
| 无嵌套函数 | ✓ `_wait_snapshot_digest` 是模块级私有函数 |
| 无兼容性代码 | ✓ 直接按新 schema 处理，不保留旧 `None` 路径兼容 |

### 3.2 过度设计检查

- 没有引入新的公共 API、protocol、abstract class 或 registry
- 没有为 digest 引入可插拔策略、factory 或 DI
- 没有扩展 `ToolAwaitSnapshot` contract
- 没有为"未来可能的 snapshot 扩展"预留扩展点

**结论：无过度设计。** 修复严格限定在 `_wait_snapshot_ref` 的 bug 修复 + `WaitSnapshotRef` 的类型/校验对齐。

### 3.3 层间污染检查

| 边界 | 检查 |
|---|---|
| Host → Engine | ✗ 无。Engine 不接收新需求，`ToolAwaitSnapshot` contract 不变 |
| Host → Fins | ✗ 无。Fins 工具只在 Engine 侧产生 `ToolAwaitSnapshot`，不感知 Host digest 计算 |
| Host durable → Host ToolRuntime | ✓ 正常。`_wait_snapshot_digest` 在 `tool_runtime.py` 中调用 `codec.sha256_digest_json` 和 `codec.format_utc_timestamp`，这是 Host 层内正常的 codec 依赖 |
| ToolRuntime → `_validation.py` | ✗ 无。`_wait_snapshot_digest` 不调用 `_validation.py`，它只消费 `codec.py` 的 format/digest 工具 |

### 3.4 代码重复留意

`require_sha256_digest` 在代码库中存在多份本地副本：`audit.py`、`api.py`、`evidence.py`、`tool_runtime.py`、`tool_duplicate_governance.py`。`state.py` 本次正确使用了 centralized `_validation.py` 版本，没有新增第 6 份副本。这是正面的模式选择。其他模块的重复属于既有技术债，不在本 fix 范围内。

---

## 4. 测试、Pyright、真实环境验证审查

### 4.1 测试覆盖

**新增 4 个测试：**

| 测试 | 文件 | 行号 | 覆盖目标 |
|---|---|---|---|
| `test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref` | `tests/host/test_toolruntime_executor.py` | 2179 | ToolRuntime 从 Engine snapshot 派生完整 WaitSnapshotRef（含 digest） |
| `test_awaiting_accept_persists_complete_snapshot_ref` | `tests/host/test_wait_awaiting_accept.py` | 113 | Accept port 将完整 snapshot ref 写入 `host_wait_records` |
| `test_wait_snapshot_ref_rejects_invalid_digest` | `tests/host/test_wait_record_state.py` | 376 | `WaitSnapshotRef` 构造阶段拒绝无效 digest |
| `test_deserialize_wait_snapshot_ref_rejects_missing_digest` | `tests/host/test_wait_record_state.py` | 390 | 三列反序列化阶段拒绝缺失 digest |

**覆盖间隙：**

- `_wait_snapshot_digest` 本身无独立单元测试，其行为通过 integration 测试间接覆盖。由于函数为纯函数且逻辑简单（2 个字段 → digest），间接覆盖可接受。
- `snapshot=None` 路径无新增测试，但已有测试充分覆盖（`test_awaiting_accept_creates_wait_record_and_waiting_state` 使用 `snapshot_ref=None` 的 candidate）。

**测试质量：**

- 新测试使用稳定 fixture（固定 datetime 与 `sha256_digest_json` 预期值），不依赖环境状态
- `test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref` 对 digest 的断言使用与生产代码相同的 `sha256_digest_json` 计算作为预期值 — 正确，因为 digest 输出必须是确定的且可独立验证
- 已通过 `pytest -x -q`：94 passed in 7.24s

### 4.2 Type Check

```text
pyright: 0 errors, 0 warnings, 0 informations
```

已确认：
- `WaitSnapshotRef.snapshot_digest: str` → `_require_sha256_digest(value: str, ...)` 类型匹配
- `_wait_snapshot_digest` 返回 `str` → `snapshot_digest` 参数类型匹配
- `deserialize_wait_snapshot_ref` 的 `snapshot_digest: str | None` 参数 → `WaitSnapshotRef(snapshot_digest=snapshot_digest)` 经过 `None` 检查后 type-narrowed 为 `str`

### 4.3 真实环境验证

Codex fix artifact（`docs/reviews/wu-cli-smoke-01-manual-validation-fix-codex.md`）记录了完整的真实环境验证：

- 命令：`dayu-cli --workspace workspace --log-level debug --log-file ... prompt --label codex-manual-f01-after "下载Visa财报"`
- 关键日志确认：`host.waiting.accept_tool_awaiting.committed`、`engine.agent.tool_awaiting`、`terminal_type=run_suspended`
- 负向搜索：`HostDurableError`、`tool_result_accepted.*failed`、`tool_executor_exception` 均无匹配
- DB 证据：`host_wait_records` 包含完整的 `snapshot_ref` / `snapshot_captured_at` / `snapshot_digest`
- git diff --check: 通过

### 4.4 自动验证

| 验证项 | 结果 |
|---|---|
| `pytest tests/host/test_wait_record_state.py tests/host/test_toolruntime_executor.py tests/host/test_wait_awaiting_accept.py -q` | 94 passed |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | pass (no output) |

---

## 5. README 更新审查

### 5.1 `dayu/host/README.md`

按 AGENTS 触发规则：`dayu/host/` 修改 → 检查 `dayu/host/README.md`。

`dayu/host/README.md` 的 `Agent更新约束【必须遵守】` 规定文档只写两类内容：
1. 整个 Agent 的设计意图、架构边界
2. `dayu.host` 的开发接口、公共契约、架构、稳定边界、主要组件、关键执行路径、状态机、事件流、关键机制、扩展点

本次修改：
- 不涉及公共 API、状态机、事件流、扩展点变更
- 不改变 Host 的架构边界或设计意图
- `WaitSnapshotRef.snapshot_digest` 类型收紧是 internal durable type 修正
- `deserialize_wait_snapshot_ref` 的 fail-fast 是 internal codec hardening

**结论：不需要更新 `dayu/host/README.md`。** ✓

### 5.2 `tests/README.md`

按 AGENTS 触发规则：`tests/` 修改 → 检查 `tests/README.md`。

本次修改只在既有 Host 测试分层（`tests/host/test_toolruntime_executor.py`、`tests/host/test_wait_awaiting_accept.py`、`tests/host/test_wait_record_state.py`）中增加回归测试，不新增测试层级或运行方式。

**结论：不需要更新 `tests/README.md`。** ✓

### 5.3 `docs/host/issues-implementation-control.md`

控制文档的更新（status line、next entry point、blocking open questions、WU-CLI-SMOKE-01 状态段落）准确反映了从 "MANUAL-F01 blocks final closeout" 到 "MANUAL-F01 fix ready for review" 的状态迁移。

---

## 6. Findings

### F-LOW-01: snapshot digest 内容范围仅覆盖 `snapshot_id` + `captured_at`，未来 ToolAwaitSnapshot 扩展需同步评估

- **位置**：`dayu/host/tool_runtime.py:6977-6982`
- **严重性**：low（非阻塞）
- **描述**：`_wait_snapshot_digest` 的输入只覆盖 `ToolAwaitSnapshot` 的当前两个字段 (`snapshot_id`, `captured_at`)。如果未来 `ToolAwaitSnapshot` 新增字段（如 `snapshot_kind`、`provider_context`），digest 不会自动包含新字段，可能导致两个快照产生相同 digest 但语义不同。
- **当前评估**：`ToolAwaitSnapshot` 是 Engine 公共契约中的 closed dataclass (`frozen=True, slots=True`)，设计文档明确"不预留任意属性袋"。`snapshot_id` 是 unique identifier，digest 只需在单个 wait record 生命周期内稳定。当前 digest 输入已经足以区分不同快照（`snapshot_id` 唯一）。
- **已记录的 residual risk**：Codex fix artifact 已列为残余风险："如果未来 snapshot contract 扩展可检索内容，需要同步评估 digest 输入是否应扩展"。不需要在本 fix 中处理。
- **裁决**：accepted（已由 Codex fix artifact 记录为 residual risk，无需重复处理）

---

## 7. 验证复跑

审查者独立复跑了以下验证：

```text
pyright                      → 0 errors, 0 warnings, 0 informations
pytest (3 files, 94 tests)   → 94 passed in 7.24s
git diff --check             → pass (no output)
```

---

## 8. Summary

| 维度 | 裁决 |
|---|---|
| Root cause 修复完整性 | ✓ 正确修复了 `_wait_snapshot_ref` 的 `snapshot_digest=None` 硬编码 |
| Python invariant hardening 正确性 | ✓ `WaitSnapshotRef.snapshot_digest` 收紧 + `deserialize_wait_snapshot_ref` 三列配对与 SQLite CHECK 约束一致 |
| 无破坏性副作用 | ✓ 已确认所有 `WaitSnapshotRef` 构造路径、序列化/反序列化路径与测试用例均兼容 |
| 无过度设计 | ✓ 最小修复，无新抽象、无新公共 API |
| 无层间污染 | ✓ 不改变 Engine/Fins contract，不泄漏 Host 内部实现 |
| 测试充分 | ✓ 4 个新测试覆盖构造/持久化/拒绝路径，已有 round-trip 测试仍通过 |
| pyright | ✓ 0 errors |
| 真实环境验证 | ✓ 已通过 `dayu-cli prompt "下载Visa财报"` 验证 |
| README 更新 | ✓ 不需要更新 `dayu/host/README.md` 或 `tests/README.md` |
| 控制文档同步 | ✓ `issues-implementation-control.md` 状态准确 |

**Verdict: pass** — 无 required fix。可推进至 WU-CLI-SMOKE-01 final closeout gate。
