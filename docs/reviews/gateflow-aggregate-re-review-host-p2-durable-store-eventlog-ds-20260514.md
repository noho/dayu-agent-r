# Code Re-Review

## Scope

- Mode: current changes (aggregate re-review after fix)
- Branch: feat/host-phase2-durable-store-eventlog
- Base: main
- Output file: docs/reviews/gateflow-aggregate-re-review-host-p2-durable-store-eventlog-ds-20260514.md
- Included scope: `dayu/host/durable/` (fix-targeted files: `_validation.py`, `idempotency.py`, `transaction.py`, `connection.py`, `artifact.py`, `liveness.py`), `tests/host/` (new/modified: `test_durable_validation.py`, `test_durable_connection.py`, `test_durable_transaction.py`, `test_idempotency_store.py`, `test_host_instance_liveness.py`, `test_artifact_store.py`)
- Excluded scope: unchanged production modules (`__init__.py`, `errors.py`, `codec.py`, `options.py`, `schema.py`, `event_log.py`, `payload.py`), README (not modified by fix), design docs, Engine/Fins/Service/UI/runtime
- Reviewed artifacts:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-ds-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`
  - `docs/reviews/gateflow-aggregate-fix-host-p2-durable-store-eventlog-20260514.md`

## Verification Results

| 检查项 | 结果 |
|--------|------|
| `pytest tests/host -q` | 101 passed in 0.37s |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q` | 29 passed in 0.55s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Controller-Accepted Finding Verification

### AGG-F1 — FIXED — `_validation.require_non_empty_text` 非 str runtime input 防御

- **文件(行号)**: `dayu/host/durable/_validation.py:23-24`
- **修复**: `isinstance(value, str)` 前置守卫，非 str 值抛出 `HostDurableError("field must be non-empty")`
- **直接证据**: 第 23 行 `if not isinstance(value, str)` 在 `isspace()` 调用前拦截非文本输入
- **测试**: `tests/host/test_durable_validation.py:13-19` — 覆盖 `None`、`int`、`bytes`，断言结构化 `HostDurableError`；`test_require_non_empty_text_preserves_string_behavior` 确认空字符串、纯空白字符串行为不变
- **通过**

### AGG-F2 — FIXED — idempotency `created_event_id` / `created_event_sequence` 成对校验

- **文件(行号)**: `dayu/host/durable/idempotency.py:249-255`
- **修复**: `(result.created_event_id is None) != (result.created_event_sequence is None)` 交叉一致性检查，不一致时抛出 `HostDurableError("created_event_id and created_event_sequence must be both set or both unset")`
- **直接证据**: 第 249-255 行——不等价比较在独立字段验证后、SQLite 写入前执行
- **测试**: `tests/host/test_idempotency_store.py:295-343` — `test_idempotency_rejects_one_sided_created_event_ref` 覆盖 `created_event_id` 单独提供和 `created_event_sequence` 单独提供两种单边情况，均断言结构化错误消息
- **通过**

### AGG-F3 — FIXED — `SQLITE_CONSTRAINT_CHECK` 分类

- **文件(行号)**: `dayu/host/durable/transaction.py:29, 310-311`
- **修复**: 第 29 行新增常量 `_SQLITE_CONSTRAINT_CHECK = sqlite3.SQLITE_CONSTRAINT_CHECK`；第 310-311 行新增分支 `if code == _SQLITE_CONSTRAINT_CHECK: return HostDurableError("Host durable CHECK constraint failed")`
- **直接证据**: 第 310 行——`_SQLITE_CONSTRAINT_CHECK` (275) 匹配返回明确诊断消息，不再落入第 312 行通用 fallback
- **测试**: `tests/host/test_durable_transaction.py:331-365` — 在测试连接上创建带 CHECK 约束的临时表，插入违反约束的值，断言 `HostDurableError("Host durable CHECK constraint failed")`
- **通过**

### AGG-F4 — FIXED — `run_write` 不可达 fallback 清理

- **文件(行号)**: `dayu/host/durable/transaction.py:215, 225-229`
- **修复**: 循环从 `while attempt < max_attempts` 改为 `while True`（第 215 行）；retry exhaustion `raise HostTransactionRetryExhaustedError` 在循环内 busy/locked 分支中执行（第 225-229 行）；原循环外第 245-248 行不可达 fallback raise 已删除
- **直接证据**: 第 215 行 `while True` + 第 225-229 行内联 retry exhaustion raise——所有退出路径（return/raise/continue）均在循环体内完成，无循环外死代码
- **测试**: 已有 busy retry 测试 (`test_durable_transaction.py`) 继续验证有限重试耗尽和 attempt count 断言
- **通过**

### AGG-F5 — FIXED — connection open/setup/bootstrap 失败时 close 不掩盖原始错误

- **文件(行号)**: `dayu/host/durable/connection.py:154, 178, 203-213`
- **修复**: 第 154 行（`open_host_durable_store`）和第 178 行（`_open_configured_connection`）的 `connection.close()` 替换为 `_close_connection_best_effort(connection)`；第 203-213 行新增 helper——`try: connection.close() except sqlite3.Error: return`
- **直接证据**: 第 210-212 行——`close()` 抛出的 `sqlite3.Error` 被静默吞掉，不会替换 `except` 块中保存的原始 `exc`
- **测试**: `tests/host/test_durable_connection.py:23-30` — 使用 `_FailingCloseConnection`（`close()` 抛 `OperationalError`），验证 `_close_connection_best_effort` 不传播 close 失败
- **通过**

### AGG-F6 — FIXED — artifact 冗余 parent containment 调用移除且 traversal 防护不退化

- **文件(行号)**: `dayu/host/durable/artifact.py:90, 358-368`
- **修复**: `write_artifact_bytes` 中第 96 行冗余 `_ensure_parent_dir_contained` 调用已删除；containment 检查仍在第 90 行 `_contained_final_path` → 第 367 行 `_ensure_parent_dir_contained` 中执行
- **直接证据**: 
  - 第 90 行：`final_path = _contained_final_path(self._artifact_root, relative_path)` —— 唯一 containment 入口
  - 第 367 行：`_contained_final_path` 内部调用 `_ensure_parent_dir_contained(root, relative_path)` —— containment 语义完整
  - 第 97 行：`_ensure_contained(self._artifact_root, final_path.parent)` —— post-mkdir symlink traversal 防护保留
- **测试**: 已有 artifact containment 测试 (`test_artifact_store.py`) 继续通过，验证 symlink traversal 拒绝、`..` 拒绝、绝对路径拒绝
- **通过**

### AGG-F7 — FIXED — liveness `boot_id` optionality 容忍任一侧 None

- **文件(行号)**: `dayu/host/durable/liveness.py:385-394`
- **修复**: `boot_id` 比较从无条件 `!=` 改为：仅当 `row.boot_id is not None` **且** `identity.boot_id is not None` **且** 两者不同时才冲突。`pid` 与 `process_start_token` 保持严格比较
- **直接证据**: 第 385-389 行——`boot_id_conflicts` 三条件 AND；第 390-394 行——冲突条件中 `boot_id_conflicts` 替换原 `row.boot_id != identity.boot_id`
- **测试**: `tests/host/test_host_instance_liveness.py:255-294` — `test_liveness_identity_tolerates_missing_boot_id_on_either_side` 覆盖：
  - `None` → `value`：heartbeat 不冲突
  - `value` → `None`：heartbeat 不冲突
  - `pid` / `process_start_token` 变化仍冲突（已有测试）
- **通过**

## Controller-Rejected Finding Verification

### AGG-R1 (DS fsync) — NOT FIXED — directory fsync failure 未被吞掉

- **文件(行号)**: `dayu/host/durable/artifact.py:238-240`
- **验证**: `_fsync_directory` 在 `os.fsync(directory_fd)` 抛出 `OSError` 时仍 `raise HostArtifactWriteError("Artifact directory fsync failed")`，未静默吞掉错误
- **直接证据**: 第 239 行 `raise HostArtifactWriteError("Artifact directory fsync failed") from exc` —— 与原始代码一致，未被修改
- **通过（符合 controller adjudication）**

## Existing MiMo Observations (not accepted for current fix)

- `heartbeat_current_instance` / `register_current_instance` 可将 `stopping` 回退为 `running`：未修改，与 controller adjudication 一致
- `SQLitePayloadWriteRequest.payload_json=None` 在 `CANONICAL_JSON` 模式下持久化为 JSON `null`：未修改，与 controller adjudication 一致

## New Findings

未发现实质性问题。

对 AGG-F1 至 AGG-F7 七项 controller-accepted finding 逐项确认修复完整。对 AGG-R1 (DS fsync) 确认未被错误"修复"。修复未引入新的逻辑错误、死代码、类型退化、架构污染或测试回退。host tests 从 94 增加到 101（新增 7 个针对性测试，覆盖 validation guard、idempotency 成对校验、CHECK constraint 分类、connection close best-effort、liveness boot_id optionality）。

## Open Questions

无。

## Residual Risk

- 以下风险已在 controller adjudication 中明确拒绝当前修复或被标记为 defer：artifact directory fsync 策略、stopping → running 状态回退、canonical JSON None payload 语义。这些不阻塞当前 re-review
- Artifact orphan cleanup、多进程 idempotency/payload/liveness 并发场景、boot_id 读取可用性变化等已有 residual risks 仍属于后续 phase 范围，当前修复未改变此现状

## Conclusion

**PASS**

全部七项 controller-accepted finding (AGG-F1 至 AGG-F7) 均已修复且通过验证。controller-rejected finding (AGG-R1) 未被错误"修复"。修复后 101 host tests 全量通过，29 runtime tests 通过，pyright 0 errors。无新增 finding，无回归。

Phase 2 aggregate deepreview fix gate 通过，可以推进到 ready-to-create-PR。
