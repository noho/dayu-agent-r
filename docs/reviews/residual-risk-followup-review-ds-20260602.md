# Residual Risk Follow-up Code Review — DS

**日期**：2026-06-02
**审查范围**：当前 workspace 未提交改动（Residual Risk follow-up）
**审查类型**：独立 adversarial code review
**审查人**：AgentDS

## 变更摘要

本次变更为 Host follow-up control document 中 7 条 residual risk 的状态更新及其对应的代码/测试/文档证据。具体变更：

| 文件 | 变更性质 |
|---|---|
| `dayu/host/durable/maintenance.py` | 新增 WAL checkpoint connection/db_path 同源校验 |
| `dayu/host/durable/schema.py` | required object existence validation 改为批量缺失诊断 |
| `dayu/host/dispatch.py` | `ActiveWorkerRegistry.clear()` + scheduler close residual handle cleanup |
| `tests/host/test_durable_connection.py` | 新增错配 connection/db_path 拒绝测试 |
| `tests/host/test_durable_schema.py` | 更新/新增批量缺失对象诊断测试 |
| `tests/host/test_dispatch_scheduler.py` | 新增 pre-consumer close 确定性窗口测试 + lifecycle matrix |
| `dayu/host/README.md` | 同步批量诊断与 connection 校验描述 |
| `tests/README.md` | 同步 pre-consumer active handle 资源释放描述 |
| `docs/host/host-core-followup-implementation-control.md` | 更新 residual risk 状态与记录 |

## 验证摘要

```
tests/host/test_durable_connection.py ...  ...  passed
tests/host/test_durable_schema.py     ...  ...  passed
tests/host/test_dispatch_scheduler.py ...  ...  passed
tests/host/test_import_boundary.py    ...  ...  passed
Total: 112 passed
pyright: 0 errors, 0 warnings, 0 informations
```

---

## Findings

### F-01: RR-DUR-02 — WAL checkpoint connection/db_path 一致性校验 — PASS

**变更**：`maintenance.py` 新增 `_assert_connection_matches_db_path` 与 `_read_main_database_path`，在校验入口处通过 `PRAGMA database_list` 读取 connection 的 main database 文件路径并与传入 `db_path` 做 `Path.resolve(strict=False)` 比较。

**审查结论**：

- **fail closed 正确**：错配时抛出 `HostDurableError`（`_HOST_WAL_CHECKPOINT_DATABASE_MISMATCH_ERROR`），不执行 checkpoint，不返回误导性 WAL 诊断。
- **路径解析正确**：`resolve(strict=False)` 对双方路径解符号链接、`..` 规范化后比较，覆盖相对路径/绝对路径混用场景。
- **`_read_main_database_path` 防御充分**：覆盖 SQL 错误、row shape 异常、无 main database、main database 非文件型、空文件路径五种失败路径，全部转为结构化 `HostDurableError`。
- **不影响正确路径**：正常 connection/db_path 同源不会触发校验失败，`_assert_connection_matches_db_path` 只做前置守卫不做副作用。
- **测试覆盖**：`test_wal_checkpoint_rejects_mismatched_connection_and_db_path` 创建两个独立 store，用 store A 的 connection 配合 store B 的 db_path 调用 checkpoint，断言精确拒绝消息。
- **关闭连接语义变更**：`test_wal_checkpoint_closed_connection_failure_is_structured` 的期望错误消息从 `"Host durable WAL checkpoint failed"` 更新为 `"Host durable WAL checkpoint failed to inspect connection database"`，这是因为 connection 校验先于 checkpoint 执行，已关闭 connection 在校验阶段失败。这是合理的诊断语义精化，不是回归。

**裁决**：RR-DUR-02 关闭证据充分，无风险。

---

### F-02: RR-DUR-03 — Schema validation 批量缺失对象诊断 — PASS

**变更**：`schema.py` 将 `_validate_required_tables` + `_validate_required_indexes` 收口为 `_validate_required_objects_exist` → `_missing_required_tables` + `_missing_required_indexes` → `_missing_required_objects_message`。单对象缺失保留旧格式（`"missing required table: X"` / `"missing required index: X"`），多对象缺失输出批量消息（`"missing required objects: tables: A, B; indexes: C, D"`）。

**审查结论**：

- **仍 fail closed**：缺失任何 required object 均抛出 `HostSchemaMismatchError`，不执行 DDL，不迁移，不修复。
- **不修复不迁移不变**：`validate_host_durable_schema` 和 `bootstrap_host_durable_store` 的 current-version 路径行为未改变——仅校验，不执行 DDL。
- **单对象消息兼容**：`_missing_required_objects_message` 对单个 table 或单个 index 保留精确旧格式，`test_current_schema_missing_index_opener_raises_without_repair` 无需修改仍通过。
- **Cascaded drop 行为正确**：`test_current_schema_missing_table_opener_raises_without_repair`（删 `TABLE_EVENT_LOG` → SQLite 自动删其索引 → 多对象缺失 → 批量消息）和 `test_secondary_connection_missing_table_raises_without_repair`（删 `TABLE_HOST_MEMORY_DIAGNOSTICS` → 同上）的断言更新反映了批量报告的语义改进。
- **新测试覆盖多对象缺失**：`test_current_schema_multiple_missing_objects_are_reported_together` 显式删除一个 table + 一个 index，断言批量消息同时列出 tables 与 indexes 缺口。
- **常量化**：`_MISSING_REQUIRED_OBJECTS_SEPARATOR = "; "` 作为模块级常量，无魔法字符串。

**裁决**：RR-DUR-03 关闭证据充分，无风险。

---

### F-03: RR-DUR-05 — Same-name wrong table/index definition validation — PASS

**变更**：本 PR 未直接修改 `_validate_required_object_definitions`，但 control doc 基于 WU-LAYER-01 已实现的定义校验声称 RR-DUR-05 closed。

**审查结论**：

- **DDL 真源单一**：`_expected_schema_sql_by_name` 在内存中执行 `HOST_DURABLE_DDL`（唯一的 DDL 真源），读取 `sqlite_master.sql` 作为 expected catalog SQL。
- **不引入 brittle string match**：`_normalize_schema_sql` 通过 `_WHITESPACE_RUN_PATTERN` 做空白归一化后比较，消除格式差异的误报。
- **范围受限**：只比较 `HOST_DURABLE_TABLES` + `HOST_DURABLE_INDEXES` 中列出的对象，不比较 SQLite 内部对象。
- **测试覆盖**：`test_current_schema_wrong_index_definition_opener_raises_without_repair`（同名 index 错误定义）、`test_current_schema_wrong_table_definition_opener_raises_without_repair`（同名 table 错误定义）均已有 fail-closed 测试，本次未修改。
- **WU-LAYER-01 证据链完整**：control doc 中 WU-LAYER-01 状态为 `local-pass`，slice commits 已接受，cross-slice tests 136 passed，pyright 0 errors。

**裁决**：RR-DUR-05 关闭证据充分。DDL 真源同源、不引入 brittle string mismatch、fail-closed 不变。无风险。

---

### F-04: RR-LIFE-01 — Scheduler close residual active handle / registry cleanup — PASS

**变更**：
- `dispatch.py`：`ActiveWorkerRegistry.clear()` 新增方法；`close()` 在 `cancel_all` + active task 取消之后，新增对 `_active_handles` 的遍历 close + discard + registry clear。
- 新测试 `test_scheduler_close_cleans_active_handle_when_consumer_task_never_started`
- 新 lifecycle matrix case `worker-accepted-before-consumer-start-close`

**审查结论**：

- **覆盖 pre-consumer 窗口**：测试精确构造了 worker accepted 后 consumer task 尚未进入 event consume body 的状态——handle 在 `_active_handles`、registry 有 entry、cancellation token 未取消、task 未启动（`Event` 未 set）。close 后断言：
  - token 已取消且 reason 为 `"scheduler_close"`
  - handle.cancel_count == 1（`cancel_all` 传播到 registry entry）
  - handle.close_count == 1（新增的 handle cleanup loop 关闭）
  - `_active_tasks` 和 `_active_handles` 均为空
  - registry cancel after close 返回 False（registry 已 clear）
- **不写 scheduler-close-created terminal fact**：registry.cancel after close 返回 False，不会产生 cancel canonical fact。这与 WU-LIFE-02 目标"close 本身不写 terminal facts"一致。
- **`_safe_close_worker_handle` 是 best-effort**：异常被 catch 并 warning log，不阻断 close 流程。
- **不破坏正常 dispatch/close**：新增 cleanup loop 在 `cancel_all` 之后、lane close 之前执行，幂等（已关闭的 handle 再次关闭无副作用，clear 空 set/registry 无副作用）。`test_scheduler_close_lets_active_task_own_handle_close`（handle 已在 events finally 中关闭的场景）仍通过。
- **Lifecycle matrix 一致性**：新 case 的 `expected_durable_mutation` 标注为 `"no scheduler-close-created terminal canonical fact"`，与所有现有 close case 的断言一致。`test_scheduler_close_lifecycle_matrix_covers_slice_b_windows` 已更新预期 id 集合包含新 case。

**裁决**：RR-LIFE-01 关闭证据充分。pre-consumer 窗口被确定性覆盖，不写 scheduler-close-created terminal fact，不破坏正常路径。无风险。

---

### F-05: RR-STRESS-01 / RR-STRESS-02 — 转 issue / closed 论证 — PASS

**RR-STRESS-01 → transferred-to-issue**：
- 慢盘/Docker 高强度 stress 已由独立 GitHub Issue #38 跟踪。
- 当前 stress suite 定位是可重复、确定性、有限预算的 production hardening suite，不覆盖极端环境规格。
- 论证合理：有独立 owner，不丢失追踪。

**RR-STRESS-02 → closed**：
- pytest-timeout 强杀行为：进程被 SIGTERM/SIGKILL 时 pytest 以非零退出码终止，CI/test runner 报告 FAILED。
- 之前 residual risk 的担忧是"timeout 先于内部 summary 终止可能导致假通过"，但 pytest-timeout 的实际行为是 FAIL，不是 PASS。
- 论证合理：pytest-timeout 作为外层兜底不会导致误判测试通过。

**裁决**：两条状态变更论证合理，不存在真实未覆盖风险被误关。

---

### F-06: RR-LAYER-02-01 — 新增 residual risk 描述 — PASS

**描述**：`llm_compaction._safe_outcome_text` 截断形状（前 240 字符 + `"..."`，总长 243）与 `runtime.truncate_diagnostic_text`（总长 ≤ max_chars）语义不同。

**审查**：
- 描述准确：`_safe_outcome_text` 超限时取前 240 字符 + 后缀 `"..."`，结果总长 ≤ 243；`truncate_diagnostic_text` 直接按 max_chars 做总长截断，不加后缀。
- Owner 明确：`future Host compactor diagnostic hardening if unified truncation is desired`
- 不阻塞当前 PR：controller 已裁决保留旧行为，测试已锁定，差异不影响安全性。
- 状态正确：`deferred-with-owner`

**裁决**：RR-LAYER-02-01 描述准确、owner 明确、不阻塞当前 PR。PASS。

---

### F-07: README / tests README 同步 — PASS

**`dayu/host/README.md` 变更**：
- durable foundation 段："缺失 required objects 时批量诊断"（同步 RR-DUR-03）
- WAL checkpoint 段："调用时会校验 connection 的 main database 与传入 DB path 同源"（同步 RR-DUR-02）
- 职责边界：属于 `dayu/host/README.md` 的开发手册职责范围（内部机制描述），不越界。

**`tests/README.md` 变更**：
- scheduler 覆盖描述行：`"active task 资源释放"` → `"active task 与 pre-consumer active handle 资源释放"`（同步 RR-LIFE-01 测试新增）
- 职责边界：属于 `tests/README.md` 的测试覆盖描述职责范围。

**裁决**：README 同步符合 AGENTS.md 职责边界，描述准确反映代码变更。

---

### F-08: 代码质量检查 — PASS

逐项检查结果：

| 检查项 | 结果 |
|---|---|
| `Any` / `object` / 无类型签名 | 未发现。所有新函数均有完整类型注解（`tuple[str, ...]`、`str`、`None`、`Path` 等）。 |
| `getattr` / `hasattr` | 未发现。 |
| lazy import | 未发现。 |
| 兼容 wrapper / re-export | 未发现。 |
| 分层反向依赖 | 未发现。变更均在 Host 层内部或跨 Host/tests 边界，无上层依赖。 |
| 魔法字符串 | 未发现。错误消息全部使用模块级常量（`_HOST_WAL_CHECKPOINT_INSPECT_DATABASE_ERROR`、`_HOST_WAL_CHECKPOINT_DATABASE_MISMATCH_ERROR`、`_MISSING_REQUIRED_OBJECTS_SEPARATOR`）。 |
| docstring 不完整 | 未发现。所有新增函数（`_assert_connection_matches_db_path`、`_read_main_database_path`、`_validate_required_objects_exist`、`_missing_required_tables`、`_missing_required_indexes`、`_missing_required_objects_message`、`ActiveWorkerRegistry.clear`）均有完整中文 docstring，包含 `:param`、`:returns`、`:raises`。 |
| `cast` 使用 | `maintenance.py` 中两处 `cast(tuple[SQLiteScalar, ...], tuple(row))` 为 SQLite row 到类型化 tuple 的必要转换，有充分理由，不是逃避类型设计。 |

**裁决**：代码质量无问题。所有新函数类型完备、docstring 完整、无魔法字符串、无分层违规。

---

## 总结

| 检查项 | 判定 |
|---|---|
| RR-DUR-02: WAL checkpoint connection/db_path 一致性 | **PASS** — fail closed，测试覆盖错配 |
| RR-DUR-03: Schema 批量缺失对象诊断 | **PASS** — fail closed + 批量报告，测试覆盖多对象 |
| RR-DUR-05: DDL text invariant validation | **PASS** — DDL 同源，无 brittle string match |
| RR-LIFE-01: Scheduler close residual handle | **PASS** — 确定性覆盖 pre-consumer 窗口，不写 terminal fact |
| RR-STRESS-01/02: 转 issue / closed | **PASS** — 论证合理 |
| RR-LAYER-02-01: 新增 residual risk | **PASS** — 描述准确，owner 明确 |
| README 同步 | **PASS** — 职责边界内 |
| 代码质量 | **PASS** — 无 Any/object/getattr/lazy-import/兼容/wrapper/魔法字符串 |
| 测试 | **112 passed** |
| pyright | **0 errors, 0 warnings** |

### 建议

**建议关闭/转移这些 residual risk 的状态变更全部有效**，无不充分证据支撑的关闭或误关。当前 workspace 变更没有引入行为回归、安全漏洞、类型退化或分层违规。

**建议当前变更可以 commit 并合并到 PR #110 的 follow-up 分支。**
