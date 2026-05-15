# PR 54 Additional Review Controller Adjudication

## 结论

Controller 裁决：**PR 54 追加 review gate 暂不通过，需要一轮 accepted fix + re-review**。

本轮纳入两份追加并行 PR review：

- `docs/reviews/pr-54-review-20260515-1221.md`
- `docs/reviews/pr-54-review-20260515-1224.md`

GitHub PR 在线 review / comments / review threads 当前仍为空；本轮问题全部来自本地 review artifacts。PR 仍保持 draft，不进入 ready-for-review。

## Accepted Current Fix Items

| ID | 来源 | 裁决 | 修复要求 |
| --- | --- | --- | --- |
| A1 | `1224` F1 | accepted-blocking | `_consume_worker_events` 必须把 envelope / ingestor 构造、`handle.local_worker_id` 读取与事件循环统一纳入 `try/finally`，确保任何前置异常都 unregister active worker、close handle、release lane token。补测试覆盖 try 前异常路径。 |
| A2 | `1224` F3 | accepted-blocking | preview event 分类必须同时校验 `event.type` 与对应 `data` 类型；`data=None` 或错误 data 类型必须被 rejected diagnostic，而不是写入残缺 preview payload。补负例测试。 |
| A3 | `1224` F6 | accepted-blocking | RunInputBuilder 读取 current facts 时必须校验 Run / Attempt / dispatch record 处于可 dispatch 状态，至少要求 Run `RUNNING`、Attempt `STARTING`、dispatch record 为 `DISPATCHING` 且 identity 与 snapshot 一致；终态 / cancelled / pending misuse 必须 fail fast。补单测。 |
| A4 | `1224` F7 | accepted | `AttemptDispatchSnapshot.__post_init__` 必须拒绝 `cancellation_token is None`，避免 None token 进入 Engine。补单测。 |
| A5 | `1224` F5 | accepted | `_run_mutation_result_for_active` 在 rowcount=0 且最新 Run 已为终态时应返回 `CAS_LOST`，不是 `INVALID_STATE`。补低层 state 测试。 |
| A6 | `1221` F3 | accepted | `_validate_terminal_input` 必须把 terminal event type helper 的 `ValueError` 统一转换为 `HostDurableError`，满足函数异常契约。补测试。 |
| A7 | `1224` F9 | accepted | `HostDispatchScheduler.close()` 不应直接二次 close active handle；close 只发送 cancel signal 并取消 active task，资源释放由 `_consume_worker_events` 的 finally 负责。补测试或调整既有测试覆盖单次 close ownership。 |
| A8 | `1221` F10 | accepted | `_DefaultLocalWorkerHandle.close()` close 后清空 `_events` 引用；close 后再次读取 events 应 fail fast 或保持明确不可用语义。补单测。 |
| A9 | `1221` F1 | accepted | 补充 LocalProxy 真实 Engine 边界错误路径测试：`run_agent_messages` 抛异常、空 stream，以及 scheduler 经真实 proxy 映射 stream error 为 LOST 的路径。 |
| A10 | `1221` F8 | accepted | Host import boundary test 应禁止 `dayu.host` 导入 `dayu.config`，因为 Phase 5 design 明确 RunInputBuilder / Host 不得隐式读取全局配置或环境变量。 |

## Rejected With Reason

| 来源 | 裁决 | 理由 |
| --- | --- | --- |
| `1224` F2 active cancel closeout 更新 dispatch record 为 cancelled | rejected | 设计真源明确：dispatch record `dispatching` 在 WorkerProxy accepted 后保持为最终非取消诊断状态；active truth 是 `ATTEMPT_RUNNING` / Attempt row `RUNNING`，terminal truth 是 Attempt / Run terminal facts。将 worker-accepted dispatch record 改为 `cancelled` 会违反 P5 schema 中 cancelled 分支要求 worker accept refs 为 `NULL`，也会把 dispatch record 误用为 owner truth。 |
| `1224` F8 非 terminal duplicate detection 缺失 | rejected | EventLog 设计与实现均以全局唯一 `event_id` 作为 ledger identity；重复同 body digest 不追加第二行，不同 digest 抛 identity conflict。非 terminal event 已受 EventLog append 幂等保护，不需要在 ingest 层复制一套 duplicate precheck。 |
| `1221` F7 已取消 token build 短路 | rejected | Phase 5 的 cancellation token 是 Host 注入 Engine 的观察信号，不是 RunInputBuilder 的 build 前置。取消事实应由 durable Run / Attempt 状态和 active cancel path 表达；builder 不应基于 token 本地状态绕过 durable truth。 |

## Deferred / Owner

| 风险 | 裁决 | Owner |
| --- | --- | --- |
| worker 收到 cancel 后长期不产出 terminal | non-blocking | Phase 11 lifecycle / recovery hardening；P5-S5 已记录 active cancel watchdog 未实现。 |
| `_drain_loop` 非预期异常结构化日志 | non-blocking | 后续 observability / lifecycle cleanup。当前 `wake_dispatch` 可重建 drain task；不影响 P5 状态机真源。 |
| terminal event sub-index plan 去重结构化 | non-blocking | 后续 ingest cleanup；当前测试和 event id 唯一约束覆盖功能正确性。 |
| scheduler 并发 lane 竞争专项测试 | non-blocking | 后续 scheduler hardening；runtime lane 已有容量测试，当前 scheduler drain 是单队列串行推进。 |
| command.py active cancel port 抽象 | non-blocking | Phase 11 / composition lifecycle；当前单 scheduler singleton 是 P5 局部装配权衡，不扩大为 PR blocker。 |
| 多 RUN_CANCELLING 与具体 cancel request 关联 | non-blocking | 后续 Engine contract refinement；需要 Engine 事件携带明确 cancel request ref。 |
| duplicate helper / payload helper 抽取 | non-blocking | 后续 cleanup；本轮不做无行为收益的重构。 |
| `admission.py` / `run_input.py` EventLogStore DI 一致性 | non-blocking | 后续 cleanup；当前 EventLogStore 为无状态 primitive wrapper。 |

## 当前 Gate

进入 PR 54 additional review accepted-fix gate。修复完成后必须：

1. 运行受影响测试与 `pytest tests/host tests/runtime -q`。
2. 运行 `python -m pyright dayu/ tests/ utils/`。
3. 按触发规则同步 `dayu/host/README.md` 与 `tests/README.md`。
4. 形成 fix artifact，随后由至少两名 review Agent 做 re-review。
5. Controller 再次裁决并写回 `docs/host/implementation-control.md`。
