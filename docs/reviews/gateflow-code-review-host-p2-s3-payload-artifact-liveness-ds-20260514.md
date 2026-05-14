# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase2-durable-store-eventlog
- Base: main
- Output file: docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-ds-20260514.md
- Included scope:
  - dayu/host/durable/payload.py (new)
  - dayu/host/durable/artifact.py (new)
  - dayu/host/durable/liveness.py (new)
  - dayu/host/durable/event_log.py (targeted update: `_validate_existing_payload_descriptor`)
  - dayu/host/README.md (update)
  - tests/README.md (update)
  - tests/host/test_payload_store.py (new)
  - tests/host/test_artifact_store.py (new)
  - tests/host/test_host_instance_liveness.py (new)
  - docs/reviews/gateflow-implementation-host-p2-s3-payload-artifact-liveness-20260514.md
- Excluded scope: slice 1/2 files (schema.py, transaction.py, connection.py, codec.py, errors.py, options.py, idempotency.py) — only reviewed for interface consistency with new module imports.
- Parallel review coverage: 无

## Validation Results

| Command | Result |
|---|---|
| `pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q` | 25 passed |
| `pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q` | 15 passed |
| `pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py tests/host/test_event_log_multiprocess.py -q` | 20 passed |
| `pytest tests/host -q` | 92 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q` | 29 passed |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| Import boundary check (no dayu.engine/fins/service/ui/runtime imports) | clean |
| Type annotation check (no Any/object in new modules) | clean |
| Coverage (payload.py / artifact.py / liveness.py) | 83% combined (86% / 79% / 87%) |

## Findings

### 1-未修复-低-标量校验 helper 在三模块间重复定义

- **入口/函数**: `_require_non_empty_text`, `_require_optional_non_empty_text`, `_require_text`, `_optional_text`, `_require_int`
- **文件(行号)**:
  - dayu/host/durable/payload.py:493-573
  - dayu/host/durable/event_log.py:594-661
  - dayu/host/durable/liveness.py:416-483
- **输入场景**: 任何调用方传入 SQLite scalar 或文本字段。
- **实际分支**: 三个模块各自定义了语义完全相同的私有 helper，共 5 个函数 × 3 份 = 15 个函数定义。
- **预期行为**: 按项目 CLAUDE.md 约束 —— "重复逻辑必须抽取" —— 这些 helper 应在 `dayu/host/durable/` 内聚到一个共享模块（如 `_row_helpers.py` 或复用 `transaction.py` 中已定义的类型转换层）。
- **实际行为**: 三份拷贝独立演进，任何 bug fix 或语义调整需要同步修改三个文件。
- **直接证据**: 逐行比对三个文件中的 `_require_non_empty_text`、`_require_optional_non_empty_text`、`_require_text`、`_optional_text`、`_require_int` —— 函数体、docstring、错误消息格式完全相同。
- **影响**: 维护风险——未来改动可能只改一份而遗漏另外两份，造成行为不一致。
- **建议改法和验证点**: 将 5 个 helper 抽取到 `dayu/host/durable/_row_helpers.py`（或 `transaction.py` 中已有抽象层），三个模块改为 import。验证点：三个模块测试仍然全量通过；pyright 无新增报错。
- **修复风险（低）**: 纯机械重构，不改变任何运行时行为。
- **严重程度（低）**: 不影响正确性、安全性、类型安全或测试覆盖；仅增加维护负担。

### 2-未修复-低-`validate_artifact_ref` 中 `artifact_size_bytes < 0` 分支无测试覆盖

- **入口/函数**: `validate_artifact_ref`
- **文件(行号)**: dayu/host/durable/artifact.py:132-133
- **输入场景**: 调用方直接构造 `LocalArtifactRef(artifact_size_bytes=-1, ...)` 并调用 `validate_artifact_ref`。
- **实际分支**: `if artifact_ref.artifact_size_bytes < 0` → `raise HostDurableError("Artifact size must be non-negative")`。
- **预期行为**: 该分支应在单元测试中被触发并断言抛出 `HostDurableError`。
- **实际行为**: 当前所有测试中 `artifact_size_bytes` 均来自 `len(content)` 或手工设为正数（如 `7`），负值路径从未被执行。覆盖报告确认该行在 `Missing` 列中。
- **直接证据**: artifacts.py:132-133；覆盖报告 `dayu/host/durable/artifact.py` Missing 列包含 `133`；`test_artifact_ref_rejects_invalid_relative_paths` 所有用例 `artifact_size_bytes=7`。
- **影响**: 低——生产代码路径中 `artifact_size_bytes` 始终来自 `len(content)`（非负），且 schema 层有 `CHECK payload_size_bytes >= 0` 约束。该分支主要作为防御性校验存在，但测试缺失意味回归不会被自动捕获。
- **建议改法和验证点**: 在 `test_artifact_ref_rejects_invalid_relative_paths` 或单独测试中增加一组 `LocalArtifactRef(..., artifact_size_bytes=-1, ...)` 输入，断言抛出 `HostDurableError`。
- **修复风险（低）**: 仅新增测试断言。
- **严重程度（低）**: 生产路径不可达，schema 层有二次防御；纯测试补齐问题。

## Open Questions

无。

## Adversarial Failure Pass 逐项检查

### Payload Descriptor (payload.py)

| 检查项 | 结果 | 证据 |
|---|---|---|
| payload row + descriptor 同事务写入 | PASS | `write_sqlite_payload` 在同一 `transaction` 内依次 INSERT 两表 (payload.py:204-237) |
| digest/size/metadata canonical | PASS | digest=sha256(canonical JSON UTF-8 bytes)；size=len(bytes)；metadata 经 `canonical_json_dumps` 编码 (payload.py:417-436, 349-351) |
| FK/unique/constraint 错误分类 | PASS | 缺失 sqlite_payload FK → `HostForeignKeyError` (test_payload_store.py:303-304)；duplicate payload_ref → `HostUniqueConstraintError` |
| 拒绝多余 extra payload | PASS | `SQLitePayloadWriteRequest` 为 frozen slots dataclass；`_validate_sqlite_payload_request` 强制 CANONICAL_JSON 不含 payload_bytes、BYTES 必须含 payload_bytes (payload.py:395-404) |
| digest mismatch 不写 row | PASS | `_validate_expected_digest` 在 INSERT 前校验 (payload.py:198-202)；test 断言 rollback 后 0 row (test_payload_store.py:348) |
| expected_digest 格式无效时结构化失败 | PASS | `_require_optional_digest` 调用 `is_sha256_digest` (payload.py:530-531) |
| 缺失 descriptor FK 分类 | PASS | EventLog `_validate_existing_payload_descriptor` 对缺失 descriptor 直接 return，FK 约束在 INSERT 时生效 (event_log.py:520-521) |

### Artifact Helper (artifact.py)

| 检查项 | 结果 | 证据 |
|---|---|---|
| 不读 cwd/env | PASS | `artifact_root` 必须由调用方显式注入 `LocalArtifactStore.__init__` (artifact.py:51)；test 断言 cwd 下无 sha256 目录 (test_artifact_store.py:120) |
| root 注入 | PASS | `LocalArtifactStore(artifact_root)` 接收显式 Path (artifact.py:51-64) |
| temp 固定在 artifact_root/.tmp | PASS | `_ARTIFACT_TEMP_DIR_NAME = ".tmp"`；`_write_temp_file_under_root` 用 `root / ".tmp"` (artifact.py:338) |
| null byte 防护 | PASS | `_validate_relative_path_text` 检查 `"\x00"` (artifact.py:179) |
| absolute path 防护 | PASS | `path.is_absolute()` 检查 (artifact.py:182) |
| `..` / `.` traversal 防护 | PASS | `any(part in ("", ".", "..") for part in path.parts)` (artifact.py:184) |
| symlink containment | PASS | `_ensure_contained` 用 `resolve(strict=True)` + `relative_to` (artifact.py:255-258)；`_ensure_parent_dir_contained` 逐级检查已有祖先 (artifact.py:263-278)；test 验证 symlink escape 被拒绝 (test_artifact_store.py:154-155) |
| fsync 顺序 | PASS | temp write + file fsync (artifact.py:296-300) → temp digest verify (artifact.py:93-95) → mkdir parent (artifact.py:97) → atomic rename (artifact.py:99) → directory fsync (artifact.py:100) → final digest verify (artifact.py:101-103) |
| temp path 不进入 EventLog | PASS | `_is_temp_relative_path` 检查首路径段为 `.tmp` (artifact.py:196)；`validate_artifact_ref` 拒绝 temp 路径 (artifact.py:128-129)；`_validate_existing_payload_descriptor` 调 `validate_artifact_ref` (event_log.py:532-538)；test 确认 .tmp 不进入 EventLog 引用 (test_artifact_store.py:261-262, 373-374) |
| temp 文件名唯一 | PASS | 使用 `tempfile.mkstemp(prefix="artifact-", suffix=".tmp")` (artifact.py:292-293) |
| 错误路径清理 temp | PASS | `write_artifact_bytes` 在异常分支调用 `_unlink_if_exists(temp_path)` (artifact.py:112-116) |

### EventLog Targeted Update (event_log.py)

| 检查项 | 结果 | 证据 |
|---|---|---|
| existing descriptor digest 校验 | PASS | `_validate_existing_payload_descriptor` 对比 `descriptor.payload_digest != payload_digest` 时抛出 `HostPayloadReferenceError` (event_log.py:522-524) |
| artifact ref 校验 | PASS | 对 `ARTIFACT_REF` 类型 descriptor 构造 `LocalArtifactRef` 并调 `validate_artifact_ref` (event_log.py:532-538) |
| 缺失 descriptor 仍由 FK 分类 | PASS | `descriptor is None` → return，不抛异常 (event_log.py:520-521)；test 确认 `HostForeignKeyError` (test_payload_store.py:303-304) |
| 无循环依赖 | PASS | event_log → payload → artifact → codec/errors；无反向导入 |
| 不引入 scope creep | PASS | `_validate_existing_payload_descriptor` 仅做 digest 一致性 + artifact ref 格式校验，不写 descriptor、不实现 command path、不接触 Session/Run/Attempt |
| descriptor artifact_relative_path 为 None 时失败 | PASS | artifact descriptor 若 `artifact_relative_path is None` 抛出 `HostPayloadReferenceError` (event_log.py:529-530) |

### Host Instance Liveness (liveness.py)

| 检查项 | 结果 | 证据 |
|---|---|---|
| 只表达 current instance diagnostic | PASS | register/heartbeat/mark 都只能作用于匹配 `host_instance_id + process_start_token + pid + boot_id` 的 row (liveness.py:190-192, 332-333) |
| 不实现 lease/fencing/takeover | PASS | 无 lease TTL、fencing token、takeover grant 相关字段或逻辑 |
| 不碰 dispatch record | PASS | 无 `dispatch_records` 表引用；不 join、不读取 |
| 不碰 Run/Attempt | PASS | 无 `run_id`/`attempt_id` 字段或状态更新 |
| register 幂等刷新 | PASS | 同 identity 重复 register 执行 UPDATE 而非 INSERT (liveness.py:191-202)；test 验证 created_at 不变、status 变回 RUNNING (test_host_instance_liveness.py:142-147) |
| register 同 id 不同 token 冲突 | PASS | `_require_same_identity` 抛 `HostInstanceIdentityConflictError` (liveness.py:383-385)；test 验证 (test_host_instance_liveness.py:161-165) |
| heartbeat 只刷新当前 identity | PASS | UPDATE WHERE `host_instance_id = ? AND process_start_token = ?` (liveness.py:232-233)；test 验证不刷新另一个 instance (test_host_instance_liveness.py:199-204) |
| heartbeat 未注册抛 NotRegisteredError | PASS | existing is None → `HostInstanceNotRegisteredError` (liveness.py:224-225)；test 验证 (test_host_instance_liveness.py:211-215) |
| heartbeat 错误 token 抛 IdentityConflictError | PASS | `_require_same_identity` 抛异常 (liveness.py:226)；test 验证 heartbeat_at 不变 (test_host_instance_liveness.py:249-250) |
| mark stopping/stopped best-effort | PASS | row 缺失返回 None (liveness.py:330-331)；test 验证 (test_host_instance_liveness.py:260-265) |
| `CRASHED_SUSPECTED` 仅定义不写入 | PASS | enum 定义存在 (liveness.py:30)；Phase 2 代码无写入该状态路径 |

### 测试覆盖（对照 Plan 要求）

| Plan 要求 | 覆盖状态 | 证据 |
|---|---|---|
| canonical JSON payload 写入 payload row + descriptor 同事务 | PASS | test_payload_store.py:119-177 |
| bytes payload 写入 | PASS | test_payload_store.py:180-228 |
| descriptor read 返回 typed descriptor | PASS | test_payload_store.py:231-258 |
| 缺失 sqlite payload FK 失败 | PASS | test_payload_store.py:262-304 |
| digest mismatch 不写 row | PASS | test_payload_store.py:307-348 |
| EventLog 引用既有 descriptor | PASS | test_payload_store.py:351-393 |
| EventLog digest mismatch → HostPayloadReferenceError | PASS | test_payload_store.py:396-435 |
| artifact 写入注入 root 非 cwd/env | PASS | test_artifact_store.py:110-120 |
| 拒绝绝对路径/null byte/../.tmp | PASS | test_artifact_store.py:123-142 |
| symlink escape 拒绝 | PASS | test_artifact_store.py:145-155 |
| temp 在 artifact_root/.tmp 且不碰撞 | PASS | test_artifact_store.py:158-171 |
| digest verify 在 descriptor 写入之前 | PASS | test_artifact_store.py:174-201 |
| final artifact 发布后 digest 匹配 | PASS | test_artifact_store.py:204-219 |
| EventLog 不引用 temp path | PASS | test_artifact_store.py:222-262 |
| SQLite rollback 后 orphan 非 fact | PASS | test_artifact_store.py:265-317 |
| EventLog 拒绝 temp descriptor | PASS | test_artifact_store.py:320-380 |
| register 插入 RUNNING | PASS | test_host_instance_liveness.py:72-93 |
| 同 identity 重复 register 幂等刷新 | PASS | test_host_instance_liveness.py:96-147 |
| 同 id 不同 token register 冲突 | PASS | test_host_instance_liveness.py:150-166 |
| heartbeat 只刷新同 identity | PASS | test_host_instance_liveness.py:169-204 |
| heartbeat 未注册抛异常 | PASS | test_host_instance_liveness.py:207-216 |
| heartbeat 错误 token 冲突 | PASS | test_host_instance_liveness.py:219-250 |
| mark stopping/stopped best-effort | PASS | test_host_instance_liveness.py:253-280 |
| read typed row + 不提供 orphan proof | PASS | test_host_instance_liveness.py:283-308 |
| payload_inline_threshold 可覆盖 | PASS | test_payload_store.py:106-117 |

### 强类型与架构边界

| 检查项 | 结果 | 证据 |
|---|---|---|
| 无 Any/object/无类型签名 | PASS | AST 扫描确认 4 个新模块 0 处使用 Any/object |
| 中文 docstring 完整 | PASS | 所有模块、类、函数均有中文 docstring 含 params/returns/raises |
| 无反向依赖 | PASS | 导入链 event_log→payload→artifact→codec/errors，无循环 |
| 无 runtime/Engine/Fins/Service/UI 导入 | PASS | AST 导入边界扫描确认 0 处跨层导入 |
| `dayu.host` 包根不导出 durable 内部 | PASS | 现有 test_package_exports.py 覆盖；Slice 3 无新增包根导出 |

### README 更新

| 检查项 | 结果 | 证据 |
|---|---|---|
| dayu/host/README.md 职责范围内更新 | PASS | 从"未实现"移出 payload/artifact/liveness，新增已实现描述和更新后的非目标列表 |
| tests/README.md 职责范围内更新 | PASS | 新增 Slice 3 测试命令，更新 durable foundation 覆盖描述 |
| 未修改禁止文件 | PASS | docs/host/design.md、docs/host/implementation-control.md 未变更 |

## Residual Risk

- artifact.py 单文件覆盖率 79%，略低于 80% 目标。未覆盖行主要是文件系统 OSError 路径（目录 open/fsync/mkdir 失败、unlink 失败等），这些路径在单元测试中难以触发。artifact.py 安全关键逻辑（路径 traversal 拒绝、symlink containment、digest verify、temp 清理）已有直接测试覆盖。缺失的覆盖为环境故障路径，不影响安全断言。
- `CRASHED_SUSPECTED` 状态在 enum 中定义但 Phase 2 未写入。后续 recovery phase 写入该状态时需要通过测试验证事务正确性。当前无风险——仅 enum 定义。
- SQLite 与文件系统 artifact publish 非原子：已由 plan 显式接受，测试覆盖了 rollback 后 orphan 窗口（test_artifact_store.py:265-317）。

## 结论

**PASS** — 两个低严重度 finding (代码重复、测试补缺) 均不阻塞合并。

生产代码正确实现了 Plan Slice 3 全部要求：payload descriptor 同事务写入与 FK 校验、artifact 路径安全（无 cwd/env 依赖、temp 隔离、symlink/traversal/null byte 防护、fsync/digest verify/atomic rename 顺序正确）、EventLog descriptor 引用校验（digest 一致性 + artifact ref 格式 + temp 路径拒绝 + FK 缺失委托）、liveness 严格限定 current instance diagnostic。无反向依赖、无跨层污染、强类型、完整中文 docstring。全部 92 个 Host 测试通过，pyright 零报错，runtime 回归干净。
