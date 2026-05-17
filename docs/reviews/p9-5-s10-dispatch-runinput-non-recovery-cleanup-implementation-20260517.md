# P9.5 S10 Dispatch / RunInput Non-Recovery Cleanup Implementation

日期：2026-05-17

## 动机判断

S10 动机成立。当前 Host dispatch scheduler 已有 durable recheck、lane token release、active registry cleanup 与 worker handle close 的基础闭环，但 drain loop 空队列 / close / 异常退出路径缺少足够可观测日志；`resolve_wait` late rejection 也会在已写入 bounded diagnostic 后继续触发 projection catch-up，扩大了拒绝路径的副作用。两类问题都能在当前 Host 边界内收紧，不需要 Phase 11 recovery、RECOVERING dispatch、startup scan、orphan proof、RemoteProxy 或状态语义变更。

Stop condition 未触发：本轮没有新增 Host 状态、没有引入 recovery 证明或远端 worker 语义，也没有改变 public error code。

## 改动文件

- `dayu/host/dispatch.py`
  - 为 `_drain_loop` 增加模块级日志常量。
  - 空队列 sleep、正常 close exit、close 取消、外部取消和未预期异常退出均写入明确日志；行为保持 logs only。
- `dayu/host/waiting.py`
  - `DefaultHostResolveWaitService.resolve_wait` 只在成功 resolve 后执行 best-effort projection catch-up。
  - `_LateRejectResult` 仍保留已提交的 bounded diagnostic，并以既有 `HostApiErrorCode.INVALID_STATE` 返回，不触发 catch-up。
- `tests/host/test_dispatch_scheduler.py`
  - 覆盖 drain loop 空队列 sleep 与 close 取消日志。
  - 覆盖 lane acquire 后 pre-accept cancel race：不调用 worker、释放 lane token、durable 状态收口为 cancelled。
  - 扩展 worker stream exception 测试，断言 LOST closeout 后 worker handle 已关闭、active registry 已注销、lane token 已释放。
- `tests/host/test_run_input_builder.py`
  - 增加 stale dispatch snapshot identity 测试，覆盖 execution id、dispatch record id、execution target 的 optimistic TOCTOU fail-closed 行为。
- `tests/host/test_wait_cancel_late_result.py`
  - 增加 late result rejection 不触发 projection catch-up、不创建 resume Attempt、不追加 resume facts 的断言。
- `dayu/host/README.md`
  - 同步当前行为：late result rejection 只写 diagnostic，不创建 resume Attempt，不触发 projection catch-up；projection catch-up 只描述为成功 `resolve_wait` 的 post-commit best-effort 行为。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py`：65 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors, 0 warnings, 0 informations。
- `git diff --check`：通过，无输出。

## 文档决策

本轮触及 `dayu/host/` 与 `tests/host/`。`dayu/host/README.md` 中 `resolve_wait` / projection catch-up 说明与新行为相关，因此做最小同步。`tests/README.md` 已覆盖 dispatch scheduler、RunInputBuilder、late diagnostic 与 after-commit catch-up failure tolerance 的测试范围，没有发现与当前行为冲突的描述，因此未修改。

## 残余风险

- `_drain_loop` 的新增 observability 只记录日志，不改变后台任务重启或异常恢复策略；异常后是否重新启动仍由当前 scheduler lifecycle 负责。
- lane release 仍是 runtime capacity cleanup，不提升为 Host ownership / fencing truth。
- late rejection diagnostic 已提交后不再触发 projection catch-up；如果调用方依赖 rejection 后立即刷新 projection，需要通过后续成功 command 或显式 repair/catch-up 路径获得一致 read model。

## 停止状态

implementation 完成；未 commit、未 push、未创建 PR。
