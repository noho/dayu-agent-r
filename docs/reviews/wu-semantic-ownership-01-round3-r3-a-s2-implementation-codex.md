# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S2 Implementation

## Gate / status

- Gate：S2 implementation。
- Slice：Host Admin 与 Public Durable Actor / Async Boundary。
- 当前状态：`ready-for-code-review`。
- Controller scope extension：controller 明确把 `tests/host/test_public_lifecycle_smoke.py` 窄扩入 S2，仅用于删除 execution `Host.purge_session()` 的过期 closed-handle 断言。未修改该文件其它 lifecycle smoke 行为，未通过 type-only shim、动态属性或把 admin 能力放回 execution Protocol 绕过。
- 未执行：commit、push、PR、control doc 修改、下一 gate。

## First-principles owner analysis

DR-007 成立。修改前 `dayu/cli/commands/session.py` 的 list / purge 会先调用完整 entrypoint runtime assembly，因而加载 scene、tool discovery、model 与 secret mapping，再打开带 scheduler / recovery / lane / worker 的 execution Host。list / purge 的业务语义只需要 Host durable Session / storage truth；其能力 owner 应是独立 `HostAdmin` public contract、admin opener 与 Service storage-only assembly，而不是 CLI 下游 fallback。

DR-011 成立。修改前 `_PublicHostHandle` 直接持有同步 `HostCommandHandle`，在 opener event loop 中执行 ensure / submit / read / watch；SQLite busy retry 会阻塞 loop。SQLite connection 的线程 owner 应是 durable actor：command handle、store、connection 的 create / use / close 全部在一个 single-worker thread，async public handle 只提交 typed `Callable[[HostCommandHandle], T]`。scheduler 继续由 opener loop 驱动并持有独立 store；本 slice不引入 async SQLite driver，也不搬迁 scheduler state machine。

跨线程 scheduler wake 与 active worker cancel 的语义 owner 是 opener-loop bridge。actor transaction 只产生 durable commit 与同步调用 typed port；scheduler callback、`LocalWorkerHandle.on_cancel()` 和 asyncio primitive 必须回到 opener loop，bridge exception 原样回到 actor caller。close owner 是 public opener lifecycle：先关闭新入口并 drain actor/wake，随后按 scheduler、projection、actor handle/store、executor、scheduler store 释放。

## Changed files

### Production

- `dayu/host/api.py`：新增独立 `HostAdmin` Protocol 与 `OpenHostAdminOptions`；从 execution `Host` 移除 list / purge / storage admin。
- `dayu/host/_durable_actor.py`：新增 single-worker durable actor、同步排队 watch attach、caller-cancellation shielding、FIFO drain、handle / executor 分阶段关闭。
- `dayu/host/open_host.py`：execution public calls 全部接入 actor；scheduler / actor store 分离；新增 scheduler wake / active cancel loop bridge、admin opener 与严格 close order。
- `dayu/host/command.py`、`dayu/host/dispatch.py`：active cancel 改用最小 typed port；bridge failure 不再被 command owner吞掉；新增显式 no-worker cancel port。
- `dayu/host/__init__.py`：导出 `HostAdmin`、`OpenHostAdminOptions`、`open_host_admin`，未增加 compatibility alias / wrapper。
- `dayu/service/host_admin.py`、`dayu/service/__init__.py`：新增只加载 `host_runtime.json` 的 Service admin assembly，不加载 model / execution profile / lane / tool / scene / secret。
- `dayu/cli/commands/session.py`：list / purge 与 resume selector resolution 路由到 admin opener；resume execution 仍使用 `open_host`；参数与输出未改。

### Tests

- 新增 `tests/host/test_durable_actor.py`、`tests/host/test_public_host_admin.py`、`tests/service/test_host_admin.py`。
- 更新 actor / bridge / close / package export / public session / purge / storage / watch / CLI tests，使断言迁移到 capability owner。
- 按 controller 窄范围扩展，`tests/host/test_public_lifecycle_smoke.py` 只删除过期 execution purge closed-handle 断言及其唯一 import/helper；等价 `HostAdmin` closed-handle 行为已由 S2 admin tests 覆盖。
- `tests/host/test_import_boundary.py` 补入 S1 accepted `_runner_call_manifest.py` 的 Engine-contract allowlist，令本轮规定 focused pytest 的 import-boundary 项恢复与 S1 accepted code 一致。

### Docs

- 更新 `docs/host/design.md`、`dayu/host/README.md`、`dayu/README.md`、`tests/README.md`。
- 未修改 root README：CLI parser、参数、输出格式、工作区路径与最终用户工作流未变化。
- 未修改 control doc、R3-F README 或配置 schema / overlay。

## Required counterexamples

1. `test_real_session_list_succeeds_without_model_api_keys` 与 `test_real_session_purge_succeeds_without_model_api_keys` 使用真实 Service / CLI，在八类 model API key 全部缺失时成功；admin integration seed `accepted` / `queued` / `recovering` Run，list 与被拒 purge 前后 Run、EventLog、host-instance count 与 status 分布完全相同。admin options 不含 lane / worker，相关 execution call count 为零。
2. `test_admin_list_and_rejected_purge_do_not_start_execution_or_mutate_runs` 把 scheduler open / recovery scan 替换为 fail-fast oracle，真实 `open_host_admin` 仍成功；`ServiceHostAdminRequest` 仅加载 host runtime；handle 无 ensure / submit / cancel / watch。
3. package export 测试证明 `Host` / `HostAdmin` 都直接继承 `Protocol`、互不继承；execution 不含 list / purge / storage admin，admin 不含 execution / cancel / watch；无 compatibility alias。
4. actor fixture 使用真实 SQLite，记录 handle create / connection use / handle-store close thread id完全一致且不同于 opener thread；scheduler store connection identity 不同，两者 journal mode / busy timeout / foreign key PRAGMA 一致。SQLite 默认 thread check 使 live connection 跨线程会直接失败。
5. 外部 connection 持有 `BEGIN IMMEDIATE`，public ensure 已进入 actor busy path 后，`asyncio.Event` + `call_soon` barrier 证明 opener loop 确定性前进且 command 未完成；释放锁后 command 成功。另一个 owner test 证明 ensure / submit / get_run / watch cursor 全部在同一个 actor thread，不以 sleep 次数作为 oracle。
6. caller 在首个 actor operation 开始后取消，底层 future 在 barrier 释放后继续完成；第二个 call 随后成功，记录顺序严格为 first-start、first-end、second。
7. active cancel bridge 从非 loop thread 调用后，cancellation token、`LocalWorkerHandle.on_cancel()` 与 `asyncio.Event.set()` 全部发生在 opener loop thread；loop callback 异常经 actor 返回原 caller，actor 随后的 call 仍成功。
8. actor command / scheduler wake 被 barrier 阻塞时启动 execution close，scheduler close 尚未发生；释放后 command+wake 收口，记录顺序严格为 scheduler、projection、actor handle、actor store、executor、scheduler store。admin close 只关闭 actor chain，重复 close 后无 `open-host-admin` worker thread 残留。

## Validation

### Passed

- 规定 focused pytest：`417 passed, 3 warnings in 10.20s`。warnings 均来自 edgartools deprecated import，与本 slice 无关。
- 规定全量 pyright：`0 errors, 0 warnings, 0 informations`。
- Source scan：CLI list / purge 与 resume selector 命中 `open_host_admin`；prompt / interactive resume execution 命中 `open_host`。
- Source scan：`open_host.py` 不再由 public handle 直接持有同步 command handle；仅 wait poller 的 thread-private resolver / closer 保留 `_command_handle`，其 store 在 poller thread 创建并关闭，不搬运 actor connection。
- Source scan：`_durable_actor.py` 明确命中 `ThreadPoolExecutor(max_workers=1)`、`Callable[[HostCommandHandle], T]`、typed `Future`；`open_host.py` 明确命中 `call_soon_threadsafe` 与 typed bridge future。
- `git diff --check`：通过。

## README decision

- `dayu/host/` public contract、actor ownership、bridge 与 close order发生变化，已更新 `dayu/host/README.md`。
- Service / Host 跨层装配边界变化，已更新 `dayu/README.md`。
- 测试边界新增 actor / admin contract，已更新 `tests/README.md`。
- 根 README 的用户可见参数、输出、命令与排障方式未变化，不更新。

## Residual risk / uncovered area

- `covered by later approved slice`：S3-S5 的 scheduler health / admission lease、recovery batching、active-cancel watchdog event / classification 与 deferred cancel state 扩展均未进入本 slice。
- 本 slice 的四个技术 stop condition均未触发：admin 未启动 execution side effect；没有 connection 跨线程；Event barrier 在数据库锁期间确定性推进；scheduler 不会在 actor wake 收口前关闭。
- 无未分类 residual risk，无 blocking open question。

## Artifact path

`docs/reviews/wu-semantic-ownership-01-round3-r3-a-s2-implementation-codex.md`
