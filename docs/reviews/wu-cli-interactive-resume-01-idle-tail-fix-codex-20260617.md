# WU-CLI-INTERACTIVE-RESUME-01 idle-tail fix

- Gate: fix
- Work unit: `WU-CLI-INTERACTIVE-RESUME-01`
- 日期: 2026-06-17
- 状态: implemented；未提交
- Finding: controller 指出 `startup_reconnect_entrypoint_session` 在 `_observe_startup_active_and_queued_runs` 读到 idle `SessionSnapshot` 后直接返回，若 terminal 已提交但尚未进入 watcher queue、且不在初始 outbox backfill 中，会丢失 startup terminal。

## 裁决

Finding 成立。直接代码证据是 idle 分支在 `active_run_id is None` 且 `queued_run_ids` 为空时直接 `return`；而 session-scoped outbox backfill 只在进入 active/queued 观察循环前执行一次，不能覆盖初始 backfill 与 idle return 之间的 tail window。

## 修复

- 在 Service 内部新增 idle-tail closure：idle snapshot 后再次从当前 `OutboxTerminalCursor` 做 session-scoped outbox backfill，再 drain 已到达 watcher terminal items。
- 若 tail outbox 或 tail watcher drain 发现 terminal，则追加结果并重新读取 Session snapshot，避免 terminal 后还有 active / queued 状态变化。
- 若 tail watcher drain 首次发现 watcher failure，即使未发现 terminal，也重新进入循环并再次走 tail outbox；后续 outbox terminal 会携带 watcher failure 诊断。
- 未修改 Host / Engine public API，未读取 Host durable internals。

## 测试与文档

- 新增 service 回归覆盖 idle snapshot 后 tail outbox 返回 terminal，断言不会进入输入态前丢失 terminal，并验证 cursor 从当前状态继续推进。
- 新增 service 回归覆盖 tail drain 首次发现 watcher failure 后会再次通过 outbox tail 关闭缺口。
- 更新 `dayu/service/README.md` 与 `tests/README.md` 中对 startup reconnect / entrypoint runtime 测试覆盖的描述。

## Residual Risks

- fixed in current slice: controller 指出的 idle snapshot terminal gap。
- fixed in current slice: tail watcher failure 后静默返回 idle 的风险。
- uncovered areas: 真实多进程 Host watcher/outbox 时序由 Host public API 与既有 watch/outbox 测试覆盖；本 fix gate 只新增 Service 级时序回归。
