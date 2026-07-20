# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: S1 accepted commit `2f2b73f8`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s2-code-review-ds.md`
- Included scope: 全部 workspace changes（staged + unstaged），覆盖 `dayu/host/_durable_actor.py`、`dayu/host/open_host.py`、`dayu/host/api.py`、`dayu/host/command.py`、`dayu/host/dispatch.py`、`dayu/host/__init__.py`、`dayu/service/host_admin.py`、`dayu/service/__init__.py`、`dayu/cli/commands/session.py`、`tests/host/test_durable_actor.py`、`tests/host/test_public_host_admin.py`、`tests/service/test_host_admin.py`、`tests/host/test_open_host_runtime.py`、`tests/host/test_public_lifecycle_smoke.py`（仅删除过期 purge closed-handle 断言）、以及相关 package export / session / purge / storage / watch / CLI / README / design doc 变更。
- Excluded scope: 无。S1 accepted code（`_runner_call_manifest.py` / `payload_resolution.py` 等）不在 S2 review scope；S3-S8 健康/恢复/取消/等待/压缩/运行时清理仅以计划约束形式参考。
- Parallel review coverage: 无。单一 reviewer 完整走读全部 S2 生产与测试代码路径。

## Review Method Summary

沿 S2 八个 review focus 逐项走读实际代码路径，验证：

1. HostAdmin 分离：`open_host_admin` → `_OpenHostAdminContextManager.__aenter__()` → `_AdminCommandHandleFactory()` → `open_durable_actor()` → `_PublicHostAdminHandle`。确认 admin opener 不构造 scheduler、recovery、wait poller、lane、worker、scene、tool 或 model secret；admin handle 不暴露 execution/cancel/watch；execution `_PublicHostHandle` 不含 list/purge/storage admin。`Host` 与 `HostAdmin` 是两个独立 `Protocol`，互不继承，无 compatibility wrapper/facade。
2. Durable actor 所有权：`open_durable_actor()` 在 `ThreadPoolExecutor(max_workers=1)` 唯一 worker thread 中通过 `handle_factory` 创建 `HostCommandHandle`；handle/store/connection 永不离开该 thread。scheduler store 由 opener loop thread 通过独立 `open_host_durable_store()` 创建，两者不共享 connection/transaction runner。`NoActiveWorkerCancelPort` 在 admin 路径显式表达无 worker 语义。
3. Busy SQLite / event loop：`test_public_write_busy_retry_does_not_block_opener_event_loop` 使用真实 `BEGIN IMMEDIATE` 持锁 + `asyncio.Event` barrier，证明 opener loop 在 actor busy retry 期间确定性前进。`test_public_ensure_submit_read_and_watch_share_actor_thread` 证明所有 command/read/watch 入口提交到同一 actor thread，不以 sleep 次数为 oracle。
4. Caller cancellation 与 FIFO：`DurableActor.call()` 使用 `asyncio.shield()` 隔离 caller cancellation；`test_caller_cancellation_preserves_underlying_fifo_completion` 证明取消后底层 operation 继续完成，后续 call 仍按 FIFO 成功。
5. Event-loop bridge：`_ThreadsafeSchedulerWakeupPort` 与 `_ThreadsafeActiveWorkerCancelPort` 通过 `loop.call_soon_threadsafe()` + `concurrent.futures.Future` 桥接，异常经 `future.result()` 回到 actor caller。`test_event_loop_bridge_exception_returns_through_actor` 证明 bridge 异常透传且 actor 不被毒化。未实现 S3 health/admission 或 S5 cancel classification。
6. Close order：execution close 顺序为 public gate → wait poller close → actor drain → scheduler close → projection flush → actor handle close → executor shutdown → scheduler store close。`test_close_drains_actor_wake_before_scheduler_and_preserves_close_order` 通过阻塞 actor wake + barrier 验证 scheduler 在 wake 收口后才关闭，完整序列为 `scheduler → projection → actor_handle → actor_store → executor → scheduler_store`。admin close 只关闭 actor chain（drain → handle → executor），`test_admin_close_is_idempotent_and_leaves_no_actor_thread` 证明幂等且无 worker thread 残留。
7. Tests/docs：测试断言 owner-level behavior（线程归属、connection 独立、能力分离、FIFO、cancel 隔离、bridge 异常、close order），不依赖 private fake 限制。`test_public_lifecycle_smoke.py` 仅删除过期 execution `Host.purge_session()` closed-handle 断言与对应 helper/import；`test_import_boundary.py` 补入 S1 accepted 的 Engine-contract allowlist。README/docs 更新匹配 S2 实现范围。
8. 项目约束：全部新增 docstring 为中文；`DurableActor`/`open_durable_actor`/`_AdminCommandHandleFactory`/`_ExecutionCommandHandleFactory` 等新增签名无 `Any`/`object`；无反向依赖；无 compatibility re-export/wrapper；无 schema migration。

## Findings

未发现实质性问题。

所有八个 review focus 的实际代码路径均与 plan 冻结的 S2 实现契约一致。controller 已通过的验证矩阵（417 passed、pyright 0 errors、`git diff --check` pass、source scans）与本次走读结果一致，未发现 report 未覆盖或与代码实际行为冲突的缺陷。

## Open Questions

无。

## Residual Risk

- S3-S5 的 scheduler health/admission lease、recovery batching、active-cancel watchdog event/classification 与 deferred cancel state 扩展均不在 S2 scope，由后续 approved slice 负责。当前 S2 的 actor/bridge 基础设施已为这些 slice 提供稳定 handoff 点。
- `DurableActor.close()` 在 `close_handle()` 失败时不会执行 `shutdown_executor()`（`_shutdown` 保持 `False`），但仍由 `_PublicHostHandle.close()` 在独立 try/except 块中调用 `shutdown_executor()` 保证 executor 回收。admin 路径 `_PublicHostAdminHandle.close()` → `DurableActor.close()` 不存在同级 fallback；但 ThreadPoolExecutor worker threads 为 daemon，不会阻止进程退出，且 SQLite close 失败是极端 I/O 错误路径。该差异在计划中未显式要求 admin close 层对 executor 做独立重试，当前行为属于可接受实现选择，不构成 S2 gate blocker。
- 无未分类 residual risk，无 blocking open question。
