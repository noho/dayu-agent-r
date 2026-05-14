# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase2-durable-store-eventlog`
- Base: `main`
- Output file: `docs/reviews/gateflow-aggregate-re-review-host-p2-durable-store-eventlog-mimo-20260514.md`
- Included scope: `dayu/host/durable/`（AGG-F1..AGG-F7 涉及的 6 个生产模块 + 新增测试）、controller adjudication、fix artifact
- Excluded scope: design docs、public exports、Engine/Fins/Service/UI/runtime（按 controller 约束未修改）
- Parallel review coverage: 无

## Verification Results

| 检查项 | 结果 |
|--------|------|
| `pytest tests/host -q` | 101 passed in 0.45s |
| `pytest tests/runtime/...` | 29 passed in 0.58s |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## AGG-F1..AGG-F7 逐项确认

### AGG-F1 - FIXED - `_validation.require_non_empty_text` 非 str runtime input

- **文件**: `dayu/host/durable/_validation.py:23-24`
- **直接证据**: `if not isinstance(value, str): raise HostDurableError(f"{field_name} must be non-empty")` 在 `value == ""` 检查之前执行
- **测试**: `tests/host/test_durable_validation.py:13-19` 覆盖 `None`、`int`、`bytes` 三种非 str 输入
- **确认**: 非 str 运行时输入现在抛出 `HostDurableError`，不再产生 `AttributeError`

### AGG-F2 - FIXED - idempotency `created_event_id` / `created_event_sequence` 成对

- **文件**: `dayu/host/durable/idempotency.py:249-254`
- **直接证据**: `if (result.created_event_id is None) != (result.created_event_sequence is None): raise HostDurableError(...)`
- **测试**: `tests/host/test_idempotency_store.py:295` (`test_idempotency_rejects_one_sided_created_event_ref`)
- **确认**: 一侧 `None` 一侧非 `None` 时在 SQLite 写入前结构化失败

### AGG-F3 - FIXED - `SQLITE_CONSTRAINT_CHECK` 分类

- **文件**: `dayu/host/durable/transaction.py:29`（常量定义）、`transaction.py:310-311`（分类分支）
- **直接证据**: `_SQLITE_CONSTRAINT_CHECK = sqlite3.SQLITE_CONSTRAINT_CHECK`；`if code == _SQLITE_CONSTRAINT_CHECK: return HostDurableError("Host durable CHECK constraint failed")`
- **测试**: `tests/host/test_durable_transaction.py:331` (`test_check_constraint_error_is_classified_explicitly`)
- **确认**: CHECK 约束失败不再落到最后的 generic fallback

### AGG-F4 - FIXED - `run_write` unreachable fallback 清理

- **文件**: `dayu/host/durable/transaction.py:215`
- **直接证据**: 循环改为 `while True:`，busy/locked 耗尽在 `if attempt >= max_attempts:` 分支内直接 `raise`（line 226-229），循环后不再有 fallback raise
- **测试**: 现有 busy retry 测试（`test_busy_locked_retries_are_finite_and_do_not_run_after_commit`）仍通过
- **确认**: 无 dead code，无 unreachable fallback

### AGG-F5 - FIXED - connection close 不掩盖原始错误

- **文件**: `dayu/host/durable/connection.py:154,178`（调用点）、`connection.py:203-213`（helper 实现）
- **直接证据**: `_close_connection_best_effort` 在 `try/except sqlite3.Error: return` 中执行 `connection.close()`，close 失败不会替换原始异常
- **测试**: `tests/host/test_durable_connection.py:23-30` 使用 `_FailingCloseConnection` 子类验证 close 异常被抑制
- **确认**: 初始化失败时原始错误不被 close 失败掩盖

### AGG-F6 - FIXED - artifact redundant parent containment call 移除

- **文件**: `dayu/host/durable/artifact.py:90,96-97`
- **直接证据**: 当前流程为：
  1. line 90: `_contained_final_path(root, relative_path)` → 内部调用 `_ensure_parent_dir_contained`（line 367）检查既有祖先目录
  2. line 96: `final_path.parent.mkdir(parents=True, exist_ok=True)` 创建目录
  3. line 97: `_ensure_contained(root, final_path.parent)` 验证新建目录未逃逸
- **确认**: 冗余调用已移除；pre-mkdir 祖先检查 + post-mkdir 结果验证的 traversal 防护不退化

### AGG-F7 - FIXED - liveness `boot_id` optionality

- **文件**: `dayu/host/durable/liveness.py:385-393`
- **直接证据**:
  ```python
  boot_id_conflicts = (
      row.boot_id is not None
      and identity.boot_id is not None
      and row.boot_id != identity.boot_id
  )
  ```
  `pid` 和 `process_start_token` 仍严格比较（line 391-392）
- **测试**: `tests/host/test_host_instance_liveness.py:255`（`test_liveness_identity_tolerates_missing_boot_id_on_either_side`）、line 297（`test_liveness_identity_rejects_different_non_empty_boot_id`）
- **确认**: 任一侧 `None` 可容忍；双方非 `None` 且不同才冲突；`pid`/`token` 仍严格

## Controller Rejected Finding 确认：AGG-R1 directory fsync

- **文件**: `dayu/host/durable/artifact.py:226-242`
- **直接证据**: `_fsync_directory` 函数中 `os.fsync(directory_fd)` 失败时 `raise HostArtifactWriteError("Artifact directory fsync failed")`，异常从 `except OSError` 分支抛出，不被吞掉
- **确认**: DS 提出的 "directory fsync failure 应被吞掉" 建议未被错误实施。fsync 失败仍然结构化抛出，符合 controller 裁决

## Findings

未发现实质性问题。

AGG-F1 至 AGG-F7 全部正确实施，controller rejected 的 AGG-R1（directory fsync）未被错误"修复"。测试和 pyright 全绿。

## Open Questions

无。

## Residual Risk

无新增风险。fix artifact 已记录的 residual areas（artifact orphan cleanup、stopping → running 行为、`payload_json=None` 语义）仍按 controller 裁决保持 out of scope。

## Conclusion

**PASS**

所有 controller-accepted findings AGG-F1..AGG-F7 已正确修复，controller-rejected AGG-R1 未被错误实施。101 host tests + 29 runtime tests 通过，pyright 全绿。可推进到 accepted deepreview commit。
