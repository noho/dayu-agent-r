# Code Review

## Scope

- Mode: PR
- PR: 139 — WU-RET-00 Host storage lifecycle retention
- Base: main
- Author: noho
- Head branch: work/wu-ret-00-retention
- URL: https://github.com/noho/dayu-agent-r/pull/139
- Output file: docs/reviews/wu-ret-00-pr139-review-mimo.md
- Included scope: PR 相对 base main 的完整 diff（+8545 / -10），含实现文件 5 个、新增模块 3 个、测试文件 4 个、文档/README 7 个、review gate artifacts 20+ 个
- Excluded scope: 无
- Parallel review coverage: 5 个 subagent 并行审查
  - storage_lifecycle.py 代码路径走读
  - storage_maintenance.py 代码路径走读
  - 测试覆盖审查（4 个测试文件）
  - 文档与 PR 一致性审查（plan / design / control doc / README / exports）
  - 架构边界审查（分层约束、类型安全、public API exposure）

## PR Facts

| 字段 | 值 |
|------|-----|
| PR # | 139 |
| Title | WU-RET-00 Host storage lifecycle retention |
| Author | noho |
| Head | work/wu-ret-00-retention |
| Base | main |
| Created | 2026-06-12T05:01:07Z |
| Commits | 14 |
| Files changed | 42 |
| Additions | 8545 |
| Deletions | 10 |

## Checks

CI checks 状态：**no checks reported on the 'work/wu-ret-00-retention' branch**。PR 为 draft 状态，CI 可能未触发或 branch 未配置 check。PR body 中记录的验证命令为手动执行。

## Findings

### 1-未修复-中-测试绕过公共 API 路径验证 recheck 行为

- **入口/函数**: `test_storage_maintenance.py` `test_storage_maintenance_reclaim_recheck_hit_skips_delete`
- **文件(行号)**: `tests/host/test_storage_maintenance.py:467-471`
- **输入场景**: orphan artifact 存在且 recheck 期间新增了 descriptor
- **实际分支**: 测试直接调用 `storage_lifecycle.reclaim_orphan_artifact_files` 并注入自定义 `is_artifact_path_referenced` callable
- **预期行为**: 应通过公共 API `run_storage_maintenance` 验证 `_ArtifactPathReferenceChecker` 的集成行为（独立 read transaction、能看到 scan 后新增的 descriptor）
- **实际行为**: 绕过了 `storage_maintenance.py` 中的 `_ArtifactPathReferenceChecker` 和 `host._run_read` 路径
- **直接证据**: `test_storage_maintenance.py:467` — `storage_lifecycle_module.reclaim_orphan_artifact_files(...)` 直接调用底层而非公共入口
- **影响**: 公共 API 路径的 recheck 集成未被验证。若 `_ArtifactPathReferenceChecker` 内部有连接泄漏或事务语义错误，测试不会捕获
- **建议改法和验证点**: 新增一个通过 `run_storage_maintenance` 的端到端 recheck 测试，或保留直接调用测试同时补充注释说明绕过理由
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-中-recheck callable 非文件级异常传播行为未测试

- **入口/函数**: `test_storage_maintenance.py` `test_reclaim_file_error_keeps_processing`
- **文件(行号)**: `tests/host/test_storage_maintenance.py:482-532`
- **输入场景**: recheck callable 抛出 `HostDurableError`（如 DB 被锁定）
- **实际分支**: 测试只注入 `HostArtifactWriteError` 作为删除失败
- **预期行为**: 应测试 `is_artifact_path_referenced` 抛出 `HostDurableError` 时的行为（当前实为 fail-safe 传播中断整个 reclaim）
- **实际行为**: 非 `HostArtifactWriteError` 异常传播路径未被验证
- **直接证据**: `storage_lifecycle.py:490` 只 catch `HostArtifactWriteError`，`HostDurableError` 直接传播
- **影响**: 生产中 DB 连接问题触发 `sqlite3.Error` → `HostDurableError` 时，是中断还是记录的行为未被测试覆盖
- **建议改法和验证点**: 新增测试 monkeypatch `is_artifact_path_referenced` 抛出 `HostDurableError`，验证传播行为
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 3-未修复中-scan_orphan_artifact_files 边界校验未测试

- **入口/函数**: `scan_orphan_artifact_files`
- **文件(行号)**: `dayu/host/durable/storage_lifecycle.py:423-424`，`tests/host/test_storage_orphan_proof.py`
- **输入场景**: `grace_seconds < 0` 或 `now` 为 naive datetime
- **实际分支**: 实现中显式 `ValueError` 校验（第 423-424 行）
- **预期行为**: 应有测试覆盖这两个拒绝路径
- **实际行为**: 无测试覆盖
- **直接证据**: `storage_lifecycle.py:423` — `if grace_seconds < 0: raise ValueError(...)`；`storage_lifecycle.py:424` — `if now.tzinfo is None: raise ValueError(...)`；四个测试文件中均无对应 `pytest.raises(ValueError)` 测试
- **影响**: 若校验被意外移除或修改，无测试会失败
- **建议改法和验证点**: 新增 `test_scan_orphan_rejects_negative_grace` 和 `test_scan_orphan_rejects_naive_datetime`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 4-未修复-低-issues-implementation-control.md WU-RET-00 状态行未同步

- **入口/函数**: 总控文档 Work Units 表
- **文件(行号)**: `docs/host/issues-implementation-control.md:215`
- **输入场景**: operator 查看 work unit 状态
- **实际分支**: 第 215 行状态仍为 `planning`
- **预期行为**: 应为 `ready-to-open-draft-PR`（与同文件第 146/149/536 行一致）
- **实际行为**: Work Units 表显示 `planning`，与当前状态表矛盾
- **直接证据**: 第 215 行 `| WU-RET-00 | planning | Host storage lifecycle retention policy |` vs 第 146 行 `implementation status | ...WU-RET-00 local gates passed and ready for draft PR`
- **影响**: 后续推进时状态判断歧义
- **建议改法和验证点**: 第 215 行 `planning` → `ready-to-open-draft-PR`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 5-未修复-低-HostStorageMaintenanceFileError 字段命名偏离 plan

- **入口/函数**: `HostStorageMaintenanceFileError` dataclass
- **文件(行号)**: `dayu/host/storage_maintenance.py:96-104`
- **输入场景**: 对照 accepted plan §6.4
- **实际分支**: 实现使用 `path`/`message`/`operation`
- **预期行为**: plan 定义 `artifact_relative_path`/`error_message`/`operation`
- **实际行为**: 字段名不同，但与 durable 层 `DurableArtifactFileError` 一致
- **直接证据**: `storage_maintenance.py:100` — `path: str`；plan §6.4 — `artifact_relative_path: str`
- **影响**: plan 与实现不一致，但 `path`/`message` 语义自解释且与 durable 层契约一致，属正常设计收敛
- **建议改法和验证点**: 无需修改代码。可在 plan 中注明偏离或在 implementation report 中记录
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 6-未修复-低-HostStorageUsageReport 通过 storage_maintenance 重导出

- **入口/函数**: `storage_maintenance.py` 的 `__all__` 和 `__init__.py` 导出
- **文件(行号)**: `dayu/host/storage_maintenance.py:32,583`；`dayu/host/__init__.py:107`
- **输入场景**: Service 通过 `from dayu.host import HostStorageUsageReport` 导入
- **实际分支**: `HostStorageUsageReport` 定义在 `durable.storage_lifecycle`，经 `storage_maintenance` 重导出到 `__init__.py`
- **预期行为**: 理想情况 `__init__.py` 直接从 `durable.storage_lifecycle` 导入
- **实际行为**: 通过 facade 模块聚合重导出
- **直接证据**: `storage_maintenance.py:32` — `from dayu.host.durable.storage_lifecycle import HostStorageUsageReport`
- **影响**: 模式上是 pure pass-through re-export，但作为新模块无旧路径问题
- **建议改法和验证点**: 可在 `__init__.py` 直接从 `durable.storage_lifecycle` 导入，从 `storage_maintenance.__all__` 移除；或接受 facade 聚合设计并在 docstring 注明
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 7-未修复-低-私有校验辅助函数跨模块重复

- **入口/函数**: `_require_string_tuple`、`_require_non_empty_text`
- **文件(行号)**: `dayu/host/storage_maintenance.py:549-575`；`dayu/host/durable/storage_lifecycle.py:701-727`
- **输入场景**: 未来校验规则变更
- **实际分支**: 两个模块各自定义完全相同的私有辅助函数
- **预期行为**: 抽取到共享位置
- **实际行为**: 重复定义
- **直接证据**: 两处代码逻辑完全一致
- **影响**: 若规则变更需同步两处，维护风险
- **建议改法和验证点**: 可抽取到 `dayu.host.durable._validators` 等共享位置
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 8-未修复-低-HostStorageMaintenanceResult.json_value() 未测试

- **入口/函数**: `HostStorageMaintenanceResult.json_value()`
- **文件(行号)**: `tests/host/test_storage_maintenance.py`
- **输入场景**: 公共 API 序列化
- **实际分支**: 测试只断言 result 字段，未调用 `json_value()`
- **预期行为**: 应有测试验证 `json_value()` 的 key、类型和结构稳定性
- **实际行为**: 无覆盖（`test_storage_usage_report.py` 中有对应 `json_value()` 测试，但 maintenance result 无）
- **直接证据**: `test_storage_usage_report.py:504-548` 有 `test_storage_usage_json_value_is_stable_self_explaining_and_non_negative`，`test_storage_maintenance.py` 中无对应测试
- **影响**: `json_value()` key 名或结构回归不会被捕获
- **建议改法和验证点**: 新增类似 `test_maintenance_result_json_value_is_stable` 测试
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- CI checks 未报告（`no checks reported on the 'work/wu-ret-00-retention' branch`）。PR 为 draft 状态，需确认 CI 是否已配置、是否会在非 draft 状态触发。

## Residual Risk

1. **TOCTOU 残余窗口**（plan §11 R1 已记录）：recheck 与 unlink 之间存在极短窗口。缓解措施（dry-run 默认、3600s grace、content-addressed 可重写性）已到位，风险可接受。
2. **SQLite VACUUM / 物理空间回收**：deferred to GitHub issue #76，不在本 PR 范围。
3. **Tool Trace cold JSONL retention**：WU-RET-01 / GitHub issue #36，不在本 PR 范围。
4. **Audit JSONL retention**：WU-RET-02 / GitHub issue #96，不在本 PR 范围。
5. **并发测试缺失**：所有测试单线程执行，无并发 maintenance 场景覆盖。考虑到 maintenance 由单一运维入口调用且有 grace window 缓解，风险低。
6. **CI 未触发**：draft PR 无 checks reported，需合并前确认 CI 状态。

## 结论

**PASS**

blocking finding 数量：**0**

所有 findings 均为 LOW severity 的文档同步、命名收敛或测试覆盖补充，不构成 correctness / stability / maintainability blocker。核心实现路径（artifact 枚举、orphan 判定、destructive reclaim safety、dry-run 默认、错误传播）经 5 个 subagent 并行走读确认安全，与 accepted plan 无实质偏差。建议在 merge 前补充 Finding 1-3 的测试覆盖，并确认 CI 状态。
