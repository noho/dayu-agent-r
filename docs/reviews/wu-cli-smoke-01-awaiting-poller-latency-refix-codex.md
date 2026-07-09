# WU-CLI-SMOKE-01 awaiting poller latency narrow re-fix 记录

## Gate

- Gate：narrow re-fix
- Work unit：`wu-cli-smoke-01-awaiting-poller-latency`
- 输入 artifact：
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-fix-codex.md`
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-review-ds.md`
- 本轮 artifact：`docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-refix-codex.md`

## 第一性原理判断

DS F-1 成立。`WaitPoller._release_not_ready(...)` 已把正常运行中的外部 job 写成 `poll_next_observe_at = now + not_ready_observe_interval_seconds`，但 supervisor 在本轮有活动时固定按 `poll_interval_seconds` sleep。若 `not_ready_observe_interval_seconds < poll_interval_seconds`，wait record 已经 due，但 loop 仍被较长的 poll interval 拖慢，形成配置契约断层。

DS F-2 成立但只需要测试侧窄修。原测试把 `_ManualClock` 写入 durable due 时间，同时让 background thread 通过真实 `threading.Event.wait(...)` 睡眠，两个时间源不同步，存在调度竞态。为这个测试新增生产 sleeper port 会过度设计；更合适的是把可确定的 due / claim cadence 用 `drain_once_for_test()` 单线程验证，再用真实 UTC clock 做 background 行为覆盖。

DS F-3 本轮不修。空轮询多一次 next-due DB 读是低优性能优化，当前 idle interval 已让净 QPS 下降；后续若需要优化，可把 claim miss 与 next due 合并进同一 durable read。

## 修改

- `dayu/host/wait_adapter.py`
  - 新增内部 `_ReleaseNotReadySummary`，让 not-ready release 成功时把本轮可推导的下一次观察 delay 返回给 `WaitPollOnceResult.next_poll_delay_seconds`。
  - `_next_loop_interval_seconds(...)` 在本轮有活动时也消费 `result.next_poll_delay_seconds`；因此 `not_ready_observe_interval_seconds < poll_interval_seconds` 时，下一轮 poll 按 not-ready interval 唤醒。
  - 保留无活动时的 idle / next-due 上限逻辑，不引入 Fins-only 特判，不改变错误 backoff、idle no-active wait、wakeup 或空日志抑制语义。
- `tests/host/test_wait_poller_runtime.py`
  - 把 `test_pure_poll_observes_ready_after_not_ready_policy_cadence` 改为单线程 `drain_once_for_test()`，验证配置不等时 not-ready result 携带 policy delay，提前 drain 不会 claim，推进 manual clock 后可 resolve。
  - 新增 `test_background_loop_uses_not_ready_due_before_poll_interval`，使用真实 UTC clock 验证 `not_ready_observe_interval_seconds=0.01`、`poll_interval_seconds=0.5` 时第二次 poll 不被 0.5 秒 poll interval 拖慢。

## README 决策

- 已检查 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。
- `dayu/host/README.md` 与 `docs/host/design.md` 已在上一轮描述：有 active wait 但未到 next-observe / claim expiry 时，supervisor 睡眠到下一次 due 或 idle 上限。
- `tests/README.md` 已描述 wait poller policy cadence 覆盖。
- 本轮只是让实现符合既有文档语义，不需要新增 README 文本。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_wait_poller_runtime.py -q`
  - 结果：`16 passed`。
- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py -q`
  - 结果：`36 passed`。
- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_open_host_runtime.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_interactive_command.py -q`
  - 结果：`152 passed, 3 warnings`；warnings 来自 `edgar` 依赖 deprecation。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`
  - 结果：通过，无输出。

## Finding 状态

- DS F-1：已修复。
- DS F-2：已修复。测试不再混用 ManualClock 与后台真实 sleep；新增后台覆盖使用真实 UTC clock。
- DS F-3：deferred，assigned to later work unit。当前不阻塞本轮 narrow re-fix。

## 残余风险

- 真实 SEC / Fins 网络 smoke 仍未在本轮重复执行，原因是本轮范围是 Host poller narrow re-fix；该风险沿用上一轮 artifact，assigned to manual/real smoke validation。
- 空轮询 next-due 额外 DB 读仍存在，classified as assigned to later work unit；当前净 QPS 下降，非 correctness blocker。
- background timing 测试仍依赖本机线程调度，但使用同一真实时间源，且阈值低于 `poll_interval_seconds`，用于捕获 DS F-1 回归；主要 correctness 断言由单线程 drain 测试覆盖。

## 完成状态

narrow re-fix 完成；未 commit、未 push、未开 PR。
