# Host P8-S8 Code Review #2：Durable Conversation Memory Store / Read Model Rebuild

- **Branch**: `migration/host-p8-attempt-lease-recovery`
- **Baseline**: `90f5c5d host: add p8 multiprocessing stress tests`
- **Review date**: 2026-05-09
- **Reviewer**: Host P8-S8 Code Review Agent #2 (Claude)
- **Review scope**: P8-S8 工作树差异（`_conversation_memory_durable.py` 新增、production InMemory 删除、smoke/tests 迁移、README/migration-plan 同步）

## 结论：PASSED — F1-F4 已修复，partial drain / non-empty roundtrip deferred-with-owner: P9

**Controller 决策（2026-05-09）**：F1（lazy import）、F2（table name）、F3（utils → tests 边界）、
F4（test alias）已 `accepted — fixed`。F3 采用 utils 私有 helper 方案：在
`utils/_smoke_memory_store.py` 新增 `SmokeInMemoryConversationMemoryStore`，明确 smoke-only 命名，
避免 `utils/` → `tests/` 反向依赖；不放回 production `dayu/host/`。partial drain + crash recovery
与 non-empty turns/facts roundtrip 测试覆盖 `deferred-with-owner: P9`，不阻塞 S8 收口。

P8-S8 slice 严格落在 plan 边界内：production `InMemoryConversationMemoryStore` 已彻底删除；
`DurableConversationMemoryStore` 落地为 SQLite durable read model + 结构化 JSON encode/decode；
`MemoryProjectionObserver` 升级为同事务写入，snapshot 与 checkpoint 在同一 `HostStorageTransaction`
内提交；`build_durable_harness` 默认装配 durable store；`startup_reconcile` 覆盖 crash-before-drain
恢复场景并保持幂等；legacy 测试/smoke 迁移到 `tests/host/_memory_store_fake.py`。`pytest tests/host -q`
291 passed，`pytest tests/host/test_phase8_durable_memory_recovery.py -q` 7 passed，
`python -m pyright dayu/host tests/host utils` 0 errors，`git diff --check` clean。

但仍有 1 项硬约束违反（mid-file lazy import 无充分理由）必须先修。修复后允许进入 user confirmation +
commit gate。

---

## 验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 新 durable memory recovery 测试 | `pytest tests/host/test_phase8_durable_memory_recovery.py -q` | 7 passed in 0.17s |
| P3/P6 memory 回归 | `pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase6_memory_rebuild.py -q` | 16 passed |
| P6/P7 harness 回归 | `pytest tests/host/test_phase6_durable_harness_integration.py tests/host/test_phase7_durable_harness_config.py -q` | 6 passed |
| Host 全量回归 | `pytest tests/host -q` | 291 passed in 2.41s |
| 类型检查 | `python -m pyright dayu/host tests/host utils` | 0 errors / 0 warnings / 0 informations |
| 空白错误 | `git diff --check` | clean |
| Production InMemory 残留扫描 | `rg -n "InMemoryConversationMemoryStore" dayu/` | 仅出现在注释/docstring/错误消息中，无 class/import/call 残留 |

---

## Slice 边界审查（逐项复核 1～10）

### 1. Slice 边界

- ✅ 只实现 P8-S8 durable conversation memory read model / rebuild。
- ✅ 未实现 P9 Session / Run admission、public memory API、UI/Service recovery。
- ✅ 未修改 EventLog schema。
- ✅ 未修改 projection checkpoint 语义；observers 仍按 `host_projection_checkpoints` 已有逻辑工作。
- ✅ 未实现 observer claim / lease。
- ✅ 未把业务 long-term memory 塞进 Host。
- ✅ 未把 owner token / scope token / raw cursor / 大 prompt / 大 tool result 写入 memory storage
  （JSON encode/decode 仅包含 memory 结构字段，schema_version `_SCHEMA_VERSION=1` 限定了
  snapshot 内容面）。

### 2. Production InMemory 删除是否彻底

- ✅ `dayu/host/_conversation_memory.py`：`InMemoryConversationMemoryStore` 类定义已完全删除
  （`_conversation_memory.py` diff：删除 117 行类定义 + `asyncio`/`field`/`dataclass`/`VERBOSE_LOG_LEVEL`
  无关导入）。
- ✅ `__all__` 中 `"InMemoryConversationMemoryStore"` 已移除（`_conversation_memory.py:1010`）。
- ✅ `dayu/` production 路径不再依赖 production InMemory：`rg "InMemoryConversationMemoryStore" dayu/`
  仅在注释/docstring/错误消息中出现，无 `class InMemory`、`from ... import InMemory`、
  `InMemoryConversationMemoryStore(...)` production 实现引用。
- ✅ `tests/host/_memory_store_fake.py` 仅被 `tests/host/` 与 `utils/` smoke 脚本 import，
  不被 production code import。
- ⚠ 4 个 `utils/*smoke*.py` 脚本 import 自 `tests/host/_memory_store_fake`，见 F3。

### 3. Durable memory schema 与实现

- ✅ schema 表名 `host_conversation_memory_snapshots`，字段 `session_id TEXT PRIMARY KEY`、
  `snapshot_payload TEXT NOT NULL`、`updated_at TEXT NOT NULL`，语义清晰。
- ✅ schema 由 `ensure_durable_memory_schema(storage)` 初始化，`open_durable_conversation_memory_store`
  在 `storage.open()` 后调用，保证 schema 先行。
- ⚠ `docs/host/migration-plan.md` 实施报告称"`session_memory` + `session_memory_events`"，
  但实际代码只用了 `host_conversation_memory_snapshots` 一张表。文档表名与代码不一致，见 F2。
- ✅ `project_run_events_in_transaction(tx=...)`：observer 调用时不获取 `_lock`（因
  ProjectionCoordinator 已通过 `_drain_lock` 串行化），不嵌套开启新事务，直接通过传入的
  `tx` 执行 read/modify/write snapshot。
- ✅ `project_run_events(...)`：非 observer convenience 路径，自行获取 `_lock` +
  `storage.transaction()`，委托 `_project_in_tx`。
- ✅ `get_snapshot`：从 durable table 读，不存在时返回空 snapshot（`_empty_snapshot`）。
- ✅ `apply_patch`：reset / SESSION scope clear / claim correction 均走 SQLite 事务持久化，
  非 SESSION scope clear 抛 `ValueError`，行为与原 P3 内存态一致。
- ✅ 并发保护：单进程内 `_lock` 序列化非 observer 调用；observer 路径由
  `ProjectionCoordinator._drain_lock` 保证串行。跨进程下 SQLite WAL + `INSERT ... ON CONFLICT`
  upsert 保证 last-writer-wins；memory projection 是 EventLog 的 at-least-once 派生，重复
  projection 幂等。

### 4. Projection 同事务不变量

- ✅ `MemoryProjectionObserver.process(tx=...)` 调用
  `self.memory_store.project_run_events_in_transaction(tx=tx, events=events)`
  （`_memory_projection.py:138`）。snapshot 写入失败时 observer 抛异常，
  `ProjectionCoordinator._run_once_locked` 不推进 checkpoint——因为 checkpoint advance 在同一
  事务内，异常导致整体回滚。
- ✅ 旧 `del tx` 胶水代码已删除；observer 不再忽略事务参数。
- ✅ `_pending_by_run` at-least-once 不变量：先累积到 staged 副本，全部成功后才替换
  `_pending_by_run` 并清理 terminal run 条目；任何 `await` 异常时控制流不到达提交点。
- ✅ 新 protocol `ConversationMemoryProjectionStore` 继承 `ConversationMemoryStore`，
  定义在 `_memory_projection.py` 中，是 Host internal 边界。未进入 `dayu.host.__init__`
  public exports。
- ✅ 无 `hasattr` / `getattr` 做 transaction-aware 胶水 seam。

### 5. `startup_reconcile` / caught-up checkpoint + missing memory rebuild

- ✅ `test_startup_reconcile_recovers_snapshot_after_crash_before_projection` 覆盖：
  1. EventLog 已有 terminal run 事件；
  2. `drain()` 未调用（模拟崩溃前未投影）；
  3. `startup_reconcile()` 重投 EventLog，memory observer 写入 snapshot；
  4. snapshot 已恢复（`recent_raw_turns` 包含本轮 user text）；
  5. 重复 `startup_reconcile()` 幂等：第二次调用后 snapshot 不变。
- ✅ 同事务设计保证 "checkpoint 已 caught up 但 snapshot 缺失" 窗口不会发生：checkpoint
  advance 与 snapshot upsert 在同一 `HostStorageTransaction` 内提交；如果 checkpoint
  存在，snapshot 必然同时存在。
- ✅ "checkpoint caught up + snapshot 丢失" 只在外部 SQLite 数据损坏时可能发生；这是
  Host 外数据完整性问题，不属于 Host 恢复治理范围。
- ✅ `startup_reconcile` 不倒退 checkpoint、不破坏 EventLog。
- ✅ 重投路径不重复 raw turns/tool facts/evidence anchors（projection helper 幂等）。
- ⚠ 当前测试只验证 "crash before drain" 场景；未直接测试 "先 drain → 外部手工
  删除 snapshot row → startup_reconcile 重建" 这种伪场景（因为重建需要
  重置 checkpoint，不属于 S8 设计）。见 Residual Risk #1。

### 6. JSON encode/decode

- ✅ 结构化 `_encode_snapshot` / `_decode_snapshot` 递归 helper 覆盖：
  - `ConversationMemorySnapshot`
  - `ConversationRawTurn`（含 optional `assistant_provenance` / `terminal_provenance`）
  - `ConversationToolFact`（含 optional `has_more` bool / None）
  - `EvidenceAnchor`（含 optional nullable 字段）
  - `MemoryProvenance`
  - `ConversationPinnedState`
  - `TaskFrame`
  - `MemoryClaim`
  - `AssumptionRegister`
  - `UserPreferenceProfileRef`
  - enums（`ClaimStatus`、`MemoryScope`、`MemoryProducerKind`、`MemoryIngestionPolicy`、
    `MemoryTrustLevel`、`RunEventType`）
  - datetime（ISO format）
- ✅ `schema_version` 字段编码进 payload。
- ✅ decode 对缺字段/错类型抛 `ValueError`（`_decode_str`、`_decode_int`、`_decode_object`、
  `_decode_array`、`_decode_datetime` 均有类型守卫）。`_decode_int` 特别处理 bool 子类陷阱。
- ✅ 使用项目 `JsonValue`（通过 `_JsonObject = Mapping[str, JsonValue]`），未扩散
  `Any` / `object` 签名。
- ✅ 不把 token/raw cursor/大结果写入 payload。
- ✅ 测试 `test_snapshot_json_encode_decode_roundtrip` 覆盖完整 snapshot roundtrip，
  含 verified_claims、assumptions、evidence_anchors、provenance。

### 7. `_conversation_memory_durable.py` import 边界

- ❌ 模块中部 lazy import（`_conversation_memory_durable.py:98-100`）：

  ```python
  from dayu.host._conversation_memory import (  # noqa: E402  循环友好惰性
      _project_canonical_events as _project_canonical_events_helper,
  )
  ```

  该 import 位于模块中段（`ensure_durable_memory_schema` 函数之后、`DurableConversationMemoryStore`
  类之前），注释称"循环友好惰性"和"使用相对导入避免 production InMemory 重新泄漏"。
  但：
  - `_conversation_memory_durable.py` 模块顶部已成功 `from dayu.host._conversation_memory
    import (...)` 多个符号（`ConversationMemorySnapshot`、`ConversationRawTurn` 等），
    证明不存在循环依赖；
  - `_conversation_memory.py` 不 import `_conversation_memory_durable.py`；
  - "避免 production InMemory 重新泄漏"可以用 `import ... as` 别名实现，不必须
    lazy import。
  
  AGENTS.md 编码硬约束明确："禁止胶水 seam，使用lazy import必须有充分理由"。
  此处无技术必要，与 P8-S7 F1（`test_phase8_multiprocess_stress.py` 中的 lazy import）
  属于同类违规。见 **F1**。

- ✅ 未从 `_conversation_memory` import 已废弃的 `InMemoryConversationMemoryStore`。
- ✅ 模块顶部 normal imports 使用 `from dayu.host._conversation_memory import (...)`，
  类型边界清晰。

### 8. `_run_harness.py` 默认 factory 改动

- ✅ `LocalRunHarness.memory_store` 默认 factory 从 `InMemoryConversationMemoryStore`
  改为 `lambda: _require_memory_store()`。
- ✅ `_require_memory_store()` 抛 `RuntimeError` 并包含清晰消息：
  `"LocalRunHarness 必须显式传入 memory_store: production InMemoryConversationMemoryStore
  已在 P8-S8 删除"`。调用方必须显式注入 store。
- ✅ `_build_default_harness()`（顶层 `start_run` 便利入口）改为使用 `:memory:` SQLite
  后端的 `DurableConversationMemoryStore`，保持 backward-compatible 的顶层使用体验。
- ⚠ `_build_default_harness()` 创建的 `HostStorage(database_path=":memory:")` 由
  `open_durable_conversation_memory_store` 打开后，`LocalRunHarness` 无 `close()` 方法
  清理该 storage。`:memory:` 连接在进程退出时自动清理，短期不造成资源泄漏，但长期
  建议 `LocalRunHarness` 增加与 durable harness 对齐的 close 语义。见 Residual Risk #2。
- ✅ 所有 `LocalRunHarness(...)` 测试 site（P1、P1.5、P3、P4）已显式传入
  `memory_store=FakeInMemoryConversationMemoryStore()`。

### 9. 测试迁移

- ✅ 旧依赖 production InMemory 的测试全部迁移或删除。
- ✅ 测试 fake `tests/host/_memory_store_fake.py` 为 `tests/host/` 私有 helper。
- ⚠ 多个测试文件使用 `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore`
  别名（`test_phase3_boundary.py:34`、`test_phase3_conversation_memory_projection.py:37`、
  `test_phase6_durable_harness_integration.py:249`、`test_phase6_memory_rebuild.py:26`、
  `test_phase6_review_fixes.py:695`）。该 alias 使得测试代码中仍然出现
  `InMemoryConversationMemoryStore(...)` 调用（如 `test_phase3_boundary.py:358,381,408,483`），
  虽然实际构造的是 `FakeInMemoryConversationMemoryStore`，但代码阅读上容易造成
  "production InMemory 仍存在" 的误导。见 F4。
- ✅ 新 `test_phase8_durable_memory_recovery.py` 7 个测试覆盖：
  - `test_build_durable_harness_default_uses_durable_memory_store`：默认装配
  - `test_durable_memory_persists_across_reopen`：reopen 持久化
  - `test_startup_reconcile_recovers_snapshot_after_crash_before_projection`：
    crash 前未投影 + 启动恢复 + 重复幂等
  - `test_durable_memory_apply_patch_persists_reset_clear_and_claim`：
    apply_patch（reset / SESSION clear / claim correction / 非 SESSION clear 拒绝）持久化
  - `test_snapshot_json_encode_decode_roundtrip`：JSON roundtrip
  - `test_production_inmemory_conversation_store_no_longer_exists`：production InMemory 残留扫描
  - `test_replace_keeps_dataclass_immutability`：sanity 检查

### 10. 文档与 residual risk

- ✅ `dayu/host/README.md`：已更新 durable memory 当前事实，明确
  `DurableConversationMemoryStore` 为默认 read model、同事务语义、跨进程恢复路径。
  已删除"in-memory store 可用于 durable path"的措辞。
- ✅ `tests/README.md`：已新增 P8-S8 durable memory recovery 测试说明（覆盖项列表、
  fake 仅供 tests/smoke 使用）。
- ✅ `docs/host/migration-plan.md`：P8-S8 residual risk 条目从
  `deferred-with-owner: P8-S8` 更新为 `resolved: P8-S8`，下一入口 P8-S9 smoke。
- ⚠ `docs/host/migration-plan.md` 实施报告摘要中错误引用表名
  `session_memory` + `session_memory_events`，见 F2。
- ✅ Residual risks 归属正确：
  - P9：`startup_reconcile` 自动 wire 进生产 Host 启动路径
  - P9：public memory API / admission
  - issue #38：慢硬盘 / Docker Linux stress
- ✅ 文档未继续暗示 in-memory memory store 可用于 durable path。

---

## Findings

### F1 — 严重: MEDIUM｜状态: accepted — fixed

**入口/函数**: 模块中部 lazy import
**文件(行号)**: `dayu/host/_conversation_memory_durable.py:98-100`
**输入场景**: 任何 import `_conversation_memory_durable` 的模块都会触发
**实际分支**: import 语句位于 `ensure_durable_memory_schema` 函数与
`DurableConversationMemoryStore` 类定义之间，带 `# noqa: E402` 注释
**预期行为**: 模块顶部 import；`_conversation_memory.py` <-> `_conversation_memory_durable.py`
之间不存在循环依赖，顶部 import 完全安全
**实际行为**: mid-file lazy import 无技术必要

**直接证据**:
- `_conversation_memory_durable.py:1-65` 顶部已成功从 `_conversation_memory` import
  多个符号（`ConversationMemorySnapshot`、`ConversationRawTurn`、`ConversationToolFact`、
  `EvidenceAnchor`、`MemoryClaim` 等），证明无循环依赖
- `_conversation_memory.py` 不 import `_conversation_memory_durable.py`
- 注释"循环友好惰性"的循环前提不成立；"避免 production InMemory 重新泄漏"可以用
  `import ... as` 别名实现，不必须 mid-file

**影响**: 违反 AGENTS.md 硬约束"禁止胶水 seam，使用lazy import必须有充分理由"；
与 P8-S7 F1 属于同类违规。该 lazy import 增加阅读成本，将符号引用从模块顶部推移到
调用点，制造不必要的 seam。

**建议改法和验证点**:
1. 将 `_project_canonical_events` 的 import 移动到模块顶部，与同模块的 `_conversation_memory`
   其他 import 合并；
2. 删除 `# noqa: E402` 注释与中间的注释行；
3. 使用 `from dayu.host._conversation_memory import _project_canonical_events`（无需别名，
   因为模块内未使用 `_project_canonical_events` 原名；如需保留 helper 别名，可
   用 `_project_canonical_events as _project_canonical_events_helper`）；
4. 重跑 `pytest tests/host/test_phase8_durable_memory_recovery.py -q` +
   `python -m pyright dayu/host`;
5. 确认 `git diff -- dayu/host/_conversation_memory_durable.py` 中 lazy import
   已移至顶部。

**修复风险（低）**: 仅移动 import 位置，不改变运行时语义。

---

### F2 — 严重: LOW｜状态: accepted — fixed

**入口/函数**: migration-plan.md §1 总控状态段实施报告摘要
**文件(行号)**: `docs/host/migration-plan.md:73-74`
**输入场景**: 任何阅读 migration-plan 总控状态的读者
**实际分支**: 文本写 "SQLite read model（`session_memory` + `session_memory_events`）"
**预期行为**: 文档表名应与代码实际表名一致
**实际行为**: 代码中仅存在单表 `host_conversation_memory_snapshots`，没有
`session_memory` 或 `session_memory_events` 表

**直接证据**:
- `_conversation_memory_durable.py:74` 定义 `_TABLE_NAME = "host_conversation_memory_snapshots"`
- `_SCHEMA_STATEMENTS` 仅包含 `CREATE TABLE IF NOT EXISTS host_conversation_memory_snapshots`
- 全代码搜索无 `session_memory` 或 `session_memory_events` 表名
- `docs/host/migration-plan.md:73-74` 写 "``session_memory`` + ``session_memory_events``"

**影响**: 文档与代码不一致，读者可能误以为 durable memory 使用两张表。

**建议改法和验证点**:
- 将 `docs/host/migration-plan.md:73` 的 "（`session_memory` + `session_memory_events`）"
  改为 "（`host_conversation_memory_snapshots`）"，或直接删除表名括号注（因
  residual risk 段 §4.4 已准确描述，无需在总控段复述内部表名）；
- 重跑 `git diff --check` 确认无空白错误。

**修复风险（低）**: 纯文档修正。

---

### F3 — 严重: LOW｜状态: accepted — fixed

**入口/函数**: smoke 脚本 import
**文件(行号)**:
- `utils/smoke_host_conversation_memory.py:64`
- `utils/smoke_host_eventlog.py:61`
- `utils/smoke_host_multiturn_no_governance.py:116`
- `utils/smoke_host_tool_runtime.py:34`

**输入场景**: smoke 脚本运行时 import `tests/host/_memory_store_fake`
**实际分支**: 4 个 `utils/*smoke*.py` 均从 `tests.host._memory_store_fake` 导入
`FakeInMemoryConversationMemoryStore`
**预期行为**: plan 明确允许 "legacy 内存 fake 迁移到 `tests/host/_memory_store_fake.py`，
仅供 tests / smoke 使用"；当前行为与 plan 一致

**直接证据**:
- `docs/host/phase8-plan.md` P8-S8 目标段："若个别测试仍需 memory store fake，
  必须迁移为 `tests/host/` 私有 fake / test helper（例如 `tests/host/_memory_store_fake.py`）"
- `docs/host/migration-plan.md` §4.4："legacy 内存 fake 迁移到 `tests/host/_memory_store_fake.py`，
  仅供 tests / smoke 使用"
- `tests/host/_memory_store_fake.py` module docstring："本模块仅供 tests/host 与
  utils smoke 使用"

**影响**: 当前行为在 plan 范围内，不属于实施偏离。但是：
- `tests/` 目录通常从 Python 生产包中排除；如果 `utils/` smoke 未来被纳入
  可分发包，import 会失败。
- 长期看 `tests/` -> `utils/` 的 import 方向违反常规依赖规则（测试依赖 utils 是正常的，
  utils 依赖 tests 是反常的）。

**Deferred owner**: P8-S10 文档同步 / P16 interface freeze。如果 P16 决定 smoke 进入
可分发包或 CI workflow，应评估将 `FakeInMemoryConversationMemoryStore` 迁移到
`dayu.host.testing` 或 `utils/_memory_store_fake.py` 等价公开测试 helper 位置。

---

### F4 — 严重: LOW｜状态: accepted — fixed

**入口/函数**: 测试 `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore` 别名
**文件(行号)**:
- `tests/host/test_phase3_boundary.py:34`
- `tests/host/test_phase3_conversation_memory_projection.py:37`
- `tests/host/test_phase6_durable_harness_integration.py:249`
- `tests/host/test_phase6_memory_rebuild.py:26`
- `tests/host/test_phase6_review_fixes.py:695`

**输入场景**: 任何阅读这些测试文件的开发者
**实际分支**: `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore`
创建别名，使得测试代码仍出现 `InMemoryConversationMemoryStore(...)` 调用
**预期行为**: 测试应直接使用 `FakeInMemoryConversationMemoryStore` 原名，避免
制造 production InMemory 仍存在的假象

**直接证据**:
- `test_phase3_boundary.py:358,381,408,483` 使用 `InMemoryConversationMemoryStore()`
  构造 store，实际来自 `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore`
- P8-S8 plan 明确要求 `grep -R "InMemoryConversationMemoryStore" dayu/ utils/` 不命中
  production 实现，但对 tests/ 内别名未设定硬性上限

**影响**: 低。别名不影响运行时正确性（对象类型确为 `FakeInMemoryConversationMemoryStore`），
但增加代码阅读混淆，不利于新人理解 "production InMemory 已删除" 的事实。

**Deferred owner**: P16 interface freeze。P16 收口时可评估将测试中所有
`FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore` 改为直接使用
`FakeInMemoryConversationMemoryStore` 原名，或统一改名以消除混淆。

---

## Residual Risks 与 Owner

| Risk | Owner | 备注 |
|------|-------|------|
| `startup_reconcile` 只覆盖 "crash before drain" 恢复场景；"先 drain 后外部损坏 snapshot" 场景（checkpoint caught up + snapshot row 丢失）不属于 Host 恢复范围 | 接受为 S8 scope | 同事务设计保证 checkpoint 存在则 snapshot 必然存在；只有外部数据损坏才会分离，不属于 Host 治理范围 |
| `_build_default_harness()` 创建的 `:memory:` `HostStorage` 无 close 路径 | P8-S10 / P9 | `:memory:` 连接在进程退出时自动清理；长期建议 `LocalRunHarness` 增加 close 语义 |
| ~~4 个 `utils/*smoke*.py` import `tests.host._memory_store_fake`~~ | ~~P8-S10 doc sync~~ | F3 已 fixed：smoke 已迁移到 `utils/_smoke_memory_store.SmokeInMemoryConversationMemoryStore`，不再 import `tests.host._memory_store_fake` |
| ~~测试 `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore` 别名~~ | ~~P16~~ | F4 已 fixed：alias 已删除，直接使用 `FakeInMemoryConversationMemoryStore` |
| 慢硬盘 + Docker Linux 重压版多进程 stress | issue #38 | 不阻塞 S8 |
| `AttemptSupervisor.recover_stale_attempts` 未自动接入 `build_durable_harness` | P9 / Session lifecycle | 不阻塞 S8 |
| 两个进程并发 `startup_reconcile` 安全 | P8-S7 review F2 advisory | 不阻塞 S8 |
| ~~`_conversation_memory_durable.py` lazy import~~ | ~~本 slice F1~~ | F1 已 fixed：`_project_canonical_events` 已移至模块顶部批量导入，mid-file lazy import 已删除 |

---

## 建议

1. **F1 已修**（lazy import → module-level import）：`_project_canonical_events` 已移至模块顶部。
2. **F2 已修**（文档表名一致性）：`migration-plan.md` 已改为 `host_conversation_memory_snapshots`。
3. **F3 已修**（utils → tests 边界）：smoke 已迁移到 `utils/_smoke_memory_store.SmokeInMemoryConversationMemoryStore`。
4. **F4 已修**（test alias）：alias 已删除，直接使用 `FakeInMemoryConversationMemoryStore`。
5. **Review #1 F5 deferred-with-owner: P9**：partial drain + crash recovery 与 non-empty turns/facts roundtrip 测试补强不阻塞 S8，本 review 合并该 deferred 决策。
