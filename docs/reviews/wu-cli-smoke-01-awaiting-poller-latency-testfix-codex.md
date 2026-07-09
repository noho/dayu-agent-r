# WU-CLI-SMOKE-01 awaiting poller latency test stability fix 记录

## Gate

- Gate：test stability fix
- Work unit：`wu-cli-smoke-01-awaiting-poller-latency`
- 输入 artifact：
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-rereview-ds.md`
- 本轮 artifact：`docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-testfix-codex.md`

## 第一性原理判断

MiMo finding 成立。`test_background_loop_uses_not_ready_due_before_poll_interval`
原先等待 `adapter.poll_count == 2` 后立即读取 durable wait record。`poll_count == 2`
只证明第二次 `adapter.poll_wait(...)` 已返回 ready，不证明后台线程已经完成
`resolve_wait(...)` command path，也不证明 wait record 的 terminal status 已提交到 durable
store。因此测试线程可能在 resolve 事务提交前读到 `WAITING`，这就是 10 次复跑 6 次失败的
直接原因。

DS pass 不能覆盖该证据，因为 DS 验证的是时钟源修复与 poll cadence 链路；MiMo 指出的失败点是
测试同步 primitive 与断言事实不同源。正确修复应让测试等待 durable truth，而不是等待 adapter
内部计数。

## 修改

- `tests/host/test_wait_poller_runtime.py`
  - 在 `test_background_loop_uses_not_ready_due_before_poll_interval` 中，把第二个等待条件从
    `adapter.poll_count == 2` 改为读取 DB wait record 并等待
    `WaitRecordStatus.RESOLVED`。
  - 保留 `elapsed_seconds < 0.3` 断言，用第二次 poll start 时间继续验证
    `not_ready_observe_interval_seconds=0.01` 时没有被
    `poll_interval_seconds=0.5` 拖慢。

本轮未修改生产代码，未回退 F-1 的生产修复。

## README 决策

- 已检查 `tests/README.md` 的维护约定和 Host 测试覆盖描述。
- 本轮只修正既有测试的线程同步条件，不新增测试层级、不改变运行命令、不改变测试职责描述。
- 因此不更新 README。

## 验证

- 重复运行目标测试 10 次：
  - 命令：`source .venv/bin/activate && for i in {1..10}; do pytest tests/host/test_wait_poller_runtime.py::test_background_loop_uses_not_ready_due_before_poll_interval -q || exit $?; done`
  - 结果：10/10 通过；每次输出均为 `1 passed`。
- 受影响测试矩阵：
  - 命令：`source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_open_host_runtime.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_interactive_command.py -q`
  - 结果：`152 passed, 3 warnings in 5.69s`。
  - warnings 来自 `edgar` 依赖 deprecation，不是本轮改动引入。
- 类型检查：
  - 命令：`source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`。
  - 额外提示：pyright 有新版本可用，不影响类型检查结果。
- diff whitespace：
  - 命令：`git diff --check`
  - 结果：通过，无输出。

## Finding 状态

- MiMo F-1：已关闭。
  - 关闭理由：测试现在等待 durable wait status `RESOLVED`，断言读取的事实与等待条件同源，不再把 adapter 内部计数误当成 resolve 提交完成信号。
- DS pass：保持有效。
  - 本轮没有改变生产 poller cadence、idle、wakeup、backoff 或 resolve path。

## 残余风险

- background timing 测试仍依赖本机线程调度来验证 `elapsed_seconds < 0.3`，但不再依赖调度顺序判断 durable terminal status；该风险 classified as accepted for current test purpose，因为单线程 `drain_once_for_test()` 测试已经覆盖主要 correctness，background 测试只捕捉实际 sleep cadence 回归。
- 真实 SEC / Fins 网络 smoke 本轮未执行，classified as assigned to manual/real smoke validation；本轮 scope 是测试稳定性修复，不触达 Fins 下载或真实网络路径。
- DS F-3 空轮询 next-due 额外 DB 读仍 defer，classified as assigned to later work unit；本轮不改变该性能取舍。

## 完成状态

test stability fix 完成；未 commit、未 push、未开 PR。
