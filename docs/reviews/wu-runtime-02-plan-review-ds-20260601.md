# WU-RUNTIME-02 Plan Review Artifact

- **Reviewed target**: `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Review role**: plan review specialist (DS)
- **Review date**: 2026-06-01
- **Timestamp**: 20260601-065552
- **Branch**: `fix/wu-runtime-02-lane-clock-cancellation`

## Review Scope

审查 plan 是否 code-generation-ready，重点裁决：

- 动机是否由代码直接证据支撑，严重性是否准确。
- TTL 时间真源选择是否为当前 phase 最佳实践，是否过度设计或不足。
- bounded cancellation cleanup 的语义是否清楚、可实现、可测，是否会引入 claim 泄漏、未消费异常、错误标记 released/lost 或吞取消。
- slices 是否足够小，allowed files / non-goals / stop conditions / tests 能否直接交给 implementation agent。
- 是否遗漏 pyright、README 触发判断、runtime import boundary、中文 docstring、禁止 Any/object/无类型签名等项目约束。

## Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|-----------|----------|---------|
| A1 | `_LaneClock.now()` 使用 monotonic anchor 推导 UTC，可导致跨进程 TTL 漂移 | `lane.py:327-334` — `elapsed_seconds = time.monotonic() - self.monotonic_anchor` + `utc_anchor + timedelta(seconds=elapsed_seconds)` | **成立** |
| A2 | `_await_task_after_outer_cancellation()` 在 `while True` 中无限等待 shielded task | `lane.py:1017-1023` — 循环体无最大等待时间、无 timeout、无退出条件（除 task done） | **成立** |
| A3 | 已有测试覆盖 repeated cancel cleanup、release/refresh cancel 后等待底层结果、close during slow acquire | `test_lane.py:397-437` (yields before retry), `test_lane.py:440-486` (refresh waits for shielded), `test_lane.py:488-533` (refresh cancel cleanup marks lost), `test_lane.py:703-746` (repeated cancel during claim cleanup) | **成立** |
| A4 | 多进程测试覆盖 capacity invariant、non-blocking timeout、release 后 acquire、crashed holder TTL cleanup | `test_lane_multiprocess.py:223-258` (capacity invariant), `test_lane_multiprocess.py:262-279` (nonblocking timeout + release), `test_lane_multiprocess.py:282-306` (crashed holder TTL cleanup) | **成立** |
| A5 | plan 声称不改变 public API、DB schema、Host truth | Plan §Non-goals 与 §Contract / Schema / Public API 章节 | **一致** |
| A6 | plan 声称 forbidden files 不包含 `dayu/engine/**`、`dayu/host/**` 等业务层 | Plan §Forbidden files for implementation | **一致** |

## Architecture Boundary Review

- **Layering**: plan 明确只修改 `dayu/runtime/lane.py`，不触碰 Host/Engine/Service/UI/Fins 层。`_LaneClock` 是私有实现类，`_await_task_after_outer_cancellation` 是模块级私有函数，修改不穿透 runtime 边界。
- **Dependency direction**: 不新增任何 import；不引入 Host truth、EventLog、Attempt owner 或业务语义。符合设计真源 §3.1 line 239 的 import boundary 约束。
- **Public contract**: `__all__` 不变；`LaneController.acquire()`、`LaneClaimToken.refresh()`、`LaneClaimToken.release()` 的 public 签名和语义不变。plan 明确拒绝新增 public API。
- **Schema boundary**: `runtime_lane_claims` 表结构不变；SQLite text 比较语义（ISO-8601 microseconds）不变。
- **Verdict**: 架构边界未被穿透，无跨层泄漏。

## Best-Practice Review

- **TTL time source**: Option A（每次 SQLite 短事务前读取 `datetime.now(UTC)`）是这一层可维护的最小 root cause 修复。对比 Option B（SQLite 时间真源），避免了把 datetime 格式/精度/TTL 加法推入 SQL，减少了 brittle SQL 风险。符合项目"最小化满足需求"的架构约束。
- **Cancellation cleanup bound**: `busy_timeout_seconds + _OUTER_CANCELLATION_CLEANUP_GRACE_SECONDS` 作为上限是合理的工程权衡——它利用了 SQLite 自身的 busy timeout 作为底层等待上限，外加 0.25s Python 层余量。保留 TTL stale cleanup 作为兜底，不假装在 timeout 后能确定 DB 状态。
- **Test design**: 测试使用 `threading.Event` 做同步（而非 sleep），符合项目既有测试模式。monkeypatch 私有方法的方式与现有测试一致。

## Overengineering Review

- plan 明确拒绝：SQLite 时间真源、可注入 public clock、强制杀死 Python thread、后台 recovery worker、cleanup timeout 提升为 Host cancel/recovery 事件。每项拒绝都有合理的"why not"说明。
- 不新增 callback/factory/profile/query/extra payload 接口，符合项目约束。
- 不顺手重构 `LaneController` 为多个类，不处理 `LaneClaimToken.released` public field。

## Overcoupling Review

- Slice 1 和 Slice 2 各自只修改 `dayu/runtime/lane.py`（及对应测试文件），不跨模块。两个 slice 有明确依赖关系（Slice 2 依赖 Slice 1 完成），但不共享可变状态。
- 私有 helper 的职责边界清晰：`_LaneClock` 只改 UTC 方法；`_await_task_after_outer_cancellation` 只改等待上限；新增 private observer 只消费 late result/exception。

## Findings

### F1-未修复-低-设计真源中 monotonic-to-wall 表述将变陈旧

- **位置**: Plan §Design Decision 1；设计真源 `docs/host/design.md` line 222
- **问题类型**: 契约缺失
- **当前写法**: Plan 选择 Option A（真实 UTC wall clock per transaction），删除 `_LaneClock` 的 monotonic-to-UTC anchor。设计真源 line 222 当前写 "clock 使用 runtime injected / stdlib monotonic-to-wall strategy 必须保证同一 process 内 TTL 计算一致"。
- **反例/失败场景**: 若后续 reader 对照设计真源读代码，会发现实现与真源描述不一致，可能误判为 bug 或引发不必要的"修正"。
- **为什么有问题**: 设计真源中该句是对 Phase 1 实现策略的描述，非架构不变量；但 plan 未提及是否需要同步更新设计真源。
- **直接证据**: `docs/host/design.md:222`
- **影响**: 文档与实现不一致，后续维护者困惑；不影响代码正确性。
- **建议改法和验证点**: plan 应在本 WU non-goals 或 open questions 中注明：实现完成后需将设计真源 line 222 更新为 "clock 使用真实 `datetime.now(UTC)` per SQLite transaction" 或等价表述。若 controller 认为不需要，也应在 plan review 裁决中明确。
- **修复风险（低）**: 一行文档修改。
- **严重程度（低）**: 不阻塞 implementation——代码行为正确是最优先的，文档同步可在 implementation 完成时一并处理。

## Open Questions

1. **设计真源同步时机**: F1 提到的设计真源 line 222 更新，是跟随本 WU 实现同步修改，还是作为独立 follow-up？
2. **Observer 实现机制**: Plan 要求"注册 done callback 或等价 observer"，但未指定具体机制（`task.add_done_callback()` vs fire-and-forget wrapper）。implementation agent 需自行选择并在测试中证明不泄漏未取回异常。当前 plan 的测试描述足够支撑这个判断。

## Residual Risks

| Risk | Severity | Mitigation | Tracking |
|------|----------|------------|----------|
| Wall clock 被人为大幅调整后 runtime capacity availability 受影响 | 低 | 符合设计真源边界：lane TTL 不是 Host truth；单机 runtime capacity primitive 可接受的 availability 风险。Plan 已明确记录。 | 无需额外追踪 |
| Cleanup timeout 后底层 thread 稍后成功但 late claim 尚未被 release，依赖 TTL cleanup 兜底 | 中 | Plan 明确要求 observer 消费 late result/exception 并记录诊断；TTL cleanup 是已有机制，有 `test_crashed_holder_is_cleaned_by_ttl` 证明。 | 实现后验证 observer 测试覆盖 |
| `busy_timeout_seconds` 配置极大（如 120s）时 cleanup timeout 也相应增大 | 低 | 当前默认 5s，实际使用由 Host construction 控制；比无限等待已是严格改进。 | 无需额外追踪 |
| 新 cancellation tests 中线程/事件同步可能引入 flakiness | 中 | Plan 已要求使用 `threading.Event` / explicit timeout config，不得依赖随机 sleep；所有阻塞线程必须在测试结束前释放。Stop condition 明确：若测试依赖不可控 sleep 或留下悬挂 thread/task，停止并重新设计。 | 实现后运行多次验证 |

## Conclusion: PASS

Plan 是 code-generation-ready。动机由代码直接证据支撑，严重性判断准确。两个 Design Decision（真实 UTC wall clock per transaction，bounded cancellation cleanup with TTL fallback）都是当前 phase 正确的最小可行方案。Slices 足够小且各自有明确的 allowed files、exact changes、tests、non-goals 和 stop conditions，可以直接交给 implementation agent。

无 blocking finding。F1（设计真源陈旧表述）为低严重度文档同步问题，不阻塞 implementation。

唯一建议：controller 裁决 F1 中文档同步的时机（跟随本 WU 实现 / 独立 follow-up），并将裁决结果写入 plan 或 control doc。
