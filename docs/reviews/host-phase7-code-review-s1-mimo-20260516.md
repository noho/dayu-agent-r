# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-review-s1-mimo-20260516.md
- Included scope: P7-S1 uncommitted diff for dayu/host/api.py, dayu/host/__init__.py, dayu/host/durable/schema.py, dayu/host/durable/state.py, dayu/host/tool_runtime.py, tests/host/test_public_contracts.py, tests/host/test_package_exports.py, tests/host/test_durable_schema.py, tests/host/test_state_schema.py, tests/host/test_public_run_api.py, tests/host/test_wait_record_state.py, docs/host/phase7-tool-awaiting-resolve-wait-plan.md
- Excluded scope: dayu/host/command.py (resolve_wait not implemented), dayu/host/engine_ingest.py, dayu/host/durable/run_transition.py, dayu/host/_event_payload.py, all P7-S2~S5 files
- Parallel review coverage: 无

## Findings

### 1-未修复-低-schema.py 重复定义 HOST_WAIT_*_MAX_LENGTH 常量

- **入口/函数**: `dayu/host/durable/schema.py` 模块级常量
- **文件(行号)**: `dayu/host/durable/schema.py:35-42`
- **输入场景**: 正常导入和使用
- **实际分支**: `schema.py` 在模块级独立定义了 `HOST_WAIT_ID_MAX_LENGTH`、`HOST_WAIT_ADAPTER_KEY_MAX_LENGTH` 等 8 个常量，与 `dayu/host/api.py:36-43` 定义的同名常量值完全相同
- **预期行为**: 按 CLAUDE.md "禁止兼容性常量 re-export" 和 "模块间依赖最小化" 精神，DDL 层应从公共契约层导入长度常量，避免维护两份相同值
- **实际行为**: 两处独立定义，当前值一致，但未来修改 api.py 常量时 schema.py 不会自动同步，可能导致 DDL CHECK 与 Python 校验使用不同上限
- **直接证据**: `schema.py:35-42` 定义 `HOST_WAIT_ID_MAX_LENGTH = 128` 等；`api.py:36-43` 定义相同常量；`state.py:15-22` 从 `api.py` 导入同一批常量用于 Python 校验
- **影响**: 维护风险。DDL CHECK 和 Python dataclass validation 可能静默使用不同长度上限
- **建议改法和验证点**: `schema.py` 从 `dayu.host.api` 导入 `HOST_WAIT_*_MAX_LENGTH` 常量，删除本地重复定义；验证 fresh schema bootstrap 测试仍通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-DDL snapshot_digest 三列配对约束不完整

- **入口/函数**: `dayu/host/durable/schema.py` `_HOST_WAIT_RECORDS_DDL`
- **文件(行号)**: `dayu/host/durable/schema.py:523-527`
- **输入场景**: 直接 SQL INSERT 绕过 Python 层
- **实际分支**: DDL CHECK 只约束 `snapshot_ref` 与 `snapshot_captured_at` 的 NULL/NOT NULL 配对，未包含 `snapshot_digest`
- **预期行为**: 按 plan §3.6 `WaitSnapshotRef(snapshot_id, captured_at, snapshot_digest)` 三字段语义，DDL 也应约束三列配对
- **实际行为**: Python 层 `deserialize_wait_snapshot_ref` 正确拒绝 `(None, None, "sha256:...")` 组合，但 DDL 允许 `snapshot_ref IS NULL AND snapshot_captured_at IS NULL AND snapshot_digest IS NOT NULL` 写入
- **直接证据**: `schema.py:523-527` CHECK 只判断 `snapshot_ref` 和 `snapshot_captured_at`；`state.py:702-705` `deserialize_wait_snapshot_ref` 检查全部三列
- **影响**: 直接 SQL 写入可能产生 Python 层不可读的脏数据；应用层正常路径不受影响
- **建议改法和验证点**: DDL CHECK 扩展为三列配对 `(snapshot_ref IS NULL AND snapshot_captured_at IS NULL AND snapshot_digest IS NULL) OR (snapshot_ref IS NOT NULL AND snapshot_captured_at IS NOT NULL)`，snapshot_digest 可选；验证 DDL 测试更新
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- `mark_wait_record_cancelled_row` CAS helper 当前无直接单元测试覆盖（`cancel_active_wait_records_for_run` 批量路径有测试，单条 cancelled CAS 路径依赖后续 P7-S4 cancel 测试覆盖）。
- `CAS_LOST` 并发竞态分支在单进程 deterministic 测试中未覆盖，已在 implementation artifact 中记录。
- `await_kind` 字段在 DDL 层无 CHECK 约束（值由 P7-S2 adapter registry 选择，当前 P7-S1 不约束）。

## 综合结论

P7-S1 实现与 plan §5 P7-S1 scope 完全对齐：`ResolveWaitRequest.outcome_ref` 已删除并替换为 typed `ResolveWaitOutcome` 联合；`observed_at` 改为 UTC-aware `datetime` 并在 `__post_init__` 校验；`HostPayloadRef` 从 `tool_runtime.py` 迁移到 `api.py` 无重复定义；`ToolFactKind.LOST` 已添加；`host_wait_records` DDL 包含正确索引和 CHECK 约束；CAS helper 返回 typed `StateMutationStatus`；`__init__.py` 导出完整；`test_wait_record_state.py` 覆盖 round-trip、DDL CHECK、unique active wait 和 CAS helper；未引入旧 `outcome_ref` 兼容、未实现 `resolve_wait`、poller 或 Engine ingest 变更。两项低严重度发现均为维护性/防御性问题，不影响当前 correctness。
