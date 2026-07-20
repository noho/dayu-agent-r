# WU-CLI-SMOKE-01-R1 Plan Re-Review Controller Adjudication

## Gate 结论

- Work unit：`WU-CLI-SMOKE-01-R1 Engine Delta Transient Live Stream Remediation`
- Plan-fix artifact：`docs/reviews/wu-cli-smoke-01-r1-plan-fix-codex.md`
- Re-review artifacts：
  - `docs/reviews/plan-review-20260720-233342.md`（AgentMiMo）
  - `docs/reviews/plan-review-20260720-233259.md`（AgentDS）
- 两路 conclusion：均为 `pass`
- Controller decision：`accepted-plan`
- 下一 gate：`accepted plan commit`

## Accepted Findings 关闭状态

| 项 | Controller 裁决 | AgentMiMo | AgentDS | 最终状态 |
|---|---|---|---|---|
| A：Slice 1 内部 S1-A/B/C 顺序、handoff invariant 与验证点 | accepted；只允许同一原子 slice 内分步，不允许中间 accepted commit | fixed | fixed | closed |
| B：Service bounded relay 唯一 owner、terminal-only 排除与完整 backpressure 链 | accepted | fixed | fixed | closed |
| C：attach/cursor typed failure timing 与全部 cleanup path | accepted | fixed | fixed | closed |
| D：Event/Queue wakeup 与真实 Host→Service→CLI slow-consumer 当前 acceptance | accepted | fixed | fixed | closed |
| E：semantic ownership、三类 zero-row、multi-watcher 与非目标保持 | required invariant | fixed，无回归 | fixed，无回归 | closed |

两路均确认 Host closable iterator 共同拥有 cursor future 与 subscription，解决 never-started async generator 的 `finally` 不执行问题；Service live relay 由 `_WatchAndWaitRuntime` factory 唯一构造，当前三个 watcher path 纳入 bounded policy，已终态且无 watcher 的 terminal-only queue 明确排除。

## 新 Finding 与 Open Question

- 新 material finding：无。
- Blocking open question：无。
- Plan 状态：`code-generation-ready`。

## Residual Risk

- capacity 256 的真实负载调优：`deferred-with-owner`，归未来 Host transient observability/capacity work unit；不阻塞当前正确性实现。
- 单 delta 大小沿用 Engine contract：`accepted` 既有边界；当前不新增截断语义。
- 跨进程、Host restart、reconnect replay：`rejected-with-reason` 作为当前缺陷；属于用户已确认的非目标。
- readiness 竞态、高量 fanout、slow-consumer 与 cleanup：不再作为未归属 residual；由当前 WU Slice 2 的独立 implementation/review acceptance owner 负责验证。

## Accepted Plan Commit Scope

Accepted plan commit 只包含本 WU 的 goal、Host design 真源、plan、两路 plan review、controller adjudication、plan-fix、两路 re-review、本裁决与总控状态；不包含生产代码、测试、push 或 PR 动作。
