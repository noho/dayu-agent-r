# WU-HOST-SESSION-EVENT-DELIVERY-01 Plan Re-review Controller Adjudication

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`plan-rereview`
- Controller：Phaseflow Controller
- 设计真源：`docs/host/design.md`
- Plan：`docs/host/wu-host-session-event-delivery-01-plan.md`
- AgentMiMo re-review：`docs/reviews/plan-review-20260721-191912.md`
- AgentDS re-review：`docs/reviews/plan-review-20260721-192031.md`

## 独立性与范围核验

AgentMiMo 与 AgentDS 在独立清理后的会话中并行执行 `$planreview`。两路 reviewer 只读取各自上一轮 review、共同 Controller 裁决、AgentCodex fix artifact、修订后的 plan 与设计真源；均明确未读取对方本轮 re-review artifact。两路均只写各自 review artifact，没有修改 plan、设计、总控或代码。

本轮只裁决上一轮已接受 finding 的闭环状态、新 material finding、被拒绝方案是否被错误写回，以及用户对 item-only capacity 的明确裁决是否保持。

## Accepted finding 闭环裁决

| Finding | Controller 最终裁决 | 直接证据 |
|---|---|---|
| MIMO-001 | `closed` | S1 逐名冻结 `entrypoint_runtime.py` 旧 relay symbols，只传播 async factory/public iterator contract；S4 是 relay 与 exact-five 状态机的唯一语义修改 slice。 |
| MIMO-002 + DS-F2 | `closed` | Plan 固定 inert scheduler → typed factory/coordinator → one-shot bind → critical tasks start；失败时 tasks 从未启动；Host close 先 stop/await 全部 producer，再 close coordinator，最后 close delivery owner。 |
| MIMO-003 narrowed | `closed` | Service 定义精确 typed callback execution port；CLI lifecycle 拥有私有单线程 executor 和 submit-before serial gate；不使用 event-loop default executor，不共享给 Host/runtime/其它 watcher。 |
| DS-F1 | `closed` | Periodic reconciliation 仅由 sole iterator 当前 `__anext__()` readiness wait timeout 分支驱动，每次最多一页，不创建 per-watcher timer/background task。 |
| DS-F4 | `closed` | 双 opener fixture 被精确限制在 `tests/host/test_watch_session_events.py`，使用两个独立 `open_host` context 共享 DB/lane DB options，并冻结 no-local-notice barrier 与 cleanup 顺序。 |
| DS-F5 | `closed` | Caller finally 顺序固定为拒绝新 display work、等待当前 job、同一 executor 串行 renderer close、shutdown executor、释放 caller-local resources，并要求 deterministic ordering test。 |
| DS-F6 | `closed` | No-backpressure 承诺限定在 Host publisher、Agent/Engine、terminal commit、promotion 与其它 watcher；慢 callback 只减速当前 consumer，并可能触发当前订阅 item overflow。 |
| DS-O1 | `closed` | Static manifest 不按 composition path 排除 standalone producer；standalone command handle 显式注入 Host-private no-local-delivery port，并由 runtime recording fake 验证 exact notice 调用。 |

两路 reviewer 对以上 8 项均独立给出 closed，证据与修复要求一致；Controller 逐项复核 plan 对应段落后接受闭环，不以多数票替代证据裁决。

## Rejected finding 边界裁决

- DS-F3 继续为 `rejected-with-reason`。Plan 未加入 timeout-abandon。Python thread job 不能被安全取消；在 timeout 后继续 cleanup 会允许仍运行 callback 迟到触碰已关闭 renderer/iterator，破坏串行 lifecycle。当前 contract 保持 callback 快速、同步、非阻塞，测试使用可释放 barrier 证明执行域隔离与最终严格 cleanup。
- DS-O2 继续为 `rejected-with-reason`。Plan 保留精确旧语义 source scan，没有扩展为会误报真实 availability owner 的宽泛组合扫描。

## 用户容量裁决核验

- Retention 只按 item 计数：`mailbox_items + counted in_flight`。
- Public policy 只有 `transient_mailbox_max_items` 与 `max_subscriptions_per_session`。
- Packaged defaults 固定为 `512` 与 `4`。
- 不增加 `transient_mailbox_max_bytes`、逐事件 byte traversal/accounting、oversized/byte-full taxonomy、容量 dimension 字段或 resident-heap safety-margin acceptance。
- 不提供 logical-byte 或 Python resident heap 上界；该 residual risk 已由用户明确接受。

两路 reviewer 均确认上述裁决保持不变。

## 新 finding 与 residual risk

- AgentMiMo：无新 material finding。
- AgentDS：无新 material finding。
- Callback 任意代码无限阻塞仍是物理保证边界；它不是 implementation blocker，也不得以 timeout-abandon 伪修复。本 WU 仍必须证明慢 callback 不阻塞 Host publisher、Agent、Engine、terminal commit、promotion或其它 watcher，并在 barrier 释放后严格 cleanup。
- Blocking open questions：`None`。

## Gate 决定

`accepted-plan`

Plan 已达到 code-generation-ready：设计 owner、4 个依赖有序语义 slices、allowed scope、failure/release paths、deterministic barriers、测试矩阵、README audit、完整 pyright 与 coverage acceptance 均明确。下一入口为 AgentCodex 实施 Slice 1；Controller 在派发前提交 accepted plan 基线。
