# WU-RET-00 Aggregate Deep Review — DS

## Scope

- **Mode**: current changes (aggregate deepreview)
- **Branch**: `work/wu-ret-00-retention`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-ret-00-aggregate-deepreview-ds.md`
- **Review date**: 2026-06-12
- **Reviewer**: AgentDS

### Included scope

全量 WU-RET-00 已提交改动（commits `a2f94be0` plan、`473f1e6d` slice 1、`9c044934` slice 2、`4691ad9b` slice 3、`f5b1cccd` slice 4）相对 `main` 的 diff，包含：

- **生产代码**:
  - `dayu/host/durable/artifact.py` — 新增 `iter_published_artifact_relative_paths`、`delete_artifact_file`
  - `dayu/host/durable/storage_lifecycle.py` — 全新模块：`HostStorageUsageReport`、`read_storage_usage`、`artifact_relative_path_is_referenced`、`collect_referenced_artifact_paths`、`scan_orphan_artifact_files`、`reclaim_orphan_artifact_files`、`physical_artifact_bytes`
  - `dayu/host/storage_maintenance.py` — 全新模块：Host facade（`report_storage_usage`、`run_storage_maintenance`）及类型
  - `dayu/host/command.py` — 新增 `_db_path()`、`_artifact_root()`、`_open_durable_connection()` 三个 typed accessor
  - `dayu/host/open_host.py` — `_PublicHostHandle` 新增 async wrapper
  - `dayu/host/api.py` — `Host` Protocol 新增 `report_storage_usage`、`run_storage_maintenance` 方法签名
  - `dayu/host/__init__.py` — 包根导出新增符号
- **文档**:
  - `docs/host/design.md` — 增补 maintenance public boundary 设计说明
  - `docs/host/issues-implementation-control.md` — WU-RET-00 状态更新及 gate artifact 清单
  - `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md` — accepted plan
  - `dayu/host/README.md` — 新增 "Storage Usage Report" 和 "Storage Maintenance" 小节
  - `tests/README.md` — 测试 inventory 增补
- **测试**:
  - `tests/host/test_artifact_store.py` — Slice 1: 枚举、删除、namespace 安全、symlink 逃逸拒绝
  - `tests/host/test_storage_usage_report.py` — Slice 2: report 只读面
  - `tests/host/test_storage_orphan_proof.py` — Slice 3: 删除证明原语
  - `tests/host/test_storage_maintenance.py` — Slice 3+4: maintenance dry-run / opt-in reclaim / error / 幂等
  - `tests/host/test_package_exports.py` — 包根导出更新
- **Review artifacts**: 各 slice 的 code-review / fix / re-review 文档（已在 `docs/reviews/` 下，不作为本 review 的 review 对象）

### Excluded scope

- 既有的 `purge.py` 删除事务语义（本 WU 不改写）
- `dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、`dayu/runtime/`（无接口耦合）
- GitHub Issue #43 本体内容
- 各 slice 的 MiMo/DS/Codex review artifact（仅作为背景参考，不作为被 review 对象）
- `docs/reviews/` 下已有 slice-level review 文档

### Review method

本 review 严格遵循 deepreview skill 定义的 Current Changes Mode 方法论：
1. 阅读 accepted plan、设计真源、总控真源，理解 change intent
2. 沿真实代码路径（entry point → durable read/write → file I/O → error mapping → async wrapper）逐行走读
3. 对每个关键函数展开入参→条件判断→下游调用→返回值/raise→副作用
4. 执行 adversarial failure pass：检查空状态、错误路径、并发/TOCTOU、symlink 逃逸、类型违反、分层边界、测试覆盖真实性

## Findings

### 001-未修复-低-Protocol 和 async handle docstring 标注 "dry-run" 与实际破坏性行为不一致

- **入口/函数**: `Host.run_storage_maintenance` (Protocol) 和 `_PublicHostHandle.run_storage_maintenance` (async wrapper)
- **文件(行号)**: `dayu/host/api.py:3323`、`dayu/host/open_host.py:528`
- **输入场景**: 调用方传入 `HostStorageMaintenanceRequest(reclaim_orphan_artifacts=True)`，期望执行破坏性回收
- **实际分支**: 方法实际行为由 `request.reclaim_orphan_artifacts` 决定，True 时执行文件删除
- **预期行为**: docstring 应准确反映方法的完整行为空间（dry-run + opt-in destructive）
- **实际行为**: Protocol docstring 写 `"""执行 Host storage maintenance dry-run。"""`；async handle docstring 同样写 "dry-run"。但该方法在 `reclaim_orphan_artifacts=True` 时会执行破坏性文件删除。docstring 与实际行为不一致
- **直接证据**:
  - `api.py:3323`: `"""执行 Host storage maintenance dry-run。"""`
  - `open_host.py:528`: `"""执行 Host storage maintenance dry-run。"""`
  - 对比 `storage_maintenance.py:237-253`（facade 函数完整 docstring 正确描述了 dry-run + destructive 双模行为）
- **影响**: 调用方阅读 Protocol/async handle docstring 后可能误认为该方法永远是安全的只读操作，在传入 `reclaim_orphan_artifacts=True` 时没有意识到破坏性后果。但该影响有限，因为 `reclaim_orphan_artifacts` 默认值为 `False`，调用方必须显式 opt-in
- **建议改法和验证点**: 将两处 docstring 改为描述完整行为空间，例如 `"""执行 Host storage maintenance。默认 dry-run 不删除文件；reclaim_orphan_artifacts=True 时执行破坏性 orphan artifact 回收。"""`
- **修复风险（低）**: 纯文档修改，不影响行为
- **严重程度（低）**: 文档不一致，不导致逻辑错误；默认 dry-run 提供了安全网

### 002-未修复-低-`run_storage_maintenance` 泛化 OSError catch 消息无法区分实际失败操作

- **入口/函数**: `run_storage_maintenance`
- **文件(行号)**: `dayu/host/storage_maintenance.py:279-284`
- **输入场景**: maintenance 执行过程中，`scan_orphan_artifact_files`、`_physical_artifact_bytes`、`_run_wal_checkpoint_if_requested` 或 `_reclaim_orphan_artifacts_if_requested` 中任一步产生 `OSError`
- **实际分支**: 所有 OSError 被同一个 `except OSError` 捕获
- **预期行为**: 错误消息应能区分失败来源（file stat、file enumeration、checkpoint 等），帮助 operator 定位问题
- **实际行为**: 所有 OSError 统一映射为 `HostApiError(code=INTERNAL_ERROR, message="Storage maintenance file operation failed")`。若 checkpoint 相关的 OSError（极罕见但可能）触发此路径，消息 "file operation failed" 会产生误导
- **直接证据**: `storage_maintenance.py:279-284` — 单个 `except OSError` 覆盖整个 try 块内四个不同操作类别的 OSError
- **影响**: operator 排查 maintenance 失败时需要额外上下文（日志、trace）才能定位具体失败操作；当前 OSError 在实际 maintenance 路径中极少发生（文件系统错误通常会被更内层的 `HostArtifactWriteError` 包装），实际影响很低
- **建议改法和验证点**: 可考虑将 OSError catch 拆分为更细粒度的操作级错误包装，或在 `HostApiError` message 中包含来自 `__cause__` 的原始错误类型名。但当前严重程度不足以 block
- **修复风险（低）**: 错误消息变更，不影响行为语义
- **严重程度（低）**: 仅在极罕见的 OSError 场景下有轻微误导，不影响正确性

### 003-未修复-低-`_raise_if_closed` 在 sync facade 路径上仅由 `_transaction_runner()` 间接调用

- **入口/函数**: `report_storage_usage`、`run_storage_maintenance`（sync facade）
- **文件(行号)**: `dayu/host/storage_maintenance.py:223-230`、`233-299`
- **输入场景**: Host handle 已关闭后调用 sync facade
- **实际分支**: `host._run_read(...)` → `host._transaction_runner()` → `self._raise_if_closed()` → 抛出 `HostApiError(INVALID_STATE)`
- **预期行为**: handle 关闭后应 fail-fast 抛出 closed-handle 错误
- **实际行为**: 行为正确——`_raise_if_closed()` 通过 `_transaction_runner()` 间接调用，会抛出 `HostApiError(INVALID_STATE)`。但该路径依赖三级间接调用（facade → `_run_read` → `_transaction_runner` → `_raise_if_closed`），且 `run_storage_maintenance` 在 `_run_read` 之外还调用了 `host._db_path()` 和 `host._artifact_root()`（这两个 accessor 本身有显式 `_raise_if_closed()` 调用）。相比之下 async wrapper 在入口处有显式 `self._raise_if_closed()` 调用，sync facade 缺少同等级别的显式 close check
- **直接证据**:
  - `storage_maintenance.py:224`: `host._run_read(...)` 间接调用 close check
  - `storage_maintenance.py:255-256`: `host._db_path()` 和 `host._artifact_root()` 各有自己的 close check
  - `open_host.py:521,532`: async wrapper 有显式 `self._raise_if_closed()`
  - 对比 `command.py:476,514,609,...` : 其他 command facade 函数有显式 `host._raise_if_closed()` 调用
- **影响**: 当前行为正确（因为 `_db_path()` 在 `_run_read` 之前调用且自带 close check），但如果未来重构改变了调用顺序，可能引入 close-check gap。此外，错误消息是 `INVALID_STATE`（来自 `_raise_if_closed`）而非 `HostClosedError`，与 async wrapper 的错误语义不同。这是既有模式（其他 sync facade 如 `purge_session` 也通过 `_raise_if_closed` → `INVALID_STATE` 报错），不属于本次变更引入
- **建议改法和验证点**: 可在 sync facade 入口处添加显式 `host._raise_if_closed()` 调用以对齐其他 command facade 的模式，但这属于 defensive hardening，当前行为正确
- **修复风险（低）**: 添加显式 close check 不改变行为
- **严重程度（低）**: 行为正确，仅涉及 defensive consistency

## Open Questions

1. **Q1: `Host` Protocol `run_storage_maintenance` docstring 中的 "不支持的 destructive reclaim 请求失败" 语义**：`api.py:3328-3329` 写 `:raises HostApiError: maintenance 读取、扫描、checkpoint 或不支持的 destructive reclaim 请求失败时抛出。` 其中"不支持的 destructive reclaim 请求"在当前实现中没有对应语义——实现要么执行回收，要么不执行，不存在"不支持"的判断分支。该措辞是否表达了未来扩展意图（如某些 Host 实现不支持 reclaim），还是 docstring 编写时的用词偏差？

2. **Q2: `report_storage_usage` facade 没有显式 `_raise_if_closed()` 入口检查**：当前依赖 `host._run_read()` → `_transaction_runner()` → `_raise_if_closed()` 的三级间接链完成 close check。其他 command facade（如 `create_session`、`purge_session`）在调用 `host._run_write` 前都有显式 `host._raise_if_closed()` 调用。sync facade 是刻意省略（因为 `_run_read` 内部已有保护）还是应添加以对齐模式？不影响当前正确性，但影响代码模式一致性。

## Residual Risk

### R1: TOCTOU between recheck and unlink（已接受，mitigated）

- **状态**: accepted residual，已在 plan §11 R1 记录
- **缓解**: grace window（默认 3600s）+ 删除前 recheck + content-addressed artifact 可重写性 + containment guard
- **残余**: recheck 返回 False（确认 orphan）与 `unlink()` 之间的极短窗口内，另一个 write transaction 可能提交同一路径的新 descriptor。此时文件被删除但新 descriptor 引用悬空。概率极低（需要新 descriptor 写入的 artifact 恰好与旧 orphan 内容相同），且 content-addressed 可重写性意味着文件可按需重建
- **当前评估**: 不 blocking；plan 已显式记录此残余风险

### R2: `_assert_report_tables_cover_schema()` 仅在 `read_storage_usage` 调用时触发

- **状态**: accepted design choice
- **说明**: schema-report 表映射一致性检查（`_REPORT_TABLES == HOST_DURABLE_TABLES`）是运行时断言而非导入时断言。如果 schema 新增表但 report 映射未同步更新，错误只在首次 `report_storage_usage` 调用时暴露（抛出 `AssertionError`），不会在模块导入或系统启动时发现
- **影响**: 低——`_REPORT_TABLES` 和 `_HOST_DURABLE_TABLE_TO_REPORT_FIELD` 在同一模块内定义，通过 slice-level review 和 pyright 保证同步；新增表时测试会因 row count 变化而失败

### R3: 多进程 artifact root 并发写入时 `iter_published_artifact_relative_paths` 可能看到部分写入的文件

- **状态**: accepted design choice（content-addressed artifact 保证原子 rename + fsync 目录）
- **说明**: `write_artifact_bytes` 使用 `tempfile.mkstemp` + `os.replace`（原子 rename）+ `_fsync_directory`，保证已发布的文件总是完整写入的。但 `iter_published_artifact_relative_paths` 枚举目录时不加锁——如果另一个进程正在 `os.replace` 中途，枚举可能看到瞬态。这不影响 orphan 判定（瞬态文件要么被 descriptor 引用，要么在 grace window 后被回收），但物理 `st_size` 统计可能包含不完整的瞬态文件
- **影响**: 极低——`os.replace` 在同一文件系统上是原子的；目录 fsync 保证元数据已持久化

### R4: 测试未覆盖 `_ensure_contained` 在 root 路径本身为 symlink 的极端场景

- **状态**: 已知 gap
- **说明**: 测试覆盖了 `sha256/` namespace 内文件的 symlink 逃逸（`test_iter_published_artifact_relative_paths_rejects_symlink_escape`、`test_delete_artifact_file_rejects_traversal_and_symlink_escape`），但未覆盖 artifact root 本身是 symlink 的场景。当前 `_ensure_contained` 会对 root 执行 `resolve(strict=True)`，能正确处理 root symlink，但缺少显式测试
- **影响**: 低——containment 逻辑本身正确，仅缺少边界测试

### R5: 测试未覆盖 `scan_orphan_artifact_files` 在 `grace_seconds=0` 边界的行为

- **状态**: 已知 gap
- **说明**: 测试用例使用默认 grace（3600s）和手动设置的旧 mtime。未测试 `grace_seconds=0`（立即将所有无引用文件视为候选）的边界行为。`grace_seconds >= 0` 的校验在 `scan_orphan_artifact_files:445`，`grace_seconds=0` 时 `cutoff_timestamp = now`，所有 mtime 不晚于 now 的文件（即所有文件）进入候选——行为正确，但缺少测试覆盖
- **影响**: 低——逻辑正确，仅缺少边界测试

## Conclusion

**结论: PASS**

- **Blocking findings**: 0
- **Non-blocking findings**: 3（001 文档不一致、002 错误消息笼统、003 defensive consistency，均为低严重度）
- **Open questions**: 2（均为非 blocking，实现期可自决）
- **Residual risks**: 5（R1 TOCTOU 已接受并缓解、R2 运行时断言、R3 多进程并发、R4 root symlink 测试 gap、R5 grace=0 边界测试 gap）

### 核心判断

经过对 WU-RET-00 全量变更（plan + 4 slices）沿真实代码路径的逐行走读和 adversarial failure pass：

1. **Artifact 删除安全** — **通过**。`delete_artifact_file` 实现了严格的 containment 守卫链条：文本校验 → `sha256/` namespace 校验 → 平台路径转换 → `lexists` 检查 → `resolve(strict=True)` 双端 containment → `unlink(missing_ok=True)`。symlink 逃逸攻击在所有已验证路径上被正确拒绝。测试覆盖了越界路径、非 `sha256/` namespace、symlink 逃逸场景。

2. **Orphan proof 直接证据** — **通过**。`artifact_relative_path_is_referenced` 和 `collect_referenced_artifact_paths` 的引用证明完全基于 `payload_descriptors` 表（`payload_kind='artifact_ref'` AND `artifact_relative_path` 匹配），不依赖 purge 的 `cleanup_refs`、EventLog payload JSON 解析或间接标志。这是唯一正确的 artifact 删除证明真源。测试覆盖了共享引用（两个 descriptor 指向同一 content-addressed 文件）和 projection lag（descriptor 仍被 EventLog 引用）场景。

3. **Dry-run 与 destructive reclaim 的 opt-in 边界** — **通过**。`reclaim_orphan_artifacts` 默认 `False`；只有显式设置 `True` 时才会执行文件删除。删除前每个候选独立执行 recheck（通过 `_ArtifactPathReferenceChecker` 在新读事务中调用 `artifact_relative_path_is_referenced`）。单文件删除失败不中断其他候选处理，失败信息以结构化 `HostStorageMaintenanceFileError` 返回。测试覆盖了 dry-run 不变性、opt-in 删除、共享引用保留、recheck 命中跳过、单文件错误诊断和幂等。

4. **DB/WAL report/checkpoint 行为** — **通过**。WAL checkpoint 使用独立 connection（`host._open_durable_connection()` → `run_host_wal_checkpoint`），在 `finally` 中保证关闭。DB/WAL size 通过 `Path.stat()` 读取，缺失文件返回 0。测试覆盖了 checkpoint on/off、独立 connection 使用。

5. **Public facade error mapping** — **通过**。`HostDurableError`（含 `HostArtifactWriteError`）→ `HostApiError(INTERNAL_ERROR)`；`OSError` → `HostApiError(INTERNAL_ERROR)`；handle closed → `HostApiError(INVALID_STATE)`（sync）或 `HostClosedError`（async）。错误映射链路完整，exception chaining（`from exc`）保留了原始错误上下文。测试覆盖了 DB/WAL stat OSError → `HostApiError` 和 closed handle → `HostClosedError`。

6. **Host 分层边界** — **通过**。所有新增代码位于 `dayu/host/` 层内。`storage_lifecycle.py`（durable 子层）只依赖 `dayu.host.durable.*` 和标准库。`storage_maintenance.py`（facade）依赖 `dayu/host/command.py`、`dayu/host/api.py` 和 durable 子层。`api.py` 的 Protocol 扩展使用 `TYPE_CHECKING` 进行前向引用。无反向依赖、无跨层穿透。

7. **AGENTS.md 约束遵守** — **通过**。所有函数有完整中文 docstring；无 `Any`/`object`/无类型签名；`frozen=True, slots=True` dataclass；无魔法数字（grace 常量具名 `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS`）；无兼容性代码；显式参数传入（`now: datetime`、`grace_seconds: float` 不进 extra payload）；职责分离（durable 原语 vs facade 编排 vs async wrapper）。pyright 在变更文件上零错误。

8. **测试覆盖真实性** — **通过**。四个测试文件共覆盖：artifact 枚举/删除/namespace 安全/symlink 拒绝、report 空库/有数据/orphan 诊断/DB-WAL stat/OSError 映射/async handle/closed handle/`json_value()` 键集合、删除证明（共享引用/projection lag/namespace 安全/grace 过滤/排序）、maintenance（dry-run 不变性/opt-in 删除/共享引用保留/recheck 跳过/单文件错误诊断/幂等/async handle/closed handle/WAL checkpoint 双模式）。测试不依赖 mock（除 `monkeypatch` 用于注入 OSError 和单文件删除失败），直接验证真实行为。
