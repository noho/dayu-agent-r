# WU-CTX-02 + WU-CTX-03 Slice C Code Review Controller Adjudication

## Gate / Scope

- Work unit: WU-CTX-02 + WU-CTX-03.
- Gate: implementation Slice C code review.
- Slice scope: proactive deterministic recent-window fallback for compact failure before ordinary dispatch.
- Design source: `docs/host/design.md`, especially section 1 and section 25 Context Governance.
- Control source: `docs/host/host-core-followup-implementation-control.md`.
- Approved plan: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`.
- Implementation artifact: `docs/reviews/wu-ctx-02-03-implementation-sliceC-codex-20260601.md`.
- Review artifacts:
  - `docs/reviews/wu-ctx-02-03-code-review-sliceC-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-review-sliceC-ds-20260601.md`

## Controller Position

本裁决只处理 controller work：阅读实现、审查 artifact 和设计真源，裁决 findings，记录 gate 结论。未直接修改 Slice C source / tests / runtime behavior。

## Review Summary

AgentMiMo 结论为 Accepted / No blocking findings。其 6 条 findings 均为 observation：SQL 表名常量拼接、`already_represented` 必保留语义、selection failure budget payload 的诊断 decision 字段、当前 input anchor 排除后由 RunInputBuilder 追加、测试阈值常量、fallback dispatch 写入 `RUN_STARTED` 的既有路径确认。

AgentDS 结论为 Accepted / No blocking findings。其审查确认 selection、payload/digest、budget re-estimate、RunInputBuilder fallback provider、proactive dispatch/fail-closed 状态机、测试和 README 同步均符合 approved plan 与设计真源。

## Finding Adjudication

| Finding | 裁决 | 理由 |
|---|---|---|
| MiMo F-01: `EventLogContextFallbackProvider` SQL 使用 `TABLE_EVENT_LOG` f-string | accepted-as-observation | `TABLE_EVENT_LOG` 是 Host durable schema 常量，不是用户输入；该写法与现有 durable SQL 风格一致，不引入注入或维护风险。 |
| MiMo F-02: `_required_block_ids` 包含 `already_represented` blocks | accepted-as-observation | 设计要求保留 stable / compact represented context；`already_represented` 正是 material view 对 compact represented block 的 typed 标记，符合第一性原理和当前 material contract。 |
| MiMo F-03: selection failure budget payload 的 `decision` 为 `fail_closed` | accepted-as-observation | selection failure 是 fallback 诊断异常路径，不是 normal estimator decision；failed payload 只要求结构化 budget result 与最终 action，可读性高于伪造 `ContextBudgetDecision`。 |
| MiMo F-04: fallback context 排除 current input anchor | accepted-as-observation | 当前输入必须由 RunInputBuilder 的正常 user message anchor 追加，排除 material anchor 可避免重复，同时保持普通 dispatch request shape。 |
| MiMo F-05: 测试 hard threshold prompt 长度常量 | accepted-as-observation | 测试使用模块级常量表达阈值 fixture，且与既有 soft threshold helper 风格一致，不属于生产魔法数字。 |
| MiMo F-06: fallback dispatch 调用 `_start_governed_in_transaction` | accepted-as-observation | 该既有方法负责写 `RUN_STARTED` / pending dispatch；事件顺序符合 design section 25 对 proactive fallback 的要求。 |
| DS: No blocking findings | accepted | DS 的检查覆盖设计、AGENTS、测试和 README 职责，未提出需要修改的 finding。 |

## Design Compliance

Slice C 符合设计真源：

- Context Governance 仍是 compact / fallback orchestrator，未越过 Host 边界写 memory、audit、trace 或 projection。
- fallback 不是 compact success：不写 `CONTEXT_COMPACTED`，不写 compact artifact，不生成 episode summary、minimum preserve、pinned state patch 或 stable facts。
- fallback 只影响本次 RunInputBuilder bounded input view，并通过 `CONTEXT_COMPACTION_FAILED` 记录 failure reason、fallback policy decision、input window / digest、budget result 和 action。
- proactive fallback 发生在 dispatch 前，不是旧 Attempt orphan recovery，不进入 `RECOVERING`。
- fallback 预算通过才 dispatch；仍超过 hard threshold 或 selection failure 时 fail closed。
- 未新增 public N 配置、provider tokenizer、public `ContextBudgetPolicy` 字段、durable schema 或 Service-facing contract。

## Validation

Reviewer 验证：

- MiMo: `pytest tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q` -> 97 passed；targeted pyright -> 0 errors；full pyright -> 0 errors。
- DS: `pytest tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q` -> 97 passed；`python -m pyright dayu/ tests/ utils/` -> 0 errors。

Controller 将在 accepted commit 前复跑受影响测试和 full pyright。

## Residual Risk

- Reactive fallback recovery path 仍属于 Slice D，不阻塞 Slice C。
- fallback dispatch 后真实 provider 仍可能 overflow；由既有 reactive governance 与后续 Slice D / E 收口。
- proactive material source 仍沿用当前 proactive ordinary material view，本 Slice 不扩大 memory raw-turn source；该边界与 approved plan 一致。

## Final Decision

Accepted. Slice C code review gate passed. No fix / re-review loop required.
