# Host Phase 8 Plan Fix - Codex - 2026-05-16

## Gate

当前 gate：Phase 8 plan fix。

Plan artifact：

- `docs/host/phase8-projection-core-event-stream-plan.md`

Fix truth：

- `docs/reviews/host-phase8-plan-review-controller-adjudication-20260516.md`

Allowed write scope：

- `docs/host/phase8-projection-core-event-stream-plan.md`
- `docs/reviews/host-phase8-plan-fix-codex-20260516.md`

## Motivation Check

P8-PLAN-F1 至 P8-PLAN-F7 的动机成立。它们都指向 plan 中会让 implementation agent 临场补契约的缺口，尤其是 checkpoint 原子性、per-class filter 语义、RunResult 冲突处理、repair batch 边界和 wakeup lifecycle。修复方式选择收紧 Phase 8 的可实施契约，不进入 production code、tests、README、design 或 control doc。

## Changes

- P8-PLAN-F1：删除“等价原子性”逃生路径，要求 checkpoint advance 与 projection writes 在同一个 `HostTransactionRunner.run_write()` transaction 内提交，并声明幂等 upsert 不能替代事务原子性。
- P8-PLAN-F2：将 filter contract 改为 `ProjectionEventClassFilter` + `ProjectionEventFilter(class_filters)`，固定 per-class type 语义，并新增多 class + type 组合测试要求。
- P8-PLAN-F3：明确 RunResult consumer 必须先按 `run_id` 读取既有 row；terminal identity 不同时 raise projection error，checkpoint 不推进；禁止 `INSERT OR REPLACE` 和静默 overwrite。
- P8-PLAN-F4：把 repair 改为 reset 短事务 + batch replay 两阶段；每批独立 transaction 推进 checkpoint，中途失败后从最后成功 checkpoint 继续。
- P8-PLAN-F5：明确 `ProjectionRunner` 构造时注入 `HostTransactionRunner`，不得自建 SQLite connection 或持有 public command facade；Phase 8 不强制 after-commit wakeup，自动追平 deferred 给 Phase 9 Conversation Memory composition owner。
- P8-PLAN-F6：把 fanout / wakeup 固定为可选 non-truth optimization；P8-S2 不要求 fanout shell，测试命名改为验证 `stream_run_events` 不依赖 projection 或 notification side effects。
- P8-PLAN-F7：新增 P8-S1 schema stop check，要求 `event_log(event_sequence)` 是合法 FK target 或使用经测试的合规方案；新增 P8-S3 payload stop check，`USER_INPUT_ACCEPTED` 无 typed `display_text` 时不得从 raw payload 拼文本。

## Validation

- Preflight：当前分支为 `feat/host-phase8-projection-core-event-stream`。
- Scope check：仅修改允许的 plan artifact，并新增允许的 Codex fix artifact。
- `git diff --check -- docs/host/phase8-projection-core-event-stream-plan.md docs/reviews/host-phase8-plan-fix-codex-20260516.md`：通过，无输出。
- 未跟踪文件补充检查：分别执行 `git diff --check --no-index /dev/null <file>`；两次命令均无 whitespace warning 输出，退出码 1 为 no-index 内容差异的预期 diff 退出码。

## Residual Risk

无新增 blocking open question。Phase 8 自动 after-commit projection catch-up 已明确 deferred 给 Phase 9 owner；Phase 8 implementation 只交付 runner / checkpoint / minimal read model / repair primitive。
