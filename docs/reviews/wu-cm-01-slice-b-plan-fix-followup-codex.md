# WU-CM-01 Slice B Plan Fix Follow-up

日期：2026-06-04

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B plan fix follow-up |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan fix artifact | `docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-controller-adjudication.md` |
| updated plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| artifact path | `docs/reviews/wu-cm-01-slice-b-plan-fix-followup-codex.md` |

## 动机判断

动机成立，且严重性没有被高估。本 gate 不改变 Slice B 的目标，只消除 implementation gate 会遇到的四个边界歧义：`engine_ingest.py` 非 closeout 旧类型残留、proactive subsequent run input 测试归属、reactive vNext artifact 写入策略、以及直接覆盖 `engine_ingest.py` reactive compaction path 的测试文件归属。

这些问题均来自 re-review 与 Controller 裁决的直接证据，不是新增 scope。若不补 plan，下一轮 implementation agent 可能为了 pyright、测试或 artifact 写入路径自行扩大修改范围，或复制 vNext artifact 构造逻辑，从而偏离 Slice B 只关闭 operation / event / artifact closeout 的边界。

## 落实内容

已修改 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- A1：明确 `engine_ingest.py` 内非 reactive closeout 路径仍使用的旧 import / annotation 可以原样保留；Slice B 清理只限 reactive closeout 迁移后 unused 的 import / annotation，不得修改非 closeout 函数签名或实现。
- A2：明确 Slice B 可以调整 `test_multi_turn_proactive_compact_feeds_subsequent_run_input`，使其只断言 proactive operation / event closeout；subsequent RunInputBuilder consumption、memory section 渲染和 compacted view 被后续 Run 消费的断言归 Slice D。
- A3：明确 reactive `engine_ingest.py` 不得继续使用旧 `CompactArtifactWriteRequest` 写 vNext artifact；vNext artifact JSON / payload ref / descriptor metadata helper 应抽到 allowed shared module，优先 `dayu/host/compact_payload.py`，并由 `dispatch.py` 与 `engine_ingest.py` 复用。
- A4：将 `tests/host/test_engine_ingest_mapping.py` 加入 Slice B allowed tests，范围限 reactive compaction closeout / fake compactor vNext 迁移；同步加入 Slice B 测试命令、退出信号、全局测试矩阵和最终验证命令。

已修改 `docs/host/issues-implementation-control.md`：

- 将当前 implementation status 更新为 `slice-b-plan-fix-follow-up`。
- 将 next entry point 更新为 `WU-CM-01 Slice B implementation gate`。
- 在 review artifact 索引中加入 Slice B plan fix re-review、Controller adjudication 与本 follow-up artifact。
- 在 WU-CM-01 状态段记录本 follow-up 已落实的四项 accepted clarification。

## 未触碰代码

本 gate 只修改允许范围内的文档 artifact：

- 未修改 production code。
- 未修改 tests。
- 未提交 commit。
- 未 push。

当前 workspace 中已有未验收 Slice B partial implementation code / test edits，本 gate 不裁决其正确性，也不回滚或继续修改这些文件。

## 验证

未运行 pytest 或 pyright。原因是本 gate 明确禁止修改 production code 或 tests，且当前 workspace 包含未验收 partial implementation；运行结果会混入未接受代码状态，不能作为本 plan follow-up gate 的验收信号。

本 gate 完成的验证是文档层核对：

- 四项 Controller accepted findings 均已写入 Slice B plan 的对应 allowed files、实现边界、旧路径边界、测试命令、退出信号和全局测试矩阵。
- Slice B 仍只关闭 operation / event / artifact closeout，不提前要求 memory projection、durable snapshot 或 RunInputBuilder 消费 vNext compact event。
- 禁止旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload、untyped event payload 的约束未放松。
- `dayu/host/compact_payload.py` 已作为共享 helper 优先位置存在于 Slice B allowed files 内，不需要新增 production module。

## Residual Risks

- 下一轮 Slice B implementation 仍需基于修正后的 plan 处理当前 partial implementation，决定保留、重做或继续修复；本 artifact 不验收现有代码。
- `engine_ingest.py` reactive failed closeout 若在实现中发现需要超出 event closeout 的状态机或 public contract 变更，应停止实现并回到 design / plan gate。
- Slice C 仍负责 vNext compact event 到 memory durable / projection 的 materialization。
- Slice D 仍负责 RunInputBuilder / subsequent run input / fallback prompt assembly 的 vNext 消费闭环。

## Completion Status

Slice B plan fix follow-up complete。下一步入口为 WU-CM-01 Slice B implementation gate；进入实现前应以本 artifact 与更新后的 plan 为边界，不提交、不 push 当前文档变更之外的未验收 partial implementation。
