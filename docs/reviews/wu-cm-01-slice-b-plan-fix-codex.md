# WU-CM-01 Slice B Plan Fix / Reslice

日期：2026-06-04

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B plan fix / reslice |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-b-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-b-blocker-controller-adjudication.md` |
| artifact path | `docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md` |

## 动机判断

动机成立。Slice B 的目标不是被高估，而是 accepted plan 对生产 owner 的 allowed-files 边界判断不完整。

直接证据是 reactive accepted compaction closeout 的生产路径位于 `dayu/host/engine_ingest.py`：该路径负责把 reactive operation accepted result 收口为 compact artifact 与 `CONTEXT_COMPACTED` event。原 Slice B 要求 accepted / rejected / failed compaction 都形成 vNext 事件闭环，却没有允许修改 `engine_ingest.py`，因此 implementation agent 无法在不越界的情况下完成 reactive accepted closeout。

同时，proactive subsequent run input failure 不是 Slice B 应修问题。该断言要求 memory projection / durable snapshot / RunInputBuilder 已消费 vNext compacted payload，而 accepted plan 已把这些行为分别交给 Slice C / D。若在 Slice B 通过旧 payload compatibility fields、projection shim、old candidate adapter 或 extra payload 字段解决，会违反 WU-CM-01 的 root-cause 修复方向。

## 修改内容

已修改 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 在 Slice B allowed files 中加入 `dayu/host/engine_ingest.py`，范围严格限制为 reactive accepted compaction event / artifact closeout。
- 明确 `engine_ingest.py` 不得在 Slice B 修改 Engine event ingest 的其它状态机、projection catch-up、RunInputBuilder 调用或旧 payload 兼容路径。
- 明确 proactive closeout 只验证 operation 编排、accepted / failed event payload、artifact descriptor 与 fallback 行为，不要求 accepted compacted event 已被 subsequent RunInputBuilder 消费。
- 明确 reactive accepted closeout 只允许把 accepted vNext operation result 写成 vNext compact artifact 与 `CONTEXT_COMPACTED` payload，并保持 reactive recovery attempt / execution closeout 语义。
- 明确 subsequent run input、memory projection、durable snapshot materialization、post-compact delta 和 RunInputBuilder 对 vNext payload 的消费断言属于 Slice C / D。
- 明确 Slice B 不得通过旧 payload compatibility fields、projection shim、old candidate adapter、额外 payload 字段或旧 compacted payload 字段让 Slice C / D 断言提前通过。
- 更新 Slice B 退出信号：proactive accepted / failed closeout 与 reactive accepted / failed / fallback closeout 都能形成 vNext event / artifact / state transition 闭环，但测试断言停在 operation/event closeout。
- 同步更新全局 allowed files / modules summary，把 `dayu/host/engine_ingest.py` 纳入 Slice B 的受限允许范围。

已修改 `docs/host/issues-implementation-control.md`：

- 在当前状态的 review artifact 索引中加入本 plan-fix artifact，便于后续 plan re-review / controller adjudication 追踪。

## 未触碰代码

本 gate 只修改 plan / review artifact：

- 未修改 production code。
- 未修改 tests。
- 未提交 commit。
- 未 push。

当前 workspace 中已有 Slice B partial code / test edits 仍不是 accepted implementation output。本 artifact 不裁决这些代码是否应保留，只修正后续 implementation gate 的 plan 边界。

## 验证

未运行 pytest 或 pyright。原因是本 gate 明确只允许修改 plan/docs artifact，不允许继续修改 production code 或 tests；当前 workspace 还包含未验收的 Slice B partial implementation edits，运行结果会混入未接受实现状态，不能作为本 plan-fix gate 的验收信号。

已完成的验证是文档层核对：

- Slice B allowed-files 边界现在覆盖 blocker 裁决中指出的 reactive accepted closeout owner。
- Slice B 测试边界保留 operation/event/proactive/reactive closeout 可验证闭环。
- Slice B 明确排除 memory durable/projection、RunInputBuilder consumption 和 proactive subsequent run input 断言。
- 禁止兼容 wrapper / re-export / lazy import / extra payload / untyped event payload 的约束未放松。

## Residual Risks

- `docs/host/wu-cm-01-conversation-memory-plan.md` 仍需进入 plan re-review / controller adjudication 后才能成为新的 accepted Slice B implementation guide。
- 当前 workspace 的 Slice B partial code / test edits 未经过本 gate 验收；下一轮 implementation gate 需要基于修正后的 plan 决定保留、重做或继续修复。
- Slice C 仍负责 vNext compact event 到 memory durable / projection 的 materialization；Slice B 不关闭该风险。
- Slice D 仍负责 RunInputBuilder / subsequent run input / fallback prompt assembly 的 vNext 消费闭环；Slice B 不关闭该风险。
- 若下一轮 implementation 发现 `engine_ingest.py` 的 reactive closeout 需要修改超出 event / artifact closeout 的状态机或 public contract，应停止实现并回到 design / plan gate，而不是扩大 Slice B。

## Completion Status

Slice B plan-fix artifact complete。下一步应进入 plan re-review / controller adjudication；在该 gate 接受前，不应提交或继续实施 Slice B production code。
