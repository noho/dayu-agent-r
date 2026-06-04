# WU-CM-01 Plan Reslice Fix Report - AgentCodex

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | plan reslice fix |
| agent | AgentCodex |
| branch | `phaseflow/wu-cm-01` |
| design source | `docs/host/design.md` 第 24 章 / 第 25 章 |
| control source | `docs/host/issues-implementation-control.md` |
| current plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| implementation blocker | `docs/reviews/wu-cm-01-implementation-codex.md` |
| artifact | `docs/reviews/wu-cm-01-plan-reslice-fix-codex.md` |

## Decision

blocker 判断成立，plan 必须修订。

直接原因不是实现 agent 工作量不足，而是原 plan 把必须同源切换的 compact contract、operation event、memory durable / projection、prompt fallback 拆成概念域 Slice 1-5，并且允许 Slice 1-4 中间阶段全量 pyright 失败。这与 AGENTS 的修改后验证要求、用户本 gate 明确要求的每 slice pyright-clean，以及 blocker report 的直接证据冲突。

本 gate 已将 plan 改写为可编译、可验证、pyright-clean 的纵向闭环 slices。修订不修改生产代码、tests、README、control_doc，不进入 implementation / review gate。

## Plan Changes

已修改 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 删除并改写原 `Slice Verification Boundary` 中允许 Slice 1-4 中间全量 pyright 失败的表述。
- 将原概念域 Slice 1-6 改写为纵向闭环 Slice A-E：
  - Slice A：Compact Contract Closure。
  - Slice B：Compact Operation And Event Closure。
  - Slice C：Memory Durable And Projection Closure。
  - Slice D：Prompt And Fallback Closure。
  - Slice E：Public Smoke And Docs Closure。
- 每个新 slice 均列出目标、allowed files/modules、实现边界、旧路径保留 / 删除边界、不得引入的 compatibility wrapper / re-export / lazy import seam、测试命令、pyright 命令、退出信号和 residual risks。
- 将 Issue-80 / design 24.7 mapping 的 slice 列从旧数字映射更新为 A-E，同时保留原有评测维度、状态、测试入口和 deferred owner。
- 保留并重新落位以下已修好的 plan 规则：issue-80/design 24.7 映射、continuity / minimum preserve 到 reference continuity 的 vNext 迁移、vNext compact schema、旧 material block 到 vNext section mapping、quality checker source label / provenance / whole-candidate repair 规则。
- 更新 allowed files summary，补齐 `dayu/host/context_policy.py` 与条件性根 `README.md` 触发边界。

## New Slice Pyright-Clean Boundaries

| Slice | 闭环边界 | pyright-clean 规则 |
|---|---|---|
| A | vNext compact input/output、material section、strict parser、label provenance、contract tests | 旧 production operation 可原样存在，但不得新增 vNext-to-old wrapper；受影响 tests 后必须运行 `python -m pyright dayu/ tests/ utils/`。 |
| B | production compaction operation、event payload、quality gate、whole-candidate repair、fallback event tests | operation 一旦切到 vNext，所有 operation consumers / tests 同步迁移；旧 candidate merge / pinned patch / minimum preserve event 字段不得保留为兼容入口。 |
| C | memory snapshot、durable rows、projection catch-up / rebuild、schema tests | memory / durable 一旦切到 vNext，所有 production consumers / tests 同步迁移；旧库兼容读取、旧 item alias、旧 snapshot field codec 禁止。 |
| D | RunInputBuilder、fallback input view、dispatch 接线、prompt tests | prompt path 一旦切到 vNext，旧 stable block headers 和 renderer wrapper 删除；fallback 只渲染 bounded recent window 与 current input。 |
| E | public smoke、README 同步、issue-80 mapping 复核 | public smoke 与 README 不保留旧术语作为新路径说明；最终运行 `pytest tests/host -q`、public smoke 和全量 pyright。 |

每个 slice 的共同退出条件为：受影响测试通过，全量 pyright 不新增或扩散错误，已切换路径的 production consumers 与 tests 同步迁移，residual risks 已分类并有 owner。

## Validation

本 gate 按用户要求不跑测试、不跑 pyright，只做只读核对：

```bash
git branch --show-current
git status --short
rg -n "Slice [1-6]|pyright 失败|不承诺|最早必须恢复|全量 pyright 失败" docs/host/wu-cm-01-conversation-memory-plan.md
```

核对结果：

- 当前分支：`phaseflow/wu-cm-01`。
- plan 中不再残留允许中间 slice 全量 pyright 失败的表述。
- plan 中不再残留旧 `Slice 1` 到 `Slice 6` 引用。
- 工作区已有非本 gate 文件状态：`docs/host/issues-implementation-control.md` 为 modified，`docs/reviews/wu-cm-01-implementation-codex.md` 为 untracked。本 gate 未修改它们。

## Changed Files

本 gate 修改 / 新增：

- `docs/host/wu-cm-01-conversation-memory-plan.md`
- `docs/reviews/wu-cm-01-plan-reslice-fix-codex.md`

本 gate 未修改：

- 生产代码
- tests
- README
- `docs/host/issues-implementation-control.md`

## Residual Risks

| 风险 | 分类 | Owner / Destination | 说明 |
|---|---|---|---|
| Conversation Memory vNext 尚未实现 | covered by later approved slice | WU-CM-01 implementation | 本 gate 只修订 plan；后续必须按 Slice A-E 实施并逐 slice 验证。 |
| 完整 Conversation Memory eval benchmark | assigned to later work unit | WU-CM-10 / GitHub Issue #80 | plan 保留可断言入口，不实现完整 eval runner。 |
| Cross-session User Profile Memory | assigned to later work unit | WU-CM-11 / GitHub Issue #115 | WU-CM-01 只固定不混入 session memory 的边界。 |
| Deep historical recall / semantic search | assigned to later work unit | GitHub Issue #39 | 当前 vNext session memory 不实现 recall / search / reranker。 |
| Provider-specific tokenizer adapter | assigned to later work unit | 后续 Context Governance 精确预算 work unit | WU-CM-01 保持 deterministic bounded policy，不实现 provider adapter。 |
| Fins fact grounding integration | assigned to later work unit | Fins integration work unit | memory snapshot 仍不得替代 accepted evidence / artifacts / Fins storage truth。 |

## Blocking Open Questions

当前没有 blocking open questions。

若后续 implementation 在 Slice A、B 或 C 发现第 24 / 25 章无法唯一裁决 public contract、durable schema、EventLog payload 或状态机语义，应停止 implementation，回到 design source / plan 修正，而不是在生产代码里新增兼容路径。

## Completion Status

状态：fixed for plan reslice gate。

按 stop condition，本 gate 到 plan 修订和 fix report 产出为止，不进入 implementation、review、commit、push、PR 或 merge。
