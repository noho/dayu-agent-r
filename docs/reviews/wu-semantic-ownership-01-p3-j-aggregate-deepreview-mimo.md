# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `f91cd6d5`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-deepreview-mimo.md`
- Included scope: P3-J S1/S2/S3/S4 committed code (commits `a63a27c7`, `2b2718a2`, `e8f32b77`, `9ffb1a3d`) and uncommitted aggregate validation artifact `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-validation.md`
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
- Parallel review coverage: 无

## Review Method

本 review 以 plan (`docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`) 为 contract baseline，逐 slice 走读代码路径、跨 slice 交互、source-of-truth 一致性、DDL/decoder/projection 语义对齐、测试覆盖与 fixture 迁移。沿真实入口 → 参数校验 → 持久化 → row decoder → projection → public output 链路追踪。

## Findings

### 1-未修复-低-RunRow.queue_policy 保留 str 与 RunResultRow.terminal_status 改为 RunStatus 存在设计不对称

- **入口/函数**: `RunRow` (`dayu/host/durable/state.py:287`) vs `RunResultRow` (`dayu/host/durable/read_model.py:58`)
- **文件(行号)**: `dayu/host/durable/state.py:287`, `dayu/host/durable/read_model.py:58`
- **输入场景**: 所有涉及 RunRow queue_policy 的 durable write/read 路径
- **实际分支**: S2 将 `RunResultRow.terminal_status` 从 `str` 改为 `RunStatus`，但 `RunRow.queue_policy` 仍为 `str`
- **预期行为**: plan 3.2 要求 "queue_policy must round-trip through the typed owner"；plan 3.3 要求 "RunResultRow.terminal_status to RunStatus"。两者都应在 durable row boundary 携带 typed 值
- **实际行为**: `RunResultRow.terminal_status` 已改为 `RunStatus`（typed），但 `RunRow.queue_policy` 仍为 `str`。`_decode_run_queue_policy` 验证并规范化但返回 `str`，不返回 `RunQueuePolicy`
- **直接证据**: `dayu/host/durable/state.py:287` 定义 `queue_policy: str`；`dayu/host/durable/state.py:1255` 的 `_decode_run_queue_policy` 返回 `str`；而 `dayu/host/durable/read_model.py:58` 定义 `terminal_status: RunStatus`
- **影响**: 功能正确（`StrEnum` 值可当 `str` 使用），但 `RunRow` 消费者无法从类型签名得知 `queue_policy` 已通过 typed owner 校验。如果未来有消费者需要 `RunQueuePolicy` 类型，需要额外 parse
- **建议改法和验证点**: 将 `RunRow.queue_policy` 改为 `RunQueuePolicy`，`_decode_run_queue_policy` 返回 `RunQueuePolicy`，`insert_run` 直接使用 `.value`。验证点：所有 RunRow 消费者能正确处理 `RunQueuePolicy` 类型
- **修复风险（低/中/高）**: 中 — 涉及 RunRow 定义和多个消费路径
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-_validate_run_result 使用 serialize 作为 validation 的间接模式

- **入口/函数**: `_validate_run_result` (`dayu/host/durable/read_model.py:320`)
- **文件(行号)**: `dayu/host/durable/read_model.py:320`
- **输入场景**: 所有 `RunResultRow` 构造和持久化路径
- **实际分支**: 调用 `serialize_run_result_terminal_status(row.terminal_status)` 做 validation
- **预期行为**: validation 应直接检查 typed 值是否 terminal，不需要序列化
- **实际行为**: `serialize_run_result_terminal_status` 先检查 `isinstance(status, RunStatus)`，再检查 `is_terminal_run_status(status)`，然后返回 `.value`。返回值被丢弃，仅利用副作用（raise）做 validation
- **直接证据**: `dayu/host/durable/read_model.py:320` 调用 `serialize_run_result_terminal_status(row.terminal_status)` 但不使用返回值
- **影响**: 功能正确，但语义不清晰 — serialize 函数的返回值被丢弃，仅用于触发异常。后续维护者可能不理解为何调用 serialize 做 validation
- **建议改法和验证点**: 增加 `_validate_terminal_run_status(status: RunStatus) -> None` 专用 validation helper，`_validate_run_result` 调用它而非 serialize
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-insert_run 中 queue_policy 的 parse/serialize 与 _validate_run_for_insert 重复校验

- **入口/函数**: `insert_run` (`dayu/host/durable/state.py:2702`)
- **文件(行号)**: `dayu/host/durable/state.py:2702`
- **输入场景**: 所有 Run 持久化路径
- **实际分支**: `insert_run` 调用 `serialize_run_queue_policy(parse_run_queue_policy(run.queue_policy))`，而 `_validate_run_for_insert` 已在上游调用 `parse_run_queue_policy(run.queue_policy)`
- **预期行为**: 边界校验在 `_validate_run_for_insert` 完成后，`insert_run` 可直接使用已校验的值
- **实际行为**: `insert_run` 对 `run.queue_policy` 再次 parse + serialize，与 `_validate_run_for_insert` 重复
- **直接证据**: `dayu/host/durable/state.py:5263-5266` 的 `_validate_run_for_insert` 已校验；`dayu/host/durable/state.py:2702` 再次校验
- **影响**: 功能正确（幂等校验），但有微量性能开销和代码冗余
- **建议改法和验证点**: 保持当前实现作为防御性编程可接受；若 `RunRow.queue_policy` 改为 `RunQueuePolicy`（finding 1），此处可直接使用 `.value`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Cross-Slice Interaction Analysis

### S1 ↔ S2: EventLog + Queue Policy DDL 一致性

- S1 的 `_EVENT_LOG_EVENT_TYPE_CHECK_VALUES_SQL` 从 `all_host_event_type_values()` 生成，S2 的 queue policy CHECK 从 `run_queue_policy_values()` 生成。两者都通过 owner helper 生成 DDL，schema version 统一升级到 23
- S2 的 `RunRow.queue_policy` decode 路径经过 `_decode_run_queue_policy`（调用 `parse_run_queue_policy` + `serialize_run_queue_policy`），与 S1 的 EventLog row decode 路径经过 `parse_host_event_type` 模式一致
- 未发现跨 slice 回归

### S1 ↔ S3: EventLog + Idempotency 交互

- S3 的 idempotency scope/result kind 使用 `IdempotencyScopeKind` / `IdempotencyResultKind` typed enum
- S1 的 EventLog event type 使用 `HostEventType` union type
- 两者在 `admission.py` 中交汇（admission 操作同时写 EventLog 和 idempotency record），typed 值通过各自的 owner helper 验证
- `test_purge_session.py:2534-2566` 使用 raw SQL 插入 out-of-scope idempotency record，正确绕过 typed validation（测试 purge 对外部/遗留记录的处理）
- 未发现跨 slice 回归

### S2 ↔ S3: Queue Policy + Idempotency 在 admission.py 交汇

- `admission.py` 同时消费 `RunQueuePolicy`（S2）和 `IdempotencyScopeKind` / `IdempotencyResultKind`（S3）
- `_StartRunOperation` 使用 `RunQueuePolicy` 和 `IdempotencyScopeKind`，两者都通过各自 owner 验证
- `_create_accepted_admission_result`、`_create_queued_admission_result`、`_create_running_admission_result` 的 `queue_policy` 参数类型已改为 `RunQueuePolicy`
- 未发现跨 slice 回归

### S3 ↔ S3: Idempotency + Descriptor Kind 交互

- `payload.py` 的 `_validate_payload_descriptor_metadata` 使用 `parse_payload_descriptor_kind`
- `idempotency.py` 的 `_validate_scope` / `_validate_result_ref` 使用 `parse_idempotency_scope_kind` / `parse_idempotency_result_kind`
- 两者都采用相同的 owner parse 模式，无交互冲突

### S4 ↔ S1/S2/S3: Runtime Config 独立性

- S4 仅修改 `dayu/runtime/config_loader.py` 和 `dayu/cli/commands/init.py`
- 不涉及 Host durable schema、EventLog、queue policy 或 idempotency
- `_LEGACY_CONFIG_FILE_NAMES` 移至 `init.py` 作为 CLI-local guard，不与 Host 层交互
- 未发现跨 slice 回归

## Source-of-Truth Consistency Check

### EventLog event_type

| Layer | Source of Truth | Status |
|---|---|---|
| Python owner | `lifecycle_events.py: all_host_event_type_values()` | ✅ |
| Append validation | `event_log.py: _validate_append_request` → `parse_host_event_type` | ✅ |
| Row decoder | `event_log.py: _event_log_row_from_host_row` → `parse_host_event_type` | ✅ |
| DDL CHECK | `schema.py: _EVENT_LOG_EVENT_TYPE_CHECK_VALUES_SQL` → `all_host_event_type_values()` | ✅ |
| Producer values | 各 producer 模块使用 typed enum 或常量 | ✅ |
| Test fixtures | 已迁移到 `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` 等合法值 | ✅ |

### RunQueuePolicy

| Layer | Source of Truth | Status |
|---|---|---|
| Python owner | `queue_policy.py: RunQueuePolicy` | ✅ |
| Public request validation | `api.py: StartRunRequest.__post_init__` → `parse_run_queue_policy` | ✅ |
| Durable validation | `state.py: _validate_run_for_insert` → `parse_run_queue_policy` | ✅ |
| Row decoder | `state.py: _decode_run_queue_policy` → `parse_run_queue_policy` + `serialize_run_queue_policy` | ✅ |
| DDL CHECK | `schema.py: _sql_text_in_values(run_queue_policy_values())` | ✅ |
| Admission consumer | `admission.py` 使用 `RunQueuePolicy` enum | ✅ |
| AdmissionPolicy deletion | 无残留引用 | ✅ |

### Idempotency Scope/Result Kind

| Layer | Source of Truth | Status |
|---|---|---|
| Python owner | `idempotency.py: IdempotencyScopeKind / IdempotencyResultKind` | ✅ |
| Constructor validation | `IdempotencyScope.__post_init__`, `IdempotencyResultRef.__post_init__`, `IdempotencyRecord.__post_init__` | ✅ |
| Store validation | `idempotency.py: _validate_scope / _validate_result_ref` | ✅ |
| Row decoder | `idempotency.py: _idempotency_record_from_host_row` → `parse_idempotency_scope_kind` + `parse_idempotency_result_kind` | ✅ |
| DDL CHECK | 无（intentional） | ✅ |
| Producer values | admission/session_lifecycle/waiting/tool_runtime/purge 使用 typed enum | ✅ |

### PayloadDescriptorKind

| Layer | Source of Truth | Status |
|---|---|---|
| Python owner | `schema.py: PayloadDescriptorKind` | ✅ |
| Producer validation | `schema.py: payload_descriptor_metadata` → `parse_payload_descriptor_kind` | ✅ |
| Consumer validation | `payload_resolution.py: _validate_descriptor_kind` → `parse_payload_descriptor_kind` | ✅ |
| Payload write validation | `payload.py: _validate_payload_descriptor_metadata` → `parse_payload_descriptor_kind` | ✅ |
| All producers | tool_runtime/run_input/engine_ingest/compaction_operation 使用 `payload_descriptor_metadata` | ✅ |

### RunResultRow.terminal_status

| Layer | Source of Truth | Status |
|---|---|---|
| Python type | `RunResultRow.terminal_status: RunStatus` | ✅ |
| Row decoder | `read_model.py: _run_result_from_host_row` → `_terminal_status_from_text` 返回 `RunStatus` | ✅ |
| Validation | `read_model.py: _validate_run_result` → `serialize_run_result_terminal_status` | ✅ |
| SQLite write | `read_model.py: insert_run_result_if_absent` → `serialize_run_result_terminal_status` | ✅ |
| DDL CHECK | `schema.py` existing terminal status CHECK | ✅ |
| Consumer | `read_model.py: _project_run_result` → `_require_terminal_status` 返回 `RunStatus` | ✅ |

### Legacy Config

| Layer | Source of Truth | Status |
|---|---|---|
| Runtime | `config_loader.py` 不再暴露 legacy names | ✅ |
| CLI guard | `init.py: _LEGACY_CONFIG_FILE_NAMES` (CLI-local) | ✅ |
| Test | `test_config_loader.py` 使用 `_REMOVED_CONFIG_FILE_NAMES` local constant | ✅ |
| Test | `test_init_command.py` 使用 `_REMOVED_CONFIG_FILE_NAMES` local constant | ✅ |

## Test Coverage Analysis

### Fixture Migration Completeness

- `TYPE_A` → `USER_INPUT_ACCEPTED`: 覆盖 test_event_log_store, test_projection_runner, test_projection_checkpoint, test_durable_concurrency_matrix, test_public_event_stream, test_durable_schema
- `TEST_EVENT` → `USER_INPUT_ACCEPTED`: 覆盖 test_durable_connection, test_durable_transaction, test_state_schema, test_purge_session, test_wait_record_state
- `host.test` / lowercase dotted values → `USER_INPUT_ACCEPTED`: 覆盖 test_artifact_store, test_storage_orphan_proof, test_idempotency_store
- `TYPE_B` → `RUN_ACCEPTED`, `DIAG_A` → `ENGINE_EVENT_DIAGNOSTIC`, `DIAG_B` → `PROVIDER_DIAGNOSTIC`: 覆盖 test_projection_runner
- `CONTENT_DELTA` → `REASONING_DELTA`: 覆盖 test_public_event_stream
- `fifo` → `queue`: 覆盖 test_accepted_result_projection, test_compact_material, test_compact_pipeline
- Source scan 确认无残留 arbitrary event type fixtures

### New Test Coverage

- `test_lifecycle_events.py`: 新增 `test_all_host_event_type_values_preserves_owner_categories`, `test_parse_host_event_type_*`, `test_serialize_host_event_type_*` 等覆盖 owner 行为
- `test_durable_schema.py`: 新增 `test_host_runs_queue_policy_check_uses_owner_values`, `test_event_log_event_type_check_uses_owner_values`, `test_descriptor_kind_*` 覆盖 DDL CHECK 和 descriptor kind
- `test_idempotency_store.py`: 新增 `test_idempotency_owner_values_match_current_host_baseline`, `test_idempotency_rejects_unknown_scope_kind`, `test_idempotency_rejects_unknown_result_kind` 覆盖 typed owner 行为
- `test_projection_read_model.py`: 更新 terminal_status 断言从 `str` 到 `RunStatus`
- `test_toolruntime_accept_barrier.py`: 新增 `test_tool_call_request_atoms_reject_missing_descriptor_kind`, `test_tool_call_request_atoms_reject_mismatched_descriptor_kind` 覆盖 consumer fail-closed
- `test_init_command.py`: 新增 `test_init_rejects_legacy_top_level_config_asset`, `test_init_allows_prompt_asset_with_removed_config_file_name` 覆盖 CLI guard 行为
- `test_runtime/test_config_loader.py`: 更新 legacy file 断言使用 local constant

### Aggregate Validation

- 642 tests passed across all affected test files
- pyright: 0 errors, 0 warnings, 0 informations
- `git diff --check`: passed
- Source scans: AdmissionPolicy 无残留, legacy_config_file_names 无残留, scope_kind/result_kind 无 DDL CHECK, arbitrary event types 无残留

## Open Questions

- 无

## Residual Risk

- `RunRow.queue_policy` 保持 `str` 的设计决策意味着 future consumers 需要额外 parse 才能获得 `RunQueuePolicy` 类型。当前所有消费路径已通过边界 validation 保护，但若后续新增 `RunRow` 消费者，需注意类型不对称
- Historical old-config filename references 在 design docs、review archives 和 Engine migration/negative tests 中仍存在，但不属于 runtime public exposure，不在 P3-J S4 scope 内
- Direct SQL corruption / historical-row tests 仍可构造 invalid durable rows 来验证 fail-closed 行为；production owner write paths 已拒绝这些值
