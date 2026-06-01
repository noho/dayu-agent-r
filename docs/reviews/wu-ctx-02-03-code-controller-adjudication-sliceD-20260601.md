# WU-CTX-02 + WU-CTX-03 Slice D Code Review Controller Adjudication

## Gate / Scope

- Work unit: WU-CTX-02 + WU-CTX-03.
- Gate: implementation Slice D code review / fix / focused re-review.
- Slice scope: reactive compact failure deterministic recent-window fallback recovery path.
- Design source: `docs/host/design.md`, especially section 1 and section 25 Context Governance.
- Control source: `docs/host/host-core-followup-implementation-control.md`.
- Approved plan: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`.
- Implementation artifact: `docs/reviews/wu-ctx-02-03-implementation-sliceD-codex-20260601.md`.
- Review artifacts:
  - `docs/reviews/wu-ctx-02-03-code-review-sliceD-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-review-sliceD-ds-20260601.md`
- Fix artifact: `docs/reviews/wu-ctx-02-03-fix-sliceD-codex-20260601.md`.
- Focused re-review artifacts:
  - `docs/reviews/wu-ctx-02-03-code-rereview-sliceD-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-rereview-sliceD-ds-20260601.md`

## Controller Position

本裁决只处理 controller work：阅读实现、review、fix 与 re-review artifact，依据设计真源裁决 findings，并记录 gate 结论。source / tests / README fix 已由 implementation agent 完成，controller 未直接修改 specialist code。

## Review Summary

AgentMiMo 结论为 Accepted with findings，只有一个 INFO 级 docstring 缩进 finding，无 blocking findings。AgentDS 结论为 Accepted，提出一个 LOW 级 docstring 缩进 finding和一个 INFO 级私有常量重复 observation。两份 review 均确认 Slice D 满足设计目标：reactive compact final failure 可写 `CONTEXT_COMPACTION_FAILED(fallback_action=dispatch)` 后创建新的 recovery Attempt，不写 `CONTEXT_COMPACTED`、compact artifact 或 memory projection；fallback over-budget / selection failure 收口为 `RUN_FAILED`，不写 `RUN_LOST`。

AgentCodex 已修复 docstring 缩进。MiMo / DS focused re-review 均 Passed，确认修复为纯格式变更，无新 findings。

## Finding Adjudication

| Finding | 裁决 | 理由 |
|---|---|---|
| MiMo / DS: `_fallback_selection_failure_reason` docstring `:param` / `:returns` 缩进不一致 | accepted-fixed | AGENTS 要求中文 docstring 完整且项目风格需一致；该 finding 虽不影响行为，但修复成本极低，已由 Slice D fix 修正并通过 focused re-review。 |
| DS Finding 2: `_FALLBACK_ACTION_NOT_APPLICABLE` 私有常量在多个模块重复 | deferred-with-owner | 当前重复来自 Slice B/C 已采用的模块私有默认值模式，三处值一致且不影响本 Slice correctness；在本 Slice 为避免无关重构和跨模块 public constant 设计，暂不处理，交给 aggregate review 判断是否需要后续 cleanup owner。 |

## Design Compliance

Slice D 符合设计真源：

- reactive path 在 Engine overflow 后由 Host 校验 attempt / execution identity，关闭旧 Attempt，让 Run 进入 `RECOVERING`，然后由 Host Context Governance 决定 compact / fallback 结果。
- fallback dispatch 不是 compact success：不写 `CONTEXT_COMPACTED`，不写 compact artifact，不触发 memory projection materialization。
- fallback dispatch 通过既有 `StartRecoveryRunInput(context_compacted_event_id=None, context_compacted_event_sequence=None)` 启动新的 recovery Attempt；这使用的是 durable transition 已支持的无 compact event 关联语义，不伪造 compacted event。
- fallback fail closed、over-budget 或 selection / estimate failure 均收口为 `RUN_FAILED`，不写 `RUN_LOST`。
- reactive count limit / unreadable count / precondition failure 仍走既有 fail-closed 路径，不突破 `max_reactive_compactions_per_run`。
- 未修改 durable schema、`dayu/host/durable/run_transition.py`、`RUN_STARTED` required payload、Service-facing public API、EngineEvent schema、`ContextBudgetPolicy` public field 或 execution profile schema。

## Validation

Implementation / review / fix / re-review 已记录以下验证：

- `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q` -> 100 passed。
- `python -m pyright dayu/ tests/ utils/` -> 0 errors。

Controller 将在 accepted commit 前复跑受影响测试和 full pyright。

## Residual Risk

- `RR-CTX-SLICEB-01` 仍 deferred-with-owner：reactive `context_budget_policy_missing` / `input_event_missing` precondition 集成覆盖未在 Slice D 扩展。当前路径仍 fail closed、不 fallback dispatch、不写 `RUN_LOST`；aggregate review 再裁决是否需要额外 hardening。
- `_FALLBACK_ACTION_NOT_APPLICABLE` 私有常量重复为 INFO 级维护风险，不阻塞 Slice D；aggregate review 可决定是否追踪到后续 cleanup。
- fallback dispatch 后真实 provider 仍可能再次 overflow，交由 Slice E repeated-overflow E2E 验证收口。

## Final Decision

Accepted. Slice D code review / fix / focused re-review gate passed. Ready for accepted local commit.
