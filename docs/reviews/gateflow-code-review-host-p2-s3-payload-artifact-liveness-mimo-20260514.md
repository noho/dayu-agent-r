# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase2-durable-store-eventlog`
- Base: `main`
- Output file: `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-mimo-20260514.md`
- Included scope:
  - `dayu/host/durable/payload.py` (new)
  - `dayu/host/durable/artifact.py` (new)
  - `dayu/host/durable/liveness.py` (new)
  - `dayu/host/durable/event_log.py` (targeted update: `_validate_existing_payload_descriptor`)
  - `dayu/host/README.md`, `tests/README.md`
  - `tests/host/test_payload_store.py` (new)
  - `tests/host/test_artifact_store.py` (new)
  - `tests/host/test_host_instance_liveness.py` (new)
  - `docs/reviews/gateflow-implementation-host-p2-s3-payload-artifact-liveness-20260514.md`
- Excluded scope: Slice 1/2 committed code, `dayu.runtime`, Engine/Fins/Service/UI
- Parallel review coverage: 无

## Findings

### 1-未修复-低-durable 内部 validation helper 跨三模块重复

- **入口/函数**: `_require_non_empty_text`、`_require_optional_non_empty_text`、`_require_text`、`_optional_text`、`_require_int`
- **文件(行号)**:
  - `dayu/host/durable/payload.py:493-573`
  - `dayu/host/durable/liveness.py:416-483`
  - `dayu/host/durable/event_log.py:594-661`
- **输入场景**: 每次新增 durable 子模块时
- **实际分支**: 三个模块各自独立实现完全相同的 5 个 `_require_*` helper
- **预期行为**: 重复逻辑必须抽取到共享模块（CLAUDE.md 编码硬约束：「数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取」）
- **实际行为**: 每个模块 copy-paste 相同的 5 个 helper 函数（约 80 行 x 3 = 240 行）
- **直接证据**:
  - `payload.py:493` / `liveness.py:416` / `event_log.py:594`: `_require_non_empty_text` 实现完全相同
  - `payload.py:534` / `liveness.py:444` / `event_log.py:622`: `_require_text` 实现完全相同
  - `payload.py:548` / `liveness.py:458` / `event_log.py:636`: `_optional_text` 实现完全相同
  - `payload.py:562` / `liveness.py:472` / `event_log.py:650`: `_require_int` 实现完全相同
- **影响**: 修改验证逻辑时需要同步三处；新增 durable 子模块时容易遗漏或不一致。不影响 correctness 或 stability。
- **建议改法和验证点**: 将 5 个 `_require_*` helper 抽取到 `dayu/host/durable/_validation.py`（或在 `codec.py` 中扩展），三模块改为 import。运行全量 host 测试确认无回归。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- **artifact fsync window**: `artifact.py:99-100` 中 `os.replace` 后 `_fsync_directory(final_path.parent)` 的顺序在 `dirsync` 未启用的文件系统上存在极窄的 crash 窗口（rename 后、fsync 前崩溃可能丢失 directory entry）。当前实现已是最佳实践，这是文件系统语义限制，非代码缺陷。
- **`CRASHED_SUSPECTED` 枚举值**: `liveness.py:30` 定义了 `CRASHED_SUSPECTED` 但无任何代码路径写入该状态，也无测试覆盖。该值是 diagnostics 基础的前置占位，schema CHECK 约束已包含，风险可控。

## Review Detail

### 1. Payload Descriptor Schema/Helper

**schema 约束验证** (`schema.py:56-80`):

- `payload_descriptors` CHECK 约束正确强制 `sqlite_payload_id` 与 `artifact_relative_path` 互斥。
- FOREIGN KEY `sqlite_payload_id -> host_sqlite_payloads(payload_id)` 正确。
- `payload_size_bytes >= 0` CHECK 正确。
- `payload_kind IN ('sqlite_payload', 'artifact_ref')` CHECK 正确。

**写入事务原子性** (`payload.py:196-241`):

- `write_sqlite_payload` 在同一个 `HostTransaction` 中先 INSERT `host_sqlite_payloads`，再 INSERT `payload_descriptors`，然后 `read_payload_descriptor` 读回。事务内一致性正确。
- `_encode_sqlite_payload` 对 canonical JSON 基于 UTF-8 bytes 计算 digest，对 bytes payload 基于原始 bytes 计算 digest，符合 codec 规范。

**错误分类**:

- `expected_digest` 不匹配抛出 `HostDigestMismatchError`（`payload.py:454`），在写入任何 row 之前，事务回滚。
- FK 缺失由 SQLite 约束分类为 `HostForeignKeyError`（`transaction.py:311-312`）。
- 不接受多余 extra payload：`SQLitePayloadWriteRequest` 只包含计划中定义的字段。

**结论**: payload descriptor schema/helper 正确。

### 2. Artifact Helper 路径安全

**root 注入** (`artifact.py:51-64`):

- `LocalArtifactStore.__init__` 接受 `artifact_root: Path`，不读取 cwd/env。`_prepare_artifact_root` 只在 `create=True` 时 mkdir，否则校验存在且为目录。

**temp 在 `.tmp`** (`artifact.py:329-342`):

- `_write_temp_file_under_root` 固定 temp 目录为 `root / ".tmp"`。`tempfile.mkstemp` 保证 exclusive creation，concurrent writers 不碰撞。

**symlink/traversal/null byte/absolute path 防御**:

- `artifact.py:169-186` (`_validate_relative_path_text`): 拒绝空、绝对、含 null byte、含 `..` / `.` / 空 part 的路径。
- `artifact.py:246-260` (`_ensure_contained`): `resolve(strict=True)` 后 `relative_to` 校验，检测 symlink 逃逸。
- `artifact.py:263-278` (`_ensure_parent_dir_contained`): 创建目录前检查已存在祖先目录的 symlink 逃逸。
- `artifact.py:128` (`validate_artifact_ref`): 拒绝 `.tmp` 前缀路径。

**fsync/digest verify/atomic rename 顺序** (`artifact.py:92-116`):

1. `sha256_digest_bytes(content)` 计算 expected digest
2. `_write_temp_file`: `mkstemp` → `write` → `flush` → `os.fsync`
3. `_read_file_digest(temp_path)` 校验 temp 内容
4. `_ensure_parent_dir_contained` 校验祖先目录
5. `os.replace(temp_path, final_path)` 原子 rename
6. `_fsync_directory(final_path.parent)` 持久化 directory entry
7. `_read_file_digest(final_path)` 最终校验
8. `validate_artifact_ref(artifact_ref)` 路径/digest/size 校验

顺序正确。异常路径中 temp 文件被清理（`artifact.py:111-116`）。

**temp path 不进入 EventLog**: 见下方 Finding 3。

**结论**: artifact helper 路径安全正确。

### 3. EventLog 对 Existing Descriptor 的校验

**`_validate_existing_payload_descriptor`** (`event_log.py:500-543`):

- descriptor 存在时：校验 `descriptor.payload_digest == payload_digest`；对 `ARTIFACT_REF` 类型进一步校验 `artifact_relative_path` 非 None 且 `validate_artifact_ref` 通过（拒绝 `.tmp` 路径）。
- descriptor 不存在时：返回，由 SQLite FK 约束分类为 `HostForeignKeyError`。
- `payload_ref is None` 时：直接返回。

**循环依赖检查**: `event_log.py` → `artifact.py`（`LocalArtifactRef`, `validate_artifact_ref`）→ `codec.py`。`payload.py` → `artifact.py` → `codec.py`。无环。

**scope creep 检查**: `_validate_existing_payload_descriptor` 只做读取校验，不写入 descriptor、不创建 artifact、不修改 EventLog row。职责边界清晰。

**结论**: EventLog 校验逻辑正确，无循环依赖或 scope creep。

### 4. Host Instance Liveness

**只表达 current instance diagnostic**:

- `register_current_instance` (`liveness.py:150-206`): INSERT 或 UPDATE（幂等刷新 heartbeat + status 为 `RUNNING`）。
- `heartbeat_current_instance` (`liveness.py:209-244`): UPDATE heartbeat，WHERE 同时匹配 `host_instance_id` + `process_start_token`。
- `mark_current_instance_stopping/stopped` (`liveness.py:247-278`): best-effort UPDATE，row 不存在返回 None。
- `_require_same_identity` (`liveness.py:367-385`): 校验 pid + process_start_token + boot_id。

**不碰 dispatch record / Run / Attempt**: 模块不 import 任何非 durable 模块，不引用 `event_log`、`idempotency` 或外部状态机。

**不变成 lease/fencing/takeover/orphan proof**: 无 TTL、无 lease acquire/release、无 orphan 判定逻辑。`CRASHED_SUSPECTED` 枚举值是 schema 占位，无代码路径写入。

**结论**: liveness 只表达 current instance diagnostic，符合计划约束。

### 5. 测试覆盖

**plan 要求 vs 实际测试**:

| Plan 测试要求 | 实际测试 | 状态 |
|---|---|---|
| canonical JSON payload + descriptor 同事务 | `test_canonical_json_payload_writes_payload_and_descriptor` | 已覆盖 |
| bytes payload digest/size | `test_bytes_payload_writes_bytes_descriptor_and_digest` | 已覆盖 |
| descriptor read typed | `test_read_payload_descriptor_returns_typed_descriptor` | 已覆盖 |
| missing FK → foreign key error | `test_descriptor_with_missing_sqlite_payload_fk_fails` | 已覆盖 |
| digest mismatch → no row | `test_payload_digest_mismatch_raises_without_writing_rows` | 已覆盖 |
| EventLog ref existing descriptor | `test_event_log_can_reference_existing_descriptor_and_digest` | 已覆盖 |
| EventLog digest mismatch | `test_event_log_payload_digest_mismatch_raises_reference_error` | 已覆盖 |
| artifact writes under injected root | `test_artifact_helper_writes_under_injected_root` | 已覆盖 |
| path rejection | `test_artifact_ref_rejects_invalid_relative_paths` | 已覆盖 |
| symlink escape | `test_artifact_helper_rejects_symlink_escape` | 已覆盖 |
| temp under .tmp, no collision | `test_temp_area_is_under_artifact_root_and_concurrent_writes_do_not_collide` | 已覆盖 |
| temp not in EventLog | `test_event_log_references_descriptor_not_artifact_temp_path` | 已覆盖 |
| digest verify before descriptor write | `test_digest_verify_happens_before_descriptor_write` | 已覆盖 |
| final published + digest match | `test_final_artifact_is_published_and_digest_matches` | 已覆盖 |
| SQLite failure → orphan not fact | `test_sqlite_failure_after_artifact_publish_leaves_orphan_not_fact` | 已覆盖 |
| EventLog rejects temp path descriptor | `test_event_log_rejects_descriptor_with_artifact_temp_path` | 已覆盖 |
| register + timestamps | `test_register_inserts_running_instance_with_timestamps` | 已覆盖 |
| idempotent register | `test_repeated_register_same_identity_refreshes_heartbeat_and_status` | 已覆盖 |
| same id diff token → conflict | `test_register_same_id_different_token_raises_identity_conflict` | 已覆盖 |
| heartbeat same identity only | `test_heartbeat_updates_only_same_identity` | 已覆盖 |
| heartbeat missing → error | `test_heartbeat_missing_registration_raises` | 已覆盖 |
| heartbeat wrong token → conflict | `test_heartbeat_wrong_token_raises_identity_conflict` | 已覆盖 |
| mark best-effort | `test_mark_stopping_and_stopped_are_best_effort_when_absent` | 已覆盖 |
| read typed + no orphan proof | `test_read_returns_typed_row_and_liveness_is_not_orphan_proof` | 已覆盖 |
| inline threshold override | `test_default_payload_inline_threshold_can_be_overridden` | 已覆盖 |

**不绕过真实 transaction/schema**: 所有测试使用 `open_host_durable_store` + `transaction_runner.run_write`，通过真实 SQLite schema。

**结论**: 测试覆盖完整，与计划要求一致。

### 6. 强类型 / 编码规范

- pyright: `0 errors, 0 warnings, 0 informations`。
- 所有函数有完整中文 docstring（参数、返回值、异常）。
- 无 `Any`、`object`、无类型参数、无类型返回值。
- 无反向依赖：`payload.py` / `artifact.py` / `liveness.py` / `event_log.py` 不 import `dayu.runtime` / `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui`。
- `dayu/host/durable/__init__.py` 为空，不导出内部模块。

## 验证记录

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q` | 25 passed |
| `pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q` | 15 passed |
| `pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py tests/host/test_event_log_multiprocess.py -q` | 20 passed |
| `pytest tests/host -q` | 92 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q` | 29 passed |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |

## 结论

**PASS** — 发现 1 项低严重程度 maintainability finding（durable 内部 validation helper 跨三模块重复）。无 correctness 或 stability 阻断项。payload descriptor、artifact helper、EventLog 校验、host instance liveness 实现均符合 approved plan 与架构约束。测试覆盖完整，pyright 清洁。
