# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-K S2

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `b5bcf767`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-code-review-ds.md`
- Included scope:
  - `tests/host/public_smoke_support.py` — `_diagnostic_event_type_count` docstring
  - `tests/host/recovery_support.py` — `projection_checkpoint_sequence` rewrite + fault-injection/diagnostic helper docstrings + imports + constants
  - `tests/host/stress_support.py` — `read_latest_event_sequence`, `read_event_log_count`, `read_host_instances` docstrings
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-controller-validation.md`
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
- Parallel review coverage: 无（review scope 紧凑，由单一 reviewer 逐链路走读）
- Review gate: S2 code review by AgentDS

## Review Focus 逐项证据

### 1. projection_checkpoint_sequence 是否使用 production owner helper

**通过。** `tests/host/recovery_support.py:797-817`：

- 旧代码（`sqlite3.connect` + 原始 `SELECT checkpoint_event_sequence FROM host_projection_checkpoints WHERE consumer_id = ?`）已删除。
- 新代码通过 `open_host_durable_store(durable_options)` 打开 durable store，调用 `store.transaction_runner.run_read(lambda transaction: read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID))`。
- `read_projection_checkpoint` 是 `dayu.host.durable.projection` 的生产 owner helper（`projection.py:87-114`），执行 `_require_non_empty_text(consumer_id)` 校验并通过 `_checkpoint_row_from_host_row` 做完整的 row 类型与字段校验。
- 返回 `row.checkpoint_event_sequence`（`ProjectionCheckpointRow.checkpoint_event_sequence: int`），与旧代码返回的 `row[0]`（同一列 `checkpoint_event_sequence`）等价。
- row 不存在时返回 `None`，与旧代码行为一致。

**行为等价性确认：**
- 旧代码：`sqlite3.connect()` 默认连接 → `SELECT checkpoint_event_sequence` → 手动 `isinstance(value, int)` 校验。
- 新代码：`open_host_durable_store()` → PRAGMA 配置 + bootstrap（幂等）→ `BEGIN` read transaction → `read_projection_checkpoint`（含 `consumer_id` 非空校验 + 5 字段类型校验）→ `COMMIT`。
- 新代码的连接配置更严格（production PRAGMA），校验更完整（owner-level row validation），但语义真源一致。旧代码对 `row[0]` 只校验 `int`，新代码对完整 row 做 typed validation — 更强而非更弱。
- 测试验证：`pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q` → `9 passed`；`pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q` → `18 passed, 1 skipped`。

### 2. 保留的 raw SQL helper 是否正确分类

**通过。** 逐一核对：

| Helper | 文件:行号 | 分类标记 | 证据 |
|---|---|---|---|
| `_diagnostic_event_type_count` | `public_smoke_support.py:1505` | `diagnostic-only` | docstring: "不表达 EventLog truth，也不替代 run-scoped EventLog owner helper" |
| `force_owner_pid_missing_and_heartbeat_stale` | `recovery_support.py:659` | `fault-injection-only` | docstring: "tests/host recovery 故障注入 owner，不是 liveness 语义真源。生产 liveness API 不应制造 pid missing / stale heartbeat 状态" |
| `force_memory_projection_lag` | `recovery_support.py:699` | `fault-injection-only` | docstring: "tests/host recovery 故障注入 owner，不是 checkpoint 语义真源。生产 checkpoint helper 只初始化或单调推进 checkpoint，不提供把既有 checkpoint 倒退并清空 checkpoint_event_id 的接口" |
| `event_type_count` | `recovery_support.py:731` | `diagnostic-only` | docstring: "point-in-time diagnostic，不是 EventLog truth。生产 run-scoped event count helper 不是该跨 Run 聚合读取的精确等价物" |
| `read_latest_event_sequence` | `stress_support.py:720` | `diagnostic-only` | docstring: "不表达 watcher replay truth，不替代 EventLog / Run / Attempt canonical facts" |
| `read_event_log_count` | `stress_support.py:743` | `diagnostic-only` | docstring: "不替代 EventLog canonical fact" |
| `read_host_instances` | `stress_support.py:984` | `diagnostic-only` | docstring: "不替代 recovery orphan proof，不暴露生产 scheduler internals，也不作为 Host durable truth 之外的新真源" |

全部 7 个保留 raw SQL helper 均有明确的 `diagnostic-only` 或 `fault-injection-only` 分类标记，且 docstring 说明了各自不替代的生产 owner。这些分类与 plan 的 S2 final dispositions 一致。

### 3. 全局聚合是否误用了 production helper / 是否为 tests 新增了 production list/query API

**通过。**
- `read_latest_event_sequence`（全局 `MAX(event_sequence)`）、`read_event_log_count`（全局 `COUNT(*)`）和 `read_host_instances`（全部 instance row）均保留 raw SQL，未路由到 `read_events_after` / `read_events_after_matching` 等 cursor replay helper。
- `rg` 扫描确认：三个文件中无 `read_events_after` 或 `read_events_after_matching` 引用。
- 未新增任何 production durable public API。
- plan 明确禁止 "Do not add production query helpers just to satisfy tests" — S2 遵守该约束。
- `read_host_instances` 保留了全量 instance 诊断读取；生产 liveness helper `read_host_instance(transaction, host_instance_id)` 只读取单个已知 id，不是精确等价物。Plan 已确认此差异并允许保留 raw SQL。

### 4. active wait record 查询

**通过。**
- `public_smoke_support.py:_active_wait_id`（line 1470-1502）未被 S2 修改。
- 该函数已使用 production owner helper `read_active_wait_records_for_run(transaction, run_id)`（`dayu/host/durable/state.py:2147`），通过 `open_host_durable_store(...).transaction_runner.run_read(...)` 调用。
- S2 未引入任何 raw wait SQL。`rg` 扫描确认三个文件中不存在对 `host_wait_records` 或 wait 相关表的 raw SQL 查询。

### 5. S2 是否进入了 S1/S3 或生产代码

**通过。**
- 变更文件限定为 `tests/host/public_smoke_support.py`、`tests/host/recovery_support.py`、`tests/host/stress_support.py` — 即 plan S2 的 allowed files。
- 未触及 S1 allowed files（`tests/host/test_memory_projection.py`、`tests/contracts/test_tool_result_envelope.py`、`tests/host/test_run_input_builder.py`、`tests/engine/test_engine_event_contract.py`）。
- 未触及 S3 allowed files（`tests/host/fake_cancellation.py`、`tests/engine/runners/openai/_fakes.py`、`tests/service/test_fins_direct.py`、`tests/host/fake_compaction.py`、`tests/host/memory_snapshot_factories.py`）。
- 未修改任何 `dayu/` 下的生产代码。未新增 `tests/host/durable_diagnostics.py`。
- `recovery_support.py` 新增的 import 均为从生产代码导入 owner helper，方向正确（tests → production），不构成反向依赖。

### 6. stress 残留分类判定

**确认 stress 失败在 S2 helper 语义之外。**

S2 对 `stress_support.py` 的变更：
- `read_latest_event_sequence`（line 720）：仅 docstring 加 `diagnostic-only：` 前缀。
- `read_event_log_count`（line 743）：仅 docstring 加 `diagnostic-only：` 前缀。
- `read_host_instances`（line 984）：仅 docstring 加 `diagnostic-only：` 前缀。

三个 helper 的 SQL 行为**未做任何修改**。`recovery_support.py` 的变更（`projection_checkpoint_sequence` 改写等）不会被 stress 测试 import。

Stress 失败详情：
- `test_sustained_watch_slow_consumer_reconnect_stress`：`HostPayloadReferenceError: EventLog canonical_fact payload_json exceeds inline payload limit` — 属于 production dispatch / runner-call manifest payload 路径，非 S2 编辑的 helper 语义。
- `test_scheduler_liveness_long_run_mixed_flow_stress`：`failure_boundary` 为 `active_cleanup`，日志指向 deterministic stream exception / clean EOF / scheduler close — 属于 production scheduler cleanup 路径。

**判定：** stress 失败是 pre-existing 或 unrelated production path 问题。S2 的三个 stress helper 变更（纯 docstring）不可能导致这些失败。Controller 将其分类为 "non-blocking residual validation risk" 是正确的。

### 7. tests/README.md 决策

**通过。** 已读 `tests/README.md`。S2 未：
- 新增 shared helper 文件（`durable_diagnostics.py` 未创建）
- 新增 test layer 或测试运行方式
- 新增需要文档化的 reusable assertion convention 或 helper responsibility

现有 README 已覆盖：public smoke synchronization 走 `public_smoke_support.py` 集中 helper、stress suite 需显式 `stress` marker、生产代码不得 import 测试 helper。S2 无需更新 README。

## Findings

### 1-未修复-低-`_HOST_DB_FILENAME` 常量未覆盖同文件内其他 raw SQL helper

- **入口/函数**: `tests/host/recovery_support.py` — `attempt_count_for_run`（line 765）、`current_attempt_id_for_run`（line 787）
- **文件(行号)**: `tests/host/recovery_support.py:765`, `tests/host/recovery_support.py:787`
- **输入场景**: 任意调用 `attempt_count_for_run` 或 `current_attempt_id_for_run`
- **实际分支**: 两个函数仍使用硬编码字符串 `"host.sqlite3"` 打开 SQLite 连接
- **预期行为**: S2 在 `recovery_support.py` 中引入了模块级常量 `_HOST_DB_FILENAME = "host.sqlite3"`（line 67）并用于所有 S2 修改的函数。同文件内其他 raw SQL helper 应复用该常量以保持一致性
- **实际行为**: `attempt_count_for_run` 和 `current_attempt_id_for_run` 仍使用字面量 `"host.sqlite3"`
- **直接证据**: `recovery_support.py:765` — `with sqlite3.connect(root_path / "host.sqlite3")`；`recovery_support.py:787` — `with sqlite3.connect(root_path / "host.sqlite3")`。与 line 67 `_HOST_DB_FILENAME = "host.sqlite3"` 是同一值
- **影响**: 低。这两个函数不在 S2 scope 内，未违反 plan 约束。但如果将来 DB 文件名变更，需要修改两处而非一处。属于 maintainability 不一致，不是 correctness 缺陷
- **建议改法和验证点**: S2 接受后可考虑将 line 765 和 787 的 `"host.sqlite3"` 替换为 `_HOST_DB_FILENAME`。不影响当前 correctness
- **修复风险（低）**: 纯字符串替换，仅需确认 `_HOST_DB_FILENAME` 在模块作用域内可见
- **严重程度（低）**: 维护一致性，非 correctness 或 stability 缺陷

## Open Questions

- 无。

## Residual Risk

- **stress 残留失败**：两个 stress case（`test_sustained_watch_slow_consumer_reconnect_stress` 和 `test_scheduler_liveness_long_run_mixed_flow_stress`）在 S2 验证时失败。已确认失败路径与 S2 helper 语义无关，属于 production dispatch / scheduler cleanup / payload inline policy 路径。这些失败应在后续 work unit 中独立排查，不阻塞 S2 acceptance。
- **同一文件中 `_HOST_DB_FILENAME` 未统一**：如上 Finding 1 所述，`recovery_support.py` 中两个 S2 范围外的函数仍使用硬编码字符串。不影响 correctness，属于后续 cleanup 范畴。
- **其他 S2 scope 外的 raw SQL**：`recovery_support.py` 的 `attempt_count_for_run` 和 `current_attempt_id_for_run`、`public_smoke_support.py` 中若干 helper 仍使用 raw SQL 且未经 diagnostic-only / fault-injection-only 分类。这些不在 P3-K S2 范围内，不构成 S2 缺陷。

## Validation Notes

- `read_projection_checkpoint` 的 `_checkpoint_row_from_host_row`（`projection.py:571-592`）对 5 个字段做了 typed validation，比旧代码的 `isinstance(value, int)` 更完整。
- `open_host_durable_store` 的 `run_read` 使用显式 `BEGIN`/`COMMIT` read transaction，旧代码使用 autocommit 模式。差异在测试上下文中无实际影响，且新行为与 production read path 一致。
- `PayloadStoragePolicy(artifact_root=root_path / "artifacts")` 在 read-only 路径中不会被实际消费（`read_projection_checkpoint` 不做 payload 操作），无副作用风险。
- `HostSQLiteStoragePolicy()` 默认参数与 `_active_wait_id` 中使用的显式参数不同（后者继承自 `OpenHostOptions`），但 `projection_checkpoint_sequence` 无 `OpenHostOptions` 引用，使用默认值是正确选择。
- pyright 通过：`0 errors, 0 warnings, 0 informations`。
- 非 stress 测试全部通过。

## Verdict

**PASS.** S2 实现正确完成了所有 planned 变更：

1. `projection_checkpoint_sequence` 已迁移到 production owner helper `read_projection_checkpoint`，行为等价性保持。
2. 7 个保留 raw SQL helper 均有正确的 `diagnostic-only` 或 `fault-injection-only` 分类标记。
3. 未为 tests 新增 production list/query API。
4. Active wait record 查询保持 production helper `read_active_wait_records_for_run`，无 raw wait SQL 引入。
5. S2 scope 严格限定于 3 个 allowed test support files，未进入 S1、S3 或 production code。
6. Stress 残留失败在 S2 helper 语义之外。
7. `tests/README.md` 更新决策正确。

一个低严重度 maintainability 发现（`_HOST_DB_FILENAME` 未覆盖同文件 S2 范围外的 helper），不阻塞 acceptance。
