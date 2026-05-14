# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase2-durable-store-eventlog
- Base: main
- Output file: docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-ds-20260514.md
- Included scope: full diff of `dayu/host/durable/` (12 production modules), `dayu/host/README.md`, `tests/host/` (8 test files), `tests/README.md`
- Excluded scope: `docs/host/design.md`, `docs/host/implementation-control.md` (explicitly forbidden by plan), `docs/reviews/` artifacts (review process records, not production code)
- Parallel review coverage:
  - Agent1: Slice 1 production code (errors, codec, options, schema, connection, transaction, `__init__`) — fully covered
  - Agent2: Slice 2 production code (event_log, idempotency) — fully covered
  - Agent3: Slice 3 production code (payload, artifact, liveness, _validation) — fully covered
  - Main reviewer: cross-cutting architecture boundary verification, README sync, import boundary, plan semantic alignment, test coverage overview, findings adjudication and severity classification

## Validation Summary

- `pytest tests/host -q`: 94 passed, 0 failed
- `pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q`: 29 passed, 0 failed
- `python -m pyright dayu/host tests/host`: 0 errors, 0 warnings
- `python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings

## Architecture Boundary Verification

### Layer Isolation (PASS)

- `dayu/host/durable/` does not import from `dayu.engine`, `dayu.fins`, `dayu.service`, `dayu.ui`: **confirmed** (zero matches via grep)
- `dayu/runtime/` has no changes in this diff: **confirmed** (no runtime files modified)
- `dayu/runtime/` does not import from `dayu.host.durable`: **confirmed** (zero matches)
- Host durable truth is contained entirely within `dayu.host.durable`: **confirmed**
- `dayu.host` package root does not export durable internal modules: **confirmed** (verified via `tests/host/test_package_exports.py`)

### Plan Semantic Alignment (PASS)

- Schema convention (TEXT ids, UTC ISO-8601 timestamps, canonical JSON, `PRAGMA user_version=1`, `foreign_keys=ON`, WAL): **matches plan**
- Transaction runner (`BEGIN IMMEDIATE`, busy/locked retry only, non-retryable constraint/digest/idempotency errors): **matches plan**
- EventLog append/read (global `event_sequence`, `AUTOINCREMENT`, duplicate `event_id` digest compare, `event_body_digest` excludes DB-assigned fields): **matches plan**
- Idempotency primitive (`(scope_kind, scope_id, idempotency_key)` unique, same-digest returns existing, different-digest raises conflict): **matches plan**
- Payload descriptor (`sqlite_payload` / `artifact_ref`, FK constraints, CHECK constraints, inline threshold): **matches plan**
- Artifact write ordering (temp under `.tmp/`, digest verify, atomic rename, SQLite descriptor after): **matches plan**
- Host instance liveness (register/register idempotent/heartbeat/mark/read, no lease/fencing/takeover): **matches plan**
- No Session/Run/Attempt tables created: **confirmed** (DDL only creates `event_log`, `idempotency_records`, `host_sqlite_payloads`, `payload_descriptors`, `host_instances`)

### README Sync (PASS)

- `dayu/host/README.md`: Durable Foundation section describes current implemented boundary, non-goals, and architecture constraints — matches code facts
- `tests/README.md`: durable foundation test commands and descriptions match current test files — matches code facts
- Root `README.md`: not modified (no user-facing CLI/workflow change — correct per plan)
- `dayu/README.md`: not modified (no terminology change — correct per plan)

## Findings

### 1-未修复-中-_validation.py require_non_empty_text 对 None 输入崩溃

- **入口/函数**: `_validation.require_non_empty_text`
- **文件(行号)**: `dayu/host/durable/_validation.py` (23)
- **输入场景**: 调用方误将 `None` 传入 `require_non_empty_text(value, field_name=...)`，例如类型检查绕过（运行时 Python 不强制类型注解）、或 dataclass 字段为 `str | None` 但验证时未提前判空。
- **实际分支**: `value == ""` 对 `None` 返回 `False`，进入 `value.isspace()` → `AttributeError: 'NoneType' object has no attribute 'isspace'`
- **预期行为**: 抛出结构化 `HostDurableError("field_name must be non-empty")`，而非裸 `AttributeError`
- **实际行为**: 裸 `AttributeError` 上抛，绕过了 Host durable error 的语义分类
- **直接证据**: 第 23 行 `if value == "" or value.isspace():` — 无 `value is None` 前置守卫；对比 `require_optional_non_empty_text`（第 38 行）有 `value is not None` 前置检查
- **影响**: 错误分类逃逸——调用方看到 Python 运行时错误而非业务语义错误，事务 runner 中的 `except HostDurableError` 无法捕获，事务回滚路径仍正确但错误消息误导调试
- **建议改法和验证点**: 在第 23 行前增加 `if not isinstance(value, str): raise HostDurableError(...)` 守卫；补充 `test_validation.py` 覆盖 `None`、`int`、`bytes` 等非预期类型输入
- **修复风险（低）**: 纯防御性守卫，不改变正常路径行为
- **严重程度（中）**: 当前调用链中所有 `require_non_empty_text` 调用方类型签名均为 `str`（非 optional），实际触发概率低，但该函数是通用 validation helper，未来调用方可能传入 `str | None` 类型

### 2-未修复-中-idempotency _validate_result_ref 未强制 created_event_id/created_event_sequence 一致性

- **入口/函数**: `idempotency._validate_result_ref`
- **文件(行号)**: `dayu/host/durable/idempotency.py` (246-252)
- **输入场景**: 调用方构造 `IdempotencyResultRef(created_event_id="evt_123", created_event_sequence=None)` 或 `(created_event_id=None, created_event_sequence=5)`
- **实际分支**: 两个字段独立校验——第 246 行校验 `created_event_id` 非空（若提供），第 249 行校验 `created_event_sequence` 正值（若提供）。无交叉一致性检查要求两者同时为 `None` 或同时非 `None`
- **预期行为**: 两个 FK 字段（`FOREIGN KEY(created_event_id) REFERENCES event_log(event_id)` 和 `FOREIGN KEY(created_event_sequence) REFERENCES event_log(event_sequence)`）应同时设置或同时不设置；不一致的中间状态是语义错误
- **实际行为**: 不一致记录可写入 `idempotency_records` 表。SQLite 对 NULL FK 不强制执行，schema 无 CHECK 约束覆盖此一致性
- **直接证据**: 第 246-248 行与第 249-252 行相互独立，无 `(result.created_event_id is None) != (result.created_event_sequence is None)` 等价检查
- **影响**: 下游 reader 读到 `created_event_id` 有值但 `created_event_sequence=None` 时，无法用 cursor 从 EventLog 回读对应事件；plan §Idempotency Primitive 定义 `created_event_sequence` 用于引用已创建事件，不一致记录破坏了此引用完整性
- **建议改法和验证点**: 在第 252 行后增加: `if (result.created_event_id is None) != (result.created_event_sequence is None): raise HostDurableError("created_event_id and created_event_sequence must be both set or both unset")`；在 `test_idempotency_store.py` 中补充只设一个字段的测试
- **修复风险（低）**: 纯验证增强，不改变既有正常路径
- **严重程度（中）**: plan 定义的 FK 引用完整性约束被绕过

### 3-未修复-中-artifact _fsync_directory 在 macOS/Darwin 可能系统性失败

- **入口/函数**: `artifact._fsync_directory`
- **文件(行号)**: `dayu/host/durable/artifact.py` (226-243)
- **输入场景**: 任何调用 `write_artifact_bytes` 的 macOS 部署环境（当前运行平台为 Darwin）
- **实际分支**: `os.fsync(fd)` 对目录 fd 调用，在 macOS 上可能返回 `EINVAL`（`fsync(2)` 对目录不保证支持），触发 `OSError` → 被第 241 行转换为 `HostArtifactWriteError("Artifact directory fsync failed")`
- **预期行为**: 目录 fsync 是附加耐久性保证，不应成为 artifact 写入的阻塞条件；`os.replace()` 已提供 POSIX 原子 rename 保证
- **实际行为**: 若 macOS 内核版本或文件系统不支持目录 fsync，所有 artifact 写入系统性失败
- **直接证据**: 第 239 行 `os.fsync(fd)` 无平台 fallback；`write_artifact_bytes` 第 100 行调用 `_fsync_directory` 在 `os.replace()` 成功后，若此处失败 artifact 虽已原子发布但整个操作报告失败
- **影响**: 部署在 macOS 上时所有大 payload artifact 写入可能全部失败，造成静默不可用
- **建议改法和验证点**: 将 `_fsync_directory` 中的 `except OSError as exc: raise HostArtifactWriteError(...)` 改为 catch 后 return（静默跳过目录 fsync 失败），因为 `os.replace()` 已保证原子性；或在 macOS 上使用 `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` 作为替代。在 artifact 测试中明确验证 macOS 兼容性
- **修复风险（低）**: 降级目录 fsync 从阻塞错误到静默跳过，不影响已通过 `os.replace()` 发布的文件原子性
- **严重程度（中）**: 运行平台为 Darwin，可能系统性影响 artifact 写入路径

### 4-未修复-低-transaction _classify_sqlite_error 未处理 SQLITE_CONSTRAINT_CHECK

- **入口/函数**: `transaction._classify_sqlite_error`
- **文件(行号)**: `dayu/host/durable/transaction.py` (301-313)
- **输入场景**: schema DDL 中多个 CHECK 约束（`event_class CHECK`, `payload_format CHECK`, `payload_kind CHECK`, `host_instance status CHECK` 等）被违反时，SQLite 返回错误码 `SQLITE_CONSTRAINT_CHECK` (275)
- **实际分支**: 错误码 275 不匹配 `_SQLITE_CONSTRAINT_UNIQUE`(2067)、`_SQLITE_CONSTRAINT_PRIMARYKEY`(1555)、`_SQLITE_CONSTRAINT_FOREIGNKEY`(787)，落入第 313 行通用 `HostDurableError("Host durable SQLite transaction failed")`
- **预期行为**: CHECK 约束违反应产生明确的结构化错误，至少区别于 generic SQLite 失败，以帮助定位是 schema 层约束违反
- **实际行为**: 通用错误消息，丢失约束违反的特异性
- **直接证据**: 第 309-312 行的 `if` 链只处理三种约束码，无 `_SQLITE_CONSTRAINT_CHECK` 分支
- **影响**: 调试时无法区分 CHECK 约束违反（schema 层 bug）与普通 SQLite 执行失败（I/O 或库错误）；但当前 production 代码的预验证（payload.py `_validate_sqlite_payload_request`、event_log.py `_validate_append_request` 等）使直接触发 CHECK 约束的概率很低
- **建议改法和验证点**: 增加 `if code == _SQLITE_CONSTRAINT_CHECK: return HostDurableError("Host durable CHECK constraint failed")`；在 transaction 测试中构造一个绕过预验证的 CHECK 违反场景确认分类正确
- **修复风险（低）**: 纯诊断增强
- **严重程度（低）**: 生产代码有预验证层，直接触发 CHECK 约束概率低；但缺少诊断特异性

### 5-未修复-低-transaction run_write 循环后 raise 为不可达死代码

- **入口/函数**: `transaction.HostTransactionRunner.run_write`
- **文件(行号)**: `dayu/host/durable/transaction.py` (245-248)
- **输入场景**: 不适用（代码路径不可达）
- **实际分支**: `while attempt < max_attempts` 循环体内每个路径都终止（`return result` 成功、`raise` 异常、`continue` 重试），且 `max_attempts >= 1` 保证至少一次迭代
- **预期行为**: 无不可达代码
- **实际行为**: 第 245-248 行的 `raise HostTransactionRetryExhaustedError(...)` 永不被执行
- **直接证据**: 循环体第 216-244 行的四条退出路径：`return result`(244)、`raise HostTransactionRetryExhaustedError`(225-228)、`raise durable_error`(236)、`raise`(239, 242)；`continue`(235) 保持循环继续。无路径落到循环外
- **影响**: 死代码是维护风险——若未来修改循环体引入新路径未覆盖 `raise`，可能错误落入此兜底 `raise`，产生误导的 "retry exhausted" 错误掩盖实际失败原因
- **建议改法和验证点**: 删除第 245-248 行；或将循环改为 `while True` 并把重试耗尽 `raise` 放在循环内，删外部的不可达 `raise`
- **修复风险（低）**: 删除死代码
- **严重程度（低）**: 不产生运行时影响，但违反代码简洁原则

### 6-未修复-低-connection 异常处理中 close() 可能掩盖原始错误

- **入口/函数**: `connection.open_host_durable_store`、`connection._open_configured_connection`
- **文件(行号)**: `dayu/host/durable/connection.py` (153-157, 177-181)
- **输入场景**: 初始化过程中发生 `sqlite3.Error` 或 `HostDurableError`，同时 `connection.close()` 自身也抛出 `sqlite3.Error`（磁盘满、I/O 错误等极端场景）
- **实际分支**: `except (sqlite3.Error, HostDurableError) as exc:` → `connection.close()` → 若 close 抛异常，原始 `exc` 被丢弃
- **预期行为**: 原始错误不应被清理阶段的次要错误掩盖
- **实际行为**: 原始初始化失败原因丢失，调试者只看到 `connection.close()` 的错误
- **直接证据**: 第 153-157 行：`connection.close()` 在 `except` 块内无自身的 try/except 保护
- **影响**: 极端磁盘/I/O 故障场景下错误诊断困难
- **建议改法和验证点**: 将 `connection.close()` 包裹在 `try: ... except sqlite3.Error: pass` 中
- **修复风险（低）**: 纯错误处理增强，不改变成功路径
- **严重程度（低）**: 仅极端故障场景触发

### 7-未修复-低-artifact _ensure_parent_dir_contained 在 write_artifact_bytes 内冗余调用

- **入口/函数**: `artifact.LocalArtifactStore.write_artifact_bytes`
- **文件(行号)**: `dayu/host/durable/artifact.py` (90, 96)
- **输入场景**: 正常 artifact 写入路径
- **实际分支**: 第 90 行 `_contained_final_path` 内部调用 `_ensure_parent_dir_contained`；第 96 行显式再次调用 `_ensure_parent_dir_contained`。两次调用都在 `mkdir` 创建父目录之前，时间窗口相同，无新增安全收益
- **预期行为**: 一次 containment 检查即可
- **实际行为**: 冗余调用，第 96 行是 `_contained_final_path` (line 90) 的同义重复
- **直接证据**: 第 90 行 `_contained_final_path` → 第 312 行调用 `_ensure_parent_dir_contained`；第 96 行直接调用 `_ensure_parent_dir_contained`，两者参数相同（`self._artifact_root`, `relative_path`），都在 `mkdir` 之前
- **影响**: 无运行时错误，但冗余代码增加维护成本，且两份 containment 检查给人以"多重防护"的错觉，实际时间窗口相同
- **建议改法和验证点**: 删除第 96-97 行的显式调用，仅保留 `_contained_final_path` 内的一次 containment 检查（或反之，保留一处并删除另一处）
- **修复风险（低）**: 删除冗余代码
- **严重程度（低）**: 无运行时影响

### 8-未修复-低-liveness _require_same_identity 对 boot_id 从 None 变为有值的相同进程可能误判冲突

- **入口/函数**: `liveness._require_same_identity`
- **文件(行号)**: `dayu/host/durable/liveness.py` (374-392)
- **输入场景**: 进程首次 register 时 `boot_id=None`（无法读取 boot_id 的系统），后续 heartbeat 时 boot_id 变为可读且有值
- **实际分支**: 第 388 行 `row.boot_id != identity.boot_id` — 若 row 中 `boot_id=None` 而 identity 中 `boot_id="abc123"`，`None != "abc123"` 为 `True`，进入冲突分支
- **预期行为**: 同一进程不应因 `boot_id` 从不可用到可用而被拒绝；身份验证应允许 `None` ↔ `value` 的首次具体化
- **实际行为**: `HostInstanceIdentityConflictError` —— 本进程的合法 heartbeat 被拒绝
- **直接证据**: 第 385-389 行对 `pid`、`process_start_token`、`boot_id` 做全等比较，无 `None` 容差
- **影响**: 在 boot_id 读取能力变化的边缘环境（容器、某些 Linux 配置等）中，已注册实例的 heartbeat 可能被拒绝；但当前 `pid` 和 `process_start_token` 的比较足以确认同一进程
- **建议改法和验证点**: 将 `boot_id` 比较改为允许 `None` ↔ `value` 过渡：`(row.boot_id is not None and identity.boot_id is not None and row.boot_id != identity.boot_id)`；或直接删除 `boot_id` 比较仅依赖 `pid` + `process_start_token`
- **修复风险（低）**: 缩小冲突检测范围，不引入安全退化（`pid` + `process_start_token` 已足够确认进程身份）
- **严重程度（低）**: 触发场景依赖 boot_id 可用性变化的边缘环境

## Open Questions

- `artifact._fsync_directory` 在当前 macOS 25 (Darwin 25.3.0) 上是否实际触发 `EINVAL`？需在本机验证 `os.fsync(dir_fd)` 的行为。若当前版本已支持，本 finding 降级为 info
- `PayloadStore` / `EventLogStore` / `IdempotencyStore` / `LocalArtifactStore` / `HostInstanceLivenessStore` 均为无状态 thin method collection，与 plan 明确列举的 target classes 一致；但代码形式为纯委托透传（方法体仅一行调用同名模块函数）。确认这是计划设计意图而非兼容性 wrapper
- `create_artifact_root=True` 默认值的测试覆盖 — 确认 `PayloadStoragePolicy` 默认行为在测试中通过可注入 temp dir 覆盖，不依赖真实 cwd

## Residual Risk

- **artifact 孤儿文件清理**: 已发布但无 descriptor 引用的 artifact 文件（SQLite transaction 在 artifact publish 后失败）无自动清理机制。Plan 明确将此推迟到后续 cleanup/diagnostics work unit。当前代码正确处理了 fact accept barrier（无 descriptor = 不是 accepted fact），但磁盘空间累积是 deferred risk
- **多进程 EventLog 竞争**: `tests/host/test_event_log_multiprocess.py` 覆盖正常短事务并发场景，但未覆盖极端慢事务（持有写锁数秒）、连接池耗尽、或进程崩溃留下未提交事务的 WAL 阻塞场景。这些属于 Phase 11 multi-process hardening 范围
- **`event_body_digest` 计算**: 当前 digest 基于 canonical JSON 输入字段，排除 `event_id`/`event_sequence`/`appended_at`，语义正确。但若未来 EventLog 表增加非业务字段，需确保 digest 计算不被误扩
- **idempotency `created_event_sequence <= 0` 防御性校验**: 无专门负例测试覆盖（该值正常路径始终为正）。当前不阻塞，但若未来 idempotency API 扩展，建议补充
- **`connection._prepare_database_parent` TOCTOU**: `parent.mkdir(parents=True, exist_ok=True)` 在两个进程同时 mkdir + 一个进程将路径替换为文件的竞态下，`exist_ok=True` 允许已存在的文件路径通过（不验证是否为目录），后续 `sqlite3.connect` 会失败但错误消息不够具体。属于极端竞态，实际概率极低

## Conclusion

**PASS**

Phase 2 Durable Store / EventLog / Payload Foundation 实现质量整体良好。测试覆盖全面（94 host tests，29 runtime tests，pyright 0 errors），架构边界整洁（无跨层污染，无运行时模块修改，Host durable truth 仅存在于 `dayu.host.durable`），plan 语义对齐（schema / transaction / EventLog / idempotency / payload / artifact / liveness 行为与 plan 一致）。

发现 8 个 findings：3 个中等严重性和 5 个低严重性。无严重（critical）或高严重性 finding。中等 finding 涉及 defensive validation gap（`require_non_empty_text` None 守卫）、FK 引用一致性（`created_event_id` / `created_event_sequence` 交叉校验）和 macOS 平台兼容性（目录 fsync 潜在失败）。所有 findings 均可通过局部修复解决，修复风险低，不涉及架构或契约变更。

不阻止 Phase 2 进入 Phase 3 (Session / Run / Attempt 状态机与 Admission)。
