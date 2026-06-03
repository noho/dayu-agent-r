# WU-RUNTIME-01 Runtime File Lock Wrapper Contraction Plan

## 1. Goal / Motivation / Non-goals / Scope Boundary

### 动机判断

动机成立，且不应扩大。

第一性原理判断：`dayu.runtime.filelock` 的稳定职责只是层中立同步文件互斥 adapter。它应统一第三方 `FileLock` 的 import 边界、parent directory 准备、timeout/error 包装和 context manager 释放路径，不应复制第三方 lock 的生命周期真源。当前 `RuntimeFileLock._active_token` 与 `RuntimeFileLockToken.released` 同时存在，已经让 wrapper 需要判断“是否仍持锁 / 是否释放成功”，这超出普通文件互斥 adapter 的必要职责，并且直接制造了 release 失败后状态被误标成功的风险。

严重性没有被低估：`release()` 在底层 `FileLock.release()` 抛错时把 `released` 标为 `True`，与 WU 验收信号“release 失败不会被标记成成功 released”冲突。虽然生产调用方没有读取 `token.released`，但 public token 状态会误导测试和后续调用方，把失败路径伪装成成功生命周期事实。

严重性也不能被扩大：该问题不证明需要 stale lock takeover、break lock、async lock、durable lease、fencing token、Host recovery 或 EventLog ordering。Host durable truth 仍只能来自 Host store、EventLog、状态索引和事务。

### Goal

收缩 `dayu.runtime.filelock`：

- 保留同步 `FileLock` wrapper 的必要 adapter 语义：显式 lock path、parent directory 准备、timeout 校验、第三方 timeout 包装、统一 runtime error、context manager 释放和 marker restore。
- 删除 public `RuntimeFileLockToken.released`，避免 wrapper 对外表达第二套 release lifecycle truth。
- 移除 `RuntimeFileLock._active_token` 及其基于 `released` 的同实例 acquire gate，让第三方 `FileLock` 继续持有 acquire/release 的实际生命周期真源。
- 保留 `RuntimeFileLockToken` 类型，因为 `acquire()` 和 `__enter__()` 仍需要返回一个可显式 `release()` 的 token；该 token 只负责把 release 调用路由到本次持有的第三方 lock，并提供幂等释放保护，不对外暴露“当前是否持锁”的 truth。

### Non-goals

- 不实现 stale lock 探测、owner pid 解析、强制 break lock、跨进程 takeover、lease、fencing、recovery proof。
- 不实现 async context manager，也不在线程池中隐藏阻塞 acquire。
- 不让 Host / Service / Engine / Fins / 工具模块直接 import 第三方 `filelock`。
- 不修改 Host durable state machine、EventLog ordering、Run / Attempt owner、projection checkpoint 或 audit/tool trace 业务语义。
- 不为旧 `token.released` 提供兼容 property、wrapper、re-export 或 facade。
- 不保留 `_active_token` 相关测试期望。

## 2. Direct Evidence And Code Check

### 设计与总控证据

- `docs/host/design.md` 明确 `dayu.runtime.filelock` 是第三方 `FileLock` 的同步统一封装，只用于普通文件互斥，不能表达 SQLite transaction、EventLog ordering、Host durable truth、Run / Attempt owner、lease / fencing 或 recovery。
- `docs/host/host-core-followup-implementation-control.md` 的 WU-RUNTIME-01 指定目标是收缩 `RuntimeFileLock`，让第三方 `FileLock` 持有实际 acquire/release 生命周期真源，并删除或隐藏无生产调用方依赖的 token released 状态。
- 同一设计真源当前 public API shape 仍列出 `RuntimeFileLockToken.released: bool`。因此删除 public field 是 public contract 收缩，implementation 必须同步更新 `docs/host/design.md` 的 `filelock` API shape 和 release 说明，不能只改代码。

### 当前代码证据

- `dayu/runtime/filelock.py`
  - `RuntimeFileLockToken` 有 public `released: bool`。
  - `RuntimeFileLock.acquire()` 使用 `_active_token is not None and not _active_token.released` 拒绝同实例重叠 acquire。
  - `RuntimeFileLock.__exit__()` 依赖 `_active_token` 找到 token 后 release，并 finally 清空 `_active_token`。
  - `RuntimeFileLockToken.release()` 在底层 release 抛错时先设置 `self.released = True` 再抛 `RuntimeFileLockError`，这就是验收信号冲突点。
- `dayu/host/audit.py`
  - 只在 `_append_audit_jsonl_line_if_absent()` 中用 `with file_lock(options.lock_path, timeout_seconds=_LOCK_TIMEOUT_SECONDS, create_parent_dirs=...)` 包住 JSONL append。
  - 不读取 `RuntimeFileLockToken`，不读取 `released`，也不依赖同一 `RuntimeFileLock` 实例复用。
- `dayu/host/tool_trace.py`
  - 只在 `ToolTraceProjectionConsumer._append_line()` 中用 `with file_lock(self._options.lock_path, timeout_seconds=_LOCK_TIMEOUT_SECONDS, create_parent_dirs=...)` 包住 cold JSONL append。
  - 不读取 token 状态，不依赖 wrapper active-token 语义。
- `tests/runtime/test_filelock.py`
  - 多个测试直接断言 `token.released` 和 `lock._active_token` 行为。
  - `test_release_failure_marks_token_released_to_prevent_retry` 是旧期望，应改为 release 失败不产生成功状态。
- `tests/runtime/test_import_boundary.py`
  - 已覆盖第三方 `filelock` import 只能在 `dayu.runtime.filelock` 中出现；本 WU 必须保留并继续运行。

### 调用方裁决

真正需要 `file_lock(...)` 的生产调用方只有：

- `dayu.host.audit`：audit JSONL append 普通文件互斥。
- `dayu.host.tool_trace`：tool trace cold JSONL append 普通文件互斥。

以下测试期望属于 wrapper 实现细节，应迁移或删除：

- 读取 `RuntimeFileLockToken.released` 来判断 context manager 是否释放。
- 直接写入或断言 `RuntimeFileLock._active_token`。
- 把同一 wrapper 实例嵌套 context / manual acquire 的具体失败方式当成 public contract。

## 3. Affected Files / Modules

### Implementation source allowed

- `dayu/runtime/filelock.py`
  - 唯一允许修改的 production source。
  - 只做 runtime adapter 收缩，不引入 Host / Engine / Service / UI / Fins import。

### Production source read-only

- `dayu/host/audit.py`
- `dayu/host/tool_trace.py`

这两个文件只作为调用方核对依据；除非 implementation 暴露出现有调用无法通过，否则不得修改。

### Tests allowed

- `tests/runtime/test_filelock.py`
  - 更新 public contract 测试，删除 `released` / `_active_token` 旧实现细节断言。
- `tests/runtime/test_import_boundary.py`
  - 原则上无需改；若 `filelock.py` import 形态变化导致扫描测试需要同步，只允许最小更新。
- `tests/host/test_audit_sink.py`
  - 补或调整一个锁路径开启的 audit JSONL append 回归测试，证明 Host 调用面仍通过 `with file_lock(...)` 工作。
- `tests/host/test_tool_trace_projection.py`
  - 补或调整一个锁路径开启的 tool trace cold JSONL append 回归测试，证明 Host 调用面仍通过 `with file_lock(...)` 工作。

### Contract / design docs allowed

- `docs/host/design.md`
  - 必须同步删除 `RuntimeFileLockToken.released: bool` public API shape。
  - 必须补充说明 token 不暴露 release 状态；幂等 release 只是防止同一 token 重复释放，不是 Host truth 或 wrapper lifecycle truth。

### README decision files

- `tests/README.md`
  - 若测试说明仍暗示 filelock 覆盖 public `released` 状态，必须更新。
- `dayu/README.md`
  - 当前只说 `filelock` 是第三方 `FileLock` 同步 wrapper、只用于普通文件互斥，不列 token / released API。按当前证据无需修改；implementation 完成后仍需检查是否有术语或 contract 不一致。

### Explicitly forbidden

- `docs/host/host-core-followup-implementation-control.md`
  - 本 WU 当前 plan 不修改总控文档；后续由 controller 在 gate 状态推进时单独维护。
- 不改 `dayu/runtime/lane.py`、Host durable store、projection runner、audit/tool trace production behavior。

## 4. Public Contract / Typing / API Decision

### `RuntimeFileLockToken.released`

裁决：删除 public `RuntimeFileLockToken.released`。

理由：

- 生产调用方没有依赖该字段。
- 该字段复制第三方 `FileLock` lifecycle 状态，且当前已经在 release 失败时表达错误事实。
- 保留 property 作为兼容 wrapper 只会继续传播第二套 truth，违反“不为旧接口保留兼容 wrapper”。
- 删除后，调用方只通过 `release()` 的返回 / 异常判断本次 release 调用是否成功；失败时不产生“成功 released”状态。

### `RuntimeFileLockToken`

裁决：保留 `RuntimeFileLockToken` 类型。

理由：

- `RuntimeFileLock.acquire()` 和 `RuntimeFileLock.__enter__()` 的稳定返回值仍需要一个可显式 `release()` 的对象。
- token 的稳定 public contract 收缩为：
  - `lock_path: Path`
  - `release() -> None`
- token 内部可以保留私有、类型明确的幂等 guard，例如 `_release_completed: bool`，但该 guard 只用于防止同一 token 在已成功释放后再次调用底层 release，不能对外暴露，也不能被 `RuntimeFileLock.acquire()` 当作 lock lifecycle truth。
- release 失败时私有 guard 不得切到成功态；后续 retry 仍会调用同一 token 持有的第三方 lock，或继续抛出底层失败包装后的 `RuntimeFileLockError`。
- 旧实现 release 失败后设置 `released = True` 阻止 retry；新实现不掩盖失败，允许后续 `release()` 调用再次尝试底层 release。这是 deliberate contract contraction，不是回归。

### `RuntimeFileLock._active_token`

裁决：移除 `_active_token`。

理由：

- `_active_token` 依赖 public `released` 判定同一 wrapper 实例是否仍 active，是第二套 lifecycle truth。
- 设计真源已声明 wrapper 不承诺 reentrant lock 语义，调用方不得依赖同一 `RuntimeFileLock` 实例重复 acquire 的成功、失败、计数或 token 复用行为；测试也不应断言第三方 reentrant 细节。
- `RuntimeFileLock` context manager 必须用私有 `_context_token: RuntimeFileLockToken | None` 保存 `__enter__()` 返回的 token 供 `__exit__()` 释放；不得在 `acquire()` 中基于该引用推导全局 lock lifecycle。该引用不是 public active token，也不替代第三方 `FileLock` 的状态。

### Typing constraints

- 所有新增或修改函数必须保留完整类型签名，不引入 `Any`、`object`、无类型参数、无类型返回值、裸容器。
- 所有新增或修改模块 / 类 / 函数 docstring 使用中文，函数 docstring 至少包含参数、返回值、异常。
- 不使用 lazy import；第三方 `filelock` import 仍只在 `dayu.runtime.filelock`。
- 不用 `hasattr` / `getattr` 逃避 contract 判断；测试检查删除 public field 时优先用 `dataclasses.fields(RuntimeFileLockToken)` 或 `RuntimeFileLock.__slots__` 这类结构化证据。

## 5. Implementation Decisions

### Acquire / release truth

- `FileLock.acquire()` 和 `FileLock.release()` 继续是实际 acquire/release 真源。
- `RuntimeFileLock.acquire()` 只做：
  - 计算 effective timeout。
  - 准备 parent directory。
  - 调用第三方 `FileLock.acquire(timeout=...)`。
  - 将第三方 `Timeout` 包装为 `RuntimeFileLockTimeoutError`。
  - 将其它 acquire 错误包装为 `RuntimeFileLockError`。
  - 返回 `RuntimeFileLockToken(lock_path=..., third_party_lock=...)`。
- `RuntimeFileLock.acquire()` 不再检查 `_active_token`，不再保存 active token。

### Token release

- `RuntimeFileLockToken.release()` 伪代码约束：

```python
def release(self) -> None:
    if self._release_completed:
        return
    try:
        self._third_party_lock.release()
    except Exception as exc:
        raise RuntimeFileLockError("释放 runtime file lock 失败") from exc
    self._release_completed = True
    try:
        _ensure_lock_file_marker_exists(self.lock_path)
    except Exception as exc:
        _LOGGER.debug(...)
```

- `_release_completed` 只能在第三方 release 成功返回后设为 `True`。
- 第三方 release 抛错时：
  - 不设置 `_release_completed`。
  - 不恢复 marker。
  - 抛 `RuntimeFileLockError`。
  - 不提供或更新 public `released`。
- marker restore 失败仍是 best-effort debug log，不向调用方抛错；这是因为底层 release 已成功，marker 文件不是 Host truth。

### Context manager

- `RuntimeFileLock` 必须使用私有 `__slots__` 字段 `_context_token: RuntimeFileLockToken | None` 保存当前 context manager frame 的 token。
- `RuntimeFileLock.__enter__()` 调用 `acquire()` 后，必须把返回的 token 存入 `_context_token` 并返回该 token。
- `RuntimeFileLock.__exit__()` 必须通过 `_context_token` 找到同一 `__enter__()` 获得的 token 并调用 `release()`，保证 marker restore 语义一致。
- `RuntimeFileLock.__exit__()` 必须在 `finally` 块中把 `_context_token` 清为 `None`，即使 `release()` 抛出 `RuntimeFileLockError`。
- `RuntimeFileLock.acquire()` 不得读写 `_context_token`，不得使用 `_context_token` 阻止或允许 acquire。
- `_context_token` 只服务 context manager cleanup，不是 lifecycle truth，不得出现在 public API、`__all__`、dataclass fields 或测试 public shape 期望中。
- context manager 退出时 release 失败必须继续向外抛 `RuntimeFileLockError`，且不得产生成功 release 状态。

### Parent directory / timeout / error / marker semantics

保持以下现有语义：

- `RuntimeFileLockOptions.__post_init__()` 校验 `lock_path` 与 timeout。
- `file_lock(str | Path, ...)` 归一化为 `Path`。
- `create_parent_dirs=True` 时创建 lock file parent directory。
- `create_parent_dirs=False` 且 parent 缺失时抛 `RuntimeFileLockError`。
- `timeout_seconds=None` 传第三方默认等待语义；`0` 是 non-blocking；正数是限时等待；负数抛 `RuntimeFileLockError`。
- 第三方 `Timeout` 包装为 `RuntimeFileLockTimeoutError`。
- release 成功后 best-effort touch lock marker；marker restore 失败只 debug log。

## 6. Implementation Slices

### Slice 1: Runtime filelock contract contraction

**Objective**

收缩 `dayu.runtime.filelock` public contract，删除 public `released` 和 `_active_token` lifecycle truth，并更新 runtime contract tests 与设计真源。

**Allowed files**

- `dayu/runtime/filelock.py`
- `tests/runtime/test_filelock.py`
- `tests/runtime/test_import_boundary.py`（仅在必要时最小调整）
- `docs/host/design.md`
- `tests/README.md`（只检查；除非现有 filelock bullet 出现 `released` 或等价旧语义，否则不改）
- `dayu/README.md`（只检查；除非发现不一致，否则不改）

**Exact changes**

- `dayu/runtime/filelock.py`
  - 从 `RuntimeFileLockToken` 删除 public `released` 字段。
  - 增加私有、类型明确的 `_release_completed: bool` 幂等 guard；只在底层 release 成功后设置。
  - 修改 `release()`：底层 release 抛错时不标成功，不 touch marker，包装为 `RuntimeFileLockError`。
  - 从 `RuntimeFileLock.__slots__` 和 annotations 删除 `_active_token`。
  - 修改 `acquire()`：删除现有 acquire gate，即删除 `if self._active_token is not None and not self._active_token.released: raise RuntimeFileLockError(...)`；不再读写 `_active_token`，不再基于 token 状态做同实例 active gate。
  - 增加私有 `_context_token: RuntimeFileLockToken | None` slot / annotation；它只服务 context manager cleanup。
  - 修改 `__enter__()` / `__exit__()`：`__enter__()` 将 `acquire()` 返回的 token 存入 `_context_token` 并返回；`__exit__()` 通过 `_context_token` 调用 `release()`，并在 `finally` 清空 `_context_token`；`acquire()` 不得读写 `_context_token`。
  - 保持 `RuntimeFileLockToken` 在 `__all__` 中导出。
- `tests/runtime/test_filelock.py`
  - 删除所有 `token.released` 断言。
  - 删除所有直接写入 / 读取 `lock._active_token` 的测试。
  - 删除 `test_nested_context_manager_on_same_instance_fails_fast`；该测试只覆盖旧同实例 acquire gate。
  - 删除 `test_manual_acquire_inside_context_fails_fast`；该测试只覆盖旧同实例 acquire gate。
  - 删除 `test_context_enter_after_manual_acquire_fails_fast`；该测试只覆盖旧同实例 acquire gate。
  - 删除或改写 `test_manual_release_allows_same_instance_reacquire`；若保留，不得断言 `released`，不得依赖同实例 gate，只能验证明确仍属于 public contract 的行为。
  - 删除或改写旧测试 `test_release_failure_marks_token_released_to_prevent_retry`，新期望不再是“阻止 retry”，而是“release 失败未标成功且允许 retry”。
  - 增加 public shape 测试：`RuntimeFileLockToken` dataclass fields 不包含 `released`，`RuntimeFileLock.__slots__` 不包含 `_active_token`，并且 `_context_token` 不出现在 token dataclass fields 或 public exports 中。
  - 增加 release 失败行为测试：底层 release 第一次抛错后，再次调用 `token.release()` 会再次调用底层 release；对 `_FailingThirdPartyLock` 断言 `release_calls == 2`，证明没有把失败标记为成功 release。
  - 保留并改写正常 context manager release 测试：退出 `with file_lock(...)` 后，第二个独立 `file_lock(lock_path).acquire(timeout_seconds=0)` 可以成功。
  - 保留异常路径 context manager release 测试：with block 抛业务异常后，第二个独立 lock 可以 non-blocking acquire。
  - 保留 release 幂等测试：底层 release 成功后重复 `token.release()` 不重复调用底层 release，lock marker 仍存在。
  - 保留 marker restore failure 测试：底层 release 成功、marker restore 失败不向调用方抛错，重复 release 不重复调用底层 release。
  - 保留 parent directory、missing parent、timeout wrapping、public non-goals 测试。
- `docs/host/design.md`
  - 从 `RuntimeFileLockToken` public API shape 删除 `released: bool`。
  - 在 release 段落说明 token release 幂等但不暴露状态；release 失败不得被标记为成功 release。

**Non-goals**

- 不改 Host source。
- 不新增 async wrapper。
- 不测试同一 wrapper 实例 reentrant 的具体第三方行为。
- 不增加兼容 property。

**Tests**

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
source .venv/bin/activate && pyright
```

**Stop condition**

- 如果 `rg "RuntimeFileLockToken|\\.released|_active_token" dayu tests docs README.md` 显示生产代码或稳定文档仍依赖 `RuntimeFileLockToken.released` / `_active_token`，且不能在本 slice 内按收缩目标清理，停止并交回 controller。
- 如果删除 `released` 需要保留兼容 property 才能通过测试，停止；不能用兼容 wrapper 掩盖 contract 变更。

### Slice 2: Host audit / tool trace lock-path regression

**Objective**

证明生产调用面只需要 `with file_lock(...)` 的普通文件互斥能力，runtime contract 收缩不破坏 audit / tool trace JSONL append。

**Allowed files**

- `tests/host/test_audit_sink.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/README.md`（只检查；除非现有 filelock bullet 出现 `released` 或等价旧语义，否则不改）

**Exact changes**

- `tests/host/test_audit_sink.py`
  - 增加或改写一个测试，使用 `LogAuditSinkOptions(audit_jsonl_path=..., create_parent_dirs=True, lock_path=<explicit lock path>)` 运行一次 audit projection。
  - 断言 JSONL line 成功追加、sink marker / checkpoint 行为保持现有预期、lock marker 文件存在。
  - 不读取 token，不 mock `_active_token`，不导入第三方 `filelock`。
- `tests/host/test_tool_trace_projection.py`
  - 增加或改写一个测试，使用 `ToolTraceSinkOptions(cold_jsonl_path=..., create_parent_dirs=True, lock_path=<explicit lock path>)` 运行一次 tool trace projection。
  - 断言 hot row 写入、cold JSONL line 追加、lock marker 文件存在。
  - 不读取 token，不导入第三方 `filelock`。

**Non-goals**

- 不修改 `dayu/host/audit.py` 或 `dayu/host/tool_trace.py`。
- 不新增多进程 contention 测试；runtime filelock 自身的 non-blocking timeout 已覆盖互斥失败包装，本 slice 只覆盖 Host 调用面。
- 不改变 projection checkpoint、audit marker、tool trace hot row 语义。

**Tests**

```bash
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q
source .venv/bin/activate && pyright
```

**Stop condition**

- 如果 Host tests 暴露需要修改 production audit/tool trace 行为才能适配 runtime contraction，停止并交回 controller；本 WU 的证据不支持改 Host 业务路径。

## 7. Tests And Validation Commands

Minimum required validation after implementation:

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q
source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
source .venv/bin/activate && pyright
```

Optional broader confidence if time budget allows:

```bash
source .venv/bin/activate && pytest tests/runtime -q
source .venv/bin/activate && pytest tests/host/test_import_boundary.py -q
```

选择依据：

- `tests/runtime/test_filelock.py` 是 contract 变更主测试。
- `tests/runtime/test_import_boundary.py` 证明第三方 `filelock` import 仍被 runtime wrapper 独占。
- `tests/host/test_audit_sink.py` 和 `tests/host/test_tool_trace_projection.py` 覆盖受影响的生产调用面。
- `pyright` 是项目强制类型检查，必须在 `.venv` 激活后运行。

## 8. README Sync Decision

### `tests/README.md`

需要检查，当前证据倾向不修改。

理由：`tests/README.md` 当前 filelock bullet 只描述 parent directory、结构化错误、context manager release、release 幂等、non-blocking timeout 和第三方 import 边界，没有出现 `released` 或等价旧语义。若 implementation 后检查仍如此，则不改；新增 public shape / release retry 行为测试属于 runtime test 内部策略变化，不需要机械同步 README。

### `dayu/README.md`

需要检查，默认不修改。

理由：`dayu/README.md` 当前只在 runtime 总览中说明 `filelock` 是第三方 `FileLock` 的同步 wrapper，只用于普通文件互斥，不替代 SQLite transaction、EventLog 顺序或 Host 状态机。该表述与收缩后的 contract 一致，且没有列出 `RuntimeFileLockToken.released`。除非 implementation 同步检查发现旧术语或 public API 描述残留，否则不改。

### `docs/host/design.md`

必须修改。

理由：删除 `RuntimeFileLockToken.released` 是 public contract 收缩，而 `docs/host/design.md` 是 Host 设计真源，当前仍列出该字段。若只改代码和测试，会形成设计真源与实现不一致。

## 9. Plan Review Gates

Plan review 必须检查：

- Scope 是否只解决 runtime filelock wrapper contraction，没有扩大到 stale lock、async lock、durable lease、Host recovery。
- Contract 裁决是否明确删除 `released`、保留 token、移除 `_active_token`，且没有兼容 wrapper。
- Implementation instructions 是否足够具体，implementation agent 不需要重新设计 release failure、marker restore、timeout wrapping 或 context manager 行为。
- Tests 是否覆盖 runtime contract、import boundary、audit/tool trace 调用面和 pyright。
- README / design doc sync 是否符合触发规则。
- 是否存在反向依赖、`Any` / `object` / 无类型签名、lazy import 或 magic compatibility path。

Implementation review 必须检查：

- `dayu.runtime.filelock` 没有 import Host / Engine / Service / UI / Fins。
- 第三方 `filelock` import 仍只在 `dayu.runtime.filelock`。
- release 失败时没有 public 或 private 成功态推进。
- marker restore 失败不掩盖底层 release 成功，也不吞底层 release 失败。
- Host audit/tool trace production source 未被不必要修改。
- Tests 不再把 `_active_token` / `released` 当成 public contract。

## 10. Open Questions

Blocking questions: none.

Non-blocking working assumptions:

- 允许 implementation slice 同步更新 `docs/host/design.md`，因为这是 public contract 收缩的真源同步，不是扩大 WU scope。
- 允许删除 `RuntimeFileLockToken.released` 造成测试和内部 API breaking change；项目约束明确不为旧接口保留兼容逻辑。
- `RuntimeFileLockToken` 保留在 public exports 中，因为 acquire/context manager 返回 token 的 shape 仍稳定。

触发回看信号：

- 若代码核对发现生产代码读取 `token.released`，必须停止并重新裁决 contract。
- 若第三方 `FileLock` release 语义无法支持 token 私有幂等 guard，必须停止并重新设计 token 与 context manager 的最小 state。
- 若 design review 认为删除 public `released` 必须先单独更新设计真源并 review，则 implementation 不应先改 source。

## 11. Risks / Residual Risk Classification

- Fixed in current slice before review:
  - `release()` 失败被标记为成功 released。
  - `_active_token` / `released` 组合形成第二套 lifecycle truth。
  - runtime tests 锁定实现细节。
- Covered by current validation:
  - Runtime import boundary。
  - audit / tool trace JSONL append 使用 lock path 的调用面。
  - pyright 类型约束。
- Accepted residual risk:
  - 同一 `RuntimeFileLock` 实例的 reentrant / nested acquire 具体行为不承诺；这是设计真源非目标，不作为 bug。
  - file lock marker 文件不是 Host truth；marker restore best-effort 失败只记录 debug，不升级为 durable failure。
- Deferred to other work unit:
  - `dayu.runtime.lane` 的 clock / cancellation 简化属于 WU-RUNTIME-02。
  - Host recovery、durable lease、Attempt owner、EventLog ordering 不属于本 WU。

## 12. Completion Report Format

Implementation agent 完成后必须用以下格式报告：

```text
WU-RUNTIME-01 completion report

Changed:
- <列出 source/test/docs/README 实际改动>

Contract decisions implemented:
- RuntimeFileLockToken.released: removed / not present
- RuntimeFileLockToken: retained with <public fields/methods>
- RuntimeFileLock._active_token: removed / not present

Validation:
- source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
  Result: <pass/fail>
- source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q
  Result: <pass/fail>
- source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
  Result: <pass/fail, coverage summary>
- source .venv/bin/activate && pyright
  Result: <pass/fail>

Docs:
- docs/host/design.md: <updated/not updated and reason>
- tests/README.md: <updated/not updated and reason>
- dayu/README.md: <updated/not updated and reason>

Residual risks:
- <none / classified list with owner>

Stop conditions hit:
- <none / details>
```
