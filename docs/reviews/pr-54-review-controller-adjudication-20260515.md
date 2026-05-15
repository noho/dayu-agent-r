# PR 54 Review Controller Adjudication

## 结论

Controller 裁决：**PR 54 退出 ready 状态，进入 PR review fix gate**。

用户说明已有 3 份手工 PR review；当前工作区与 GitHub API 可见证据中只找到 2 份：

- `docs/reviews/pr-54-review-20260515-1056.md`
- `docs/reviews/pr-54-review-20260515-1102.md`

GitHub PR API / thread-aware fetch 均返回 0 个线上 review、comment、review thread。第三份 review 暂记为 **missing evidence**；如后续出现，必须作为追加 PR review gate 继续处理。

## 输入证据

- PR：`https://github.com/noho/dayu-agent-r/pull/54`
- 设计真源：`docs/host/design.md`
- 总控文档：`docs/host/implementation-control.md`
- Phase 5 plan：`docs/host/phase5-runinputbuilder-local-dispatch-plan.md`
- 手工 review artifacts：
  - `docs/reviews/pr-54-review-20260515-1056.md`
  - `docs/reviews/pr-54-review-20260515-1102.md`

## 总体裁决原则

- correctness / state-machine / lane release / EventLog idempotency / terminal closeout finding 默认当前 PR 修复。
- 纯测试缺口如果覆盖当前 Phase 5 已实现路径，当前 PR 修复。
- 明确属于 Phase 6 / 7 / 9 / 10 / 11 / 13 / 14 的后续能力，不夹带实现，但必须保留 owner。
- 与 `HostCommandHandleOptions.local_execution` 装配相关的问题需要先做 root-cause 判断：当前公共 factory 是同步 API，而 scheduler open 是 async；若无法在不破坏公共边界的情况下正确实现，必须作为 blocking design gap 写明，而不是做局部胶水。
- schema v2 -> v3 旧库迁移不修复；项目约束是 fresh schema 起库，不做旧库兼容读取。

## Accepted Fix Items

### A1. Dispatch / lane / worker lifecycle consistency

来源：
- 1056 F1 / F5 / F6 / F12
- 1102 F2 / F3 / F9 / F10 / F11 / F13

裁决：**accepted current PR fix**。

必须修复：
- lane acquire timeout / worker startup timeout 不得留下 orphan dispatch record。
- `worker.accept()` 非 `TimeoutError` 异常必须释放 lane 并收口。
- lane acquired 后的 `CancelledError` / exception path 必须保证 lane token release。
- `handle.close()` / `handle.cancel()` exception 不得阻断其它 handle、task、lane controller 清理。
- `_consume_worker_events` 中 `ingestor.ingest()` 异常必须收口为 worker lost 或等价 terminal closeout，不得让 Run 永久 `RUNNING`。
- `cancel_starting_dispatch_record_row` 对已 `CANCELLED` dispatch record 应幂等吸收为 CAS-lost 类结果，而不是 `INVALID_STATE`。
- `_run_mutation_result_for_active` 的 active CAS-lost 分类必须与 active Run 集合一致，覆盖 `CANCELLING` / `RECOVERING`。
- `_is_dispatchable_recheck` 与 plan 对齐，接受 `pending` 或 `waiting_for_lane`，前提是底层 CAS helper 也支持对应安全迁移。

### A2. Engine ingest idempotency / lifecycle mapping

来源：
- 1056 F4 / F11
- 1102 F1 / F4 / F12 / F21

裁决：**accepted current PR fix or explicit design rejection with tests**。

必须修复或形成可审计裁决：
- `RUN_SUSPENDED` / `TOOL_AWAITING` 首次处理和重复处理必须有测试；重复 candidate 不得追加噪声 diagnostic。
- `close_worker_lost` 的 duplicate detection 与 `engine_event_ref` 不得把 lost 误标为 `run_failed`。
- `PROVIDER_PROTOCOL_ERROR`、preview、terminal 后迟到事件、无前置 active cancel 的 `RUN_CANCELLED`、unsupported event type 必须有测试。
- `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 在 Phase 5 no-tool boundary 下的处理必须明确：若作为 preview 接受，需结构化 payload 与测试；若继续拒绝，需以 design / plan non-goal 为依据并保留 Phase 6 owner，不能静默丢 trace。
- 可恢复 `RUN_FAILED` diagnostic 与 closeout 的事务原子性需修正或证明当前行为不会提交孤立 diagnostic。

### A3. RunInputBuilder message semantics and leakage

来源：
- 1056 F3 / F7
- 1102 F5 / F6 / F15

裁决：**accepted current PR fix except retry/replay failure-context projection may defer with owner**。

必须修复：
- 失败 / 取消 / 丢失 Run 不得在 continuity 中留下孤立 `UserMessage`。
- system message 不得泄漏 Host 内部 `attempt_id` / `execution_id`。
- no-tool executor cancellation-token 合规性可作为低风险当前 PR 修复。

可 deferred：
- retry / replay 中是否投影失败上下文属于后续 retry / recovery 语义；如不在当前 PR 实现，owner 为 Phase 11，代码或文档需避免误导。

### A4. Current Phase 5 test gaps

来源：
- 1056 F4 / F8
- 1102 F14 及 residual test gaps

裁决：**accepted current PR fix**。

必须补充：
- dispatch record 四状态 nullability 非法组合测试。
- Engine ingest 关键分支测试。
- dispatch exception / timeout / close cleanup 测试。
- `cancel_session_runs` 在 Phase 5 supported subset 上的集成覆盖。

### A5. Local execution public option root-cause decision

来源：
- 1056 F2

裁决：**accepted as blocking design / implementation question**。

Phase 5 plan 明确 `HostCommandHandleOptions.local_execution` 非 `None` 应连接本地 dispatch runtime；当前实现只校验字段但完全不消费，动机成立。由于 `create_host_command_handle` 是同步函数而 `HostDispatchScheduler.open` 是 async，禁止用不稳定事件循环胶水局部止血。Fix agent 必须给出以下之一：

- 可维护的最小正确实现，并补 public handle 集成测试；
- 或明确裁决为当前 PR blocking design gap，提出需要新增 async factory / composition root 的公共契约变更，并写入总控文档，PR 不得宣称 public handle 已支持 local execution。

## Rejected / Deferred Items

| Finding | 裁决 | Owner / 原因 |
| --- | --- | --- |
| 1102 F16 schema v2 -> v3 无迁移路径 | rejected | 项目约束要求 fresh schema 起库；不做旧库兼容读取 / 迁移。若 README 当前职责范围缺失 fresh schema 说明，可补文档，但不改 schema 行为。 |
| 1056 F9 `_validate_no_tool_snapshot` 重复校验 | deferred | 低风险清晰度重构，不阻塞 PR；可在后续 cleanup 中统一 no-tool policy validation。 |
| 1056 F10 事件类型常量重复 | deferred | 低风险重构；当前 PR 优先 correctness。后续如抽常量必须保持 durable 包内边界，不做兼容 re-export。 |
| 1102 F17 bool 校验不一致 | optional current fix | 低风险 API 防御；若顺手补测试可接受，否则不阻塞。 |
| 1102 F18 参数名混淆 | deferred | 维护性问题，不影响状态机正确性。 |
| 1102 F19 default worker handle cancel no-op | deferred with owner | 已在 Phase 5 residual risk 中归 Phase 11 / lifecycle hardening；当前可补文档或诊断，不要求实现强制中断。 |
| 1102 F20 events 生成器并发调用 | deferred | 非预期并发访问；当前 scheduler 单消费者。 |

## 修复派发

已派发 AgentCodex 作为 implementation / fix agent，要求写入：

- `docs/reviews/pr-54-review-fix-host-p5-local-dispatch-codex-20260515.md`

要求验证：

```text
pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_phase5_local_execution_integration.py tests/host/test_public_cancel_session_runs.py tests/host/test_state_schema.py -q
python -m pyright dayu/host tests/host
git diff --check
```

修复完成后必须由 AgentMiMo / AgentDS 做 PR review fix re-review，controller 再写 re-review adjudication，并更新 `docs/host/implementation-control.md` 与 PR branch。

