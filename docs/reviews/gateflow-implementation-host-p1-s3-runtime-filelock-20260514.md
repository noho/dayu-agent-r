# Host Phase 1 Slice 3 Implementation Artifact

## Work Gate

implementation

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Assigned Slice

Slice 3: `dayu.runtime.filelock` sync wrapper。

## Approved Plan

- `docs/host/phase1-public-contract-runtime-plan.md`
- accepted plan commit: `34b1b41`
- accepted Slice 1 commit: `66d8dc3`
- accepted Slice 2 commit: `27e0d8b`
- controller state commit: `9ae1238`

## Assigned Scope

只实现层中立同步 file lock wrapper，统一第三方 `filelock.FileLock` 依赖边界和错误语义。

允许修改并已触达：

- `dayu/runtime/filelock.py`
- `pyproject.toml`
- `tests/runtime/test_filelock.py`
- `tests/runtime/test_import_boundary.py`
- `dayu/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p1-s3-runtime-filelock-20260514.md`
- `dayu/runtime/__init__.py`（code review controller 授权补充包 docstring）

未触达 forbidden files；`dayu/runtime/__init__.py` 仅按 controller 授权补充包 docstring，`__all__` 仍为空且未新增 package-root re-export。

## Changed Files

- `dayu/runtime/filelock.py`
- `pyproject.toml`
- `tests/runtime/test_filelock.py`
- `tests/runtime/test_import_boundary.py`
- `dayu/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p1-s3-runtime-filelock-20260514.md`
- `dayu/runtime/__init__.py`

## Plan Items Implemented

- 在 `pyproject.toml` production dependencies 增加 `filelock>=3.18.0`，不依赖 transitive dependency。
- 新增 `RuntimeFileLockOptions`、`RuntimeFileLock`、`RuntimeFileLockToken`、`file_lock`、`RuntimeFileLockError`、`RuntimeFileLockTimeoutError`。
- `dayu.runtime.filelock` 是唯一直接 import 第三方 `filelock` 的模块。
- `lock_path` 作为显式 lock file 路径处理，不从业务文件路径派生。
- `create_parent_dirs=True` 时创建 parent directory；`False` 且 parent 缺失时先抛 `RuntimeFileLockError`。
- `timeout_seconds=None` 使用第三方默认等待语义；`0` non-blocking；正数限时等待；第三方 timeout 包装为 `RuntimeFileLockTimeoutError`。
- parent directory、路径、acquire 与 release 失败统一包装为 `RuntimeFileLockError` 或子类。
- `RuntimeFileLockToken.release()` 幂等；context manager 正常与异常路径均 release。
- release 后恢复 lock marker 文件存在性，避免当前第三方 Unix 实现 release 时 unlink lock file 破坏本 slice 的“不删除锁文件”外部语义。
- 测试覆盖 parent directory 创建、禁用创建时结构化错误、context manager release、异常路径 release、release 幂等、non-blocking timeout 包装、public non-goals 与 import boundary。
- README 同步当前 runtime filelock 能力和测试入口。
- code review accepted finding #3 doc-only fix：按 controller 授权最小更新 `dayu/runtime/__init__.py` 包 docstring，说明 Phase 1 当前已有 lane 与同步 filelock 两个层中立 runtime 能力；未从包根 re-export `lane` / `filelock` 符号，`__all__` 仍为空。

## Not Implemented

- 未实现 async file lock / async context manager。
- 未实现 stale lock detection、owner pid parsing、cross-process takeover、force break lock。
- 未用 filelock 保护 SQLite、EventLog、Host durable truth 或 Host 状态机。
- 未修改 Host / Engine / Fins / Service / UI。
- 未修改 lockfile；当前 handoff 仅授权 `pyproject.toml`。

## Validation Commands And Results

- `source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q`
  - result: passed, `12 passed in 0.13s`
- `source .venv/bin/activate && python -m pyright dayu/runtime/filelock.py tests/runtime/test_filelock.py`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed

## Documentation Update

- `dayu/README.md`: 将 filelock 从设计要求同步为 `dayu.runtime.filelock` 当前已实现的同步 wrapper 能力，并记录 non-goals。
- `dayu/runtime/__init__.py`: code review controller 授权的 doc-only fix，补充 Phase 1 当前已有 `lane` 与同步 `filelock` 两个层中立 runtime 能力；未新增包根导出。
- `tests/README.md`: 增加 runtime filelock 测试命令与测试覆盖说明。
- 根目录 `README.md` 未更新：本 slice 不改变用户安装、配置、CLI、trace/render 入口或常用工作流。

## Plan Gaps / Controller Questions

- 无阻塞缺口。
- 发现 `filelock 3.28.0` 的 Unix 实现 release 时会 unlink lock file；本实现通过 release 后恢复 marker 文件维持 wrapper 外部“不删除锁文件”语义。若 controller 要求“底层绝不发生 unlink”而不是“wrapper 对外不删除”，需要后续单独裁决第三方实现选择或更底层适配方案。

## Residual Risks Classification

- accepted as covered by later phase: Host durable store / EventLog / ToolRuntime 不使用 filelock 的集成边界由后续 Host phases 继续保持。
- assigned to later phase or work unit: 若未来 async 调用方需要 file lock，必须在调用方边界显式决定 executor 策略；本 slice 不提供隐藏 threadpool wrapper。
- no current-slice blocker: 当前同步 wrapper API、错误语义、import boundary 与测试均已落地。

## Completion Signal

`dayu.runtime.filelock` 可导入，指定 runtime filelock tests 与 pyright 验证通过。

## Stop Condition Status

未触发 stop condition。未实现 async wrapper、stale takeover、删除 lock file、在 `dayu.runtime.filelock` 外直接使用第三方 `filelock` 或触碰 forbidden files；`dayu/runtime/__init__.py` 的包 docstring 修改来自 code review controller 对 accepted finding #3 的明确授权，未新增 package-root re-export。

## Artifact Path

`docs/reviews/gateflow-implementation-host-p1-s3-runtime-filelock-20260514.md`
