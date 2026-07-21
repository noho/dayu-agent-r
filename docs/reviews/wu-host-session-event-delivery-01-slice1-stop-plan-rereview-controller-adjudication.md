# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Stop Plan Amendment Re-review Controller Adjudication

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`plan-rereview-after-slice1-stop`
- 原 accepted plan commit：`8b29462c`
- Stop adjudication：`docs/reviews/wu-host-session-event-delivery-01-slice1-stop-condition-controller-adjudication.md`
- AgentCodex plan fix：`docs/reviews/wu-host-session-event-delivery-01-slice1-stop-plan-fix-codex.md`
- AgentMiMo re-review：`docs/reviews/plan-review-20260721-200106.md`
- AgentDS re-review：`docs/reviews/plan-review-20260721-200058.md`

## 独立性核验

原 AgentMiMo 与 AgentDS 在独立清理后的会话中并行执行 `$planreview`。两路均只审查 accepted plan commit `8b29462c` 之后的 plan amendment、共同 stop adjudication、AgentCodex fix artifact、AGENTS.md 与 4 个 `utils/` 文件的真实 direct callsites；均明确未读取对方本轮 artifact，也未修改 plan、代码、测试或总控。

## 逐项裁决

| 项目 | Controller 裁决 | 直接证据 |
|---|---|---|
| Caller 闭集 | `closed` | `utils/` 中共 4 个文件、5 个 `host.watch_session_events(...)` callsites；全部将同步 factory 返回值直接传给 async iterator consumer。 |
| Owner-boundary fix | `closed` | Async activation contract 由 `dayu.host.api` 拥有；caller 显式 `await` 是正确消费方式，不能在下游兼容 coroutine。 |
| Allowed scope | `closed` | Plan 只授权现有 direct callsites 的机械 async/public iterator 传播，明确禁止修改 smoke 场景、断言、数据流、Service relay或其它行为。 |
| Compatibility 禁令 | `closed` | Plan 禁止同步 compatibility、lazy attach、下游 coroutine 识别、`cast`/`getattr` shim。 |
| Validation | `closed` | 4 个脚本纳入 `py_compile`、完整 pyright 与 `dayu tests utils` source scan。 |
| Coverage | `closed` | `utils/` 按 AGENTS.md 默认无需新增测试/单文件 coverage；plan 明确不降低任何 production/test coverage acceptance。 |
| Service/CLI fake typing | `closed` | `__aiter__` 精确 public iterator return type 修复仍属于原 S1 mechanical propagation scope。 |
| Frozen decisions | `closed` | Item-only、packaged `512/4`、不设 byte bound、S2-S4 scope 与 4-slice dependency graph 均未改变。 |

两路 reviewer 对全部项目均独立给出 closed/pass，无新 material finding。Controller 复核 plan diff 与实际 5 个 callsites 后逐项接受，不以多数票替代证据裁决。

## Residual risk 与 open questions

- 本 amendment 未产生新 residual risk。
- 上一 plan gate 已接受的 callback 任意代码无限阻塞物理保证边界保持不变。
- Blocking open questions：`None`。

## Gate 决定

`accepted-plan-amendment`

Controller 将只提交 plan/control/review artifacts，不提交暂停中的 implementation changes。提交后恢复 `implementation-slice-1`，由 AgentCodex 仅完成 4 个 `utils/` mechanical await、已授权 fake typing fix 与剩余 S1 validation/README audit；仍不得进入 S2-S4。
