# WU-TOOLS-01-F01-01 Fins filelock convergence plan

## 1. Goal / motivation / success signal

Goal：

- 将 Fins ingestion job store 的私有 `_StoreFileLock` 收敛为直接使用 `dayu.runtime.filelock`。
- 将 Fins storage batch 当前通过 `dayu.fins._file_lock` 持有的 ticker lock 与 recovery lock 收敛为直接使用 `dayu.runtime.filelock`。
- 收敛后若无生产引用，删除 `dayu.fins._file_lock` 与 `FsFinsIngestionJobStore` 同文件内的 `_StoreFileLock`。

Motivation 判断：

- 动机成立，且不是过度修复。设计真源要求 `dayu.runtime` 承载层中立、可复用运行期基础能力，业务层需要公共运行时能力时应优先复用或扩展 `dayu.runtime`，不得自行实现语义不一致的 runtime helper（`docs/host/design.md:63-65`）。
- 设计真源已经把 `dayu.runtime.filelock` 定义为普通文件多进程互斥统一封装（`docs/host/design.md:70`、`docs/host/design.md:245-266`），而 Fins 当前仍有两套私有锁实现：ingestion job store 内联 `_StoreFileLock`（`dayu/fins/ingestion_runtime.py:704`、`dayu/fins/ingestion_runtime.py:1945`）与 storage batch 的 `dayu.fins._file_lock`（`dayu/fins/storage/_fs_storage_infra.py:16`、`dayu/fins/_file_lock.py:94`、`dayu/fins/_file_lock.py:139`）。这是同类普通文件互斥能力重复实现。
- 控制真源明确本 work unit 的目标和进入前评估要求（`docs/host/issues-implementation-control.md:218`）。

Success signal：

- `dayu/fins/ingestion_runtime.py` 不再 import `fcntl`，不再定义或引用 `_StoreFileLock`；所有 job record 临界区直接通过 `dayu.runtime.filelock.file_lock(...).acquire()` / context manager 保护。
- `dayu/fins/storage/_fs_storage_infra.py` 不再 import `dayu.fins._file_lock`，ticker lock 与 recovery lock 直接持有 `RuntimeFileLockToken`。
- `dayu/fins/_file_lock.py` 在无生产引用后删除，测试不再导入或断言该私有 helper。
- job store 的 atomic replace / temp cleanup、跨进程互斥、storage batch 同 ticker fail-fast 冲突语义保持不变。
- `tests/runtime/test_import_boundary.py` 中第三方 `filelock` 只能出现在 `dayu.runtime.filelock` 的约束继续通过（`tests/runtime/test_import_boundary.py:159-172`）。
- Code-generation-ready：yes。Implementation agent 可按 Slice 1 -> Slice 2 -> Slice 3 顺序直接执行；若遇到 stop condition，必须停在对应 slice 并回报。

## 2. Non-goals / scope boundary

Non-goals：

- 不修改 Fins job schema、job id、record JSON 字段、状态机、状态枚举或落盘路径。
- 不修改 `dayu.fins.storage` 仓储协议；`BatchToken` 仍保持当前公开字段，不塞入 runtime token（`dayu/fins/domain/document_models.py:120-144`）。
- 不修改 atomic replace / json store 数据落盘语义。
- 不修改 Host / Engine / ToolRuntime contract。
- 不引入 async filelock、Host 专用 durable lock、lease、fencing、stale takeover、break lock 或 recovery ownership 语义。
- 不增加仅透传 `dayu.runtime.filelock` 的 Fins wrapper / facade。
- 不把显式参数放进 extra payload；本 work unit 不涉及 provider、Host request 或 tool schema payload。

Scope boundary：

- 允许的生产改动应只覆盖 Fins 当前两处私有文件锁使用点与删除死代码。
- Runtime filelock 公共契约只有在直接证据证明能力不足时才扩展；若扩展，必须先进入 runtime 公共契约 slice，而不是在 Fins 中造 wrapper。
- 财报文档存取仍只能通过 `dayu.fins.storage` 仓储协议与仓储实现完成；本 work unit 只替换仓储实现内部锁 primitive，不绕过仓储写业务文件。

## 3. Design document alignment

Host design alignment：

- `dayu.runtime` 是层中立运行期基础设施，不属于 UI / Service / Host / Engine 任一业务层，不得承载财报语义或 Host durable truth（`docs/host/design.md:63`）。
- `dayu.runtime` 不得 import `dayu.fins`，各层需要公共运行时能力时应优先复用或扩展 `dayu.runtime`（`docs/host/design.md:65`）。
- `dayu.runtime.filelock` 用于普通文件访问互斥，不能表达 Host durable truth、EventLog ordering、Run / Attempt owner，也不能兜底数据库事务（`docs/host/design.md:70`）。
- `RuntimeFileLock` public API 是同步 `acquire()`、context manager 和 `RuntimeFileLockToken.release()`（`docs/host/design.md:247-266`）。
- `timeout_seconds=0` 是 non-blocking acquire，第三方 timeout 必须包装为 runtime timeout error（`docs/host/design.md:280-284`）。
- filelock 第一版不实现 stale takeover、break lock、lease、fencing 或 recovery 判断（`docs/host/design.md:286-293`）。
- 只有 `dayu.runtime.filelock` 可以直接 import 第三方 `filelock`（`docs/host/design.md:295-297`）。

Engine alignment：

- Engine 不理解财报业务语义，也不直接访问财报文档存储（`docs/engine/design.md:18-26`）。
- 本 work unit 不改变 Engine tool-calling contract、`ToolExecutor` handshake、EngineEvent stream 或 Runner 行为。Fins storage batch 与 ingestion job store 均在 Engine 外部执行环境内。
- 因此无需修改 `docs/engine/design.md`、Engine 代码或 Engine tests；只需在验证中保留 runtime import boundary，防止 runtime 反向依赖 Fins。

## 4. First-principles judgment and direct code evidence

First-principles judgment：

- 两处 Fins 锁保护的是普通文件系统临界区：job store 的单目录 JSON record 读写，以及 storage batch 的 per-ticker / recovery 文件系统事务。它们不表达 Host truth、业务事实、lease、owner takeover 或 recovery proof。
- 公共 runtime filelock 已覆盖普通文件互斥、parent directory 创建、阻塞 / 非阻塞 acquire、异常包装和 token release 生命周期；保留 Fins 私有锁会制造重复 runtime helper，削弱 import 边界和测试真源。
- storage batch 的“同 ticker fail-fast”是 Fins storage 业务错误语义，不是 runtime 公共契约语义；应在 Fins 调用点把 `RuntimeFileLockTimeoutError` 映射为现有用户可读 `RuntimeError`，而不是让 runtime filelock 学会 ticker。

Direct code evidence：

- Work unit 控制条目要求收敛 Fins ingestion job store 与 storage batch 私有 filelock 到 `dayu.runtime.filelock`，并保持 job store blocking lock、storage batch non-blocking conflict、异常映射和跨进程互斥要求（`docs/host/issues-implementation-control.md:218`）。
- `FsFinsIngestionJobStore` 在 `create_job`、`save_job`、`save_succeeded_or_cancelled`、`claim_running_or_cancelled`、`read_job`、`request_cancel` 中用 `_StoreFileLock(self.root_dir / _LOCK_FILE_NAME)` 包裹读写临界区（`dayu/fins/ingestion_runtime.py:704-708`、`dayu/fins/ingestion_runtime.py:726-730`、`dayu/fins/ingestion_runtime.py:756-780`、`dayu/fins/ingestion_runtime.py:805-826`、`dayu/fins/ingestion_runtime.py:843-844`、`dayu/fins/ingestion_runtime.py:862-873`）。
- `_StoreFileLock` 定义在 `dayu/fins/ingestion_runtime.py:1945`，直接使用 POSIX `fcntl.flock(..., LOCK_EX)` 与 `LOCK_UN`（`dayu/fins/ingestion_runtime.py:1980`、`dayu/fins/ingestion_runtime.py:2010`）。
- `_write_record_locked` 使用临时文件、`os.replace` 与异常清理保证 atomic replace 语义，本 work unit 不应改动该路径（`dayu/fins/ingestion_runtime.py:913-944`）。
- Storage infra 当前 import `dayu.fins._file_lock`（`dayu/fins/storage/_fs_storage_infra.py:16`），`_open_and_lock_stream` 打开 lock 文件、调用 `acquire_text_file_lock`，非阻塞竞争时映射为 `RuntimeError(f"ticker={lock_path.stem} 已存在跨进程活动 batch")`（`dayu/fins/storage/_fs_storage_infra.py:425-453`）。
- Storage ticker lock 在 `begin_batch` 获取，失败清理路径和 commit / rollback finally 路径释放（`dayu/fins/storage/_fs_storage_infra.py:167-199`、`dayu/fins/storage/_fs_storage_infra.py:254-258`、`dayu/fins/storage/_fs_storage_infra.py:287-291`）。
- Recovery 使用全局 recovery lock 包裹 orphan batch scan（`dayu/fins/storage/_fs_storage_infra.py:353-375`），并在恢复单个 ticker 时尝试获取 per-ticker non-blocking lock，竞争时返回 `None` 跳过（`dayu/fins/storage/_fs_storage_infra.py:620-648`、`dayu/fins/storage/_fs_storage_infra.py:678-693`、`dayu/fins/storage/_fs_storage_infra.py:721-737`）。
- `dayu.fins._file_lock` 目前提供 POSIX `fcntl` 与 Windows `msvcrt` 两套文本流锁 helper（`dayu/fins/_file_lock.py:39-48`、`dayu/fins/_file_lock.py:94-136`、`dayu/fins/_file_lock.py:139-169`）。
- Tests 当前直接导入 `_StoreFileLock` 并 monkeypatch `ingestion_runtime.fcntl.flock` 验证锁失败关闭 stream（`tests/fins/test_fins_ingestion_runtime.py:27-41`、`tests/fins/test_fins_ingestion_runtime.py:1166-1200`）；该测试应迁移为 runtime filelock 或 Fins 行为测试，而不是保留私有类。
- `tests/runtime/test_filelock.py` 已覆盖 parent dir、context manager release、异常路径 release、幂等 release、non-blocking timeout 包装和公共 API non-goals（`tests/runtime/test_filelock.py:87-107`、`tests/runtime/test_filelock.py:110-163`、`tests/runtime/test_filelock.py:200-269`、`tests/runtime/test_filelock.py:272-294`）。
- `tests/runtime/test_import_boundary.py` 已覆盖 runtime 不反向依赖业务层与第三方 `filelock` 只在 runtime wrapper 中直接 import（`tests/runtime/test_import_boundary.py:77-87`、`tests/runtime/test_import_boundary.py:159-172`）。

## 5. `dayu.runtime.filelock` capability assessment

Blocking lock：

- 满足。`timeout_seconds=None` 时 wrapper 传入第三方默认无限等待语义（`dayu/runtime/filelock.py:148-170`、`dayu/runtime/filelock.py:243-260`），可替代 `_StoreFileLock` 的阻塞 `LOCK_EX`。

Parent dir creation：

- 满足。`RuntimeFileLock.acquire()` 在 acquire 前调用 `_prepare_parent_directory`，默认创建 parent directory（`dayu/runtime/filelock.py:167`、`dayu/runtime/filelock.py:263-284`）。job store 和 batch lock parent 的当前 mkdir 语义可保持或简化。

Exception propagation：

- 满足，但需要调用点映射。runtime 将第三方 timeout 包装为 `RuntimeFileLockTimeoutError`，其它 acquire / release 问题包装为 `RuntimeFileLockError`（`dayu/runtime/filelock.py:169-174`、`dayu/runtime/filelock.py:101-105`）。Fins job store 可让该 runtime error 作为 runtime failure 透出；storage batch 的 non-blocking conflict 必须捕获 timeout 并映射为现有 `RuntimeError`。

Lifecycle：

- 满足。runtime context manager 在正常与异常退出时 release（`dayu/runtime/filelock.py:182-215`），manual token release 幂等（`dayu/runtime/filelock.py:91-105`）。Storage batch 不能只创建临时 context manager，因为 lock 要跨 `begin_batch` 到 `commit_batch` / `rollback_batch` 持有；必须保存 `RuntimeFileLockToken` 私有映射。

Non-blocking timeout：

- 满足。`timeout_seconds=0` 表示 non-blocking acquire（`docs/host/design.md:280-284`），测试已断言 timeout 包装（`tests/runtime/test_filelock.py:259-269`）。

Storage batch conflict mapping：

- 满足但属于 Fins 调用点责任。`_acquire_ticker_lock` 应调用 `file_lock(self._ticker_lock_path(ticker)).acquire(timeout_seconds=0)`；捕获 `RuntimeFileLockTimeoutError` 后抛出与现有一致的 `RuntimeError(f"ticker={ticker} 已存在跨进程活动 batch")`。`_try_acquire_recovery_ticker_lock` 继续捕获该 `RuntimeError` 并返回 `None`。

Cross-process behavior：

- 满足当前 work unit 要求。设计真源定义 runtime filelock 用于多进程普通文件访问互斥（`docs/host/design.md:70`、`docs/host/design.md:245`），实现统一封装第三方 `filelock.FileLock`（`dayu/runtime/filelock.py:16`、`dayu/runtime/filelock.py:143-145`）。本 work unit 不需要比现有 runtime 公共契约更强的跨进程 owner / stale recovery 语义。

macOS / Linux portability：

- 满足当前目标，且优于 ingestion job store 的 POSIX-only `_StoreFileLock`。`_StoreFileLock` 直接 import `fcntl`（`dayu/fins/ingestion_runtime.py:25`）并使用 `fcntl.flock`（`dayu/fins/ingestion_runtime.py:1980`、`dayu/fins/ingestion_runtime.py:2010`）。runtime 统一依赖第三方 `filelock`，避免 Fins 中散落平台分支或 POSIX-only 实现。

是否需要扩展 runtime filelock：

- 当前证据下不需要。blocking acquire、non-blocking acquire、parent dir creation、context manager、manual token lifecycle 与异常包装均已满足 Fins 当前需求。
- 若 implementation 发现 `filelock.FileLock` 在当前版本无法稳定提供同一 lock path 的多进程互斥，或 release 后 marker 行为破坏 Fins lock 文件假设，应停止当前 Fins 实现，先作为 runtime 公共契约问题扩展 `dayu.runtime.filelock` 与 `tests/runtime/test_filelock.py`，不得在 Fins 中新增 wrapper。

## 6. Affected files/modules

Production files expected in implementation gate：

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/_file_lock.py`（删除，前提是无生产引用）

Tests expected in implementation gate：

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_storage_provider.py` 或新增/调整同目录 storage batch 相关测试
- `tests/runtime/test_filelock.py`（仅当发现 runtime 公共契约需要补充测试时）
- `tests/runtime/test_import_boundary.py`（通常无需修改，但必须运行）

README check expected in implementation gate：

- `dayu/fins/README.md`
- `tests/README.md`

No expected changes：

- `docs/engine/design.md`
- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- Host / Engine / ToolRuntime production code
- `dayu.fins.storage.repository_protocols`
- `dayu/fins/domain/document_models.py`

## 7. Contract / schema / state-machine / public-interface changes

- Contract changes：无。
- Schema changes：无。
- Durable state changes：无。
- State-machine changes：无。
- Public interface changes：无。
- Tool schema / LLM-facing text changes：无。
- Storage repository protocol changes：无。
- BatchToken public shape changes：无。`BatchToken.ticker_lock_path` 继续作为可诊断路径字段；runtime token 只存在于 `_FsStorageInfra` 私有状态。

## 8. Implementation decisions

Ingestion job store：

- 在 `dayu/fins/ingestion_runtime.py` 中删除 `import fcntl`。
- 从 `dayu.runtime.filelock` import `file_lock`，如需类型注解再 import `RuntimeFileLockToken` / `RuntimeFileLockError`，不得 import 第三方 `filelock`。
- 将所有 `with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):` 改为 `with file_lock(self.root_dir / _LOCK_FILE_NAME):`。默认 blocking acquire 保持现有 `_StoreFileLock` 阻塞语义。
- 删除 `_StoreFileLock` 类。不要新增 `_fins_store_file_lock()` 这类仅透传 helper。
- `_write_record_locked`、`_read_record_locked`、job schema 与 atomic replace 不改。

Storage batch：

- 在 `dayu/fins/storage/_fs_storage_infra.py` 中替换 `from dayu.fins import _file_lock as file_lock_module` 为 `from dayu.runtime.filelock import RuntimeFileLockTimeoutError, RuntimeFileLockToken, file_lock`。
- 将 `_ticker_lock_streams: dict[str, TextIO]` 改为 `_ticker_lock_tokens: dict[str, RuntimeFileLockToken]`。不要把 token 放进 `BatchToken`，避免修改仓储协议。
- 将 `_open_and_lock_stream(lock_path, blocking=...) -> TextIO` 改为私有 `_acquire_lock_token(lock_path, *, blocking: bool) -> RuntimeFileLockToken`，或等价命名；该 helper 必须：
  - 对 `blocking=True` 调用 `file_lock(lock_path).acquire()` 或 `file_lock(lock_path, timeout_seconds=None).acquire()`。
  - 对 `blocking=False` 调用 `file_lock(lock_path).acquire(timeout_seconds=0)`。
  - 捕获 `RuntimeFileLockTimeoutError`；若 `blocking=False`，抛出 `RuntimeError(f"ticker={lock_path.stem} 已存在跨进程活动 batch")`；若 `blocking=True` 理论上不应 timeout，仍透传 runtime error。
  - 不打开 `TextIO`，不手工 close stream，不调用 Fins 私有锁模块。
- 将 `_release_lock_stream(stream)` 改为 `_release_lock_token(token)`，调用 `token.release()`。
- `_acquire_ticker_lock(ticker)` 返回 `RuntimeFileLockToken`，保存到 `_ticker_lock_tokens[ticker]`。
- `_release_ticker_lock` 的参数 `stream` 必须改为 `token: RuntimeFileLockToken | None = None`；实现签名为 `_release_ticker_lock(ticker, *, token: RuntimeFileLockToken | None = None)` 或等价的严格类型签名。
- `_release_ticker_lock` 必须无条件先执行 `_ticker_lock_tokens.pop(ticker, None)` 或同等 dict 清理；即使调用方显式传入 `token`，也必须移除对应 ticker 条目，避免继承当前显式 stream release 不 pop dict 的 stale-reference edge case。随后 release 显式 token 或 pop 得到的 token，存在则 release。
- `_acquire_recovery_lock()` 返回 `RuntimeFileLockToken`，`recover_orphan_batches()` 的 `finally` 调用 `_release_lock_token(recovery_token)`。
- `_try_acquire_recovery_ticker_lock(ticker)` 返回 `RuntimeFileLockToken | None`，保持捕获 `RuntimeError` 后返回 `None` 的 skip live batch 语义。
- 所有变量名从 `stream` / `ticker_stream` / `lock_stream` 改为 `token` / `ticker_token` / `recovery_token`，避免误导。
- 内部 docstring 的 Returns / Raises 同步到 `RuntimeFileLockToken`、`RuntimeFileLockError` / `RuntimeError`。不改公共仓储协议 docstring，除非它直接描述底层 stream。

Deletion：

- 运行 `rg -n "dayu\\.fins\\._file_lock|from dayu\\.fins import _file_lock|_file_lock|_StoreFileLock|fcntl" dayu tests -g '*.py'`，确认生产引用清空。
- 删除 `dayu/fins/_file_lock.py`。
- 迁移或删除测试对 `_StoreFileLock`、`ingestion_runtime.fcntl` 的直接依赖；不得为测试保留兼容 export。

## 9. Small implementation slices

### Slice 1：Ingestion job store convergence

Objective：

- 用 `dayu.runtime.filelock` 替换 `FsFinsIngestionJobStore` 的 `_StoreFileLock`，删除同文件私有 POSIX lock。

Allowed files：

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/runtime/test_filelock.py`（仅当发现 runtime filelock 测试缺口）
- `dayu/fins/README.md`、`tests/README.md`（只按 README decision 判断后修改）

Exact allowed changes：

- 删除 `import fcntl`。
- 添加 `from dayu.runtime.filelock import file_lock`。
- 替换 6 个 `_StoreFileLock` context manager 使用点。
- 删除 `_StoreFileLock` 类。
- 删除或迁移 `tests/fins/test_fins_ingestion_runtime.py` 中 `_StoreFileLock` import 与 `test_store_file_lock_closes_stream_when_flock_fails`。
- 删除旧 `test_store_file_lock_closes_stream_when_flock_fails` 不是覆盖缺口：替换后 Fins 不再打开锁文件 `TextIO` / stream，文件描述符生命周期由 `dayu.runtime.filelock` 与第三方 `filelock` 内部管理；implementation report 必须明确确认这一点。

Functions / classes / data flow：

- `FsFinsIngestionJobStore.create_job`、`save_job`、`save_succeeded_or_cancelled`、`claim_running_or_cancelled`、`read_job`、`request_cancel`：只替换锁 primitive，不改变读写顺序。
- `_read_record_locked`、`_write_record_locked`：保持不变。

Error handling：

- Blocking acquire 失败抛 `RuntimeFileLockError`，作为 runtime 文件锁错误透出；不包装成 Fins-specific error。
- Atomic replace 失败仍按现有 `OSError` 路径清理临时文件。

Invariants：

- 同一 job store root 下的 record 读改写仍在同一 `.store.lock` 临界区内。
- `.store.lock` 路径不变。
- job JSON schema 和状态转移不变。

Tests：

- 保留现有 job store atomic write failure cleanup 测试（`tests/fins/test_fins_ingestion_runtime.py:1140-1163`）。
- 将旧 `_StoreFileLock` stream close 测试删除或迁移为 runtime filelock 已覆盖的 acquire failure / context release 测试；不能继续导入私有类。
- 若需要证明 job store 使用 runtime lock，可添加 focused monkeypatch：替换 `ingestion_runtime.file_lock` 为记录 lock path 的 fake context manager，并断言 `create_job` / `request_cancel` 使用 `<root>/.store.lock`；fake 必须有严格类型签名，不能用 `Any`。

Completion signal：

- `rg -n "_StoreFileLock|import fcntl|ingestion_runtime\\.fcntl" dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` 无命中。
- Ingestion runtime 相关 tests 通过。

Stop condition：

- 如果 `RuntimeFileLock` blocking acquire 不能替代 `_StoreFileLock` 的跨进程互斥，停止并提出 runtime 公共契约扩展，不在 Fins 中新增 wrapper。

### Slice 2：Storage batch lock convergence

Objective：

- 用 `RuntimeFileLockToken` 替换 storage batch 裸 `TextIO` lock stream 与 `dayu.fins._file_lock`。

Allowed files：

- `dayu/fins/storage/_fs_storage_infra.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_ingestion_runtime.py`（若该文件已有 batch fixture 需要同步）
- `tests/runtime/test_filelock.py`（仅当 runtime contract 测试缺口）
- `dayu/fins/README.md`、`tests/README.md`（只按 README decision 判断后修改）

Exact allowed changes：

- 替换 `_ticker_lock_streams` 私有 dict 为 `_ticker_lock_tokens`。
- 替换 `_open_and_lock_stream` / `_release_lock_stream` 为 token acquire / release helper，或在原函数名下改返回类型与语义，但变量名和 docstring 必须避免继续称 stream。
- 更新 `_acquire_ticker_lock`、`_release_ticker_lock`、`_acquire_recovery_lock`、`recover_orphan_batches`、`_recover_single_batch_dir`、`_recover_orphan_backup_dirs`、`_try_acquire_recovery_ticker_lock` 的局部变量和返回类型。
- `_release_ticker_lock` 的显式参数必须从 `stream` 改为 `token: RuntimeFileLockToken | None = None`；函数内部必须 pop `_ticker_lock_tokens` 中的 ticker 条目或等价清理，即使显式传入 token 也不能留下 stale token reference。
- 删除 `dayu.fins._file_lock` import。

Functions / classes / data flow：

- `begin_batch`：同实例 `_active_batches` fail-fast 保持在获取跨进程锁之前；跨进程 ticker lock 获取成功后写 journal，异常时 release token。
- `commit_batch` / `rollback_batch`：finally 继续 release per-ticker token。
- `recover_orphan_batches`：blocking recovery lock 持有整个 recovery scan，finally release。
- `_try_acquire_recovery_ticker_lock`：per-ticker non-blocking conflict 仍返回 `None`，使 recovery 跳过 live batch。

Error handling：

- `_acquire_ticker_lock` 捕获 `RuntimeFileLockTimeoutError` 后映射为现有 `RuntimeError(f"ticker={ticker} 已存在跨进程活动 batch")`。
- `RuntimeFileLockError` 代表锁文件路径、parent dir、acquire / release 等 runtime lock failure，按现有 OSError 类似运行时失败透出；不要吞掉后进入临界区。
- release failure 透出为 runtime lock error；commit / rollback finally 的行为与现有 release OSError 失败风险等价。

Invariants：

- 同 ticker 只能有一个跨进程活动 batch。
- 不同 ticker 仍可并发 batch。
- Recovery 不抢占 live ticker batch；遇到 ticker lock 竞争时跳过该 orphan token / backup。
- Batch journal、backup、staging、atomic directory swap 语义不变。
- `BatchToken` 不携带 runtime token，仓储协议不变。

Tests：

- 增加或调整 storage batch conflict 测试：同一 workspace 两个独立 repository/core 尝试同 ticker `begin_batch("AAPL")`，第二个必须 fail-fast 抛 `RuntimeError`，消息包含 `ticker=AAPL 已存在跨进程活动 batch`；第一个 rollback 后第二个可成功 acquire。
- 保留现有 batch commit / rollback fixture 行为（例如 `tests/fins/test_fins_ingestion_runtime.py:1284-1312`、`tests/fins/test_fins_ingestion_runtime.py:1363-1429`、`tests/fins/test_fins_storage_provider.py:404-471`）。
- 如已有 recovery tests，更新为 token 变量语义；如无，则至少覆盖 `_try_acquire_recovery_ticker_lock` skip live batch 的行为，可通过 public `recover_orphan_batches(dry_run=True)` 路径构造 live batch + orphan dir。

Completion signal：

- `rg -n "_file_lock|file_lock_module|_ticker_lock_streams|_release_lock_stream|_open_and_lock_stream" dayu/fins/storage/_fs_storage_infra.py` 无旧 stream/helper 命中，除非函数名被有意保留且语义已改为 token；更推荐无命中。
- Storage / Fins affected tests 通过。

Stop condition：

- 如果 runtime filelock 的 non-blocking timeout 不能稳定映射为当前 fail-fast conflict，停止并提出 runtime 公共契约扩展，不在 Fins 中保留 `_file_lock` facade。

### Slice 3：Delete dead Fins private lock and boundary cleanup

Objective：

- 删除 `dayu/fins/_file_lock.py`，清理所有生产与测试引用，确认 import boundary。

Allowed files：

- `dayu/fins/_file_lock.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/runtime/test_import_boundary.py`（通常只运行不改）
- README files only if decision says needed

Exact allowed changes：

- 删除 `dayu/fins/_file_lock.py`。
- 删除测试中对 `_StoreFileLock`、`ingestion_runtime.fcntl`、`dayu.fins._file_lock` 的引用。
- 不增加 `dayu/fins/filelock.py`、`dayu/fins/_runtime_filelock.py` 或 package-level re-export。

Functions / classes / data flow：

- 无新增 production data flow。

Error handling：

- 无新增错误路径；只验证旧错误路径已由 Slice 1 / Slice 2 测试覆盖。

Invariants：

- `dayu.runtime` 不 import Fins。
- Fins 不直接 import 第三方 `filelock`。
- 生产代码中没有重复 filelock helper。

Tests：

- `tests/runtime/test_import_boundary.py`
- `rg` 引用清理检查。

Completion signal：

- `rg -n "dayu\\.fins\\._file_lock|from dayu\\.fins import _file_lock|_file_lock|_StoreFileLock|import fcntl|from filelock import|import filelock" dayu tests -g '*.py'` 只允许 `dayu/runtime/filelock.py` 与 runtime tests 中直接第三方 filelock 测试引用；Fins 生产代码无命中。

Stop condition：

- 如果仍存在生产引用，不能删除 `dayu/fins/_file_lock.py`；必须先回到对应 slice 清理引用，而不是保留兼容 re-export。

## 10. Tests / validation commands and expected assertions

Plan gate validation：

```bash
git diff --check docs/host/wu-tools-01-f01-01-filelock-plan.md
```

Expected：

- 无 whitespace error。

Implementation gate required validation：

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q
pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
pyright
git diff --check
```

Expected assertions：

- Fins ingestion runtime tests pass，特别是 job store atomic write failure cleanup、cancel transition、cross-runtime shared job store 等现有行为不变。
- Storage provider / batch tests pass，特别是同 ticker active batch fail-fast、commit / rollback、fixture workspace 写入不变。
- Runtime filelock tests pass，确认 blocking / non-blocking / release lifecycle 公共契约未退化。
- Runtime import boundary tests pass，确认 runtime 没有反向依赖 Fins，第三方 `filelock` direct import 仍只在 `dayu.runtime.filelock`。
- Pyright 0 errors；不得新增、扩散、掩盖类型错误。
- `git diff --check` 无 whitespace error。

Recommended focused coverage commands if production files are modified：

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.ingestion_runtime --cov-report=term-missing -q
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.storage._fs_storage_infra --cov-report=term-missing -q
pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing -q
```

Expected：

- Modified production files should remain at or above the repository single-file coverage target where practical. If `_fs_storage_infra` coverage cannot reach 80% because it is broad shared infra, implementation report must classify that as test coverage residual risk with owner/destination; it must not lower or bypass coverage settings.

Reference cleanup commands：

```bash
rg -n "dayu\\.fins\\._file_lock|from dayu\\.fins import _file_lock|_file_lock|_StoreFileLock|ingestion_runtime\\.fcntl|import fcntl" dayu tests -g '*.py'
rg -n "from filelock import|import filelock" dayu -g '*.py'
```

Expected：

- First command has no Fins private lock production references; test references only if intentionally testing absence, otherwise none.
- Second command only reports `dayu/runtime/filelock.py`; runtime tests may import third-party `filelock` for wrapper tests outside this `dayu` production scan.

## 11. Docs decision

`dayu/fins/README.md`：

- Triggered for check because implementation will modify `dayu/fins/`.
- Current README already says Fins must use `dayu.fins.storage` for financial document access（`dayu/fins/README.md:35`）, read/download/preprocess share runtime and workspace job store（`dayu/fins/README.md:36`）, Fins ingestion job is Fins durable record（`dayu/fins/README.md:38`）, and `dayu.runtime` provides filelock without importing Fins（`dayu/fins/README.md:65`）。
- Decision：likely no update if implementation only replaces private lock primitive and public Fins capabilities remain unchanged. Update only if implementation changes current stable developer-facing storage/job-store boundary text, which this plan forbids.

`tests/README.md`：

- Triggered for check because implementation will modify `tests/fins` and possibly `tests/runtime`。
- Current README already describes runtime filelock coverage（`tests/README.md:93`）and Fins ingestion runtime file-lock failure coverage as current fact（`tests/README.md:151`）。
- Decision：if the old `_StoreFileLock` failure-close test is removed or replaced, update `tests/README.md:151` to avoid claiming Fins ingestion runtime covers “文件锁失败关闭” through the deleted private stream helper. If only wording changes to “job store 使用 runtime filelock 的路径 / 原子写入清理”， keep it concise and factual. Do not add work-unit process notes.

## 12. Risks / open questions / residual risks

Blocking open questions：

- None under current evidence.

Implementation owner risks：

- R1：`RuntimeFileLockError` 不是 `OSError`，部分 internal docstring 当前只声明 `OSError`。Owner：implementation agent。Destination：Slice 1 / Slice 2 docstring updates and pyright/test review。
- R2：Storage batch release failure type changes from raw `OSError` to `RuntimeFileLockError`。Owner：implementation agent。Destination：Slice 2 tests and implementation report。Classification：acceptable if treated as runtime lock failure and not swallowed。
- R3：`filelock.FileLock` 的同进程 reentrancy 细节不应被 tests 断言。Owner：implementation agent。Destination：tests must assert Fins public behavior, not third-party internals。

Plan / review owner risks：

- R4：If reviewers require a stronger cross-process proof than current runtime contract and tests provide, that is a runtime contract coverage question, not a Fins wrapper justification。Owner：plan review。Destination：plan review finding or future runtime test slice。

Deferred / future owner risks：

- R5：This work unit does not add stale lock detection, crash recovery ownership, lease, fencing or distributed lock semantics。Owner：future runtime/Host recovery work only if product need appears。Destination：not this work unit; design truth explicitly excludes these semantics（`docs/host/design.md:286-293`）。

No unclassified residual risks remain.

## 13. Why this is not over-designed

- The plan replaces two existing private implementations with an already-designed public runtime primitive; it does not introduce a new abstraction.
- It keeps storage conflict wording in Fins because ticker-specific conflict is Fins storage behavior, while generic timeout remains runtime behavior.
- It keeps token ownership private to `_FsStorageInfra` instead of widening `BatchToken` or repository protocols.
- It deletes compatibility code rather than preserving old import paths.
- It does not modify Host / Engine / ToolRuntime contracts, durable schemas, job schemas, storage protocols, or README text unless current facts actually change.

## 14. Completion report format

Implementation / fix agent should report:

- Work unit / gate / slice。
- Files changed。
- What changed：
  - ingestion job store lock convergence；
  - storage batch lock convergence；
  - private lock deletion；
  - tests / README updates, if any。
- Validation performed：
  - exact pytest commands and results；
  - pyright result；
  - `git diff --check` result；
  - coverage commands and result, if run。
- If deleting old `_StoreFileLock` fd-close test, confirm it is not a coverage gap because Fins no longer opens lock streams and fd lifecycle is owned by `dayu.runtime.filelock` / third-party `filelock`。
- Blocking open questions。
- Residual risks with owner/destination。
- Confirmation that no Host / Engine / ToolRuntime contract, job schema, storage protocol or atomic replace semantics changed。
