# WU-CTX-04 Slice 1 implementation artifact（AgentCodex）

## Gate metadata

- status：`complete`
- work unit：`WU-CTX-04`
- gate：`implementation Slice 1/3`
- accepted plan commit：`1f032b5e2d1aba974304ee4537be76ed4a1174e6`
- scope：strict-native runtime primitive 与 Host internal attachment registry contract-only 实现。
- stop boundary：未进入 Slice 2、code review、commit、push、PR 或其它后续 gate。
- blocking questions：None。

## First-principles judgment 与 root owner 实现

问题动机成立：SQLite transaction/CAS 只拥有 durable truth，无法提供跨 opener 的
Session 新工作资格；普通 third-party filelock 又不承诺 strict-native、process-exit
释放与 unsupported fail-closed。Slice 1 因而只建立两个同源 owner，不改变任何现有
production call path：

1. `dayu.runtime.native_mutex` 是跨进程机械互斥唯一 owner。它只接收最终 `Path`，
   使用 POSIX `flock` 或 Windows `msvcrt.locking` nonblocking acquire；明确 busy 返回
   `None`，unsupported、open/truncate、非白名单 syscall、partial cleanup 与 release
   错误均 fail closed。handle 成功 close 幂等，失败结果稳定缓存；进程退出依赖 OS
   关闭 descriptor 释放锁。
2. `HostSessionAttachmentRegistry` 是 opener 内 canonical DB/Session key、不可变 mode、
   live record、RECOVERING/ACTIVE/CLOSING/CLOSED、mutation/new-work lease 与 close 顺序
   的唯一 owner。duplicate live record 在 path 准备/native acquire 前 typed conflict；
   RECOVERING 只允许 allocation recovery lease；ACTIVE RW 才允许 mutation/new work。
   lease 绑定底层 Future/task。单 attachment 并发 close 共享 cleanup；Host close 使用
   独立 `begin_host_close -> drain_host_close -> release_host_close` batch contract，drain
   后仍持有全部 native mutex，等待后续 Slice 2 的 scheduler lifecycle barrier 成功后
   才允许显式 release。
3. `dayu.host.api` 只增加 registry 内部消费的 mode/error value types，并把两个 detail
   纳入 closed `HostApiErrorDetail` union。`Host` Protocol、`dayu.host` 包根 export、
   `open_host`、scheduler、recovery 与现有 production behavior 均未修改。

## Changed files

- `dayu/runtime/native_mutex.py`（new）：stdlib-only strict-native nonblocking mutex、busy
  白名单、partial descriptor cleanup、Windows lock-byte、幂等 handle close。
- `dayu/runtime/__init__.py`：仅在层中立 package 概览中登记 native mutex；没有包根
  re-export。
- `dayu/host/session_attachment.py`（new）：canonical key、internal allocation/attachment、
  registry lifecycle、mutation/new-work/recovery lease 与 Host-close batch contract。
- `dayu/host/api.py`：仅新增 `HostSessionAccessMode`、mutation/attachment rejection reason
  与 typed detail，并扩展 `HostApiErrorDetail` closed union；未修改 `Host` Protocol 或
  `__all__`。
- `tests/runtime/test_native_mutex.py`（new）：真实同/different key、subprocess close/
  exit/kill、POSIX/Windows backend、busy/unavailable/partial failure 与 close 幂等测试。
- `tests/runtime/test_import_boundary.py`：把 `native_mutex.py` 加入 runtime import scan
  显式覆盖断言。
- `tests/host/test_session_attachment_registry.py`（new）：canonical key、RECOVERING/
  ACTIVE/CLOSING uniqueness、RW/RO immutable mode、lease/Future/task、attach caller
  cancellation、concurrent close、Host-close mark/drain/release、API value types与包根
  非导出测试。
- `docs/reviews/wu-ctx-04-slice-1-implementation-codex.md`（new）：本 implementation
  artifact。

总控持有的 `docs/host/issues-implementation-control.md` 是既存未提交修改，不属于上述
implementation changed files；本 Agent 未修改。实施前后 worktree content hash 均为
`e6bae4c74864199c6005e757c790fe1a56e129b9`。

## Contract / state machine completion signal

- 同一 strict-native key：首个 handle 获取、第二个明确 busy；close 后 fresh acquire；
  不同 key 并行；marker 文件残留不表示 owner。
- subprocess 显式 close、正常 process exit 与 kill 后均可重新获取同 key。
- POSIX 与 Windows backend 均只把白名单 contention 映射为 `None`；unsupported/backend
  缺失、unexpected errno、open/truncate、partial close 与 release 错误均 unavailable。
- Host mutex 文件名精确来自
  `sha256(normcase(str(db_path.resolve(strict=True))) + "\0" + session_id)`，目录位于真实
  DB 同目录的固定私有子目录，不暴露 raw Session id。
- 同 registry/Session 在 RECOVERING、ACTIVE、CLOSING 全集只有一个 live record；
  duplicate 在任何 native acquire 前返回不可重试 typed conflict。
- RO mode 在原 attachment 生命周期内不升级；owner release 后必须 close/fresh attach
  才重新竞争。
- mutation 与 new-work lease 均阻止 mutex 提前释放，并可绑定底层 Future/task；取消
  attachment/allocation close awaiter 不取消共享 cleanup。
- Host-close drain 完成后 mutex 仍保持 busy；只有显式 `release_host_close` 才关闭 handle
  并删除 record。该模块不写 durable fact，也不从 mutex 推导 Run/Attempt truth。

## Validation

- accepted plan §8.1 focused pytest：
  `source .venv/bin/activate && pytest tests/runtime/test_native_mutex.py tests/runtime/test_import_boundary.py tests/host/test_session_attachment_registry.py -q`
  → `43 passed in 1.37s`。
- accepted plan §8.1 targeted pyright：
  `source .venv/bin/activate && python -m pyright dayu/runtime/native_mutex.py dayu/host/session_attachment.py tests/runtime/test_native_mutex.py tests/host/test_session_attachment_registry.py`
  → `0 errors, 0 warnings, 0 informations`。
- runtime 全套：
  `source .venv/bin/activate && pytest tests/runtime -q`
  → `594 passed, 3 warnings in 7.35s`；warnings 均为既有 `edgar` deprecation warnings。
- API/export/weak-typing affected matrix：
  `source .venv/bin/activate && pytest tests/runtime/test_weak_typing_guard.py tests/host/test_weak_typing_guard.py tests/host/test_package_exports.py tests/host/test_public_contracts.py -q`
  → `65 passed in 0.85s`。
- API 新分支核对：
  `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_session_attachment_registry.py --cov=dayu.host.api --cov-report=term-missing -q`
  → `61 passed in 0.46s`；新增 value type 行均未出现在 missing-lines，`api.py`
  全文件 coverage `74%` 按 accepted plan 留待 Slice 3 最终矩阵。
- changed API/runtime/import-boundary targeted pyright：
  `source .venv/bin/activate && python -m pyright dayu/host/api.py dayu/runtime/__init__.py tests/runtime/test_import_boundary.py`
  → `0 errors, 0 warnings, 0 informations`。
- 全量 pyright：
  `source .venv/bin/activate && python -m pyright`
  → `0 errors, 0 warnings, 0 informations`。
- 双新增 production module coverage：
  `source .venv/bin/activate && pytest tests/runtime/test_native_mutex.py tests/host/test_session_attachment_registry.py --cov=dayu.runtime.native_mutex --cov=dayu.host.session_attachment --cov-report=term-missing -q`
  → `29 passed in 0.49s`；`dayu/runtime/native_mutex.py=91%`，
  `dayu/host/session_attachment.py=86%`，均 `>=80%`。
- Ruff targeted：
  `source .venv/bin/activate && python -m ruff check dayu/runtime/native_mutex.py dayu/host/session_attachment.py tests/runtime/test_native_mutex.py tests/runtime/test_import_boundary.py tests/host/test_session_attachment_registry.py`
  → `All checks passed!`。
- whitespace：tracked `git diff --check` exit `0`；四个 untracked Python 文件分别执行
  `git diff --no-index --check /dev/null <file>`，均无 whitespace error 输出（exit `1`
  仅表示存在预期 diff）。artifact 创建后再执行相同最终审计。
- changed-files audit：除总控既存 dirty file 外，仅包含 accepted Slice 1 allowlist 与本
  artifact；`dayu/host/__init__.py`、`open_host.py`、scheduler、recovery、README 及其它
  文件均未修改。

## README decision

本 Slice 不修改任何 README。accepted plan 明确要求基于最终 production wiring 在
Slice 3 统一更新；Slice 1 是 contract-only，提前把 internal 半成品写成 current public
behavior 会造成文档语义错误。`dayu/runtime/__init__.py` 仅同步当前已落地的层中立能力
概览，不是 README 更新。

## Blocking / residual risks

- blocking：None。
- `covered by later approved slice`：public `Host.attach_session`、mutation/scheduler gate、
  target recovery、Host scheduler-before-unlock lifecycle barrier 与 production behavior
  尚未接线；这是 accepted Slice 2/3 的明确范围，本 Slice 禁止提前进入。
- `covered by later approved slice`：当前验证环境为 Darwin；Windows backend 已通过强类型
  fake 验证 lock-byte、nonblocking/busy、unlock、truncate/close failure 路径，真实 Windows
  环境验证保留给 WU-CTX-04 Slice 3 final matrix / CI owner。
- `covered by later approved slice`：`dayu/host/api.py` 全文件 coverage 最终目标留 Slice 3；
  本 Slice 新增 value type 的所有新分支已执行，未新增未测分支。

## Completion status

- Slice 1 completion signal：`pass`。
- slices completed：`1/3`。
- next entry point：按用户约束停止；不进入 Slice 2 或 code review gate。
