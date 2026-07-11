# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `b5bcf767`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-code-review-mimo.md`
- Included scope:
  - `tests/host/public_smoke_support.py`
  - `tests/host/recovery_support.py`
  - `tests/host/stress_support.py`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-controller-validation.md`
- Excluded scope: unrelated dirty/untracked files per review task definition
- Parallel review coverage: two subagents — (1) production helper API verification, (2) stress test failure path analysis

## Findings

未发现实质性问题。

以下为 review 逐项验证结论：

### 1. `projection_checkpoint_sequence` — production owner helper 替换

**验证结果：PASS**

`recovery_support.py:797-817` 的 `projection_checkpoint_sequence(...)` 已从 raw SQL 改为调用 production owner helper `read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID)`，通过 `open_host_durable_store(...).transaction_runner.run_read(...)` 执行 durable read transaction。返回 `row.checkpoint_event_sequence` 或 `None`，与原始行为一致。

Production helper 验证：
- `read_projection_checkpoint(transaction, consumer_id)` 存在于 `dayu/host/durable/projection.py:87`，签名为 `(HostTransaction, str) -> ProjectionCheckpointRow | None`。
- `ProjectionCheckpointRow.checkpoint_event_sequence` 存在（`projection.py:43`），类型为 `int`。
- `open_host_durable_store(options)` 存在于 `dayu/host/durable/connection.py:148`，返回 `HostDurableStore` context manager。
- `HostDurableStoreOptions`、`HostSQLiteStoragePolicy`、`PayloadStoragePolicy` 均存在于 `dayu/host/durable/options.py`，签名匹配。
- `bootstrap_host_durable_store` 对已有 DB（`user_version == HOST_SCHEMA_VERSION`）只执行 schema 校验，不执行 DDL，对 test 数据库安全。

### 2. Retained raw SQL 分类

**验证结果：PASS**

| Helper | 文件 | 分类 | 理由 |
|--------|------|------|------|
| `_diagnostic_event_type_count` | `public_smoke_support.py:1505` | diagnostic-only | 跨 Run EventLog event_type count，run-scoped helper 不是精确等价物 |
| `force_owner_pid_missing_and_heartbeat_stale` | `recovery_support.py:659` | fault-injection-only | 生产 liveness API 不应制造 pid missing / stale heartbeat |
| `force_memory_projection_lag` | `recovery_support.py:699` | fault-injection-only | 生产 checkpoint helper 只初始化或单调推进，不提供倒退接口 |
| `event_type_count` | `recovery_support.py:731` | diagnostic-only | 同 `_diagnostic_event_type_count`，跨 Run 聚合 |
| `read_latest_event_sequence` | `stress_support.py:720` | diagnostic-only | 全局 `MAX(event_sequence)`，无 production 等价 helper |
| `read_event_log_count` | `stress_support.py:743` | diagnostic-only | 全局 EventLog row count，无 production 等价 helper |
| `read_host_instances` | `stress_support.py:984` | diagnostic-only | 全实例 liveness 视图，production helper 只读单实例 |

每个 retained raw SQL helper 的 docstring 已标注 `diagnostic-only` 或 `fault-injection-only` 前缀，并说明了为什么不使用 production helper。

### 3. No mismatched production helper / no test-only production API

**验证结果：PASS**

- 全局聚合（EventLog count、max sequence、all-instance liveness）无 production helper，S2 正确保留 raw SQL。
- S2 未添加任何 production list/query API 仅为满足测试。
- `count_committed_events_by_run_and_type`（`event_log.py:796`）是 run-scoped，不是跨 Run 聚合的等价物。
- `read_host_instance`（`liveness.py:344`）只读单实例，无 all-instance 列表 helper。

### 4. Active wait record lookup

**验证结果：PASS**

`public_smoke_support.py:1491-1502` 的 `_active_wait_id(...)` 仍使用 production helper `read_active_wait_records_for_run(transaction, run_id)`，通过 Host durable transaction runner 执行。未引入 raw wait SQL。

### 5. S2 scope boundary

**验证结果：PASS**

- S2 只修改了 3 个 test support 文件。
- `recovery_support.py` 的变更为：新增 production imports（`open_host_durable_store`、`HostDurableStoreOptions`、`HostSQLiteStoragePolicy`、`PayloadStoragePolicy`、`ProjectionCheckpointRow`、`read_projection_checkpoint`）、新增模块常量（`_HOST_DB_FILENAME`、`_ARTIFACT_ROOT_NAME`）、docstring 更新、`projection_checkpoint_sequence` 实现替换。
- `public_smoke_support.py` 和 `stress_support.py` 的变更为 docstring 更新，无行为变更。
- 未进入 S1（owner-level contract assertions）或 S3（protocol-faithful test double consolidation）范围。
- 未修改 production 代码。

### 6. Stress residual classification

**验证结果：PASS — stress failures 非 S2 引入**

Controller 分类为 non-blocking residual validation risk，证据支持该分类：

- `test_sustained_watch_slow_consumer_reconnect_stress`（slice 3）：使用 `read_event_log_count`（S2 仅改 docstring，SQL 未变）。失败原因为 `HostPayloadReferenceError: EventLog canonical_fact payload_json exceeds inline payload limit`，发生在 production dispatch / runner-call manifest recording 路径，与 diagnostic helper 无关。`HostPayloadReferenceError` 不出现在 stress test 文件中，是 production code path 抛出。
- `test_scheduler_liveness_long_run_mixed_flow_stress`（slice 4）：使用 `read_host_instances`（S2 仅改 docstring，SQL 未变）。失败 boundary 为 `active_cleanup`，涉及 scheduler close / stream exception closeout 路径。
- 两个 stress test 均不使用 `projection_checkpoint_sequence`、`read_latest_event_sequence`（dead import）、`_diagnostic_event_type_count` 或 `event_type_count`。
- `read_latest_event_sequence` 在 `test_host_production_stress.py` 中是 dead import（line 57 导入但从未调用），属于 pre-existing tech debt，非 S2 引入。

### 7. `tests/README.md` decision

**验证结果：PASS**

S2 未新增 shared helper file、new test layer 或 durable diagnostics responsibility section。现有 README 已覆盖 public smoke 同步使用 `public_smoke_support.py`、stress suite 需显式 `stress` marker、production code 不得 import test helper 的约定。无需更新。

## Validation Notes

Implementation artifact 和 controller validation artifact 均报告了以下验证结果，与 review 发现一致：

- `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`: 18 passed, 1 skipped
- `pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q`: 9 passed
- `python -m compileall -q` + `python -c "import ..."`: pass
- `python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: pass
- Source scan 确认 `projection_checkpoint_sequence` 调用 `read_projection_checkpoint`，`host_projection_checkpoints` 仅存于 `force_memory_projection_lag`（fault-injection-only），无 `read_events_after` / `read_events_after_matching` 路由引入，wait records 仍使用 `read_active_wait_records_for_run`

## Open Questions

无。

## Residual Risk

- Stress suite 有 2 个 pre-existing failing cases（dispatch payload inline limit、scheduler cleanup），不影响 S2 语义正确性，但阻止 clean stress validation pass。Controller 已分类为 non-blocking residual。
- `recovery_support.py:765` 和 `recovery_support.py:787` 仍有 inline `"host.sqlite3"` 字符串（`attempt_count_for_run`、`current_attempt_id_for_run`），未被 S2 引入的 `_HOST_DB_FILENAME` 常量覆盖。这是 pre-existing inconsistency，S2 的 scope 内函数已正确使用常量。后续 slice 可统一。
- `read_latest_event_sequence` 在 `test_host_production_stress.py` 中是 dead import。Pre-existing tech debt，非 S2 引入。

## Overall Verdict

**PASS**

S2 实现与 approved plan 一致。`projection_checkpoint_sequence` 正确替换为 production owner helper，retained raw SQL 正确分类为 diagnostic-only 或 fault-injection-only，未引入 production API 仅为测试，未进入 S1/S3 或 production code。Stress failures 由 production dispatch / scheduler 路径导致，与 S2 helper 语义无关。
