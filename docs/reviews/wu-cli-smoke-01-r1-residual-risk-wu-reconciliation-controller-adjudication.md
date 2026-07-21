# WU-CLI-SMOKE-01-R1 Residual Risk WU Reconciliation Controller Adjudication

## Scope

- Gate: final-closeout residual-risk reconciliation correction。
- Trigger: 用户要求所有真实 remaining risk 必须经代码裁决后，以稳定 WU 形式进入主总控；可在当前 WU 正确关闭的事项不得 defer。
- Proposal: `docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-proposal-codex.md`。
- Dual reviews:
  - `docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-proposal-review-mimo.md`：accepted，0 blocking finding。
  - `docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-proposal-review-ds.md`：accepted，0 blocking finding；2 个 test-constant notes。
- Design truth: `docs/host/design.md` 与 `docs/engine/design.md`。
- Control truth: `docs/host/issues-implementation-control.md`；附加控制为 `docs/phaseflow-umbrella-optimization-control.md`。

## First-Principles And Current-WU-Fix Decision

“事实存在”不等于“仍有待修 risk”。当前 WU 只有在目标已成立、semantic owner 明确、最小实现能闭环、验收 oracle 可确定且不会推翻已冻结 contract 时，才应继续 implementation。AgentCodex、AgentMiMo、AgentDS 与 Controller 对五项逐条走读后均未发现满足该条件的 production/test gap。

因此本轮没有 current-WU implementation slice：

- live-only 补放和跨域可重放总序会引入新的 Host persistence/query contract，直接推翻 R1 的 transient/durable owner 裁决。
- 两个固定容量缺少代表性 workload、SLO、内存预算与生产失败数据；任意改常量或提前暴露 public knob 不能证明更正确。
- 可控 worker 是 deterministic failure-matrix oracle；真实 provider 无法稳定构造三类 delta、overflow 与 terminal 组合，且 R1 生产路径不包含 provider transport 改动。
- CLI R2 是 R1 之前已存在且需要产品 UX 选择的独立 feature，不是当前 PR regression。

## Five-Item Adjudication

| 来源项 | Controller 裁决 | current-WU-fix | 主总控处理 |
|---|---|---:|---|
| overflow、detach、断线、Host close/crash/restart 后不补放 | `rejected-with-reason` as remaining risk；accepted live-only contract boundary | no | 从 active residual 删除，不创建 WU；直接证据保留在 proposal/reviews。 |
| Host watcher 与 Service relay 固定容量 256 | `needs-more-evidence`，且两个 owner/失败域不能合并 | no | 拆为 `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01`，均 `deferred-with-owner`。 |
| durable 与 transient 无跨域可重放总序 | `rejected-with-reason` as remaining risk；accepted two-domain ordering contract | no | 从 active residual 删除，不创建 WU。 |
| R1 E2E 使用可控 worker | `rejected-with-reason` as remaining risk；accepted deterministic test boundary | no | 从 active residual 删除，不创建 WU；provider conformance 继续由既有 Engine/provider smoke owner。 |
| CLI thinking 160 字符单行表述 | `deferred-with-owner`；原文字失真 | no | 复用 `WU-CLI-SMOKE-01-R2`，修正为“每个 delta 160 截断后累计追加，累计行无明确上限/panel/history”。 |

## Capacity Ownership Decision

两个容量数值虽然都是 256，但不是同一业务事实：

- Host watcher 使用 `put_nowait`；满队列时只把该订阅标记 overflow 并 detach，owner 是 `HostTransientDeltaSubscription` / hub。
- Service relay 使用 `await queue.put`；满队列时 backpressure drain task，并可能让 Host watcher 进入 slow-consumer failure / Outbox terminal fallback，owner 是 `_WatchAndWaitRuntime` / `_drain_host_events(...)`。

两者的生产者、消费者、阻塞方式、错误传播、观测信号与验证矩阵均不同。共享常量、联动调参或合并成一个 WU 会制造跨层耦合；因此按 semantic owner 拆为两个 evidence-gated WU。

## DS Test-Constant Notes

### DS-F01：`tests/service/test_entrypoint_runtime.py` 直接断言 256

- `rejected-with-reason` as finding。
- 该断言是 Service owner-level exact contract oracle；如果改为导入生产 private constant，再断言由同一常量构造的 queue 等于该常量，会使测试自证实现，无法捕获容量 contract 的无意变化。
- 裸值位于单一、命名明确且 docstring 自解释的 exact expectation，不是生产业务规则的多处魔法真源；无需 current-WU-fix。

### DS-F02：CLI E2E 定义 `_SERVICE_RELAY_CAPACITY = 256`

- `rejected-with-reason` as finding。
- 该值已有 test-local 稳定名称，并用于构造第 257 个 pending item 的对抗边界；不是裸 magic number。导入 Service private 实现常量会让跨层 E2E 依赖下游实现细节。
- 无 semantic ownership drift，无 current-WU-fix。

## Control Write Decision

主总控必须同时写入：

1. Residual Risk Reconciliation 表中的三个 remaining WU；
2. Current Work Units 表中的同三个 WU；
3. 本 proposal、双路 review 与 Controller adjudication artifact；
4. final closeout artifact 中“保留三项、删除三项”的最终代码裁决。

附加总控的旧 baseline residual 概括必须同步替换，不能继续声称 live-only、cross-domain ordering 与可控 worker 是 remaining residual。

## Validation Accepted

- AgentCodex 与 Controller 均执行 owner/path regression：75 passed，3 个第三方 deprecation warnings。
- AgentCodex 与 Controller 均执行独立 transient stress：1 passed。
- AgentCodex 与 Controller 均执行全量 pyright：0 errors。
- AgentMiMo / AgentDS 双路对抗复核：accepted，0 blocking finding。
- Controller 直接复核 owner path、blame/diff、主总控状态值与 duplicate WU/Issue：pass。

## Decision

`accepted-residual-risk-WU-reconciliation`。当前 WU 无 implementation fix；真实 remaining risks 已收敛为两个 capacity evidence WU 与既有 CLI R2，全部以稳定 WU 形式进入主总控。三项 accepted/rejected boundary 不再作为 remaining risk，但其代码裁决保存在本 artifact、proposal 与双路 reviews 中。
