# WU-CLI-SMOKE-01 / MANUAL-F01 实现 Code Review — AgentMiMo

## 结论

**pass**

MANUAL-F01 root cause 修复正确、完整、符合分层约束。`WaitSnapshotRef.snapshot_digest` 从 `str | None` 收紧为必填 `str` 是 schema 不变量的自然补齐，不是过度设计。测试覆盖了构造、反序列化和真实持久化路径。无 blocking finding。

## 审查范围

- `dayu/host/tool_runtime.py`：`_wait_snapshot_ref(...)` 和新增 `_wait_snapshot_digest(...)`。
- `dayu/host/durable/state.py`：`WaitSnapshotRef` 类型收紧和 `deserialize_wait_snapshot_ref(...)` 三列同存同缺校验。
- `dayu/host/durable/_validation.py`：`require_sha256_digest` 已有，本次只是 import。
- `tests/host/test_toolruntime_executor.py`：新增 snapshot digest 派生测试。
- `tests/host/test_wait_awaiting_accept.py`：新增 snapshot ref 持久化测试。
- `tests/host/test_wait_record_state.py`：新增 digest 校验和反序列化拒绝测试。
- `docs/host/issues-implementation-control.md`：状态更新。

## 审查维度

### 1. Root Cause 修复正确性

**通过。**

MANUAL-F01 的 root cause 是 `dayu/host/tool_runtime._wait_snapshot_ref(...)` 把 Engine `ToolAwaitSnapshot(snapshot_id, captured_at)` 转为 Host `WaitSnapshotRef` 时写入 `snapshot_digest=None`。Fins awaiting 工具会生成 snapshot，导致 Host insert `host_wait_records` 时形成 `snapshot_ref` / `snapshot_captured_at` 非空而 `snapshot_digest` 为空，违反 durable schema 三字段同存同缺 CHECK 约束。Engine 把 `HostDurableError` 归一为 failed tool result，用户看到的是工具路径失败。

修复方式：新增 `_wait_snapshot_digest(snapshot)` 使用 Host durable `format_utc_timestamp(...)` + `sha256_digest_json(...)` 对 `snapshot_id` 和 `captured_at` 计算稳定 digest。这是 Host 层自主派生，不依赖 Engine 提供 digest，符合 Host 是 durable truth owner 的架构约束。

关键证据：
- `dayu/host/tool_runtime.py:6970-6982`：`_wait_snapshot_digest` 实现。
- `dayu/host/tool_runtime.py:6963-6967`：`_wait_snapshot_ref` 调用新 digest 计算。
- 真实 `dayu-cli prompt "下载Visa财报"` 日志确认 `host.waiting.accept_tool_awaiting.committed` 和 `host_wait_records` 包含完整 snapshot ref / captured_at / digest。
- 负向搜索 `HostDurableError|tool_result_accepted.*failed` 无匹配。

### 2. Durable State Schema 收紧

**通过。**

`WaitSnapshotRef.snapshot_digest` 从 `str | None` 收紧为 `str`，并使用 `require_sha256_digest` 校验格式。这是 schema 不变量的自然补齐：durable CHECK 约束已经要求三列同存同缺，Python 层类型只是反映了已有约束。

`deserialize_wait_snapshot_ref(...)` 从检查 `snapshot_id is None or captured_at is None` 改为 `snapshot_id is None or captured_at is None or snapshot_digest is None`，确保 Python row codec 层在构造 `WaitSnapshotRef` 前就拒绝不完整引用，避免同类错误推迟到 SQLite CHECK 才暴露。

分层合规：
- `WaitSnapshotRef` 是 Host durable 内部类型，收紧不影响 Engine 公共契约。
- `deserialize_wait_snapshot_ref` 是 Host durable 私有 codec，收紧是防御性加固。
- `require_sha256_digest` 来自 `dayu/host/durable/_validation.py`，是 durable 层内部 helper，不向上泄漏。

### 3. 反向依赖与 Contract 污染

**通过。**

- `tool_runtime.py` 新增 `from dayu.contracts.tool_await import ToolAwaitSnapshot`：这是读取 Engine 公共 contract 的正向依赖（Host 消费 Engine 产出），不是反向依赖。
- `tool_runtime.py` 新增 `from dayu.host.durable.codec import format_utc_timestamp`：这是 Host 内部 durable codec 的正向依赖。
- `_wait_snapshot_digest(...)` 的 digest 计算使用 Host 自有的 `format_utc_timestamp` + `sha256_digest_json`，不依赖 Engine 提供 digest 或 digest 算法。
- 未修改 Engine 公共 contract、Engine 设计真源、Fins 工具逻辑或任何跨层接口。
- 无兼容性胶水、无 `hasattr` / `getattr` 逃逸、无 `Any` / `object` 类型。

### 4. 类型与 Docstring

**通过。**

- `_wait_snapshot_digest(snapshot: ToolAwaitSnapshot) -> str`：签名完整，类型精确，无 `Any` 或无类型参数。
- `_wait_snapshot_ref(outcome: ToolAwaitingOutcome) -> WaitSnapshotRef | None`：返回类型正确，`None` 表示无 snapshot 的合法情况。
- `WaitSnapshotRef.snapshot_digest: str`：收紧为必填，docstring 已更新。
- `deserialize_wait_snapshot_ref` docstring 和异常说明已更新。
- 所有新增/修改函数均有完整中文 docstring，包含参数、返回值、异常。

### 5. 测试覆盖

**通过。**

| 测试 | 覆盖内容 |
|---|---|
| `test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref` | ToolRuntime 从 Engine snapshot 派生完整 `WaitSnapshotRef`，断言 `snapshot_id`、`captured_at`、`snapshot_digest` 均正确。 |
| `test_awaiting_accept_persists_complete_snapshot_ref` | `DefaultHostToolAwaitingAcceptPort` 把完整 snapshot ref 真实写入 `host_wait_records`。 |
| `test_wait_snapshot_ref_rejects_invalid_digest` | `WaitSnapshotRef` 构造阶段拒绝非 sha256 格式 digest。 |
| `test_deserialize_wait_snapshot_ref_rejects_missing_digest` | 三列反序列化拒绝缺失 digest 的不完整引用。 |

94 passed（`test_toolruntime_executor` + `test_wait_awaiting_accept` + `test_wait_record_state`）。pyright 0 errors。`git diff --check` 通过。

真实环境验证：`dayu-cli prompt "下载Visa财报"` 确认 Agent 路径 `start_fins_download` 进入 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED`，`host_wait_records` 包含完整 snapshot ref。

### 6. README 更新

**通过，无需更新。**

修复 artifact 已检查：
- `dayu/host/README.md`：此次变更不改变 Host public API、状态机、扩展点或开发者稳定边界，只是补齐内部 durable snapshot ref digest 和 row codec 不变量。
- `tests/README.md`：只在既有 Host 测试分层内增加回归测试，不新增测试层级或运行方式。

符合 AGENTS README 触发规则。

## Findings

### F01 [informational] 测试 digest 硬编码与 captured_at 不同源

- **文件**: `tests/host/test_wait_awaiting_accept.py:122-133`
- **描述**: `test_awaiting_accept_persists_complete_snapshot_ref` 使用 `_NOW`（`2026-05-16T00:00:00Z`）作为 `captured_at`，但 digest 使用硬编码字符串 `"2026-05-16T01:02:03.000000Z"` 计算。两者时间不同，但测试仍然通过，因为它只验证 snapshot ref 能被持久化和读取，不验证 digest 与 `captured_at` 的派生关系。digest 派生正确性由 `test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref` 覆盖。
- **严重性**: low。功能正确，但不一致可能让未来维护者困惑。
- **建议**: 可选改进，将 digest 计算改为基于 `_NOW` 的 `format_utc_timestamp`，使测试数据自洽。不阻塞当前 gate。

### F02 [informational] digest 输入范围与 contract 演进风险

- **文件**: `dayu/host/tool_runtime.py:6977-6982`
- **描述**: `_wait_snapshot_digest` 只使用 `snapshot_id` 和 `captured_at` 计算 digest，符合当前 `ToolAwaitSnapshot` contract（只有这两个字段）。如果未来 `ToolAwaitSnapshot` 扩展新字段，digest 输入需要同步评估。
- **严重性**: low。fix artifact 已在残余风险中记录此点。
- **建议**: 无需当前动作。contract 演进时重新评估。

## 残余风险

- 真实 CLI 验证在确认 Host awaiting durable 边界修复后被 SIGINT 中止，未等待 Visa 全量外部下载完成。这是外部 job 耗时风险，不是本次 `HostDurableError` 根因。
- digest 输入只覆盖 `snapshot_id` 和 `captured_at`，符合当前 `ToolAwaitSnapshot` contract；contract 扩展时需同步评估。
