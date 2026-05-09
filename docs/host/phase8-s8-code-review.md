# Host P8-S8 Code Review：Durable Conversation Memory Store / Read Model Rebuild

- **Branch**: `migration/host-p8-attempt-lease-recovery`
- **Baseline**: `90f5c5d host: add p8 multiprocessing stress tests`
- **Review date**: 2026-05-09
- **Reviewer**: Host P8-S8 Code Review Agent (Claude)
- **Review scope**: P8-S8 entry 工作树差异（durable memory store / observer upgrade / test migration / docs）

## 结论：PASSED — F1-F4 已修复，F5 deferred-with-owner: P9

**Controller 决策（2026-05-09）**：F1/F2/F3/F4 已 `accepted — fixed`；F5 `deferred-with-owner: P9`，不阻塞 S8 收口。F3 采用 utils 私有 helper 方案 ：在 `utils/_smoke_memory_store.py` 新增 `SmokeInMemoryConversationMemoryStore`，明确 smoke-only 命名，避免 `utils/` → `tests/` 反向依赖；不放回 production `dayu/host/`。

P8-S8 核心设计正确：durable snapshot table + observer 同事务投影 + startup_reconcile 重投恢复 + production InMemory 彻底删除。JSON encode/decode 结构化、schema 稳定、并发安全、幂等恢复路径覆盖。但有 4 项需修复（1 medium + 3 low），1 项 advisory deferred。

`pytest tests/host -q` 291 passed，`python -m pyright dayu/host tests/host utils` 0 errors，`git diff --check` clean。

---

## 验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| durable memory recovery 测试 | `pytest tests/host/test_phase8_durable_memory_recovery.py -q` | 7 passed in 0.16s |
| memory projection + rebuild 回归 | `pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase6_memory_rebuild.py -q` | 16 passed |
| durable harness 集成 | `pytest tests/host/test_phase6_durable_harness_integration.py -q` | 2 passed |
| Host 全量回归 | `pytest tests/host -q` | 291 passed in 2.36s |
| 类型检查 | `python -m pyright dayu/host tests/host utils` | 0 errors / 0 warnings / 0 informations |
| 空白错误 | `git diff --check` | clean |

---

## Slice 边界审查

### 1. Slice 边界

- ✅ 只实现 P8-S8 durable conversation memory read model / rebuild。未实现 P9 Session / Run admission、public memory API、UI/Service recovery。
- ✅ 未修改 EventLog schema。`_conversation_memory_durable.py` 只新增 `host_conversation_memory_snapshots` 表。
- ✅ 未修改 projection checkpoint 语义。`startup_reconcile` 复用既有 `ProjectionCoordinator.drain()` 路径。
- ✅ 未引入 observer claim / lease。
- ✅ 未把业务 long-term memory 塞进 Host。
- ✅ 未把 owner token / scope token / raw cursor / 大 prompt / 大 tool result 写入 memory storage。JSON payload 只存 `RunEventCursor(sequence=int)` 与摘要文本。

### 2. Production InMemory 删除彻底性

- ✅ `dayu/host/_conversation_memory.py`：`InMemoryConversationMemoryStore` 类已删除（117 行移除），`__all__` 已移除对应导出。
- ✅ `dayu/` production 路径不再依赖 production InMemory。`grep -R "InMemoryConversationMemoryStore" dayu/` 仅在 docstring / 注释中以 ```` ``InMemoryConversationMemoryStore`` ```` 形式保留历史说明。
- ✅ `build_durable_harness` 默认装配改为 `open_durable_conversation_memory_store(storage)`。
- ✅ `tests/host/_memory_store_fake.py` 确实 tests-only，`__all__` 只导出 `FakeInMemoryConversationMemoryStore`。
- ⚠ `utils/smoke_host_*.py` import `tests.host._memory_store_fake`：见 F3。

### 3. Durable memory schema 与实现

- ✅ schema 清楚：`host_conversation_memory_snapshots(session_id PK, snapshot_payload TEXT, updated_at TEXT)`，由 `ensure_durable_memory_schema` 通过 `CREATE TABLE IF NOT EXISTS` 初始化。
- ⚠ 文档/报告/实现不一致：见 F1。
- ✅ `DurableConversationMemoryStore.project_run_events_in_transaction(tx=...)` 不嵌套开启事务。observer 路径直接调用 `_project_in_tx(tx=tx, events=events)`，不获取 `_lock`（observer 串行由 `ProjectionCoordinator._drain_lock` 保证）。
- ✅ `project_run_events(...)` 仅用于非 observer convenience，自行开 `self.storage.transaction()` 后委托同事务版本。
- ✅ `get_snapshot` 从 durable table 读，不存在时返回空 snapshot（`_empty_snapshot(session_id)`）。
- ✅ `apply_patch` 持久化 reset / SESSION clear / claim correction，行为与原 `InMemoryConversationMemoryStore` 语义一致。非 SESSION scope clear 抛 `ValueError`。
- ✅ 并发安全：非 observer 路径通过 `asyncio.Lock` + SQLite `BEGIN IMMEDIATE` 双重保护；observer 路径由 `ProjectionCoordinator` 串行化。`ON CONFLICT DO UPDATE` upsert 保证重投幂等。

### 4. Projection 同事务不变量

- ✅ `MemoryProjectionObserver.process(tx=...)` 调用 `self.memory_store.project_run_events_in_transaction(tx=tx, events=events)`。
- ✅ memory snapshot 写入失败时，事务整体回滚，`ProjectionCoordinator` checkpoint 不推进。
- ✅ observer `_pending_by_run` 在写入失败时仍保持 at-least-once 不变量（staged 副本机制未改动）。
- ✅ 未使用 `hasattr` / `getattr` 做 transaction-aware 胶水 seam。
- ✅ `ConversationMemoryProjectionStore` 是 Host internal 边界（在 `_memory_projection.py` 的 `__all__` 中，但不在 `dayu.host.__init__` 的 public exports 中）。

### 5. startup_reconcile / caught-up checkpoint + missing memory rebuild

- ✅ 测试 `test_startup_reconcile_recovers_snapshot_after_crash_before_projection` 覆盖：
  - EventLog 已落库但 drain 未执行（模拟崩溃前 projection 未持久化）。
  - `startup_reconcile()` 重投 EventLog 把 snapshot 写回。
  - 重复 `startup_reconcile()` 幂等（snapshot 内容不变）。
- ✅ 重投通过 `_project_in_tx` 的 upsert 语义保证幂等：`_read_snapshot_in_tx` 读现有 snapshot → `_project_canonical_events_helper` 合并 → `_write_snapshot` upsert。同一事件重投不会重复 raw turns / tool facts（canonical 投影 helper 按 `RunEventCursor.sequence` 去重合并）。
- ✅ 不倒退 checkpoint、不破坏 EventLog。`startup_reconcile` 复用 `ProjectionCoordinator.drain()` 只推进 `host_projection_checkpoints`。
- ⚠ 当前测试只覆盖"drain 未执行 + reconcile 恢复"场景，未覆盖"drain 已执行一半 + 进程崩溃 + reconcile 补齐"场景。见 F5 advisory。

### 6. JSON encode/decode

- ✅ 结构化 `_encode_*` / `_decode_*` helper，不使用 ad hoc 字符串拼接。
- ✅ 覆盖类型：
  - `ConversationMemorySnapshot` ✅
  - `ConversationRawTurn` ✅
  - `ConversationToolFact` ✅
  - `EvidenceAnchor` ✅
  - `MemoryProvenance` ✅
  - `ConversationPinnedState` ✅
  - `TaskFrame` ✅
  - `MemoryClaim` ✅
  - `AssumptionRegister` ✅
  - `UserPreferenceProfileRef` ✅
  - enums (`ClaimStatus`, `MemoryScope`, `MemoryProducerKind`, `MemoryIngestionPolicy`, `MemoryTrustLevel`, `RunEventType`) ✅
  - datetime ✅
- ✅ encode 写入 `schema_version: 1`。
- ⚠ decode 不验证 `schema_version` 值。见 F4。
- ✅ decode 对缺字段/错类型抛 `ValueError`（`_decode_str` / `_decode_int` / `_decode_object` / `_decode_array` / `_decode_str_tuple` 均 raise `ValueError`）。
- ✅ 使用项目 `JsonValue`（`_JsonObject: TypeAlias = Mapping[str, JsonValue]`），未扩散 `Any` / `object` 签名。
- ✅ 不把 token / raw cursor / 大结果写入 payload。
- ✅ `test_snapshot_json_encode_decode_roundtrip` 覆盖包含全部字段（含 tool facts、evidence anchors、provenance、claims、pinned state、task frame、user preference ref）的完整 roundtrip。
- ⚠ roundtrip 测试 snapshot 的 `recent_raw_turns` / `older_raw_turns` / `tool_facts` 为空元组。见 F5 advisory。

### 7. `_conversation_memory_durable.py` import 边界

- ✅ 模块顶部已有 `from dayu.host._conversation_memory import (...)` 批量导入（lines 36-56）。
- ⚠ 模块中部 line 103 又有 `from dayu.host._conversation_memory import _project_canonical_events as _project_canonical_events_helper  # noqa: E402`。见 F2。

### 8. `_run_harness.py` 默认 factory 改动

- ✅ `_require_memory_store()` 抛 `RuntimeError`，错误消息清晰（"LocalRunHarness 必须显式传入 memory_store: production InMemoryConversationMemoryStore 已在 P8-S8 删除"）。
- ✅ `_build_default_harness()` 使用 `:memory:` SQLite + `open_durable_conversation_memory_store` 作为 legacy 顶层 `start_run` 便利入口。
- ✅ `_build_default_harness()` 的 lazy import 有合理理由：避免 `_run_harness` ↔ `_durable_harness` 循环依赖（`_durable_harness` import `_run_harness` 中的 `LocalRunHarness`）。
- ✅ 不破坏 non-durable tests / smoke：tests 使用 `FakeInMemoryConversationMemoryStore` 显式注入；smoke 同样显式注入。

### 9. 测试迁移

- ✅ 旧依赖 production InMemory 的测试已迁移：`test_phase3_conversation_memory_projection.py`、`test_phase6_memory_rebuild.py`、`test_phase3_multiturn_smoke.py`、`test_phase4_overflow_retry.py`、`test_phase1_run_harness.py`、`test_phase1_5_run_harness_eventlog.py`、`test_phase3_boundary.py`、`test_phase6_review_fixes.py` 均改为 import `FakeInMemoryConversationMemoryStore`。
- ✅ 测试 fake 在 `tests/host/_memory_store_fake.py`（下划线前缀私有 helper）。
- ⚠ `test_phase6_memory_rebuild.py:26` 和 `test_phase3_conversation_memory_projection.py:37` 使用 `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore` 别名。见 F4。
- ✅ `test_phase8_durable_memory_recovery.py` 覆盖：
  - 默认 durable harness 装配 ✅
  - reopen file SQLite 后 snapshot 持久 ✅
  - checkpoint 未推进 + memory 丢失时 startup_reconcile 恢复 ✅
  - repeat startup_reconcile 幂等 ✅
  - apply_patch 持久（reset / SESSION clear / claim correction / 非 SESSION scope ValueError）✅
  - JSON roundtrip ✅
  - production InMemory 残留扫描 ✅

### 10. 文档与 residual risk

- ✅ `dayu/host/README.md` 只写当前事实，已更新为 `DurableConversationMemoryStore` 描述，不再暗示 in-memory store 可用于 durable path。
- ✅ `tests/README.md` 说明 durable memory recovery 与 tests fake。
- ✅ `docs/host/migration-plan.md` 将 P8-S8 标记 `resolved`，下一入口 P8-S9 smoke。
- ⚠ `migration-plan.md:73-74` 引用 `session_memory + session_memory_events` 但代码实际只用 `host_conversation_memory_snapshots`。见 F1。

---

## Findings

### F1 — 严重: MEDIUM｜状态: accepted — fixed — artifact consistency

**入口/函数**: `docs/host/migration-plan.md` §1 P8-S8 描述段

**文件(行号)**: `docs/host/migration-plan.md:73-74`

**输入场景**: 读者按 migration plan 理解 S8 实现

**实际分支**: plan 写 `session_memory + session_memory_events`

**预期行为**: 文档表名应与代码一致

**实际行为**: `migration-plan.md:73-74` 写 "SQLite read model（`session_memory` + `session_memory_events`）"，但 `_conversation_memory_durable.py` 实际只有一张表 `host_conversation_memory_snapshots`，没有 `session_memory` 或 `session_memory_events` 表。

**直接证据**:
- `docs/host/migration-plan.md:73-74`: "`session_memory` + `session_memory_events`"
- `dayu/host/_conversation_memory_durable.py:76`: `_TABLE_NAME: str = "host_conversation_memory_snapshots"`
- `dayu/host/_conversation_memory_durable.py:80-88`: `_SCHEMA_STATEMENTS` 只有 `host_conversation_memory_snapshots` 一张表

**影响**: 文档读者会误以为有两张表，与实际 schema 不一致；后续开发者可能按错误表名写查询或 migration。

**建议改法和验证点**: 把 `migration-plan.md:73-74` 改为 "`host_conversation_memory_snapshots`"；同步检查 `phase8-plan.md` S8 描述段是否有相同错误。

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 中

---

### F2 — 严重: LOW｜状态: accepted — fixed — noqa: E402 lazy import without justification

**入口/函数**: `DurableConversationMemoryStore` 模块级

**文件(行号)**: `dayu/host/_conversation_memory_durable.py:102-105`

**输入场景**: 模块 import 顺序审查

**实际分支**: line 103 `from dayu.host._conversation_memory import _project_canonical_events as _project_canonical_events_helper  # noqa: E402 循环友好惰性`

**预期行为**: 同一来源的 import 应集中在模块顶部；若存在循环依赖需 lazy import，应有明确技术理由

**实际行为**: 模块顶部（lines 36-56）已有 `from dayu.host._conversation_memory import (...)` 批量导入 18 个符号。`_project_canonical_events` 也是从 `_conversation_memory` 导入，却单独放在 line 103，用 `noqa: E402` 抑制 lint。注释说"循环友好惰性"，但 `_conversation_memory` 不 import `_conversation_memory_durable`，不存在循环依赖。`as _project_canonical_events_helper` 重命名也无必要。

**直接证据**:
- `dayu/host/_conversation_memory_durable.py:36-56`: 顶部已有 `_conversation_memory` 批量导入
- `dayu/host/_conversation_memory_durable.py:103`: `noqa: E402` lazy import
- `dayu/host/_conversation_memory.py`: 不 import `_conversation_memory_durable`，无循环

**影响**: 违反 AGENTS.md "禁止胶水 seam，使用 lazy import 必须有充分理由"；增加阅读成本。

**建议改法和验证点**: 把 `_project_canonical_events` 移到 lines 36-56 的批量导入中，删除 `noqa: E402` 和 `as _project_canonical_events_helper` 别名，全文替换 `_project_canonical_events_helper` → `_project_canonical_events`。重跑 `pytest tests/host/test_phase8_durable_memory_recovery.py -q` + `python -m pyright`。

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

### F3 — 严重: LOW｜状态: accepted — fixed — utils/ import tests.host 边界

**入口/函数**: 4 个 `utils/smoke_host_*.py` 脚本

**文件(行号)**:
- `utils/smoke_host_conversation_memory.py:64`
- `utils/smoke_host_eventlog.py:61`
- `utils/smoke_host_multiturn_no_governance.py:116-118`
- `utils/smoke_host_tool_runtime.py:34`

**输入场景**: `utils/` smoke 脚本 import 边界审查

**实际分支**: `from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore`

**预期行为**: `utils/` 属于项目生产/辅助代码目录，不应依赖 `tests/` 私有 helper

**实际行为**: 4 个 smoke 脚本 import `tests.host._memory_store_fake.FakeInMemoryConversationMemoryStore`。fake 的 docstring 写 "仅供 tests/host 与 utils smoke 使用"，但 `utils/` import `tests/` 违反常规分层：若未来 `tests/` 不随 production 打包，smoke 脚本会 break。

**直接证据**:
- `utils/smoke_host_conversation_memory.py:64`: `from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore`
- `tests/host/_memory_store_fake.py:1-7`: docstring 声明 "仅供 tests/host 与 utils smoke 使用"

**影响**: 当前开发环境可工作；但 `utils/` 依赖 `tests/` 是架构边界弱化。若后续打包或 CI 隔离 tests/，smoke 会 import 失败。

**建议改法和验证点**: 两种方案：(a) 把 `FakeInMemoryConversationMemoryStore` 移到 `dayu/host/_conversation_memory_fake.py`（标注 tests/smoke only），utils 和 tests 都从 `dayu.host` 导入；(b) 接受当前边界并在 fake docstring / tests README 中显式声明 `utils/` 依赖 `tests.host` 的约定。方案 (a) 更干净但改动更大；方案 (b) 是有意识的 trade-off。需 controller 决策。

**修复风险（低/中/高）**: 低（方案 b）/ 中（方案 a）

**严重程度（低/中/高/严重）**: 低

---

### F4 — 严重: LOW｜状态: accepted — fixed — test alias 制造误导

**入口/函数**: 2 个测试文件的 import alias

**文件(行号)**:
- `tests/host/test_phase6_memory_rebuild.py:25-27`
- `tests/host/test_phase3_conversation_memory_projection.py:36-38`

**输入场景**: 测试 import 审查

**实际分支**: `from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore`

**预期行为**: production InMemory 已删除后，测试应使用新名字 `FakeInMemoryConversationMemoryStore`，不保留旧名 alias

**实际行为**: 两个测试文件把 fake alias 为 `InMemoryConversationMemoryStore`，最小化 diff 但制造"production InMemory 仍存在"的假象。`test_phase8_durable_memory_recovery.py:439-468` 的残留扫描只检查 `dayu/` production 目录，不检查 `tests/` 中的 alias。

**直接证据**:
- `tests/host/test_phase6_memory_rebuild.py:26`: `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore`
- `tests/host/test_phase3_conversation_memory_projection.py:37`: 同上
- `tests/host/test_phase8_durable_memory_recovery.py:443`: 扫描范围仅 `repo_root / "dayu"`

**影响**: 阅读者可能误以为 production InMemory 仍在使用；grep `InMemoryConversationMemoryStore` 会在 tests/ 中持续命中，干扰后续清理判断。

**建议改法和验证点**: 把两个文件的 alias 去掉，直接使用 `FakeInMemoryConversationMemoryStore`（或简写 `FakeMemoryStore`），并全文替换测试中 `InMemoryConversationMemoryStore` 的引用。重跑 `pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase6_memory_rebuild.py -q`。

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

### F5 — 严重: LOW｜状态: deferred-with-owner: P9 advisory — partial drain + crash recovery 与 roundtrip 覆盖

**入口/函数**: `test_phase8_durable_memory_recovery.py`

**文件(行号)**:
- `tests/host/test_phase8_durable_memory_recovery.py:193-235` (reconcile 测试)
- `tests/host/test_phase8_durable_memory_recovery.py:420-427` (roundtrip 测试)

**输入场景**: 更强的 recovery 与 encode/decode 覆盖

**实际分支**: 测试只覆盖 "drain 完全未执行 + reconcile 恢复" 和 "全字段空 turns/facts roundtrip"

**预期行为**: 应额外覆盖 (a) drain 已执行一半（timeline/audit checkpoint 推进但 memory observer 未完成）后崩溃 + reconcile 补齐；(b) roundtrip 包含非空 `recent_raw_turns` / `tool_facts`

**实际行为**: 当前测试路径是"完全不 drain → reconcile 全量重投"。若 drain 已部分完成（部分 observer checkpoint 推进、memory observer 未完成），`startup_reconcile` 只重投 checkpoint 之后的事件，此时 snapshot 需要从已有 checkpoint 位置续投——该路径未直接覆盖。roundtrip 的 `recent_raw_turns` / `older_raw_turns` / `tool_facts` 为空元组，未测非空 encode/decode。

**直接证据**:
- `test_phase8_durable_memory_recovery.py:218-219`: `# 故意不调用 drain`
- `test_phase8_durable_memory_recovery.py:410-417`: `recent_raw_turns=(), older_raw_turns=(), tool_facts=()`

**影响**: upsert 语义和 `_project_canonical_events_helper` 的合并逻辑在部分重投路径下理论上正确（因为每次都是 read-modify-write），但未被测试直接证明。roundtrip 空 turns/facts 不验证 `_encode_raw_turn` / `_decode_raw_turn` / `_encode_tool_fact` / `_decode_tool_fact` 的实际序列化。

**建议改法和验证点**: 在 P9 或 P8-S10 收口时补一个测试：先 drain 一部分事件（例如只 drain 到第一个 terminal 之前的 checkpoint），然后模拟崩溃、再 reconcile，验证 snapshot 恢复完整。roundtrip 补一个包含非空 turns/facts 的 snapshot。不阻塞 S8。

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

## Residual Risks 与 Owner

| Risk | Owner | 备注 |
|------|-------|------|
| `startup_reconcile` 自动 wire 到生产 Host 启动路径 | P9 / Session lifecycle | `migration-plan.md` 已标记 `deferred-with-owner: P9`；S8 只提供显式入口 |
| public memory API / admission | P9 / issue #24 | S8 非目标明确 |
| 慢硬盘 / Docker Linux stress | issue #38 | 不阻塞 S8 |
| partial drain + crash recovery 测试补强 | P9 advisory | 见 F5，不阻塞 S8 |
| JSON schema_version 前向兼容验证 | 后续 schema 演进 | V1 → V2 时需在 decode 中加版本检查 |
| ~~`tests/` alias `InMemoryConversationMemoryStore` 残留~~ | ~~P8-S8 fix 或 P16~~ | F4 已 fixed：alias 已删除，直接使用 `FakeInMemoryConversationMemoryStore` |

---

## 建议

1. **F1 已修**（文档表名一致性）：`migration-plan.md` 已改为 `host_conversation_memory_snapshots`。
2. **F2 已修**（lazy import）：`_project_canonical_events` 已移至模块顶部批量导入。
3. **F4 已修**（test alias）：`as InMemoryConversationMemoryStore` 别名已删除，直接使用 `FakeInMemoryConversationMemoryStore`。
4. **F3 已修**（utils → tests 边界）：controller 决策采用 utils 私有 helper 方案，`utils/_smoke_memory_store.py` 新增 `SmokeInMemoryConversationMemoryStore`，smoke 不再 import `tests.host._memory_store_fake`。
5. **F5 deferred-with-owner: P9**：partial drain + crash recovery 与 non-empty turns/facts roundtrip 测试补强不阻塞 S8。
6. 修复后重跑：`pytest tests/host/test_phase8_durable_memory_recovery.py tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase6_memory_rebuild.py -q` + `python -m pyright dayu/host tests/host utils`。
